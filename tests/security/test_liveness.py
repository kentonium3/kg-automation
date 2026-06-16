"""Tests for credential_health_check.liveness.probe_oauth_liveness.

13 contract test cases per:
  kitty-specs/credential-liveness-probe-01KTP9M8/contracts/liveness-probe-function.md
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    """Build a test credential with a real keyring file for stat() calls."""
    keyring = tmp_path / "keyring_file"
    keyring.write_bytes(b"")  # real file for stat()
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


def _set_keyring_mtime(keyring_path: Path, dt: datetime) -> None:
    """Set both atime and mtime of keyring_path to the given UTC datetime."""
    ts = dt.timestamp()
    os.utime(str(keyring_path), (ts, ts))


# ---------- 13 Contract tests ----------

def test_alive_returns_none(tmp_path, monkeypatch):
    """T-01: rc=0, empty stderr → None."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(subprocess, "run", make_subprocess_run(returncode=0))
    assert probe_oauth_liveness(cred) is None


def test_dead_routine_7day(tmp_path, monkeypatch):
    """T-02: invalid_grant + mtime = now - 6.9 days → dead-routine-7day."""
    cred = make_credential(tmp_path)
    now = datetime.now(timezone.utc)
    # mtime+7d will be ~6.9 days + 7 = 13.9 days from epoch, but 0.1 days ahead of now
    mtime_dt = now - timedelta(days=6, hours=21, minutes=36)  # now - 6.9 days
    _set_keyring_mtime(Path(cred.liveness_probe.keyring_file), mtime_dt)

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred, now_utc=now)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead-routine-7day"


def test_dead_unexpected_too_early(tmp_path, monkeypatch):
    """T-03: invalid_grant + mtime = now - 3 days → dead-unexpected (too early)."""
    cred = make_credential(tmp_path)
    now = datetime.now(timezone.utc)
    mtime_dt = now - timedelta(days=3)
    _set_keyring_mtime(Path(cred.liveness_probe.keyring_file), mtime_dt)

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred, now_utc=now)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead-unexpected"


def test_dead_unexpected_too_late(tmp_path, monkeypatch):
    """T-04: invalid_grant + mtime = now - 9 days → dead-unexpected (too late)."""
    cred = make_credential(tmp_path)
    now = datetime.now(timezone.utc)
    mtime_dt = now - timedelta(days=9)
    _set_keyring_mtime(Path(cred.liveness_probe.keyring_file), mtime_dt)

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred, now_utc=now)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead-unexpected"


def test_routine_boundary_just_inside(tmp_path, monkeypatch):
    """T-05: mtime = now - 7d - 23h → delta = 23h → inside ±24h → dead-routine-7day."""
    cred = make_credential(tmp_path)
    now = datetime.now(timezone.utc)
    # mtime + 7d = now - 23h → delta = 23h ≤ 24h → routine
    mtime_dt = now - timedelta(days=7, hours=23)
    _set_keyring_mtime(Path(cred.liveness_probe.keyring_file), mtime_dt)

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred, now_utc=now)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead-routine-7day"


def test_routine_boundary_just_outside(tmp_path, monkeypatch):
    """T-06: mtime = now - 7d - 25h → delta = 25h → outside ±24h → dead-unexpected."""
    cred = make_credential(tmp_path)
    now = datetime.now(timezone.utc)
    # mtime + 7d = now - 25h → delta = 25h > 24h → unexpected
    mtime_dt = now - timedelta(days=7, hours=25)
    _set_keyring_mtime(Path(cred.liveness_probe.keyring_file), mtime_dt)

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred, now_utc=now)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead-unexpected"


def test_probe_timeout(tmp_path, monkeypatch):
    """T-07: TimeoutExpired → probe-error with 15s in reason."""
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
    """T-08: FileNotFoundError → probe-error with 'gog binary not found' in reason."""
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
    """T-09: rc=2, stderr without invalid_grant → probe-error with exit code 2 in reason."""
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
    """T-10: dead-routine-7day result carries the configured recovery_command."""
    cred = make_credential(tmp_path)
    now = datetime.now(timezone.utc)
    mtime_dt = now - timedelta(days=7)  # exactly at boundary; delta=0 → routine
    _set_keyring_mtime(Path(cred.liveness_probe.keyring_file), mtime_dt)

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred, now_utc=now)
    assert isinstance(result, LivenessResult)
    assert result.recovery_command == cred.liveness_probe.recovery_command


