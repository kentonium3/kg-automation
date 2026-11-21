"""Tests for the read-only schedule drift check (FR-013, mission felix-rrule-adaptation, #1111).

``python3 -m scripts.habits.schedule_loader --check-live`` reads each habit's
live task with ``VikunjaClient.get_task_v2`` and reports
``match | missing | differs | inactive | unreadable``. The HTTP-level test
drives a real ``VikunjaClient`` against a fake ``urlopen`` so "only GETs"
is proven at the wire, not at a mock's method name.
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Self

import pytest

from scripts.common.vikunja_client import (
    VikunjaAuthError,
    VikunjaClient,
    VikunjaTimeoutError,
)
from scripts.habits import schedule_loader as sl
from tests.common.vikunja_v2_factory import make_task

SCHEDULE = """\
operations: []
habits:
  - task_id: 14
    title: "Wake at 5:00 AM"
    rrule: "FREQ=DAILY;INTERVAL=1"
  - task_id: 15
    title: "Meditate"
    rrule: "FREQ=DAILY;INTERVAL=1"
  - task_id: 16
    title: "Morning shoulder PT"
    rrule: "FREQ=DAILY;INTERVAL=1"
  - task_id: 75
    title: "Strength training — Monday"
    designated_weekdays: ["Mon"]
    rrule: "FREQ=WEEKLY;BYDAY=MO"
  - task_id: 18
    title: "Get steps in today"
    rrule: "FREQ=DAILY;INTERVAL=1"
