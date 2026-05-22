# Contract: Ledger JSONL schema

**Mission**: `drift-event-auto-resolution-01KS8J32`
**File**: `/data/services/security-monitor/logs/drift-events-ledger.jsonl`

Append-only JSONL. One row per processed drift event. Operator-readable and machine-queryable.

---

## Row schema (E3 — AuditLedgerEntry)

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | int | yes | `1` for this contract; bumps on incompatible changes |
| `event_id` | string | yes | Composite `<cursor_line>:<timestamp>`, e.g., `"47:2026-05-22T03:00:07Z"` |
| `timestamp_utc` | string | yes | ISO 8601 UTC; when the verdict was finalized (NOT when the drift was detected) |
| `baseline` | string | yes | The audit.sh baseline name (e.g., `"openclaw-cron"`) |
| `mapping_id` | string | yes | The signal-to-doc-map.json mapping id (e.g., `"openclaw-cron-drift"`) |
| `verdict` | string | yes | `"PROPOSED_EDIT" \| "JUDGMENT_REQUIRED" \| "NO_CHANGE_NEEDED" \| "RETRY_EXHAUSTED"` |
| `confidence` | float \| null | yes | [0.0, 1.0]; `null` when verdict is `"RETRY_EXHAUSTED"` |
| `outcome` | string | yes | `"auto_committed" \| "pr_filed" \| "issue_filed" \| "auto_closed" \| "retry_exhausted"` |
| `doc_paths` | string[] | yes | Doc target paths involved (from the mapping's `doc_targets`) |
| `retry_count` | int | yes | 0..3 |
| `latency_ms` | int | yes | End-to-end including retries; from drift-event read to verdict finalize |
| `tier_classification_outcome` | string \| null | yes | `"tier_a" \| "tier_b" \| "judgment" \| null`; `null` when Moment 1 not invoked (NO_CHANGE_NEEDED / JUDGMENT_REQUIRED / RETRY_EXHAUSTED paths) |
| `github_issue_number` | int \| null | yes | Set when outcome includes a filed issue or PR |

### Serialization rules

- **One row per line**: each JSONL row is exactly one JSON object, terminated by `\n`
- **No embedded newlines**: strings with literal newlines (e.g., LLM rationales) MUST escape as `\n` per JSON spec
- **Field order**: writer emits fields in the order above for deterministic diffing (Python 3.7+ dict insertion order; `json.dumps(..., sort_keys=False)`)
- **No trailing whitespace**: writer strips/omits trailing whitespace
- **UTC always**: all timestamps `Z`-suffixed; no local-tz mixing

### Atomicity

Append writes use `tempfile + rename` pattern when the ledger doesn't yet exist OR is being rotated. Steady-state appends use `open(path, "a")` with `flush()` + `fsync()` — sufficient for the single-writer pipeline (one cron job at a time).

If two writers ever race (shouldn't happen, but defensive): the JSON-Lines format is naturally append-safe because each line is independently parseable. A torn write of one row corrupts that row but not the file.

---

## Example rows

### NO_CHANGE_NEEDED (auto-close)

```json
{"schema_version":1,"event_id":"47:2026-05-22T03:00:07Z","timestamp_utc":"2026-05-22T03:00:18Z","baseline":"openclaw-cron","mapping_id":"openclaw-cron-drift","verdict":"NO_CHANGE_NEEDED","confidence":0.92,"outcome":"auto_closed","doc_paths":["docs/design/architecture/data/service-inventory.json"],"retry_count":0,"latency_ms":11342,"tier_classification_outcome":null,"github_issue_number":null}
```

### PROPOSED_EDIT → Tier B PR

```json
{"schema_version":1,"event_id":"48:2026-05-22T03:00:08Z","timestamp_utc":"2026-05-22T03:00:36Z","baseline":"systemd-user-dropins","mapping_id":"systemd-user-dropins-drift","verdict":"PROPOSED_EDIT","confidence":0.88,"outcome":"pr_filed","doc_paths":["docs/design/architecture/data/service-inventory.json"],"retry_count":0,"latency_ms":28104,"tier_classification_outcome":"tier_b","github_issue_number":374}
```

### JUDGMENT_REQUIRED → issue filed

```json
{"schema_version":1,"event_id":"49:2026-05-22T03:00:09Z","timestamp_utc":"2026-05-22T03:00:22Z","baseline":"openclaw-json","mapping_id":"openclaw-json-hash-drift","verdict":"JUDGMENT_REQUIRED","confidence":0.45,"outcome":"issue_filed","doc_paths":["docs/design/architecture/data/service-inventory.json"],"retry_count":0,"latency_ms":13201,"tier_classification_outcome":null,"github_issue_number":375}
```

### RETRY_EXHAUSTED (fallback escalation)

```json
{"schema_version":1,"event_id":"50:2026-05-22T03:00:10Z","timestamp_utc":"2026-05-22T03:04:12Z","baseline":"openclaw-cron","mapping_id":"openclaw-cron-drift","verdict":"RETRY_EXHAUSTED","confidence":null,"outcome":"retry_exhausted","doc_paths":["docs/design/architecture/data/service-inventory.json"],"retry_count":3,"latency_ms":242100,"tier_classification_outcome":null,"github_issue_number":376}
```

---

## Query examples

### Triage rate over last 7 days

```python
from scripts.doc_audit.output.drift_ledger import read_window

entries = read_window(days=7)
total = len(entries)
escalated = sum(1 for e in entries if e.verdict == "JUDGMENT_REQUIRED")
rate = escalated / total if total else 0.0
print(f"Triage rate (7d): {rate:.1%}")  # NFR-001: target ≤30%
```

### Reliability rate (NFR-005)

```python
entries = read_window(days=7)
total = len(entries)
exhausted = sum(1 for e in entries if e.verdict == "RETRY_EXHAUSTED")
reliability = 1.0 - (exhausted / total) if total else 1.0
print(f"Reliability (7d): {reliability:.1%}")  # NFR-005: target ≥98%
```

### Outcome breakdown

```python
from collections import Counter
entries = read_window(days=7)
breakdown = Counter(e.outcome for e in entries)
for outcome, count in breakdown.most_common():
    print(f"  {outcome}: {count}")
```

---

## Rotation / archival

Out of scope for v1. The ledger file grows append-only. At current drift volume (~10 events/day), the file grows ~5KB/day or ~2MB/year. Manual archival or rotation can be added in a future mission if size becomes operationally relevant.

---

## Backwards compatibility

The schema starts at `schema_version: 1`. Any future change that requires migration MUST:

- Bump `schema_version` to 2
- Document migration in a follow-on mission
- Ensure `read_window()` handles both versions during a transition period

Adding new optional fields without bumping schema_version is allowed (consumers MUST ignore unknown fields per standard JSON forward-compatibility).
