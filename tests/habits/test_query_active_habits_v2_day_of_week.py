"""Tests for the mission #408 day-of-week filter in query_active_habits_v2.

Updated for mission #519 WP02: all GET-path mock_urlopen fixtures have been
replaced with mock_sync_cache_fixture from tests/common/conftest.py.

Verifies that when ``schedule_path`` is supplied to ``query_active_today``,
day-specific habits whose designated weekdays don't include today's weekday
are excluded. Without ``schedule_path``, the behavior is identical to the
pre-#408 helper — preserving existing test fixtures and contract.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.habits import query_active_habits_v2 as qv2


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

HABITS_PROJECT_ID = qv2.HABITS_PROJECT_ID  # aligned with source (#556)


def _task_fields(
    title: str = "Habit",
    due_date: str = "2026-05-15T08:00:00Z",  # past-due so client-filter includes it
    done: bool = False,
    project_id: int = HABITS_PROJECT_ID,
) -> dict:
    return {
        "title": title,
        "due_date": due_date,
        "done": done,
        "repeat_after": 86400,
        "repeat_mode": "default",
        "project_id": project_id,
        "labels": [],
    }


def _write_schedule(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "schedule.yaml"
    p.write_text(body, encoding="utf-8")
    return p


# ===========================================================================
# Group 1 — schedule_path=None preserves existing behavior
# ===========================================================================


class TestNoSchedulePathPreservesBehavior:
    def test_no_schedule_path_returns_all_candidates(self, mock_sync_cache_fixture):
        """When schedule_path is omitted, all candidates flow through unchanged."""
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Strength training — Friday"),
            },
        )
        result = qv2.query_active_today(
            today="2026-05-20",  # Wednesday — would exclude Fri if filter on
        )
        ids = sorted(t["id"] for t in result)
        assert ids == [14, 77]


# ===========================================================================
# Group 2 — Day-of-week filter active
# ===========================================================================


class TestDayOfWeekFilter:
    SCHEDULE = """
habits:
  - task_id: 14
    title: "Wake"
    repeat_after_seconds: 86400
  - task_id: 77
    title: "Friday strength"
    designated_weekdays: ["Fri"]
    repeat_after_seconds: 604800
  - task_id: 76
    title: "Wed strength"
    designated_weekdays: ["Wed"]
    repeat_after_seconds: 604800
"""

    def test_friday_only_habit_included_on_friday(
        self, tmp_path, mock_sync_cache_fixture
    ):
        """2026-05-22 is a Friday — Friday-only habit should be included."""
        schedule = _write_schedule(tmp_path, self.SCHEDULE)
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
                76: _task_fields(title="Wed strength"),
            },
        )
        result = qv2.query_active_today(
            today="2026-05-22",  # Fri
            schedule_path=schedule,
        )
        # Wake (daily) + Fri strength (today is Fri) — Wed strength excluded.
        assert sorted(t["id"] for t in result) == [14, 77]

    def test_friday_only_habit_excluded_on_wednesday(
        self, tmp_path, mock_sync_cache_fixture
    ):
        """2026-05-20 is a Wednesday — Friday-only habit should be excluded."""
        schedule = _write_schedule(tmp_path, self.SCHEDULE)
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
                76: _task_fields(title="Wed strength"),
            },
        )
        result = qv2.query_active_today(
            today="2026-05-20",  # Wed
            schedule_path=schedule,
        )
        assert sorted(t["id"] for t in result) == [14, 76]

    def test_thursday_excludes_both_day_specific(self, tmp_path, mock_sync_cache_fixture):
        """2026-05-21 is a Thursday — neither Wed-only nor Fri-only included."""
        schedule = _write_schedule(tmp_path, self.SCHEDULE)
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
                76: _task_fields(title="Wed strength"),
            },
        )
        result = qv2.query_active_today(
            today="2026-05-21",  # Thu
            schedule_path=schedule,
        )
        ids = [t["id"] for t in result]
        assert ids == [14]

    def test_explicit_today_weekday_overrides_date_derived(
        self, tmp_path, mock_sync_cache_fixture
    ):
        """``today_weekday`` argument takes precedence over the derived value."""
        schedule = _write_schedule(tmp_path, self.SCHEDULE)
        mock_sync_cache_fixture(
            tasks={77: _task_fields(title="Friday strength")},
        )
        # today is a Mon but operator forces "Fri" — Fri strength should pass.
        result = qv2.query_active_today(
            today="2026-05-18",  # Mon
            today_weekday="Fri",
            schedule_path=schedule,
        )
        assert [t["id"] for t in result] == [77]


# ===========================================================================
# Group 3 — Habit in cache but not in schedule
# ===========================================================================


class TestUnscheduledHabitFallback:
    def test_unscheduled_habit_passes_through_with_warning(
        self, tmp_path, mock_sync_cache_fixture, capsys
    ):
        """A task not in schedule.yaml is included (daily fallback) + warned."""
        schedule = _write_schedule(
            tmp_path,
            """
habits:
  - task_id: 100
    title: "Known"
    repeat_after_seconds: 86400
""",
        )
        mock_sync_cache_fixture(
            tasks={
                100: _task_fields(title="Known"),
                999: _task_fields(title="Stranger"),
            },
        )
        result = qv2.query_active_today(
            today="2026-05-20",  # Wed
            schedule_path=schedule,
        )
        ids = sorted(t["id"] for t in result)
        assert ids == [100, 999]
        captured = capsys.readouterr()
        assert "999" in captured.err
        assert "not in schedule" in captured.err


# ===========================================================================
# Group 4 — Schedule validation errors propagate
# ===========================================================================


class TestScheduleErrorPropagation:
    def test_invalid_schedule_raises_config_error(
        self, tmp_path, mock_sync_cache_fixture
    ):
        schedule = _write_schedule(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "Bad"
    designated_weekdays: ["Xyz"]
    repeat_after_seconds: 86400
""",
        )
        mock_sync_cache_fixture(
            tasks={1: _task_fields()},
        )
        with pytest.raises(qv2.ScheduleConfigError, match="not a valid"):
            qv2.query_active_today(
                today="2026-05-20",
                schedule_path=schedule,
            )

    def test_cli_emits_exit_2_on_schedule_error(
        self, tmp_path, mock_sync_cache_fixture
    ):
        schedule = _write_schedule(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "Bad"
    designated_weekdays: ["Xyz"]
    repeat_after_seconds: 86400
""",
        )
        mock_sync_cache_fixture(tasks={1: _task_fields()})
        exit_code = qv2.main(
            [
                "--today", "2026-05-20",
                "--schedule-path", str(schedule),
            ]
        )
        assert exit_code == 2


# ===========================================================================
# Group 5 — Weekday derivation helper
# ===========================================================================


class TestWeekdayForDate:
    @pytest.mark.parametrize(
        "date,expected",
        [
            ("2026-05-18", "Mon"),
            ("2026-05-19", "Tue"),
            ("2026-05-20", "Wed"),
            ("2026-05-21", "Thu"),
            ("2026-05-22", "Fri"),
            ("2026-05-23", "Sat"),
            ("2026-05-24", "Sun"),
        ],
    )
    def test_each_weekday(self, date, expected):
        assert qv2._weekday_name_for_date(date) == expected
