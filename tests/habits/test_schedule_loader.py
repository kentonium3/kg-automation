"""Tests for scripts/habits/schedule_loader.py (mission #408 / WP-01 / T002).

Covers the public API: ``load_schedule``, ``is_day_specific``,
``is_active_today``, and ``ScheduleConfigError``. All tests work against
in-memory YAML written to ``tmp_path`` so the suite is independent of the
production schedule file's contents.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.habits import schedule_loader as sl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "schedule.yaml"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy-path loading
# ---------------------------------------------------------------------------


class TestLoadSchedule:
    def test_loads_mixed_daily_and_day_specific(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "Daily wake"
    repeat_after_seconds: 86400
  - task_id: 2
    title: "Wed strength"
    designated_weekdays: ["Wed"]
    repeat_after_seconds: 604800
""",
        )
        entries = sl.load_schedule(path)
        assert len(entries) == 2
        assert entries[0].task_id == 1
        assert entries[0].designated_weekdays == ()
        assert entries[1].task_id == 2
        assert entries[1].designated_weekdays == ("Wed",)
        assert entries[1].repeat_after_seconds == 604800

    def test_dedupes_duplicate_weekdays(self, tmp_path: Path) -> None:
        """[Wed, Wed] -> (Wed,) — dedupe silently per the contract."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 5
    title: "Dup Wed"
    designated_weekdays: ["Wed", "Wed", "Wed"]
    repeat_after_seconds: 604800
""",
        )
        entries = sl.load_schedule(path)
        assert entries[0].designated_weekdays == ("Wed",)

    def test_preserves_first_occurrence_order_in_dedupe(
        self, tmp_path: Path
    ) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 9
    title: "Multi"
    designated_weekdays: ["Thu", "Mon", "Thu", "Fri"]
    repeat_after_seconds: 86400
""",
        )
        entries = sl.load_schedule(path)
        # First occurrences in input order: Thu, Mon, Fri.
        assert entries[0].designated_weekdays == ("Thu", "Mon", "Fri")

    def test_absent_designated_weekdays_means_daily(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 7
    title: "Daily"
    repeat_after_seconds: 86400
""",
        )
        entries = sl.load_schedule(path)
        assert entries[0].designated_weekdays == ()
        assert sl.is_day_specific(entries[0]) is False

    def test_empty_list_designated_weekdays_means_daily(
        self, tmp_path: Path
    ) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 8
    title: "Empty list daily"
    designated_weekdays: []
    repeat_after_seconds: 86400
