"""Unit tests for ``scripts.habits.history`` (WP01 / T002-T004).

Mission: ``trustworthy-weekly-habit-report-01KV4GZ7``.

Test data comes exclusively from the golden-week fixture
(``tests/habits/fixtures/golden_week_jsonl.py``); no test invents records
in-place beyond extending the fixture. ``mock_state_log_dir`` from
``tests/habits/conftest.py`` sandboxes ``state_log.STATE_DIR`` to a temp
directory so reads never escape to ``/data/services/openclaw/state``.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.habits import history
from tests.habits.fixtures.golden_week_jsonl import (
    DAILY_COMPLETED_OFFSETS,
    DAILY_HABIT_ID,
    DAYSPEC_HABIT_ID,
    GOLDEN_WEEK_ANCHOR,
    GOLDEN_WEEK_TZ,
    WEEKLY_HABIT_ID,
    write_golden_week_jsonl,
)


# ---------------------------------------------------------------------------
# Local test helpers
# ---------------------------------------------------------------------------


def _habits_jsonl_path(sandbox: Path) -> Path:
    """Return the canonical ``habits-history.jsonl`` path inside the sandbox."""
    return sandbox / "habits-history.jsonl"


def _window_full_week() -> tuple[datetime, datetime]:
    """Return the canonical (start, end) for the golden week (Mon 00:00 ET)."""
    start = GOLDEN_WEEK_ANCHOR
    end = start + timedelta(days=7)
    return start, end


def _write_record_lines(path: Path, records: list[dict]) -> None:
    """Write an arbitrary list of record dicts as JSONL to ``path``.

    Used by tests that need a specific (often out-of-order or empty)
    fixture beyond the golden-week defaults.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(
        json.dumps(r, ensure_ascii=False, sort_keys=False) for r in records
    )
    path.write_text(payload + ("\n" if records else ""), encoding="utf-8")


def _record(
    *,
    task_id: int,
    date_iso: str,
    timestamp_iso: str,
    title: str = "Habit",
    state: str = "complete",
    source: str = "whatsapp",
) -> dict:
    """Return a minimal habits state-log record (matches state_log schema)."""
    return {
        "domain": "habits",
        "task_id": task_id,
        "title": title,
        "date": date_iso,
        "state": state,
        "source": source,
        "timestamp": timestamp_iso,
    }


# ===========================================================================
# Group: completion_events_in_window (T002)
# ===========================================================================


