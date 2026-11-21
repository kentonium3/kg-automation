"""Round-trip regression tests: habits writes keep the recurrence rule (#1111).

Mission felix-rrule-adaptation-01M7TKNX, WP03 (NFR-002, SC-001, SC-004).

Each test drives a real entry point (``record_completion.record`` /
``main``, ``sweeper.run_sweep``, ``set_due_dates.main``) against a small
stateful fake of the Vikunja HTTP API, patched in at
``urllib.request.urlopen`` (the seam ``VikunjaClient`` itself calls). The
fake models the server facts the mission rests on:

- v2 ``PATCH /api/v2/tasks/{id}`` is an RFC 7396 merge patch: omitted fields
  survive; a no-op answers 304 with an empty body.
- v1 ``POST /api/v1/tasks/{id}`` is a *replacement*: a narrow body clears the
  rule (``strip_rule``). This is the defect the mission fixes, so a test that
  passes against the v1 path is not a test of anything.

Tests that must fail against the pre-fix code (``cc4f2154``) assert the exact
v2 PATCH body and that the stored rule is unchanged afterwards. The
positive controls make the fake strip the rule on a due-date PATCH and
assert the write site reports ``rule_changed``; a do-nothing change cannot
pass them.

The schedule is stubbed at ``sweeper.load_schedule`` so these tests do not
depend on the schedule YAML format (owned by ``schedule_loader``).
"""
from __future__ import annotations

import copy
import io
import json
import sys
import urllib.error
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Self

import pytest

from scripts.common import state_log
from scripts.common.et_datetime import parse_vikunja_instant
from scripts.common.vikunja_rule import parts_to_rrule_text, same_rule
from scripts.habits import record_completion as rc
from scripts.habits import set_due_dates as sdd
from scripts.habits import sweeper
from tests.common.vikunja_v2_factory import make_task, strip_rule, with_reminder

V1_BASE = "http://test/api/v1/"

# ---------------------------------------------------------------------------
# Fake Vikunja server
# ---------------------------------------------------------------------------


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    body: Any


class _Response:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _http_error(url: str, code: int, payload: Any = None) -> urllib.error.HTTPError:
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return urllib.error.HTTPError(url, code, "error", hdrs=None, fp=io.BytesIO(body))  # type: ignore[arg-type]


def _with_rule(task: dict, repeat: dict | None) -> dict:
    out = copy.deepcopy(task)
    out["repeat"] = repeat
    if repeat:
        out["repeats_rrule"] = parts_to_rrule_text(repeat)
    else:
        out.pop("repeats_rrule", None)
    return out


