"""Tests for scripts/habits/record_completion.py (WP03 / T011).

Covers the ``record()`` Python API and the ``__main__`` CLI surface.
All Vikunja HTTP traffic is mocked via ``urllib.request.urlopen`` with v2 task
bodies from ``tests/common/vikunja_v2_factory`` (#1111); state_log
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
from unittest.mock import MagicMock

import pytest

from scripts.common import state_log
from scripts.habits import record_completion as rc
from tests.common.vikunja_v2_factory import make_task

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


def _before(task_id: int = 14, **overrides) -> dict:
    """The v2 task before completion: a daily habit, open."""
    return make_task(**{"id": task_id, "due_date": "2026-05-21T03:59:59Z", **overrides})


def _after(task_id: int = 14, **overrides) -> dict:
    """The v2 task the server returns after a normal completion: +1 day, open."""
    return make_task(**{"id": task_id, "due_date": "2026-05-22T03:59:59Z", **overrides})


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
        """Pre-flight state_log.read empty -> GET v2 task -> PATCH done -> PUT comment -> append.

        The GET reads the rule for the completion-outcome classifier; the
        PATCH body is exactly ``{"done": true}`` because a v2 merge patch
        leaves omitted fields (the rule) as stored (#1111).
        """
        mock_urlopen.side_effect = [
            _resp(_before()),  # step 2a: GET v2 pre-done
            _resp(_after()),  # step 2b: PATCH done=true
            _resp({"id": 999, "comment": "[Felix] ..."}),  # step 3: PUT comment
        ]

        rc.record(**VALID_KWARGS)

        # urlopen called three times (GET + PATCH + PUT).
        assert mock_urlopen.call_count == 3

        # First call is GET /api/v2/tasks/14 (rule read).
        get_req = mock_urlopen.call_args_list[0][0][0]
        assert get_req.get_method() == "GET"
        assert get_req.full_url == "http://test/api/v2/tasks/14"
        assert get_req.data is None

        # Second call is PATCH /api/v2/tasks/14 with ONLY done (no echo).
        patch_req = mock_urlopen.call_args_list[1][0][0]
        assert patch_req.get_method() == "PATCH"
        assert patch_req.full_url == "http://test/api/v2/tasks/14"
        assert patch_req.headers.get("Content-type") == "application/merge-patch+json"
        assert json.loads(patch_req.data.decode("utf-8")) == {"done": True}

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

    def test_comment_non_json_2xx_body_is_tolerated(
        self, mock_urlopen, mock_state_log_dir
    ):
        """A non-JSON 2xx body on the comment PUT must NOT raise (Vikunja quirk).

        Pre-migration ``_http_request`` returned ``(200, None)`` for a non-JSON
        comment-create body and tolerated it; the migrated path must preserve
        that (post-merge Codex HIGH). A raw ``b"OK"`` body makes VikunjaClient
        raise ``VikunjaServerError(status=200)``, which record() swallows so the
        state_log append (step 4) still lands.
        """
        raw_resp = MagicMock(name="raw-response")
        raw_resp.status = 200
        raw_resp.read = MagicMock(return_value=b"OK")  # non-JSON 2xx body
        raw_cm = MagicMock(name="raw-cm")
        raw_cm.__enter__ = MagicMock(return_value=raw_resp)
        raw_cm.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [
            _resp(_before()),  # GET v2 pre-done
            _resp(_after()),  # PATCH done=true
            raw_cm,  # step 3: PUT comment -> non-JSON 2xx body (tolerated)
        ]

        # Must NOT raise despite the non-JSON comment response.
        rc.record(**VALID_KWARGS)

        assert mock_urlopen.call_count == 3
        # step 4 still landed -- the tolerated comment did not abort the record.
        records = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(records) == 1

    def test_passes_authorization_header(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = [
            _resp(_before()),
            _resp(_after()),
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
        # GET pre-done succeeds; PATCH done=true fails.
        mock_urlopen.side_effect = [
            _resp(_before()),
            _http_error(503, b'{"message":"down"}'),
        ]

        with pytest.raises(OSError, match=r"step 2 \(Vikunja done=true\)"):
            rc.record(**VALID_KWARGS)

        # GET landed, PATCH attempted. State_log NOT written.
        assert mock_urlopen.call_count == 2
        records = state_log.read("habits", task_id=14)
        assert records == []

    def test_get_pre_done_failure_propagates_with_step2_prefix(
        self, mock_urlopen, mock_state_log_dir
    ):
        # GET pre-done fails before the PATCH is ever attempted.
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')

        with pytest.raises(OSError, match=r"step 2 \(Vikunja GET pre-done\)"):
            rc.record(**VALID_KWARGS)

        # Only the GET was attempted; PATCH never fires.
        assert mock_urlopen.call_count == 1
        records = state_log.read("habits", task_id=14)
        assert records == []

    def test_get_pre_done_non_dict_body_raises_with_step2_prefix(
        self, mock_urlopen, mock_state_log_dir
    ):
        # Defensive: if Vikunja returns a non-dict body (list / null), bail
        # before the PATCH (the v2 client refuses a non-object body).
        mock_urlopen.side_effect = [
            _resp([1, 2, 3]),  # list -- not a task dict
        ]

        with pytest.raises(OSError, match=r"step 2 \(Vikunja GET pre-done\)"):
            rc.record(**VALID_KWARGS)

        assert mock_urlopen.call_count == 1

    def test_patch_body_is_exactly_done_for_weekly_rule(
        self, mock_urlopen, mock_state_log_dir
    ):
        # Inverted #524 guard: the old v1 POST had to echo the recurrence
        # config; the v2 merge patch must NOT carry any rule field at all.
        weekly = {"freq": "weekly", "interval": 1, "by_day": ["we"]}
        mock_urlopen.side_effect = [
            _resp(_before(repeat=weekly)),
            _resp(_after(repeat=weekly, due_date="2026-05-28T03:59:59Z")),
            _resp({"id": 999}),
        ]
        rc.record(**VALID_KWARGS)
        patch_req = mock_urlopen.call_args_list[1][0][0]
        assert json.loads(patch_req.data.decode("utf-8")) == {"done": True}

    def test_not_modified_patch_rereads_task(
        self, mock_urlopen, mock_state_log_dir
    ):
        # A 304 (no change) makes the client return None; record() re-reads
        # the task for the classifier instead of guessing.
        mock_urlopen.side_effect = [
            _resp(_before()),
            _http_error(304, b""),
            _resp(_after()),  # re-read after 304
            _resp({"id": 999}),
        ]
        rc.record(**VALID_KWARGS)
        reread = mock_urlopen.call_args_list[2][0][0]
        assert reread.get_method() == "GET"
        assert reread.full_url == "http://test/api/v2/tasks/14"
        assert mock_urlopen.call_count == 4

    def test_task_without_rule_is_unexpected_after_recording(
        self, mock_urlopen, mock_state_log_dir
    ):
        # A habit with no rule that stays done is not a normal series end:
        # comment + state log are written, then step 2 reports unexpected.
        mock_urlopen.side_effect = [
            _resp(_before(repeat=None)),
            _resp(_before(repeat=None, done=True)),
            _resp({"id": 999}),
        ]
        with pytest.raises(OSError, match=r"step 2: unexpected completion outcome"):
            rc.record(**VALID_KWARGS)
        assert mock_urlopen.call_count == 3
        assert len(state_log.read("habits", task_id=14)) == 1


# ===========================================================================
# Group 5 — Step 3 failure (Vikunja comment)
# ===========================================================================


class TestStep3Failure:
    def test_comment_put_failure_propagates_with_step3_prefix(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = [
            _resp(_before()),  # step 2a: GET
            _resp(_after()),  # step 2b: PATCH succeeds
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
            _resp(_before()),
            _resp(_after()),
            _resp({"id": 999}),
        ]

        def _boom(*_a, **_kw):
            raise OSError("disk full")

        monkeypatch.setattr(state_log, "append", _boom)

        with pytest.raises(OSError, match=r"step 4 \(state_log append\)"):
            rc.record(**VALID_KWARGS)

        # GET + PATCH + PUT all attempted (already committed at this point).
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
            _resp(_before()),
            _resp(_after()),
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
            _resp(_before()),
            _resp(_after()),
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
            _resp(_before(17)),
            _resp(_after(17)),
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
            _resp(_before()),
            _resp(_after()),
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
            _resp(_before()),
            _resp(_after()),
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
            _resp(_before()),
            _resp(_after()),
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
            _resp(_before()),
            _resp(_after()),
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
            _resp(_before()),
            _resp(_after()),
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


# ===========================================================================
# Group 11 — correlated_checkin_date_et instrumentation (#515)
# ===========================================================================


class TestCorrelatedCheckinDateEt:
    """The parser's top-level ``correlated_checkin_date_et`` (mission #408 /
    WP-02) must round-trip through ``record()`` and both CLI surfaces into the
    persisted JSONL row so mis-correlations are observable (#509 trigger 2)."""

    def _three_ok(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(_before()),
            _resp(_after()),
            _resp({"id": 999}),
        ]

    def test_record_persists_field_when_non_empty(
        self, mock_urlopen, mock_state_log_dir
    ):
        self._three_ok(mock_urlopen)
        rc.record(**VALID_KWARGS, correlated_checkin_date_et="2026-05-19")

        rows = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(rows) == 1
        assert rows[0]["correlated_checkin_date_et"] == "2026-05-19"

    def test_record_omits_field_when_empty(
        self, mock_urlopen, mock_state_log_dir
    ):
        self._three_ok(mock_urlopen)
        rc.record(**VALID_KWARGS, correlated_checkin_date_et="")

        rows = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(rows) == 1
        assert "correlated_checkin_date_et" not in rows[0]

    def test_record_omits_field_when_absent(
        self, mock_urlopen, mock_state_log_dir
    ):
        # Default (None) — the field never appears; row shape unchanged.
        self._three_ok(mock_urlopen)
        rc.record(**VALID_KWARGS)

        rows = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(rows) == 1
        assert "correlated_checkin_date_et" not in rows[0]

    def test_cli_persists_field_via_flag(
        self, mock_urlopen, mock_state_log_dir, tmp_token_file, monkeypatch
    ):
        self._three_ok(mock_urlopen)
        _patch_stdin(monkeypatch, None)  # no stdin -> flags path
        exit_code = rc.main([
            "--task-id", "14",
            "--title", "Wake at 5:00 AM",
            "--date", "2026-05-20",
            "--state", "complete",
            "--source", "whatsapp",
            "--correlated-checkin-date-et", "2026-05-19",
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 0
        rows = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(rows) == 1
        assert rows[0]["correlated_checkin_date_et"] == "2026-05-19"

    def test_cli_persists_field_via_stdin(
        self, mock_urlopen, mock_state_log_dir, tmp_token_file, monkeypatch
    ):
        self._three_ok(mock_urlopen)
        payload = json.dumps({
            "task_id": 14,
            "title": "Wake at 5:00 AM",
            "date": "2026-05-20",
            "state": "complete",
            "source": "whatsapp",
            "correlated_checkin_date_et": "2026-05-19",
        })
        _patch_stdin(monkeypatch, payload)
        exit_code = rc.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 0
        rows = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(rows) == 1
        assert rows[0]["correlated_checkin_date_et"] == "2026-05-19"

    def test_field_is_not_part_of_dedup_key(
        self, mock_urlopen, mock_state_log_dir
    ):
        """A second call for the same (task_id, date, state) is still an
        idempotent no-op even if the correlation value differs — the field is
        metadata, not part of the dedup key."""
        self._three_ok(mock_urlopen)
        rc.record(**VALID_KWARGS, correlated_checkin_date_et="2026-05-19")

        # Second call: no Vikunja traffic allowed (idempotent short-circuit).
        mock_urlopen.side_effect = AssertionError(
            "urlopen must not be called on idempotent re-record"
        )
        rc.record(**VALID_KWARGS, correlated_checkin_date_et="2026-05-18")

        rows = state_log.read("habits", task_id=14, date="2026-05-20")
        assert len(rows) == 1
        # First write wins; no duplicate row.
        assert rows[0]["correlated_checkin_date_et"] == "2026-05-19"
