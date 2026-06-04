"""Tests for the mission #408 day-of-week filter integration in morning_checkin_list.

Updated for mission #519 WP02: all GET-path mock_urlopen fixtures have been
replaced with mock_sync_cache_fixture from tests/common/conftest.py.

Verifies:
  * ``MorningListHabit`` carries ``designated_weekdays`` through to the
    persisted artifact ONLY when non-empty.
  * The day-of-week filter excludes mis-scheduled habits at the query layer
    so they never appear in the morning list.
  * ``ScheduleInvariantError`` fires if a day-specific habit somehow
    survives the filter — production safety net.
  * The CLI ``--schedule-path`` / ``--no-schedule`` flags wire through.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.habits import morning_checkin_list as mcl
from scripts.habits import schedule_loader as sl


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


HABITS_PROJECT_ID = 42


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


SCHEDULE_TEMPLATE = """
habits:
  - task_id: 14
    title: "Wake"
    repeat_after_seconds: 86400
  - task_id: 77
    title: "Friday strength"
    designated_weekdays: ["Fri"]
    repeat_after_seconds: 604800
"""


# ---------------------------------------------------------------------------
# Group 1 — build_morning_list integrates the filter
# ---------------------------------------------------------------------------


class TestBuildMorningListWithSchedule:
    def test_friday_only_included_on_friday(
        self, tmp_path, mock_sync_cache_fixture, mock_state_log_dir
    ):
        """2026-05-22 is Fri — Friday-only habit appears in the list."""
        schedule = _write_schedule(tmp_path, SCHEDULE_TEMPLATE)
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
            },
        )
        ml = mcl.build_morning_list(
            date="2026-05-22",
            schedule_path=schedule,
        )
        ids = [h.vikunja_task_id for h in ml.habits]
        assert ids == [14, 77]
        # Day-specific entry retains designated_weekdays through the dataclass.
        fri = next(h for h in ml.habits if h.vikunja_task_id == 77)
        assert fri.designated_weekdays == ("Fri",)
        # Daily entry has empty designated_weekdays.
        wake = next(h for h in ml.habits if h.vikunja_task_id == 14)
        assert wake.designated_weekdays == ()

    def test_friday_only_excluded_on_wednesday(
        self, tmp_path, mock_sync_cache_fixture, mock_state_log_dir
    ):
        schedule = _write_schedule(tmp_path, SCHEDULE_TEMPLATE)
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
            },
        )
        ml = mcl.build_morning_list(
            date="2026-05-20",  # Wed
            schedule_path=schedule,
        )
        assert [h.vikunja_task_id for h in ml.habits] == [14]

    def test_no_schedule_path_disables_filter(
        self, tmp_path, mock_sync_cache_fixture, mock_state_log_dir
    ):
        """schedule_path=None preserves pre-#408 behavior (no filter)."""
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
            },
        )
        ml = mcl.build_morning_list(
            date="2026-05-20",  # Wed
            schedule_path=None,
        )
        # Both habits pass through; designated_weekdays is empty on both
        # since no schedule was consulted.
        assert sorted(h.vikunja_task_id for h in ml.habits) == [14, 77]
        for h in ml.habits:
            assert h.designated_weekdays == ()


# ---------------------------------------------------------------------------
# Group 2 — Artifact serialization (E2 extension behavior)
# ---------------------------------------------------------------------------


class TestArtifactSerialization:
    def test_designated_weekdays_only_on_day_specific(
        self, tmp_path, mock_sync_cache_fixture, mock_state_log_dir
    ):
        """Persisted JSON includes designated_weekdays ONLY on day-specific entries.

        Preserves the pre-#408 shape for daily habits (regression: existing
        readers don't see a new field on daily entries).
        """
        schedule = _write_schedule(tmp_path, SCHEDULE_TEMPLATE)
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
            },
        )
        ml = mcl.build_morning_list(
            date="2026-05-22",  # Fri
            schedule_path=schedule,
        )
        state_dir = tmp_path / "out"
        mcl.persist_morning_list(ml, state_dir=state_dir)
        payload = json.loads(
            (state_dir / "morning-checkin-2026-05-22.json").read_text()
        )
        # Both habits emitted.
        assert len(payload["habits"]) == 2
        wake = next(h for h in payload["habits"] if h["vikunja_task_id"] == 14)
        fri = next(h for h in payload["habits"] if h["vikunja_task_id"] == 77)
        # Daily habit has no `designated_weekdays` key (back-compat).
        assert "designated_weekdays" not in wake
        # Day-specific habit serializes the list.
        assert fri["designated_weekdays"] == ["Fri"]