def _recompute_relative_reminders(task: dict) -> dict:
    out = copy.deepcopy(task)
    reminders = []
    for reminder in out.get("reminders") or []:
        relative_to = reminder.get("relative_to") or ""
        base = parse_vikunja_instant(out.get(relative_to)) if relative_to else None
        if base is not None:
            reminder = {
                **reminder,
                "reminder": (base + timedelta(seconds=reminder["relative_period"]))
                .astimezone(timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        reminders.append(reminder)
    out["reminders"] = reminders or None
    return out


@dataclass
class FakeVikunja:
    """Stateful stand-in for Vikunja v1 + v2 task endpoints."""

    tasks: dict[int, dict] = field(default_factory=dict)
    requests: list[Request] = field(default_factory=list)
    #: Server reaction to a ``done: true`` write, per task (before -> after).
    on_done: dict[int, Callable[[dict], dict]] = field(default_factory=dict)
    #: Optional hook run on the stored task after a v2 ``due_date`` PATCH.
    after_due_patch: Callable[[dict], dict] | None = None
    #: ``GET .../occurrences`` answer per task: a body dict or an HTTP status.
    #: A callable gets the stored task and computes the answer from it
    #: (stateful, like the real endpoint).
    occurrences: dict[int, dict | int | Callable[[dict], dict]] = field(
        default_factory=dict
    )
    #: Task ids whose next v2 PATCH commits and then answers HTTP 500 once
    #: (a write whose outcome the client cannot see).
    fail_after_commit: set[int] = field(default_factory=set)
    #: ``POST /tasks/occurrences/preview`` answer: a body dict or an HTTP status.
    preview: dict | int = 400

    def add(self, task: dict) -> dict:
        self.tasks[task["id"]] = copy.deepcopy(task)
        return self.tasks[task["id"]]

    def writes(self) -> list[Request]:
        return [r for r in self.requests if r.method in ("POST", "PATCH", "PUT")]

    def task_writes(self) -> list[Request]:
        """Writes to a task itself (not comments, not preview)."""
        return [
            r
            for r in self.writes()
            if not r.path.endswith("/comments") and "occurrences" not in r.path
        ]

    # -- dispatch ----------------------------------------------------------

    def __call__(self, req: Any, timeout: float | None = None) -> _Response:
        url = req.full_url
        parts = urllib.parse.urlsplit(url)
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        method = req.get_method()
        path = parts.path
        self.requests.append(
            Request(method, path, urllib.parse.parse_qs(parts.query), body)
        )
        segs = path.strip("/").split("/")  # api, v1|v2, tasks, id, ...
        if segs[:3] == ["api", "v2", "tasks"] and segs[3:] == ["occurrences", "preview"]:
            if isinstance(self.preview, int):
                raise _http_error(url, self.preview, {"code": 2002, "message": "x"})
            return _Response(self.preview)
        if len(segs) < 4 or segs[2] != "tasks":
            raise _http_error(url, 404)
        task_id = int(segs[3])
        rest = segs[4:]
        version = segs[1]
        if task_id not in self.tasks:
            raise _http_error(url, 404, {"code": 2001, "message": "not found"})
        task = self.tasks[task_id]
        if rest == ["comments"] and method == "PUT":
            return _Response({"id": 900, "comment": body.get("comment")})
        if rest == ["occurrences"] and method == "GET" and version == "v2":
            answer = self.occurrences.get(task_id, {"occurrences": []})
            if callable(answer):
                answer = answer(copy.deepcopy(task))
            if isinstance(answer, int):
                raise _http_error(url, answer, {"code": 11, "message": "forbidden"})
            return _Response(answer)
        if rest:
            raise _http_error(url, 404)
        if method == "GET":
            return _Response(copy.deepcopy(task))
        if method == "POST" and version == "v1":
            # v1 POST replaces the task: a narrow body clears the rule.
            new = strip_rule(task)
            for key, value in body.items():
                if key in new:
                    new[key] = value
            self.tasks[task_id] = new
            return _Response(copy.deepcopy(new))
        if method == "PATCH" and version == "v2":
            before = copy.deepcopy(task)
            if body.get("done") is True and not task.get("done") and task_id in self.on_done:
                new = self.on_done[task_id](before)
            else:
                new = copy.deepcopy(task)
                new.update(body)
            # Every save recomputes relative reminders from their base date
            # (d7e202228 pkg/models/tasks.go updateRelativeReminderDates);
            # absolute reminders are left alone.
            new = _recompute_relative_reminders(new)
            if "due_date" in body and self.after_due_patch is not None:
                new = self.after_due_patch(new)
            if new == before:
                raise _http_error(url, 304)
            self.tasks[task_id] = new
            if task_id in self.fail_after_commit:
                self.fail_after_commit.discard(task_id)
                raise _http_error(url, 500, {"code": 1, "message": "boom"})
            return _Response(copy.deepcopy(new))
        raise _http_error(url, 405)


@pytest.fixture
def fake_vikunja(monkeypatch) -> FakeVikunja:
    fake = FakeVikunja()
    monkeypatch.setattr("urllib.request.urlopen", fake)
    return fake


# ---------------------------------------------------------------------------
# Task builders
# ---------------------------------------------------------------------------

DAILY = {"freq": "daily", "interval": 1}


def _habit(task_id: int = 14, *, repeat: dict | None = None, **overrides: Any) -> dict:
    """A habit with a rule, ``repeats_from_current_date=True`` (unless
    overridden) and one relative reminder."""
    fields: dict[str, Any] = {
        "id": task_id,
        "identifier": f"#{task_id}",
        "index": task_id,
        "repeat": DAILY if repeat is None else repeat,
        "repeats_from_current_date": True,
        "due_date": "2026-05-21T03:59:59Z",
        **overrides,
    }
    return with_reminder(make_task(**fields), relative_period=-3600)


def _advanced(before: dict, *, repeat: dict | None = None) -> dict:
    """What the server stores after completing *before* normally: +1 day, open."""
    after = _with_rule(before, before["repeat"] if repeat is None else repeat)
    after["done"] = False
    after["due_date"] = "2026-05-22T03:59:59Z"
    return with_reminder({**after, "reminders": None}, relative_period=-3600)


def _ended_by_count(before: dict) -> dict:
    after = _with_rule(before, None)
    after["done"] = True
    after["done_at"] = "2026-05-20T12:00:00Z"
    return after


def _done_keep_rule(before: dict) -> dict:
    after = copy.deepcopy(before)
    after["done"] = True
    after["done_at"] = "2026-05-20T12:00:00Z"
    return after


RECORD_KW: dict[str, Any] = {
    "task_id": 14,
    "title": "Wake at 5:00 AM",
    "date": "2026-05-20",
    "state": "complete",
    "source": "whatsapp",
    "api_base_url": V1_BASE,
    "token": "test-token",
}


def _comments(fake: FakeVikunja) -> list[str]:
    return [r.body["comment"] for r in fake.writes() if r.path.endswith("/comments")]


def _assert_single_done_patch(fake: FakeVikunja, task_id: int = 14) -> None:
    task_writes = fake.task_writes()
    assert [(r.method, r.path) for r in task_writes] == [
        ("PATCH", f"/api/v2/tasks/{task_id}")
    ], f"expected exactly one v2 PATCH, got {[(r.method, r.path) for r in task_writes]}"
    assert task_writes[0].body == {"done": True}


# ---------------------------------------------------------------------------
# Completion (record_completion)
# ---------------------------------------------------------------------------


class TestCompletion:
    def test_advanced_keeps_rule_and_sends_only_done(
        self, fake_vikunja, mock_state_log_dir
    ):
        before = fake_vikunja.add(_habit())
        fake_vikunja.on_done[14] = _advanced

        rc.record(**RECORD_KW)

        _assert_single_done_patch(fake_vikunja)
        stored = fake_vikunja.tasks[14]
        assert same_rule(before["repeat"], stored["repeat"])
        assert stored["repeats_from_current_date"] is True
        assert stored["reminders"], "reminder must survive the completion"
        assert _comments(fake_vikunja) == ["[Felix] 2026-05-20 | complete"]
        rows = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(rows) == 1 and "note" not in rows[0]

    def test_count_two_to_one_is_advanced(self, fake_vikunja, mock_state_log_dir):
        rule = {"freq": "daily", "interval": 1, "count": 2}
        fake_vikunja.add(_habit(repeat=rule))
        fake_vikunja.on_done[14] = lambda b: _advanced(b, repeat={**rule, "count": 1})

        rc.record(**RECORD_KW)

        _assert_single_done_patch(fake_vikunja)
        assert fake_vikunja.tasks[14]["repeat"]["count"] == 1
        assert _comments(fake_vikunja) == ["[Felix] 2026-05-20 | complete"]

    def test_count_one_is_series_ended(self, fake_vikunja, mock_state_log_dir):
        fake_vikunja.add(_habit(repeat={"freq": "daily", "interval": 1, "count": 1}))
        fake_vikunja.on_done[14] = _ended_by_count

        rc.record(**RECORD_KW)

        _assert_single_done_patch(fake_vikunja)
        assert _comments(fake_vikunja) == [
            "[Felix] 2026-05-20 | complete | series_ended"
        ]
        rows = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(rows) == 1
        assert rows[0]["note"] == "series_ended"

    def test_until_passed_is_series_ended_with_rule_kept(
        self, fake_vikunja, mock_state_log_dir
    ):
        """UNTIL exhaustion established by preview before the write: the
        server leaves the task Done with the rule kept (R-010)."""
        rule = {"freq": "daily", "interval": 1, "until": "2026-05-21T03:59:59Z"}
        before = fake_vikunja.add(_habit(repeat=rule, repeats_from_current_date=False))
        fake_vikunja.preview = {"occurrences": [], "reason": "until_passed"}
        fake_vikunja.on_done[14] = _done_keep_rule

        rc.record(**RECORD_KW)

        _assert_single_done_patch(fake_vikunja)
        preview = [r for r in fake_vikunja.requests if r.path.endswith("/preview")]
        assert len(preview) == 1
        assert preview[0].body["repeats_from_current_date"] is False
        stored = fake_vikunja.tasks[14]
        assert stored["done"] is True
        assert same_rule(before["repeat"], stored["repeat"])
        assert _comments(fake_vikunja) == [
            "[Felix] 2026-05-20 | complete | series_ended"
        ]
        rows = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(rows) == 1
        assert rows[0]["note"] == "series_ended"

    @pytest.mark.parametrize(
        "repeat",
        [
            pytest.param(DAILY, id="no-count-no-until"),
            pytest.param(
                {"freq": "daily", "interval": 1, "until": "2026-12-31T23:59:59Z"},
                id="until-from-current-date-unknown",
            ),
        ],
    )
    def test_unexpected_done_exits_nonzero_after_recording(
        self, fake_vikunja, mock_state_log_dir, tmp_token_file, monkeypatch, capsys, repeat
    ):
        fake_vikunja.add(_habit(repeat=repeat))
        fake_vikunja.on_done[14] = _done_keep_rule
        stdin = io.StringIO(
            json.dumps({k: RECORD_KW[k] for k in ("task_id", "title", "date", "state", "source")})
        )
        stdin.isatty = lambda: False  # type: ignore[method-assign]
        monkeypatch.setattr(sys, "stdin", stdin)

        exit_code = rc.main(["--token-file", str(tmp_token_file), "--base-url", V1_BASE])

        assert exit_code != 0
        err = capsys.readouterr().err
        assert "unexpected" in err
        assert "repeats_rrule" in err and "done=True" in err
        _assert_single_done_patch(fake_vikunja)
        # The facts are still recorded.
        assert _comments(fake_vikunja) == ["[Felix] 2026-05-20 | complete"]
        assert len(state_log.read("habits", task_id=14, date="2026-05-20")) == 1


# ---------------------------------------------------------------------------
# Completion keeps the flag and the reminders (WP08, WP03 arbiter item 5)
# ---------------------------------------------------------------------------

_ABS_REMINDER = {"reminder": "2026-05-20T12:30:00Z", "relative_to": "", "relative_period": 0}


def _habit_with_absolute(**overrides: Any) -> dict:
    """``repeats_from_current_date=True``, a relative reminder AND an absolute one."""
    task = _habit(**overrides)
    task["reminders"] = [*task["reminders"], dict(_ABS_REMINDER)]
    return task


def _advanced_moving_absolute(before: dict) -> dict:
    """The server's advance: +1 day, relative recomputed, absolute moved as the
    engine moves it (DAILY names no time: same wall clock, one calendar day on)."""
    after = _advanced(before)
    after["reminders"] = [
        *after["reminders"],
        {**_ABS_REMINDER, "reminder": "2026-05-21T12:30:00Z"},
    ]
    return after


def _run_main(fake, monkeypatch, tmp_token_file) -> int:
    stdin = io.StringIO(
        json.dumps({k: RECORD_KW[k] for k in ("task_id", "title", "date", "state", "source")})
    )
    stdin.isatty = lambda: False  # type: ignore[method-assign]
    monkeypatch.setattr(sys, "stdin", stdin)
    return rc.main(["--token-file", str(tmp_token_file), "--base-url", V1_BASE])


class TestCompletionCompanions:
    """``record_completion`` runs the shared ``recurrence_drift`` on completion.

    Completion-aware: relative reminders are recomputed from the moved due
    date and absolute ones move exactly as the server engine moves them;
    anything else is damage, reported as ``unexpected`` with a non-zero exit
    AFTER the comment and the state-log row are written.
    """

    def test_from_completion_with_relative_and_absolute_reminders_advances(
        self, fake_vikunja, mock_state_log_dir, tmp_token_file, monkeypatch, capsys
    ):
        before = fake_vikunja.add(_habit_with_absolute())
        assert before["repeats_from_current_date"] is True
        fake_vikunja.on_done[14] = _advanced_moving_absolute

        assert _run_main(fake_vikunja, monkeypatch, tmp_token_file) == 0

        stored = fake_vikunja.tasks[14]
        assert stored["repeats_from_current_date"] is True
        assert len(stored["reminders"]) == 2
        # The relative trigger was recomputed from the new due date, not kept.
        assert stored["reminders"][0]["reminder"] != before["reminders"][0]["reminder"]
        assert capsys.readouterr().err == ""

    def test_relative_day_reminder_across_dst_is_not_damage(
        self, fake_vikunja, mock_state_log_dir, tmp_token_file, monkeypatch
    ):
        """A whole-day relative reminder on a from-completion habit whose due
        date crosses the 2027-03-14 clock change: its trigger moves by an
        elapsed day here and by a calendar day on the server; either is fine."""
        task = make_task(
            id=14, repeat=DAILY, repeats_from_current_date=True,
            due_date="2027-03-14T03:59:59Z",
        )
        fake_vikunja.add(with_reminder(task, relative_period=-86400))

        def advance(b: dict) -> dict:
            after = {**copy.deepcopy(b), "done": False, "due_date": "2027-03-15T03:59:59Z"}
            return after

        fake_vikunja.on_done[14] = advance
        assert _run_main(fake_vikunja, monkeypatch, tmp_token_file) == 0

    @pytest.mark.parametrize(
        ("corrupt", "lost"),
        [
            pytest.param(
                lambda t: {**t, "reminders": None}, "reminders", id="reminders-removed"
            ),
            pytest.param(
                lambda t: {**t, "reminders": t["reminders"][:1]},
                "reminders",
                id="absolute-reminder-dropped",
            ),
            pytest.param(
                lambda t: {
                    **t,
                    "reminders": [t["reminders"][0], dict(_ABS_REMINDER)],
                },
                "reminders",
                id="absolute-reminder-not-moved",
            ),
            pytest.param(
                lambda t: {**t, "repeats_from_current_date": False},
                "repeats_from_current_date",
                id="flag-flipped",
            ),
        ],
    )
    def test_companion_loss_is_unexpected_and_exits_nonzero_after_recording(
        self, fake_vikunja, mock_state_log_dir, tmp_token_file, monkeypatch, capsys,
        corrupt, lost,
    ):
        fake_vikunja.add(_habit_with_absolute())
        fake_vikunja.on_done[14] = lambda b: corrupt(_advanced_moving_absolute(b))

        exit_code = _run_main(fake_vikunja, monkeypatch, tmp_token_file)

        assert exit_code == 1
        err = capsys.readouterr().err
        assert "unexpected completion outcome" in err
        assert f"companion fields changed: {lost}" in err
        _assert_single_done_patch(fake_vikunja)
        # The facts are still recorded, and the series is not called ended.
        assert _comments(fake_vikunja) == ["[Felix] 2026-05-20 | complete"]
        assert len(state_log.read("habits", task_id=14, date="2026-05-20")) == 1

    def test_sentinel_relative_trigger_beside_due_date_is_unexpected(
        self, fake_vikunja, mock_state_log_dir, tmp_token_file, monkeypatch, capsys
    ):
        fake_vikunja.add(_habit_with_absolute())
        fake_vikunja.on_done[14] = _advanced_moving_absolute
        # The fake recomputes relative triggers on every save; disable that for
        # this one write so the readback shows the zero sentinel.
        original = _recompute_relative_reminders

        def broken(task: dict) -> dict:
            out = original(task)
            for reminder in out.get("reminders") or []:
                if reminder.get("relative_to"):
                    reminder["reminder"] = "0001-01-01T00:00:00Z"
            return out

        monkeypatch.setattr(sys.modules[__name__], "_recompute_relative_reminders", broken)

        assert _run_main(fake_vikunja, monkeypatch, tmp_token_file) == 1
        assert "companion fields changed: reminders" in capsys.readouterr().err
        assert len(state_log.read("habits", task_id=14, date="2026-05-20")) == 1

    def test_series_end_with_lost_reminders_is_not_series_ended(
        self, fake_vikunja, mock_state_log_dir, tmp_token_file, monkeypatch, capsys
    ):
        fake_vikunja.add(_habit_with_absolute(repeat={"freq": "daily", "interval": 1, "count": 1}))
        fake_vikunja.on_done[14] = lambda b: {**_ended_by_count(b), "reminders": None}

        assert _run_main(fake_vikunja, monkeypatch, tmp_token_file) == 1
        assert "companion fields changed: reminders" in capsys.readouterr().err
        assert _comments(fake_vikunja) == ["[Felix] 2026-05-20 | complete"]


# ---------------------------------------------------------------------------
# Sweeper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Entry:
    task_id: int
    title: str
    designated_weekdays: tuple[str, ...] = ()


WEEKLY_WED = {"freq": "weekly", "interval": 1, "by_day": ["we"]}
NOW = datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc)


def _sweep_args(
    tmp_path: Path,
    monkeypatch,
    entries: list[_Entry],
    habits: list[int],
    checkin_dates: tuple[str, ...] = ("2026-05-27",),
) -> dict:
    monkeypatch.setattr(sweeper, "load_schedule", lambda _path: list(entries))
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    for date in checkin_dates:
        (state_dir / f"morning-checkin-{date}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "date": date,
                    "delivered_at_utc": f"{date}T11:05:00Z",
                    "habits": [
                        {"vikunja_task_id": t, "title": f"habit {t}"} for t in habits
                    ],
                }
            ),
            encoding="utf-8",
        )
    token = tmp_path / "token"
    token.write_text("token-xxx\n", encoding="utf-8")
    return {
        "schedule_path": tmp_path / "schedule.yaml",
        "state_dir": state_dir,
        "history_path": tmp_path / "history.jsonl",
        "vikunja_token_path": token,
        "vikunja_base_url": "https://vikunja.test/api/v1",
        "now_utc": NOW,
    }