def test_recovery_command_none_in_probe_error(tmp_path, monkeypatch):
    """T-11: probe-error result has recovery_command=None."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=2, stderr="boom"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.recovery_command is None


def test_raises_if_liveness_probe_disabled(tmp_path):
    """T-12: enabled=False → ValueError (caller filtered incorrectly)."""
    cred = make_credential(tmp_path, enabled=False)
    with pytest.raises(ValueError, match="no enabled liveness_probe block"):
        probe_oauth_liveness(cred)


def test_probed_at_is_utc(tmp_path, monkeypatch):
    """T-13: any case → result.probed_at.tzinfo == timezone.utc."""
    cred = make_credential(tmp_path)
    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=2, stderr="boom"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.probed_at.tzinfo == timezone.utc


def test_keyring_missing_is_probe_error(tmp_path, monkeypatch):
    """Supplement: invalid_grant but keyring file absent → probe-error (not dead)."""
    cred = make_credential(tmp_path)
    # Remove the keyring file so stat() raises FileNotFoundError.
    Path(cred.liveness_probe.keyring_file).unlink()

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "probe-error"
    assert "keyring file not found" in result.reason
    assert result.recovery_command is None


# ---------- reauth_marker_glob tests (#616) ----------

def make_credential_with_reauth_marker(
    tmp_path: Path,
    *,
    marker_files: list[str],
    enabled: bool = True,
) -> _CredentialStub:
    """Credential whose liveness_probe has a reauth_marker_glob set.

    The keyring file mtime is left at NOW (simulating a recently-touched
    keyring — the real-world condition where every probe tick updates it
    and the keyring-fallback heuristic always says 'unexpected'). The
    marker files' mtimes are what each test drives.
    """
    keyring = tmp_path / "keyring_file"
    keyring.write_bytes(b"")  # mtime = now
    for name in marker_files:
        (tmp_path / name).write_text("")  # mtime = now (caller overwrites)
    return _CredentialStub(
        name="gog-credentials-keyring",
        liveness_probe=LivenessProbeConfig(
            enabled=enabled,
            gog_account="kentgale@gmail.com",
            keyring_file=str(keyring),
            recovery_command=RECOVERY_CMD,
            reauth_marker_glob=str(tmp_path / "oauth-manual-state-*.json"),
        ),
    )


def _set_mtime(path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    os.utime(str(path), (ts, ts))


def test_reauth_marker_drives_routine_classification(tmp_path, monkeypatch):
    """#616: reauth marker at ~6.9d → dead-routine-7day even when keyring is fresh."""
    cred = make_credential_with_reauth_marker(
        tmp_path, marker_files=["oauth-manual-state-abc.json"]
    )
    now = datetime.now(timezone.utc)
    # Keyring is fresh — this is the production state every 6h.
    _set_mtime(Path(cred.liveness_probe.keyring_file), now)
    # Marker says last re-auth was 6.9 days ago — within the ±24h routine window.
    _set_mtime(tmp_path / "oauth-manual-state-abc.json", now - timedelta(days=6, hours=21, minutes=36))

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead-routine-7day"
    # Reason must label the baseline source so operators know which clock fired.
    assert "reauth+7d=" in result.reason


def test_reauth_marker_drives_unexpected_classification(tmp_path, monkeypatch):
    """#616: reauth marker at 3d (mid-week token death) → dead-unexpected."""
    cred = make_credential_with_reauth_marker(
        tmp_path, marker_files=["oauth-manual-state-abc.json"]
    )
    now = datetime.now(timezone.utc)
    _set_mtime(Path(cred.liveness_probe.keyring_file), now)
    _set_mtime(tmp_path / "oauth-manual-state-abc.json", now - timedelta(days=3))

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead-unexpected"
    assert "reauth+7d=" in result.reason


def test_reauth_marker_picks_max_mtime_across_multiple_files(tmp_path, monkeypatch):
    """When the glob matches several files, the newest mtime wins."""
    cred = make_credential_with_reauth_marker(
        tmp_path,
        marker_files=[
            "oauth-manual-state-old.json",
            "oauth-manual-state-new.json",
        ],
    )
    now = datetime.now(timezone.utc)
    _set_mtime(Path(cred.liveness_probe.keyring_file), now)
    _set_mtime(tmp_path / "oauth-manual-state-old.json", now - timedelta(days=15))
    _set_mtime(
        tmp_path / "oauth-manual-state-new.json",
        now - timedelta(days=6, hours=21, minutes=36),
    )

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    # Newer marker (6.9d) drives the result → routine, not unexpected (15d).
    assert result.classification == "dead-routine-7day"


def test_reauth_marker_no_match_falls_back_to_keyring(tmp_path, monkeypatch):
    """If the glob matches nothing, behaviour falls back to keyring mtime."""
    cred = make_credential_with_reauth_marker(tmp_path, marker_files=[])
    now = datetime.now(timezone.utc)
    # Keyring at 6.9d → routine via fallback.
    _set_mtime(
        Path(cred.liveness_probe.keyring_file),
        now - timedelta(days=6, hours=21, minutes=36),
    )

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead-routine-7day"
    # Fallback path labels the source.
    assert "keyring+7d=" in result.reason


def test_keyring_fallback_message_labels_source(tmp_path, monkeypatch):
    """#616 regression pin: without reauth_marker_glob, message says 'keyring+7d='."""
    cred = make_credential(tmp_path)  # no reauth_marker_glob set
    now = datetime.now(timezone.utc)
    _set_keyring_mtime(
        Path(cred.liveness_probe.keyring_file),
        now - timedelta(days=3),
    )

    monkeypatch.setattr(
        subprocess, "run",
        make_subprocess_run(returncode=1, stderr="invalid_grant"),
    )
    result = probe_oauth_liveness(cred)
    assert isinstance(result, LivenessResult)
    assert result.classification == "dead-unexpected"
    assert "keyring+7d=" in result.reason
