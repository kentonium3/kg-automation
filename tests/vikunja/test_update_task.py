"""Tests for :mod:`scripts.vikunja.update_task` (#1111 WP12, FR-025).

They drive a **real** :class:`scripts.common.vikunja_client.VikunjaClient`
against :class:`FakeVikunja`, a stateful fake of the fork's v2 task surface
installed over ``urllib.request.urlopen``, so the exact wire traffic (merge
patch bodies, request order, the absence of any write) is what is pinned.
Task bodies come from the shared v2 factory: a weekly rule with
``repeats_from_current_date=true`` and one relative plus one absolute reminder.

``FakeVikunja`` is imported by ``tests/habits/test_manage_habit.py`` too.
"""

from __future__ import annotations

import copy
import io
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, timedelta
from typing import Any, Self

import pytest

from scripts.common.et_datetime import parse_vikunja_instant
from scripts.common.vikunja_client import VikunjaClient
from scripts.vikunja import update_task as ut
from tests.common.vikunja_v2_factory import make_task, strip_rule, with_reminder

BASE = "https://vikunja.test"
MERGE_PATCH = "application/merge-patch+json"
_V2_TASK = re.compile(r"^/api/v2/tasks/(\d+)$")

WEEKLY = {"freq": "weekly", "interval": 1, "by_day": ["mo"]}
ABSOLUTE = {"reminder": "2026-11-22T13:00:00Z", "relative_period": 0, "relative_to": ""}


def _utc_z(value: Any) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def recurring_task(**overrides: Any) -> dict[str, Any]:
    """A from-completion weekly habit with a relative and an absolute reminder."""
    fields: dict[str, Any] = {
        "id": 14,
        "project_id": 13,
        "repeat": WEEKLY,
        "repeats_from_current_date": True,
        "due_date": "2026-11-24T04:59:59Z",
        "description": "<p>Stretch for ten minutes</p>",
    }
    fields.update(overrides)
    task = with_reminder(make_task(**fields), relative_period=-3600)
    task["reminders"].append(dict(ABSOLUTE))
    return task


def one_off_task(**overrides: Any) -> dict[str, Any]:
    task = recurring_task(**overrides)
    return strip_rule(task)


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._buf = io.BytesIO(body)

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self._buf.close()


def _http_error(url: str, status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url,
        status,
        "error",
        None,  # type: ignore[arg-type]
        io.BytesIO(b'{"code": 0, "message": "simulated"}'),
    )


class FakeVikunja:
    """Stateful fake of ``GET``/``PATCH /api/v2/tasks/{id}`` (vikunja-harness d7e202228).

    Server facts modelled: a merge-patch ``null`` deletes the key (``repeat``
    takes ``repeats_rrule`` with it); ``done=true`` on a task that still has a
    rule advances it instead of finishing it; every save recomputes relative
    reminders from their base date.

    Knobs: ``damage`` mutates the task after each applied PATCH (the
    corruption controls); ``patch_status`` maps a 1-based PATCH ordinal to an
    HTTP error answered without applying it; ``answer_304`` answers every
    PATCH 304, applying it first when ``apply_on_304`` (a concurrent writer
    already stored the value).
    """

    def __init__(
        self,
        *tasks: dict[str, Any],
        damage: Callable[[dict[str, Any]], None] | None = None,
        patch_status: dict[int, int] | None = None,
        get_status: int | None = None,
        answer_304: bool = False,
        apply_on_304: bool = False,
    ) -> None:
        self.tasks = {t["id"]: copy.deepcopy(t) for t in tasks}
        self.damage = damage
        self.patch_status = dict(patch_status or {})
        self.get_status = get_status
        self.answer_304 = answer_304
        self.apply_on_304 = apply_on_304
        self.requests: list[tuple[str, str, Any]] = []
        self._patches = 0

    def methods(self) -> list[str]:
        return [method for method, _path, _body in self.requests]

    def patch_bodies(self) -> list[dict[str, Any]]:
        return [body for method, _p, body in self.requests if method == "PATCH"]

    def writes(self) -> list[tuple[str, str, Any]]:
        return [r for r in self.requests if r[0] != "GET"]

    def _apply(self, task: dict[str, Any], body: dict[str, Any]) -> None:
        for key, value in body.items():
            if value is None:
                task[key] = None
                if key == "repeat":
                    task.pop("repeats_rrule", None)
            else:
                task[key] = copy.deepcopy(value)
        if task.get("done") is True and task.get("repeat"):
            due = parse_vikunja_instant(task["due_date"])
            assert due is not None
            task["due_date"] = _utc_z(due + timedelta(days=7))
            task["done"] = False
        for reminder in task.get("reminders") or []:
            anchor = reminder.get("relative_to")
            if anchor:
                base = parse_vikunja_instant(task.get(anchor))
                if base is not None:
                    reminder["reminder"] = _utc_z(
                        base + timedelta(seconds=reminder["relative_period"])
                    )

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _Resp:
        method = req.get_method()
        path = req.full_url[len(BASE) :].split("?", 1)[0]
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        self.requests.append((method, path, body))
        match = _V2_TASK.match(path)
        if match is None:
            pytest.fail(f"unexpected request {method} {path}")
        task_id = int(match.group(1))
        if method == "GET":
            if self.get_status is not None:
                raise _http_error(req.full_url, self.get_status)
            if task_id not in self.tasks:
                raise _http_error(req.full_url, 404)
            return self._ok(self.tasks[task_id])
        if method == "PATCH":
            assert req.get_header("Content-type") == MERGE_PATCH
            self._patches += 1
            status = self.patch_status.get(self._patches)
            if status is not None:
                raise _http_error(req.full_url, status)
            task = self.tasks[task_id]
            if self.answer_304:
                if self.apply_on_304:
                    self._apply(task, body)
                raise _http_error(req.full_url, 304)
            self._apply(task, body)
            if self.damage is not None:
                self.damage(task)
            return self._ok(task)
        pytest.fail(f"unexpected request {method} {path}")

    @staticmethod
    def _ok(payload: Any) -> _Resp:
        return _Resp(json.dumps(payload).encode("utf-8"))


