"""Tests for ``scripts.escalation.record_completion`` (Phase 6 / WP03).

Coverage targets per WP03 § Validation:

- Three-write ordering verified by mock call-sequence assertions
  (Vikunja-then-JSONL, never the reverse).
- Every event_type happy path (level_sent, snoozed, dismissed, done,
  rescheduled).
- ``snooze_until`` computed at write-time in America/New_York TZ (FR-004),
  verified by monkeypatching ``_today_local``.
- Vikunja step failure -> no JSONL write.
- JSONL step failure -> Vikunja already committed (operator triage).
- Idempotency: pre-existing record short-circuits, both Vikunja AND JSONL.
- Schema validation: invalid record raises ``EscalationSchemaError`` before
  any side-effect.
- felix-bot identity (FR-010): Authorization header carries the token from
  the token file.
- v1 ``[Felix-Escalation]`` comment vocabulary (data-model Entity 3 reverse)
  roundtrip-able by the SKILL.md regex.
- CLI exit codes 0/1/2/3 per contracts/cli.md.

All HTTP traffic is mocked via the ``mock_urlopen`` fixture from
``tests/escalation/conftest.py``. JSONL writes land under
``tmp_path/state/escalation`` via the ``JSONL_STATE_DIR`` monkeypatch fixture
defined locally below.
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.escalation import record_completion as rc
from scripts.escalation.record_completion import (
    EscalationSchemaError,
    StateLogError,
    VikunjaError,
    _compute_snooze_until,
    _format_v1_comment,
    idempotent_record_event,
    main,
    record_event,
)


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def jsonl_sandbox(tmp_path: Path, monkeypatch) -> Path:
    """Redirect ``JSONL_STATE_DIR`` to a tmp directory for the test.

    Returns the directory path. Creating it eagerly mirrors how the helper
    will create the parent in production.
    """
    sandbox = tmp_path / "escalation_state"
    sandbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rc, "JSONL_STATE_DIR", sandbox)
    return sandbox


@pytest.fixture
def freeze_today(monkeypatch):
    """Return a callable that pins ``_today_local`` to the given date."""

    def _freeze(today: date) -> None:
        monkeypatch.setattr(rc, "_today_local", lambda: today)

    return _freeze


def _resp(payload, *, status: int = 200):
    """Build a context-manager-shaped fake urlopen response."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock(name="response")
    resp.status = status
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _http_error(code: int = 500, body: bytes = b'{"message":"boom"}'):
    return urllib.error.HTTPError(
        url="http://test/", code=code, msg="boom",
        hdrs=None, fp=io.BytesIO(body),
    )


def _read_jsonl(path: Path) -> list[dict]:
    """Return the parsed JSONL records at ``path``, or [] if not present."""
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# Group 1 — Happy path per event_type (with three-write ordering)
# ---------------------------------------------------------------------------


