"""Tests for `scripts.inbox.route_calendar_event`.

The helper accepts a JSON `CalendarPayload` (`{title, start, end?, location?,
description?}`) at `--payload-file <abs-path>`. On valid: emits a normalized
payload JSON on stdout (default `end = start + 1h` when absent). On invalid:
emits `{"error": "invalid_payload", "missing": [...]}` on stderr.

Invocation form is `python3 -m scripts.inbox.route_calendar_event` per
NFR-004 and `[[feedback_helper_m_invocation_form]]`. Tests drive `main()`
directly rather than spawning subprocesses, which is the existing
`tests/inbox/` convention and keeps coverage measurement honest.

Design-time note: the WP prompt assumed
`scripts.calendar_routing.validate_calendar_event.validate_payload(payload)
-> (is_valid, missing)`. The actual `validate_calendar_event` module exposes
`validate(block)` over a different input shape (an `ExtractedCalendarBlock`
with `start_natural`, `tick_iso`, etc.) — that validator is for extracting
natural-language fields, not for validating an already-structured
`CalendarPayload`. We document the gap and inline a small validator here
that matches the WP's stated test contract.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.inbox import route_calendar_event as helper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_payload(tmp_path: Path, payload: dict | list | str, name: str = "payload.json") -> Path:
    """Write a payload to a tempfile and return its absolute path."""
    target = tmp_path / name
    if isinstance(payload, str):
        # Caller wants raw bytes (e.g., to inject malformed JSON).
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    """Drive `helper.main(argv)`; return (exit_code, stdout, stderr)."""
    code = helper.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# Normalization (unit tests for the pure functions)
# ---------------------------------------------------------------------------


class TestNormalizePayload:
    def test_fills_in_end_when_absent(self):
        payload = {
            "title": "Sync with Rob",
            "start": "2026-06-12T15:00:00-04:00",
        }
        result = helper.normalize_payload(payload)
        assert result["end"] == "2026-06-12T16:00:00-04:00"
        # All other fields preserved.
        assert result["title"] == "Sync with Rob"
        assert result["start"] == "2026-06-12T15:00:00-04:00"

    def test_preserves_explicit_end(self):
        payload = {
            "title": "Long meeting",
            "start": "2026-06-12T15:00:00-04:00",
            "end": "2026-06-12T17:30:00-04:00",
        }
        result = helper.normalize_payload(payload)
        assert result["end"] == "2026-06-12T17:30:00-04:00"

    def test_preserves_optional_fields(self):
        payload = {
            "title": "Office hours",
            "start": "2026-06-12T15:00:00-04:00",
            "location": "Boston",
            "description": "Drop in",
        }
        result = helper.normalize_payload(payload)
        assert result["location"] == "Boston"
        assert result["description"] == "Drop in"
        # Default end is still computed.
        assert result["end"] == "2026-06-12T16:00:00-04:00"

    def test_utc_zulu_start_default_end(self):
        payload = {
            "title": "Sync",
            "start": "2026-06-12T15:00:00+00:00",
        }
        result = helper.normalize_payload(payload)
        # Default end preserves the same offset format.
        assert result["end"].startswith("2026-06-12T16:00:00")


# ---------------------------------------------------------------------------
# Validation (unit tests for the pure functions)
# ---------------------------------------------------------------------------


class TestValidatePayload:
    def test_valid_returns_empty_missing(self):
        payload = {
            "title": "Sync",
            "start": "2026-06-12T15:00:00-04:00",
        }
        is_valid, missing = helper.validate_payload(payload)
        assert is_valid is True
        assert missing == []

    def test_missing_title(self):
        payload = {"start": "2026-06-12T15:00:00-04:00"}
        is_valid, missing = helper.validate_payload(payload)
        assert is_valid is False
        assert "title" in missing

    def test_missing_start(self):
        payload = {"title": "Sync"}
        is_valid, missing = helper.validate_payload(payload)
        assert is_valid is False
        assert "start" in missing

    def test_blank_title_is_missing(self):
        payload = {"title": "   ", "start": "2026-06-12T15:00:00-04:00"}
        is_valid, missing = helper.validate_payload(payload)
        assert is_valid is False
        assert "title" in missing

    def test_unparseable_start_is_missing(self):
        payload = {"title": "Sync", "start": "next Tuesday at 3pm"}
        is_valid, missing = helper.validate_payload(payload)
        assert is_valid is False
        assert "start" in missing

    def test_unparseable_end_is_missing(self):
        payload = {
            "title": "Sync",
            "start": "2026-06-12T15:00:00-04:00",
            "end": "not a date",
        }
        is_valid, missing = helper.validate_payload(payload)
        assert is_valid is False
        assert "end" in missing

    def test_non_dict_payload(self):
        is_valid, missing = helper.validate_payload(["not", "a", "dict"])
        assert is_valid is False
        assert missing == ["payload_not_object"]

    def test_blank_start_is_missing(self):
        # Exercises the `if not text` branch in _parse_iso.
        payload = {"title": "Sync", "start": "   "}
        is_valid, missing = helper.validate_payload(payload)
        assert is_valid is False
        assert "start" in missing

    def test_zulu_start_is_accepted(self):
        # Exercises the `endswith("Z")` translation branch in _parse_iso.
        payload = {"title": "Sync", "start": "2026-06-12T15:00:00Z"}
        is_valid, missing = helper.validate_payload(payload)
        assert is_valid is True
        assert missing == []


# ---------------------------------------------------------------------------
# CLI surface (the contract the prompt and integrations consume)
# ---------------------------------------------------------------------------


class TestCli:
    def test_valid_payload_emits_normalized_json(self, tmp_path, capsys):
        payload = {
            "title": "Sync with Rob",
            "start": "2026-06-12T15:00:00-04:00",
        }
        path = _write_payload(tmp_path, payload)

        code, out, err = _run(["--payload-file", str(path)], capsys)

        assert code == 0
        assert err == ""
        emitted = json.loads(out)
        assert emitted["title"] == "Sync with Rob"
        assert emitted["start"] == "2026-06-12T15:00:00-04:00"
        assert emitted["end"] == "2026-06-12T16:00:00-04:00"

    def test_valid_payload_with_end_passes_through(self, tmp_path, capsys):
        payload = {
            "title": "Long meeting",
            "start": "2026-06-12T15:00:00-04:00",
            "end": "2026-06-12T17:30:00-04:00",
            "location": "Boston",
            "description": "Drop in",
        }
        path = _write_payload(tmp_path, payload)

        code, out, err = _run(["--payload-file", str(path)], capsys)

        assert code == 0
        emitted = json.loads(out)
        assert emitted["end"] == "2026-06-12T17:30:00-04:00"
        assert emitted["location"] == "Boston"
        assert emitted["description"] == "Drop in"

    def test_invalid_payload_emits_structured_error(self, tmp_path, capsys):
        payload = {"location": "Boston"}  # missing both title and start
        path = _write_payload(tmp_path, payload)

        code, out, err = _run(["--payload-file", str(path)], capsys)

        assert code == 1
        assert out == ""
        report = json.loads(err)
        assert report["error"] == "invalid_payload"
        assert "title" in report["missing"]
        assert "start" in report["missing"]

    def test_payload_file_missing_exits_1(self, tmp_path, capsys):
        absent = tmp_path / "absent.json"

        code, out, err = _run(["--payload-file", str(absent)], capsys)

        assert code == 1
        assert out == ""
        report = json.loads(err)
        assert report["error"] == "file_not_found"
        assert str(absent) in report["detail"]

    def test_payload_file_malformed_json_exits_1(self, tmp_path, capsys):
        path = _write_payload(tmp_path, "{ not json", name="bad.json")

        code, out, err = _run(["--payload-file", str(path)], capsys)

        assert code == 1
        assert out == ""
        report = json.loads(err)
        assert report["error"] == "malformed_json"

    def test_payload_file_top_level_not_object_exits_1(self, tmp_path, capsys):
        path = _write_payload(tmp_path, ["not", "a", "dict"], name="list.json")

        code, out, err = _run(["--payload-file", str(path)], capsys)

        assert code == 1
        report = json.loads(err)
        assert report["error"] == "invalid_payload"
        assert "payload_not_object" in report["missing"]

    def test_help_exits_0(self, capsys):
        # argparse calls sys.exit() on --help; capture that.
        with pytest.raises(SystemExit) as exc:
            helper.main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "--payload-file" in out

    def test_payload_file_flag_is_required(self, capsys):
        with pytest.raises(SystemExit) as exc:
            helper.main([])
        # argparse exits 2 when required args are missing.
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Delegation-envelope mode (#679 — route through felix-admin-calendar)
# ---------------------------------------------------------------------------


class TestBuildDelegationPayload:
    def test_maps_fields_and_defaults(self):
        normalized = {
            "title": "Tuesday trivia night",
            "start": "2026-06-09T18:00:00-04:00",
            "end": "2026-06-09T19:00:00-04:00",
            "location": "Tru West Brewery",
            "description": "Source note",
        }
        env = helper.build_delegation_payload(normalized, "/inbox/note.md")
        assert env["action"] == "create_calendar_event"
        assert env["calendar_id"] == "primary"
        # D5: default account flipped to the personal credential set.
        assert env["account"] == "personal"
        # renamed fields
        assert env["summary"] == "Tuesday trivia night"
        assert env["start_rfc3339"] == "2026-06-09T18:00:00-04:00"
        assert env["end_rfc3339"] == "2026-06-09T19:00:00-04:00"
        # passthrough optionals
        assert env["location"] == "Tru West Brewery"
        assert env["description"] == "Source note"
        # inbox-path nulls
        assert env["start_timezone"] is None
        assert env["rrule"] is None
        assert env["attendees"] is None
        assert env["clarification_id"] is None
        assert env["source_inbox_path"] == "/inbox/note.md"

    def test_optional_fields_default_null_when_absent(self):
        normalized = {
            "title": "Quick sync",
            "start": "2026-06-09T18:00:00-04:00",
            "end": "2026-06-09T19:00:00-04:00",
        }
        env = helper.build_delegation_payload(normalized, "/inbox/x.md")
        assert env["location"] is None
        assert env["description"] is None


class TestDelegationCLI:
    def test_emits_envelope_with_source_path(self, tmp_path, capsys):
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-06-12T15:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--as-delegation-payload", "--source-path", "/inbox/n.md"],
            capsys,
        )
        assert code == 0, err
        env = json.loads(out)
        assert env["action"] == "create_calendar_event"
        assert env["summary"] == "Sync"
        assert env["start_rfc3339"] == "2026-06-12T15:00:00-04:00"
        assert env["end_rfc3339"] == "2026-06-12T16:00:00-04:00"  # +1h default
        assert env["source_inbox_path"] == "/inbox/n.md"

    def test_requires_source_path(self, tmp_path, capsys):
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-06-12T15:00:00-04:00"})
        code, out, err = _run(["--payload-file", str(pf), "--as-delegation-payload"], capsys)
        assert code == 1
        assert "missing_source_path" in err
        assert out == ""

    def test_default_mode_unchanged(self, tmp_path, capsys):
        # Without the flag, the bare normalized payload is emitted (backward compat).
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-06-12T15:00:00-04:00"})
        code, out, err = _run(["--payload-file", str(pf)], capsys)
        assert code == 0, err
        result = json.loads(out)
        assert "action" not in result
        assert result["title"] == "Sync"
        assert result["end"] == "2026-06-12T16:00:00-04:00"


# ---------------------------------------------------------------------------
# Default account (D5): personal
# ---------------------------------------------------------------------------


def test_default_account_is_personal():
    """The routing helper's default credential-set selector is `personal`."""
    assert helper.DEFAULT_ACCOUNT == "personal"


