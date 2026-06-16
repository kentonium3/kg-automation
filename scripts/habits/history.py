"""Habits-domain canonical read API on top of ``scripts.common.state_log``.

This module is the **single read path** for any consumer of Felix habit
completion history — the Monday weekly report, future trend-analysis
tooling, ad-hoc analysis, and the architectural test that ratchets the
canonical-read rule. Nobody else parses raw ``habits-history.jsonl``; nobody
else infers historical completion state from Vikunja ``done_at``.

Why a wrapper instead of letting every caller call ``state_log.read``
directly:

- ``done_at`` on a Vikunja task is a single timestamp that gets reset on
  every ``repeat_after`` recurrence cycle. For a daily habit, ``done_at``
  is only useful for "is today's instance currently done" — it is NOT a
  history. Reading it for weekly accountability collapses 7 completions
  to either 0 or 1 depending on whether today's instance happens to be
  done at query time. This is the bug captured in GitHub issue #605.
- The canonical history lives in ``/data/services/openclaw/state/habits-history.jsonl``,
  an append-only JSONL log written by ``record_completion.py``,
  ``sweeper.py``, and ``backfill_jsonl_from_comments.py``. It survives
  Vikunja recurrence resets, restarts, and process crashes (per ADR-0002
  Phase 2). It is the source of truth for "did this habit happen on this
  date."
- Wrapping the raw JSONL behind three habit-shaped operations keeps the
  domain semantics (dedup-by-date, completion-only counting, window
  inclusivity) in one place. Callers stay declarative: "give me the
  completion rate for habit 100 in this window." The math, the boundary
  rules, and the schema knowledge stay here.

Mission: ``trustworthy-weekly-habit-report-01KV4GZ7`` (IC-01).

Imports allowed: stdlib + ``scripts.common.state_log``.
Imports forbidden: ``scripts.common.vikunja_client`` and anything that
reads Vikunja ``done_at`` for historical purposes. The architectural test
in IC-03 enforces this — ``scripts/habits/history.py`` is intentionally
NOT on the VikunjaClient allowlist.

Determinism contract (NFR-001): for the same ``habits-history.jsonl``
byte content + the same arguments, every operation returns
byte-identical results across runs. There are no ``datetime.now()``
calls inside this module; callers pass tz-aware datetimes explicitly,
which also makes DST-safe testing trivial.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from scripts.common import state_log

__all__ = [
    "completion_events_in_window",
    "completion_rate_for_habit",
    "scheduled_vs_completed_for_habit",
]


# Records with this state count as a "completion" for rate / scheduled-vs-
# completed math. ``skipped`` and ``incomplete`` records are returned by
# ``completion_events_in_window`` (callers may want to see them for audit
# purposes) but are NOT counted toward completion totals.
_COMPLETION_STATE: str = "complete"


# ---------------------------------------------------------------------------
# Argument validation helpers
# ---------------------------------------------------------------------------


def _validate_window(start: datetime, end: datetime) -> None:
    """Raise ``ValueError`` if the (start, end) datetime window is malformed.

    The contract requires both bounds tz-aware and ``end`` strictly greater
    than ``start``. Naive datetimes would silently compare as wall-clock
    only, producing wrong results across DST boundaries. ``end == start``
    is rejected to keep the half-open semantics unambiguous.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be tz-aware datetimes")
    if end <= start:
        raise ValueError("end must be > start (window is [start, end))")


def _validate_scheduled_days_count(scheduled_days_count: int) -> None:
    """Raise ``ValueError`` if ``scheduled_days_count`` is not a positive int.

    Zero is rejected (would be division-by-zero for the rate operation).
    Negative is rejected (nonsensical). This validator is shared by both
    rate and scheduled-vs-completed operations so the error message and
    the rejection threshold stay consistent.
    """
    if scheduled_days_count <= 0:
        raise ValueError(
            f"scheduled_days_count must be > 0 (got {scheduled_days_count})"
        )


# ---------------------------------------------------------------------------
# Internal: read + window-clip the underlying records
# ---------------------------------------------------------------------------


