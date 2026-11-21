"""Rule round-trip tests for :mod:`scripts.intake.apply_reply` (WP05, #1111).

These drive a **real** :class:`scripts.common.vikunja_client.VikunjaClient`
against a stateful fake Vikunja installed over ``urllib.request.urlopen``, so
the exact wire shape (v2 merge-patch bodies, request order) is what is pinned.
Task bodies come from the WP01 v2 factory (the real ``GET /api/v2/tasks/{id}``
key set). The shared ``mock_vikunja_urlopen`` fixture serves one canned answer
per scenario and lives in ``tests/common``; the eliminate flow needs a server
that keeps state across calls, so this module carries its own.

The fake server models the fork's facts the client contract relies on
(vikunja-harness ``d7e202228``): a merge-patch ``null`` deletes the key; setting
``done`` on a task that still has a rule advances it instead of finishing it;
relative reminders recompute on **every** save in the saver's zone, whole days
as calendar days (``updateReminders`` at ``pkg/models/tasks.go:1813``,
``updateRelativeReminderDates`` at ``tasks.go:2575``, ``relativeReminderTime``
at ``task_next_occurrence.go:283``), so a project-only move across DST shifts
a "one day before" reminder by an hour.

Load-bearing invariants:

- a field change PATCHes exactly the changed keys (project move, due change);
- the readback fails loud (``ApplyError``) when the rule was stripped — the
  positive control that the check can fail;
- ``q:eliminate`` on a recurring task ends the series in two calls that never
  share a body, and a partial end is reported ``failed`` with its state;
- ``_is_recurring`` reads the ``repeat`` shape (FR-009).
"""
from __future__ import annotations

import copy
import io
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Self
from zoneinfo import ZoneInfo

import pytest

from scripts.common import vikunja_refs
from scripts.common.et_datetime import parse_vikunja_instant
from scripts.common.vikunja_client import VikunjaClient
from scripts.intake import apply_reply as ar
from tests.common.vikunja_v2_factory import make_task, strip_rule, with_reminder

BASE = "https://vikunja.test"
SAVER_ZONE = ZoneInfo("America/New_York")
_DAY = 24 * 60 * 60
INBOX_ID = 1
PERSONAL_ID = 20
MERGE_PATCH = "application/merge-patch+json"

_LABEL_ID = {
    entry["name"]: entry["selector"]["value"]
    for entry in vikunja_refs.declared_labels()
    if entry["selector"]["value"] is not None
}
_ID_LABEL = {v: k for k, v in _LABEL_ID.items()}

_V1_TASK = re.compile(r"^/api/v1/tasks/(\d+)$")
_V2_TASK = re.compile(r"^/api/v2/tasks/(\d+)$")
_V1_LABEL_ADD = re.compile(r"^/api/v1/tasks/(\d+)/labels$")
_V1_LABEL_DEL = re.compile(r"^/api/v1/tasks/(\d+)/labels/(\d+)$")


def _relative_reminder_time(base: datetime, period: int) -> datetime:
    """Mirror of the fork's ``relativeReminderTime`` in :data:`SAVER_ZONE`.

    Whole days move the local wall clock by calendar days (a gap moving
    forward, an overlap taking the earlier instant: zoneinfo ``fold=0``); the
    remainder, and any period under a day, is elapsed time.
    """
    days = abs(period) // _DAY * (1 if period >= 0 else -1)
    rest = period - days * _DAY
    if days == 0:
        return base + timedelta(seconds=period)
    wall = base.astimezone(SAVER_ZONE).replace(tzinfo=None) + timedelta(days=days)
    return wall.replace(tzinfo=SAVER_ZONE).astimezone(timezone.utc) + timedelta(
        seconds=rest
    )


