"""Tests for credential_health_check.liveness.probe_oauth_liveness.

Post-#731: the probe classifies any ``invalid_grant`` as a single ``dead`` state.
The routine/unexpected 7-day split and the #616 reauth-marker baseline are gone,
so the probe no longer consults the keyring mtime for classification.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
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
    expiry_notes: str = "oauth2 gog token"
    liveness_probe: Optional[LivenessProbeConfig] = None


# ---------- Fixtures ----------

RECOVERY_CMD = (
    "ssh -t office2-claude "
    "/home/claude/kg-automation/scripts/security/gog-reauth.sh"
)


def make_credential(tmp_path: Path, *, enabled: bool = True) -> _CredentialStub:
    """Build a test credential with a keyring file present on disk."""
    keyring = tmp_path / "keyring_file"
    keyring.write_bytes(b"")
    return _CredentialStub(
        name="gog-credentials-keyring",
        liveness_probe=LivenessProbeConfig(
            enabled=enabled,
            gog_account="kentgale@gmail.com",
            keyring_file=str(keyring),
            recovery_command=RECOVERY_CMD,
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

def test_alive_returns_none(tmp_path, monkeypatch):
    """rc=0, empty stderr → None (alive)."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(subprocess, "run", make_subprocess_run(returncode=0))
    assert probe_oauth_liveness(cred) is None


def test_invalid_grant_is_dead(tmp_path, monkeypatch):
    """invalid_grant → single `dead` classification; reason names no 7-day/Testing concept."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead"
    assert result.recovery_command == cred.liveness_probe.recovery_command
    lowered = result.reason.lower()
    for forbidden in ("7-day", "testing", "reauth", "keyring+", "cycle boundary"):
        assert forbidden not in lowered


def test_invalid_grant_keyring_missing_is_dead(tmp_path, monkeypatch):
    """Post-#731 the keyring is not consulted: invalid_grant is `dead` even if the file is gone."""
    cred = make_credential(tmp_path)
    # Remove the keyring file — it must no longer affect classification.
    Path(cred.liveness_probe.keyring_file).unlink()
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead"
    assert result.recovery_command == cred.liveness_probe.recovery_command


def test_probe_timeout(tmp_path, monkeypatch):
    """TimeoutExpired → probe-error with 15s in reason."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(side_effect=subprocess.TimeoutExpired(cmd=[], timeout=15)),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "probe-error"
    assert "15s" in result.reason


def test_probe_missing_binary(tmp_path, monkeypatch):
    """FileNotFoundError → probe-error with 'gog binary not found' in reason."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(side_effect=FileNotFoundError()),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "probe-error"
    assert "gog binary not found" in result.reason


def test_probe_other_failure(tmp_path, monkeypatch):
    """rc=2, stderr without invalid_grant → probe-error with the exit code in reason."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=2, stderr="boom"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "probe-error"
    assert "2" in result.reason


def test_recovery_command_in_dead_result(tmp_path, monkeypatch):
    """A dead result carries the configured recovery_command."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead"
    assert result.recovery_command == cred.liveness_probe.recovery_command


def test_recovery_command_none_in_probe_error(tmp_path, monkeypatch):
    """probe-error result has recovery_command=None."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=2, stderr="boom"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.recovery_command is None


def test_raises_if_liveness_probe_disabled(tmp_path):
    """enabled=False → ValueError (caller filtered incorrectly)."""
    cred = make_credential(tmp_path, enabled=False)
    with pytest.raises(ValueError, match="no enabled liveness_probe block"):
        probe_oauth_liveness(cred)


def test_probed_at_is_utc(tmp_path, monkeypatch):
    """Any result → result.probed_at.tzinfo == timezone.utc."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=2, stderr="boom"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.probed_at.tzinfo == timezone.utc