class TestCompletionEventsInWindow:
    def test_empty_jsonl_returns_empty_list(self, mock_state_log_dir):
        """No JSONL file exists yet → empty list, not an error."""
        start, end = _window_full_week()
        assert history.completion_events_in_window(start, end) == []

    def test_habit_id_none_returns_all_events_in_window(self, mock_state_log_dir):
        """habit_id=None returns every habit's events in the window."""
        write_golden_week_jsonl(_habits_jsonl_path(mock_state_log_dir))
        start, end = _window_full_week()

        result = history.completion_events_in_window(start, end, habit_id=None)

        # Golden week writes 4 (daily) + 1 (dayspec) + 1 (weekly) = 6 records.
        assert len(result) == 6
        ids = {r["task_id"] for r in result}
        assert ids == {DAILY_HABIT_ID, DAYSPEC_HABIT_ID, WEEKLY_HABIT_ID}

    def test_habit_id_filters_to_that_task(self, mock_state_log_dir):
        """habit_id=N restricts the result to events with that task_id."""
        write_golden_week_jsonl(_habits_jsonl_path(mock_state_log_dir))
        start, end = _window_full_week()

        result = history.completion_events_in_window(
            start, end, habit_id=DAILY_HABIT_ID
        )

        assert len(result) == len(DAILY_COMPLETED_OFFSETS)
        assert all(r["task_id"] == DAILY_HABIT_ID for r in result)

    def test_events_outside_window_are_excluded(self, mock_state_log_dir):
        """Records with timestamps before start or at/after end are dropped."""
        path = _habits_jsonl_path(mock_state_log_dir)
        start, end = _window_full_week()

        # Build three records: one before start, one at exactly end
        # (exclusive — should be dropped), one inside.
        before_ts = (start - timedelta(hours=1)).astimezone(ZoneInfo("UTC"))
        boundary_end_ts = end.astimezone(ZoneInfo("UTC"))
        inside_ts = (start + timedelta(hours=2)).astimezone(ZoneInfo("UTC"))

        _write_record_lines(
            path,
            [
                _record(
                    task_id=99,
                    date_iso=before_ts.astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=before_ts.isoformat(),
                ),
                _record(
                    task_id=99,
                    date_iso=boundary_end_ts.astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=boundary_end_ts.isoformat(),
                ),
                _record(
                    task_id=99,
                    date_iso=inside_ts.astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=inside_ts.isoformat(),
                ),
            ],
        )

        result = history.completion_events_in_window(start, end, habit_id=99)

        # Only the inside record survives.
        assert len(result) == 1
        assert result[0]["timestamp"] == inside_ts.isoformat()

    def test_start_is_inclusive_boundary(self, mock_state_log_dir):
        """A record at exactly start is included (inclusive lower bound)."""
        path = _habits_jsonl_path(mock_state_log_dir)
        start, end = _window_full_week()

        boundary_ts = start.astimezone(ZoneInfo("UTC"))
        _write_record_lines(
            path,
            [
                _record(
                    task_id=99,
                    date_iso=start.astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=boundary_ts.isoformat(),
                ),
            ],
        )

        result = history.completion_events_in_window(start, end, habit_id=99)
        assert len(result) == 1

    def test_stable_ordering_by_date_then_timestamp(self, mock_state_log_dir):
        """Out-of-order JSONL is sorted ascending by (date, timestamp)."""
        path = _habits_jsonl_path(mock_state_log_dir)
        start, end = _window_full_week()

        # Three records, deliberately written in reverse chronological
        # order, all inside the window.
        ts_thu = (start + timedelta(days=3, hours=10)).astimezone(
            ZoneInfo("UTC")
        )
        ts_mon = (start + timedelta(hours=10)).astimezone(ZoneInfo("UTC"))
        ts_wed_early = (start + timedelta(days=2, hours=6)).astimezone(
            ZoneInfo("UTC")
        )
        ts_wed_late = (start + timedelta(days=2, hours=22)).astimezone(
            ZoneInfo("UTC")
        )

        _write_record_lines(
            path,
            [
                _record(
                    task_id=99,
                    date_iso=ts_thu.astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=ts_thu.isoformat(),
                ),
                _record(
                    task_id=99,
                    date_iso=ts_wed_late.astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=ts_wed_late.isoformat(),
                ),
                _record(
                    task_id=99,
                    date_iso=ts_mon.astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=ts_mon.isoformat(),
                ),
                _record(
                    task_id=99,
                    date_iso=ts_wed_early.astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=ts_wed_early.isoformat(),
                ),
            ],
        )

        result = history.completion_events_in_window(start, end, habit_id=99)
        timestamps = [r["timestamp"] for r in result]
        assert timestamps == sorted(timestamps)
        # Sanity: Monday before both Wednesdays before Thursday.
        assert timestamps[0] == ts_mon.isoformat()
        assert timestamps[-1] == ts_thu.isoformat()

    def test_determinism_same_args_same_result(self, mock_state_log_dir):
        """NFR-001: identical fixture + identical args → byte-identical output."""
        write_golden_week_jsonl(_habits_jsonl_path(mock_state_log_dir))
        start, end = _window_full_week()

        result_a = history.completion_events_in_window(start, end)
        result_b = history.completion_events_in_window(start, end)
        assert result_a == result_b

    def test_naive_start_raises_value_error(self, mock_state_log_dir):
        """A naive start datetime is rejected."""
        end = GOLDEN_WEEK_ANCHOR + timedelta(days=7)
        naive_start = datetime(2026, 6, 8, 0, 0)
        with pytest.raises(ValueError, match="tz-aware"):
            history.completion_events_in_window(naive_start, end)

    def test_naive_end_raises_value_error(self, mock_state_log_dir):
        """A naive end datetime is rejected."""
        start = GOLDEN_WEEK_ANCHOR
        naive_end = datetime(2026, 6, 15, 0, 0)
        with pytest.raises(ValueError, match="tz-aware"):
            history.completion_events_in_window(start, naive_end)

    def test_end_equal_to_start_raises_value_error(self, mock_state_log_dir):
        """end == start is rejected (must be strictly greater)."""
        start = GOLDEN_WEEK_ANCHOR
        with pytest.raises(ValueError, match="end must be > start"):
            history.completion_events_in_window(start, start)

    def test_end_before_start_raises_value_error(self, mock_state_log_dir):
        """end < start is rejected."""
        start = GOLDEN_WEEK_ANCHOR
        bad_end = start - timedelta(days=1)
        with pytest.raises(ValueError, match="end must be > start"):
            history.completion_events_in_window(start, bad_end)


