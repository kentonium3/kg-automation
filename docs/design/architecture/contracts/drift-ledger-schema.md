---
title: Drift-Ledger JSONL Schema
doc_type: reference
status: approved
---

# Contract: Drift-Ledger JSONL Schema (post-#403)

**Status**: Canonical live contract for the drift-events ledger row schema at `docs/design/architecture/contracts/drift-ledger-schema.md`. Code modules that implement this contract (notably `scripts/doc_audit/output/drift_ledger.py`) reference this file from their dataclass docstring. Schema changes must update this file in the same PR.

**File on disk**: `/data/services/security-monitor/logs/drift-events-ledger.jsonl` (office2)
**Writer module**: `scripts/doc_audit/output/drift_ledger.py`
**Dataclass**: `AuditLedgerEntry` (drift-ledger variant)
**Schema version**: `1` (NOT bumped — widening is additive and backward-compatible)

Append-only JSONL. One row per processed drift event. Operator-readable, machine-queryable.

---

## Row schema

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | int | yes | `1` for this contract; bumps on incompatible changes |
| `event_id` | string | yes | Composite `<cursor_line>:<timestamp>`, e.g., `"47:2026-05-22T03:00:07Z"` |
| `timestamp_utc` | string | yes | ISO 8601 UTC; when the verdict was finalized (NOT when the drift was detected) |
| `baseline` | string | yes | The audit.sh baseline name (e.g., `"openclaw-cron"`) |
| `mapping_id` | string | yes | The signal-to-doc-map.json mapping id (e.g., `"openclaw-cron-drift"`) |
| `verdict` | string | yes | `"PROPOSED_EDIT" \| "JUDGMENT_REQUIRED" \| "NO_CHANGE_NEEDED" \| "RETRY_EXHAUSTED"` |
| `confidence` | float \| null | yes | `[0.0, 1.0]`; `null` when verdict is `"RETRY_EXHAUSTED"` |
| `outcome` | string | yes | `"auto_committed" \| "pr_filed" \| "issue_filed" \| "auto_closed" \| "retry_exhausted"` |
| `doc_paths` | string[] | yes | Doc target paths involved (from the mapping's `doc_targets`) |
| **`retry_count`** | **int** | **yes** | **`[0, retry_max]`** where `retry_max = 1 + len(RETRY_DELAYS_SECONDS)`. Currently `retry_max = 4`. **CHANGED FROM `0..3` per #403** — widened to faithfully record the actual attempt count of the retry helper, including the final failing attempt. |
| `latency_ms` | int | yes | End-to-end including retries; from drift-event read to verdict finalize |
| `tier_classification_outcome` | string \| null | yes | `"tier_a" \| "tier_b" \| "judgment" \| null`; `null` when Moment 1 not invoked (NO_CHANGE_NEEDED / JUDGMENT_REQUIRED / RETRY_EXHAUSTED paths) |
| `github_issue_number` | int \| null | yes | Set when outcome includes a filed issue or PR |

### Source-of-truth for `retry_max`

`retry_max` is derived as `1 + len(RETRY_DELAYS_SECONDS)` where `RETRY_DELAYS_SECONDS` is the module-level constant in `scripts/doc_audit/judgment/drift_interpretation.py`. Currently `(30, 60, 120)` → `retry_max = 4`. Future changes to the retry policy automatically propagate to the schema bound.

### Serialization rules

- **One row per line**: each JSONL row is exactly one JSON object, terminated by `\n`
- **No embedded newlines**: strings with literal newlines (e.g., LLM rationales) MUST escape as `\n` per JSON spec
- **Field order**: writer emits fields in the order in `FIELD_ORDER` (see `output/drift_ledger.py`) for deterministic diffing; Python 3.7+ dict insertion order, `json.dumps(..., sort_keys=False)`
- **No trailing whitespace**: writer strips/omits trailing whitespace
- **UTC always**: all timestamps `Z`-suffixed; no local-tz mixing

### Atomicity

Append writes use `tempfile + rename` pattern when the ledger doesn't yet exist or is being rotated. Steady-state appends use `open(path, "a")` with `flush()` + `fsync()` — sufficient for the single-writer pipeline (one cron job at a time).

If two writers ever race: JSONL format is naturally append-safe; a torn write of one row corrupts that row but not the file.

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

### RETRY_EXHAUSTED (post-#403 — note `retry_count: 4`)

```json
{"schema_version":1,"event_id":"50:2026-05-22T03:00:10Z","timestamp_utc":"2026-05-22T03:04:12Z","baseline":"openclaw-cron","mapping_id":"openclaw-cron-drift","verdict":"RETRY_EXHAUSTED","confidence":null,"outcome":"retry_exhausted","doc_paths":["docs/design/architecture/data/service-inventory.json"],"retry_count":4,"latency_ms":242100,"tier_classification_outcome":null,"github_issue_number":376}
```

Pre-#403 rows would show `retry_count: 3` because the old clamp truncated `exc.attempts = 4` to `3`. Post-#403 rows show the actual attempt count.

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

### Retry-budget consumption (NEW post-#403)

```python
from collections import Counter
entries = read_window(days=7)
retry_dist = Counter(e.retry_count for e in entries if e.verdict == "RETRY_EXHAUSTED")
for count, n in sorted(retry_dist.items()):
    print(f"  retry_count={count}: {n} events")
# Useful for confirming the retry policy is doing what we expect.
# Pre-#403 all exhausted events would show retry_count=3; post-#403, retry_count=4
# is the expected value for events that hit the full retry budget.
```

---

## Rotation / archival

Out of scope for this contract. The ledger file grows append-only. At current drift volume (~10 events/day), the file grows ~5 KB/day or ~2 MB/year. Manual archival or rotation can be added in a future mission if size becomes operationally relevant.

---

## Backwards compatibility

The schema starts at `schema_version: 1`. Adding new optional fields without bumping schema_version is allowed (consumers MUST ignore unknown fields).

**Widening an existing field's accepted range is also backward-compatible**, provided no on-disk row in the wild has a value outside the new range. Per #403, no existing row has `retry_count > 3`; widening to `[0, retry_max]` therefore does not require a schema_version bump or migration.

Any future change that requires a schema_version bump MUST:

- Bump `schema_version` to `2`
- Document migration in a follow-on mission
- Ensure `read_window()` handles both versions during a transition period

---

## Change history

| Date | Mission | Change |
|---|---|---|
| 2026-05-22 | `drift-event-auto-resolution-01KS8J32` (#362) | Initial schema. `retry_count: [0, 3]` |
| 2026-05-24 | `drift-ledger-retry-count-hardening-01KSC6AJ` (#403) | Widened `retry_count` bound to `[0, retry_max]`. Lifted contract doc from mission archive to live arch docs. |