"""


def _write_schedule(tmp_path: Path, text: str = SCHEDULE) -> Path:
    path = tmp_path / "schedule.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class _FakeClient:
    """Answers ``get_task_v2`` from a dict; records every call by name."""

    def __init__(self, answers: dict[int, Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, int]] = []

    def get_task_v2(self, task_id: int, *, timeout: float | None = None) -> dict:
        self.calls.append(("get_task_v2", task_id))
        answer = self.answers[task_id]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def __getattr__(self, name: str) -> Any:  # any other method is a test failure
        raise AssertionError(f"drift check called client.{name}; it may only GET tasks")


def _answers() -> dict[int, Any]:
    return {
        # match: lowercase server parts, read_only flag, list-ordering noise.
        14: make_task(id=14, repeat={"freq": "daily", "interval": 1, "read_only": False}),
        # differs: interval 2 is not the declared daily rule.
        15: make_task(id=15, title="Meditate", repeat={"freq": "daily", "interval": 2}),
        # missing: rule stripped (the #1111 damage shape).
        16: make_task(id=16, title="Morning shoulder PT", repeat=None),
        # inactive: Done with no rule (C-008) — not drift.
        75: make_task(id=75, title="Strength training — Monday", done=True, repeat=None),
        # unreadable: the GET failed.
        18: VikunjaTimeoutError(path="/tasks/18"),
    }


def test_check_live_rows(tmp_path: Path) -> None:
    entries = sl.load_schedule(_write_schedule(tmp_path))
    client = _FakeClient(_answers())
    rows = sl.check_live(entries, client)
    by_id = {row["task_id"]: row for row in rows}
    assert {tid: row["status"] for tid, row in by_id.items()} == {
        14: "match",
        15: "differs",
        16: "missing",
        75: "inactive",
        18: "unreadable",
    }
    assert by_id[14]["schedule_rrule"] == "FREQ=DAILY;INTERVAL=1"
    assert by_id[14]["live_rrule"] == "FREQ=DAILY;INTERVAL=1"
    assert by_id[15]["live_rrule"] == "FREQ=DAILY;INTERVAL=2"
    assert by_id[16]["live_rrule"] is None
    assert by_id[18]["error"] == "VikunjaTimeoutError"
    assert by_id[18]["live_rrule"] is None
    # Schedule order preserved; exactly one GET per habit.
    assert [row["task_id"] for row in rows] == [14, 15, 16, 75, 18]
    assert client.calls == [("get_task_v2", t) for t in (14, 15, 16, 75, 18)]


def test_check_live_inactive_wins_over_differs(tmp_path: Path) -> None:
    """A done task is ``inactive`` even if it still carries a different rule."""
    entries = sl.load_schedule(_write_schedule(tmp_path))[:1]
    client = _FakeClient({14: make_task(id=14, done=True, repeat={"freq": "weekly"})})
    assert sl.check_live(entries, client)[0]["status"] == "inactive"


def test_check_live_live_rule_rendered_when_rrule_text_absent(tmp_path: Path) -> None:
    """A body without ``repeats_rrule`` (list-shaped) still reports the rule text."""
    entries = sl.load_schedule(_write_schedule(tmp_path))[:1]
    task = make_task(id=14, repeat={"freq": "daily", "interval": 1})
    task.pop("repeats_rrule")
    row = sl.check_live(entries, _FakeClient({14: task}))[0]
    assert row["status"] == "match"
    assert row["live_rrule"] == "FREQ=DAILY;INTERVAL=1"


def test_unreadable_error_never_carries_token_or_body(tmp_path: Path) -> None:
    entries = sl.load_schedule(_write_schedule(tmp_path))[:1]
    exc = VikunjaAuthError(path="/tasks/14", status=401, body='{"secret":"tok-XYZ"}')
    row = sl.check_live(entries, _FakeClient({14: exc}))[0]
    assert row["status"] == "unreadable"
    assert row["error"] == "VikunjaAuthError"
    assert "tok-XYZ" not in json.dumps(row)


def test_summary_counts_and_ok_flag() -> None:
    rows = [
        {"status": "match"},
        {"status": "inactive"},
        {"status": "inactive"},
    ]
    assert sl.summarise(rows) == {
        "ok": True,
        "match": 1,
        "inactive": 2,
        "missing": 0,
        "differs": 0,
        "unreadable": 0,
    }
    for bad in ("missing", "differs", "unreadable"):
        assert sl.summarise([{"status": "match"}, {"status": bad}])["ok"] is False


# ---------------------------------------------------------------------------
# CLI: output shape and exit codes
# ---------------------------------------------------------------------------


def _run_main(monkeypatch, capsys, tmp_path: Path, answers: dict[int, Any]) -> tuple[int, list[str]]:
    client = _FakeClient(answers)
    monkeypatch.setattr(sl, "VikunjaClient", lambda **_kw: client)
    rc = sl.main(["--check-live", "--schedule-path", str(_write_schedule(tmp_path))])
    out = capsys.readouterr().out.strip().splitlines()
    return rc, out


def test_main_exit_one_on_drift_and_summary_last(monkeypatch, capsys, tmp_path: Path) -> None:
    rc, lines = _run_main(monkeypatch, capsys, tmp_path, _answers())
    assert rc == 1
    assert len(lines) == 6  # 5 habits + summary
    rows = [json.loads(line) for line in lines[:-1]]
    assert [r["status"] for r in rows] == [
        "match", "differs", "missing", "inactive", "unreadable",
    ]
    assert json.loads(lines[-1]) == {
        "ok": False,
        "match": 1,
        "inactive": 1,
        "missing": 1,
        "differs": 1,
        "unreadable": 1,
    }


def test_main_exit_zero_when_only_match_and_inactive(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    answers = {
        tid: make_task(id=tid, repeat={"freq": "daily", "interval": 1})
        for tid in (14, 15, 16, 18)
    }
    answers[75] = make_task(id=75, done=True, repeat=None)
    rc, lines = _run_main(monkeypatch, capsys, tmp_path, answers)
    assert rc == 0
    assert json.loads(lines[-1]) == {
        "ok": True,
        "match": 4,
        "inactive": 1,
        "missing": 0,
        "differs": 0,
        "unreadable": 0,
    }


def test_main_exit_two_on_schedule_error(monkeypatch, capsys, tmp_path: Path) -> None:
    bad = _write_schedule(tmp_path, "habits:\n  - task_id: 1\n    title: X\n")
    monkeypatch.setattr(sl, "VikunjaClient", lambda **_kw: pytest.fail("no client expected"))
    rc = sl.main(["--check-live", "--schedule-path", str(bad)])
    assert rc == 2
    assert "schedule error" in capsys.readouterr().err


def test_main_exit_two_when_client_cannot_be_built(monkeypatch, capsys, tmp_path: Path) -> None:
    def _no_token(**_kw: Any) -> Any:
        raise FileNotFoundError("/secret/path/token")

    monkeypatch.setattr(sl, "VikunjaClient", _no_token)
    rc = sl.main(["--check-live", "--schedule-path", str(_write_schedule(tmp_path))])
    err = capsys.readouterr().err
    assert rc == 2
    assert "FileNotFoundError" in err
    assert "/secret/path/token" not in err


def test_main_without_check_live_only_validates(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(sl, "VikunjaClient", lambda **_kw: pytest.fail("no client expected"))
    rc = sl.main(["--schedule-path", str(_write_schedule(tmp_path))])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "habits": 5}


def test_production_schedule_canary_seven_match_three_inactive(
    monkeypatch, capsys
) -> None:
    """Quickstart canary shape: the real schedule against today's live state
    (7 daily habits carrying FREQ=DAILY;INTERVAL=1, tasks 75–77 Done with no
    rule, C-008) gives 7 ``match`` and 3 ``inactive``."""
    entries = sl.load_schedule(sl.DEFAULT_SCHEDULE_PATH)
    answers: dict[int, Any] = {}
    for entry in entries:
        if entry.designated_weekdays:
            answers[entry.task_id] = make_task(id=entry.task_id, done=True, repeat=None)
        else:
            answers[entry.task_id] = make_task(
                id=entry.task_id, repeat={"freq": "daily", "interval": 1}
            )
    client = _FakeClient(answers)
    monkeypatch.setattr(sl, "VikunjaClient", lambda **_kw: client)
    rc = sl.main(["--check-live"])
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0
    assert summary["match"] == 7
    assert summary["inactive"] == 3
    assert summary["ok"] is True


# ---------------------------------------------------------------------------
# Wire-level read-only proof: a real VikunjaClient, a fake urlopen.
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.status = 200
        self.headers: dict[str, str] = {}

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_only_get_requests_reach_the_wire(monkeypatch, capsys, tmp_path: Path) -> None:
    seen: list[tuple[str, str]] = []
    bodies = {
        14: make_task(id=14),
        15: make_task(id=15, repeat={"freq": "daily", "interval": 3}),
        16: make_task(id=16, repeat=None),
        75: make_task(id=75, done=True, repeat=None),
    }

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> _Resp:
        seen.append((req.get_method(), req.full_url))
        task_id = int(req.full_url.rstrip("/").rsplit("/", 1)[-1])
        if task_id not in bodies:
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=401,
                msg="unauthorized",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"code":11,"message":"no"}'),
            )
        return _Resp(json.dumps(bodies[task_id]).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        sl,
        "VikunjaClient",
        lambda **_kw: VikunjaClient(base_url="https://vikunja.test/api/v1", token="tok"),
    )
    rc = sl.main(["--check-live", "--schedule-path", str(_write_schedule(tmp_path))])
    lines = capsys.readouterr().out.strip().splitlines()
    assert rc == 1
    assert [json.loads(line)["status"] for line in lines[:-1]] == [
        "match", "differs", "missing", "inactive", "unreadable",
    ]
    assert seen, "expected the drift check to reach the fake wire"
    assert {method for method, _url in seen} == {"GET"}
    assert all("/api/v2/tasks/" in url for _method, url in seen)
