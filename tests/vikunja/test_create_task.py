"""Tests for scripts.vikunja.create_task (issue #686; RRULE create, #1111 WP08).

Unit tests inject a fake client — no network, no token, no base-url config.
The HTTP-level tests drive a real ``VikunjaClient`` against a patched
``urllib.request.urlopen`` so the exact create body is asserted.
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from scripts.common.vikunja_client import VikunjaClient
from scripts.common.vikunja_rule import parts_to_rrule_text, rrule_text_to_parts
from scripts.vikunja import create_task as ct

FORTNIGHTLY = "FREQ=WEEKLY;INTERVAL=2;COUNT=6"


def _stored(rrule: str | None, **task: Any) -> dict[str, Any]:
    """A v2 task readback storing *rrule* (or no rule) the way the server does."""
    out: dict[str, Any] = {
        "id": 98,
        "identifier": "#38",
        "title": "T",
        "due_date": "2026-07-16T14:00:00Z",
        "repeats_from_current_date": False,
        **task,
    }
    if rrule is not None:
        parts = rrule_text_to_parts(rrule)
        out["repeat"] = {**parts, "read_only": False}
        out["repeats_rrule"] = parts_to_rrule_text(parts)
    return out


class _FakeClient:
    """Records calls and returns canned v2 responses."""

    def __init__(self, *, projects=None, created=None, readback=None, readback_exc=None):
        self._projects = projects if projects is not None else []
        self._created = created if created is not None else {"id": 98, "identifier": "#38"}
        self._readback = readback
        self._readback_exc = readback_exc
        self.create_calls: list[tuple[int, dict, dict]] = []
        self.read_calls: list[int] = []
        self.get_calls: list[str] = []

    def get(self, path, **_kwargs):
        self.get_calls.append(path)
        if path == "/projects":
            return self._projects
        raise AssertionError(f"unexpected GET {path}")

    def create_task_v2(self, project_id, fields, **kwargs):
        self.create_calls.append((project_id, dict(fields), kwargs))
        return dict(self._created)

    def get_task_v2(self, task_id):
        self.read_calls.append(task_id)
        if self._readback_exc is not None:
            raise self._readback_exc
        if self._readback is not None:
            return dict(self._readback)
        return {**self._created, "title": "T"}


# --- build_payload ---------------------------------------------------------


def test_build_payload_title_only():
    assert ct.build_payload("Buy milk") == {"title": "Buy milk"}


def test_build_payload_strips_title():
    assert ct.build_payload("  Buy milk  ") == {"title": "Buy milk"}


def test_build_payload_all_fields():
    payload = ct.build_payload(
        "T", due_date="2026-07-16T14:00:00Z", description="d", priority=3
    )
    assert payload == {
        "title": "T",
        "due_date": "2026-07-16T14:00:00Z",
        "description": "d",
        "priority": 3,
    }


def test_build_payload_omits_empty_optionals():
    # Empty/None optionals must not leak nulls into the create body.
    assert ct.build_payload("T", due_date=None, description="") == {"title": "T"}


def test_build_payload_empty_title_raises():
    with pytest.raises(ValueError):
        ct.build_payload("   ")


def test_build_payload_rule_keeps_rule_out_of_fields():
    # The rule travels as create_task_v2(rrule=...), never as a raw field.
    payload = ct.build_payload("Ping", due_date="2026-07-31T13:00:00Z", rrule=FORTNIGHTLY)
    assert payload == {"title": "Ping", "due_date": "2026-07-31T13:00:00Z"}


def test_build_payload_from_completion_maps_to_flag():
    payload = ct.build_payload(
        "Ping", due_date="2026-07-31T13:00:00Z", rrule="FREQ=DAILY", from_completion=True
    )
    assert payload["repeats_from_current_date"] is True


def test_build_payload_rule_without_anchor_raises():
    with pytest.raises(ValueError, match="needs a due date or --initial-due-time"):
        ct.build_payload("Ping", rrule="FREQ=DAILY")


def test_build_payload_initial_due_time_allows_no_due_date():
    assert ct.build_payload("Ping", rrule="FREQ=DAILY", initial_due_time="07:30") == {
        "title": "Ping"
    }


@pytest.mark.parametrize("bad", ["7:30", "24:00", "07:60", "0730", "07:30:00"])
def test_build_payload_rejects_bad_initial_due_time(bad):
    with pytest.raises(ValueError, match="HH:MM"):
        ct.build_payload("Ping", rrule="FREQ=DAILY", initial_due_time=bad)


def test_build_payload_due_and_initial_due_time_conflict():
    with pytest.raises(ValueError, match="not both"):
        ct.build_payload(
            "Ping", due_date="2026-07-31T13:00:00Z", rrule="FREQ=DAILY",
            initial_due_time="07:30",
        )


@pytest.mark.parametrize(
    "kwargs", [{"from_completion": True}, {"initial_due_time": "07:30"}]
)
def test_build_payload_recurrence_options_need_rrule(kwargs):
    with pytest.raises(ValueError, match="need --rrule"):
        ct.build_payload("Ping", due_date="2026-07-31T13:00:00Z", **kwargs)


@pytest.mark.parametrize(
    "bad", ["WEEKLY", "FREQ=WEEKLY;BOGUS=1", "INTERVAL=2", "FREQ=DAILY;UNTIL=20261231"]
)
def test_build_payload_invalid_rrule_raises(bad):
    with pytest.raises(ValueError):
        ct.build_payload("Ping", due_date="2026-07-31T13:00:00Z", rrule=bad)


# --- resolve_project_id ----------------------------------------------------


def test_resolve_numeric_passthrough():
    client = _FakeClient()
    assert ct.resolve_project_id(client, "14") == 14
    assert client.get_calls == []  # no /projects fetch for a numeric id


def test_resolve_name_single_match():
    client = _FakeClient(projects=[{"id": 7, "title": "Work"}, {"id": 3, "title": "Home"}])
    assert ct.resolve_project_id(client, "work") == 7  # case-insensitive


def test_resolve_name_multi_match_lowest_id_wins():
    # Two "Inbox" projects (id 1 and 14) — deterministic tie-break to 1.
    client = _FakeClient(
        projects=[{"id": 14, "title": "Inbox"}, {"id": 1, "title": "Inbox"}]
    )
    assert ct.resolve_project_id(client, "Inbox") == 1


def test_resolve_name_no_match_raises():
    client = _FakeClient(projects=[{"id": 1, "title": "Inbox"}])
    with pytest.raises(ValueError):
        ct.resolve_project_id(client, "Nonexistent")


# --- create_task -----------------------------------------------------------


def test_create_task_uses_create_task_v2_and_reads_back():
    client = _FakeClient(readback=_stored(None))
    result = ct.create_task(client, 1, {"title": "T"})
    assert client.create_calls == [(1, {"title": "T"}, {"rrule": None, "initial_due_time": None})]
    assert client.read_calls == [98]
    assert result["identifier"] == "#38"


def test_create_task_passes_rule_and_accepts_stored_rule():
    client = _FakeClient(readback=_stored(FORTNIGHTLY))
    result = ct.create_task(client, 1, {"title": "T"}, rrule=FORTNIGHTLY)
    assert client.create_calls[0][2] == {"rrule": FORTNIGHTLY, "initial_due_time": None}
    assert result["repeats_rrule"] == "FREQ=WEEKLY;INTERVAL=2;COUNT=6"


@pytest.mark.parametrize(
    "stored",
    [
        pytest.param(None, id="rule-missing"),
        pytest.param("FREQ=WEEKLY;INTERVAL=1;COUNT=6", id="rule-different"),
    ],
)
def test_create_task_rule_not_stored_raises_with_task_id(stored):
    client = _FakeClient(readback=_stored(stored))
    with pytest.raises(ct.RuleNotStoredError) as info:
        ct.create_task(client, 1, {"title": "T"}, rrule=FORTNIGHTLY)
    assert info.value.task_id == 98
    assert "created task 98 but its rule is missing/different" in str(info.value)


@pytest.mark.parametrize(
    ("asked", "served_by_day", "stored_text"),
    [
        ("FREQ=MONTHLY;BYDAY=+1MO", ["1mo"], "FREQ=MONTHLY;BYDAY=+1MO"),
        ("FREQ=MONTHLY;BYDAY=-1FR", ["-1fr"], "FREQ=MONTHLY;BYDAY=-1FR"),
        ("FREQ=MONTHLY;BYDAY=+1MO,-1FR", ["1mo", "-1fr"], "FREQ=MONTHLY;BYDAY=+1MO,-1FR"),
    ],
)
def test_create_task_accepts_server_shaped_ordinal_by_day(asked, served_by_day, stored_text):
    """The server serves structured by_day without "+" (d7e202228
    task_repeat.go:556-562) beside the stored text: a successful create."""
    readback = {
        **_stored(None),
        "repeat": {"freq": "monthly", "interval": 1, "by_day": served_by_day},
        "repeats_rrule": stored_text,
    }
    client = _FakeClient(readback=readback)
    result = ct.create_task(client, 1, {"title": "T"}, rrule=asked)
    assert result["repeats_rrule"] == stored_text


def test_main_ordinal_rule_exits_0_and_wrong_ordinal_exits_1(capsys):
    served = {**_stored(None), "repeat": {"freq": "monthly", "interval": 1, "by_day": ["1mo"]},
              "repeats_rrule": "FREQ=MONTHLY;BYDAY=+1MO"}
    ok = ct.main(["--title", "T", "--due", "2026-07-16T14:00:00Z",
                  "--rrule", "FREQ=MONTHLY;BYDAY=+1MO"], client=_FakeClient(readback=served))
    assert ok == 0
    wrong = ct.main(["--title", "T", "--due", "2026-07-16T14:00:00Z",
                     "--rrule", "FREQ=MONTHLY;BYDAY=+2MO"], client=_FakeClient(readback=served))
    assert wrong == 1
    assert "rule is missing/different" in capsys.readouterr().err


def test_create_task_from_completion_flag_must_stick():
    client = _FakeClient(readback=_stored("FREQ=DAILY", repeats_from_current_date=False))
    with pytest.raises(ct.RuleNotStoredError, match="repeats_from_current_date"):
        ct.create_task(
            client, 1, {"title": "T", "repeats_from_current_date": True}, rrule="FREQ=DAILY"
        )


def test_create_task_initial_due_time_without_generated_due_raises():
    client = _FakeClient(
        created={"id": 98, "reason": "until_passed"},
        readback=_stored("FREQ=DAILY;UNTIL=20200101T000000Z", due_date=None),
    )
    with pytest.raises(ct.RuleNotStoredError, match="until_passed"):
        ct.create_task(
            client, 1, {"title": "T"},
            rrule="FREQ=DAILY;UNTIL=20200101T000000Z", initial_due_time="07:30",
        )


def test_create_task_readback_failure_names_the_created_task():
    client = _FakeClient(readback_exc=RuntimeError("api down"))
    with pytest.raises(RuntimeError, match="created task 98 but could not read it back"):
        ct.create_task(client, 1, {"title": "T"})


# --- main ------------------------------------------------------------------


def test_main_success_human_output(capsys):
    client = _FakeClient(readback=_stored(None))
    rc = ct.main(["--title", "T", "--project", "1", "--due", "2026-07-16T14:00:00Z"], client=client)
    assert rc == 0
    out = capsys.readouterr().out
    assert "identifier=#38" in out and "id=98" in out and "title: T" in out
    assert client.create_calls[0][1] == {"title": "T", "due_date": "2026-07-16T14:00:00Z"}


def test_main_recurring_success_reports_rule(capsys):
    client = _FakeClient(readback=_stored(FORTNIGHTLY))
    rc = ct.main(
        ["--title", "T", "--due", "2026-07-16T14:00:00Z", "--rrule", FORTNIGHTLY],
        client=client,
    )
    assert rc == 0
    assert "rule: FREQ=WEEKLY;INTERVAL=2;COUNT=6" in capsys.readouterr().out


def test_main_rule_missing_on_readback_exits_1(capsys, monkeypatch):
    """Positive control: a recurring create that came back a one-off never
    reports success (and never emits a completion assertion)."""
    emitted: list[dict] = []
    monkeypatch.setattr(ct, "_emit_completion_assertion", emitted.append)
    client = _FakeClient(readback=_stored(None))
    rc = ct.main(
        ["--title", "T", "--due", "2026-07-16T14:00:00Z", "--rrule", FORTNIGHTLY],
        client=client,
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "created task 98 but its rule is missing/different" in captured.err
    assert "CREATED" not in captured.out
    assert emitted == []


def test_main_from_completion_and_initial_due_time(capsys):
    client = _FakeClient(
        readback=_stored("FREQ=DAILY", repeats_from_current_date=True)
    )
    rc = ct.main(
        ["--title", "T", "--rrule", "FREQ=DAILY", "--from-completion",
         "--initial-due-time", "07:30"],
        client=client,
    )
    assert rc == 0
    _project, fields, kwargs = client.create_calls[0]
    assert fields == {"title": "T", "repeats_from_current_date": True}
    assert kwargs == {"rrule": "FREQ=DAILY", "initial_due_time": "07:30"}


def test_main_invalid_rrule_rejected_before_any_call(capsys):
    client = _FakeClient()
    rc = ct.main(
        ["--title", "T", "--due", "2026-07-16T14:00:00Z", "--rrule", "FREQ=WEEKLY;NOPE=1"],
        client=client,
    )
    assert rc == 1
    assert "unknown RRULE key" in capsys.readouterr().err
    assert client.create_calls == [] and client.get_calls == []


@pytest.mark.parametrize("flag", ["--repeat-after", "--repeat-mode"])
def test_main_retired_repeat_flags_are_rejected(flag):
    with pytest.raises(SystemExit) as info:
        ct.main(["--title", "T", flag, "1"], client=_FakeClient())
    assert info.value.code == 2


def test_main_json_output(capsys):
    client = _FakeClient(readback=_stored(None))
    rc = ct.main(["--title", "T", "--json"], client=client)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["id"] == 98


def test_main_defaults_to_inbox_project_1():
    client = _FakeClient(readback=_stored(None))
    ct.main(["--title", "T"], client=client)
    assert client.create_calls[0][0] == 1


def test_main_reports_failure_and_returns_1(capsys):
    class _Boom(_FakeClient):
        def create_task_v2(self, project_id, fields, **kwargs):
            raise RuntimeError("api down")

    rc = ct.main(["--title", "T"], client=_Boom())
    assert rc == 1
    assert "ERROR:" in capsys.readouterr().err


# --- HTTP level: the real client's create body ---------------------------------


class _Resp:
    def __init__(self, payload: Any) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _http_client(monkeypatch, readback: dict) -> list[urllib.request.Request]:
    calls: list[urllib.request.Request] = []

    def urlopen(req, timeout=None):
        calls.append(req)
        if req.get_method() == "POST":
            return _Resp({"id": 98, "identifier": "#38"})
        if req.get_method() == "GET" and req.full_url.endswith("/api/v2/tasks/98"):
            return _Resp(readback)
        raise urllib.error.HTTPError(req.full_url, 404, "nf", hdrs=None, fp=io.BytesIO(b""))  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    return calls


def test_http_create_body_carries_repeats_rrule(monkeypatch, capsys):
    calls = _http_client(monkeypatch, _stored(FORTNIGHTLY, repeats_from_current_date=True))
    client = VikunjaClient(base_url="https://vikunja.test/api/v1", token="t")
    rc = ct.main(
        ["--title", "T", "--project", "3", "--due", "2026-07-16T14:00:00Z",
         "--rrule", FORTNIGHTLY, "--from-completion"],
        client=client,
    )
    assert rc == 0
    post = calls[0]
    assert post.get_method() == "POST"
    assert post.full_url == "https://vikunja.test/api/v2/projects/3/tasks"
    body = json.loads(post.data.decode("utf-8"))
    assert body == {
        "title": "T",
        "due_date": "2026-07-16T14:00:00Z",
        "repeats_from_current_date": True,
        "repeats_rrule": FORTNIGHTLY,
    }
    assert "repeat_after" not in body and "repeat_mode" not in body
    assert [c.get_method() for c in calls] == ["POST", "GET"]


def test_http_one_off_readback_exits_1(monkeypatch, capsys):
    """Positive control at the HTTP seam: the server stored no rule."""
    _http_client(monkeypatch, _stored(None))
    client = VikunjaClient(base_url="https://vikunja.test/api/v1", token="t")
    rc = ct.main(
        ["--title", "T", "--due", "2026-07-16T14:00:00Z", "--rrule", FORTNIGHTLY],
        client=client,
    )
    assert rc == 1
    assert "created task 98 but its rule is missing/different" in capsys.readouterr().err