@pytest.fixture
def serve(monkeypatch):
    def install(*tasks: dict[str, Any], **kwargs: Any) -> FakeVikunja:
        server = FakeVikunja(*tasks, **kwargs)
        monkeypatch.setattr(urllib.request, "urlopen", server)
        return server

    return install


def client() -> VikunjaClient:
    return VikunjaClient(base_url=f"{BASE}/api/v1", token="test-token-not-real")


def run_cli(capsys, *argv: str) -> tuple[int, dict[str, Any], str]:
    """Run the CLI; return (exit code, parsed last stdout line, stderr)."""
    code = ut.main(list(argv), client=client())
    out = capsys.readouterr()
    lines = [line for line in out.out.splitlines() if line.strip()]
    return code, json.loads(lines[-1]), out.err


def _no_nulls(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return all(_no_nulls(v) for v in value.values())
    if isinstance(value, list):
        return all(_no_nulls(v) for v in value)
    return True


def _rule_state(task: dict[str, Any]) -> tuple[Any, ...]:
    return (
        task.get("repeat"),
        task.get("repeats_rrule"),
        task.get("repeats_from_current_date"),
        [r["relative_to"] for r in task.get("reminders") or []],
        [r["reminder"] for r in task.get("reminders") or [] if not r["relative_to"]],
    )


# ---------------------------------------------------------------------------
# Round trips: only the changed keys go out; the rule, flag and reminders stay
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "body"),
    [
        (["--title", "Stretch 15 min"], {"title": "Stretch 15 min"}),
        (
            ["--description", "<p>Ten minutes, slow</p>"],
            {"description": "<p>Ten minutes, slow</p>"},
        ),
        (["--priority", "3"], {"priority": 3}),
        (["--project-id", "20"], {"project_id": 20}),
    ],
    ids=["title", "description", "priority", "project"],
)
def test_single_field_change_keeps_rule(serve, capsys, argv, body):
    task = recurring_task()
    server = serve(task)

    code, summary, _err = run_cli(capsys, "--task-id", "14", *argv)

    assert code == ut.EXIT_OK
    assert summary["ok"] is True and summary["outcome"] == "updated"
    assert server.patch_bodies() == [body]
    assert server.methods() == ["GET", "PATCH", "GET"]
    stored = server.tasks[14]
    assert _rule_state(stored) == _rule_state(task)
    for key, value in body.items():
        assert stored[key] == value


def test_several_fields_send_only_the_changed_ones(serve, capsys):
    server = serve(recurring_task(priority=2))

    code, summary, _ = run_cli(
        capsys, "--task-id", "14", "--title", "Stretch", "--priority", "2", "--project-id", "20"
    )

    assert code == 0
    assert server.patch_bodies() == [{"title": "Stretch", "project_id": 20}]
    assert summary["requested"] == ["priority", "project_id", "title"]
    assert summary["written"] == ["project_id", "title"]


