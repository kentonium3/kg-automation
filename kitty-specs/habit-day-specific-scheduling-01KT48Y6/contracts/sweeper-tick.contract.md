# Contract: `sweeper-tick-<date>.json`

**Path**: `/data/services/openclaw/state/habits/sweeper-tick-<date>.json`
**Format**: JSON, single document, overwritten per-date if the sweeper re-runs the same date
**Producer**: `scripts/habits/sweeper.py`
**Consumer**: operator (manual `cat | jq`), future health-check tooling

## Schema

```json
{
  "schema_version": 1,
  "tick_id": "01KT4ABC7XYZ123456789DEFG",
  "started_at_utc": "2026-06-02T11:30:00Z",
  "duration_ms": 1230,
  "dry_run": false,
  "expired_checkin_dates_evaluated": ["2026-05-31"],
  "habits_evaluated": [
    {
      "task_id": 14,
      "original_checkin_date_et": "2026-05-31",
      "status": "completed_in_window"
    },
    {
      "task_id": 17,
      "original_checkin_date_et": "2026-05-31",
      "status": "auto_skipped_this_tick"
    },
    {
      "task_id": 18,
      "original_checkin_date_et": "2026-05-31",
      "status": "deferred_outside_48hr"
    }
  ],
  "habits_auto_skipped": [
    {
      "task_id": 17,
      "original_checkin_date_et": "2026-05-31",
      "original_designated_weekday": "Wed",
      "new_due_date_et": "2026-06-10T23:59:59-04:00"
    }
  ],
  "errors": [],
  "exit_status": "success"
}
```

## Field definitions

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Currently 1. Bump on breaking change. |
| `tick_id` | str (ULID) | Unique per tick. |
| `started_at_utc` | str (ISO 8601 with `Z`) | Sweeper start time. |
| `duration_ms` | int | Total tick wall-clock (extraction + evaluation + Vikunja PUTs + history append). |
| `dry_run` | bool | True when `--dry-run` passed; false in normal production. |
| `expired_checkin_dates_evaluated` | list[str] (YYYY-MM-DD) | Morning-checkin dates the sweeper considered "older than 48 hours, eligible for auto-skip." Always at least one entry per tick under normal cadence. |
| `habits_evaluated[]` | list of objects | All habits the sweeper considered. See enum below. |
| `habits_evaluated[].status` | enum | `completed_in_window` (Kent replied done within 48hr), `skipped_in_window` (Kent replied skip within 48hr), `already_auto_skipped` (prior sweeper tick already marked it; idempotent skip), `auto_skipped_this_tick` (this tick newly marked it), `deferred_outside_48hr` (still within 48hr window — defer to a future tick). |
| `habits_auto_skipped[]` | list of objects | Subset of `habits_evaluated` with `status == "auto_skipped_this_tick"`. |
| `habits_auto_skipped[].new_due_date_et` | str (ISO 8601 with explicit `-04:00` or `-05:00` offset, NOT `Z`) | The advanced Vikunja `due_date` for day-specific habits. Absent for daily habits. |
| `errors[]` | list of `{task_id, error_type, error_message}` | Per-habit failures. Empty list = clean tick. |
| `exit_status` | enum `{"success","partial","failure"}` | `success` = all habits resolved, no errors. `partial` = at least one habit errored but the tick completed. `failure` = sweeper aborted before processing all habits. |

## Health-check contract

A healthy tick has:
- `exit_status == "success"`
- `errors == []`
- `started_at_utc` within the last ~24 hours

If `exit_status != "success"` OR `started_at_utc` is older than 26 hours (cadence + slack), operator attention needed.

## Atomicity

Written via `<path>.tmp` + `os.rename(tmp, final)` to avoid partial-read window. Append-only ledger writes (`sweeper-ledger.jsonl`) use standard append + flush.

## Issue #112 regression-prevention

`habits_auto_skipped[].new_due_date_et` MUST be an explicit ET-offset ISO 8601 timestamp (e.g., `2026-06-10T23:59:59-04:00` or `2026-06-10T23:59:59-05:00`). The sweeper rejects any computed timestamp ending with `Z` (UTC) at exit-status `failure`. This mirrors `set_due_dates.py`'s `--iso-eod-et` guard.
