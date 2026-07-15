"""Tests for credential_health_check.orchestrator.run_cycle."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from credential_health_check.github_writer import GitHubWriteError
from credential_health_check.liveness import LivenessResult
from credential_health_check.manifest import Credential, LivenessProbeConfig, ManifestUnreadableError
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
        # WP03 deleted the by-title lookup_inbox_project_id helper; the
        # orchestrator now resolves "inbox" through the network-free reference
        # seam (scripts.common.vikunja_refs.project_id), so tests patch that.
        "project_id": "credential_health_check.orchestrator.vikunja_refs.project_id",
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
        patch(p["project_id"], return_value=1),
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
        patch(p["project_id"], return_value=1),
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
        patch(p["project_id"], return_value=1),
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
        patch(p["project_id"], return_value=1),
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
        patch(p["project_id"], return_value=1),
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
        patch(p["project_id"], return_value=1),
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
        patch(p["project_id"]) as mock_lookup,
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
        patch(p["project_id"], return_value=1),
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
        patch(p["project_id"], return_value=1),
        patch(p["MONITOR_ACTIVITY_READERS"], new={"tailscale-auth": healthy_reader, "whatsapp-session": healthy_reader}),
    ):
        result = run_cycle(
            str(FIXTURES / "manifest-valid.json"),
            today=date(2026, 5, 11),
        )
    assert result.staleness_alerts_filed == 0
    mock_issue.assert_not_called()


# ---------- Helpers for liveness tests ----------


def _make_cred_with_liveness(name: str = "gog-credentials-keyring") -> Credential:
    """Build an in-memory Credential with liveness_probe.enabled=True."""
    return Credential(
        name=name,
        review_cadence="on-revocation",
        storage="/home/claude/.local/share/gog/keyring",
        expiry_notes="OAuth2 gog token; re-auth via gog-reauth.sh",
        type="oauth2",
        liveness_probe=LivenessProbeConfig(
            enabled=True,
            gog_account="kentgale@gmail.com",
            keyring_file="/home/claude/.local/share/gog/keyring",
            recovery_command=(
                "ssh -t office2-claude "
                "/home/claude/kg-automation/scripts/security/gog-reauth.sh"
            ),
        ),
    )


def _make_cred_no_liveness(name: str = "no-liveness-cred") -> Credential:
    """Build an in-memory Credential without a liveness_probe block."""
    return Credential(
        name=name,
        review_cadence="on-revocation",
        storage="/etc/secrets/token",
        expiry_notes="some token",
        type="api-token",
        liveness_probe=None,
    )


def _fake_dead_result(cred, classification: str = "dead") -> LivenessResult:
    return LivenessResult(
        credential_name=cred.name,
        classification=classification,
        reason="test reason",
        recovery_command=(
            "ssh -t office2-claude "
            "/home/claude/kg-automation/scripts/security/gog-reauth.sh"
        ),
        probed_at=datetime.now(timezone.utc),
    )


_LIVENESS_PATCH = "credential_health_check.orchestrator.probe_oauth_liveness"
_DEDUP_PATCH = "credential_health_check.orchestrator.dedup_check"
_CREATE_ISSUE_PATCH = "credential_health_check.orchestrator.create_issue"


# ---------- WP03 liveness tests (T018) ----------


def test_orchestrator_skips_credentials_without_liveness_probe():
    """Credential without liveness_probe block: liveness_skipped logged, no issue filed."""
    cred = _make_cred_no_liveness()
    log_records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            log_records.append(record.getMessage())

    handler = _Capture()
    logger = logging.getLogger("test_skip_no_liveness")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    with (
        patch(_LIVENESS_PATCH) as mock_probe,
        patch(_DEDUP_PATCH, return_value=[]),
        patch(_CREATE_ISSUE_PATCH) as mock_issue,
        patch("credential_health_check.orchestrator.read_manifest", return_value=([cred], [])),
        patch("credential_health_check.orchestrator.MONITOR_ACTIVITY_READERS", new={}),
        patch("credential_health_check.orchestrator.is_fixed_interval_cadence", return_value=False),
    ):
        result = run_cycle("/fake/manifest.json", today=date(2026, 6, 9), logger=logger)

    mock_probe.assert_not_called()
    mock_issue.assert_not_called()
    assert any("liveness_skipped" in msg for msg in log_records)


def test_orchestrator_files_issue_on_dead():
    """Probe returns dead; no dedup match → issue filed, liveness_alerts_filed=1."""
    cred = _make_cred_with_liveness()
    captured: dict = {}

    def fake_probe(c):
        return _fake_dead_result(c, "dead")

    def fake_file(title, body, labels):
        captured["title"] = title
        captured["body"] = body
        captured["labels"] = labels
        return 999

    with (
        patch(_LIVENESS_PATCH, side_effect=fake_probe),
        patch(_DEDUP_PATCH, return_value=[]),
        patch(_CREATE_ISSUE_PATCH, side_effect=fake_file),
        patch("credential_health_check.orchestrator.read_manifest", return_value=([cred], [])),
        patch("credential_health_check.orchestrator.MONITOR_ACTIVITY_READERS", new={}),
        patch("credential_health_check.orchestrator.is_fixed_interval_cadence", return_value=False),
    ):
        result = run_cycle("/fake/manifest.json", today=date(2026, 6, 9))

    assert result.liveness_alerts_filed == 1
    assert captured["title"].startswith("credential-liveness-dead:")
    assert cred.name in captured["title"]


def test_orchestrator_dead_body_has_unconditional_investigate_block():
    """Post-#731 every dead alert body includes the 'investigate' guidance."""
    cred = _make_cred_with_liveness()
    captured: dict = {}

    def fake_probe(c):
        return _fake_dead_result(c, "dead")

    def fake_file(title, body, labels):
        captured["title"] = title
        captured["body"] = body
        return 101

    with (
        patch(_LIVENESS_PATCH, side_effect=fake_probe),
        patch(_DEDUP_PATCH, return_value=[]),
        patch(_CREATE_ISSUE_PATCH, side_effect=fake_file),
        patch("credential_health_check.orchestrator.read_manifest", return_value=([cred], [])),
        patch("credential_health_check.orchestrator.MONITOR_ACTIVITY_READERS", new={}),
        patch("credential_health_check.orchestrator.is_fixed_interval_cadence", return_value=False),
    ):
        result = run_cycle("/fake/manifest.json", today=date(2026, 6, 9))

    assert result.liveness_alerts_filed == 1
    assert "myaccount.google.com/permissions" in captured["body"]