def _history(args: dict) -> list[dict]:
    path = args["history_path"]
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


ABSOLUTE_REMINDER = {
    "reminder": "2026-05-27T12:00:00Z",
    "relative_period": 0,
    "relative_to": "",
}


def _dayspec(task_id: int = 76, repeat: dict | None = WEEKLY_WED) -> dict:
    """A day-specific habit with ``repeats_from_current_date=True``, one
    relative reminder (1 h before due) and one absolute reminder."""
    task = make_task(
        id=task_id,
        title="Strength training — Wednesday",
        repeat=repeat,
        repeats_from_current_date=True,
        due_date="2026-05-28T03:59:59Z",
    )
    task = with_reminder(task, relative_period=-3600)
    task["reminders"].append(dict(ABSOLUTE_REMINDER))
    return task


def _assert_recurrence_preserved(before: dict, after: dict) -> None:
    """Rule, flag and reminder set survived a due-date write.

    Relative reminders: same (relative_to, relative_period), instant
    recomputed by the server from the new due date. Absolute: strict.
    """
    assert same_rule(before["repeat"], after["repeat"])
    assert after["repeats_from_current_date"] is True
    rel_before = [
        (r["relative_to"], r["relative_period"])
        for r in before["reminders"]
        if r["relative_to"]
    ]
    rel_after = [r for r in after["reminders"] if r["relative_to"]]
    assert [(r["relative_to"], r["relative_period"]) for r in rel_after] == rel_before
    due = parse_vikunja_instant(after["due_date"])
    assert due is not None
    assert parse_vikunja_instant(rel_after[0]["reminder"]) == due - timedelta(hours=1)
    assert [r for r in after["reminders"] if not r["relative_to"]] == [ABSOLUTE_REMINDER]


