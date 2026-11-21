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
    rrule: "FREQ=DAILY;INTERVAL=1"
  - task_id: 2
    title: "Wed strength"
    designated_weekdays: ["Wed"]
    rrule: "FREQ=WEEKLY;BYDAY=WE"
""",
        )
        entries = sl.load_schedule(path)
        assert len(entries) == 2
        assert entries[0].task_id == 1
        assert entries[0].designated_weekdays == ()
        assert entries[1].task_id == 2
        assert entries[1].designated_weekdays == ("Wed",)
        assert entries[0].rrule == "FREQ=DAILY;INTERVAL=1"
        assert entries[1].rrule == "FREQ=WEEKLY;BYDAY=WE"

    def test_dedupes_duplicate_weekdays(self, tmp_path: Path) -> None:
        """[Wed, Wed] -> (Wed,) — dedupe silently per the contract."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 5
    title: "Dup Wed"
    designated_weekdays: ["Wed", "Wed", "Wed"]
    rrule: "FREQ=WEEKLY;BYDAY=WE"
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
    rrule: "FREQ=WEEKLY;BYDAY=TH,MO,FR"
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
    rrule: "FREQ=DAILY;INTERVAL=1"
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
    rrule: "FREQ=DAILY;INTERVAL=1"
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

    def test_real_schedule_operations_block_is_frozen(self) -> None:
        """C-005: the frozen ``operations:`` record is byte-identical to the
        pre-mission text (SHA-256 pinned from cc4f2154). Only the header
        comments and the ``habits:`` block may change."""
        import hashlib

        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "scripts" / "habits" / "migrations" / "phase3-schedule.yaml"
        text = path.read_text(encoding="utf-8")
        start = text.index("\noperations:\n") + 1
        end = text.index("\n# ── habits: runtime schedule") + 1
        digest = hashlib.sha256(text[start:end].encode("utf-8")).hexdigest()
        assert digest == (
            "f72b586d889645f392712d8c89465776e765ce9ad4d11c1c0cb0d58f1c8abaa0"
        )

    def test_real_schedule_declares_rules(self) -> None:
        """FR-013: every production habit declares its rule (7 daily + 3 weekday)."""
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "scripts" / "habits" / "migrations" / "phase3-schedule.yaml"
        entries = sl.load_schedule(path)
        rules = {e.task_id: e.rrule for e in entries}
        for daily_id in (14, 15, 16, 18, 19, 20, 65):
            assert rules[daily_id] == "FREQ=DAILY;INTERVAL=1"
        assert rules[75] == "FREQ=WEEKLY;BYDAY=MO"
        assert rules[76] == "FREQ=WEEKLY;BYDAY=WE"
        assert rules[77] == "FREQ=WEEKLY;BYDAY=FR"


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
    rrule: "FREQ=DAILY;INTERVAL=1"
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="not a valid"):
            sl.load_schedule(path)

    def test_day_specific_daily_rule_rejected(self, tmp_path: Path) -> None:
        """#608 ratchet on the rule: a day-specific habit whose rule recurs
        daily (more often than weekly) must fail loudly at load time."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 76
    title: "Strength training — Wednesday"
    designated_weekdays: ["Wed"]
    rrule: "FREQ=DAILY;INTERVAL=1"
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="weekly or less often"):
            sl.load_schedule(path)

    def test_day_specific_byday_mismatch_rejected(self, tmp_path: Path) -> None:
        """#608 ratchet on the rule: BYDAY must equal designated_weekdays."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 75
    title: "Strength training — Monday"
    designated_weekdays: ["Mon"]
    rrule: "FREQ=WEEKLY;BYDAY=TU"
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="BYDAY must equal"):
            sl.load_schedule(path)

    def test_day_specific_missing_byday_rejected(self, tmp_path: Path) -> None:
        """A weekly rule with no BYDAY does not pin the designated weekday."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 75
    title: "Strength training — Monday"
    designated_weekdays: ["Mon"]
    rrule: "FREQ=WEEKLY"
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="BYDAY must equal"):
            sl.load_schedule(path)

    def test_day_specific_byday_compared_as_a_set(self, tmp_path: Path) -> None:
        """BYDAY order and case do not matter; the weekday set does."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 100
    title: "Mon+Thu"
    designated_weekdays: ["Mon", "Thu"]
    rrule: "freq=weekly;byday=th,mo"
""",
        )
        entries = sl.load_schedule(path)
        assert entries[0].designated_weekdays == ("Mon", "Thu")

    def test_day_specific_monthly_rule_allowed(self, tmp_path: Path) -> None:
        """Coarser than weekly is allowed (the floor is weekly)."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 101
    title: "Monthly Monday"
    designated_weekdays: ["Mon"]
    rrule: "FREQ=MONTHLY;BYDAY=MO"
