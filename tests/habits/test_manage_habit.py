"""Tests for :mod:`scripts.habits.manage_habit` (#1111 WP12, FR-026).

A real :class:`VikunjaClient` against the stateful ``FakeVikunja`` from
``tests/vikunja/test_update_task.py``. The habit carries a weekly rule,
``repeats_from_current_date=true`` and a relative plus an absolute reminder;
after pause, resume and remove everything that should survive does.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

import pytest

from scripts.common import vikunja_scope
from scripts.habits import manage_habit as mh
from tests.vikunja.test_update_task import (
    ABSOLUTE,
    FakeVikunja,
    _drop_reminders,
    _flip_flag,
    _strip_rule,
    client,
    recurring_task,
)

HABITS_PROJECT = vikunja_scope.habit_project_id()


@pytest.fixture
def serve(monkeypatch):
    def install(*tasks: dict[str, Any], **kwargs: Any) -> FakeVikunja:
        server = FakeVikunja(*tasks, **kwargs)
        monkeypatch.setattr(urllib.request, "urlopen", server)
        return server

    return install


def habit(**overrides: Any) -> dict[str, Any]:
    return recurring_task(project_id=HABITS_PROJECT, **overrides)


def run_cli(capsys, *argv: str) -> tuple[int, dict[str, Any]]:
    code = mh.main(list(argv), client=client())
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return code, json.loads(lines[-1])


def _kept(before: dict[str, Any], after: dict[str, Any]) -> None:
    """The rule, the flag and both reminders survived (relative by kind)."""
    assert after["repeat"] == before["repeat"]
    assert after["repeats_rrule"] == before["repeats_rrule"]
    assert after["repeats_from_current_date"] is True
    assert [r["relative_to"] for r in after["reminders"]] == ["due_date", ""]
    assert after["reminders"][1] == ABSOLUTE


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "paused"),
    [
        ("(PAUSED) <p>Stretch</p>", True),
        ("(PAUSED) ", True),
        ("(PAUSED)", True),
        ("<p>(PAUSED) Stretch</p>", True),
        ("  (PAUSED) Stretch", True),
        ("<p>Stretch</p>", False),
        ("Stretch (PAUSED)", False),
        ("(paused) Stretch", False),
        ("PAUSED Stretch", False),
        ("", False),
        (None, False),
        (42, False),
    ],
)
def test_is_paused_tests_the_description_prefix(description, paused):
    assert mh.is_paused({"description": description}) is paused


def test_title_containing_paused_is_not_paused():
    assert mh.is_paused({"title": "(PAUSED) Stretch", "description": "<p>x</p>"}) is False
    assert mh.is_paused({"title": "(PAUSED) Stretch"}) is False


@pytest.mark.parametrize(
    "description", ["<p>Stretch</p>", "", "Plain text", "<p>(PAUSED) inner</p>"]
)
def test_prefix_round_trip(description):
    paused = mh.add_paused_prefix(description)
    assert mh.is_paused({"description": paused})
    assert mh.strip_paused_prefix(paused) == description


def test_strip_keeps_the_editor_paragraph():
    assert mh.strip_paused_prefix("<p>(PAUSED) Stretch</p>") == "<p>Stretch</p>"


# ---------------------------------------------------------------------------
# pause / resume round trip
# ---------------------------------------------------------------------------


def test_pause_then_resume_round_trip_keeps_rule_and_reminders(serve, capsys):
    task = habit()
    server = serve(task)

    code, summary = run_cli(capsys, "pause", "--task-id", "14")
    assert code == 0 and summary["outcome"] == "paused"
    assert server.patch_bodies() == [{"description": "(PAUSED) <p>Stretch for ten minutes</p>"}]
    assert mh.is_paused(server.tasks[14])
    _kept(task, server.tasks[14])

    code, summary = run_cli(capsys, "resume", "--task-id", "14")
    assert code == 0 and summary["outcome"] == "resumed"
    assert server.patch_bodies()[-1] == {"description": "<p>Stretch for ten minutes</p>"}
    assert server.tasks[14]["description"] == task["description"]
    _kept(task, server.tasks[14])
    assert "DELETE" not in server.methods()


def test_pause_is_idempotent(serve, capsys):
    server = serve(habit(description="(PAUSED) <p>x</p>"))

    code, summary = run_cli(capsys, "pause", "--task-id", "14")

    assert code == 0 and summary["outcome"] == "already_paused"
    assert server.writes() == []


def test_resume_of_active_habit_is_a_no_op(serve, capsys):
    server = serve(habit())

    code, summary = run_cli(capsys, "resume", "--task-id", "14")

    assert code == 0 and summary["outcome"] == "not_paused"
    assert server.writes() == []


def test_pause_with_empty_description_sends_no_null(serve, capsys):
    server = serve(habit(description=""))

    code, _summary = run_cli(capsys, "pause", "--task-id", "14")

    assert code == 0
    assert server.patch_bodies() == [{"description": "(PAUSED) "}]


@pytest.mark.parametrize("damage", [_drop_reminders, _flip_flag, _strip_rule])
@pytest.mark.parametrize("action", ["pause", "resume"])
def test_pause_and_resume_go_through_the_readback_guard(serve, capsys, damage, action):
    description = "(PAUSED) <p>x</p>" if action == "resume" else "<p>x</p>"
    serve(habit(description=description), damage=damage)

    code, summary = run_cli(capsys, action, "--task-id", "14")

    assert code == mh.EXIT_UNEXPECTED
    assert summary["ok"] is False and summary["outcome"] == "unexpected"
    assert summary["error"] == "rule_drift"


def test_description_not_sticking_is_unexpected(serve, capsys):
    def revert(task):
        task["description"] = "<p>x</p>"

    serve(habit(description="<p>x</p>"), damage=revert)

    code, summary = run_cli(capsys, "pause", "--task-id", "14")

    assert code == mh.EXIT_UNEXPECTED
    assert summary["error"] == "field_mismatch"


# ---------------------------------------------------------------------------
# remove: end the series, never delete
# ---------------------------------------------------------------------------


def test_remove_ends_the_series_in_two_patches_and_never_deletes(serve, capsys):
    server = serve(habit())

    code, summary = run_cli(capsys, "remove", "--task-id", "14")

    assert code == 0 and summary["outcome"] == "removed"
    assert server.patch_bodies() == [{"repeat": None}, {"done": True}]
    stored = server.tasks[14]
    assert stored["done"] is True and stored["repeat"] is None
    assert "repeats_rrule" not in stored
    assert stored["description"] == "<p>Stretch for ten minutes</p>"
    assert "DELETE" not in server.methods()


def test_remove_of_an_ended_habit_writes_nothing(serve, capsys):
    server = serve(habit(done=True, repeat=None))

    code, summary = run_cli(capsys, "remove", "--task-id", "14")

    assert code == 0 and summary["outcome"] == "removed"
    assert server.writes() == []


def test_remove_failure_after_rule_cleared_surfaces_recovery_state(serve, capsys):
    server = serve(habit(), patch_status={2: 400})

    code, summary = run_cli(capsys, "remove", "--task-id", "14")

    assert code == mh.EXIT_UNEXPECTED
    assert summary["outcome"] == "partial"
    assert summary["state"] == "rule_cleared_not_done"
    assert "run remove again" in summary["message"]
    # No blind retry: exactly the two PATCHes end_series makes.
    assert server.patch_bodies() == [{"repeat": None}, {"done": True}]
    assert "DELETE" not in server.methods()

    # Running remove again resumes from the fresh read.
    server.patch_status = {}
    code, summary = run_cli(capsys, "remove", "--task-id", "14")
    assert code == 0 and summary["outcome"] == "removed"
    assert server.patch_bodies()[-1] == {"done": True}
    assert server.tasks[14]["done"] is True


def test_remove_refused_first_write_is_error_with_nothing_changed(serve, capsys):
    server = serve(habit(), patch_status={1: 403})

    code, summary = run_cli(capsys, "remove", "--task-id", "14")

    assert code == mh.EXIT_UNEXPECTED
    assert summary["outcome"] == "error"
    assert server.tasks[14]["repeat"] is not None


# ---------------------------------------------------------------------------
# Refusals and usage errors: no write
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["pause", "resume", "remove"])
def test_non_habit_task_is_refused(serve, capsys, action):
    server = serve(recurring_task(project_id=HABITS_PROJECT + 1))

    code, summary = run_cli(capsys, action, "--task-id", "14")

    assert code == mh.EXIT_USAGE
    assert summary["outcome"] == "refused" and summary["error"] == "not_a_habit"
    assert server.writes() == []


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["pause"],
        ["delete", "--task-id", "14"],
        ["archive", "--task-id", "14"],
        ["pause", "--task-id", "0"],
        ["pause", "--task-id", "x"],
        ["pause", "--task-id", "14", "--force"],
        ["remove", "--task", "14"],
    ],
)
def test_usage_errors_exit_2_without_a_request(serve, capsys, argv):
    server = serve(habit())

    code, summary = run_cli(capsys, *argv)

    assert code == mh.EXIT_USAGE
    assert summary["outcome"] == "refused"
    assert server.requests == []


def test_unreadable_task_is_error(serve, capsys):
    server = serve(habit(), get_status=500)

    code, summary = run_cli(capsys, "pause", "--task-id", "14")

    assert code == mh.EXIT_UNEXPECTED and summary["outcome"] == "error"
    assert server.writes() == []