# ---------------------------------------------------------------------------
# Group 3 — Schedule invariant safety net
# ---------------------------------------------------------------------------


class TestScheduleInvariantViolation:
    def test_invariant_violation_raised_when_filter_bypassed(
        self, tmp_path, mock_sync_cache_fixture, mock_state_log_dir
    ):
        """If a day-specific habit slips through the query layer, build_morning_list raises."""
        schedule = _write_schedule(tmp_path, SCHEDULE_TEMPLATE)
        mock_sync_cache_fixture(tasks={77: _task_fields(title="Friday strength")})
        # Simulate the filter being broken: _query_habits returns the Fri
        # habit even though today is Wed. build_morning_list's invariant
        # check must catch it.
        with patch.object(
            mcl,
            "_query_habits",
            return_value=[{"id": 77, "title": "Friday strength",
                           "due_date": "2026-05-15T08:00:00Z", "done": False,
                           "repeat_after": 86400, "project_id": HABITS_PROJECT_ID,
                           "labels": []}],
        ):
            with pytest.raises(mcl.ScheduleInvariantError, match="day-specific"):
                mcl.build_morning_list(
                    date="2026-05-20",  # Wed
                    schedule_path=schedule,
                )

    def test_cli_maps_invariant_violation_to_exit_4(
        self, tmp_path, mock_sync_cache_fixture, mock_state_log_dir, capsys
    ):
        schedule = _write_schedule(tmp_path, SCHEDULE_TEMPLATE)
        mock_sync_cache_fixture(tasks={77: _task_fields(title="Friday strength")})
        # We need _query_habits to bypass the filter for this test.
        with patch.object(
            mcl,
            "_query_habits",
            return_value=[{"id": 77, "title": "Friday strength",
                           "due_date": "2026-05-15T08:00:00Z", "done": False,
                           "repeat_after": 86400, "project_id": HABITS_PROJECT_ID,
                           "labels": []}],
        ):
            state_dir = tmp_path / "state"
            exit_code = mcl.main([
                "--date", "2026-05-20",  # Wed
                "--state-dir", str(state_dir),
                "--schedule-path", str(schedule),
            ])
        assert exit_code == 4
        captured = capsys.readouterr()
        assert "schedule_invariant_violation" in captured.err


# ---------------------------------------------------------------------------
# Group 4 — CLI wiring for --no-schedule
# ---------------------------------------------------------------------------


class TestCliFlags:
    def test_no_schedule_flag_disables_filter(
        self, tmp_path, mock_sync_cache_fixture, mock_state_log_dir
    ):
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
            },
        )
        state_dir = tmp_path / "state"
        exit_code = mcl.main([
            "--date", "2026-05-20",  # Wed
            "--state-dir", str(state_dir),
            "--no-schedule",
        ])
        assert exit_code == 0
        payload = json.loads(
            (state_dir / "morning-checkin-2026-05-20.json").read_text()
        )
        # Both habits present — filter disabled.
        assert sorted(h["vikunja_task_id"] for h in payload["habits"]) == [14, 77]

    def test_cli_schedule_load_error_returns_3(
        self, tmp_path, mock_sync_cache_fixture, mock_state_log_dir, capsys
    ):
        bad_schedule = _write_schedule(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "Bad"
    designated_weekdays: ["Xyz"]
    repeat_after_seconds: 86400
""",
        )
        # Schedule load error fires before cache read; still need a valid
        # cache so the fixture infrastructure is consistent.
        mock_sync_cache_fixture(
            tasks={1: _task_fields()},
        )
        state_dir = tmp_path / "state"
        exit_code = mcl.main([
            "--date", "2026-05-20",
            "--state-dir", str(state_dir),
            "--schedule-path", str(bad_schedule),
        ])
        assert exit_code == 3
        captured = capsys.readouterr()
        assert "schedule_load" in captured.err


# ---------------------------------------------------------------------------
# Group 5 — Helper
# ---------------------------------------------------------------------------


class TestWeekdayHelper:
    def test_weekday_for_known_dates(self):
        assert mcl._weekday_name_for_date("2026-05-22") == "Fri"
        assert mcl._weekday_name_for_date("2026-05-20") == "Wed"
        assert mcl._weekday_name_for_date("2026-05-18") == "Mon"