""",
        )
        assert sl.load_schedule(path)[0].rrule == "FREQ=MONTHLY;BYDAY=MO"

    def test_daily_interval_two_rejected(self, tmp_path: Path) -> None:
        """A daily habit must declare exactly FREQ=DAILY;INTERVAL=1."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 14
    title: "Wake at 5:00 AM"
    rrule: "FREQ=DAILY;INTERVAL=2"
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="FREQ=DAILY;INTERVAL=1"):
            sl.load_schedule(path)

    def test_daily_habit_weekly_rule_rejected(self, tmp_path: Path) -> None:
        """A habit with no designated weekdays cannot carry a weekly rule."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 14
    title: "Wake at 5:00 AM"
    rrule: "FREQ=WEEKLY;BYDAY=MO"
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="daily habit"):
            sl.load_schedule(path)

    def test_daily_without_interval_allowed(self, tmp_path: Path) -> None:
        """INTERVAL defaults to 1, so FREQ=DAILY alone is the daily rule."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 14
    title: "Wake at 5:00 AM"
    rrule: "FREQ=DAILY"
""",
        )
        assert sl.load_schedule(path)[0].rrule == "FREQ=DAILY"

    def test_leftover_repeat_after_seconds_rejected(self, tmp_path: Path) -> None:
        """The retired key is refused with a migration message, even beside a rule."""
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 14
    title: "Wake at 5:00 AM"
    rrule: "FREQ=DAILY;INTERVAL=1"
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="repeat_after_seconds.*rrule"):
            sl.load_schedule(path)

    def test_missing_rrule_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 14
    title: "Wake at 5:00 AM"
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match=r"habits\[0\].*rrule"):
            sl.load_schedule(path)

    @pytest.mark.parametrize(
        "rule",
        ["FREQ=SOMETIMES;=", "INTERVAL=1", "FREQ=DAILY;BOGUS=1", "FREQ=WEEKLY;UNTIL=20261231"],
    )
    def test_unparseable_rrule_names_entry_index(self, tmp_path: Path, rule: str) -> None:
        path = _write(
            tmp_path,
            f"""
habits:
  - task_id: 14
    title: "Daily"
    rrule: "FREQ=DAILY;INTERVAL=1"
  - task_id: 15
    title: "Bad rule"
    rrule: "{rule}"
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match=r"habits\[1\].*invalid"):
            sl.load_schedule(path)

    def test_non_string_rrule_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 14
    title: "Daily"
    rrule: 86400
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="rrule must be"):
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
    rrule: "FREQ=DAILY;INTERVAL=1"
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
    rrule: "FREQ=DAILY;INTERVAL=1"
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
    rrule: "FREQ=DAILY;INTERVAL=1"
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
    rrule: "FREQ=DAILY;INTERVAL=1"
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
    rrule: "FREQ=DAILY;INTERVAL=1"
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
    rrule: "FREQ=DAILY;INTERVAL=1"
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
    rrule: "FREQ=DAILY;INTERVAL=1"
""",
        )
        with pytest.raises(sl.ScheduleConfigError, match="title"):
            sl.load_schedule(path)

    def test_duplicate_task_id_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
habits:
  - task_id: 5
    title: "First"
    rrule: "FREQ=DAILY;INTERVAL=1"
  - task_id: 5
    title: "Dup"
    rrule: "FREQ=DAILY;INTERVAL=1"
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
        e = sl.ScheduleEntry(task_id=1, title="X", rrule="FREQ=DAILY;INTERVAL=1")
        for day in sl.WEEKDAY_NAMES:
            assert sl.is_active_today(e, day) is True
        assert sl.is_day_specific(e) is False

    def test_day_specific_only_on_designated_day(self) -> None:
        e = sl.ScheduleEntry(
            task_id=2,
            title="Wed",
            rrule="FREQ=WEEKLY;BYDAY=WE",
            designated_weekdays=("Wed",),
        )
        assert sl.is_day_specific(e) is True
        assert sl.is_active_today(e, "Wed") is True
        assert sl.is_active_today(e, "Mon") is False
        assert sl.is_active_today(e, "Fri") is False

    def test_multi_day_active_on_each_designated(self) -> None:
        e = sl.ScheduleEntry(
            task_id=3,
            title="Multi",
            rrule="FREQ=WEEKLY;BYDAY=MO,TH",
            designated_weekdays=("Mon", "Thu"),
        )
        assert sl.is_active_today(e, "Mon") is True
        assert sl.is_active_today(e, "Thu") is True
        assert sl.is_active_today(e, "Tue") is False
        assert sl.is_active_today(e, "Sun") is False

    def test_invalid_weekday_raises(self) -> None:
        e = sl.ScheduleEntry(task_id=4, title="Y", rrule="FREQ=DAILY;INTERVAL=1")
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
