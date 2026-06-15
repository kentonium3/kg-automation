# Phase 1 Data Model: Trustworthy weekly habit report

This mission is read-only against the canonical `habits-history.jsonl` store. No new persistent entities are introduced. The data-model below covers (a) the existing entities the mission consumes, (b) the new in-memory return shapes the wrapper exposes, and (c) the new optional field added to `WeeklyHabitReport`.

## E-01 — `HabitCompletionRecord` (existing)

Single completion event in `/data/services/openclaw/state/habits-history.jsonl`. Schema is fixed by `scripts/common/state_log.py` validation per domain `"habits"`.

| Field | Type | Description |
| --- | --- | --- |
| `task_id` | int | Vikunja task ID for the habit |
| `date` | str (`YYYY-MM-DD`) | Wall-clock date of completion (America/New_York) |
| `state` | enum | `complete` \| `auto_skipped` \| (other `state_log_schema.DOMAIN_STATES` values) |
| `note` | str (optional) | Free-form note carried from the morning-checkin reply or completion source |
| `source` | str | `morning-reply` \| `historical-backfill` \| `sweeper-auto-skip` \| (other) |
| `timestamp` | str (ISO 8601, tz-aware) | UTC timestamp when the record was written |

**Invariants** (enforced by existing `state_log.validate_record`):
- `(task_id, date, state)` is the dedup tuple — `state_log.read` with these three params is idempotent.
- `date` is wall-clock ET; `timestamp` is UTC.

**This mission does NOT modify the schema** (C-002).

## E-02 — `WeeklyHabitReport` (existing contract, additive field)

The helper's JSON output document. Existing contract lives at `kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/weekly_report_payload.md`. This mission adds ONE optional field:

| Field | Type | Description | Status |
| --- | --- | --- | --- |
| `report_date` | str (`YYYY-MM-DD`) | Date the report was generated (Monday in ET) | EXISTING |
| `window_start` | str (`YYYY-MM-DD`) | First day of reporting window (prior Monday in ET) | EXISTING |
| `window_end` | str (`YYYY-MM-DD`) | Last day of reporting window inclusive (prior Sunday in ET) | EXISTING |
| `per_habit[]` | array | Per-habit row: title, classification, current %, prior %, trend | EXISTING |
| `overall` | object | Overall % current + prior | EXISTING |
| **`rendered_text`** | str (optional) | **NEW** — fully formatted WhatsApp message text. Renderer-deterministic per NFR-004. | NEW |

**Backward compatibility**: Consumers that ignore `rendered_text` continue to work unchanged (NFR-005). The schema version field, if any in the existing contract, stays the same.

**Rendering contract**: `rendered_text` is a pure function of the rest of the JSON document. Given identical other fields, `rendered_text` is byte-identical.

## E-03 — `HabitsHistoryWrapper` (new — public API surface)

The new wrapper module `scripts/habits/history.py`. Not persisted state — a pure read API over `state_log.read("habits", ...)`.

### Operation 1: `completion_events_in_window`

```python
def completion_events_in_window(
    start: datetime,           # tz-aware (America/New_York or UTC)
    end: datetime,             # tz-aware, exclusive end
    habit_id: int | None = None,
) -> list[HabitCompletionRecord]
```

Returns all records in the window. If `habit_id` is None, all habits. If provided, filters to that task_id.

**Invariants**: ordering is stable (`(date, timestamp)` ascending); same JSONL + same args → byte-identical list.

### Operation 2: `completion_rate_for_habit`

```python
def completion_rate_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> float
```

Returns `completed / scheduled_days_count` as a float in `[0.0, 1.0]`. The caller computes `scheduled_days_count` because habit scheduling (daily vs day-specific vs week-bounded) is the caller's concern.

**Invariants**: `0 ≤ rate ≤ 1.0`; `scheduled_days_count == 0` raises `ValueError` (would be div-by-zero).

### Operation 3: `scheduled_vs_completed_for_habit`

```python
def scheduled_vs_completed_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> tuple[int, int]   # (scheduled, completed)
```

Returns the raw counts. Equivalent to (`scheduled_days_count`, `completed_count`) where `completed_count = len(completion_events_in_window(..., habit_id))` after dedup by date.

**Invariants**: `scheduled ≥ completed ≥ 0`.

## E-04 — `ArchitecturalTestAllowlist` (new — test-internal)

Test-internal data: a Python `frozenset[str]` of file basenames declared in `tests/architectural/test_habits_history_canonical_read.py`. Files in the allowlist may import `VikunjaClient`; files not in the allowlist may not.

Example (illustrative; concrete contents land in IC-03):

```python
VIKUNJA_CURRENT_STATE_ALLOWLIST: frozenset[str] = frozenset({
    "query_active_habits_v2.py",        # current-state: due-today list
    "exclude_completed_v2.py",          # current-state: today's completion check
    "morning_checkin_list.py",          # invokes query_active_habits_v2.py
    "record_completion.py",             # WRITES completion to Vikunja (current-state write)
    "sweeper.py",                       # current-state sweeper for missed day-specific habits
    "set_due_dates.py",                 # current-state mutation
    "identify_workout_task.py",         # current-state query
    "backfill_jsonl_from_comments.py",  # ONE-TIME backfill from Vikunja comments
})
```

**Test rule**: For each `scripts/habits/*.py` file whose basename is NOT in the allowlist, AST-scan its `Import` and `ImportFrom` nodes. If any import resolves to `VikunjaClient` (from `scripts.common.vikunja_client` or any other path), the test fails with `<file>:<lineno>: <import line> — VikunjaClient import not allowlisted for completion-history-safe usage`.

**State transition**: Pre-IC-02, `query_active_habits_weekly.py` is on this allowlist (it imports VikunjaClient for the broken `done_at` path). Post-IC-02, it's REMOVED (it no longer imports VikunjaClient at all — it imports `scripts.habits.history` instead).
