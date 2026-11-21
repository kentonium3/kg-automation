"""Tests for ``scripts.vikunja.preview_rule`` (WP09 T041/T045, #1111).

The helper drives the real ``VikunjaClient.preview_occurrences`` call path;
only ``urllib.request.urlopen`` is faked, and every request is recorded so the
tests can prove the helper is read-only (one POST to the preview endpoint).
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Self
from zoneinfo import ZoneInfo

import pytest

from scripts.common.vikunja_client import VikunjaClient
from scripts.common.vikunja_rule import parts_to_rrule_text, rrule_text_to_parts
from scripts.vikunja import create_task, preview_rule

ET = ZoneInfo("America/New_York")

V2_PREVIEW = "https://vikunja.test/api/v2/tasks/occurrences/preview"
TOKEN = "secret-token-preview-do-not-leak"


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._buf = io.BytesIO(body)

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self._buf.close()


Calls = list[tuple[str, str, Any]]


@pytest.fixture
def server(monkeypatch) -> Callable[[int, Any], Calls]:
    """Answer every request with one ``(status, body)``; record the requests."""

    def install(status: int, body: Any) -> Calls:
        calls: Calls = []

        def fake(req: urllib.request.Request, timeout: float | None = None) -> _Resp:
            data = json.loads(req.data.decode("utf-8")) if req.data else None
            calls.append((req.get_method(), req.full_url, data))
            encoded = json.dumps(body).encode("utf-8")
            if status >= 300:
                raise urllib.error.HTTPError(
                    req.full_url, status, "error", None, io.BytesIO(encoded)  # type: ignore[arg-type]
                )
            return _Resp(encoded)

        monkeypatch.setattr(urllib.request, "urlopen", fake)
        return calls

    return install


def _client() -> VikunjaClient:
    return VikunjaClient(base_url="https://vikunja.test/api/v1", token=TOKEN)


def _run(capsys, *argv: str) -> tuple[int, list[str], str]:
    code = preview_rule.main(list(argv), client=_client())
    out, err = capsys.readouterr()
    return code, out.strip().splitlines(), err


def _summary(lines: list[str]) -> dict[str, Any]:
    return json.loads(lines[-1])


def _answer(
    due: str | None,
    later: list[str],
    *,
    reason: str | None = None,
    source: str = "generated",
) -> dict[str, Any]:
    """A production-shaped answer (vikunja-harness d7e202228, previewAnswer).

    ``due_date`` is the anchor; ``occurrences`` are only the dates after it.
    """
    body: dict[str, Any] = {
        "occurrences": later,
        "timezone": "America/New_York",
        "evaluated_at": "2026-11-20T18:00:00Z",
    }
    if due is not None:
        body["due_date"] = due
        body["due_date_source"] = source
    if reason is not None:
        body["reason"] = reason
    return body


ANCHOR = "2026-11-23T12:30:00Z"
LATER = ["2026-11-30T12:30:00Z", "2026-12-07T12:30:00Z", "2026-12-14T12:30:00Z"]
THREE = _answer(ANCHOR, LATER)


def test_happy_path_shows_anchor_first_then_three_later_dates(server, capsys) -> None:
    calls = server(200, THREE)
    code, lines, err = _run(
        capsys, "--rrule", "FREQ=WEEKLY;BYDAY=MO", "--initial-due-time", "07:30"
    )
    assert code == 0, err
    info = [line for line in lines if line.startswith("INFO: ")]
    assert info[1:] == [
        "INFO: first: Mon 2026-11-23 07:30 ET",
        "INFO: then: Mon 2026-11-30 07:30 ET",
        "INFO: then: Mon 2026-12-07 07:30 ET",
        "INFO: then: Mon 2026-12-14 07:30 ET",
        f"INFO: create with: --rrule FREQ=WEEKLY;BYDAY=MO --due {ANCHOR}",
    ]
    summary = _summary(lines)
    assert summary["ok"] is True
    assert summary["due_date"] == ANCHOR
    assert summary["due_date_et"] == "Mon 2026-11-23 07:30 ET"
    assert summary["due_date_source"] == "generated"
    assert summary["occurrences"] == LATER
    assert summary["dates_et"] == [
        "Mon 2026-11-23 07:30 ET",
        "Mon 2026-11-30 07:30 ET",
        "Mon 2026-12-07 07:30 ET",
        "Mon 2026-12-14 07:30 ET",
    ]
    assert summary["reason"] is None and summary["reason_text"] is None
    assert summary["create_args"] == ["--rrule", "FREQ=WEEKLY;BYDAY=MO", "--due", ANCHOR]
    assert calls[0][2] == {
        "repeats_rrule": "FREQ=WEEKLY;BYDAY=MO",
        "initial_due_time": "07:30",
        "timezone": "America/New_York",
        "repeats_from_current_date": False,
        "count": 3,
    }


def test_only_call_is_the_preview_post(server, capsys) -> None:
    calls = server(200, _answer(ANCHOR, LATER, source="explicit"))
    code, _, _ = _run(
        capsys,
        "--rrule",
        "FREQ=DAILY;INTERVAL=10",
        "--due",
        ANCHOR,
        "--from-completion",
    )
    assert code == 0
    assert [(method, url) for method, url, _ in calls] == [("POST", V2_PREVIEW)]
    body = calls[0][2]
    assert body["due_date"] == ANCHOR
    assert body["repeats_from_current_date"] is True
    assert "initial_due_time" not in body


def test_est_dates_render_in_standard_time(server, capsys) -> None:
    server(200, _answer("2027-01-04T12:30:00Z", ["2027-01-05T12:30:00Z"]))
    _, lines, _ = _run(capsys, "--rrule", "FREQ=DAILY", "--initial-due-time", "07:30", "--count", "1")
    assert _summary(lines)["dates_et"] == ["Mon 2027-01-04 07:30 ET", "Tue 2027-01-05 07:30 ET"]


def test_count_1_is_the_anchor_alone(server, capsys) -> None:
    """COUNT=1: the server returns the anchor and no later date."""
    server(200, _answer(ANCHOR, [], reason="count_exhausted"))
    code, lines, _ = _run(capsys, "--rrule", "FREQ=WEEKLY;COUNT=1", "--initial-due-time", "07:30")
    assert code == 0
    assert "INFO: first: Mon 2026-11-23 07:30 ET" in lines
    assert "INFO: series ends after 1 occurrence (COUNT)" in lines
    assert not any("no due date" in line for line in lines)
    summary = _summary(lines)
    assert summary["dates_et"] == ["Mon 2026-11-23 07:30 ET"]
    assert summary["occurrences"] == []
    assert summary["reason_text"] == "series ends after 1 occurrence (COUNT)"


def test_count_2_is_the_anchor_and_one_later_date(server, capsys) -> None:
    server(200, _answer(ANCHOR, LATER[:1], reason="count_exhausted"))
    code, lines, _ = _run(capsys, "--rrule", "FREQ=WEEKLY;COUNT=2", "--initial-due-time", "07:30")
    assert code == 0
    summary = _summary(lines)
    assert summary["dates_et"] == ["Mon 2026-11-23 07:30 ET", "Mon 2026-11-30 07:30 ET"]
    assert summary["reason_text"] == "series ends after 2 occurrences (COUNT)"


def test_until_counts_the_anchor(server, capsys) -> None:
    server(200, _answer(ANCHOR, LATER[:2], reason="until_passed", source="explicit"))
    _, lines, _ = _run(capsys, "--rrule", "FREQ=WEEKLY;UNTIL=20261210T000000Z", "--due", ANCHOR)
    assert _summary(lines)["reason_text"] == "series ends after 3 occurrences (UNTIL)"


def test_no_selectable_due_date_is_reported(server, capsys) -> None:
    server(200, _answer(None, [], reason="until_passed"))
    code, lines, _ = _run(
        capsys, "--rrule", "FREQ=DAILY;UNTIL=20200101T000000Z", "--initial-due-time", "07:30"
    )
    assert code == 0
    assert "INFO: no due date" in lines
    summary = _summary(lines)
    assert summary["dates_et"] == [] and summary["due_date"] is None
    assert summary["reason_text"] == "no due date: the rule gives no date (server reason: until_passed)"


@pytest.mark.parametrize(
    "argv",
    [
        ["--rrule", "FREQ=WEEKLY;BOGUS=1", "--initial-due-time", "07:30"],
        ["--rrule", "INTERVAL=2", "--initial-due-time", "07:30"],
        ["--rrule", "FREQ=DAILY;UNTIL=20270301", "--initial-due-time", "07:30"],
        ["--rrule", "FREQ=DAILY", "--initial-due-time", "7:30am"],
        ["--rrule", "FREQ=DAILY", "--due", "next monday"],
        ["--rrule", "FREQ=DAILY", "--due", ANCHOR, "--count", "0"],
        ["--rrule", "FREQ=DAILY", "--due", ANCHOR, "--count", "101"],
    ],
)
def test_invalid_input_rejected_locally_without_a_call(server, capsys, argv) -> None:
    calls = server(200, THREE)
    code, lines, err = _run(capsys, *argv)
    assert code == 2
    assert calls == []
    assert err.startswith("ERROR: ")
    summary = _summary(lines)
    assert summary["ok"] is False and summary["error"] == "invalid_input"
    assert summary["rrule"] == argv[1]


def test_count_100_is_accepted(server, capsys) -> None:
    calls = server(200, THREE)
    code, _, _ = _run(capsys, "--rrule", "FREQ=DAILY", "--due", ANCHOR, "--count", "100")
    assert code == 0
    assert calls[0][2]["count"] == 100


@pytest.mark.parametrize(
    "argv",
    [
        ["--rrule", "FREQ=DAILY"],  # no anchor
        ["--rrule", "FREQ=DAILY", "--due", ANCHOR, "--initial-due-time", "07:30"],
        ["--rrule", "FREQ=DAILY", "--due", ANCHOR, "--count", "three"],
        ["--initial-due-time", "07:30"],  # no rule
        ["--rrule", "FREQ=DAILY", "--due", ANCHOR, "--bogus"],
    ],
)
def test_argument_errors_go_through_the_json_summary(server, capsys, argv) -> None:
    calls = server(200, THREE)
    code = preview_rule.main(argv, client=_client())
    out, err = capsys.readouterr()
    assert code == 2
    assert calls == []
    assert err.startswith("ERROR: ")
    summary = json.loads(out.strip().splitlines()[-1])
    assert summary["ok"] is False and summary["error"] == "invalid_input"


def test_server_2002_invalid_rule_exits_2(server, capsys) -> None:
    server(400, {"code": 2002, "message": "invalid rule"})
    code, lines, err = _run(
        capsys, "--rrule", "FREQ=MONTHLY;BYMONTHDAY=31;BYSETPOS=9", "--initial-due-time", "07:30"
    )
    assert code == 2
    assert "2002" in err
    assert _summary(lines)["error"] == "invalid_rule"


def test_server_2003_bad_timezone_exits_2(server, capsys) -> None:
    server(400, {"code": 2003, "message": "invalid time zone"})
    code, lines, _ = _run(capsys, "--rrule", "FREQ=DAILY", "--initial-due-time", "07:30")
    assert code == 2
    assert _summary(lines)["error"] == "invalid_timezone"


def test_401_names_missing_permission_and_exits_2(server, capsys) -> None:
    server(401, {"code": 11, "message": "missing permission"})
    code, lines, err = _run(capsys, "--rrule", "FREQ=DAILY", "--initial-due-time", "07:30")
    assert code == 2
    assert "tasks.occurrences_preview" in err
    summary = _summary(lines)
    assert summary["error"] == "missing_permission"
    assert "tasks.occurrences_preview" in summary["message"]
    assert TOKEN not in err and TOKEN not in "\n".join(lines)


def test_other_server_error_exits_3(server, capsys) -> None:
    server(500, {"message": "boom"})
    code, lines, _ = _run(capsys, "--rrule", "FREQ=DAILY", "--initial-due-time", "07:30")
    assert code == 3
    assert _summary(lines)["error"] == "vikunja_error"


def _with(**changes: Any) -> dict[str, Any]:
    body = dict(THREE)
    for key, value in changes.items():
        if value is _DROP:
            body.pop(key, None)
        else:
            body[key] = value
    return body


_DROP = object()


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="empty-object"),
        pytest.param(_with(occurrences=_DROP), id="occurrences-missing"),
        pytest.param(_with(occurrences="2026-11-30T12:30:00Z"), id="occurrences-not-list"),
        pytest.param(_with(occurrences=[1700000000]), id="occurrence-not-string"),
        pytest.param(_with(occurrences=["next week"]), id="occurrence-bad-timestamp"),
        pytest.param(_with(occurrences=["2026-11-30T12:30:00"]), id="occurrence-naive"),
        pytest.param(_with(due_date=20261123), id="due-not-string"),
        pytest.param(_with(due_date="2026-13-45T00:00:00Z"), id="due-bad-timestamp"),
        pytest.param(_with(due_date=_DROP, due_date_source=_DROP), id="later-dates-without-anchor"),
        pytest.param(_with(due_date_source="guessed"), id="bad-due-source"),
        pytest.param(_with(due_date_source=[]), id="due-source-list"),
        pytest.param(_with(due_date_source={}), id="due-source-dict"),
        pytest.param(_with(due_date_source=["explicit"]), id="due-source-list-of-valid"),
        pytest.param(_with(due_date_source=1), id="due-source-int"),
        pytest.param(_with(due_date_source=_DROP), id="due-without-source"),
        pytest.param(
            _with(due_date=_DROP, due_date_source=_DROP, occurrences=[]),
            id="no-anchor-no-dates-no-reason",
        ),
        pytest.param(
            _with(due_date=_DROP, due_date_source=_DROP, occurrences=[], reason=""),
            id="no-anchor-empty-reason",
        ),
        pytest.param(
            _with(due_date=None, due_date_source=None, occurrences=[]),
            id="no-anchor-explicit-nulls",
        ),
        pytest.param(_with(reason=5), id="reason-not-string"),
        pytest.param(_with(timezone=_DROP), id="timezone-missing"),
        pytest.param(_with(timezone="UTC"), id="timezone-different"),
        pytest.param(_with(evaluated_at=_DROP), id="evaluated-at-missing"),
        pytest.param(_with(evaluated_at="yesterday"), id="evaluated-at-bad"),
        pytest.param(_with(occurrences=list(reversed(LATER))), id="occurrences-not-ascending"),
        pytest.param(_with(occurrences=[ANCHOR]), id="occurrence-not-after-anchor"),
    ],
)
def test_malformed_200_answer_exits_3(server, capsys, body) -> None:
    server(200, body)
    code, lines, err = _run(capsys, "--rrule", "FREQ=DAILY", "--initial-due-time", "07:30")
    assert code == 3
    assert err.startswith("ERROR: ")
    summary = _summary(lines)
    assert summary["ok"] is False and summary["error"] == "malformed_response"
    assert not any(line.startswith("INFO: first") for line in lines)


def test_non_object_200_answer_exits_3(server, capsys) -> None:
    """The client itself refuses a non-object body (``_expect_dict``)."""
    server(200, [])
    code, lines, _ = _run(capsys, "--rrule", "FREQ=DAILY", "--initial-due-time", "07:30")
    assert code == 3
    summary = _summary(lines)
    assert summary["ok"] is False and summary["error"] == "vikunja_error"


# ---------------------------------------------------------------------------
# Delayed confirmation: preview at 07:29, Kent confirms after 07:30 (cycle 3)
# ---------------------------------------------------------------------------


class _ClockedServer:
    """A fake v2 server with a settable clock, for preview -> create.

    ``initial_due_time`` is resolved the way the server does it
    (selectInitialDue): the first 07:30 ET strictly after *now*. An explicit
    ``due_date`` is stored as sent, to the second (pkg/models/tasks.go create).
    """

    def __init__(self, now: str) -> None:
        self.now = datetime.fromisoformat(now.replace("Z", "+00:00"))
        self.task: dict[str, Any] | None = None
        self.calls: list[tuple[str, str, Any]] = []
        self.store_due_override: str | None = None

    def _next_0730(self) -> datetime:
        local = self.now.astimezone(ET)
        candidate = local.replace(hour=7, minute=30, second=0, microsecond=0)
        if candidate <= local:
            candidate += timedelta(days=1)
        return candidate.astimezone(UTC)

    @staticmethod
    def _z(value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    def urlopen(self, req: urllib.request.Request, timeout: float | None = None) -> _Resp:
        method, url = req.get_method(), req.full_url
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        self.calls.append((method, url, body))
        if method == "POST" and url == V2_PREVIEW:
            if "initial_due_time" in body:
                anchor, source = self._next_0730(), "generated"
            else:
                anchor = datetime.fromisoformat(body["due_date"].replace("Z", "+00:00"))
                source = "explicit"
            later = [self._z(anchor + timedelta(days=i)) for i in range(1, body["count"] + 1)]
            answer = {
                "due_date": self._z(anchor),
                "due_date_source": source,
                "occurrences": later,
                "timezone": body["timezone"],
                "evaluated_at": self._z(self.now),
            }
            return _Resp(json.dumps(answer).encode())
        if method == "POST" and url == "https://vikunja.test/api/v2/projects/1/tasks":
            if "initial_due_time" in body:
                due = self._z(self._next_0730())
            else:
                due = body["due_date"]
            if self.store_due_override is not None:
                due = self.store_due_override
            parts = rrule_text_to_parts(body["repeats_rrule"])
            self.task = {
                "id": 98,
                "identifier": "#38",
                "title": body["title"],
                "due_date": due,
                "repeat": {**parts, "read_only": False},
                "repeats_rrule": parts_to_rrule_text(parts),
                "repeats_from_current_date": bool(body.get("repeats_from_current_date")),
            }
            return _Resp(json.dumps({"id": 98, "identifier": "#38"}).encode())
        if method == "GET" and url == "https://vikunja.test/api/v2/tasks/98":
            return _Resp(json.dumps(self.task).encode())
        raise AssertionError(f"unexpected request {method} {url}")


@pytest.fixture
def clocked(monkeypatch) -> _ClockedServer:
    fake = _ClockedServer("2026-11-23T12:29:00Z")  # Mon 07:29 ET
    monkeypatch.setattr(urllib.request, "urlopen", fake.urlopen)
    monkeypatch.setattr(create_task, "_emit_completion_assertion", lambda task: None)
    return fake


def _preview_then_wait(clocked: _ClockedServer, capsys, *extra: str) -> dict[str, Any]:
    code, lines, err = _run(
        capsys, "--rrule", "FREQ=DAILY", "--initial-due-time", "07:30", *extra
    )
    assert code == 0, err
    summary = _summary(lines)
    assert summary["due_date"] == "2026-11-23T12:30:00Z"
    assert summary["due_date_et"] == "Mon 2026-11-23 07:30 ET"
    clocked.now += timedelta(minutes=2)  # Kent confirms at 07:31
    return summary


def test_delayed_confirmation_creates_the_previewed_anchor(clocked, capsys) -> None:
    summary = _preview_then_wait(clocked, capsys)
    assert summary["create_args"] == ["--rrule", "FREQ=DAILY", "--due", "2026-11-23T12:30:00Z"]

    code = create_task.main(
        ["--title", "Standup", "--project", "1", *summary["create_args"]], client=_client()
    )
    capsys.readouterr()

    assert code == 0
    create_body = next(b for m, u, b in clocked.calls if u.endswith("/projects/1/tasks"))
    assert "initial_due_time" not in create_body
    assert create_body["due_date"] == summary["due_date"]
    assert clocked.task is not None
    assert clocked.task["due_date"] == summary["due_date"]


def test_delayed_confirmation_keeps_from_completion(clocked, capsys) -> None:
    summary = _preview_then_wait(clocked, capsys, "--from-completion")
    assert summary["create_args"][-1] == "--from-completion"
    code = create_task.main(
        ["--title", "Stretch", "--project", "1", *summary["create_args"]], client=_client()
    )
    capsys.readouterr()
    assert code == 0
    assert clocked.task is not None
    assert clocked.task["due_date"] == summary["due_date"]
    assert clocked.task["repeats_from_current_date"] is True


def test_control_reusing_initial_due_time_after_delay_moves_the_anchor(clocked, capsys) -> None:
    """Positive control: the fixture models the hazard the flow avoids."""
    summary = _preview_then_wait(clocked, capsys)
    code = create_task.main(
        ["--title", "Standup", "--project", "1", "--rrule", "FREQ=DAILY",
         "--initial-due-time", "07:30"],
        client=_client(),
    )
    capsys.readouterr()
    assert code == 0
    assert clocked.task is not None
    assert clocked.task["due_date"] == "2026-11-24T12:30:00Z"
    assert clocked.task["due_date"] != summary["due_date"]


def test_create_refuses_a_stored_anchor_other_than_the_previewed_one(clocked, capsys) -> None:
    summary = _preview_then_wait(clocked, capsys)
    clocked.store_due_override = "2026-11-24T12:30:00Z"
    code = create_task.main(
        ["--title", "Standup", "--project", "1", *summary["create_args"]], client=_client()
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "asked due '2026-11-23T12:30:00Z'" in err


def test_no_anchor_gives_no_create_args(server, capsys) -> None:
    server(200, _answer(None, [], reason="until_passed"))
    _, lines, _ = _run(
        capsys, "--rrule", "FREQ=DAILY;UNTIL=20200101T000000Z", "--initial-due-time", "07:30"
    )
    summary = _summary(lines)
    assert summary["create_args"] is None
    assert not any("create with" in line for line in lines)
