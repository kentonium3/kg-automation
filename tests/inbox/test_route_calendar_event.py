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

import io
import json
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
        assert env["account"] == "kent@intentional.biz"
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
