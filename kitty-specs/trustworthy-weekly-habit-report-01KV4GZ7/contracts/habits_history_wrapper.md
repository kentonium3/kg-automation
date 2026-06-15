# Contract: `scripts/habits/history.py` (HabitsHistoryWrapper)

**Module**: `scripts.habits.history`
**Purpose**: Habits-domain read API on top of generic `scripts.common.state_log`. All callers consuming habits completion history go through this module — never raw JSONL parsing, never Vikunja `done_at`.

## Imports allowed

```python
from scripts.common import state_log          # the generic primitive
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
# stdlib only
```

## Imports forbidden

```python
from scripts.common.vikunja_client import VikunjaClient   # NEVER — enforced by IC-03 architectural test
```

## Public API

### `completion_events_in_window`

```python
def completion_events_in_window(
    start: datetime,
    end: datetime,
    habit_id: int | None = None,
) -> list[dict]:
    """Return all habits-history completion events in [start, end).

    Args:
        start: tz-aware datetime. Inclusive lower bound.
        end: tz-aware datetime. Exclusive upper bound.
        habit_id: Optional Vikunja task ID; if provided, only events for that habit.

    Returns:
        List of HabitCompletionRecord dicts (per state_log.read schema).
        Ordering: stable ascending by (date, timestamp).

    Raises:
        ValueError: if start.tzinfo is None or end.tzinfo is None.
        ValueError: if end <= start.
        OSError: bubbled from state_log.read on file-read failure.
    """
```

### `completion_rate_for_habit`

```python
def completion_rate_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> float:
    """Return completed / scheduled as float in [0.0, 1.0].

    The caller computes `scheduled_days_count` because scheduling logic
    (daily / day-specific / week-bounded) lives in the caller.

    Args:
        habit_id: Vikunja task ID.
        window_start: tz-aware datetime, inclusive.
        window_end: tz-aware datetime, exclusive.
        scheduled_days_count: How many days the habit was scheduled in the window.

    Returns:
        Float in [0.0, 1.0]. Dedup'd by date (multiple records same day = 1 completion).

    Raises:
        ValueError: if scheduled_days_count <= 0.
        ValueError: per completion_events_in_window arg validation.
    """
```

### `scheduled_vs_completed_for_habit`

```python
def scheduled_vs_completed_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> tuple[int, int]:
    """Return (scheduled_days_count, completed_count) for the habit in the window.

    Same semantics as completion_rate_for_habit but returns raw counts.
    Useful for renderers that want to display "3 of 5" rather than "60%".

    Raises:
        ValueError: if scheduled_days_count < 0.
        ValueError: per completion_events_in_window arg validation.
    """
```

## Determinism contract (NFR-001)

For the same `habits-history.jsonl` byte content + the same arguments, all three operations return byte-identical results across runs.

- No `datetime.now()` calls inside the module — all time inputs are explicit arguments.
- No `os.getenv` lookups that could affect output.
- `state_log.read` is itself deterministic by its existing contract.

## Test surface

`tests/habits/test_history.py` covers:
- Empty JSONL → all operations return empty / `(N, 0)` / `0.0` consistently
- Single-completion fixture with `habit_id` filter
- Multi-day completion of a daily habit → correct rate
- Day-specific habit (Monday only) with one completion → `(1, 1)` and `1.0`
- Same date appearing twice in JSONL → counted once (dedup by date per record)
- `end <= start` → `ValueError`
- naive datetime → `ValueError`
- `scheduled_days_count = 0` for rate → `ValueError`