def test_due_change_on_one_off_task_keeps_reminders(serve, capsys):
    server = serve(one_off_task())

    code, summary, _ = run_cli(capsys, "--task-id", "14", "--due", "2026-11-25T23:59:59-05:00")

    assert code == 0, summary
    assert server.patch_bodies() == [{"due_date": "2026-11-25T23:59:59-05:00"}]
    # The relative reminder moved with the due date (not damage); the
    # absolute one stayed put.
    reminders = server.tasks[14]["reminders"]
    assert reminders[0]["reminder"] == "2026-11-26T03:59:59Z"
    assert reminders[1] == ABSOLUTE


def test_same_values_write_nothing(serve, capsys):
    server = serve(recurring_task(title="Stretch", priority=1))

    code, summary, _ = run_cli(capsys, "--task-id", "14", "--title", " Stretch ", "--priority", "1")

    assert code == 0
    assert summary["outcome"] == "unchanged"
    assert server.writes() == []


def test_equal_due_instant_in_another_offset_writes_nothing(serve, capsys):
    server = serve(one_off_task(due_date="2026-11-26T04:59:59Z"))

    code, summary, _ = run_cli(capsys, "--task-id", "14", "--due", "2026-11-25T23:59:59-05:00")

    assert code == 0 and summary["outcome"] == "unchanged"
    assert server.writes() == []


def test_empty_description_is_sent_as_empty_string_not_null(serve, capsys):
    server = serve(recurring_task())

    code, _summary, _ = run_cli(capsys, "--task-id", "14", "--description", "")

    assert code == 0
    assert server.patch_bodies() == [{"description": ""}]


def test_304_with_value_stored_is_success_without_change(serve, capsys):
    server = serve(recurring_task(), answer_304=True, apply_on_304=True)

    code, summary, _ = run_cli(capsys, "--task-id", "14", "--title", "Stretch")

    assert code == 0
    assert summary["ok"] is True and summary["outcome"] == "unchanged"
    assert server.methods() == ["GET", "PATCH", "GET"]


def test_304_without_the_value_is_unexpected(serve, capsys):
    serve(recurring_task(), answer_304=True)

    code, summary, _ = run_cli(capsys, "--task-id", "14", "--title", "Stretch")

    assert code == ut.EXIT_UNEXPECTED
    assert summary["outcome"] == "unexpected"
    assert summary["mismatch"] == ["title"]


# ---------------------------------------------------------------------------
# Corruption controls: the readback guard must fail loud
# ---------------------------------------------------------------------------


def _drop_reminders(task: dict[str, Any]) -> None:
    task["reminders"] = None


def _flip_flag(task: dict[str, Any]) -> None:
    task["repeats_from_current_date"] = not task["repeats_from_current_date"]


def _strip_rule(task: dict[str, Any]) -> None:
    stripped = strip_rule(task)
    stripped["repeats_from_current_date"] = task["repeats_from_current_date"]
    task.clear()
    task.update(stripped)


def _move_absolute(task: dict[str, Any]) -> None:
    for reminder in task["reminders"]:
        if not reminder["relative_to"]:
            reminder["reminder"] = "2026-11-29T13:00:00Z"


def _ignore_title(task: dict[str, Any]) -> None:
    task["title"] = "Wake at 5:00 AM"


@pytest.mark.parametrize(
    ("damage", "drift", "mismatch"),
    [
        (_drop_reminders, ["reminders"], []),
        (_flip_flag, ["repeats_from_current_date"], []),
        (_strip_rule, ["repeat"], []),
        (_move_absolute, ["reminders"], []),
        (_ignore_title, [], ["title"]),
    ],
    ids=["reminders-dropped", "flag-flipped", "rule-dropped", "absolute-moved", "field-ignored"],
)
def test_corrupted_readback_exits_unexpected(serve, capsys, damage, drift, mismatch):
    serve(recurring_task(), damage=damage)

    code, summary, err = run_cli(capsys, "--task-id", "14", "--title", "Stretch 15 min")

    assert code == ut.EXIT_UNEXPECTED
    assert summary["ok"] is False
    assert summary["outcome"] == "unexpected"
    assert summary["drift"] == drift
    assert summary["mismatch"] == mismatch
    assert summary["write_attempted"] is True
    assert err.startswith("ERROR: ")


def test_rule_dropped_on_project_move_is_unexpected(serve):
    serve(recurring_task(), damage=_strip_rule)

    result = ut.update_task(client(), 14, {"project_id": 20})

    assert result.outcome == "unexpected"
    assert result.error == "rule_drift"
    assert result.drift == ["repeat"]