def _drop_reminders(task: dict) -> dict:
    return {**task, "reminders": None}


def _flip_flag(task: dict) -> dict:
    return {**task, "repeats_from_current_date": False}


def _move_absolute_reminder(task: dict) -> dict:
    reminders = [
        {**r, "reminder": "2026-05-27T13:00:00Z"} if not r["relative_to"] else r
        for r in task["reminders"]
    ]
    return {**task, "reminders": reminders}


CORRUPTIONS = [
    pytest.param(strip_rule, "repeat", id="rule-stripped"),
    pytest.param(_drop_reminders, "reminders", id="reminders-removed"),
    pytest.param(_flip_flag, "repeats_from_current_date", id="flag-flipped"),
    pytest.param(_move_absolute_reminder, "reminders", id="absolute-reminder-moved"),
]


def _weekly_occurrence(task: dict) -> dict:
    """Stateful occurrences for a weekly rule, as the real endpoint answers:
    the first occurrence strictly after the stored due date and after now."""
    due = parse_vikunja_instant(task["due_date"])
    assert due is not None
    nxt = due + timedelta(days=7)
    while nxt <= NOW:
        nxt += timedelta(days=7)
    return {"occurrences": [nxt.strftime("%Y-%m-%dT%H:%M:%SZ")]}


