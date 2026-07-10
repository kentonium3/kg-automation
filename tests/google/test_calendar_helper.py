"""Unit tests for ``scripts.google.calendar_helper`` (mission WP02).

CI-safe by construction: the real ``google-*`` / ``googleapiclient`` packages
are NOT relied upon. These tests inject fakes into ``sys.modules`` for
``googleapiclient.discovery`` **before** importing the module under test and
mock ``calendar_auth.load_credentials`` per-test, so nothing requires the real
libraries and no test touches the network. Any unmocked ``.execute()`` on the
fake service raises, guaranteeing no accidental live call.

Canonical invocation (repo threshold 90):

    pytest tests/google/test_calendar_helper.py \
        --cov=scripts.google.calendar_helper --cov-branch --cov-fail-under=90

Covers:
- create happy path (payload-file + explicit); body mapping incl. rrule/attendees;
- ``sendUpdates=none`` default (asserts the kwarg);
- attendees rejected on the payload-file path without ``--allow-attendees`` (exit 2);
- idempotent retry (matching key → existing event, no second insert);
- list (window + empty); update patch + ``--clear``; recurring-scope error; delete;
- ``not_found`` (exit 1); ``--self-check`` ok + auth-fail (exit 3, no mutation);
- exit-code contract per subcommand; ``SUMMARY:`` is the final stdout line always.
"""
from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest


# --------------------------------------------------------------------------- #
# Fake googleapiclient service — records calls, guards .execute()
# --------------------------------------------------------------------------- #


class _FakeRequest:
    """A pending API request. ``.execute()`` returns a preset value or raises."""

    def __init__(self, name: str, kwargs: dict[str, Any], recorder: "_Recorder"):
        self.name = name
        self.kwargs = kwargs
        self._recorder = recorder

    def execute(self) -> Any:
        outcome = self._recorder.outcomes.get(self.name)
        if outcome is None:
            raise AssertionError(
                f"unmocked .execute() for {self.name!r} — no live calls allowed"
            )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeEvents:
    def __init__(self, recorder: "_Recorder"):
        self._recorder = recorder

    def _record(self, name: str, **kwargs: Any) -> _FakeRequest:
        self._recorder.calls.append((name, kwargs))
        return _FakeRequest(name, kwargs, self._recorder)

    def insert(self, **kwargs: Any) -> _FakeRequest:
        return self._record("insert", **kwargs)

    def list(self, **kwargs: Any) -> _FakeRequest:
        return self._record("list", **kwargs)

    def get(self, **kwargs: Any) -> _FakeRequest:
        return self._record("get", **kwargs)

    def patch(self, **kwargs: Any) -> _FakeRequest:
        return self._record("patch", **kwargs)

    def delete(self, **kwargs: Any) -> _FakeRequest:
        return self._record("delete", **kwargs)


class _FakeService:
    def __init__(self, recorder: "_Recorder"):
        self._events = _FakeEvents(recorder)

    def events(self) -> _FakeEvents:
        return self._events


class _Recorder:
    """Records API calls and holds per-method ``.execute()`` outcomes.

    ``outcomes[name]`` may be a return value (dict) or an ``Exception`` to raise.
    ``list`` is special-cased: successive ``list`` calls consume from
    ``list_queue`` if present (so idempotency-dedupe list and a later list can
    differ); otherwise fall back to ``outcomes['list']``.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.outcomes: dict[str, Any] = {}
        self.list_queue: list[Any] | None = None

    def calls_for(self, name: str) -> list[dict[str, Any]]:
        return [kw for (n, kw) in self.calls if n == name]


class _HttpError(Exception):
    """Stand-in for googleapiclient.errors.HttpError with a ``.resp.status``."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.resp = types.SimpleNamespace(status=status)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def recorder() -> _Recorder:
    return _Recorder()