class TestHappyPathPerEventType:
    def test_record_level_sent_writes_comment_then_jsonl(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """Level 1 sent: PUT comment FIRST, then JSONL append.

        Verifies the three-write ordering invariant (research D6) via the
        mock call sequence -- urlopen MUST be called before the JSONL file
        gains a line.
        """
        record = make_jsonl_record(state="level_sent", level=1)
        jsonl_path = jsonl_sandbox / "project-4-escalation-history.jsonl"

        # Sanity: JSONL doesn't exist before the call.
        assert not jsonl_path.exists()

        # Use a side_effect spy on urlopen that captures the JSONL state at
        # the moment Vikunja is contacted: it MUST be absent then.
        observed_during_vikunja: list[bool] = []
        canned = [_resp({"id": 999, "comment": "[Felix-Escalation] ..."})]

        def _side_effect(*args, **kwargs):
            observed_during_vikunja.append(jsonl_path.exists())
            return canned.pop(0)

        mock_urlopen.side_effect = _side_effect

        result = record_event(record, token_path=tmp_token_file)

        assert result["ok"] is True
        assert result["deduped"] is False
        assert result["vikunja_actions"] == ["comment_PUT"]
        assert observed_during_vikunja == [False], (
            "JSONL was written BEFORE Vikunja was called; three-write "
            "ordering violated (research D6)"
        )
        records = _read_jsonl(jsonl_path)
        assert len(records) == 1
        assert records[0]["state"] == "level_sent"
        assert records[0]["level"] == 1

    def test_record_done_patches_task_then_comments(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """`done` path issues PATCH /tasks/{id} (done=true) BEFORE the comment PUT."""
        mock_urlopen.side_effect = [
            _resp({"id": 1234, "done": True}),
            _resp({"id": 5000, "comment": "[Felix-Escalation] ..."}),
        ]
        record = make_jsonl_record(state="done", source="kent_reply")
        record_event(record, token_path=tmp_token_file)

        assert mock_urlopen.call_count == 2

        first_req = mock_urlopen.call_args_list[0][0][0]
        assert first_req.get_method() == "PATCH"
        assert first_req.full_url.endswith("/tasks/1234")
        assert json.loads(first_req.data.decode("utf-8")) == {"done": True}

        second_req = mock_urlopen.call_args_list[1][0][0]
        assert second_req.get_method() == "PUT"
        assert second_req.full_url.endswith("/tasks/1234/comments")

    def test_record_rescheduled_patches_due_date_then_comments(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """`rescheduled` path PATCHes due_date BEFORE the comment PUT."""
        mock_urlopen.side_effect = [
            _resp({"id": 1234, "due_date": "2026-06-15T00:00:00Z"}),
            _resp({"id": 5001}),
        ]
        record = make_jsonl_record(
            state="rescheduled",
            source="kent_reply",
            reschedule_to="2026-06-15",
        )
        record_event(record, token_path=tmp_token_file)

        first_req = mock_urlopen.call_args_list[0][0][0]
        assert first_req.get_method() == "PATCH"
        assert first_req.full_url.endswith("/tasks/1234")
        body = json.loads(first_req.data.decode("utf-8"))
        assert body == {"due_date": "2026-06-15T00:00:00Z"}

        second_req = mock_urlopen.call_args_list[1][0][0]
        assert second_req.get_method() == "PUT"
        assert second_req.full_url.endswith("/tasks/1234/comments")

    def test_record_snoozed_computes_snooze_until_at_write_time(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
        freeze_today,
    ):
        """``snooze_until = today + snooze_days`` in America/New_York TZ.

        FR-004: write-time clock is authoritative. We freeze ``_today_local``
        and confirm the persisted JSONL carries the deterministic value.
        """
        freeze_today(date(2026, 5, 21))
        mock_urlopen.side_effect = [_resp({"id": 5002})]

        # The record arrives without snooze_until (CLI computes it). We
        # invoke the CLI surface via flag-driven path to exercise the
        # compute path.
        from io import StringIO

        # Use main() to exercise the CLI compute step.
        # First, build a stdin record WITHOUT snooze_until so the CLI
        # has to compute it.
        stdin_record = {
            "domain": "escalation",
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "snoozed",
            "source": "kent_reply",
            "snooze_days": 3,
        }
        buf = StringIO(json.dumps(stdin_record))
        buf.isatty = lambda: False  # type: ignore[assignment]
        # monkeypatch sys.stdin via the test's monkeypatch fixture would
        # be cleaner, but the simplest route is the direct attribute set.
        orig_stdin = sys.stdin
        sys.stdin = buf
        try:
            rc_code = main(
                [
                    "--token-path",
                    str(tmp_token_file),
                    "--base-url",
                    "http://test/api/v1/",
                ]
            )
        finally:
            sys.stdin = orig_stdin

        assert rc_code == 0
        records = _read_jsonl(
            jsonl_sandbox / "project-4-escalation-history.jsonl"
        )
        assert len(records) == 1
        # today=2026-05-21 + 3d = 2026-05-24
        assert records[0]["snooze_until"] == "2026-05-24"
        assert records[0]["snooze_days"] == 3

    def test_record_dismissed_writes_comment_only(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """`dismissed` path performs ONE PUT (comment) -- no PATCH."""
        mock_urlopen.side_effect = [_resp({"id": 5003})]
        record = make_jsonl_record(state="dismissed", source="kent_reply")
        result = record_event(record, token_path=tmp_token_file)

        assert mock_urlopen.call_count == 1
        only_req = mock_urlopen.call_args_list[0][0][0]
        assert only_req.get_method() == "PUT"
        assert only_req.full_url.endswith("/tasks/1234/comments")
        assert result["vikunja_actions"] == ["comment_PUT"]

    def test_skip_vikunja_writes_only_jsonl(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """``skip_vikunja=True`` reconcile path: no HTTP calls, JSONL only."""
        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called when skip_vikunja=True"
        )
        record = make_jsonl_record(
            state="done", source="reconcile",
        )
        result = record_event(
            record, token_path=tmp_token_file, skip_vikunja=True
        )
        assert mock_urlopen.call_count == 0
        assert result["vikunja_actions"] == []
        records = _read_jsonl(
            jsonl_sandbox / "project-4-escalation-history.jsonl"
        )
        assert len(records) == 1


# ---------------------------------------------------------------------------
# Group 2 — Three-write ordering invariant (research D6)
# ---------------------------------------------------------------------------


class TestThreeWriteOrdering:
    def test_vikunja_failure_no_jsonl_write(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """If Vikunja raises, the JSONL file MUST NOT gain a line."""
        mock_urlopen.side_effect = urllib.error.URLError("network down")
        record = make_jsonl_record(state="level_sent", level=1)
        with pytest.raises(VikunjaError, match="network failure"):
            record_event(record, token_path=tmp_token_file)
        # JSONL is absent.
        path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        assert not path.exists() or _read_jsonl(path) == []

    def test_jsonl_failure_after_vikunja_commit_raises_state_log_error(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
        monkeypatch,
    ):
        """Vikunja succeeds, JSONL append raises -> StateLogError (exit 2 in CLI).

        Asserts (a) StateLogError raised, (b) Vikunja PUT was called once
        (i.e., the side-effect committed before the failure).
        """
        mock_urlopen.side_effect = [_resp({"id": 6000})]

        def _boom(_record: dict) -> Path:
            raise StateLogError("simulated disk full")

        monkeypatch.setattr(rc, "_append_jsonl", _boom)

        record = make_jsonl_record(state="level_sent", level=1)
        with pytest.raises(StateLogError, match="simulated disk full"):
            record_event(record, token_path=tmp_token_file)
        assert mock_urlopen.call_count == 1

    def test_vikunja_http_error_no_jsonl_write(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """HTTP 5xx from Vikunja -> VikunjaError; no JSONL line written."""
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')
        record = make_jsonl_record(state="level_sent", level=1)
        with pytest.raises(VikunjaError, match="HTTP 503"):
            record_event(record, token_path=tmp_token_file)
        path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        assert not path.exists() or _read_jsonl(path) == []


# ---------------------------------------------------------------------------
# Group 3 — Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_idempotent_record_event_no_op_on_duplicate(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """Pre-existing match -> NO Vikunja calls AND no new JSONL line."""
        record = make_jsonl_record(state="level_sent", level=1)
        path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        # Pre-seed the file with the exact (task_id, date, state) match.
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        # If Vikunja IS called, the test fails.
        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called when dedup detected"
        )
        result = idempotent_record_event(record, token_path=tmp_token_file)

        assert result["ok"] is True
        assert result["deduped"] is True
        assert result["vikunja_actions"] == []
        assert mock_urlopen.call_count == 0
        # JSONL still has exactly one record (no duplicate append).
        records = _read_jsonl(path)
        assert len(records) == 1

    def test_idempotent_record_event_writes_on_no_match(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """No existing match -> normal three-write flow runs."""
        mock_urlopen.side_effect = [_resp({"id": 6001})]
        record = make_jsonl_record(state="level_sent", level=1)
        result = idempotent_record_event(record, token_path=tmp_token_file)

        assert result["deduped"] is False
        assert mock_urlopen.call_count == 1
        records = _read_jsonl(
            jsonl_sandbox / "project-4-escalation-history.jsonl"
        )
        assert len(records) == 1

    def test_idempotent_record_event_validates_before_dedup(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """Malformed record must NOT short-circuit silently as dedup."""
        bad = make_jsonl_record(state="level_sent")
        # Missing required ``level`` -> EscalationSchemaError.
        bad.pop("level", None)
        with pytest.raises(EscalationSchemaError):
            idempotent_record_event(bad, token_path=tmp_token_file)
        assert mock_urlopen.call_count == 0


# ---------------------------------------------------------------------------
# Group 4 — Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_invalid_record_raises_schema_error_no_writes(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """Missing ``level`` on level_sent -> EscalationSchemaError before any I/O."""
        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called on validation failure"
        )
        bad = make_jsonl_record(state="level_sent")
        bad.pop("level", None)

        with pytest.raises(EscalationSchemaError, match="level"):
            record_event(bad, token_path=tmp_token_file)
        assert mock_urlopen.call_count == 0
        path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        assert not path.exists() or _read_jsonl(path) == []

    def test_invalid_shared_field_raises_schema_error(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """Phase 2 shared validator failure surfaces as EscalationSchemaError."""
        mock_urlopen.side_effect = AssertionError("must not be called")
        bad = make_jsonl_record(state="level_sent", level=1)
        bad["date"] = "5/21/2026"  # invalid shape

        with pytest.raises(EscalationSchemaError):
            record_event(bad, token_path=tmp_token_file)


# ---------------------------------------------------------------------------
# Group 5 — felix-bot identity (FR-010)
# ---------------------------------------------------------------------------


class TestFelixBotIdentity:
    def test_request_uses_felix_bot_token(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        fake_vikunja_token,
        make_jsonl_record,
    ):
        """Authorization header MUST be ``Bearer <token>`` from the token file."""
        mock_urlopen.side_effect = [_resp({"id": 7001})]
        record = make_jsonl_record(state="level_sent", level=1)
        record_event(record, token_path=tmp_token_file)

        first_req = mock_urlopen.call_args_list[0][0][0]
        # urllib normalizes header capitalization.
        assert first_req.headers.get("Authorization") == (
            f"Bearer {fake_vikunja_token}"
        )


# ---------------------------------------------------------------------------
# Group 6 — v1 comment vocabulary (data-model Entity 3 reverse)
# ---------------------------------------------------------------------------


# SKILL.md § 3 parsing regex (the v1 surface this comment must roundtrip).
SKILL_COMMENT_RE = re.compile(
    r"^\[Felix-Escalation\] (?P<date>\d{4}-\d{2}-\d{2}) "
    r"\| (?P<state_token>"
    r"level-[12]|snoozed:\d+d|dismissed|done|rescheduled:\d{4}-\d{2}-\d{2}"
    r") \| (?P<disposition>sent|acknowledged)$"
)


class TestV1CommentFormat:
    def test_comment_format_level_1_sent(self, make_jsonl_record):
        record = make_jsonl_record(state="level_sent", level=1)
        comment = _format_v1_comment(record)
        assert comment == (
            "[Felix-Escalation] 2026-05-21 | level-1 | sent"
        )
        assert SKILL_COMMENT_RE.match(comment) is not None

    def test_comment_format_level_2_sent(self, make_jsonl_record):
        record = make_jsonl_record(state="level_sent", level=2)
        comment = _format_v1_comment(record)
        assert comment == (
            "[Felix-Escalation] 2026-05-21 | level-2 | sent"
        )
        assert SKILL_COMMENT_RE.match(comment) is not None

    def test_comment_format_snoozed_3d(self, make_jsonl_record):
        record = make_jsonl_record(
            state="snoozed",
            source="kent_reply",
            snooze_days=3,
            snooze_until="2026-05-24",
        )
        comment = _format_v1_comment(record)
        assert comment == (
            "[Felix-Escalation] 2026-05-21 | snoozed:3d | acknowledged"
        )
        assert SKILL_COMMENT_RE.match(comment) is not None

    def test_comment_format_dismissed(self, make_jsonl_record):
        record = make_jsonl_record(state="dismissed", source="kent_reply")
        comment = _format_v1_comment(record)
        assert comment == (
            "[Felix-Escalation] 2026-05-21 | dismissed | acknowledged"
        )
        assert SKILL_COMMENT_RE.match(comment) is not None

    def test_comment_format_done(self, make_jsonl_record):
        record = make_jsonl_record(state="done", source="kent_reply")
        comment = _format_v1_comment(record)
        assert comment == (
            "[Felix-Escalation] 2026-05-21 | done | acknowledged"
        )
        assert SKILL_COMMENT_RE.match(comment) is not None

    def test_comment_format_rescheduled(self, make_jsonl_record):
        record = make_jsonl_record(
            state="rescheduled",
            source="kent_reply",
            reschedule_to="2026-06-15",
        )
        comment = _format_v1_comment(record)
        assert comment == (
            "[Felix-Escalation] 2026-05-21 | rescheduled:2026-06-15 "
            "| acknowledged"
        )
        assert SKILL_COMMENT_RE.match(comment) is not None

    def test_comment_body_round_trips_through_actual_put(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """The body PUT to /comments matches the SKILL.md vocabulary."""
        mock_urlopen.side_effect = [_resp({"id": 8001})]
        record = make_jsonl_record(state="snoozed",
                                   source="kent_reply",
                                   snooze_days=2,
                                   snooze_until="2026-05-23")
        record_event(record, token_path=tmp_token_file)
        req = mock_urlopen.call_args_list[0][0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert "comment" in body
        assert SKILL_COMMENT_RE.match(body["comment"]) is not None


# ---------------------------------------------------------------------------
# Group 7 — snooze_until compute helper
# ---------------------------------------------------------------------------


class TestSnoozeUntilCompute:
    def test_basic_arithmetic(self, freeze_today):
        freeze_today(date(2026, 5, 21))
        assert _compute_snooze_until(1) == "2026-05-22"
        assert _compute_snooze_until(7) == "2026-05-28"
        assert _compute_snooze_until(30) == "2026-06-20"

    def test_rejects_non_positive(self):
        with pytest.raises(ValueError, match="positive integer"):
            _compute_snooze_until(0)
        with pytest.raises(ValueError, match="positive integer"):
            _compute_snooze_until(-3)

    def test_rejects_bool(self):
        with pytest.raises(ValueError):
            _compute_snooze_until(True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Group 8 — CLI
# ---------------------------------------------------------------------------


def _patch_stdin(monkeypatch, payload: str | None) -> None:
    """Replace sys.stdin with a StringIO containing ``payload``.

    Also stubs ``isatty()`` to False so the CLI treats the stream as piped.
    """
    if payload is None:
        fake = MagicMock(name="fake-tty-stdin")
        fake.isatty = MagicMock(return_value=True)
        fake.read = MagicMock(return_value="")
        monkeypatch.setattr(sys, "stdin", fake)
        return
    buf = io.StringIO(payload)
    buf.isatty = lambda: False  # type: ignore[assignment]
    monkeypatch.setattr(sys, "stdin", buf)


class TestCli:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "record_completion" in captured.out or "usage" in captured.out

    def test_cli_exit_code_0_on_success_stdin(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        """Happy stdin invocation -> exit 0 + stdout has ``"ok": true``."""
        mock_urlopen.side_effect = [_resp({"id": 9001})]
        payload = json.dumps({
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "level_sent",
            "source": "agent",
            "level": 1,
        })
        _patch_stdin(monkeypatch, payload)
        rc_code = main([
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 0
        out = capsys.readouterr().out
        assert json.loads(out)["ok"] is True

    def test_cli_exit_code_0_on_success_flags(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        monkeypatch,
    ):
        mock_urlopen.side_effect = [_resp({"id": 9002})]
        _patch_stdin(monkeypatch, None)
        rc_code = main([
            "--task-id", "1234",
            "--project-id", "4",
            "--title", "Task",
            "--date", "2026-05-21",
            "--state", "level_sent",
            "--level", "1",
            "--source", "agent",
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 0

    def test_cli_exit_code_3_on_missing_required(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        """Missing --level for --state level_sent -> exit 3 + stderr error."""
        mock_urlopen.side_effect = AssertionError("must not be called")
        _patch_stdin(monkeypatch, None)
        rc_code = main([
            "--task-id", "1234",
            "--project-id", "4",
            "--title", "Task",
            "--date", "2026-05-21",
            "--state", "level_sent",
            # Missing --level
            "--source", "agent",
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "--level" in err

    def test_cli_exit_code_3_on_malformed_stdin(
        self,
        mock_urlopen,
        tmp_token_file,
        monkeypatch,
        capsys,
        jsonl_sandbox,
    ):
        mock_urlopen.side_effect = AssertionError("must not be called")
        _patch_stdin(monkeypatch, "{not json")
        rc_code = main([
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 3

    def test_cli_exit_code_3_on_validation_failure(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        """Bad ``state`` via stdin (bypasses argparse choices) -> exit 3."""
        mock_urlopen.side_effect = AssertionError("must not be called")
        payload = json.dumps({
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "Levl_sent",  # typo
            "source": "agent",
            "level": 1,
        })
        _patch_stdin(monkeypatch, payload)
        rc_code = main([
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "validation" in err or "Levl_sent" in err

    def test_cli_exit_code_1_on_vikunja_failure(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        """Vikunja HTTP failure -> exit 1; stderr names ``vikunja`` step."""
        mock_urlopen.side_effect = _http_error(500, b'{"message":"down"}')
        payload = json.dumps({
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "level_sent",
            "source": "agent",
            "level": 1,
        })
        _patch_stdin(monkeypatch, payload)
        rc_code = main([
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 1
        err = capsys.readouterr().err
        assert "vikunja" in err

    def test_cli_exit_code_2_on_state_log_failure(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        """JSONL append failure after Vikunja commit -> exit 2."""
        mock_urlopen.side_effect = [_resp({"id": 9003})]

        def _boom(_record):
            raise StateLogError("disk full")

        monkeypatch.setattr(rc, "_append_jsonl", _boom)
        payload = json.dumps({
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "level_sent",
            "source": "agent",
            "level": 1,
        })
        _patch_stdin(monkeypatch, payload)
        rc_code = main([
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 2
        err = capsys.readouterr().err
        assert "state_log" in err

    def test_cli_exit_code_3_on_missing_token_file(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        mock_urlopen.side_effect = AssertionError("must not be called")
        payload = json.dumps({
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "level_sent",
            "source": "agent",
            "level": 1,
        })
        _patch_stdin(monkeypatch, payload)
        missing = tmp_path / "nope" / "token"
        rc_code = main([
            "--token-path", str(missing),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "Token file not found" in err

    def test_cli_exit_3_on_invalid_state_flag(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        """Invalid ``--state`` enum -> exit 3 (not argparse's default 2).

        contracts/cli.md exit code 3 covers "bad state value". The CLI must
        remap argparse usage errors (which default to ``SystemExit(2)``) to
        exit ``3`` with a structured stderr line.
        """
        mock_urlopen.side_effect = AssertionError("must not be called")
        _patch_stdin(monkeypatch, None)
        rc_code = main([
            "--task-id", "1",
            "--project-id", "1",
            "--title", "T",
            "--date", "2026-05-21",
            "--state", "bogus",
            "--source", "agent",
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        # Structured stderr line names the ``argparse`` step.
        assert "argparse" in err
        assert "bogus" in err or "invalid choice" in err

    def test_cli_exit_3_on_empty_token_file(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Empty token file -> exit 3 (was uncaught ValueError pre-fix)."""
        mock_urlopen.side_effect = AssertionError("must not be called")
        empty_token = tmp_path / "empty_token"
        empty_token.write_text("", encoding="utf-8")
        payload = json.dumps({
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "level_sent",
            "source": "agent",
            "level": 1,
        })
        _patch_stdin(monkeypatch, payload)
        rc_code = main([
            "--token-path", str(empty_token),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "token_load" in err
        assert "empty" in err.lower()

    def test_cli_exit_3_on_token_file_with_whitespace_only(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Whitespace-only token file -> exit 3 (strip yields empty)."""
        mock_urlopen.side_effect = AssertionError("must not be called")
        ws_token = tmp_path / "ws_token"
        ws_token.write_text("   \n\t  \n", encoding="utf-8")
        payload = json.dumps({
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "level_sent",
            "source": "agent",
            "level": 1,
        })
        _patch_stdin(monkeypatch, payload)
        rc_code = main([
            "--token-path", str(ws_token),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "token_load" in err

    def test_cli_idempotent_flag_dedups(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        """``--idempotent`` flag short-circuits when a match exists."""
        # Pre-seed the JSONL.
        prior = {
            "domain": "escalation",
            "task_id": 1234,
            "title": "Task",
            "date": "2026-05-21",
            "state": "level_sent",
            "source": "agent",
            "timestamp": "2026-05-21T12:00:00+00:00",
            "note": None,
            "project_id": 4,
            "level": 1,
        }
        path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        path.write_text(json.dumps(prior) + "\n", encoding="utf-8")

        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called on dedup"
        )
        payload = json.dumps({
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "level_sent",
            "source": "agent",
            "level": 1,
        })
        _patch_stdin(monkeypatch, payload)
        rc_code = main([
            "--idempotent",
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 0
        out = capsys.readouterr().out
        assert json.loads(out)["deduped"] is True

    def test_cli_no_vikunja_flag_skips_http(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        """``--no-vikunja`` (reconcile) writes JSONL without calling Vikunja."""
        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called when --no-vikunja"
        )
        payload = json.dumps({
            "task_id": 1234,
            "project_id": 4,
            "title": "Task",
            "date": "2026-05-21",
            "state": "done",
            "source": "reconcile",
        })
        _patch_stdin(monkeypatch, payload)
        rc_code = main([
            "--no-vikunja",
            "--token-path", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 0
        records = _read_jsonl(
            jsonl_sandbox / "project-4-escalation-history.jsonl"
        )
        assert len(records) == 1
        assert records[0]["state"] == "done"


# ---------------------------------------------------------------------------
# Group 9 — JSONL routing + atomicity helper
# ---------------------------------------------------------------------------


class TestJsonlRouting:
    def test_filename_keyed_on_project_id(self, jsonl_sandbox, make_jsonl_record):
        record = make_jsonl_record(project_id=7)
        path = rc._jsonl_path_for_record(record)
        assert path.name == "project-7-escalation-history.jsonl"
        assert path.parent == jsonl_sandbox

    def test_append_creates_parent_directory(
        self,
        mock_urlopen,
        tmp_path,
        tmp_token_file,
        make_jsonl_record,
        monkeypatch,
    ):
        """``_append_jsonl`` creates ``JSONL_STATE_DIR`` if absent."""
        nested = tmp_path / "deep" / "nested" / "state"
        monkeypatch.setattr(rc, "JSONL_STATE_DIR", nested)
        mock_urlopen.side_effect = [_resp({"id": 10001})]

        record = make_jsonl_record(state="level_sent", level=1)
        record_event(record, token_path=tmp_token_file)
        path = nested / "project-4-escalation-history.jsonl"
        assert path.exists()

    def test_append_idempotent_within_file(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """Calling record_event twice with same key writes only one line."""
        mock_urlopen.side_effect = [
            _resp({"id": 10002}),
            _resp({"id": 10003}),
        ]
        record = make_jsonl_record(state="level_sent", level=1)
        record_event(record, token_path=tmp_token_file)
        record_event(record, token_path=tmp_token_file)
        path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        records = _read_jsonl(path)
        assert len(records) == 1

    def test_append_tolerates_malformed_existing_lines(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """Malformed prior lines do not poison the dedup check.

        The helper should still write the new record (no dedup hit even
        though the file is not empty), tolerating both unparseable JSON and
        objects missing the dedup-key fields.
        """
        path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        # Mix one malformed line, one valid-but-non-matching line, one
        # object with missing keys.
        valid = make_jsonl_record(
            task_id=9999, state="level_sent", level=2
        )
        path.write_text(
            "not a json line\n"
            + json.dumps(valid) + "\n"
            + "{}\n",  # missing dedup keys
            encoding="utf-8",
        )
        mock_urlopen.side_effect = [_resp({"id": 10010})]
        record = make_jsonl_record(state="level_sent", level=1)
        # No exception, new record appended.
        record_event(record, token_path=tmp_token_file)
        # Tail of file is the new record.
        lines = path.read_text(encoding="utf-8").splitlines()
        assert json.loads(lines[-1])["task_id"] == 1234
        assert json.loads(lines[-1])["level"] == 1


# ---------------------------------------------------------------------------
# Group 10 — Token loader
# ---------------------------------------------------------------------------


class TestTokenLoader:
    def test_empty_token_file_raises_value_error(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_path,
        monkeypatch,
        capsys,
        make_jsonl_record,
    ):
        """Empty token file -> ValueError that surfaces as CLI exit 3."""
        empty = tmp_path / "empty_token"
        empty.write_text("", encoding="utf-8")
        record = make_jsonl_record(state="level_sent", level=1)
        with pytest.raises(ValueError, match="empty"):
            record_event(record, token_path=empty)


# ---------------------------------------------------------------------------
# Group 11 — HTTP method coverage (non-2xx without HTTPError)
# ---------------------------------------------------------------------------


class TestHttpEdgeCases:
    def test_non_2xx_with_status_attr_raises_vikunja_error(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """Status 199 (no HTTPError raised) still raises VikunjaError."""
        mock_urlopen.side_effect = [_resp(None, status=199)]
        record = make_jsonl_record(state="level_sent", level=1)
        with pytest.raises(VikunjaError, match="HTTP 199"):
            record_event(record, token_path=tmp_token_file)

    def test_non_json_response_body_is_tolerated(
        self,
        mock_urlopen,
        jsonl_sandbox,
        tmp_token_file,
        make_jsonl_record,
    ):
        """Comment-create may return non-JSON; helper must not blow up."""
        # Build a non-JSON 2xx response.
        resp = MagicMock(name="response")
        resp.status = 201
        resp.read = MagicMock(return_value=b"OK\n")
        cm = MagicMock(name="cm")
        cm.__enter__ = MagicMock(return_value=resp)
        cm.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = [cm]

        record = make_jsonl_record(state="level_sent", level=1)
        result = record_event(record, token_path=tmp_token_file)
        assert result["ok"] is True
