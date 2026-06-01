# Contract: `last-tick.json` (signal-extraction tick)

**Path**: `/data/services/openclaw/felix-core-digest-signals/last-tick.json`
**Format**: JSON, single document, overwritten atomically each cycle.
**Producer**: `scripts/openclaw/observation/tick.py`
**Consumer**: operator (manual `cat | jq`), future alerting integration (per #327 contract).

## Schema

```json
{
  "schema_version": 1,
  "cycle_id": "01J6XYZAB1234567890ABCDEFG",
  "started_at_utc": "2026-06-01T17:15:00Z",
  "duration_ms": 740,
  "exit_status": "success",
  "signals_evaluated": [
    {
      "signal_id": "whatsapp_creds_restore",
      "count_cycle": 12,
      "count_rolling": 35,
      "threshold_status": "tripped_both"
    },
    {
      "signal_id": "web_watchdog_reconnect",
      "count_cycle": 0,
      "count_rolling": 4,
      "threshold_status": "below"
    },
    {
      "signal_id": "openclaw_unhandled_error",
      "count_cycle": 0,
      "count_rolling": 0,
      "threshold_status": "below"
    }
  ],
  "issues_filed": [
    {
      "signal_id": "whatsapp_creds_restore",
      "issue_number": 491,
      "issue_url": "https://github.com/kentonium3/kg-automation/issues/491"
    }
  ],
  "issues_skipped_dedup": [],
  "errors": []
}
```

## Field definitions

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Bump on breaking schema change. Currently 1. |
| `cycle_id` | str (ULID) | Unique per cycle. Matches a row in `signals-ledger.jsonl`. |
| `started_at_utc` | str (ISO 8601, UTC, trailing Z) | Cycle start. |
| `duration_ms` | int | Total cycle duration, including all extraction + filing + state writes. |
| `exit_status` | enum `{"success", "partial", "failure"}` | `partial` when some signals errored but the cycle ran to completion. `failure` when the cycle aborted. |
| `signals_evaluated[].signal_id` | str | Matches a signal definition. |
| `signals_evaluated[].count_cycle` | int | Events matched in this 15-min cycle. |
| `signals_evaluated[].count_rolling` | int | Events matched in the rolling window. |
| `signals_evaluated[].threshold_status` | enum `{"below","tripped_cycle","tripped_rolling","tripped_both"}` | Which threshold(s) triggered, if any. |
| `issues_filed[].signal_id` | str | Signal that triggered the filing. |
| `issues_filed[].issue_number` | int | Numeric issue id from GitHub. |
| `issues_filed[].issue_url` | str | Full https URL. |
| `issues_skipped_dedup[].signal_id` | str | Signal that tripped but was suppressed. |
| `issues_skipped_dedup[].existing_issue_ref` | int | Number of the open issue blocking the new filing. |
| `errors[].signal_id` | str \| null | `null` for cycle-wide errors. |
| `errors[].error_type` | str | Short stable identifier (e.g., `"source_missing"`, `"gh_cli_failed"`, `"state_corrupt"`). |
| `errors[].error_message` | str | Free-form detail. |

## Health-check contract

A healthy tick has:
- `exit_status == "success"`
- `errors == []`
- `started_at_utc` within the last ~30 minutes (≤ 2 hours after recovery from a missed tick per systemd `Persistent=true`)

Stale or non-success ticks indicate operator attention is needed.

## Atomicity

The file is written via `<path>.tmp` + `os.rename(tmp, final)` so partial-write reads never happen. Consumers can poll the file without coordination.
