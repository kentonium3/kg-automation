"""Tests for scripts/habits/exclude_completed.py (FR-004).

Verifies the contract in
kitty-specs/habits-checkin-d6-extract-01KRNV46/contracts/exclude_completed.md.

The critical correctness concern: if a habit IS marked complete today but the
helper says it's ready for checkin, Kent gets a duplicate WhatsApp message.
The comment-format parser must accept the production shape exactly.
"""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

# scripts/habits/ is on sys.path via tests/habits/conftest.py
import exclude_completed as exc  # type: ignore  # noqa: E402


TODAY = "2026-05-15"


def _fake_token_file(tmp_path):
    p = tmp_path / "vikunja-token"
    p.write_text("fake-token-for-tests\n")
    return p


def _mock_response(payload):
    """Return a context-manager-compatible mock with the given JSON payload."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(
        return_value=json.dumps(payload).encode("utf-8")
    )))
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _patch_comments_for(comment_payloads):
    """Patch urlopen to return per-task comment payloads keyed by URL substring.

    `comment_payloads` is {habit_id: [comments...]}.
    """
    def side_effect(req, timeout=15):  # noqa: ARG001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for habit_id, comments in comment_payloads.items():
            if f"/tasks/{habit_id}/comments" in url:
                return _mock_response(comments)
        raise AssertionError(f"Unexpected URL: {url}")
    return patch.object(exc.urllib.request, "urlopen", side_effect=side_effect)


# ---------- parse_felix_comment unit tests ----------


def test_parse_felix_comment_complete():
    parsed = exc.parse_felix_comment(f"[Felix] {TODAY} | complete")
    assert parsed == (TODAY, "complete", None)


def test_parse_felix_comment_with_note():
    parsed = exc.parse_felix_comment(f"[Felix] {TODAY} | rescheduled | this afternoon")
    assert parsed == (TODAY, "rescheduled", "this afternoon")


def test_parse_felix_comment_will_not_do():
    parsed = exc.parse_felix_comment(f"[Felix] {TODAY} | will-not-do | rest day")
    assert parsed == (TODAY, "will-not-do", "rest day")


def test_parse_felix_comment_state_lowercased():
    parsed = exc.parse_felix_comment(f"[Felix] {TODAY} | COMPLETE")
    assert parsed is not None
    assert parsed[1] == "complete"


def test_parse_felix_comment_non_felix_returns_none():
    assert exc.parse_felix_comment("Random user note") is None
    assert exc.parse_felix_comment("[Other] tag") is None


def test_parse_felix_comment_malformed_returns_none():
    # missing pipe separators
    assert exc.parse_felix_comment("[Felix] 2026-05-15 complete") is None
    # bad date
    assert exc.parse_felix_comment("[Felix] tomorrow | complete") is None


# ---------- End-to-end tests ----------


def test_no_comments_all_ready(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    with _patch_comments_for({100: [], 101: [], 102: []}):
        rc = exc.main([
            "--habit-ids", "100,101,102",
            "--today", TODAY,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test",
        ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["ready_for_checkin"] == [100, 101, 102]
    assert payload["already_addressed"] == []
    assert payload["total_checked"] == 3


def test_complete_today_addressed(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    comments = [{"id": 9876, "comment": f"[Felix] {TODAY} | complete"}]
    with _patch_comments_for({100: comments}):
        rc = exc.main([
            "--habit-ids", "100",
            "--today", TODAY,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test",
        ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["ready_for_checkin"] == []
    assert payload["already_addressed"] == [{"id": 100, "state": "complete", "comment_id": 9876}]


def test_rescheduled_today_addressed(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    comments = [{"id": 9876, "comment": f"[Felix] {TODAY} | rescheduled | this afternoon"}]
    with _patch_comments_for({100: comments}):
        rc = exc.main([
            "--habit-ids", "100", "--today", TODAY,
            "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
        ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["already_addressed"][0]["state"] == "rescheduled"


def test_will_not_do_today_addressed(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    comments = [{"id": 9876, "comment": f"[Felix] {TODAY} | will-not-do | rest day"}]
    with _patch_comments_for({100: comments}):
        rc = exc.main([
            "--habit-ids", "100", "--today", TODAY,
            "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
        ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["already_addressed"][0]["state"] == "will-not-do"


def test_yesterday_comment_ignored(tmp_path, capsys):
    """A complete comment from YESTERDAY does NOT address today's habit."""
    token = _fake_token_file(tmp_path)
    comments = [{"id": 9876, "comment": "[Felix] 2026-05-14 | complete"}]
    with _patch_comments_for({100: comments}):
        rc = exc.main([
            "--habit-ids", "100", "--today", TODAY,
            "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
        ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["ready_for_checkin"] == [100]
    assert payload["already_addressed"] == []


def test_non_felix_comment_ignored(tmp_path, capsys):
    """Comments that don't start with [Felix] are skipped silently."""
    token = _fake_token_file(tmp_path)
    comments = [{"id": 9876, "comment": "Random user note about this habit"}]
    with _patch_comments_for({100: comments}):
        rc = exc.main([
            "--habit-ids", "100", "--today", TODAY,
            "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
        ])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out.splitlines()[0])
    assert payload["ready_for_checkin"] == [100]
    # No WARN for non-Felix comments
    assert "WARN" not in captured.err


def test_multiple_addressed_uses_most_recent(tmp_path, capsys):
    """When multiple Felix comments match today, the highest comment_id wins."""
    token = _fake_token_file(tmp_path)
    comments = [
        {"id": 9876, "comment": f"[Felix] {TODAY} | complete"},
        {"id": 9999, "comment": f"[Felix] {TODAY} | rescheduled | actually moving to PM"},
    ]
    with _patch_comments_for({100: comments}):
        rc = exc.main([
            "--habit-ids", "100", "--today", TODAY,
            "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
        ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["already_addressed"] == [
        {"id": 100, "state": "rescheduled", "comment_id": 9999},
    ]


def test_malformed_felix_prefix_warned(tmp_path, capsys):
    """A comment starting with [Felix] but not matching shape gets a WARN; habit stays ready."""
    token = _fake_token_file(tmp_path)
    comments = [{"id": 9876, "comment": "[Felix] 2026-05-15 complete"}]  # missing pipes
    with _patch_comments_for({100: comments}):
        rc = exc.main([
            "--habit-ids", "100", "--today", TODAY,
            "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
        ])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out.splitlines()[0])
    assert payload["ready_for_checkin"] == [100]
    assert "WARN" in captured.err
    assert "malformed" in captured.err


def test_unknown_state_in_felix_format_warned(tmp_path, capsys):
    """Felix-formatted but unknown state (e.g., 'maybe') triggers WARN, habit stays ready."""
    token = _fake_token_file(tmp_path)
    comments = [{"id": 9876, "comment": f"[Felix] {TODAY} | maybe | unsure"}]
    with _patch_comments_for({100: comments}):
        rc = exc.main([
            "--habit-ids", "100", "--today", TODAY,
            "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
        ])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out.splitlines()[0])
    assert payload["ready_for_checkin"] == [100]
    assert "WARN" in captured.err
    assert "unknown state" in captured.err


def test_empty_habit_ids(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    rc = exc.main([
        "--habit-ids", "", "--today", TODAY,
        "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["ready_for_checkin"] == []
    assert payload["already_addressed"] == []
    assert payload["total_checked"] == 0


def test_vikunja_unreachable_exit_1(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    with patch.object(
        exc.urllib.request, "urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        rc = exc.main([
            "--habit-ids", "100", "--today", TODAY,
            "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
        ])
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERROR" in captured.err


def test_malformed_today_exit_2(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    rc = exc.main([
        "--habit-ids", "100", "--today", "garbage",
        "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test",
    ])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR" in captured.err