# ---------------------------------------------------------------------------
# --create mode (D4 / #679): validate -> envelope -> helper subprocess
#
# The helper subprocess is MOCKED — the real calendar_helper needs the google
# client libraries + a live token, which never run under CI.
# ---------------------------------------------------------------------------


import subprocess  # noqa: E402


def _fake_completed(returncode: int, stdout: str = "", stderr: str = ""):
    """Build a subprocess.CompletedProcess stand-in for the mocked helper."""
    return subprocess.CompletedProcess(
        args=["calendar_helper"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestCreateMode:
    def test_created_emits_status_created(self, tmp_path, capsys, monkeypatch):
        """A complete payload -> helper success -> {status: created, ...}."""
        captured: dict = {}

        def fake_invoke(envelope, source_inbox_path, account):
            captured["envelope"] = envelope
            captured["source_inbox_path"] = source_inbox_path
            captured["account"] = account
            # The helper prints a JSON line then a SUMMARY line.
            stdout = (
                '{"status": "created", "idempotent": false, '
                '"event_id": "evt_abc123", "html_link": "https://cal/evt_abc123"}\n'
                "SUMMARY: op=create status=created event_id=evt_abc123\n"
            )
            return _fake_completed(0, stdout=stdout)

        monkeypatch.setattr(helper, "_invoke_calendar_helper", fake_invoke)

        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-06-12T15:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--create", "--source-path", "/inbox/n.md"],
            capsys,
        )

        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "created"
        assert result["event_id"] == "evt_abc123"
        assert result["html_link"] == "https://cal/evt_abc123"
        # The envelope handed to the helper carries account=personal (D5).
        assert captured["envelope"]["account"] == "personal"
        assert captured["envelope"]["action"] == "create_calendar_event"
        assert captured["account"] == "personal"
        assert captured["source_inbox_path"] == "/inbox/n.md"

    def test_needs_clarification_when_missing_fields(self, tmp_path, capsys, monkeypatch):
        """An invalid payload -> needs_clarification; the helper is NOT called."""
        called = {"invoked": False}

        def fake_invoke(envelope, source_inbox_path, account):  # pragma: no cover
            called["invoked"] = True
            return _fake_completed(0)

        monkeypatch.setattr(helper, "_invoke_calendar_helper", fake_invoke)

        # Missing `start`.
        pf = _write_payload(tmp_path, {"title": "Sync"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--create", "--source-path", "/inbox/n.md"],
            capsys,
        )

        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "needs_clarification"
        assert "start" in result["missing"]
        assert called["invoked"] is False

    def test_error_surfaced_verbatim_on_helper_failure(self, tmp_path, capsys, monkeypatch):
        """Helper exit 3 (auth) -> {status: error, ...}; error surfaced, never faked."""

        def fake_invoke(envelope, source_inbox_path, account):
            return _fake_completed(
                3,
                stdout="SUMMARY: op=create status=auth_failed account=personal\n",
                stderr="ERROR: auth_failed invalid_grant\n",
            )

        monkeypatch.setattr(helper, "_invoke_calendar_helper", fake_invoke)

        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-06-12T15:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--create", "--source-path", "/inbox/n.md"],
            capsys,
        )

        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["exit_code"] == 3
        assert "auth_failed invalid_grant" in result["error"]
        # Must NOT fabricate an event_id / created status.
        assert "event_id" not in result

    def test_create_requires_source_path(self, tmp_path, capsys):
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-06-12T15:00:00-04:00"})
        code, out, err = _run(["--payload-file", str(pf), "--create"], capsys)
        assert code == 1
        assert "missing_source_path" in err
        assert out == ""

    def test_create_and_delegation_mutually_exclusive(self, tmp_path, capsys):
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-06-12T15:00:00-04:00"})
        code, out, err = _run(
            [
                "--payload-file", str(pf),
                "--create", "--as-delegation-payload",
                "--source-path", "/inbox/n.md",
            ],
            capsys,
        )
        assert code == 1
        assert "mutually_exclusive" in err

    def test_create_non_object_payload_needs_clarification(self, tmp_path, capsys, monkeypatch):
        """A top-level non-object under --create is a needs_clarification result."""

        def fake_invoke(envelope, source_inbox_path, account):  # pragma: no cover
            raise AssertionError("helper must not be called for a non-object payload")

        monkeypatch.setattr(helper, "_invoke_calendar_helper", fake_invoke)

        pf = _write_payload(tmp_path, ["not", "a", "dict"], name="list.json")
        code, out, err = _run(
            ["--payload-file", str(pf), "--create", "--source-path", "/inbox/n.md"],
            capsys,
        )
        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "needs_clarification"
        assert "payload_not_object" in result["missing"]

    def test_create_success_uses_source_path_as_idempotency_key(self, tmp_path, monkeypatch):
        """The real _invoke passes source_inbox_path as --idempotency-key."""
        recorded: dict = {}

        def fake_run(cmd, **kwargs):
            recorded["cmd"] = cmd
            return _fake_completed(
                0,
                stdout='{"status": "created", "event_id": "e1", "html_link": "h1"}\n'
                "SUMMARY: op=create status=created\n",
            )

        monkeypatch.setattr(helper.subprocess, "run", fake_run)

        env = {"action": "create_calendar_event", "account": "personal"}
        proc = helper._invoke_calendar_helper(env, "/inbox/n.md", "personal")
        assert proc.returncode == 0
        cmd = recorded["cmd"]
        assert "--idempotency-key" in cmd
        assert cmd[cmd.index("--idempotency-key") + 1] == "/inbox/n.md"
        assert "--account" in cmd
        assert cmd[cmd.index("--account") + 1] == "personal"
        assert "-m" in cmd
        assert helper.CALENDAR_HELPER_MODULE in cmd
        # Interpreter MUST be the dedicated venv python (the only one with the
        # google libs on office2), NOT sys.executable — regression guard for the
        # post-merge CRITICAL: capture runs this module under system python3.
        assert cmd[0] == helper.DEFAULT_CALENDAR_HELPER_PYTHON
        assert cmd[0] != sys.executable

    def test_calendar_helper_python_default_and_override(self, monkeypatch):
        """The helper interpreter defaults to the office2 venv, overridable by env."""
        monkeypatch.delenv("FELIX_CALENDAR_HELPER_PYTHON", raising=False)
        assert (
            helper._calendar_helper_python()
            == "/data/services/openclaw/felix-calendar/venv/bin/python"
        )
        monkeypatch.setenv("FELIX_CALENDAR_HELPER_PYTHON", "/tmp/venv/bin/python")
        assert helper._calendar_helper_python() == "/tmp/venv/bin/python"


# ---------------------------------------------------------------------------
# --finalize mode (#737/#738/#657): atomic create -> verify -> mark -> log
#
# _invoke_calendar_helper (create) and _invoke_mark_processed (subprocess) are
# MOCKED; the routing log is redirected to a tmp file.
# ---------------------------------------------------------------------------


from scripts.inbox import routing_log as _routing_log  # noqa: E402


def _created_stdout(event_id="evt_1", html="https://cal/evt_1", idempotent=False):
    return (
        f'{{"status": "created", "idempotent": {str(idempotent).lower()}, '
        f'"event_id": "{event_id}", "html_link": "{html}"}}\n'
        "SUMMARY: op=create status=created\n"
    )


class TestFinalizeMode:
    def _redirect_log(self, tmp_path, monkeypatch):
        log = tmp_path / "routing.jsonl"
        monkeypatch.setattr(_routing_log, "DEFAULT_ROUTING_LOG_PATH", log)
        return log

    def test_finalize_success_marks_and_logs(self, tmp_path, capsys, monkeypatch):
        log = self._redirect_log(tmp_path, monkeypatch)
        monkeypatch.setattr(
            helper, "_invoke_calendar_helper",
            lambda *a, **k: _fake_completed(0, stdout=_created_stdout()),
        )
        marked = {"called_with": None}

        def fake_mark(source_path):
            marked["called_with"] = source_path
            return _fake_completed(0, stdout='{"finalized": true, "status": "processed"}\n')

        monkeypatch.setattr(helper, "_invoke_mark_processed", fake_mark)

        pf = _write_payload(tmp_path, {"title": "Emanuel call", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--source-path", "/inbox/Note 1.md"],
            capsys,
        )
        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "finalized"
        assert result["event_id"] == "evt_1"
        assert result["marked_processed"] is True
        assert result["routing_logged"] is True
        # mark_processed was invoked with the raw source path.
        assert marked["called_with"] == "/inbox/Note 1.md"
        # A calendar routing-log row was written (basename key, kind, destination).
        rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["filename"] == "Note 1.md"
        assert rows[0]["kind"] == "calendar"
        assert rows[0]["destination"] == "evt_1"

    def test_finalize_idempotent_hit_still_finalizes(self, tmp_path, capsys, monkeypatch):
        self._redirect_log(tmp_path, monkeypatch)
        monkeypatch.setattr(
            helper, "_invoke_calendar_helper",
            lambda *a, **k: _fake_completed(0, stdout=_created_stdout(idempotent=True)),
        )
        monkeypatch.setattr(helper, "_invoke_mark_processed", lambda p: _fake_completed(0))
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--source-path", "/inbox/n.md"], capsys
        )
        assert code == 0, err
        assert json.loads(out)["status"] == "finalized"

    def test_finalize_create_error_does_not_mark_or_log(self, tmp_path, capsys, monkeypatch):
        log = self._redirect_log(tmp_path, monkeypatch)
        monkeypatch.setattr(
            helper, "_invoke_calendar_helper",
            lambda *a, **k: _fake_completed(3, stderr="ERROR: auth_failed invalid_grant\n"),
        )

        def fake_mark(source_path):  # pragma: no cover - must NOT be called
            raise AssertionError("mark_processed must not run when create fails")

        monkeypatch.setattr(helper, "_invoke_mark_processed", fake_mark)
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--source-path", "/inbox/n.md"], capsys
        )
        assert code == 1, "create failure must be a NON-zero exit (fail-loud)"
        result = json.loads(out)
        assert result["status"] == "error"
        assert "auth_failed invalid_grant" in result["error"]
        assert not log.exists() or log.read_text().strip() == ""

    def test_finalize_needs_clarification_not_finalized(self, tmp_path, capsys, monkeypatch):
        self._redirect_log(tmp_path, monkeypatch)

        def fake_invoke(*a, **k):  # pragma: no cover - not called for invalid payload
            raise AssertionError("helper must not be called for an invalid payload")

        monkeypatch.setattr(helper, "_invoke_calendar_helper", fake_invoke)
        monkeypatch.setattr(helper, "_invoke_mark_processed", lambda p: _fake_completed(0))
        pf = _write_payload(tmp_path, {"title": "Sync"})  # missing start
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--source-path", "/inbox/n.md"], capsys
        )
        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "needs_clarification"
        assert "start" in result["missing"]

    def test_finalize_mark_failure_is_error_logged_but_not_marked(self, tmp_path, capsys, monkeypatch):
        # Under log-before-mark (#746 post-merge), the routing-log entry is
        # written BEFORE the mark. A mark failure therefore leaves the note
        # UNprocessed but the log row already present — both the log append and
        # the mark are idempotent, so the next tick completes cleanly.
        log = self._redirect_log(tmp_path, monkeypatch)
        monkeypatch.setattr(
            helper, "_invoke_calendar_helper",
            lambda *a, **k: _fake_completed(0, stdout=_created_stdout()),
        )
        monkeypatch.setattr(
            helper, "_invoke_mark_processed",
            lambda p: _fake_completed(3, stderr='{"error": "refused"}'),
        )
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--source-path", "/inbox/n.md"], capsys
        )
        assert code == 1, "mark_processed failure must be NON-zero (fail-loud)"
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["stage"] == "mark_processed"
        assert result["event_id"] == "evt_1"  # the event DID get created — surface it
        assert result.get("marked_processed") is not True  # note left unprocessed
        # routing log IS written (log-before-mark) — a calendar row for the note.
        rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        assert len(rows) == 1 and rows[0]["kind"] == "calendar"

    def test_finalize_routing_log_failure_is_error_and_not_marked(self, tmp_path, capsys, monkeypatch):
        # #746 post-merge fix (log-before-mark): a routing-log write failure is
        # surfaced loudly as an error (non-zero exit) AND the note is left
        # UNprocessed — `mark_processed` must NOT run when the log write fails, so
        # the #746 health rail never sees a `processed`-without-routing-log note.
        # The event IS created (create key dedups it) but the note stays
        # unprocessed so the next idempotent tick completes the whole finalize.
        self._redirect_log(tmp_path, monkeypatch)
        monkeypatch.setattr(
            helper, "_invoke_calendar_helper",
            lambda *a, **k: _fake_completed(0, stdout=_created_stdout()),
        )

        def _mark_must_not_run(p):
            raise AssertionError(
                "mark_processed must NOT run when the routing-log write fails "
                "(log-before-mark)"
            )

        monkeypatch.setattr(helper, "_invoke_mark_processed", _mark_must_not_run)
        # Simulate a routing-log write failure.
        monkeypatch.setattr(helper, "_append_calendar_routing_log", lambda *a, **k: False)
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--source-path", "/inbox/n.md"], capsys
        )
        assert code == 1, "a routing-log failure must be a NON-zero exit (fail-loud)"
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["stage"] == "routing_log"
        assert result["event_id"] == "evt_1"  # the event DID get created — surface it
        assert result["marked_processed"] is False  # note left unprocessed

    def test_finalize_routing_log_is_idempotent(self, tmp_path, capsys, monkeypatch):
        log = self._redirect_log(tmp_path, monkeypatch)
        # Pre-seed an existing calendar row for this note.
        log.write_text(json.dumps({"filename": "n.md", "kind": "calendar", "destination": "old"}) + "\n")
        monkeypatch.setattr(
            helper, "_invoke_calendar_helper",
            lambda *a, **k: _fake_completed(0, stdout=_created_stdout()),
        )
        monkeypatch.setattr(helper, "_invoke_mark_processed", lambda p: _fake_completed(0))
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--source-path", "/inbox/n.md"], capsys
        )
        assert code == 0, err
        assert json.loads(out)["routing_logged"] is True
        # No duplicate row appended.
        rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        assert len(rows) == 1

    def test_finalize_dry_run_no_side_effects(self, tmp_path, capsys, monkeypatch):
        log = self._redirect_log(tmp_path, monkeypatch)

        def fake_invoke(*a, **k):  # pragma: no cover
            raise AssertionError("dry-run must not call the calendar helper")

        def fake_mark(p):  # pragma: no cover
            raise AssertionError("dry-run must not mark processed")

        monkeypatch.setattr(helper, "_invoke_calendar_helper", fake_invoke)
        monkeypatch.setattr(helper, "_invoke_mark_processed", fake_mark)
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--dry-run", "--source-path", "/inbox/n.md"],
            capsys,
        )
        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "dry_run"
        assert result["would_finalize"] is True
        assert result["envelope"]["summary"] == "Sync"
        assert not log.exists() or log.read_text().strip() == ""

    def test_finalize_dry_run_invalid_is_needs_clarification(self, tmp_path, capsys):
        pf = _write_payload(tmp_path, {"title": "Sync"})  # missing start
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--dry-run", "--source-path", "/inbox/n.md"],
            capsys,
        )
        assert code == 0, err
        assert json.loads(out)["status"] == "needs_clarification"

    def test_finalize_requires_source_path(self, tmp_path, capsys):
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(["--payload-file", str(pf), "--finalize"], capsys)
        assert code == 1
        assert "missing_source_path" in err

    def test_finalize_and_create_mutually_exclusive(self, tmp_path, capsys):
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--create", "--source-path", "/inbox/n.md"],
            capsys,
        )
        assert code == 1
        assert "mutually_exclusive" in err

    def test_dry_run_without_finalize_rejected(self, tmp_path, capsys):
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(["--payload-file", str(pf), "--dry-run"], capsys)
        assert code == 1
        assert "invalid_flag" in err