DAYSPEC_ENTRY = _Entry(76, "Strength training — Wednesday", ("Wed",))
DAILY_ENTRY = _Entry(14, "Wake at 5:00 AM")


class TestSweeper:
    def test_dayspecific_takes_next_date_from_rule(
        self, fake_vikunja, tmp_path, monkeypatch
    ):
        before = fake_vikunja.add(_dayspec())
        # Server zone UTC: Wed 2026-06-03 23:59:59 EDT.
        fake_vikunja.occurrences[76] = {"occurrences": ["2026-06-04T03:59:59Z"]}
        args = _sweep_args(tmp_path, monkeypatch, [DAYSPEC_ENTRY], [76])

        tick = sweeper.run_sweep(**args)

        assert tick.errors == []
        assert [r.new_due_date_et for r in tick.habits_auto_skipped] == [
            "2026-06-03T23:59:59-04:00"
        ]
        writes = fake_vikunja.task_writes()
        assert [(r.method, r.path, r.body) for r in writes] == [
            ("PATCH", "/api/v2/tasks/76", {"due_date": "2026-06-03T23:59:59-04:00"})
        ]
        _assert_recurrence_preserved(before, fake_vikunja.tasks[76])
        assert [e["task_id"] for e in _history(args)] == [76]

    def test_non_eod_occurrence_keeps_server_time(
        self, fake_vikunja, tmp_path, monkeypatch
    ):
        """An 08:00 ET occurrence is written as 08:00 ET (review cycle 1):
        the server's time of day is kept, only the offset is made explicit."""
        before = fake_vikunja.add(_dayspec())
        fake_vikunja.occurrences[76] = {"occurrences": ["2026-06-03T12:00:00Z"]}
        args = _sweep_args(tmp_path, monkeypatch, [DAYSPEC_ENTRY], [76])

        tick = sweeper.run_sweep(**args)

        assert tick.errors == []
        assert [r.new_due_date_et for r in tick.habits_auto_skipped] == [
            "2026-06-03T08:00:00-04:00"
        ]
        assert [r.body for r in fake_vikunja.task_writes()] == [
            {"due_date": "2026-06-03T08:00:00-04:00"}
        ]
        _assert_recurrence_preserved(before, fake_vikunja.tasks[76])

    def test_daily_habit_makes_one_read_and_no_write(self, fake_vikunja, tmp_path, monkeypatch):
        # WP12 (FR-026): one live v2 read confirms the habit is not paused
        # before the history append; a daily habit is still never written.
        fake_vikunja.add(_habit())
        args = _sweep_args(tmp_path, monkeypatch, [DAILY_ENTRY], [14])

        tick = sweeper.run_sweep(**args)

        assert [(r.method, r.path) for r in fake_vikunja.requests] == [
            ("GET", "/api/v2/tasks/14")
        ]
        assert tick.errors == []
        assert [r.task_id for r in tick.habits_auto_skipped] == [14]

    def test_no_rule_is_error_and_no_write(self, fake_vikunja, tmp_path, monkeypatch):
        fake_vikunja.add(_dayspec(repeat=None))
        fake_vikunja.occurrences[76] = {"occurrences": ["2026-06-04T03:59:59Z"]}
        args = _sweep_args(tmp_path, monkeypatch, [DAYSPEC_ENTRY], [76])

        tick = sweeper.run_sweep(**args)

        assert [e.error_type for e in tick.errors] == ["no_rule"]
        assert tick.exit_status != "success"
        assert fake_vikunja.task_writes() == []
        assert tick.habits_auto_skipped == []
        assert _history(args) == []

    def test_occurrences_401_is_error_and_no_write(
        self, fake_vikunja, tmp_path, monkeypatch
    ):
        fake_vikunja.add(_dayspec())
        fake_vikunja.occurrences[76] = 401
        args = _sweep_args(tmp_path, monkeypatch, [DAYSPEC_ENTRY], [76])

        tick = sweeper.run_sweep(**args)

        assert [e.error_type for e in tick.errors] == ["occurrences_unauthorized"]
        assert "tasks.occurrences" in tick.errors[0].error_message
        assert tick.exit_status != "success"
        assert fake_vikunja.task_writes() == []
        assert _history(args) == []

    @pytest.mark.parametrize(("corrupt", "field_name"), CORRUPTIONS)
    def test_positive_control_corrupted_by_due_patch(
        self, fake_vikunja, tmp_path, monkeypatch, corrupt, field_name
    ):
        fake_vikunja.add(_dayspec())
        fake_vikunja.occurrences[76] = {"occurrences": ["2026-06-04T03:59:59Z"]}
        fake_vikunja.after_due_patch = corrupt
        args = _sweep_args(tmp_path, monkeypatch, [DAYSPEC_ENTRY], [76])

        tick = sweeper.run_sweep(**args)

        assert [e.error_type for e in tick.errors] == ["rule_changed"]
        assert field_name in tick.errors[0].error_message
        assert tick.habits_auto_skipped == []
        assert _history(args) == []


