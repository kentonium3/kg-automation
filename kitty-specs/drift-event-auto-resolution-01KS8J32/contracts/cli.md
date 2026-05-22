# Contract: CLI surface

**Mission**: `drift-event-auto-resolution-01KS8J32`
**Module**: `scripts/doc_audit/judgment/drift_interpretation.py`

Standalone CLI for the drift_interpretation judgment, mirroring the pattern in `scripts/doc_audit/judgment/tier_classification.py`. Two additional CLIs ship with the mission: `cutover_362.py` and `drift_ledger.py` (read-only queries).

---

## drift_interpretation CLI

### Invocation

```bash
python3 -m scripts.doc_audit.judgment.drift_interpretation \
    [--input-file PATH] \
    [--output-file PATH] \
    [--model MODEL] \
    [--api-key-path PATH] \
    [--timeout SECONDS]
```

### Flags

| Flag | Type | Default | Purpose |
|---|---|---|---|
| `--input-file` | path | stdin | E2 `DriftInterpretationContext` JSON to interpret |
| `--output-file` | path | stdout | E1 `DriftVerdict` JSON output target |
| `--model` | string | `claude-haiku-4-5-20251001` | Anthropic model identifier |
| `--api-key-path` | path | `/data/services/openclaw/secrets/anthropic` | API key file (mode 0600) |
| `--timeout` | int | `30` | Per-call timeout in seconds |
| `--no-retry` | flag | false | Disable retries (for testing failure paths) |

### Stdin/stdout JSON shape

**Input** (matches E2 `DriftInterpretationContext`):
```json
{
  "event_id": "47:2026-05-22T03:00:07Z",
  "timestamp_utc": "2026-05-22T03:00:07Z",
  "baseline": "openclaw-cron",
  "mapping_id": "openclaw-cron-drift",
  "mapping_rationale": "OpenClaw cron config drift implies service-inventory.json fields...",
  "diff": "...",
  "doc_targets": [
    {"path": "docs/design/architecture/data/service-inventory.json", "contents": "...", "truncated": false, "truncation_strategy": "full"}
  ]
}
```

**Output** (matches E1 `DriftVerdict`):
```json
{
  "verdict": "NO_CHANGE_NEEDED",
  "confidence": 0.90,
  "rationale": "service-inventory.json does not track deliveryMode field on cron entries; doc state is correct."
}
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success — verdict written |
| 1 | Operational error (API failure after retries, file unreadable, etc.) |
| 3 | Invalid input JSON (schema violation in E2) |
| 5 | Out-of-set proposed edit (LLM proposed doc_path outside mapping's doc_targets) |

Codes match the existing pattern (`scripts/doc_audit/judgment/tier_classification.py`).

---

## cutover_362 CLI

### Invocation

```bash
python3 scripts/doc_audit/helpers/cutover_362.py [--dry-run] [--force]
```

### Flags

| Flag | Type | Default | Purpose |
|---|---|---|---|
| `--dry-run` | flag | false | Print what would happen; no GitHub or filesystem mutations |
| `--force` | flag | false | Override the marker check; re-run cutover even if already done |

### Behavior

1. Check marker `~/.config/doc-audit/cutover-362.done` — if exists and `--force` not set, exit 0
2. Query GitHub: `gh issue list --repo kentonium3/kg-automation --search 'is:issue is:open label:P3-candidate "[doc-audit]" in:title' --json number,title`
3. For each result: comment + close
4. Reset drift-events cursor (call `handle_drift_events.py --reset-cursor` or write `.drift-events.cursor` to `0`)
5. Write marker file

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (or idempotent no-op) |
| 1 | GitHub API failure |
| 2 | Filesystem failure (cursor or marker write) |

---

## drift_ledger CLI (read-only queries)

### Invocation

```bash
python3 -m scripts.doc_audit.output.drift_ledger \
    {summary | tail | triage-rate} \
    [--ledger-path PATH] \
    [--days N]
```

### Subcommands

| Subcommand | Purpose |
|---|---|
| `summary` | Print verdict counts + outcome breakdown for last N days (default 7) |
| `tail` | Show last 10 ledger entries (pretty-printed JSON) |
| `triage-rate` | Compute and print `count(verdict=JUDGMENT_REQUIRED) / count(*)` for last N days — the NFR-001 metric |

### Flags

| Flag | Type | Default | Purpose |
|---|---|---|---|
| `--ledger-path` | path | `/data/services/security-monitor/logs/drift-events-ledger.jsonl` | Ledger file location |
| `--days` | int | 7 | Window for summary/triage-rate subcommands |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Ledger file unreadable |
| 3 | Invalid subcommand or flag |

---

## handle_drift_events (existing CLI — modified)

### New flags

| Flag | Type | Default | Purpose |
|---|---|---|---|
| `--reset-cursor` | flag | false | Reset cursor to 0 (called by cutover_362.py) |
| `--config-path` | path | `scripts/doc_audit/config.toml` | Override config file location |

### Existing flags unchanged

`--events`, `--cursor`, `--mapping`, `--unmapped`, `--repo` — all unchanged per C-002.

### New config.toml block

```toml
[drift_interpretation]
enabled = true                         # FR-012; toggle Moment 0 on/off
ledger_path = "/data/services/security-monitor/logs/drift-events-ledger.jsonl"  # D4
model = "claude-haiku-4-5-20251001"   # C-009
api_key_path = "/data/services/openclaw/secrets/anthropic"
timeout_seconds = 30                   # NFR-002 single-attempt P95 budget
confidence_threshold = 0.80            # PROPOSED_EDIT / NO_CHANGE_NEEDED gate
```