""",
        )
        entries = sl.load_schedule(path)
        assert entries[0].designated_weekdays == ()

    def test_no_habits_section_returns_empty_list(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "operations: []\n")
        entries = sl.load_schedule(path)
        assert entries == []

    def test_empty_file_returns_empty_list(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "")
        entries = sl.load_schedule(path)
        assert entries == []

    def test_loads_real_in_repo_schedule(self) -> None:
        """The actual phase3-schedule.yaml must load cleanly via the new loader."""
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "scripts" / "habits" / "migrations" / "phase3-schedule.yaml"
        if not path.exists():  # pragma: no branch -- present in repo
            pytest.skip("phase3-schedule.yaml not present in this checkout")
        entries = sl.load_schedule(path)
        assert len(entries) >= 1
        # The Friday strength training entry (task 77, per live Vikunja
        # project 13) must be day-specific. Task IDs 75/76/77 = Mon/Wed/Fri.
        fri = [e for e in entries if e.task_id == 77]
        assert fri, "expected task_id=77 (Strength training — Friday) in schedule"
        assert fri[0].designated_weekdays == ("Fri",)
        # task_id 15 is "Meditate" (daily habit), NOT the Friday strength task.
        # Regression guard against the pre-fix mis-binding (#408 cycle 1 bug).
        meditate = [e for e in entries if e.task_id == 15]
        assert meditate, "expected task_id=15 (Meditate) in schedule"
        assert meditate[0].designated_weekdays == ()
        assert "Strength" not in meditate[0].title


# ---------------------------------------------------------------------------
# Validation failures (load-time errors)
# ---------------------------------------------------------------------------


class TestLoadScheduleValidation:
    def test_unknown_weekday_raises(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "Bad weekday"
    designated_weekdays: ["Xyz"]
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="not a valid"):
            sl.load_schedule(path)

    def test_lowercase_weekday_rejected(self, tmp_path: Path) -> None:
        """3-letter ISO names are case-sensitive — `wed` is not `Wed`."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "Lowercase wed"
    designated_weekdays: ["wed"]
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="not a valid"):
            sl.load_schedule(path)

    def test_non_list_designated_weekdays(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "Not a list"
    designated_weekdays: "Wed"
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="must be a list"):
            sl.load_schedule(path)

    def test_non_string_weekday_value(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "Int weekday"
    designated_weekdays: [42]
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="must be a string"):
            sl.load_schedule(path)

    def test_missing_task_id(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - title: "No id"
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="task_id"):
            sl.load_schedule(path)

    def test_zero_task_id_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 0
    title: "Zero id"
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="task_id"):
            sl.load_schedule(path)

    def test_boolean_task_id_rejected(self, tmp_path: Path) -> None:
        """``True`` is an ``int`` subclass; explicitly reject."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: true
    title: "Bool id"
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="task_id"):
            sl.load_schedule(path)

    def test_empty_title_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "   "
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="title"):
            sl.load_schedule(path)

    def test_negative_repeat_after_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 1
    title: "Negative"
    repeat_after_seconds: -1
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="repeat_after_seconds"):
            sl.load_schedule(path)

    def test_duplicate_task_id_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 5
    title: "First"
    repeat_after_seconds: 86400
  - task_id: 5
    title: "Dup"
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="duplicates"):
            sl.load_schedule(path)

    def test_habits_not_a_list_rejected(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "habits: not-a-list\n")
        with pytest.raises(sl.ScheduleConfigError, match="must be a list"):
            sl.load_schedule(path)

    def test_top_level_not_mapping_rejected(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "- just\n- a\n- list\n")
        with pytest.raises(sl.ScheduleConfigError, match="must be a YAML mapping"):
            sl.load_schedule(path)

    def test_invalid_yaml_rejected(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "habits: [not closed\n")
        with pytest.raises(sl.ScheduleConfigError, match="YAML parse error"):
            sl.load_schedule(path)

    def test_missing_file_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(sl.ScheduleConfigError, match="not found"):
            sl.load_schedule(tmp_path / "does-not-exist.yaml")

    def test_entry_not_mapping_rejected(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "habits:\n  - just-a-string\n")
        with pytest.raises(sl.ScheduleConfigError, match="must be a YAML mapping"):
            sl.load_schedule(path)


# ---------------------------------------------------------------------------
# is_day_specific / is_active_today
# ---------------------------------------------------------------------------


class TestIsActiveToday:
    def test_daily_active_every_day(self) -> None:
        e = sl.ScheduleEntry(task_id=1, title="X")
        for day in sl.WEEKDAY_NAMES:
            assert sl.is_active_today(e, day) is True
        assert sl.is_day_specific(e) is False

    def test_day_specific_only_on_designated_day(self) -> None:
        e = sl.ScheduleEntry(
            task_id=2, title="Wed", designated_weekdays=("Wed",)
        )
        assert sl.is_day_specific(e) is True
        assert sl.is_active_today(e, "Wed") is True
        assert sl.is_active_today(e, "Mon") is False
        assert sl.is_active_today(e, "Fri") is False

    def test_multi_day_active_on_each_designated(self) -> None:
        e = sl.ScheduleEntry(
            task_id=3, title="Multi", designated_weekdays=("Mon", "Thu")
        )
        assert sl.is_active_today(e, "Mon") is True
        assert sl.is_active_today(e, "Thu") is True
        assert sl.is_active_today(e, "Tue") is False
        assert sl.is_active_today(e, "Sun") is False

    def test_invalid_weekday_raises(self) -> None:
        e = sl.ScheduleEntry(task_id=4, title="Y")
        with pytest.raises(ValueError, match="must be one of"):
            sl.is_active_today(e, "Xyz")

    def test_weekday_constants(self) -> None:
        """WEEKDAY_NAMES is the canonical Mon=0..Sun=6 ordering."""
        assert sl.WEEKDAY_NAMES == (
            "Mon",
            "Tue",
            "Wed",
            "Thu",
            "Fri",
            "Sat",
            "Sun",
        )
