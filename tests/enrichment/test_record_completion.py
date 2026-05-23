"""Tests for ``scripts.enrichment.record_completion`` (WP01 / T003).

Coverage targets per WP01 § Validation:

- Three-write ordering verified by mock call-sequence assertions
  (Vikunja-then-JSONL, never the reverse).
- Every enrichment state happy path (proposed, confirmed, skipped, declined).
- Every source happy path (agent, reconcile, backfill, operator_repair).
- Vikunja step failure -> exit 1, no JSONL write.
- JSONL step failure AFTER Vikunja commit -> exit 0 (FR-013 soft-fail),
  warning logged to stderr.
- JSONL step failure on --no-vikunja path -> exit 2 (pre-Vikunja semantics
  apply: nothing downstream has committed).
- Idempotency: pre-existing (task_id, state) short-circuits both Vikunja
  AND JSONL.
- Schema validation: invalid record exits 3 before any side-effect.
- felix-bot identity: Authorization header carries the bearer token from
  the token file.
- v1 ``[Felix] enrichment`` comment vocabulary verified per deployed
  AGENTS.md (proposed/confirmed/skipped/declined).
- CLI exit codes 0/1/2/3 covered, including argparse error -> 3 mapping.

All HTTP traffic is mocked via the ``mock_urlopen`` fixture. JSONL writes
land under ``tmp_path`` via the ``ledger_sandbox`` fixture defined below.
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.enrichment import record_completion as rc
from scripts.enrichment.record_completion import (
    EnrichmentSchemaError,
    StateLogError,
    VikunjaError,
    _format_v1_comment,
    idempotent_record_event,
    main,
    record,
    record_event,
)


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_vikunja_token() -> str:
    """Placeholder bearer token for tests. Never sent to a real server."""
    return "test-enrichment-token"


@pytest.fixture
def tmp_token_file(tmp_path: Path, fake_vikunja_token: str) -> Path:
    """Write the placeholder token to a temp file (mode 0600) and return it."""
    import os

    token_path = tmp_path / "token"
    token_path.write_text(fake_vikunja_token + "\n", encoding="utf-8")
    os.chmod(token_path, 0o600)
    return token_path


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    """Path to a fresh JSONL ledger under tmp_path (not created eagerly)."""
    return tmp_path / "state" / "enrichment" / "enrichment-history.jsonl"


@pytest.fixture
def activity_log_sandbox(tmp_path: Path, monkeypatch) -> Path:
    """Redirect ACTIVITY_LOG_DIR to a tmp directory; return the path."""
    sandbox = tmp_path / "logs" / "enrichment"
    monkeypatch.setattr(rc, "ACTIVITY_LOG_DIR", sandbox)
    return sandbox


@pytest.fixture
def freeze_now(monkeypatch):
    """Return a callable that pins ``_now_utc_iso`` to the given ISO string."""

    def _freeze(value: str) -> None:
        monkeypatch.setattr(rc, "_now_utc_iso", lambda: value)

    return _freeze


@pytest.fixture
def mock_urlopen(monkeypatch):
    """Monkey-patch ``urllib.request.urlopen`` to a ``MagicMock``."""
    mock = MagicMock(name="urlopen")
    monkeypatch.setattr("urllib.request.urlopen", mock)
    return mock


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
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _make_record(
    *,
    task_id: int = 1234,
    state: str = "proposed",
    source: str = "agent",
    timestamp_utc: str = "2026-05-23T19:00:00Z",
    note=None,
    schema_version: int = 1,
) -> dict:
    """Minimal valid enrichment record dict."""
    return {
        "task_id": task_id,
        "state": state,
        "timestamp_utc": timestamp_utc,
        "source": source,
        "schema_version": schema_version,
        "note": note,
    }


def _patch_stdin(monkeypatch, payload):
    """Replace sys.stdin (currently unused — CLI is flag-driven only)."""
    if payload is None:
        fake = MagicMock(name="fake-tty-stdin")
        fake.isatty = MagicMock(return_value=True)
        fake.read = MagicMock(return_value="")
        monkeypatch.setattr(sys, "stdin", fake)
        return
    buf = io.StringIO(payload)
    buf.isatty = lambda: False  # type: ignore[assignment]
    monkeypatch.setattr(sys, "stdin", buf)


# ---------------------------------------------------------------------------
# Group 1 — Happy path per state + source
# ---------------------------------------------------------------------------


class TestHappyPathPerState:
    @pytest.mark.parametrize(
        "state", ["proposed", "confirmed", "skipped", "declined"]
    )
    def test_record_each_state_writes_comment_then_jsonl(
        self,
        state,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Each enrichment state PUTs a v1 comment FIRST, then JSONL.

        Verifies the three-write ordering invariant via the mock call
        sequence — urlopen MUST be called before the JSONL file gains a line.
        """
        rec = _make_record(state=state)

        observed_during_vikunja: list[bool] = []
        canned = [_resp({"id": 999, "comment": "[Felix] enrichment | ..."})]

        def _side_effect(*args, **kwargs):
            observed_during_vikunja.append(ledger_path.exists())
            return canned.pop(0)

        mock_urlopen.side_effect = _side_effect

        result = record_event(
            rec, token_path=tmp_token_file, ledger_path=ledger_path
        )

        assert result["ok"] is True
        assert result["deduped"] is False
        assert result["vikunja_actions"] == ["comment_PUT"]
        assert observed_during_vikunja == [False], (
            "JSONL was written BEFORE Vikunja was called; three-write "
            "ordering violated"
        )
        records = _read_jsonl(ledger_path)
        assert len(records) == 1
        assert records[0]["state"] == state
        assert records[0]["task_id"] == 1234

    @pytest.mark.parametrize(
        "source", ["agent", "reconcile", "backfill", "operator_repair"]
    )
    def test_record_each_source_succeeds(
        self,
        source,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Every valid source value flows end-to-end without error."""
        mock_urlopen.side_effect = [_resp({"id": 1})]
        rec = _make_record(source=source)
        result = record_event(
            rec, token_path=tmp_token_file, ledger_path=ledger_path
        )
        assert result["ok"] is True
        assert _read_jsonl(ledger_path)[0]["source"] == source

    def test_skip_vikunja_writes_only_jsonl(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """``skip_vikunja=True`` reconcile path: no HTTP calls, JSONL only."""
        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called when skip_vikunja=True"
        )
        rec = _make_record(source="reconcile")
        result = record_event(
            rec,
            token_path=tmp_token_file,
            ledger_path=ledger_path,
            skip_vikunja=True,
        )
        assert mock_urlopen.call_count == 0
        assert result["vikunja_actions"] == []
        assert len(_read_jsonl(ledger_path)) == 1

    def test_record_writes_activity_log(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Step 3 (activity log) writes a per-day file under ACTIVITY_LOG_DIR."""
        mock_urlopen.side_effect = [_resp({"id": 1})]
        rec = _make_record(
            timestamp_utc="2026-05-23T19:00:00Z",
            note="kent confirmed via WA",
        )
        record_event(
            rec, token_path=tmp_token_file, ledger_path=ledger_path
        )
        log_file = activity_log_sandbox / "2026-05-23.log"
        assert log_file.exists()
        body = log_file.read_text(encoding="utf-8")
        assert "2026-05-23T19:00:00Z" in body
        assert "1234" in body
        assert "proposed" in body
        assert "kent confirmed via WA" in body

    def test_activity_log_failure_is_swallowed(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        monkeypatch,
    ):
        """A failing activity log write must not propagate to the caller.

        Forces ``_write_activity_log`` into its except-swallow branch by
        pointing ACTIVITY_LOG_DIR at a path whose parent is a file (so
        ``mkdir`` cannot create the directory).
        """
        mock_urlopen.side_effect = [_resp({"id": 1})]
        # Make a file where the activity log dir would go.
        sentinel = activity_log_sandbox.parent
        sentinel.mkdir(parents=True, exist_ok=True)
        blocker_file = sentinel / "enrichment"  # was a dir; make it a file
        # Remove the sandbox dir created by the fixture (if present).
        if activity_log_sandbox.exists():
            for p in activity_log_sandbox.iterdir():
                p.unlink()
            activity_log_sandbox.rmdir()
        blocker_file.write_text("not a directory", encoding="utf-8")
        monkeypatch.setattr(rc, "ACTIVITY_LOG_DIR", blocker_file / "subdir")

        rec = _make_record()
        # Should NOT raise — the activity log error is swallowed.
        result = record_event(
            rec, token_path=tmp_token_file, ledger_path=ledger_path
        )
        assert result["ok"] is True
        # JSONL still got written.
        assert len(_read_jsonl(ledger_path)) == 1

    def test_write_activity_log_returns_none_on_failure(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Direct exercise of the activity-log error-swallow path.

        Points ACTIVITY_LOG_DIR at an un-creatable path (parent is a file)
        and confirms the helper returns ``None`` rather than raising.
        """
        from scripts.enrichment.record_completion import _write_activity_log

        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir", encoding="utf-8")
        monkeypatch.setattr(
            rc, "ACTIVITY_LOG_DIR", blocker / "wont_exist"
        )
        result = _write_activity_log(_make_record())
        assert result is None


# ---------------------------------------------------------------------------
# Group 2 — Three-write ordering invariant
# ---------------------------------------------------------------------------


class TestThreeWriteOrdering:
    def test_vikunja_network_failure_no_jsonl_write(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """If Vikunja raises a network error, the JSONL file must remain empty."""
        mock_urlopen.side_effect = urllib.error.URLError("network down")
        rec = _make_record()
        with pytest.raises(VikunjaError, match="network failure"):
            record_event(
                rec, token_path=tmp_token_file, ledger_path=ledger_path
            )
        assert not ledger_path.exists() or _read_jsonl(ledger_path) == []

    def test_vikunja_http_error_no_jsonl_write(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """HTTP 5xx -> VikunjaError; no JSONL line written."""
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')
        rec = _make_record()
        with pytest.raises(VikunjaError, match="HTTP 503"):
            record_event(
                rec, token_path=tmp_token_file, ledger_path=ledger_path
            )
        assert not ledger_path.exists() or _read_jsonl(ledger_path) == []

    def test_jsonl_failure_after_vikunja_commit_raises_state_log_error(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        monkeypatch,
    ):
        """Library layer: Vikunja success + JSONL fail -> StateLogError raised.

        The CLI layer applies the FR-013 soft-fail; the library raises so
        callers can choose their own policy.
        """
        mock_urlopen.side_effect = [_resp({"id": 1})]

        def _boom(_rec, _path):
            raise StateLogError("simulated disk full")

        monkeypatch.setattr(rc, "_append_jsonl", _boom)

        rec = _make_record()
        with pytest.raises(StateLogError, match="simulated disk full"):
            record_event(
                rec, token_path=tmp_token_file, ledger_path=ledger_path
            )
        assert mock_urlopen.call_count == 1

    def test_non_2xx_with_status_attr_raises_vikunja_error(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Status 199 (no HTTPError raised) still raises VikunjaError."""
        mock_urlopen.side_effect = [_resp(None, status=199)]
        rec = _make_record()
        with pytest.raises(VikunjaError, match="HTTP 199"):
            record_event(
                rec, token_path=tmp_token_file, ledger_path=ledger_path
            )

    def test_non_json_response_body_tolerated(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Comment-create may return non-JSON; helper must not blow up."""
        resp = MagicMock(name="response")
        resp.status = 201
        resp.read = MagicMock(return_value=b"OK\n")
        cm = MagicMock(name="cm")
        cm.__enter__ = MagicMock(return_value=resp)
        cm.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = [cm]

        rec = _make_record()
        result = record_event(
            rec, token_path=tmp_token_file, ledger_path=ledger_path
        )
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Group 3 — Idempotency (FR-004)
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_idempotent_record_event_no_op_on_duplicate(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Pre-existing (task_id, state) match -> NO Vikunja AND no new JSONL."""
        rec = _make_record()
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(rec) + "\n", encoding="utf-8")

        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called when dedup detected"
        )
        result = idempotent_record_event(
            rec, token_path=tmp_token_file, ledger_path=ledger_path
        )

        assert result["ok"] is True
        assert result["deduped"] is True
        assert result["vikunja_actions"] == []
        assert mock_urlopen.call_count == 0
        # JSONL still has exactly one record (no duplicate append).
        assert len(_read_jsonl(ledger_path)) == 1

    def test_idempotent_record_event_writes_on_no_match(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """No existing match -> normal three-write flow runs."""
        mock_urlopen.side_effect = [_resp({"id": 1})]
        rec = _make_record()
        result = idempotent_record_event(
            rec, token_path=tmp_token_file, ledger_path=ledger_path
        )
        assert result["deduped"] is False
        assert mock_urlopen.call_count == 1
        assert len(_read_jsonl(ledger_path)) == 1

    def test_idempotent_record_event_validates_before_dedup(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Malformed record must NOT short-circuit silently as dedup."""
        bad = _make_record(state="pending")  # not in VALID_STATES
        with pytest.raises(EnrichmentSchemaError):
            idempotent_record_event(
                bad, token_path=tmp_token_file, ledger_path=ledger_path
            )
        assert mock_urlopen.call_count == 0

    def test_dedup_distinguishes_state(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Same task_id but different state is NOT a duplicate."""
        prior = _make_record(state="proposed")
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(prior) + "\n", encoding="utf-8")

        mock_urlopen.side_effect = [_resp({"id": 1})]
        new = _make_record(state="confirmed")
        result = idempotent_record_event(
            new, token_path=tmp_token_file, ledger_path=ledger_path
        )
        assert result["deduped"] is False
        records = _read_jsonl(ledger_path)
        assert len(records) == 2
        assert {r["state"] for r in records} == {"proposed", "confirmed"}

    def test_append_idempotent_within_file(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Calling record_event twice with same key writes only one line."""
        mock_urlopen.side_effect = [
            _resp({"id": 1}),
            _resp({"id": 2}),
        ]
        rec = _make_record()
        record_event(rec, token_path=tmp_token_file, ledger_path=ledger_path)
        record_event(rec, token_path=tmp_token_file, ledger_path=ledger_path)
        records = _read_jsonl(ledger_path)
        assert len(records) == 1

    def test_append_tolerates_malformed_existing_lines(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Malformed prior lines do not poison the dedup check."""
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        valid = _make_record(task_id=9999, state="confirmed")
        ledger_path.write_text(
            "not a json line\n"
            + json.dumps(valid) + "\n"
            + "{}\n",
            encoding="utf-8",
        )
        mock_urlopen.side_effect = [_resp({"id": 1})]
        rec = _make_record()
        # No exception, new record appended.
        record_event(rec, token_path=tmp_token_file, ledger_path=ledger_path)
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        # Tail of file is the new record.
        assert json.loads(lines[-1])["task_id"] == 1234


# ---------------------------------------------------------------------------
# Group 4 — Schema validation surface
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_invalid_record_raises_schema_error_no_writes(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """Bad state -> EnrichmentSchemaError before any I/O."""
        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called on validation failure"
        )
        bad = _make_record(state="rogue")
        with pytest.raises(EnrichmentSchemaError, match="rogue"):
            record_event(
                bad, token_path=tmp_token_file, ledger_path=ledger_path
            )
        assert mock_urlopen.call_count == 0
        assert not ledger_path.exists()

    def test_missing_required_field_raises(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        mock_urlopen.side_effect = AssertionError("must not be called")
        bad = _make_record()
        del bad["task_id"]
        with pytest.raises(EnrichmentSchemaError, match="task_id"):
            record_event(
                bad, token_path=tmp_token_file, ledger_path=ledger_path
            )


# ---------------------------------------------------------------------------
# Group 5 — felix-bot identity
# ---------------------------------------------------------------------------


class TestFelixBotIdentity:
    def test_request_uses_felix_bot_token(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        fake_vikunja_token,
        activity_log_sandbox,
    ):
        """Authorization header MUST be ``Bearer <token>`` from the token file."""
        mock_urlopen.side_effect = [_resp({"id": 1})]
        rec = _make_record()
        record_event(rec, token_path=tmp_token_file, ledger_path=ledger_path)

        first_req = mock_urlopen.call_args_list[0][0][0]
        assert first_req.headers.get("Authorization") == (
            f"Bearer {fake_vikunja_token}"
        )


# ---------------------------------------------------------------------------
# Group 6 — v1 comment vocabulary (deployed AGENTS.md verbatim)
# ---------------------------------------------------------------------------


# Roundtripping the parsed form: prefix is the literal "[Felix] enrichment",
# then " | state | timestamp [| note]".
COMMENT_RE = re.compile(
    r"^\[Felix\] enrichment \| "
    r"(?P<state>proposed|confirmed|skipped|declined) \| "
    r"(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"
    r"(?: \| (?P<note>.+))?$"
)


class TestV1CommentFormat:
    @pytest.mark.parametrize(
        "state", ["proposed", "confirmed", "skipped", "declined"]
    )
    def test_comment_format_per_state(self, state):
        rec = _make_record(state=state, timestamp_utc="2026-05-23T19:00:00Z")
        comment = _format_v1_comment(rec)
        assert comment == (
            f"[Felix] enrichment | {state} | 2026-05-23T19:00:00Z"
        )
        match = COMMENT_RE.match(comment)
        assert match is not None
        assert match.group("state") == state
        assert match.group("note") is None

    def test_comment_format_with_note_appends_fourth_field(self):
        rec = _make_record(
            state="skipped",
            timestamp_utc="2026-05-23T19:00:00Z",
            note="Kent skipped during batch",
        )
        comment = _format_v1_comment(rec)
        assert comment == (
            "[Felix] enrichment | skipped | 2026-05-23T19:00:00Z | "
            "Kent skipped during batch"
        )
        match = COMMENT_RE.match(comment)
        assert match is not None
        assert match.group("note") == "Kent skipped during batch"

    def test_comment_body_round_trips_through_put(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """The body PUT to /comments matches the deployed vocabulary."""
        mock_urlopen.side_effect = [_resp({"id": 1})]
        rec = _make_record(
            state="confirmed", timestamp_utc="2026-05-23T19:00:00Z"
        )
        record_event(rec, token_path=tmp_token_file, ledger_path=ledger_path)
        req = mock_urlopen.call_args_list[0][0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert "comment" in body
        assert COMMENT_RE.match(body["comment"]) is not None
        # And the URL is /tasks/<id>/comments.
        assert req.full_url.endswith("/tasks/1234/comments")
        assert req.get_method() == "PUT"


# ---------------------------------------------------------------------------
# Group 7 — Public record() wrapper
# ---------------------------------------------------------------------------


class TestRecordWrapper:
    def test_record_builds_completion_and_writes(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        freeze_now,
    ):
        """``record(...)`` is the public convenience wrapper used by callers."""
        freeze_now("2026-05-23T19:00:00Z")
        mock_urlopen.side_effect = [_resp({"id": 1})]
        result = record(
            task_id=1234,
            state="proposed",
            source="agent",
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )
        assert result["ok"] is True
        rows = _read_jsonl(ledger_path)
        assert rows[0]["task_id"] == 1234
        assert rows[0]["state"] == "proposed"
        assert rows[0]["source"] == "agent"
        assert rows[0]["timestamp_utc"] == "2026-05-23T19:00:00Z"

    def test_record_idempotent_flag_dedups(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        freeze_now,
    ):
        """``record(idempotent=True)`` honors the same dedup rule."""
        freeze_now("2026-05-23T19:00:00Z")
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        prior = _make_record()
        ledger_path.write_text(json.dumps(prior) + "\n", encoding="utf-8")

        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called on dedup"
        )
        result = record(
            task_id=1234,
            state="proposed",
            source="agent",
            idempotent=True,
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )
        assert result["deduped"] is True

    def test_record_skip_vikunja_flag(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        freeze_now,
    ):
        freeze_now("2026-05-23T19:00:00Z")
        mock_urlopen.side_effect = AssertionError("must not be called")
        result = record(
            task_id=1234,
            state="proposed",
            source="backfill",
            skip_vikunja=True,
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )
        assert result["ok"] is True
        assert result["vikunja_actions"] == []


# ---------------------------------------------------------------------------
# Group 8 — CLI exit codes 0/1/2/3
# ---------------------------------------------------------------------------


class TestCli:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "record_completion" in captured.out or "usage" in captured.out

    def test_cli_exit_0_on_success(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        capsys,
    ):
        mock_urlopen.side_effect = [_resp({"id": 1})]
        rc_code = main([
            "--task-id", "1234",
            "--state", "proposed",
            "--source", "agent",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(ledger_path),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["ok"] is True
        assert payload["vikunja_actions"] == ["comment_PUT"]

    def test_cli_exit_0_on_idempotent_dedup(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        capsys,
        freeze_now,
    ):
        freeze_now("2026-05-23T19:00:00Z")
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        prior = _make_record()
        ledger_path.write_text(json.dumps(prior) + "\n", encoding="utf-8")

        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called on dedup"
        )
        rc_code = main([
            "--task-id", "1234",
            "--state", "proposed",
            "--source", "agent",
            "--idempotent",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(ledger_path),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 0
        out = capsys.readouterr().out
        assert json.loads(out)["deduped"] is True

    def test_cli_exit_0_on_no_vikunja_flag(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        capsys,
    ):
        """``--no-vikunja`` writes JSONL without calling Vikunja."""
        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called when --no-vikunja"
        )
        rc_code = main([
            "--task-id", "1234",
            "--state", "proposed",
            "--source", "reconcile",
            "--no-vikunja",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(ledger_path),
        ])
        assert rc_code == 0
        records = _read_jsonl(ledger_path)
        assert len(records) == 1
        assert records[0]["state"] == "proposed"

    def test_cli_exit_1_on_vikunja_failure(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        capsys,
    ):
        """Vikunja HTTP failure -> exit 1; stderr names ``vikunja`` step."""
        mock_urlopen.side_effect = _http_error(500, b'{"message":"down"}')
        rc_code = main([
            "--task-id", "1234",
            "--state", "proposed",
            "--source", "agent",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(ledger_path),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 1
        err = capsys.readouterr().err
        assert "vikunja" in err
        # And JSONL is empty.
        assert not ledger_path.exists() or _read_jsonl(ledger_path) == []

    def test_cli_exit_0_on_jsonl_failure_after_vikunja_success(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        capsys,
        monkeypatch,
    ):
        """FR-013 soft-fail: JSONL fails post-Vikunja -> exit 0 + warning."""
        mock_urlopen.side_effect = [_resp({"id": 1})]

        def _boom(_rec, _path):
            raise StateLogError("simulated disk full")

        monkeypatch.setattr(rc, "_append_jsonl", _boom)
        rc_code = main([
            "--task-id", "1234",
            "--state", "proposed",
            "--source", "agent",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(ledger_path),
            "--base-url", "http://test/api/v1/",
        ])
        assert rc_code == 0
        err = capsys.readouterr().err
        # Soft-fail signal appears in stderr per CLI contract.
        assert "state_log_soft_fail" in err
        assert "simulated disk full" in err

    def test_cli_exit_2_on_jsonl_failure_with_no_vikunja(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        capsys,
        monkeypatch,
    ):
        """With --no-vikunja, JSONL failure -> exit 2 (nothing downstream)."""
        mock_urlopen.side_effect = AssertionError("must not be called")

        def _boom(_rec, _path):
            raise StateLogError("simulated disk full")

        monkeypatch.setattr(rc, "_append_jsonl", _boom)
        rc_code = main([
            "--task-id", "1234",
            "--state", "proposed",
            "--source", "reconcile",
            "--no-vikunja",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(ledger_path),
        ])
        assert rc_code == 2
        err = capsys.readouterr().err
        assert "state_log" in err

    def test_cli_exit_3_on_invalid_state_choice(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        capsys,
    ):
        """Invalid ``--state`` enum -> exit 3 (not argparse's default 2)."""
        mock_urlopen.side_effect = AssertionError("must not be called")
        rc_code = main([
            "--task-id", "1234",
            "--state", "bogus",
            "--source", "agent",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(ledger_path),
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "argparse" in err
        assert "bogus" in err or "invalid choice" in err

    def test_cli_exit_3_on_missing_required_flag(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        capsys,
    ):
        """Missing required ``--task-id`` -> exit 3."""
        mock_urlopen.side_effect = AssertionError("must not be called")
        rc_code = main([
            "--state", "proposed",
            "--source", "agent",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(ledger_path),
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "argparse" in err

    def test_cli_exit_3_on_missing_token_file(
        self,
        mock_urlopen,
        ledger_path,
        tmp_path,
        activity_log_sandbox,
        capsys,
    ):
        mock_urlopen.side_effect = AssertionError("must not be called")
        missing = tmp_path / "nope" / "token"
        rc_code = main([
            "--task-id", "1234",
            "--state", "proposed",
            "--source", "agent",
            "--token-path", str(missing),
            "--ledger-path", str(ledger_path),
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "token_load" in err
        assert "Token file not found" in err

    def test_cli_exit_3_on_validation_failure(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
        capsys,
    ):
        """task_id=0 passes argparse but fails ``validate_record`` -> exit 3."""
        mock_urlopen.side_effect = AssertionError("must not be called")
        rc_code = main([
            "--task-id", "0",  # zero is non-positive
            "--state", "proposed",
            "--source", "agent",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(ledger_path),
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "validation" in err
        assert "task_id" in err

    def test_cli_exit_2_on_idempotent_precheck_io_error(
        self,
        mock_urlopen,
        tmp_path,
        tmp_token_file,
        activity_log_sandbox,
        monkeypatch,
        capsys,
    ):
        """Pre-Vikunja I/O failure on the --idempotent precheck -> exit 2."""
        mock_urlopen.side_effect = AssertionError("must not be called")

        def _io_boom(*args, **kwargs):
            raise OSError("simulated filesystem error")

        monkeypatch.setattr(rc, "_idempotency_match", _io_boom)
        rc_code = main([
            "--task-id", "1234",
            "--state", "proposed",
            "--source", "agent",
            "--idempotent",
            "--token-path", str(tmp_token_file),
            "--ledger-path", str(tmp_path / "ledger.jsonl"),
        ])
        assert rc_code == 2
        err = capsys.readouterr().err
        assert "state_log_precheck" in err

    def test_cli_exit_3_on_empty_token_file(
        self,
        mock_urlopen,
        ledger_path,
        tmp_path,
        activity_log_sandbox,
        capsys,
    ):
        """Empty token file -> exit 3 (not uncaught ValueError)."""
        mock_urlopen.side_effect = AssertionError("must not be called")
        empty = tmp_path / "empty_token"
        empty.write_text("", encoding="utf-8")
        rc_code = main([
            "--task-id", "1234",
            "--state", "proposed",
            "--source", "agent",
            "--token-path", str(empty),
            "--ledger-path", str(ledger_path),
        ])
        assert rc_code == 3
        err = capsys.readouterr().err
        assert "token_load" in err
        assert "empty" in err.lower()


# ---------------------------------------------------------------------------
# Group 9 — JSONL atomicity helpers
# ---------------------------------------------------------------------------


class TestJsonlRouting:
    def test_append_creates_parent_directory(
        self,
        mock_urlopen,
        tmp_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """``_append_jsonl`` creates the parent directory if absent."""
        nested = tmp_path / "deep" / "nested" / "state" / "ledger.jsonl"
        mock_urlopen.side_effect = [_resp({"id": 1})]

        rec = _make_record()
        record_event(rec, token_path=tmp_token_file, ledger_path=nested)
        assert nested.exists()

    def test_jsonl_serialization_preserves_field_order(
        self,
        mock_urlopen,
        ledger_path,
        tmp_token_file,
        activity_log_sandbox,
    ):
        """On-disk JSONL preserves the canonical field order (data-model E1)."""
        mock_urlopen.side_effect = [_resp({"id": 1})]
        rec = _make_record(note="hi")
        record_event(rec, token_path=tmp_token_file, ledger_path=ledger_path)
        raw = ledger_path.read_text(encoding="utf-8").strip()
        # The keys must appear in the canonical order; load with
        # object_pairs_hook to verify insertion order.
        from collections import OrderedDict

        parsed = json.loads(raw, object_pairs_hook=OrderedDict)
        assert list(parsed.keys()) == [
            "task_id",
            "state",
            "timestamp_utc",
            "source",
            "schema_version",
            "note",
        ]


# ---------------------------------------------------------------------------
# Group 10 — Token loader
# ---------------------------------------------------------------------------


class TestTokenLoader:
    def test_empty_token_file_raises_value_error(self, tmp_path):
        """Empty token file -> ValueError that surfaces as CLI exit 3."""
        from scripts.enrichment.record_completion import _read_token

        empty = tmp_path / "empty_token"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            _read_token(empty)

    def test_whitespace_only_token_file_raises_value_error(self, tmp_path):
        from scripts.enrichment.record_completion import _read_token

        ws = tmp_path / "ws_token"
        ws.write_text("   \n\t  \n", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            _read_token(ws)

    def test_missing_token_file_raises_file_not_found(self, tmp_path):
        from scripts.enrichment.record_completion import _read_token

        missing = tmp_path / "nope" / "token"
        with pytest.raises(FileNotFoundError, match="not found"):
            _read_token(missing)

    def test_valid_token_file_returns_stripped(self, tmp_path):
        from scripts.enrichment.record_completion import _read_token

        token_file = tmp_path / "token"
        token_file.write_text("  abc123  \n", encoding="utf-8")
        assert _read_token(token_file) == "abc123"


# ---------------------------------------------------------------------------
# Group 11 — Now / clock helper
# ---------------------------------------------------------------------------


class TestClockHelper:
    def test_now_utc_iso_returns_z_suffixed_string(self):
        """``_now_utc_iso`` returns a Z-suffixed ISO-8601 instant."""
        from scripts.enrichment.record_completion import _now_utc_iso

        value = _now_utc_iso()
        assert isinstance(value, str)
        # Pattern: YYYY-MM-DDTHH:MM:SSZ (no microseconds).
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", value)