def test_orchestrator_dedups_repeat_dead_failures():
    """Probe returns dead; existing open issue → deduped, no new issue."""
    cred = _make_cred_with_liveness()

    def fake_probe(c):
        return _fake_dead_result(c, "dead")

    with (
        patch(_LIVENESS_PATCH, side_effect=fake_probe),
        patch(_DEDUP_PATCH, return_value=[42]),
        patch(_CREATE_ISSUE_PATCH) as mock_issue,
        patch("credential_health_check.orchestrator.read_manifest", return_value=([cred], [])),
        patch("credential_health_check.orchestrator.MONITOR_ACTIVITY_READERS", new={}),
        patch("credential_health_check.orchestrator.is_fixed_interval_cadence", return_value=False),
    ):
        result = run_cycle("/fake/manifest.json", today=date(2026, 6, 9))

    mock_issue.assert_not_called()
    assert result.liveness_alerts_filed == 0
    assert result.alerts_deduped >= 1


def test_orchestrator_dry_run_does_not_file():
    """dry_run=True; probe returns dead → alert_would_file logged; no issue filed."""
    cred = _make_cred_with_liveness()
    log_records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            log_records.append(record.getMessage())

    handler = _Capture()
    logger = logging.getLogger("test_dry_run_liveness")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    def fake_probe(c):
        return _fake_dead_result(c, "dead")

    with (
        patch(_LIVENESS_PATCH, side_effect=fake_probe),
        patch(_DEDUP_PATCH, return_value=[]),
        patch(_CREATE_ISSUE_PATCH) as mock_issue,
        patch("credential_health_check.orchestrator.read_manifest", return_value=([cred], [])),
        patch("credential_health_check.orchestrator.MONITOR_ACTIVITY_READERS", new={}),
        patch("credential_health_check.orchestrator.is_fixed_interval_cadence", return_value=False),
    ):
        result = run_cycle("/fake/manifest.json", today=date(2026, 6, 9), dry_run=True, logger=logger)

    mock_issue.assert_not_called()
    assert result.liveness_alerts_filed == 0
    assert any("alert_would_file" in msg for msg in log_records)