# ---------------------------------------------------------------------------
# Refusals: zero writes (and no request at all when input is bad)
# ---------------------------------------------------------------------------


def test_due_change_on_recurring_task_is_refused_before_any_write(serve, capsys):
    server = serve(recurring_task())

    code, summary, err = run_cli(capsys, "--task-id", "14", "--due", "2026-11-30T23:59:59-05:00")

    assert code == ut.EXIT_USAGE
    assert summary["outcome"] == "refused"
    assert summary["error"] == "recurring_due_change"
    assert server.methods() == ["GET"]
    assert "change it in Vikunja" in err


def test_due_refusal_also_holds_for_half_shaped_rule(serve, capsys):
    task = recurring_task()
    task["repeat"] = None  # repeats_rrule still present
    server = serve(task)

    code, summary, _ = run_cli(capsys, "--task-id", "14", "--due", "2026-11-30T23:59:59-05:00")

    assert code == ut.EXIT_USAGE and summary["error"] == "recurring_due_change"
    assert server.writes() == []


def test_due_change_with_other_fields_writes_none_of_them(serve, capsys):
    server = serve(recurring_task())

    code, _summary, _ = run_cli(
        capsys, "--task-id", "14", "--title", "X", "--due", "2026-11-30T23:59:59-05:00"
    )

    assert code == ut.EXIT_USAGE
    assert server.writes() == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--task-id", "14"],  # empty change set
        ["--task-id", "14", "--rrule", "FREQ=DAILY"],
        ["--task-id", "14", "--repeat", "daily"],
        ["--task-id", "14", "--done"],
        ["--task-id", "14", "--desc", "x"],  # no abbreviations
        ["--task-id", "14", "--from-completion"],
        ["--task-id", "14", "--priority", "9"],
        ["--task-id", "14", "--priority", "high"],
        ["--task-id", "14", "--title", "   "],
        ["--task-id", "14", "--due", "tomorrow"],
        ["--task-id", "14", "--due", "2026-11-25T23:59:59"],  # naive
        ["--task-id", "14", "--project-id", "0"],
        ["--task-id", "0", "--title", "X"],
        ["--task-id", "-3", "--title", "X"],
        ["--task-id", "abc", "--title", "X"],
        ["--title", "X"],
        [],
    ],
)
def test_bad_input_exits_2_with_no_request(serve, capsys, argv):
    server = serve(recurring_task())

    code, summary, err = run_cli(capsys, *argv)

    assert code == ut.EXIT_USAGE
    assert summary["ok"] is False and summary["outcome"] == "refused"
    assert server.requests == []
    assert err.startswith("ERROR: ")


def test_core_refuses_unknown_and_null_fields_without_a_request(serve):
    server = serve(recurring_task())
    for changes in ({"repeat": WEEKLY}, {"done": True}, {"reminders": []}, {"title": None}, {}):
        with pytest.raises(ut.UpdateRefused):
            ut.update_task(client(), 14, changes)
    assert server.requests == []


# ---------------------------------------------------------------------------
# Vikunja failures
# ---------------------------------------------------------------------------


def test_patch_failure_is_error_with_write_attempted(serve, capsys):
    server = serve(recurring_task(), patch_status={1: 500})

    code, summary, _ = run_cli(capsys, "--task-id", "14", "--title", "Stretch")

    assert code == ut.EXIT_UNEXPECTED
    assert summary["outcome"] == "error" and summary["write_attempted"] is True
    assert server.methods() == ["GET", "PATCH"]


def test_missing_task_is_error_without_a_write(serve, capsys):
    server = serve(recurring_task())

    code, summary, _ = run_cli(capsys, "--task-id", "999", "--title", "Stretch")

    assert code == ut.EXIT_UNEXPECTED
    assert summary["outcome"] == "error" and summary["write_attempted"] is False
    assert server.writes() == []


def test_no_write_ever_carries_a_null(serve, capsys):
    server = serve(recurring_task(), one_off_task(id=15))
    run_cli(capsys, "--task-id", "14", "--title", "A", "--description", "", "--priority", "0")
    run_cli(capsys, "--task-id", "15", "--due", "2026-12-01T09:00:00-05:00", "--project-id", "2")

    bodies = server.patch_bodies()
    assert len(bodies) == 2
    assert all(_no_nulls(body) for body in bodies)
    assert all(method in ("GET", "PATCH") for method in server.methods())
