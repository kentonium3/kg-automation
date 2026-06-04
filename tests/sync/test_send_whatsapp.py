"""Tests for scripts/sync/send_whatsapp.py (WP04 / T016).

Mocks ``subprocess.run`` and ``os.environ`` to drive the wrapper without
invoking the real openclaw CLI.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from scripts.sync import send_whatsapp as sw


# ---------------------------------------------------------------------------
# Fixture: mock subprocess.run
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_run(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("scripts.sync.send_whatsapp.subprocess.run", mock)
    return mock


# ===========================================================================
# Group 1 — Happy path
# ===========================================================================


class TestSendHappyPath:
    def test_exit_0_returns_success(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        result = sw.send(message="hi", recipient="+15551234567")
        assert result.success is True
        assert result.exit_code == 0
        assert result.stderr is None


# ===========================================================================
# Group 2 — Subprocess argument order matches contract
# ===========================================================================


class TestArgumentOrder:
    def test_args_match_sync_heartbeat_precedent(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        sw.send(message="msg", recipient="+15551234567")
        called_args = mock_run.call_args[0][0]
        # Exact precedence per contracts/whatsapp-send.md.
        assert called_args == [
            "openclaw", "agent",
            "--agent", "main",
            "--message", "msg",
            "--deliver",
            "--channel", "whatsapp",
            "--to", "+15551234567",
        ]

    def test_custom_agent_propagates(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        sw.send(message="x", recipient="+15551234567", agent="custom-agent")
        called_args = mock_run.call_args[0][0]
        assert "custom-agent" in called_args
        # Position of agent name follows --agent.
        idx = called_args.index("--agent")
        assert called_args[idx + 1] == "custom-agent"


# ===========================================================================
# Group 3 — Failure paths
# ===========================================================================


class TestFailurePaths:
    def test_nonzero_exit_returns_failure_with_stderr(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="something broke"
        )
        result = sw.send(message="x", recipient="+15551234567")
        assert result.success is False
        assert result.exit_code == 1
        assert result.stderr == "something broke"

    def test_timeout_returns_minus_1(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=60)
        result = sw.send(message="x", recipient="+15551234567", timeout_seconds=60)
        assert result.success is False
        assert result.exit_code == -1
        assert "timeout after 60s" in result.stderr

    def test_file_not_found_returns_minus_2(self, mock_run):
        mock_run.side_effect = FileNotFoundError("no openclaw")
        result = sw.send(message="x", recipient="+15551234567")
        assert result.success is False
        assert result.exit_code == -2
        assert "openclaw binary not found" in result.stderr

    def test_empty_stderr_becomes_none(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=2, stdout="", stderr=""
        )
        result = sw.send(message="x", recipient="+15551234567")
        # Empty stderr → None per the contract.
        assert result.stderr is None
        assert result.exit_code == 2


# ===========================================================================
# Group 4 — Dry-run path
# ===========================================================================


class TestDryRun:
    def test_dry_run_does_not_invoke_subprocess(self, mock_run, capsys):
        result = sw.send(message="hello world", recipient="+15551234567", dry_run=True)
        assert mock_run.call_count == 0
        assert result.success is True
        # Logs the would-send to stderr.
        assert "[whatsapp send: dry-run]" in capsys.readouterr().err

    def test_dry_run_returns_success_zero(self, mock_run):
        result = sw.send(message="x", recipient="+15551234567", dry_run=True)
        assert result.exit_code == 0
        assert result.stderr is None


# ===========================================================================
# Group 5 — resolve_recipient
# ===========================================================================


class TestResolveRecipient:
    def test_cli_arg_wins(self, monkeypatch):
        monkeypatch.setenv(sw.WHATSAPP_RECIPIENT_ENV_VAR, "+19998887777")
        assert sw.resolve_recipient("+15551234567") == "+15551234567"

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setenv(sw.WHATSAPP_RECIPIENT_ENV_VAR, "+19998887777")
        assert sw.resolve_recipient(None) == "+19998887777"

    def test_missing_both_raises(self, monkeypatch):
        monkeypatch.delenv(sw.WHATSAPP_RECIPIENT_ENV_VAR, raising=False)
        with pytest.raises(OSError, match="recipient unresolved"):
            sw.resolve_recipient(None)

    def test_empty_cli_falls_through_to_env(self, monkeypatch):
        monkeypatch.setenv(sw.WHATSAPP_RECIPIENT_ENV_VAR, "+19998887777")
        assert sw.resolve_recipient("") == "+19998887777"


# ===========================================================================
# Group 6 — format_message
# ===========================================================================


class TestFormatMessage:
    def test_downstream_uses_orange_marker(self):
        msg = sw.format_message(
            diff_field="due_date",
            vikunja_value="2026-06-10",
            felix_cached_value="2026-06-08",
            vikunja_entity_id=27,
            task_title="Buy gift",
            is_downstream=True,
            is_private=False,
        )
        assert msg.split("\n")[0] == sw.MARKER_UNSAFE_DOWNSTREAM
        assert "🟠" in msg

    def test_non_downstream_uses_yellow_marker(self):
        msg = sw.format_message(
            diff_field="labels",
            vikunja_value=["a"],
            felix_cached_value=[],
            vikunja_entity_id=27,
            task_title="x",
            is_downstream=False,
            is_private=False,
        )
        assert msg.split("\n")[0] == sw.MARKER_UNSAFE_CAUTION
        assert "🟡" in msg

    def test_includes_task_id_and_title(self):
        msg = sw.format_message(
            diff_field="title",
            vikunja_value="new",
            felix_cached_value="old",
            vikunja_entity_id=42,
            task_title="My Task",
            is_downstream=False,
            is_private=False,
        )
        assert "Task #42: My Task" in msg

    def test_truncates_long_title(self):
        long_title = "X" * 200
        msg = sw.format_message(
            diff_field="title",
            vikunja_value="x",
            felix_cached_value="y",
            vikunja_entity_id=1,
            task_title=long_title,
            is_downstream=False,
            is_private=False,
        )
        line2 = msg.split("\n")[1]
        # Truncated at 60 chars; ends with ellipsis.
        assert "…" in line2
        # Line 2 is "Task #1: <truncated_title>"; bounded length.
        assert len(line2) <= len("Task #1: ") + sw.TITLE_TRUNCATE_LEN

    def test_unknown_title_fallback(self):
        msg = sw.format_message(
            diff_field="title",
            vikunja_value="x",
            felix_cached_value="y",
            vikunja_entity_id=1,
            task_title=None,
            is_downstream=False,
            is_private=False,
        )
        assert "<unknown task>" in msg

    def test_diff_line_uses_json_repr(self):
        msg = sw.format_message(
            diff_field="due_date",
            vikunja_value="2026-06-10T17:00:00Z",
            felix_cached_value="2026-06-08T17:00:00Z",
            vikunja_entity_id=27,
            task_title="x",
            is_downstream=True,
            is_private=False,
        )
        line3 = msg.split("\n")[2]
        # JSON-encoded string values are quoted.
        assert '"2026-06-10T17:00:00Z"' in line3
        assert "→" in line3

    def test_private_task_fully_redacted(self):
        msg = sw.format_message(
            diff_field="title",
            vikunja_value="real value",
            felix_cached_value="other",
            vikunja_entity_id=999,
            task_title="Sensitive",
            is_downstream=True,
            is_private=True,
        )
        # Task ID is fine to expose (no semantic content).
        assert "Task #999:" in msg
        # But title and diff values are redacted.
        assert "<redacted>" in msg
        assert "Sensitive" not in msg
        assert "real value" not in msg