# ===========================================================================
# Group: completion_rate_for_habit (T003)
# ===========================================================================


class TestCompletionRateForHabit:
    def test_daily_perfect_week_returns_one(self, mock_state_log_dir):
        """Daily habit completed all 7 days → 1.0."""
        path = _habits_jsonl_path(mock_state_log_dir)
        start, end = _window_full_week()

        # Write a 7-day perfect-week fixture for habit 99.
        records: list[dict] = []
        for offset in range(7):
            ts = (start + timedelta(days=offset, hours=12)).astimezone(
                ZoneInfo("UTC")
            )
            records.append(
                _record(
                    task_id=99,
                    date_iso=(start + timedelta(days=offset))
                    .astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=ts.isoformat(),
                )
            )
        _write_record_lines(path, records)

        rate = history.completion_rate_for_habit(
            habit_id=99,
            window_start=start,
            window_end=end,
            scheduled_days_count=7,
        )
        assert rate == 1.0

    def test_daily_partial_week_returns_fraction(self, mock_state_log_dir):
        """Golden-week daily walk: 4/7 → ≈0.4286."""
        write_golden_week_jsonl(_habits_jsonl_path(mock_state_log_dir))
        start, end = _window_full_week()

        rate = history.completion_rate_for_habit(
            habit_id=DAILY_HABIT_ID,
            window_start=start,
            window_end=end,
            scheduled_days_count=7,
        )
        assert rate == pytest.approx(4 / 7)

    def test_day_specific_scheduled_one_completed_one(self, mock_state_log_dir):
        """Day-specific habit (Mon only), completed Mon → 1.0."""
        write_golden_week_jsonl(_habits_jsonl_path(mock_state_log_dir))
        start, end = _window_full_week()

        rate = history.completion_rate_for_habit(
            habit_id=DAYSPEC_HABIT_ID,
            window_start=start,
            window_end=end,
            scheduled_days_count=1,
        )
        assert rate == 1.0

    def test_day_specific_scheduled_one_completed_zero(self, mock_state_log_dir):
        """Day-specific habit scheduled for Monday but no completion → 0.0."""
        # Empty JSONL — the day-specific habit has no records.
        path = _habits_jsonl_path(mock_state_log_dir)
        _write_record_lines(path, [])
        start, end = _window_full_week()

        rate = history.completion_rate_for_habit(
            habit_id=DAYSPEC_HABIT_ID,
            window_start=start,
            window_end=end,
            scheduled_days_count=1,
        )
        assert rate == 0.0

    def test_dedup_by_date_counts_as_one(self, mock_state_log_dir):
        """Two ``complete`` records on the same date count as one completion."""
        path = _habits_jsonl_path(mock_state_log_dir)
        start, end = _window_full_week()
        same_day_iso = (start + timedelta(hours=10)).astimezone(
            GOLDEN_WEEK_TZ
        ).date().isoformat()

        ts1 = (start + timedelta(hours=10)).astimezone(ZoneInfo("UTC"))
        ts2 = (start + timedelta(hours=20)).astimezone(ZoneInfo("UTC"))

        _write_record_lines(
            path,
            [
                _record(
                    task_id=99,
                    date_iso=same_day_iso,
                    timestamp_iso=ts1.isoformat(),
                ),
                _record(
                    task_id=99,
                    date_iso=same_day_iso,
                    timestamp_iso=ts2.isoformat(),
                ),
            ],
        )

        # Two records but one distinct date → 1/7 not 2/7.
        rate = history.completion_rate_for_habit(
            habit_id=99,
            window_start=start,
            window_end=end,
            scheduled_days_count=7,
        )
        assert rate == pytest.approx(1 / 7)

    def test_scheduled_days_count_zero_raises(self, mock_state_log_dir):
        """scheduled_days_count=0 → ValueError (div-by-zero guard)."""
        start, end = _window_full_week()
        with pytest.raises(ValueError, match="scheduled_days_count"):
            history.completion_rate_for_habit(
                habit_id=1,
                window_start=start,
                window_end=end,
                scheduled_days_count=0,
            )

    def test_scheduled_days_count_negative_raises(self, mock_state_log_dir):
        """scheduled_days_count<0 → ValueError."""
        start, end = _window_full_week()
        with pytest.raises(ValueError, match="scheduled_days_count"):
            history.completion_rate_for_habit(
                habit_id=1,
                window_start=start,
                window_end=end,
                scheduled_days_count=-1,
            )

    def test_naive_window_inherits_validation(self, mock_state_log_dir):
        """Argument validation from completion_events_in_window is inherited."""
        naive_start = datetime(2026, 6, 8, 0, 0)
        end = GOLDEN_WEEK_ANCHOR + timedelta(days=7)
        with pytest.raises(ValueError, match="tz-aware"):
            history.completion_rate_for_habit(
                habit_id=1,
                window_start=naive_start,
                window_end=end,
                scheduled_days_count=7,
            )


