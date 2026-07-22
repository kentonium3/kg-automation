"""Tests for the date-only due-date migration (#736).

The migration normalizes legacy/UI date-only Vikunja due-dates (midnight in some
tz) to end-of-day ET. These pin the classification (what counts as date-only vs a
genuine datetime), the idempotence (already-EOD-ET values are skipped), and the
apply path's instant-based readback (Vikunja returns due_date as UTC ``Z``, so a
string compare of the ET-offset write would false-fail — #757).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.vikunja import migrate_date_only_due_dates as m


# ---------------------------------------------------------------------------
# Normalizing mock — mimics live Vikunja: a POST stores the due_date re-serialized
# to UTC 'Z', so the apply readback exercises the instant-compare (#757), not a
# string compare that would false-fail on the ET-offset write.
# ---------------------------------------------------------------------------


class _NormalizingVikunja:
    def __init__(self, tasks: list[dict]):
        self.tasks = {t["id"]: dict(t) for t in tasks}
        self.posts: list[tuple[int, dict]] = []

    def _pages(self):
        return list(self.tasks.values())

    def list_all_tasks(self, **_):
        # Mirrors VikunjaClient.list_all_tasks — a flat, done-inclusive list.
        return self._pages()

    def get(self, path, **_):
        tid = int(path.rsplit("/", 1)[1])
        return dict(self.tasks[tid])

    def post(self, path, *, json=None, **_):
        tid = int(path.rsplit("/", 1)[1])
        payload = dict(json or {})
        due = payload.get("due_date")
        if isinstance(due, str) and due and not due.startswith("0001-01-01"):
            inst = datetime.fromisoformat(due.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
            payload["due_date"] = inst.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.tasks[tid].update(payload)
        self.posts.append((tid, payload))
        return dict(self.tasks[tid])


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


def test_apply_readback_detects_other_field_drift():
    class _DriftingVikunja(_NormalizingVikunja):
        def get(self, path, **kw):
            r = super().get(path, **kw)
            if path != "/tasks/all":
                r["title"] = "CHANGED"  # simulate a partial-replace zeroing
            return r

    client = _DriftingVikunja([_task(1, "2026-06-15T00:00:00Z", title="Keep")])
    task = {"id": 1, "title": "Keep", "due_date": "2026-06-15T00:00:00Z", "project_id": 1}
    with pytest.raises(m.MigrationError, match="drifted"):
        m.apply_change(client, task, "2026-06-15T23:59:59-04:00")


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