def _parse_record_timestamp(record: dict) -> datetime | None:
    """Parse the record's ``timestamp`` field into a tz-aware datetime.

    Returns ``None`` for missing or unparseable timestamps; callers treat
    those records as outside any window (they were already validated on
    write, so this only fires for hand-edited or corrupted lines, which
    we silently skip rather than crashing the weekly report).
    """
    ts = record.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _records_in_window(
    start: datetime,
    end: datetime,
    habit_id: int | None,
) -> list[dict]:
    """Return raw records in [start, end), filtered by habit_id if given.

    Ordering: stable ascending by ``(date, timestamp)``. The dedup of
    completion-state records by ``date`` happens in the rate / counts
    operations, not here — this helper preserves every event so callers
    that want the full picture (including ``skipped`` / ``incomplete``)
    see it.
    """
    filters: dict[str, Any] = {}
    if habit_id is not None:
        filters["task_id"] = habit_id

    raw = state_log.read("habits", **filters)

    in_window: list[dict] = []
    for record in raw:
        parsed_ts = _parse_record_timestamp(record)
        if parsed_ts is None:
            continue
        if parsed_ts < start or parsed_ts >= end:
            continue
        in_window.append(record)

    # Sort by (date, timestamp) ascending. Both are strings on disk —
    # date is YYYY-MM-DD (string-sortable as ISO date) and timestamp is
    # ISO 8601 (string-sortable when normalized to UTC; the existing
    # state_log validator does not require UTC but the canonical writers
    # all emit UTC). Sorting by string is byte-stable and matches
    # append-order under sane writer conditions.
    in_window.sort(key=lambda r: (r.get("date", ""), r.get("timestamp", "")))
    return in_window


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def completion_events_in_window(
    start: datetime,
    end: datetime,
    habit_id: int | None = None,
) -> list[dict]:
    """Return all habits-history records whose ``timestamp`` is in [start, end).

    Args:
        start: tz-aware datetime. Inclusive lower bound.
        end: tz-aware datetime. Exclusive upper bound. Must be > start.
        habit_id: Optional Vikunja task ID. If given, the result is
            filtered to records with that ``task_id``.

    Returns:
        List of record dicts (per ``state_log.read`` schema). Ordered
        ascending by ``(date, timestamp)``. Empty if no records match.

    Raises:
        ValueError: if start or end is naive (no tzinfo), or end <= start.
        OSError: bubbled from ``state_log.read`` on file-read failure.
    """
    _validate_window(start, end)
    return _records_in_window(start, end, habit_id)


def _distinct_completion_dates(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """Count distinct ``date`` values where this habit has a complete record.

    Dedup-by-date is the operator-edge rule from the contract: two
    ``complete`` records for the same habit on the same date count as
    one completion. This typically happens when a habit is recorded via
    two channels (morning reply + manual UI tick) or when a sweeper
    re-emits an already-recorded completion.
    """
    records = _records_in_window(window_start, window_end, habit_id)
    return len({
        r["date"]
        for r in records
        if r.get("state") == _COMPLETION_STATE and isinstance(r.get("date"), str)
    })


def completion_rate_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> float:
    """Return completed / scheduled as a float in [0.0, 1.0].

    Scheduling logic (daily vs day-specific vs week-bounded) lives in the
    caller; this function only needs the count of days the habit was
    scheduled in the window. ``completed`` is computed here as the count
    of distinct ``date`` values with a ``complete`` state record for the
    habit within [window_start, window_end).

    Args:
        habit_id: Vikunja task ID for the habit.
        window_start: tz-aware datetime, inclusive lower bound.
        window_end: tz-aware datetime, exclusive upper bound.
        scheduled_days_count: How many days the habit was scheduled in
            the window. Must be > 0.

    Returns:
        Float in [0.0, 1.0]. Clamped to ``1.0`` defensively in case
        completions outnumber scheduled days (which would indicate a
        caller bug, but a clamp keeps the report renderer honest).

    Raises:
        ValueError: if ``scheduled_days_count`` <= 0, or if window args
            fail validation.
    """
    _validate_window(window_start, window_end)
    _validate_scheduled_days_count(scheduled_days_count)

    completed = _distinct_completion_dates(habit_id, window_start, window_end)
    rate = completed / scheduled_days_count
    # Defensive clamp: if upstream over-counts (e.g. a sweeper bug),
    # the renderer should still show a sane <=100% value rather than
    # leak the inconsistency to Kent.
    return min(rate, 1.0)


def scheduled_vs_completed_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> tuple[int, int]:
    """Return (scheduled_days_count, completed_count) for the habit.

    Same dedup-by-date semantics as :func:`completion_rate_for_habit`.
    Useful for renderers that want to display "3 of 5" rather than
    "60%".

    Args:
        habit_id: Vikunja task ID for the habit.
        window_start: tz-aware datetime, inclusive lower bound.
        window_end: tz-aware datetime, exclusive upper bound.
        scheduled_days_count: How many days the habit was scheduled in
            the window. Must be > 0.

    Returns:
        Tuple ``(scheduled, completed)`` of non-negative ints with
        ``scheduled >= completed``. ``completed`` is clamped to
        ``scheduled`` defensively (same rationale as the rate clamp).

    Raises:
        ValueError: if ``scheduled_days_count`` <= 0, or if window args
            fail validation.
    """
    _validate_window(window_start, window_end)
    _validate_scheduled_days_count(scheduled_days_count)

    completed = _distinct_completion_dates(habit_id, window_start, window_end)
    completed_capped = min(completed, scheduled_days_count)
    return (scheduled_days_count, completed_capped)