class TestSweeperBacklogAndRetry:
    """Review cycle 2: a backlog advances once; a retry after a committed
    write does not advance again. The fake's occurrences are stateful."""

    def test_backlog_of_two_checkins_advances_once(
        self, fake_vikunja, tmp_path, monkeypatch
    ):
        before = fake_vikunja.add(_dayspec())
        fake_vikunja.occurrences[76] = _weekly_occurrence
        args = _sweep_args(
            tmp_path,
            monkeypatch,
            [DAYSPEC_ENTRY],
            [76],
            checkin_dates=("2026-05-27", "2026-05-29"),
        )

        tick = sweeper.run_sweep(**args)

        assert tick.errors == []
        # One write, to the next Wednesday (June 3) — not June 3 then June 10.
        assert [r.body for r in fake_vikunja.task_writes()] == [
            {"due_date": "2026-06-03T23:59:59-04:00"}
        ]
        assert [r.new_due_date_et for r in tick.habits_auto_skipped] == [
            "2026-06-03T23:59:59-04:00",
            "2026-06-03T23:59:59-04:00",
        ]
        assert sorted(e["original_checkin_date_et"] for e in _history(args)) == [
            "2026-05-27",
            "2026-05-29",
        ]
        stored = fake_vikunja.tasks[76]
        assert parse_vikunja_instant(stored["due_date"]) == parse_vikunja_instant(
            "2026-06-04T03:59:59Z"
        )
        _assert_recurrence_preserved(before, stored)

    def test_retry_after_committed_write_does_not_advance_again(
        self, fake_vikunja, tmp_path, monkeypatch
    ):
        fake_vikunja.add(_dayspec())
        fake_vikunja.occurrences[76] = _weekly_occurrence
        fake_vikunja.fail_after_commit.add(76)
        args = _sweep_args(tmp_path, monkeypatch, [DAYSPEC_ENTRY], [76])

        first = sweeper.run_sweep(**args)

        # The PATCH committed but its answer was a 500: an error, no event.
        assert [e.error_type for e in first.errors] == ["vikunja_put"]
        assert first.habits_auto_skipped == []
        assert _history(args) == []
        assert len(fake_vikunja.task_writes()) == 1

        second = sweeper.run_sweep(**args)

        # The stored due date is already the upcoming occurrence: no second
        # write (which would skip June 3), and the auto-skip is recorded.
        assert second.errors == []
        assert len(fake_vikunja.task_writes()) == 1
        assert [r.new_due_date_et for r in second.habits_auto_skipped] == [
            "2026-06-03T23:59:59-04:00"
        ]
        assert [e["task_id"] for e in _history(args)] == [76]

    def test_future_due_date_is_not_advanced(self, fake_vikunja, tmp_path, monkeypatch):
        """Already on an upcoming occurrence (e.g. completed since the
        missed check-in): record the skip, write nothing."""
        task = _dayspec()
        task["due_date"] = "2026-06-04T03:59:59Z"
        fake_vikunja.add(task)
        fake_vikunja.occurrences[76] = _weekly_occurrence
        args = _sweep_args(tmp_path, monkeypatch, [DAYSPEC_ENTRY], [76])

        tick = sweeper.run_sweep(**args)

        assert tick.errors == []
        assert fake_vikunja.task_writes() == []
        assert not [r for r in fake_vikunja.requests if r.path.endswith("/occurrences")]
        assert [r.new_due_date_et for r in tick.habits_auto_skipped] == [
            "2026-06-03T23:59:59-04:00"
        ]


