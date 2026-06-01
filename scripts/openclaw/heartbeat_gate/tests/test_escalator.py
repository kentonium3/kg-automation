"""Tests for ``heartbeat_gate.escalator`` (WP-03 T021)."""
from __future__ import annotations

import subprocess
from typing import Any

import pytest

from scripts.openclaw.heartbeat_gate import escalator as _escalator
from scripts.openclaw.heartbeat_gate.escalator import (
    EscalationResult,
    REASON_MAX_LEN,
    escalate,
)


def _patch_which(monkeypatch: pytest.MonkeyPatch, present: bool = True) -> None:
    monkeypatch.setattr(
        _escalator.shutil,
        "which",
        lambda name: "/usr/local/bin/openclaw" if present else None,
    )


def _patch_run(monkeypatch: pytest.MonkeyPatch, *, side_effect: Any) -> None:
    monkeypatch.setattr(_escalator.subprocess, "run", side_effect)


def test_escalate_success_returns_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        assert cmd[0:5] == ["openclaw", "system", "event", "--mode", "now"]
        assert "--json" in cmd
        assert "--text" in cmd
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"event": {"id": "evt_01JABC"}}\n',
            stderr="",
        )

    _patch_run(monkeypatch, side_effect=fake_run)
    result = escalate("Signal whatsapp_creds_restore tripped.")
    assert result.escalated_event_id == "evt_01JABC"
    assert result.error is None


def test_escalate_parses_top_level_id_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)
    _patch_run(
        monkeypatch,
        side_effect=lambda cmd, **kw: subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"id": "evt_top_level"}',
            stderr="",
        ),
    )
    result = escalate("reason")
    assert result.escalated_event_id == "evt_top_level"


def test_escalate_parses_event_id_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)
    _patch_run(
        monkeypatch,
        side_effect=lambda cmd, **kw: subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout='{"event_id": "evt_x"}', stderr=""
        ),
    )
    result = escalate("reason")
    assert result.escalated_event_id == "evt_x"


def test_escalate_truncates_long_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)
    captured_cmd: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        captured_cmd.append(list(cmd))
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout='{"id": "evt_z"}', stderr=""
        )

    _patch_run(monkeypatch, side_effect=fake_run)
    long_reason = "z" * (REASON_MAX_LEN + 200)
    escalate(long_reason)
    # The reason is the last positional after --text.
    text_arg_idx = captured_cmd[0].index("--text") + 1
    assert len(captured_cmd[0][text_arg_idx]) == REASON_MAX_LEN


def test_escalate_empty_reason_returns_error_no_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)

    def fake_run(cmd, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("subprocess.run must not be called")

    _patch_run(monkeypatch, side_effect=fake_run)
    result = escalate("")
    assert result.escalated_event_id is None
    assert result.error and "empty" in result.error.lower()


def test_escalate_binary_not_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=False)
    result = escalate("reason")
    assert result.escalated_event_id is None
    assert result.error and "not found on PATH" in result.error


def test_escalate_subprocess_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)
    _patch_run(
        monkeypatch,
        side_effect=lambda cmd, **kw: subprocess.CompletedProcess(
            args=cmd, returncode=2, stdout="", stderr="openclaw: oops\n"
        ),
    )
    result = escalate("reason")
    assert result.escalated_event_id is None
    assert result.error and "exited 2" in result.error
    assert "openclaw: oops" in result.error


def test_escalate_subprocess_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

    _patch_run(monkeypatch, side_effect=fake_run)
    result = escalate("reason", timeout_seconds=30)
    assert result.escalated_event_id is None
    assert result.error and "timed out" in result.error


def test_escalate_subprocess_os_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("permission denied")

    _patch_run(monkeypatch, side_effect=fake_run)
    result = escalate("reason")
    assert result.escalated_event_id is None
    assert result.error and "OS error" in result.error


def test_escalate_malformed_json_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)
    _patch_run(
        monkeypatch,
        side_effect=lambda cmd, **kw: subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="not json {{{", stderr=""
        ),
    )
    result = escalate("reason")
    assert result.escalated_event_id is None
    assert result.error and "missing event id" in result.error


def test_escalate_stdout_missing_id_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)
    _patch_run(
        monkeypatch,
        side_effect=lambda cmd, **kw: subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout='{"status": "queued"}', stderr=""
        ),
    )
    result = escalate("reason")
    assert result.escalated_event_id is None
    assert result.error


def test_escalate_stdout_array_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)
    _patch_run(
        monkeypatch,
        side_effect=lambda cmd, **kw: subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout='["not", "a", "dict"]', stderr=""
        ),
    )
    result = escalate("reason")
    assert result.escalated_event_id is None


def test_escalate_stdout_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_which(monkeypatch, present=True)
    _patch_run(
        monkeypatch,
        side_effect=lambda cmd, **kw: subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        ),
    )
    result = escalate("reason")
    assert result.error
