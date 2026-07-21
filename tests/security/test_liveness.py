"""Tests for credential_health_check.liveness.probe_oauth_liveness.

#845: the probe is generic/command-based. It runs the credential's configured
``command`` and classifies by exit code — 0 = alive, a code in
``dead_exit_codes`` = dead, anything else (or a failure to execute the command)
= probe-error. Every terminal path emits exactly one marker token.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import timezone
from typing import Optional

import pytest

from credential_health_check.liveness import (
    LivenessResult,
    probe_oauth_liveness,
)
from credential_health_check.manifest import LivenessProbeConfig


# ---------- Synthetic Credential stub ----------

@dataclass(frozen=True)
class _CredentialStub:
    """Minimal credential with liveness_probe support for tests."""

    name: str
    review_cadence: str = "monitor-activity"
    storage: str = "keyring"
    expiry_notes: str = "credential with a liveness probe"
    liveness_probe: Optional[LivenessProbeConfig] = None


# ---------- Fixtures ----------

RECOVERY_CMD = "Re-mint the token on the Mac. See docs/runbooks/calendar-helper-ops.md."
PROBE_COMMAND = (
    "/data/services/openclaw/felix-calendar/venv/bin/python",
    "-m",
    "scripts.google.calendar_helper",
    "--self-check",
    "--account",
    "personal",
)


def make_credential(
    *, enabled: bool = True, dead_exit_codes=(3,), timeout_seconds: int = 20
) -> _CredentialStub:
    """Build a test credential with a generic command-based liveness probe."""
    return _CredentialStub(
        name="felix-google-personal-calendar",
        liveness_probe=LivenessProbeConfig(
            enabled=enabled,
            command=PROBE_COMMAND,
            dead_exit_codes=tuple(dead_exit_codes),
            recovery_command=RECOVERY_CMD,
            timeout_seconds=timeout_seconds,
        ),
    )


def make_subprocess_run(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    side_effect: Optional[BaseException] = None,
):
    """Return a fake subprocess.run callable suitable for monkeypatching."""

    def fake_run(*args, **kwargs):
        if side_effect is not None:
            raise side_effect
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    return fake_run


# ---------- Contract tests ----------

def test_alive_returns_none(monkeypatch):
    """rc=0 → None (alive)."""
    cred = make_credential()
    monkeypatch.setattr(subprocess, "run", make_subprocess_run(returncode=0))
    assert probe_oauth_liveness(cred) is None


def test_dead_exit_code_is_dead(monkeypatch):
    """rc in dead_exit_codes → `dead`, carrying the recovery_command."""
    cred = make_credential(dead_exit_codes=(3,))
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=3, stderr="ERROR: auth_failed no token.json"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead"
    assert result.recovery_command == cred.liveness_probe.recovery_command


def test_multiple_dead_exit_codes(monkeypatch):
    """Any code in dead_exit_codes counts as dead."""
    cred = make_credential(dead_exit_codes=(3, 4))
    monkeypatch.setattr(subprocess, "run", make_subprocess_run(returncode=4))
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead"


def test_nonzero_not_in_dead_is_probe_error(monkeypatch):
    """A non-zero exit NOT in dead_exit_codes → probe-error, never dead.

    This is the HIGH-2 guard: an operational/dependency fault (e.g. the calendar
    helper exiting 1 because its venv is broken) must NOT be reported as a dead
    credential.
    """
    cred = make_credential(dead_exit_codes=(3,))
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="ERROR: googleapiclient is not installed"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "probe-error"
    assert "1" in result.reason


def test_probe_timeout(monkeypatch):
    """TimeoutExpired → probe-error naming the configured timeout."""
    cred = make_credential(timeout_seconds=20)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(side_effect=subprocess.TimeoutExpired(cmd=[], timeout=20)),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "probe-error"
    assert "20s" in result.reason


def test_probe_command_not_found_is_probe_error(monkeypatch):
    """FileNotFoundError (missing interpreter) → probe-error, NOT dead."""
    cred = make_credential()
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(side_effect=FileNotFoundError("no such file")),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "probe-error"
    assert "could not be executed" in result.reason


def test_probe_permission_error_is_probe_error(monkeypatch):
    """PermissionError (an OSError subclass) → probe-error."""
    cred = make_credential()
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(side_effect=PermissionError("denied")),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "probe-error"


def test_probe_unexpected_exception_is_probe_error(monkeypatch):
    """A defensive catch: any unexpected exception → probe-error, never dead."""
    cred = make_credential()
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(side_effect=RuntimeError("kaboom")),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "probe-error"
    assert "kaboom" in result.reason


def test_recovery_command_none_in_probe_error(monkeypatch):
    """probe-error result has recovery_command=None."""
    cred = make_credential(dead_exit_codes=(3,))
    monkeypatch.setattr(subprocess, "run", make_subprocess_run(returncode=2, stderr="boom"))
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.recovery_command is None


def test_uses_configured_command_and_timeout(monkeypatch):
    """The runner executes exactly the configured argv with the configured timeout."""
    captured = {}

    def fake_run(*args, **kwargs):
        captured["argv"] = args[0]
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    cred = make_credential(timeout_seconds=17)
    monkeypatch.setattr(subprocess, "run", fake_run)
    probe_oauth_liveness(cred)
    assert captured["argv"] == list(PROBE_COMMAND)
    assert captured["timeout"] == 17


def test_raises_if_liveness_probe_disabled():
    """enabled=False → ValueError (caller filtered incorrectly)."""
    cred = make_credential(enabled=False)
    with pytest.raises(ValueError, match="no enabled liveness_probe block"):
        probe_oauth_liveness(cred)


def test_probed_at_is_utc(monkeypatch):
    """Any result → result.probed_at.tzinfo == timezone.utc."""
    cred = make_credential(dead_exit_codes=(3,))
    monkeypatch.setattr(subprocess, "run", make_subprocess_run(returncode=2, stderr="boom"))
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.probed_at.tzinfo == timezone.utc