# ---------------------------------------------------------------------------
# set_due_dates bulk --iso-eod-et mode
# ---------------------------------------------------------------------------

ISO = "2026-06-03T23:59:59-04:00"


def _bulk(token: Path) -> list[str]:
    return [
        "--habit-ids", "76",
        "--iso-eod-et", ISO,
        "--vikunja-token-path", str(token),
        "--vikunja-base-url", V1_BASE,
    ]


class TestBulkSetDueDates:
    def test_bulk_patch_sends_only_due_date_and_keeps_rule(
        self, fake_vikunja, tmp_token_file, capsys
    ):
        before = fake_vikunja.add(_dayspec())

        exit_code = sdd.main(_bulk(tmp_token_file))

        assert exit_code == 0
        writes = fake_vikunja.task_writes()
        assert [(r.method, r.path, r.body) for r in writes] == [
            ("PATCH", "/api/v2/tasks/76", {"due_date": ISO})
        ]
        _assert_recurrence_preserved(before, fake_vikunja.tasks[76])
        assert json.loads(capsys.readouterr().out.splitlines()[0]) == {
            "succeeded": [76],
            "failed": [],
        }

    @pytest.mark.parametrize(("corrupt", "field_name"), CORRUPTIONS)
    def test_positive_control_corrupted_by_due_patch(
        self, fake_vikunja, tmp_token_file, capsys, corrupt, field_name
    ):
        fake_vikunja.add(_dayspec())
        fake_vikunja.after_due_patch = corrupt

        exit_code = sdd.main(_bulk(tmp_token_file))

        assert exit_code == 1
        payload = json.loads(capsys.readouterr().out.splitlines()[0])
        assert payload["succeeded"] == []
        assert payload["failed"][0]["id"] == 76
        assert payload["failed"][0]["reason"].startswith("rule_changed")
        assert field_name in payload["failed"][0]["reason"]
