"""Tests for scripts/habits/record_completion.py (WP03 / T011).

Covers the ``record()`` Python API and the ``__main__`` CLI surface.
All Vikunja HTTP traffic is mocked via ``urllib.request.urlopen``; state_log
I/O is sandboxed via the ``mock_state_log_dir`` fixture from conftest.

Test groups:

1. Happy path — three writes succeed in the prescribed order.
2. Idempotency — pre-flight state_log hit skips all writes.
3. Validation — invalid state value raises ValueError before any I/O.
4. Step 2 failure (Vikunja done=true).
5. Step 3 failure (Vikunja comment).
6. Step 4 failure (state_log append).
7. G4 verification — comment write uses HTTP method PUT (not POST).
8. Comment body formatting — with and without note segment.
9. CLI happy path (in-process main() with stdin JSON).
10. CLI step-2-fail exit code 1.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.common import state_log
from scripts.habits import record_completion as rc


# ---------------------------------------------------------------------------
# Local mocking helpers
# ---------------------------------------------------------------------------


def _resp(payload, *, status: int = 200):
    """Return a context-manager-compatible mock urlopen response."""
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
        url="http://test/",
        code=code,
        msg="Server Error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


VALID_KWARGS = dict(
    task_id=14,
    title="Wake at 5:00 AM",
    date="2026-05-20",
    state="complete",
    source="whatsapp",
    api_base_url="http://test/api/v1/",
    token="test-token",
)


# ===========================================================================
# Group 1 — Happy path
# ===========================================================================


class TestHappyPath:
    def test_three_writes_in_correct_order(
        self, mock_urlopen, mock_state_log_dir
    ):
        """Pre-flight state_log.read empty -> GET task -> POST done -> PUT comment -> append.

        The GET before POST preserves repeat_after/repeat_mode against Vikunja
        v0.24.6's destructive partial-update semantics (#524).
        """
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),  # step 2a: GET pre-done
            _resp({"id": 14, "done": True}),  # step 2b: POST done=true
            _resp({"id": 999, "comment": "[Felix] ..."}),  # step 3: PUT comment
        ]

        rc.record(**VALID_KWARGS)

        # urlopen called three times (GET + POST + PUT).
        assert mock_urlopen.call_count == 3

        # First call is GET /tasks/14 (preserve-recurrence read).
        get_req = mock_urlopen.call_args_list[0][0][0]
        assert get_req.get_method() == "GET"
        assert get_req.full_url == "http://test/api/v1/tasks/14"
        assert get_req.data is None

        # Second call is POST /tasks/14 with recurrence config echoed back.
        post_req = mock_urlopen.call_args_list[1][0][0]
        assert post_req.get_method() == "POST"
        assert post_req.full_url == "http://test/api/v1/tasks/14"
        post_body = json.loads(post_req.data.decode("utf-8"))
        assert post_body == {
            "done": True,
            "repeat_after": 86400,
            "repeat_mode": 0,
        }

        # Third call is PUT /tasks/14/comments (G4 verified).
        third_req = mock_urlopen.call_args_list[2][0][0]
        assert third_req.get_method() == "PUT"
        assert third_req.full_url == "http://test/api/v1/tasks/14/comments"
        third_body = json.loads(third_req.data.decode("utf-8"))
        assert third_body == {"comment": "[Felix] 2026-05-20 | complete"}

        # state_log.append landed -- read back from the sandbox.
        records = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(records) == 1
        rec_row = records[0]
        assert rec_row["task_id"] == 14
        assert rec_row["title"] == "Wake at 5:00 AM"
        assert rec_row["date"] == "2026-05-20"
        assert rec_row["state"] == "complete"
        assert rec_row["source"] == "whatsapp"
        assert "timestamp" in rec_row

    def test_passes_authorization_header(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _resp({"id": 14, "done": True}),
            _resp({"id": 999}),
        ]
        rc.record(**VALID_KWARGS)
        req = mock_urlopen.call_args_list[0][0][0]
        # urllib normalizes header capitalization.
        assert req.headers.get("Authorization") == "Bearer test-token"


# ===========================================================================
# Group 2 — Idempotency
# ===========================================================================


class TestIdempotency:
    def test_existing_record_short_circuits_all_writes(
        self, mock_urlopen, mock_state_log_dir
    ):
        """If state_log already has (task_id, date, state), no writes happen."""
        # Pre-seed the state_log sandbox with a matching record.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 14,
                "title": "Wake at 5:00 AM",
                "date": "2026-05-20",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-20T10:00:00+00:00",
            },
        )

        # If a Vikunja call IS made the test fails (no side_effect configured).
        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called when idempotent no-op is detected"
        )

        rc.record(**VALID_KWARGS)
        assert mock_urlopen.call_count == 0

        # JSONL still has exactly one record (no duplicate append).
        records = state_log.read("habits", task_id=14)
        assert len(records) == 1


# ===========================================================================
# Group 3 — Validation
# ===========================================================================


class TestValidation:
    def test_invalid_state_raises_value_error_before_any_io(
        self, mock_urlopen, mock_state_log_dir
    ):
        bad = dict(VALID_KWARGS)
        bad["state"] = "Complet"  # typo
        mock_urlopen.side_effect = AssertionError("must not be called")

        with pytest.raises(ValueError, match="state 'Complet' not in"):
            rc.record(**bad)
        assert mock_urlopen.call_count == 0

    def test_missing_title_raises_value_error(
        self, mock_urlopen, mock_state_log_dir
    ):
        bad = dict(VALID_KWARGS)
        bad["title"] = ""  # empty -> validation failure
        mock_urlopen.side_effect = AssertionError("must not be called")

        with pytest.raises(ValueError):
            rc.record(**bad)
        assert mock_urlopen.call_count == 0

    def test_bad_date_format_raises_value_error(
        self, mock_urlopen, mock_state_log_dir
    ):
        bad = dict(VALID_KWARGS)
        bad["date"] = "5/20/2026"
        mock_urlopen.side_effect = AssertionError("must not be called")

        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            rc.record(**bad)
        assert mock_urlopen.call_count == 0


# ===========================================================================
# Group 4 — Step 2 failure (Vikunja done=true)
# ===========================================================================


class TestStep2Failure:
    def test_done_post_failure_propagates_with_step2_prefix(
        self, mock_urlopen, mock_state_log_dir
    ):
        # GET pre-done succeeds; POST done=true fails.
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _http_error(503, b'{"message":"down"}'),
        ]

        with pytest.raises(OSError, match=r"step 2 \(Vikunja done=true\)"):
            rc.record(**VALID_KWARGS)

        # GET landed, POST attempted. State_log NOT written.
        assert mock_urlopen.call_count == 2
        records = state_log.read("habits", task_id=14)
        assert records == []

    def test_get_pre_done_failure_propagates_with_step2_prefix(
        self, mock_urlopen, mock_state_log_dir
    ):
        # GET pre-done fails before the POST is ever attempted.
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')

        with pytest.raises(OSError, match=r"step 2 \(Vikunja GET pre-done\)"):
            rc.record(**VALID_KWARGS)

        # Only the GET was attempted; POST never fires.
        assert mock_urlopen.call_count == 1
        records = state_log.read("habits", task_id=14)
        assert records == []

    def test_get_pre_done_non_dict_body_raises_with_step2_prefix(
        self, mock_urlopen, mock_state_log_dir
    ):
        # Defensive: if Vikunja returns a non-dict body (list / null), bail
        # before the POST. Without this guard we'd attribute-error on .get().
        mock_urlopen.side_effect = [
            _resp([1, 2, 3]),  # list -- not a task dict
        ]

        with pytest.raises(OSError, match=r"step 2 \(Vikunja GET pre-done\) returned non-dict"):
            rc.record(**VALID_KWARGS)

        assert mock_urlopen.call_count == 1

    def test_post_done_body_echoes_repeat_after_and_repeat_mode_from_get(
        self, mock_urlopen, mock_state_log_dir
    ):
        # Regression guard for #524: POST body MUST include the recurrence
        # config returned from GET, so Vikunja's auto-advance trigger keeps
        # firing on subsequent completions.
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 604800, "repeat_mode": 1}),  # weekly
            _resp({"id": 14, "done": True}),
            _resp({"id": 999}),
        ]
        rc.record(**VALID_KWARGS)
        post_req = mock_urlopen.call_args_list[1][0][0]
        post_body = json.loads(post_req.data.decode("utf-8"))
        assert post_body == {
            "done": True,
            "repeat_after": 604800,
            "repeat_mode": 1,
        }

    def test_post_done_body_defaults_repeat_fields_when_get_omits_them(
        self, mock_urlopen, mock_state_log_dir
    ):
        # If the GET response omits repeat_after / repeat_mode (e.g. a
        # non-recurring one-off task), default both to 0 -- matches Vikunja's
        # own zero value for non-recurring tasks.
        mock_urlopen.side_effect = [
            _resp({"id": 14}),  # no repeat_* fields
            _resp({"id": 14, "done": True}),
            _resp({"id": 999}),
        ]
        rc.record(**VALID_KWARGS)
        post_req = mock_urlopen.call_args_list[1][0][0]
        post_body = json.loads(post_req.data.decode("utf-8"))
        assert post_body == {
            "done": True,
            "repeat_after": 0,
            "repeat_mode": 0,
        }


# ===========================================================================
# Group 5 — Step 3 failure (Vikunja comment)
# ===========================================================================


class TestStep3Failure:
    def test_comment_put_failure_propagates_with_step3_prefix(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),  # step 2a: GET
            _resp({"id": 14, "done": True}),  # step 2b: POST succeeds
            _http_error(500, b'{"message":"comment endpoint down"}'),  # step 3
        ]

        with pytest.raises(OSError, match=r"step 3 \(Vikunja comment\)"):
            rc.record(**VALID_KWARGS)

        assert mock_urlopen.call_count == 3
        # state_log NOT written (Vikunja-done landed but the JSONL append
        # is only after step 3 succeeds).
        records = state_log.read("habits", task_id=14)
        assert records == []


# ===========================================================================
# Group 6 — Step 4 failure (state_log append)
# ===========================================================================


class TestStep4Failure:
    def test_state_log_append_failure_propagates_with_step4_prefix(
        self, mock_urlopen, mock_state_log_dir, monkeypatch
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _resp({"id": 14, "done": True}),
            _resp({"id": 999}),
        ]

        def _boom(*_a, **_kw):
            raise OSError("disk full")

        monkeypatch.setattr(state_log, "append", _boom)

        with pytest.raises(OSError, match=r"step 4 \(state_log append\)"):
            rc.record(**VALID_KWARGS)

        # GET + POST + PUT all attempted (already committed at this point).
        assert mock_urlopen.call_count == 3


# ===========================================================================
# Group 7 — G4 verification (comment write uses PUT)
# ===========================================================================


class TestG4PutVerification:
    def test_comment_endpoint_uses_put_method(
        self, mock_urlopen, mock_state_log_dir
    ):
        """G4: Vikunja comment-create endpoint requires PUT, not POST.

        Regression guard: implementer must not copy a generic 'POST a comment'
        pattern from elsewhere.
        """
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _resp({"id": 14, "done": True}),
            _resp({"id": 999, "comment": "stub"}),
        ]

        rc.record(**VALID_KWARGS)

        comment_req = mock_urlopen.call_args_list[2][0][0]
        assert comment_req.get_method() == "PUT", (
            f"comment endpoint must use PUT per G4 "
            f"(got {comment_req.get_method()})"
        )
        # URL points at the comments collection for the task.
        assert comment_req.full_url.endswith("/tasks/14/comments")


# ===========================================================================
# Group 8 — Comment body formatting
# ===========================================================================


class TestCommentBodyFormat:
    def test_comment_format_without_note(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _resp({"id": 14, "done": True}),
            _resp({"id": 999}),
        ]
        rc.record(**VALID_KWARGS)
        comment_req = mock_urlopen.call_args_list[2][0][0]
        body = json.loads(comment_req.data.decode("utf-8"))
        assert body == {"comment": "[Felix] 2026-05-20 | complete"}

    def test_comment_format_with_note(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 17, "repeat_after": 0, "repeat_mode": 0}),
            _resp({"id": 17, "done": True}),
            _resp({"id": 999}),
        ]
        kwargs = dict(VALID_KWARGS)
        kwargs["task_id"] = 17
        kwargs["title"] = "Workout"
        kwargs["date"] = "2026-05-19"
        kwargs["state"] = "skipped"
        kwargs["note"] = "travel — no gym access"

        rc.record(**kwargs)
        comment_req = mock_urlopen.call_args_list[2][0][0]
        body = json.loads(comment_req.data.decode("utf-8"))
        assert body == {
            "comment": "[Felix] 2026-05-19 | skipped | travel — no gym access"
        }

    def test_empty_string_note_treated_as_no_note(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _resp({"id": 14, "done": True}),
            _resp({"id": 999}),
        ]
        kwargs = dict(VALID_KWARGS)
        kwargs["note"] = "   "  # whitespace only
        rc.record(**kwargs)
        comment_req = mock_urlopen.call_args_list[2][0][0]
        body = json.loads(comment_req.data.decode("utf-8"))
        assert body == {"comment": "[Felix] 2026-05-20 | complete"}


# ===========================================================================
# Group 9 — _format_comment unit
# ===========================================================================


class TestFormatCommentUnit:
    def test_basic_form(self):
        assert (
            rc._format_comment("2026-05-20", "complete", None)
            == "[Felix] 2026-05-20 | complete"
        )

    def test_with_note(self):
        assert (
            rc._format_comment("2026-05-19", "skipped", "travel")
            == "[Felix] 2026-05-19 | skipped | travel"
        )

    def test_note_stripped(self):
        assert (
            rc._format_comment("2026-05-19", "skipped", "  travel  ")
            == "[Felix] 2026-05-19 | skipped | travel"
        )

    def test_empty_note_drops_segment(self):
        assert (
            rc._format_comment("2026-05-19", "skipped", "")
            == "[Felix] 2026-05-19 | skipped"
        )


# ===========================================================================
# Group 10 — CLI surface
# ===========================================================================


def _patch_stdin(monkeypatch, payload: str | None) -> None:
    """Replace sys.stdin with a StringIO containing ``payload``.

    Also stubs ``isatty()`` to False so the CLI treats the stream as piped.
    """
    if payload is None:
        # Simulate a TTY (no stdin data).
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
            rc.main(["--help"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "record_completion" in captured.out.lower() or "usage" in captured.out.lower()

    def test_cli_happy_path_stdin_json(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        monkeypatch,
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _resp({"id": 14, "done": True}),
            _resp({"id": 999}),
        ]
        payload = json.dumps({
            "task_id": 14,
            "title": "Wake at 5:00 AM",
            "date": "2026-05-20",
            "state": "complete",
            "source": "whatsapp",
            "note": None,
        })
        _patch_stdin(monkeypatch, payload)
        exit_code = rc.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 0

        records = state_log.read("habits", task_id=14)
        assert len(records) == 1
        assert records[0]["state"] == "complete"

    def test_cli_happy_path_flags(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        monkeypatch,
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _resp({"id": 14, "done": True}),
            _resp({"id": 999}),
        ]
        _patch_stdin(monkeypatch, None)  # no stdin
        exit_code = rc.main([
            "--task-id", "14",
            "--title", "Wake at 5:00 AM",
            "--date", "2026-05-20",
            "--state", "complete",
            "--source", "whatsapp",
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 0

    def test_cli_step2_failure_exits_one(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')
        payload = json.dumps({
            "task_id": 14,
            "title": "Wake at 5:00 AM",
            "date": "2026-05-20",
            "state": "complete",
            "source": "whatsapp",
        })
        _patch_stdin(monkeypatch, payload)
        exit_code = rc.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "step 2" in err

    def test_cli_step3_failure_exits_one(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _resp({"id": 14, "done": True}),
            _http_error(500, b'{"message":"comment-down"}'),
        ]
        payload = json.dumps({
            "task_id": 14,
            "title": "Wake at 5:00 AM",
            "date": "2026-05-20",
            "state": "complete",
            "source": "whatsapp",
        })
        _patch_stdin(monkeypatch, payload)
        exit_code = rc.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "step 3" in err

    def test_cli_step4_failure_exits_two(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        mock_urlopen.side_effect = [
            _resp({"id": 14, "repeat_after": 86400, "repeat_mode": 0}),
            _resp({"id": 14, "done": True}),
            _resp({"id": 999}),
        ]

        def _boom(*_a, **_kw):
            raise OSError("disk full")

        monkeypatch.setattr(state_log, "append", _boom)
        payload = json.dumps({
            "task_id": 14,
            "title": "Wake at 5:00 AM",
            "date": "2026-05-20",
            "state": "complete",
            "source": "whatsapp",
        })
        _patch_stdin(monkeypatch, payload)
        exit_code = rc.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "step 4" in err

    def test_cli_validation_failure_exits_three(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        # Invalid state value via stdin (bypasses argparse choices guard).
        payload = json.dumps({
            "task_id": 14,
            "title": "Wake at 5:00 AM",
            "date": "2026-05-20",
            "state": "Complet",
            "source": "whatsapp",
        })
        _patch_stdin(monkeypatch, payload)
        mock_urlopen.side_effect = AssertionError("must not be called")
        exit_code = rc.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 3
        err = capsys.readouterr().err
        assert "validation failed" in err

    def test_cli_missing_required_args_exits_three(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        _patch_stdin(monkeypatch, None)  # no stdin
        mock_urlopen.side_effect = AssertionError("must not be called")
        exit_code = rc.main([
            "--task-id", "14",
            # missing --title etc.
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 3
        err = capsys.readouterr().err
        assert "missing required" in err

    def test_cli_malformed_stdin_exits_three(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        monkeypatch,
        capsys,
    ):
        _patch_stdin(monkeypatch, "{not json")
        mock_urlopen.side_effect = AssertionError("must not be called")
        exit_code = rc.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 3

    def test_cli_missing_token_file_exits_three(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        _patch_stdin(monkeypatch, json.dumps({
            "task_id": 14,
            "title": "Wake at 5:00 AM",
            "date": "2026-05-20",
            "state": "complete",
            "source": "whatsapp",
        }))
        mock_urlopen.side_effect = AssertionError("must not be called")
        missing = tmp_path / "nope" / "token"
        exit_code = rc.main([
            "--token-file", str(missing),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 3
        err = capsys.readouterr().err
        assert "Token file not found" in err