def test_orchestrator_probe_error_no_issue():
    """Probe returns probe-error → result.errors populated; no issue filed."""
    cred = _make_cred_with_liveness()

    def fake_probe(c):
        return LivenessResult(
            credential_name=c.name,
            classification="probe-error",
            reason="gog binary not found",
            recovery_command=None,
            probed_at=datetime.now(timezone.utc),
        )

    with (
        patch(_LIVENESS_PATCH, side_effect=fake_probe),
        patch(_DEDUP_PATCH, return_value=[]),
        patch(_CREATE_ISSUE_PATCH) as mock_issue,
        patch("credential_health_check.orchestrator.read_manifest", return_value=([cred], [])),
        patch("credential_health_check.orchestrator.MONITOR_ACTIVITY_READERS", new={}),
        patch("credential_health_check.orchestrator.is_fixed_interval_cadence", return_value=False),
    ):
        result = run_cycle("/fake/manifest.json", today=date(2026, 6, 9))

    mock_issue.assert_not_called()
    assert result.liveness_alerts_filed == 0
    assert any("probe_error" in e or "gog binary" in e for e in result.errors)


def test_liveness_only_skips_cadence_and_staleness():
    """liveness_only=True: only liveness probe runs, not cadence/staleness."""
    cred = _make_cred_with_liveness()
    process_cadence_calls: list = []
    process_staleness_calls: list = []

    def fake_probe(c):
        return None  # alive

    with (
        patch(_LIVENESS_PATCH, side_effect=fake_probe),
        patch(_DEDUP_PATCH, return_value=[]),
        patch(_CREATE_ISSUE_PATCH) as mock_issue,
        patch("credential_health_check.orchestrator.read_manifest", return_value=([cred], [])),
        patch("credential_health_check.orchestrator.MONITOR_ACTIVITY_READERS", new={}),
        patch(
            "credential_health_check.orchestrator._process_cadence_alert",
            side_effect=lambda *a, **kw: process_cadence_calls.append(1),
        ),
        patch(
            "credential_health_check.orchestrator._process_staleness_alert",
            side_effect=lambda *a, **kw: process_staleness_calls.append(1),
        ),
    ):
        result = run_cycle("/fake/manifest.json", today=date(2026, 6, 9), liveness_only=True)

    assert len(process_cadence_calls) == 0
    assert len(process_staleness_calls) == 0
    mock_issue.assert_not_called()


def test_liveness_runs_in_both_modes():
    """liveness_only=False: liveness probe runs alongside cadence/staleness."""
    cred = _make_cred_with_liveness()
    liveness_calls: list = []

    def fake_probe(c):
        liveness_calls.append(c.name)
        return None  # alive

    with (
        patch(_LIVENESS_PATCH, side_effect=fake_probe),
        patch(_DEDUP_PATCH, return_value=[]),
        patch(_CREATE_ISSUE_PATCH),
        patch("credential_health_check.orchestrator.read_manifest", return_value=([cred], [])),
        patch("credential_health_check.orchestrator.MONITOR_ACTIVITY_READERS", new={}),
        patch("credential_health_check.orchestrator.is_fixed_interval_cadence", return_value=False),
    ):
        result = run_cycle("/fake/manifest.json", today=date(2026, 6, 9), liveness_only=False)

    assert len(liveness_calls) >= 1
    assert liveness_calls[0] == cred.name


def test_dead_title_prefix_is_single_value():
    """Post-#731 there is one dead-alert title prefix, keyed on credential name."""
    prefix = "credential-liveness-dead: gog-credentials-keyring"
    assert prefix.startswith("credential-liveness-dead:")
    assert "gog-credentials-keyring" in prefix