class TestSubprocessTimeouts:
    def test_calendar_helper_timeout_returns_nonzero(self, monkeypatch):
        import subprocess as _sp

        def raise_timeout(*a, **k):
            raise _sp.TimeoutExpired(cmd="calendar_helper", timeout=90)

        monkeypatch.setattr(helper.subprocess, "run", raise_timeout)
        proc = helper._invoke_calendar_helper({"a": 1}, "/inbox/n.md", "personal")
        assert proc.returncode == helper._TIMEOUT_RETURNCODE
        assert "timed out" in proc.stderr

    def test_mark_processed_timeout_returns_nonzero(self, monkeypatch):
        import subprocess as _sp

        def raise_timeout(*a, **k):
            raise _sp.TimeoutExpired(cmd="mark_processed", timeout=30)

        monkeypatch.setattr(helper.subprocess, "run", raise_timeout)
        proc = helper._invoke_mark_processed("/inbox/n.md")
        assert proc.returncode == helper._TIMEOUT_RETURNCODE
        assert "timed out" in proc.stderr

    def test_finalize_surfaces_helper_timeout_as_error(self, tmp_path, capsys, monkeypatch):
        import subprocess as _sp

        # subprocess.run raises TimeoutExpired -> _invoke_calendar_helper catches
        # it and returns rc=124 -> _run_create -> error -> _run_finalize exit 1.
        monkeypatch.setattr(
            helper.subprocess, "run",
            lambda *a, **k: (_ for _ in ()).throw(_sp.TimeoutExpired("x", 90)),
        )
        pf = _write_payload(tmp_path, {"title": "Sync", "start": "2026-07-16T12:00:00-04:00"})
        code, out, err = _run(
            ["--payload-file", str(pf), "--finalize", "--source-path", "/inbox/n.md"], capsys
        )
        assert code == 1
        assert json.loads(out)["status"] == "error"