def _utc_z(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _flip_flag(task: dict[str, Any]) -> None:
    task["repeats_from_current_date"] = not task.get("repeats_from_current_date")


def _drop_reminders(task: dict[str, Any]) -> None:
    task["reminders"] = None


def _labels(*titles: str) -> list[dict[str, Any]]:
    return [{"id": _LABEL_ID[t], "title": t} for t in titles]


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._buf = io.BytesIO(body)

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self._buf.close()


class FakeVikunjaServer:
    """Stateful fake of the fork's v1 + v2 task surface.

    ``patch_fail`` maps a 1-based PATCH ordinal to an HTTP status answered
    *without* applying that PATCH. ``strip_on_patch`` makes every applied PATCH
    also drop the rule (the v1 narrow-write damage this mission fixes);
    ``damage`` is any other mutation applied after each PATCH (a negative
    control: flip the from-current flag, drop the reminders).
    """

    def __init__(
        self,
        task: dict[str, Any],
        *,
        patch_fail: dict[int, int] | None = None,
        strip_on_patch: bool = False,
        damage: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.tasks: dict[int, dict[str, Any]] = {task["id"]: copy.deepcopy(task)}
        self.patch_fail = dict(patch_fail or {})
        self.strip_on_patch = strip_on_patch
        self.damage = damage
        self.requests: list[tuple[str, str, Any]] = []  # (method, path, body)
        self._patches = 0

    # --- helpers for assertions ------------------------------------------
    def v2_sequence(self) -> list[tuple[str, Any]]:
        return [
            (method, body)
            for method, path, body in self.requests
            if path.startswith("/api/v2/")
        ]

    def patch_bodies(self) -> list[dict[str, Any]]:
        return [body for method, _p, body in self.requests if method == "PATCH"]

    # --- server semantics ---------------------------------------------------
    def _apply_patch(self, task: dict[str, Any], body: dict[str, Any]) -> None:
        for key, value in body.items():
            if value is None:
                task[key] = None  # merge-patch null deletes
                if key == "repeat":
                    task.pop("repeats_rrule", None)
            else:
                task[key] = value
        if task.get("done") is True and task.get("repeat"):
            # The fork advances a repeating task on done instead of finishing it.
            due = parse_vikunja_instant(task["due_date"])
            assert due is not None
            task["due_date"] = (due + timedelta(days=1)).astimezone(
                timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            task["done"] = False
        # Every save recomputes every relative reminder (updateReminders).
        for reminder in task.get("reminders") or []:
            anchor = reminder.get("relative_to")
            if anchor:
                base = parse_vikunja_instant(task.get(anchor))
                if base is not None:
                    reminder["reminder"] = _utc_z(
                        _relative_reminder_time(base, reminder["relative_period"])
                    )
        if self.strip_on_patch:
            stripped = strip_rule(task)
            task.clear()
            task.update(stripped)
        if self.damage is not None:
            self.damage(task)

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _Resp:
        method = req.get_method()
        path = req.full_url[len(BASE):].split("?", 1)[0]
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        self.requests.append((method, path, body))

        if method == "GET" and (m := _V2_TASK.match(path)):
            return self._ok(self.tasks[int(m.group(1))])
        if method == "GET" and (m := _V1_TASK.match(path)):
            v1 = copy.deepcopy(self.tasks[int(m.group(1))])
            v1.pop("repeats_rrule", None)  # v1 carries repeat, not the text
            return self._ok(v1)
        if method == "PATCH" and (m := _V2_TASK.match(path)):
            assert req.get_header("Content-type") == MERGE_PATCH
            self._patches += 1
            status = self.patch_fail.get(self._patches)
            if status is not None:
                raise urllib.error.HTTPError(
                    req.full_url, status, "error", None,  # type: ignore[arg-type]
                    io.BytesIO(b'{"code": 0, "message": "simulated"}'),
                )
            task = self.tasks[int(m.group(1))]
            self._apply_patch(task, body)
            return self._ok(task)
        if method == "PUT" and (m := _V1_LABEL_ADD.match(path)):
            labels = self.tasks[int(m.group(1))].setdefault("labels", [])
            lid = body["label_id"]
            if not any(label["id"] == lid for label in labels):
                labels.append({"id": lid, "title": _ID_LABEL[lid]})
            return self._ok({"label_id": lid})
        if method == "DELETE" and (m := _V1_LABEL_DEL.match(path)):
            tid, lid = int(m.group(1)), int(m.group(2))
            task = self.tasks[tid]
            task["labels"] = [x for x in task.get("labels") or [] if x["id"] != lid]
            return self._ok({})
        pytest.fail(f"unexpected request {method} {path}")

    @staticmethod
    def _ok(payload: Any) -> _Resp:
        return _Resp(json.dumps(payload).encode("utf-8"))


@pytest.fixture
def serve(monkeypatch):
    def install(task: dict[str, Any], **kwargs: Any) -> FakeVikunjaServer:
        server = FakeVikunjaServer(task, **kwargs)
        monkeypatch.setattr(urllib.request, "urlopen", server)
        return server

    return install


def _client() -> VikunjaClient:
    return VikunjaClient(base_url=f"{BASE}/api/v1", token="test-token-not-real")


def _apply(text: str, task_id: int) -> ar.ApplyResult:
    from scripts.intake.shorthand import parse_reply

    return ar.apply_line(
        _client(), parse_reply(text)[0], task_id, inbox_id=INBOX_ID, dry_run=False
    )


# ---------------------------------------------------------------------------
# Field writes: exact PATCH bodies + rule-checked readback
# ---------------------------------------------------------------------------


def test_project_move_of_recurring_task_patches_only_project_id(serve):
    task = make_task(id=501, project_id=INBOX_ID, labels=_labels("q:do"))
    server = serve(task)

    result = _apply("1 personal", 501)

    assert result.status == "applied", result.notes
    assert server.patch_bodies() == [{"project_id": PERSONAL_ID}]
    stored = server.tasks[501]
    assert stored["project_id"] == PERSONAL_ID
    assert stored["repeat"] == {"freq": "daily", "interval": 1}


def test_due_change_patches_only_due_date_and_tolerates_relative_reminder(serve):
    task = with_reminder(
        make_task(id=502, project_id=PERSONAL_ID, labels=_labels("q:do"))
    )
    server = serve(task)

    result = _apply("1 do due:2026-11-25", 502)

    assert result.status == "applied", result.notes
    assert server.patch_bodies() == [{"due_date": "2026-11-25T23:59:59-05:00"}]
    # The relative reminder moved with the due date, and that is not damage.
    assert server.tasks[502]["reminders"][0]["reminder"] == "2026-11-26T03:59:59Z"


def test_readback_with_stripped_rule_raises_apply_error(serve):
    # Positive control: the readback check must be able to fail.
    task = make_task(id=503, project_id=INBOX_ID)
    serve(task, strip_on_patch=True)

    with pytest.raises(ar.ApplyError, match="'repeat' changed"):
        ar._patch_task_fields(_client(), task, {"project_id": PERSONAL_ID})


def test_stripped_rule_makes_the_line_failed(serve):
    task = make_task(id=504, project_id=INBOX_ID, labels=_labels("q:do"))
    serve(task, strip_on_patch=True)

    result = _apply("1 personal", 504)

    assert result.status == "failed"
    assert any("ApplyError" in note for note in result.notes)


# ---------------------------------------------------------------------------
# From-current flag + reminders on every intake write path (review cycle 1)
# ---------------------------------------------------------------------------

#: Sun 2027-03-14 20:00 EDT, the evening of the spring-forward change. "One day
#: before" is Sat 20:00 EST = 01:00Z on the server, an hour after the elapsed
#: 00:00Z the reminder was stored with: the review-cycle-1 reproduction.
_DST_DUE = "2027-03-15T00:00:00Z"

#: (reply line, starting project, expected PATCH body) for each intake write.
_WRITE_PATHS = {
    "move": ("1 personal", INBOX_ID, {"project_id": PERSONAL_ID}),
    "due": ("1 do due:2027-03-20", PERSONAL_ID, {"due_date": "2027-03-20T23:59:59-04:00"}),
}


def _flagged_task(task_id: int, project_id: int) -> dict[str, Any]:
    """A from-current recurring task with a whole-day relative reminder."""
    return with_reminder(
        make_task(
            id=task_id,
            project_id=project_id,
            labels=_labels("q:do"),
            due_date=_DST_DUE,
            repeats_from_current_date=True,
        ),
        relative_period=-_DAY,
    )


def test_project_only_move_across_dst_keeps_the_relative_reminder(serve):
    # Regression (review cycle 1): the server recomputes the relative reminder
    # on a move that never touched due_date; that is not damage.
    task = _flagged_task(511, INBOX_ID)
    assert task["reminders"][0]["reminder"] == "2027-03-14T00:00:00Z"
    server = serve(task)

    result = _apply("1 personal", 511)

    assert result.status == "applied", result.notes
    assert server.patch_bodies() == [{"project_id": PERSONAL_ID}]
    assert server.tasks[511]["reminders"][0]["reminder"] == "2027-03-14T01:00:00Z"


@pytest.mark.parametrize("path", sorted(_WRITE_PATHS))
def test_write_keeps_from_current_flag_and_reminder(serve, path):
    line, project_id, body = _WRITE_PATHS[path]
    server = serve(_flagged_task(512, project_id))

    result = _apply(line, 512)

    assert result.status == "applied", result.notes
    assert server.patch_bodies() == [body]
    stored = server.tasks[512]
    assert stored["repeats_from_current_date"] is True
    assert [r["relative_period"] for r in stored["reminders"]] == [-_DAY]


@pytest.mark.parametrize("path", sorted(_WRITE_PATHS))
@pytest.mark.parametrize(
    ("damage", "field"),
    [(_flip_flag, "repeats_from_current_date"), (_drop_reminders, "reminders")],
)
def test_write_that_damages_flag_or_reminders_fails(serve, path, damage, field):
    line, project_id, body = _WRITE_PATHS[path]
    task = _flagged_task(513, project_id)
    serve(task, damage=damage)

    with pytest.raises(ar.ApplyError, match=field):
        ar._patch_task_fields(_client(), task, body)

    serve(task, damage=damage)  # fresh server: the whole line fails too
    result = _apply(line, 513)
    assert result.status == "failed"
    assert any("ApplyError" in note for note in result.notes)


def test_absolute_reminder_shift_still_fails(serve):
    # Absolute reminders stay strict: only relative ones may recompute.
    task = make_task(
        id=514,
        project_id=INBOX_ID,
        reminders=[
            {"reminder": "2027-03-14T00:00:00Z", "relative_period": 0, "relative_to": ""}
        ],
    )

    def shift(stored: dict[str, Any]) -> None:
        stored["reminders"][0]["reminder"] = "2027-03-14T01:00:00Z"

    serve(task, damage=shift)

    with pytest.raises(ar.ApplyError, match="'reminders' changed"):
        ar._patch_task_fields(_client(), task, {"project_id": PERSONAL_ID})


# ---------------------------------------------------------------------------
# Eliminate (FR-008): end the series on a recurring task
# ---------------------------------------------------------------------------


def test_eliminate_recurring_task_ends_series_in_two_separate_writes(serve):
    task = make_task(id=505, project_id=INBOX_ID, labels=_labels("q:do"))
    server = serve(task)

    result = _apply("1 elim", 505)

    assert result.status == "applied", result.notes
    assert server.v2_sequence() == [
        ("GET", None),
        ("PATCH", {"repeat": None}),
        ("GET", None),
        ("PATCH", {"done": True}),
        ("GET", None),
    ]
    for body in server.patch_bodies():
        assert not ({"repeat", "done"} <= set(body))
    stored = server.tasks[505]
    assert stored["done"] is True
    assert stored["repeat"] is None
    assert {x["title"] for x in stored["labels"]} == {"q:eliminate"}
    assert result.applied.get("series_ended") is True
    assert any("recurring series ended" in note for note in result.notes)


def test_eliminate_recurring_task_labels_precede_end_series(serve):
    task = make_task(id=506, project_id=INBOX_ID, labels=_labels("q:do"))
    server = serve(task)

    _apply("1 elim", 506)

    methods = [method for method, _p, _b in server.requests]
    first_patch = methods.index("PATCH")
    assert "DELETE" in methods[:first_patch]
    assert "PUT" in methods[:first_patch]


def test_eliminate_one_off_task_patches_done(serve):
    task = make_task(id=507, project_id=INBOX_ID, repeat=None)
    server = serve(task)

    result = _apply("1 elim", 507)

    assert result.status == "applied", result.notes
    assert server.patch_bodies() == [{"done": True}]
    assert server.tasks[507]["done"] is True
    assert "series_ended" not in result.applied


def test_eliminate_partial_end_is_failed_with_state(serve):
    # Step 1 (clear rule) lands; step 2 (done) answers 500 and did not apply.
    task = make_task(id=508, project_id=INBOX_ID)
    server = serve(task, patch_fail={2: 500})

    result = _apply("1 elim", 508)

    assert result.status == "failed"
    assert any("rule_cleared_not_done" in note for note in result.notes)
    assert server.tasks[508]["repeat"] is None
    assert server.tasks[508]["done"] is False


# ---------------------------------------------------------------------------
# _is_recurring (FR-009)
# ---------------------------------------------------------------------------


def test_is_recurring_reads_the_repeat_shape():
    assert ar._is_recurring(make_task()) is True
    assert ar._is_recurring(make_task(repeat=None)) is False
    assert ar._is_recurring(make_task(repeat={})) is False
    # The dead shape no longer counts.
    assert ar._is_recurring({"repeat_after": 86400}) is False


def test_habit_note_fires_on_recurring_task(serve):
    task = make_task(id=509, project_id=PERSONAL_ID, labels=_labels("q:do"))
    serve(task)

    result = _apply("1 do habit", 509)

    assert result.status == "applied", result.notes
    assert any("already recurring" in note for note in result.notes)


def test_habit_note_absent_on_one_off_task(serve):
    task = make_task(id=510, project_id=PERSONAL_ID, labels=_labels("q:do"), repeat=None)
    serve(task)

    result = _apply("1 do habit", 510)

    assert not any("already recurring" in note for note in result.notes)
