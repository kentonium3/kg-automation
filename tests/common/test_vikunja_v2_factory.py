"""Tests for tests.common.vikunja_v2_factory (WP01, #1111)."""

from __future__ import annotations

from scripts.common.vikunja_rule import has_rule
from tests.common.vikunja_v2_factory import (
    V2_TASK_KEYS,
    make_list_task,
    make_task,
    strip_rule,
    with_reminder,
)


def test_default_key_set_matches_live_v2_capture() -> None:
    assert set(make_task()) == set(V2_TASK_KEYS)
    assert len(V2_TASK_KEYS) == len(set(V2_TASK_KEYS)) == 33


def test_default_values_mirror_task_14() -> None:
    task = make_task()
    assert task["id"] == 14
    assert task["done"] is False
    assert task["due_date"] == "2026-11-20T04:59:59Z"
    assert task["repeat"] == {"freq": "daily", "interval": 1}
    assert task["repeats_rrule"] == "FREQ=DAILY;INTERVAL=1"
    assert task["repeats_from_current_date"] is False
    assert task["reminders"] is None


def test_repeat_override_derives_rrule_text() -> None:
    task = make_task(repeat={"freq": "weekly", "interval": 1, "by_day": ["mo"]})
    assert task["repeats_rrule"] == "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO"


def test_explicit_rrule_override_wins() -> None:
    task = make_task(repeat={"freq": "weekly", "interval": 1}, repeats_rrule="FREQ=WEEKLY")
    assert task["repeats_rrule"] == "FREQ=WEEKLY"


def test_repeat_none_override_drops_rrule() -> None:
    assert "repeats_rrule" not in make_task(repeat=None)


def test_overrides_are_not_shared_between_tasks() -> None:
    rule = {"freq": "daily", "interval": 1}
    task = make_task(repeat=rule)
    task["repeat"]["interval"] = 5
    assert rule["interval"] == 1
    assert make_task()["labels"] is not make_task()["labels"]


def test_list_task_lacks_repeats_rrule() -> None:
    task = make_list_task()
    assert "repeats_rrule" not in task
    assert set(task) == set(V2_TASK_KEYS) - {"repeats_rrule"}


def test_strip_rule_removes_rule_without_mutating_input() -> None:
    task = make_task(repeats_from_current_date=True)
    stripped = strip_rule(task)
    assert stripped["repeat"] is None
    assert "repeats_rrule" not in stripped
    assert stripped["repeats_from_current_date"] is False
    assert not has_rule(stripped)
    assert has_rule(task) and task["repeats_from_current_date"] is True


def test_with_reminder_computes_instant_from_referenced_date() -> None:
    # Server d7e202228 computes reminder = due_date + relative_period.
    task = with_reminder(make_task())
    assert task["reminders"] == [
        {"reminder": "2026-11-20T03:59:59Z", "relative_period": -3600, "relative_to": "due_date"}
    ]
    twice = with_reminder(task, relative_period=-60)
    assert len(twice["reminders"]) == 2
    assert twice["reminders"][1]["reminder"] == "2026-11-20T04:58:59Z"
    assert len(task["reminders"]) == 1


def test_with_reminder_offset_due_date_is_rendered_utc() -> None:
    task = with_reminder(make_task(due_date="2026-11-19T23:59:59-05:00"), relative_period=-1800)
    assert task["reminders"][0]["reminder"] == "2026-11-20T04:29:59Z"


def test_with_reminder_unset_only_when_referenced_date_absent() -> None:
    # make_task's start_date is the unset sentinel.
    task = with_reminder(make_task(), relative_to="start_date")
    assert task["reminders"][0]["reminder"] == "0001-01-01T00:00:00Z"
    no_due = with_reminder(make_task(due_date=None))
    assert no_due["reminders"][0]["reminder"] == "0001-01-01T00:00:00Z"
