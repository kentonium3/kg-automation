"""Tests for the date-only due-date migration (#736).

The migration normalizes legacy/UI date-only Vikunja due-dates (midnight in some
tz) to end-of-day ET. These pin the classification (what counts as date-only vs a
genuine datetime), the idempotence (already-EOD-ET values are skipped), and the
apply path: a merge-patch carrying only ``due_date`` (#1111), an instant-based
readback (Vikunja returns due_date as UTC ``Z``, so a string compare of the
ET-offset write would false-fail — #757), and the recurrence-state check (a
stripped rule or a removed reminder must fail; a relative reminder may move).
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from scripts.vikunja import migrate_date_only_due_dates as m
from tests.common.vikunja_v2_factory import make_task, strip_rule, with_reminder

# ---------------------------------------------------------------------------
# Normalizing mock — mimics live Vikunja: a PATCH stores the due_date re-serialized
# to UTC 'Z', so the apply readback exercises the instant-compare (#757), not a
# string compare that would false-fail on the ET-offset write.
# ---------------------------------------------------------------------------


class _NormalizingVikunja:
    def __init__(self, tasks: list[dict]):
        self.tasks = {t["id"]: copy.deepcopy(t) for t in tasks}
        self.posts: list[tuple[int, dict]] = []

    def _pages(self):
        return list(self.tasks.values())

    def list_all_tasks(self, **_):
        # Mirrors VikunjaClient.list_all_tasks — a flat, done-inclusive list.
        return self._pages()

    def get(self, path, **_):
        tid = int(path.rsplit("/", 1)[1])
        return copy.deepcopy(self.tasks[tid])

    def get_task_v2(self, task_id, **_):
        return self.get(f"/tasks/{task_id}")

    def patch_task(self, task_id, changes, **_):
        tid = task_id
        payload = dict(changes)
        due = payload.get("due_date")
        if isinstance(due, str) and due and not due.startswith("0001-01-01"):
            inst = datetime.fromisoformat(due.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
            payload["due_date"] = inst.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.posts.append((tid, dict(changes)))
        self.tasks[tid].update(payload)
        task = self.tasks[tid]
        # Relative reminders recompute from the new due date, as the server
        # does (updateRelativeReminderDates).
        for reminder in task.get("reminders") or []:
            if reminder.get("relative_to") == "due_date":
                base = datetime.fromisoformat(task["due_date"])
                moved = base.timestamp() + reminder["relative_period"]
                reminder["reminder"] = datetime.fromtimestamp(
                    moved, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
        return copy.deepcopy(task)


def _task(tid, due, title="T"):
    return {"id": tid, "title": title, "due_date": due, "project_id": 1}


# ---------------------------------------------------------------------------
# plan_migration — classification
# ---------------------------------------------------------------------------


def test_plan_normalizes_midnight_utc():
    plan = m.plan_migration([_task(1, "2026-06-15T00:00:00Z")])
    assert len(plan) == 1
    assert plan[0]["new_due"] == "2026-06-15T23:59:59-04:00"


def test_plan_normalizes_midnight_edt():
    # 04:00Z = midnight EDT June 15 → same intended date, same EOD-ET target.
    plan = m.plan_migration([_task(1, "2026-06-15T04:00:00Z")])
    assert len(plan) == 1
    assert plan[0]["new_due"] == "2026-06-15T23:59:59-04:00"


def test_plan_normalizes_midnight_est():
    # 05:00Z = midnight EST Jan 15 → EOD-ET Jan 15 (winter offset -05:00).
    plan = m.plan_migration([_task(1, "2026-01-15T05:00:00Z")])
    assert len(plan) == 1
    assert plan[0]["new_due"] == "2026-01-15T23:59:59-05:00"


def test_plan_skips_genuine_datetime():
    # A real time-of-day (11:30) is a timed event — left untouched.
    assert m.plan_migration([_task(1, "2026-06-15T11:30:00Z")]) == []


def test_plan_idempotent_on_already_eod_et():
    # An already-normalized EOD-ET value is not midnight → skipped.
    assert m.plan_migration([_task(1, "2026-06-15T23:59:59-04:00")]) == []


def test_plan_skips_no_due_and_sentinel():
    tasks = [
        _task(1, None),
        _task(2, ""),
        _task(3, "0001-01-01T00:00:00Z"),
    ]
    assert m.plan_migration(tasks) == []


def test_plan_reports_id_title_and_old_due():
    plan = m.plan_migration([_task(7, "2026-06-15T00:00:00Z", title="Pay rent")])
    assert plan[0]["task_id"] == 7
    assert plan[0]["title"] == "Pay rent"
    assert plan[0]["old_due"] == "2026-06-15T00:00:00Z"


# ---------------------------------------------------------------------------
# apply_change — RMW + instant readback
# ---------------------------------------------------------------------------


def test_apply_writes_eod_et_and_readback_passes():
    client = _NormalizingVikunja([_task(1, "2026-06-15T00:00:00Z")])
    task = client.get("/tasks/1")
    m.apply_change(client, task, "2026-06-15T23:59:59-04:00")
    # Stored as UTC-Z by the normalizing mock; the same instant as our write.
    assert client.tasks[1]["due_date"] == "2026-06-16T03:59:59Z"


def test_apply_patch_body_is_exactly_due_date():
    client = _NormalizingVikunja([make_task(id=1, due_date="2026-06-15T00:00:00Z")])
    task = client.get("/tasks/1")
    m.apply_change(client, task, "2026-06-15T23:59:59-04:00")
    assert client.posts == [(1, {"due_date": "2026-06-15T23:59:59-04:00"})]


def test_apply_recurring_task_keeps_rule_and_moves_relative_reminder():
    # A relative reminder legitimately moves with the due date (R-001 hazard 6).
    start = with_reminder(make_task(id=1, due_date="2026-06-15T00:00:00Z"))
    client = _NormalizingVikunja([start])
    m.apply_change(client, client.get("/tasks/1"), "2026-06-15T23:59:59-04:00")
    # due 00:00Z - 1h before the write; EOD-ET (03:59:59Z next day) - 1h after.
    assert start["reminders"][0]["reminder"] == "2026-06-14T23:00:00Z"
    assert client.tasks[1]["reminders"][0]["reminder"] == "2026-06-16T02:59:59Z"
    assert client.tasks[1]["repeat"] == {"freq": "daily", "interval": 1}


def test_apply_readback_stripped_rule_raises():
    # Positive control (#1111): the readback lost the rule → fail loud.
    class _StrippingVikunja(_NormalizingVikunja):
        def get_task_v2(self, task_id, **kw):
            return strip_rule(super().get_task_v2(task_id, **kw))

    client = _StrippingVikunja([make_task(id=1, due_date="2026-06-15T00:00:00Z")])
    task = client.get("/tasks/1")
    with pytest.raises(m.MigrationError, match="'repeat' changed"):
        m.apply_change(client, task, "2026-06-15T23:59:59-04:00")


def test_apply_readback_removed_reminder_raises():
    class _DroppingVikunja(_NormalizingVikunja):
        def get_task_v2(self, task_id, **kw):
            return {**super().get_task_v2(task_id, **kw), "reminders": []}

    start = with_reminder(make_task(id=1, due_date="2026-06-15T00:00:00Z"))
    client = _DroppingVikunja([start])
    with pytest.raises(m.MigrationError, match="'reminders' changed"):
        m.apply_change(client, client.get("/tasks/1"), "2026-06-15T23:59:59-04:00")


def _flagged_task():
    """From-current recurring task with a whole-day relative reminder (cycle 1)."""
    return with_reminder(
        make_task(id=1, due_date="2026-06-15T00:00:00Z", repeats_from_current_date=True),
        relative_period=-86400,
    )


def test_apply_flagged_task_keeps_flag_and_reminder():
    client = _NormalizingVikunja([_flagged_task()])
    m.apply_change(client, client.get("/tasks/1"), "2026-06-15T23:59:59-04:00")
    stored = client.tasks[1]
    assert stored["repeats_from_current_date"] is True
    assert [r["relative_period"] for r in stored["reminders"]] == [-86400]


def test_apply_flagged_task_flip_control_raises():
    class _FlippingVikunja(_NormalizingVikunja):
        def get_task_v2(self, task_id, **kw):
            return {**super().get_task_v2(task_id, **kw), "repeats_from_current_date": False}

    client = _FlippingVikunja([_flagged_task()])
    with pytest.raises(m.MigrationError, match="repeats_from_current_date"):
        m.apply_change(client, client.get("/tasks/1"), "2026-06-15T23:59:59-04:00")


def test_apply_flagged_task_remove_control_raises():
    class _DroppingVikunja(_NormalizingVikunja):
        def get_task_v2(self, task_id, **kw):
            return {**super().get_task_v2(task_id, **kw), "reminders": None}

    client = _DroppingVikunja([_flagged_task()])
    with pytest.raises(m.MigrationError, match="'reminders' changed"):
        m.apply_change(client, client.get("/tasks/1"), "2026-06-15T23:59:59-04:00")


# ---------------------------------------------------------------------------
# main — dry-run vs apply
# ---------------------------------------------------------------------------


def test_main_dry_run_writes_nothing(capsys):
    client = _NormalizingVikunja(
        [_task(1, "2026-06-15T00:00:00Z"), _task(2, "2026-06-15T11:30:00Z")]
    )
    rc = m.main([], client=client)
    assert rc == 0
    assert client.posts == []  # no writes on dry-run
    out = capsys.readouterr().out
    assert "DRY-RUN: 1 date-only" in out


def test_main_apply_normalizes(capsys):
    client = _NormalizingVikunja(
        [_task(1, "2026-06-15T00:00:00Z"), _task(2, "2026-06-15T11:30:00Z")]
    )
    rc = m.main(["--apply"], client=client)
    assert rc == 0
    assert len(client.posts) == 1  # only the date-only task written
    assert client.posts[0][0] == 1
    assert capsys.readouterr().out.strip().endswith("applied=1")