# ===========================================================================
# Group: scheduled_vs_completed_for_habit (T004)
# ===========================================================================


class TestScheduledVsCompletedForHabit:
    def test_daily_perfect_week_returns_seven_seven(self, mock_state_log_dir):
        """Daily habit completed 7/7 → (7, 7)."""
        path = _habits_jsonl_path(mock_state_log_dir)
        start, end = _window_full_week()

        records: list[dict] = []
        for offset in range(7):
            ts = (start + timedelta(days=offset, hours=12)).astimezone(
                ZoneInfo("UTC")
            )
            records.append(
                _record(
                    task_id=99,
                    date_iso=(start + timedelta(days=offset))
                    .astimezone(GOLDEN_WEEK_TZ)
                    .date()
                    .isoformat(),
                    timestamp_iso=ts.isoformat(),
                )
            )
        _write_record_lines(path, records)

        result = history.scheduled_vs_completed_for_habit(
            habit_id=99,
            window_start=start,
            window_end=end,
            scheduled_days_count=7,
        )
        assert result == (7, 7)

    def test_daily_three_of_seven_returns_counts(self, mock_state_log_dir):
        """Golden-week daily walk: 4 distinct days completed → (7, 4)."""
        write_golden_week_jsonl(_habits_jsonl_path(mock_state_log_dir))
        start, end = _window_full_week()

        result = history.scheduled_vs_completed_for_habit(
            habit_id=DAILY_HABIT_ID,
            window_start=start,
            window_end=end,
            scheduled_days_count=7,
        )
        assert result == (7, 4)

    def test_day_specific_completed_returns_one_one(self, mock_state_log_dir):
        """Day-specific habit scheduled 1, completed 1 → (1, 1)."""
        write_golden_week_jsonl(_habits_jsonl_path(mock_state_log_dir))
        start, end = _window_full_week()

        result = history.scheduled_vs_completed_for_habit(
            habit_id=DAYSPEC_HABIT_ID,
            window_start=start,
            window_end=end,
            scheduled_days_count=1,
        )
        assert result == (1, 1)

    def test_day_specific_missed_returns_one_zero(self, mock_state_log_dir):
        """Day-specific habit scheduled 1, no completion → (1, 0)."""
        _write_record_lines(_habits_jsonl_path(mock_state_log_dir), [])
        start, end = _window_full_week()

        result = history.scheduled_vs_completed_for_habit(
            habit_id=DAYSPEC_HABIT_ID,
            window_start=start,
            window_end=end,
            scheduled_days_count=1,
        )
        assert result == (1, 0)

    def test_weekly_bounded_completed_returns_one_one(self, mock_state_log_dir):
        """Week-bounded habit (Sunday completion) → (1, 1)."""
        write_golden_week_jsonl(_habits_jsonl_path(mock_state_log_dir))
        start, end = _window_full_week()

        result = history.scheduled_vs_completed_for_habit(
            habit_id=WEEKLY_HABIT_ID,
            window_start=start,
            window_end=end,
            scheduled_days_count=1,
        )
        assert result == (1, 1)

    def test_validation_inherited_for_scheduled_zero(self, mock_state_log_dir):
        """scheduled_days_count=0 → ValueError."""
        start, end = _window_full_week()
        with pytest.raises(ValueError, match="scheduled_days_count"):
            history.scheduled_vs_completed_for_habit(
                habit_id=1,
                window_start=start,
                window_end=end,
                scheduled_days_count=0,
            )

    def test_validation_inherited_for_naive_window(self, mock_state_log_dir):
        """Naive window datetime → ValueError."""
        start = GOLDEN_WEEK_ANCHOR
        naive_end = datetime(2026, 6, 15, 0, 0)
        with pytest.raises(ValueError, match="tz-aware"):
            history.scheduled_vs_completed_for_habit(
                habit_id=1,
                window_start=start,
                window_end=naive_end,
                scheduled_days_count=7,
            )


