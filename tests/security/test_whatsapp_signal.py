"""Tests for credential_health_check.signals.whatsapp_session_signal + duration parser."""
from __future__ import annotations

import subprocess
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from credential_health_check.signals import (
    ActivitySignalFailure,
    MONITOR_ACTIVITY_READERS,
    parse_duration,
    whatsapp_session_signal,
)
from credential_health_check.manifest import Credential

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _credential() -> Credential:
    return Credential(
        name="whatsapp-session",
        review_cadence="monitor-activity",
        storage="~/.openclaw/credentials/whatsapp/",
        expiry_notes="fixture",
        type="session-managed",
    )


def _fake_completed(stdout: str, returncode: int = 0, stderr: str = ""):
    cp = subprocess.CompletedProcess(
        args=["openclaw", "channels", "status"], returncode=returncode
    )
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


# ---------- parse_duration ----------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("38m", timedelta(minutes=38)),
        ("2h 14m", timedelta(hours=2, minutes=14)),
        ("3d 5h", timedelta(days=3, hours=5)),
        ("2w", timedelta(weeks=2)),
        ("38m ago", timedelta(minutes=38)),
        ("14d 5h ago", timedelta(days=14, hours=5)),
        ("45s", timedelta(seconds=45)),
        ("1w 2d 3h 4m 5s", timedelta(weeks=1, days=2, hours=3, minutes=4, seconds=5)),
    ],
)
def test_parse_duration_valid(raw, expected):
    assert parse_duration(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["bogus", "", "   ", "abc 123", "5x", "ago", "1y"],
)
def test_parse_duration_invalid(raw):
    assert parse_duration(raw) is None


def test_parse_duration_two_weeks_equals_14_days():
    """Boundary case: 14-day threshold; '2w' is exactly at threshold."""
    assert parse_duration("2w") == timedelta(days=14)


# ---------- whatsapp_session_signal ----------


def test_healthy_fixture_returns_none():
    stdout = (FIXTURES / "openclaw-channels-status-healthy.txt").read_text()
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed(stdout),
    ):
        assert whatsapp_session_signal(_credential()) is None


def test_not_connected_fixture_alerts():
    stdout = (FIXTURES / "openclaw-channels-status-not-connected.txt").read_text()
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed(stdout),
    ):
        failure = whatsapp_session_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "connected" in failure.reason.lower()


def test_stale_in_activity_alerts():
    stdout = (FIXTURES / "openclaw-channels-status-stale.txt").read_text()
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed(stdout),
    ):
        failure = whatsapp_session_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "14" in failure.reason
    # The reason should mention staleness, threshold, or activity.
    assert any(
        keyword in failure.reason.lower() for keyword in ("stale", "threshold", "activity")
    )


def test_subprocess_nonzero_exit_alerts():
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed("", returncode=3, stderr="gateway unreachable"),
    ):
        failure = whatsapp_session_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "exit" in failure.summary.lower()
    assert "gateway" in failure.reason.lower()


def test_subprocess_timeout_alerts():
    with patch(
        "credential_health_check.signals.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["openclaw"], timeout=10),
    ):
        failure = whatsapp_session_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "timeout" in failure.summary.lower()


def test_channel_missing_from_output_alerts():
    stdout = "Checking channel status…\nGateway reachable.\n\n(no channels configured)\n"
    with patch(
        "credential_health_check.signals.subprocess.run",
        return_value=_fake_completed(stdout),
    ):
        failure = whatsapp_session_signal(_credential())
    assert isinstance(failure, ActivitySignalFailure)
    assert "channel" in failure.reason.lower()
    assert "missing" in failure.summary.lower()


def test_whatsapp_registered_in_monitor_activity_readers():
    assert "whatsapp-session" in MONITOR_ACTIVITY_READERS
    assert MONITOR_ACTIVITY_READERS["whatsapp-session"] is whatsapp_session_signal