@pytest.fixture()
def helper(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder):
    """Import the helper with a fake googleapiclient and stubbed auth.

    ``build`` returns a service whose ``.events()`` records calls against the
    shared ``recorder``. ``load_credentials`` is stubbed to succeed by default;
    individual tests override it to raise ``CalendarAuthError``.
    """
    # Fake googleapiclient.discovery.build → our fake service.
    gac_mod = types.ModuleType("googleapiclient")
    discovery_mod = types.ModuleType("googleapiclient.discovery")

    def _build(*_a: Any, **_k: Any) -> _FakeService:
        return _FakeService(recorder)

    discovery_mod.build = _build  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "googleapiclient", gac_mod)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery_mod)

    module = importlib.import_module("scripts.google.calendar_helper")
    module = importlib.reload(module)

    # Stub auth so no real credential file/network is touched.
    monkeypatch.setattr(
        module, "load_credentials", lambda *a, **k: object()
    )
    return module


def _seed_list_queue(
    recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enable queue-based ``list`` responses (consumed in call order).

    Uses ``monkeypatch`` so the class method is restored after the test — no
    cross-test leakage.
    """
    original_execute = _FakeRequest.execute

    def queued_execute(self: _FakeRequest) -> Any:
        if self.name == "list" and recorder.list_queue is not None:
            if not recorder.list_queue:
                raise AssertionError("list_queue exhausted")
            return recorder.list_queue.pop(0)
        return original_execute(self)

    monkeypatch.setattr(_FakeRequest, "execute", queued_execute)


def run(module: Any, argv: list[str]) -> int:
    return module.main(argv)


def _last_line(capsys: pytest.CaptureFixture[str]) -> str:
    out = capsys.readouterr().out.strip().splitlines()
    return out[-1] if out else ""


def _stdout_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().out.strip().splitlines()


# --------------------------------------------------------------------------- #
# create — explicit mode + body mapping
# --------------------------------------------------------------------------- #


def test_create_explicit_maps_body_and_defaults_send_updates_none(
    helper, recorder, capsys
):
    recorder.outcomes["insert"] = {"id": "evt1", "htmlLink": "https://cal/evt1"}
    code = run(
        helper,
        [
            "create",
            "--summary", "Dentist",
            "--start", "2026-07-14T15:00:00-04:00",
            "--end", "2026-07-14T16:00:00-04:00",
            "--start-timezone", "America/New_York",
            "--location", "Office",
            "--description", "Source: note.md",
            "--rrule", "RRULE:FREQ=WEEKLY;BYDAY=MO",
            "--json",
        ],
    )
    assert code == 0
    inserts = recorder.calls_for("insert")
    assert len(inserts) == 1
    kw = inserts[0]
    # sendUpdates default is none (no accidental invitations).
    assert kw["sendUpdates"] == "none"
    body = kw["body"]
    assert body["summary"] == "Dentist"
    assert body["start"] == {
        "dateTime": "2026-07-14T15:00:00-04:00",
        "timeZone": "America/New_York",
    }
    assert body["end"]["dateTime"] == "2026-07-14T16:00:00-04:00"
    assert body["location"] == "Office"
    assert body["description"] == "Source: note.md"
    assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO"]
    lines = _stdout_lines(capsys)
    # JSON precedes SUMMARY; SUMMARY is the final line.
    assert lines[-1].startswith("SUMMARY:")
    parsed = json.loads(lines[0])
    assert parsed == {
        "status": "created",
        "idempotent": False,
        "event_id": "evt1",
        "html_link": "https://cal/evt1",
    }
    assert "status=created" in lines[-1]
    assert "idempotent=false" in lines[-1]
    assert "event_id=evt1" in lines[-1]


def test_create_default_timezone_when_omitted(helper, recorder, capsys):
    recorder.outcomes["insert"] = {"id": "evt2"}
    code = run(
        helper,
        [
            "create",
            "--summary", "Call",
            "--start", "2026-07-14T15:00:00-04:00",
            "--end", "2026-07-14T16:00:00-04:00",
        ],
    )
    assert code == 0
    body = recorder.calls_for("insert")[0]["body"]
    assert body["start"]["timeZone"] == "America/New_York"


def test_create_payload_file_mode(helper, recorder, capsys, tmp_path: Path):
    payload = {
        "action": "create_calendar_event",
        "calendar_id": "primary",
        "account": "personal",
        "summary": "Dentist",
        "start_rfc3339": "2026-07-14T15:00:00-04:00",
        "end_rfc3339": "2026-07-14T16:00:00-04:00",
        "start_timezone": "America/New_York",
        "location": None,
        "description": "Source: note-123.md",
        "rrule": None,
        "attendees": None,
        "source_inbox_path": "/x/note-123.md",
    }
    pf = tmp_path / "payload.json"
    pf.write_text(json.dumps(payload))
    recorder.outcomes["insert"] = {"id": "evtP", "htmlLink": "L"}
    code = run(helper, ["create", "--payload-file", str(pf), "--json"])
    assert code == 0
    body = recorder.calls_for("insert")[0]["body"]
    assert body["summary"] == "Dentist"
    assert "attendees" not in body
    assert _last_line(capsys).startswith("SUMMARY:")


def test_create_payload_attendees_rejected_without_flag(
    helper, recorder, capsys, tmp_path: Path
):
    payload = {
        "summary": "Dinner",
        "start_rfc3339": "2026-07-14T15:00:00-04:00",
        "end_rfc3339": "2026-07-14T16:00:00-04:00",
        "attendees": "a@x.com,b@y.com",
    }
    pf = tmp_path / "payload.json"
    pf.write_text(json.dumps(payload))
    code = run(helper, ["create", "--payload-file", str(pf)])
    assert code == 2  # usage error
    # No mutation attempted.
    assert recorder.calls_for("insert") == []
    err = capsys.readouterr().err
    assert "allow-attendees" in err


def test_create_payload_attendees_allowed_with_flag(
    helper, recorder, capsys, tmp_path: Path
):
    payload = {
        "summary": "Dinner",
        "start_rfc3339": "2026-07-14T15:00:00-04:00",
        "end_rfc3339": "2026-07-14T16:00:00-04:00",
        "attendees": "a@x.com, b@y.com",
    }
    pf = tmp_path / "payload.json"
    pf.write_text(json.dumps(payload))
    recorder.outcomes["insert"] = {"id": "evtA"}
    code = run(
        helper,
        ["create", "--payload-file", str(pf), "--allow-attendees"],
    )
    assert code == 0
    body = recorder.calls_for("insert")[0]["body"]
    assert body["attendees"] == [{"email": "a@x.com"}, {"email": "b@y.com"}]


def test_create_explicit_attendees_and_send_updates_all(helper, recorder, capsys):
    recorder.outcomes["insert"] = {"id": "evtE"}
    code = run(
        helper,
        [
            "create",
            "--summary", "Sync",
            "--start", "2026-07-14T15:00:00-04:00",
            "--end", "2026-07-14T16:00:00-04:00",
            "--attendees", "x@z.com",
            "--send-updates", "all",
        ],
    )
    assert code == 0
    kw = recorder.calls_for("insert")[0]
    assert kw["sendUpdates"] == "all"
    assert kw["body"]["attendees"] == [{"email": "x@z.com"}]


def test_create_both_modes_is_usage_error(helper, recorder, capsys, tmp_path: Path):
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps({"summary": "x"}))
    code = run(
        helper,
        ["create", "--payload-file", str(pf), "--summary", "y"],
    )
    assert code == 2
    assert recorder.calls_for("insert") == []


def test_create_neither_mode_is_usage_error(helper, recorder, capsys):
    code = run(helper, ["create"])
    assert code == 2
    assert recorder.calls_for("insert") == []


def test_create_missing_summary_is_usage_error(helper, recorder, capsys):
    code = run(
        helper,
        ["create", "--start", "2026-07-14T15:00:00-04:00",
         "--end", "2026-07-14T16:00:00-04:00", "--location", "here"],
    )
    # explicit mode active (location), but no summary → exit 2
    assert code == 2
    assert recorder.calls_for("insert") == []


def test_create_missing_end_is_usage_error(helper, recorder, capsys):
    code = run(
        helper,
        ["create", "--summary", "x", "--start", "2026-07-14T15:00:00-04:00"],
    )
    assert code == 2
    assert recorder.calls_for("insert") == []


def test_create_bad_payload_file_is_usage_error(helper, recorder, capsys):
    code = run(helper, ["create", "--payload-file", "/no/such/file.json"])
    assert code == 2


def test_create_payload_not_json_is_usage_error(
    helper, recorder, capsys, tmp_path: Path
):
    pf = tmp_path / "bad.json"
    pf.write_text("{not json")
    code = run(helper, ["create", "--payload-file", str(pf)])
    assert code == 2


def test_create_payload_not_object_is_usage_error(
    helper, recorder, capsys, tmp_path: Path
):
    pf = tmp_path / "arr.json"
    pf.write_text("[1,2,3]")
    code = run(helper, ["create", "--payload-file", str(pf)])
    assert code == 2


def test_create_dry_run_does_not_insert(helper, recorder, capsys):
    code = run(
        helper,
        [
            "create", "--summary", "x",
            "--start", "2026-07-14T15:00:00-04:00",
            "--end", "2026-07-14T16:00:00-04:00",
            "--dry-run",
        ],
    )
    assert code == 0
    assert recorder.calls_for("insert") == []
    last = _last_line(capsys)
    assert last.startswith("SUMMARY:")
    assert "status=dry_run" in last


# --------------------------------------------------------------------------- #
# create — idempotency
# --------------------------------------------------------------------------- #


def test_create_idempotent_returns_existing_no_second_insert(
    helper, recorder, monkeypatch, capsys
):
    _seed_list_queue(recorder, monkeypatch)
    # The dedupe list finds an existing event → no insert.
    recorder.list_queue = [
        {"items": [{"id": "evtExisting", "htmlLink": "L"}]}
    ]
    code = run(
        helper,
        [
            "create", "--summary", "x",
            "--start", "2026-07-14T15:00:00-04:00",
            "--end", "2026-07-14T16:00:00-04:00",
            "--idempotency-key", "note-123",
            "--json",
        ],
    )
    assert code == 0
    assert recorder.calls_for("insert") == []
    lines = _stdout_lines(capsys)
    assert "idempotent=true" in lines[-1]
    assert "event_id=evtExisting" in lines[-1]
    parsed = json.loads(lines[0])
    assert parsed["idempotent"] is True


def test_create_idempotent_no_match_inserts_and_stamps_key(
    helper, recorder, monkeypatch, capsys
):
    _seed_list_queue(recorder, monkeypatch)
    recorder.list_queue = [{"items": []}]  # dedupe list finds nothing
    recorder.outcomes["insert"] = {"id": "evtNew"}
    code = run(
        helper,
        [
            "create", "--summary", "x",
            "--start", "2026-07-14T15:00:00-04:00",
            "--end", "2026-07-14T16:00:00-04:00",
            "--idempotency-key", "note-999",
        ],
    )
    assert code == 0
    body = recorder.calls_for("insert")[0]["body"]
    assert body["extendedProperties"]["private"]["felix_source_key"] == "note-999"
    # The dedupe list filtered on the private key.
    list_kw = recorder.calls_for("list")[0]
    assert list_kw["privateExtendedProperty"] == "felix_source_key=note-999"


def test_create_idempotency_skipped_on_dry_run(helper, recorder, capsys):
    code = run(
        helper,
        [
            "create", "--summary", "x",
            "--start", "2026-07-14T15:00:00-04:00",
            "--end", "2026-07-14T16:00:00-04:00",
            "--idempotency-key", "k", "--dry-run",
        ],
    )
    assert code == 0
    # dry-run performs no list-lookup and no insert
    assert recorder.calls_for("list") == []
    assert recorder.calls_for("insert") == []


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #


def test_list_window_returns_concrete_schema(helper, recorder, capsys):
    recorder.outcomes["list"] = {
        "items": [
            {
                "id": "abc",
                "summary": "Dentist",
                "start": {"dateTime": "2026-07-14T15:00:00-04:00"},
                "end": {"dateTime": "2026-07-14T16:00:00-04:00"},
            },
            {
                "id": "def",
                "summary": "Weekly",
                "start": {"dateTime": "2026-07-15T09:00:00-04:00"},
                "end": {"dateTime": "2026-07-15T10:00:00-04:00"},
                "recurrence": ["RRULE:FREQ=WEEKLY"],
            },
        ]
    }
    code = run(
        helper,
        ["list", "--from", "2026-07-14T00:00:00-04:00",
         "--to", "2026-07-16T00:00:00-04:00", "--json"],
    )
    assert code == 0
    lines = _stdout_lines(capsys)
    payload = json.loads(lines[0])
    assert payload["status"] == "ok"
    assert payload["count"] == 2
    assert payload["events"][0] == {
        "event_id": "abc",
        "summary": "Dentist",
        "start": "2026-07-14T15:00:00-04:00",
        "end": "2026-07-14T16:00:00-04:00",
        "recurring": False,
    }
    assert payload["events"][1]["recurring"] is True
    assert lines[-1].startswith("SUMMARY:")
    assert "count=2" in lines[-1]


def test_list_empty_window_is_count_zero_not_error(helper, recorder, capsys):
    recorder.outcomes["list"] = {"items": []}
    code = run(
        helper,
        ["list", "--from", "2026-07-14T00:00:00-04:00",
         "--to", "2026-07-16T00:00:00-04:00", "--json"],
    )
    assert code == 0
    payload = json.loads(_stdout_lines(capsys)[0])
    assert payload["count"] == 0
    assert payload["events"] == []


def test_list_passes_window_and_max(helper, recorder, capsys):
    recorder.outcomes["list"] = {"items": []}
    run(
        helper,
        ["list", "--from", "F", "--to", "T", "--max", "10"],
    )
    kw = recorder.calls_for("list")[0]
    assert kw["timeMin"] == "F"
    assert kw["timeMax"] == "T"
    assert kw["maxResults"] == 10
    assert kw["singleEvents"] is True


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #


def test_update_patch_only_provided_fields(helper, recorder, capsys):
    recorder.outcomes["get"] = {"id": "evt1"}
    recorder.outcomes["patch"] = {"id": "evt1"}
    code = run(
        helper,
        ["update", "--event-id", "evt1", "--summary", "New Title", "--json"],
    )
    assert code == 0
    patch_kw = recorder.calls_for("patch")[0]
    assert patch_kw["eventId"] == "evt1"
    assert patch_kw["body"] == {"summary": "New Title"}
    assert patch_kw["sendUpdates"] == "none"
    lines = _stdout_lines(capsys)
    assert lines[-1].startswith("SUMMARY:")
    assert "status=updated" in lines[-1]


def test_update_clear_removes_fields(helper, recorder, capsys):
    recorder.outcomes["get"] = {"id": "evt1"}
    recorder.outcomes["patch"] = {"id": "evt1"}
    code = run(
        helper,
        ["update", "--event-id", "evt1", "--clear", "location,description"],
    )
    assert code == 0
    body = recorder.calls_for("patch")[0]["body"]
    assert body["location"] is None
    assert body["description"] is None


def test_update_clear_unknown_field_is_usage_error(helper, recorder, capsys):
    recorder.outcomes["get"] = {"id": "evt1"}
    code = run(
        helper,
        ["update", "--event-id", "evt1", "--clear", "bogus"],
    )
    assert code == 2
    assert recorder.calls_for("patch") == []


def test_update_no_changes_is_usage_error(helper, recorder, capsys):
    recorder.outcomes["get"] = {"id": "evt1"}
    code = run(helper, ["update", "--event-id", "evt1"])
    assert code == 2
    assert recorder.calls_for("patch") == []


def test_update_missing_event_is_not_found_exit_1(helper, recorder, capsys):
    recorder.outcomes["get"] = _HttpError(404)
    code = run(
        helper,
        ["update", "--event-id", "missing", "--summary", "x"],
    )
    assert code == 1
    assert recorder.calls_for("patch") == []
    err = capsys.readouterr().err
    assert "not_found" in err


def test_update_recurrence_single_scope_unsupported_exit_2(helper, recorder, capsys):
    code = run(
        helper,
        ["update", "--event-id", "evt1", "--summary", "x",
         "--recurrence-scope", "single"],
    )
    assert code == 2
    # Guard fires before any get/patch.
    assert recorder.calls_for("get") == []
    assert recorder.calls_for("patch") == []
    assert "recurrence_scope_unsupported" in capsys.readouterr().err


def test_update_start_carries_timezone(helper, recorder, capsys):
    recorder.outcomes["get"] = {"id": "evt1"}
    recorder.outcomes["patch"] = {"id": "evt1"}
    run(
        helper,
        ["update", "--event-id", "evt1",
         "--start", "2026-07-14T15:00:00-04:00",
         "--end", "2026-07-14T16:00:00-04:00"],
    )
    body = recorder.calls_for("patch")[0]["body"]
    assert body["start"]["timeZone"] == "America/New_York"


def test_update_dry_run_does_not_patch(helper, recorder, capsys):
    recorder.outcomes["get"] = {"id": "evt1"}
    code = run(
        helper,
        ["update", "--event-id", "evt1", "--summary", "x", "--dry-run"],
    )
    assert code == 0
    assert recorder.calls_for("patch") == []
    assert "status=dry_run" in _last_line(capsys)


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #


def test_delete_removes_event(helper, recorder, capsys):
    recorder.outcomes["delete"] = ""
    code = run(helper, ["delete", "--event-id", "evt1", "--json"])
    assert code == 0
    kw = recorder.calls_for("delete")[0]
    assert kw["eventId"] == "evt1"
    assert kw["sendUpdates"] == "none"
    lines = _stdout_lines(capsys)
    assert lines[-1].startswith("SUMMARY:")
    assert "status=deleted" in lines[-1]
    assert json.loads(lines[0])["status"] == "deleted"


def test_delete_missing_event_is_not_found_exit_1(helper, recorder, capsys):
    recorder.outcomes["delete"] = _HttpError(404)
    code = run(helper, ["delete", "--event-id", "missing"])
    assert code == 1
    assert "not_found" in capsys.readouterr().err


def test_delete_send_updates_all(helper, recorder, capsys):
    recorder.outcomes["delete"] = ""
    run(helper, ["delete", "--event-id", "evt1", "--send-updates", "all"])
    assert recorder.calls_for("delete")[0]["sendUpdates"] == "all"


def test_delete_recurrence_single_scope_unsupported_exit_2(helper, recorder, capsys):
    code = run(
        helper,
        ["delete", "--event-id", "evt1", "--recurrence-scope", "single"],
    )
    assert code == 2
    assert recorder.calls_for("delete") == []


def test_delete_dry_run_confirms_but_does_not_delete(helper, recorder, capsys):
    recorder.outcomes["get"] = {"id": "evt1"}
    code = run(helper, ["delete", "--event-id", "evt1", "--dry-run"])
    assert code == 0
    assert recorder.calls_for("delete") == []
    assert "status=dry_run" in _last_line(capsys)


# --------------------------------------------------------------------------- #
# generic API error (non-404) → exit 1
# --------------------------------------------------------------------------- #


def test_api_5xx_error_is_operational_exit_1(helper, recorder, capsys):
    recorder.outcomes["insert"] = _HttpError(503)
    code = run(
        helper,
        ["create", "--summary", "x",
         "--start", "2026-07-14T15:00:00-04:00",
         "--end", "2026-07-14T16:00:00-04:00"],
    )
    assert code == 1
    last = _last_line(capsys)
    assert last.startswith("SUMMARY:")
    assert "status=error" in last


# --------------------------------------------------------------------------- #
# --self-check
# --------------------------------------------------------------------------- #


def test_self_check_ok(helper, recorder, capsys):
    recorder.outcomes["list"] = {"items": []}
    code = run(helper, ["--self-check"])
    assert code == 0
    kw = recorder.calls_for("list")[0]
    assert kw["calendarId"] == "primary"
    assert kw["maxResults"] == 1
    line = _last_line(capsys)
    assert line.startswith("SUMMARY:")
    assert "op=self-check" in line
    assert "status=ok" in line


def test_self_check_auth_failure_exit_3_no_mutation(helper, recorder, monkeypatch, capsys):
    from scripts.google.calendar_auth import CalendarAuthError

    def _raise(*a: Any, **k: Any):
        raise CalendarAuthError("no token.json: re-mint on the Mac")

    monkeypatch.setattr(helper, "load_credentials", _raise)
    code = run(helper, ["--self-check"])
    assert code == 3
    # No API call whatsoever (auth resolved first).
    assert recorder.calls == []
    out = capsys.readouterr()
    assert "auth_failed" in out.err
    # SUMMARY status=auth_failed on stdout, and it is the final line.
    summary = out.out.strip().splitlines()[-1]
    assert summary.startswith("SUMMARY:")
    assert "op=self-check" in summary
    assert "status=auth_failed" in summary


def test_auth_failure_on_create_exit_3_never_inserts(
    helper, recorder, monkeypatch, capsys
):
    from scripts.google.calendar_auth import CalendarAuthError

    monkeypatch.setattr(
        helper, "load_credentials",
        lambda *a, **k: (_ for _ in ()).throw(CalendarAuthError("bad token")),
    )
    code = run(
        helper,
        ["create", "--summary", "x",
         "--start", "2026-07-14T15:00:00-04:00",
         "--end", "2026-07-14T16:00:00-04:00"],
    )
    assert code == 3
    assert recorder.calls_for("insert") == []
    out = capsys.readouterr()
    assert out.err.startswith("ERROR: auth_failed")
    assert "status=auth_failed" in out.out.strip().splitlines()[-1]


# --------------------------------------------------------------------------- #
# invalid account name → exit 2 (ValueError from calendar_auth)
# --------------------------------------------------------------------------- #


def test_invalid_account_name_exit_2(helper, recorder, monkeypatch, capsys):
    def _raise(*a: Any, **k: Any):
        raise ValueError("invalid account name '../etc'")

    monkeypatch.setattr(helper, "load_credentials", _raise)
    code = run(
        helper,
        ["list", "--account", "../etc", "--from", "F", "--to", "T"],
    )
    assert code == 2
    assert recorder.calls == []
    assert "invalid account name" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# no subcommand → usage error
# --------------------------------------------------------------------------- #


def test_no_subcommand_is_usage_error(helper, recorder, capsys):
    code = run(helper, [])
    assert code == 2


# --------------------------------------------------------------------------- #
# SUMMARY is always the final stdout line (parse-anchor invariant)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "argv, setup",
    [
        (["create", "--summary", "x", "--start", "2026-07-14T15:00:00-04:00",
          "--end", "2026-07-14T16:00:00-04:00", "--json"],
         {"insert": {"id": "e"}}),
        (["list", "--from", "F", "--to", "T", "--json"], {"list": {"items": []}}),
    ],
)
def test_summary_is_final_line(helper, recorder, capsys, argv, setup):
    recorder.outcomes.update(setup)
    run(helper, argv)
    assert _last_line(capsys).startswith("SUMMARY:")


# --------------------------------------------------------------------------- #
# Body-mapping unit branches (helpers)
# --------------------------------------------------------------------------- #


def test_parse_attendees_accepts_list_form(helper):
    assert helper._parse_attendees(["a@x.com", " b@y.com "]) == [
        {"email": "a@x.com"},
        {"email": "b@y.com"},
    ]
    assert helper._parse_attendees(None) == []


def test_time_field_without_timezone(helper):
    assert helper._time_field("2026-07-14T15:00:00-04:00", None) == {
        "dateTime": "2026-07-14T15:00:00-04:00"
    }


def test_clear_fields_ignores_empty_tokens(helper):
    # Trailing/duplicate commas produce empty tokens that must be skipped;
    # aliases collapse to the same Google field once.
    assert helper._clear_fields("location, ,rrule,recurrence") == [
        "location",
        "recurrence",
    ]
    assert helper._clear_fields(None) == []


def test_http_status_non_integer_returns_none(helper):
    exc = type("E", (Exception,), {})()
    exc.resp = types.SimpleNamespace(status="not-a-number")
    assert helper._http_status(exc) is None
    # No resp attribute at all → None.
    assert helper._http_status(Exception("x")) is None