# ===========================================================================
# Cross-cutting: ``skipped`` records do not count as completions
# ===========================================================================


class TestSkippedRecordsNotCounted:
    def test_skipped_record_does_not_count_as_completion(
        self, mock_state_log_dir
    ):
        """A ``skipped`` record is still returned by events_in_window but does
        not count toward completion rate / scheduled-vs-completed."""
        path = _habits_jsonl_path(mock_state_log_dir)
        start, end = _window_full_week()

        ts = (start + timedelta(hours=12)).astimezone(ZoneInfo("UTC"))
        skip_date_iso = (start + timedelta(hours=12)).astimezone(
            GOLDEN_WEEK_TZ
        ).date().isoformat()
        _write_record_lines(
            path,
            [
                _record(
                    task_id=99,
                    date_iso=skip_date_iso,
                    timestamp_iso=ts.isoformat(),
                    state="skipped",
                ),
            ],
        )

        # All-events view returns the skip record.
        events = history.completion_events_in_window(
            start, end, habit_id=99
        )
        assert len(events) == 1
        assert events[0]["state"] == "skipped"

        # But the rate / counts treat it as not completed.
        rate = history.completion_rate_for_habit(
            habit_id=99,
            window_start=start,
            window_end=end,
            scheduled_days_count=7,
        )
        assert rate == 0.0

        counts = history.scheduled_vs_completed_for_habit(
            habit_id=99,
            window_start=start,
            window_end=end,
            scheduled_days_count=7,
        )
        assert counts == (7, 0)
