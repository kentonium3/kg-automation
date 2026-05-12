"""Tests for credential_health_check.signals.tailscale_auth_signal."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from credential_health_check.signals import (
    ActivitySignalFailure,
    tailscale_auth_signal,
    MONITOR_ACTIVITY_READERS,
)
from credential_health_check.manifest import Credential

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _credential() -> Credential:
    return Credential(
        name="tailscale-auth",
        review_cadence="monitor-activity",
        storage="managed by tailscaled",
        expiry_notes="fixture",
        type="system-managed",
    )


def _fake_completed(stdout: str, returncode: int = 0, stderr: str = ""):
    cp = subprocess.CompletedProcess(args=["tailscale", "status", "--json"], returncode=returncode)
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def test_running_fixture_returns_none():
    stdout = (FIXTURES / "tailscale-status-running.json").read_text()
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed(stdout),
    ):
        assert tailscale_auth_signal(_credential()) is None


def test_needs_login_fixture_alerts():
    stdout = (FIXTURES / "tailscale-status-needs-login.json").read_text()
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed(stdout),
    ):
        failure = tailscale_auth_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert failure.credential_name == "tailscale-auth"
    assert "NeedsLogin" in failure.reason
    assert "tailscale" in failure.summary.lower()


def test_stopped_fixture_alerts():
    stdout = (FIXTURES / "tailscale-status-stopped.json").read_text()
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed(stdout),
    ):
        failure = tailscale_auth_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "Stopped" in failure.reason


def test_subprocess_nonzero_exit_alerts():
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed("", returncode=2, stderr="boom"),
    ):
        failure = tailscale_auth_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "exit" in failure.summary.lower()
    assert "boom" in failure.reason


def test_subprocess_timeout_alerts():
    with patch(
        "credential_health_check.signals.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["tailscale"], timeout=5),
    ):
        failure = tailscale_auth_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "timeout" in failure.summary.lower()


def test_binary_missing_alerts():
    with patch(
        "credential_health_check.signals.subprocess.run",
        side_effect=FileNotFoundError(),
    ):
        failure = tailscale_auth_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "binary missing" in failure.summary


def test_malformed_json_alerts():
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed("not valid {{{{"),
    ):
        failure = tailscale_auth_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "JSON" in failure.summary or "JSON" in failure.reason


def test_tailscale_registered_in_monitor_activity_readers():
    assert "tailscale-auth" in MONITOR_ACTIVITY_READERS
    assert MONITOR_ACTIVITY_READERS["tailscale-auth"] is tailscale_auth_signal
