"""Tests for credential_health_check.orchestrator.run_cycle."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from credential_health_check.github_writer import GitHubWriteError
from credential_health_check.manifest import ManifestUnreadableError
from credential_health_check.orchestrator import CycleResult, run_cycle
from credential_health_check.signals import ActivitySignalFailure
from credential_health_check.vikunja_writer import VikunjaWriteError

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# Most tests patch the writers/readers in the orchestrator's namespace,
# not the underlying CLI/HTTP boundaries.

def _patch_paths():
    return {
        "dedup_check": "credential_health_check.orchestrator.dedup_check",
        "create_issue": "credential_health_check.orchestrator.create_issue",
        "create_task": "credential_health_check.orchestrator.create_task",
        "load_token": "credential_health_check.orchestrator.load_token",
        "lookup_inbox_project_id": "credential_health_check.orchestrator.lookup_inbox_project_id",
        "MONITOR_ACTIVITY_READERS": "credential_health_check.orchestrator.MONITOR_ACTIVITY_READERS",
    }


# ---------- Happy path: nothing due ----------


def test_cycle_no_credentials_due_files_nothing():
    p = _patch_paths()
    with (
        patch(p["dedup_check"], return_value=[]),
        patch(p["create_issue"], return_value=999) as mock_issue,
        patch(p["create_task"], return_value=999) as mock_task,
        patch(p["load_token"], return_value="t"),
        patch(p["lookup_inbox_project_id"], return_value=1),
        patch(p["MONITOR_ACTIVITY_READERS"], new={}),  # disable signal readers
    ):
        result = run_cycle(
            str(FIXTURES / "manifest-valid.json"),
            today=date(2026, 5, 11),  # at this date, no credentials in valid manifest are inside warning window
        )
    assert isinstance(result, CycleResult)
    assert result.cadence_alerts_filed == 0
    assert result.staleness_alerts_filed == 0
    mock_issue.assert_not_called()
    mock_task.assert_not_called()


# ---------- Near-expiry path ----------


def test_cycle_near_expiry_files_paired_alert():
    """Vikunja task is created BEFORE GitHub issue."""
    call_order: list[str] = []
    p = _patch_paths()

    def fake_create_task(*args, **kwargs):
        call_order.append("task")
        return 88

    def fake_create_issue(*args, **kwargs):
        call_order.append("issue")
        return 77

    with (
        patch(p["dedup_check"], return_value=[]),
        patch(p["create_task"], side_effect=fake_create_task),
        patch(p["create_issue"], side_effect=fake_create_issue),
        patch(p["load_token"], return_value="t"),
        patch(p["lookup_inbox_project_id"], return_value=1),
        patch(p["MONITOR_ACTIVITY_READERS"], new={}),
    ):
        result = run_cycle(
            str(FIXTURES / "manifest-near-expiry.json"),
            today=date(2026, 5, 11),
        )
    assert result.cadence_alerts_filed == 1
    # Ordering: task first, then issue (so issue body can reference task ID).
    assert call_order[0] == "task"
    assert call_order[1] == "issue"


# ---------- Dedup ----------


def test_cycle_dedup_skips_already_open():
    p = _patch_paths()
    with (
        patch(p["dedup_check"], return_value=[42]),  # any prefix returns an existing issue
        patch(p["create_task"]) as mock_task,
        patch(p["create_issue"]) as mock_issue,
        patch(p["load_token"], return_value="t"),
        patch(p["lookup_inbox_project_id"], return_value=1),
        patch(p["MONITOR_ACTIVITY_READERS"], new={}),
    ):
        result = run_cycle(
            str(FIXTURES / "manifest-near-expiry.json"),
            today=date(2026, 5, 11),
        )
    assert result.cadence_alerts_filed == 0
    assert result.alerts_deduped >= 1
    mock_task.assert_not_called()
    mock_issue.assert_not_called()


# ---------- Vikunja failure ----------


def test_cycle_vikunja_failure_skips_credential():
    p = _patch_paths()
    with (
        patch(p["dedup_check"], return_value=[]),
        patch(p["create_task"], side_effect=VikunjaWriteError("boom")),
        patch(p["create_issue"]) as mock_issue,
        patch(p["load_token"], return_value="t"),
        patch(p["lookup_inbox_project_id"], return_value=1),
        patch(p["MONITOR_ACTIVITY_READERS"], new={}),
    ):
        result = run_cycle(
            str(FIXTURES / "manifest-near-expiry.json"),
            today=date(2026, 5, 11),
        )
    # No GitHub issue filed when Vikunja failed first.
    mock_issue.assert_not_called()
    assert result.cadence_alerts_filed == 0
    assert any("vikunja" in e for e in result.errors)


# ---------- GitHub failure after Vikunja succeeded (orphan) ----------


def test_cycle_github_failure_after_task_orphans_task():
    p = _patch_paths()
    with (
        patch(p["dedup_check"], return_value=[]),
        patch(p["create_task"], return_value=88),
        patch(p["create_issue"], side_effect=GitHubWriteError("issue boom")),
        patch(p["load_token"], return_value="t"),
        patch(p["lookup_inbox_project_id"], return_value=1),
        patch(p["MONITOR_ACTIVITY_READERS"], new={}),
    ):
        result = run_cycle(
            str(FIXTURES / "manifest-near-expiry.json"),
            today=date(2026, 5, 11),
        )
    assert result.cadence_alerts_filed == 0
    assert any("orphan" in e.lower() for e in result.errors)


# ---------- Manifest unreadable ----------


def test_cycle_manifest_unreadable_propagates():
    with pytest.raises(ManifestUnreadableError):
        run_cycle(str(FIXTURES / "manifest-invalid-json.txt"), today=date(2026, 5, 11))


# ---------- Manifest quality batching ----------


def test_cycle_manifest_quality_batched():
    p = _patch_paths()
    with (
        patch(p["dedup_check"], return_value=[]),
        patch(p["create_task"]),
        patch(p["create_issue"], return_value=555),
        patch(p["load_token"], return_value="t"),
        patch(p["lookup_inbox_project_id"], return_value=1),
        patch(p["MONITOR_ACTIVITY_READERS"], new={}),
    ):
        result = run_cycle(
            str(FIXTURES / "manifest-missing-last-reviewed.json"),
            today=date(2026, 5, 11),
        )
    assert result.manifest_quality_issue_filed is True


# ---------- Dry run ----------


def test_cycle_dry_run_does_not_call_writers():
    p = _patch_paths()
    with (
        patch(p["dedup_check"], return_value=[]),
        patch(p["create_task"]) as mock_task,
        patch(p["create_issue"]) as mock_issue,
        patch(p["load_token"]) as mock_load,
        patch(p["lookup_inbox_project_id"]) as mock_lookup,
        patch(p["MONITOR_ACTIVITY_READERS"], new={}),
    ):
        run_cycle(
            str(FIXTURES / "manifest-near-expiry.json"),
            today=date(2026, 5, 11),
            dry_run=True,
        )
    mock_task.assert_not_called()
    mock_issue.assert_not_called()


# ---------- Activity-staleness path ----------


def test_cycle_activity_staleness_files_issue_only():
    p = _patch_paths()

    def fake_reader(cred):
        return ActivitySignalFailure(
            credential_name=cred.name,
            reason="signal failed for test",
            summary="test-fail",
        )

    with (
        patch(p["dedup_check"], return_value=[]),
        patch(p["create_task"]) as mock_task,
        patch(p["create_issue"], return_value=42),
        patch(p["load_token"], return_value="t"),
        patch(p["lookup_inbox_project_id"], return_value=1),
        patch(p["MONITOR_ACTIVITY_READERS"], new={"tailscale-auth": fake_reader, "whatsapp-session": fake_reader}),
    ):
        result = run_cycle(
            str(FIXTURES / "manifest-valid.json"),
            today=date(2026, 5, 11),
        )
    # Two monitor-activity credentials in the valid manifest both alert.
    assert result.staleness_alerts_filed == 2
    # No Vikunja tasks for staleness.
    mock_task.assert_not_called()


def test_cycle_activity_signal_healthy_does_not_alert():
    p = _patch_paths()

    def healthy_reader(cred):
        return None  # signal healthy

    with (
        patch(p["dedup_check"], return_value=[]),
        patch(p["create_task"]),
        patch(p["create_issue"]) as mock_issue,
        patch(p["load_token"], return_value="t"),
        patch(p["lookup_inbox_project_id"], return_value=1),
        patch(p["MONITOR_ACTIVITY_READERS"], new={"tailscale-auth": healthy_reader, "whatsapp-session": healthy_reader}),
    ):
        result = run_cycle(
            str(FIXTURES / "manifest-valid.json"),
            today=date(2026, 5, 11),
        )
    assert result.staleness_alerts_filed == 0
    mock_issue.assert_not_called()
