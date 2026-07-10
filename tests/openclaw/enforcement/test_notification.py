"""Tests for notification dispatch."""

from unittest.mock import patch, MagicMock

from scripts.common.alert_bus import Severity
from scripts.openclaw.enforcement.detection import DriftResult, DriftState
from scripts.openclaw.enforcement.notification import (
    compose_alert_message,
    compose_issue_body,
    send_whatsapp,
    create_drift_issue,
    notify,
)


def _make_result(state, agent="main", filename="AGENTS.md", factory=False):
    return DriftResult(
        agent_id=agent, filename=filename, state=state,
        current_repo_hash="aaa", current_office2_hash="bbb",
        baseline_repo_hash="ccc", baseline_office2_hash="ddd",
        is_factory_default=factory,
    )


def _config():
    return {
        "notification": {
            "channel": "whatsapp",
            "openclaw_agent": "main",
            "recipient": "+15555550123",
            "issue_repo": "kentonium3/kg-automation",
            "issue_labels": ["drift-alert", "area/felix-core"],
        },
    }


class TestComposeAlertMessage:
    def test_conflicts(self):
        actions = {"conflicts": [_make_result(DriftState.CONFLICT)], "factory_transitions": [], "deployed": [], "captured": [], "errors": []}
        msg = compose_alert_message(actions)
        assert "Conflicts" in msg
        assert "main/AGENTS.md" in msg

    def test_factory_transitions(self):
        actions = {"conflicts": [], "factory_transitions": [_make_result(DriftState.OFFICE2_CHANGED)], "deployed": [], "captured": [], "errors": []}
        msg = compose_alert_message(actions)
        assert "Factory transitions" in msg

    def test_auto_remediated_summary(self):
        actions = {"conflicts": [], "factory_transitions": [], "deployed": [_make_result(DriftState.REPO_CHANGED)], "captured": [], "errors": []}
        msg = compose_alert_message(actions)
        assert "1 deployed" in msg


class TestComposeIssueBody:
    def test_includes_hashes(self):
        actions = {"conflicts": [_make_result(DriftState.CONFLICT)], "factory_transitions": []}
        body = compose_issue_body(actions)
        assert "`aaa`" in body  # repo hash
        assert "`bbb`" in body  # office2 hash
        assert "Resolution" in body


class TestSendWhatsapp:
    def test_dry_run(self):
        assert send_whatsapp("test message", _config(), dry_run=True) is True

    def test_success(self):
        mock = MagicMock(returncode=0)
        with patch("scripts.openclaw.enforcement.notification.subprocess.run", return_value=mock):
            assert send_whatsapp("test", _config()) is True

    def test_failure(self):
        mock = MagicMock(returncode=1, stderr="gateway down")
        with patch("scripts.openclaw.enforcement.notification.subprocess.run", return_value=mock):
            assert send_whatsapp("test", _config()) is False

    def test_timeout(self):
        import subprocess
        with patch("scripts.openclaw.enforcement.notification.subprocess.run", side_effect=subprocess.TimeoutExpired("openclaw", 60)):
            assert send_whatsapp("test", _config()) is False


class TestCreateDriftIssue:
    def test_dry_run(self):
        actions = {"conflicts": [_make_result(DriftState.CONFLICT)], "factory_transitions": []}
        assert create_drift_issue(actions, _config(), dry_run=True) is None

    def test_success(self):
        mock = MagicMock(returncode=0, stdout="https://github.com/repo/issues/999\n")
        actions = {"conflicts": [_make_result(DriftState.CONFLICT)], "factory_transitions": []}
        with patch("scripts.openclaw.enforcement.notification.subprocess.run", return_value=mock):
            url = create_drift_issue(actions, _config())
        assert url == "https://github.com/repo/issues/999"

    def test_failure(self):
        mock = MagicMock(returncode=1, stderr="auth failed")
        actions = {"conflicts": [], "factory_transitions": [_make_result(DriftState.OFFICE2_CHANGED)]}
        with patch("scripts.openclaw.enforcement.notification.subprocess.run", return_value=mock):
            assert create_drift_issue(actions, _config()) is None


class TestNotify:
    def test_no_notification_when_nothing_actionable(self):
        actions = {"conflicts": [], "factory_transitions": [], "deployed": [], "captured": [], "errors": []}
        with patch("scripts.openclaw.enforcement.notification.send_whatsapp") as mock_wa:
            notify(actions, _config())
        mock_wa.assert_not_called()

    def test_sends_whatsapp_and_issue_for_conflicts(self):
        actions = {"conflicts": [_make_result(DriftState.CONFLICT)], "factory_transitions": [], "deployed": [], "captured": [], "errors": []}
        with patch("scripts.openclaw.enforcement.notification.send_whatsapp") as mock_wa, \
             patch("scripts.openclaw.enforcement.notification.create_drift_issue", return_value="https://issue/1") as mock_issue:
            notify(actions, _config())
        mock_issue.assert_called_once()
        mock_wa.assert_called_once()

    def test_co_emit_is_additive_whatsapp_and_github_still_fire(self):
        """SC-007: felix-alert co-emit is ADDITIVE — WhatsApp + GitHub untouched."""
        actions = {"conflicts": [_make_result(DriftState.CONFLICT)], "factory_transitions": [], "deployed": [], "captured": [], "errors": []}
        with patch("scripts.openclaw.enforcement.notification.send_whatsapp") as mock_wa, \
             patch("scripts.openclaw.enforcement.notification.create_drift_issue", return_value="https://issue/1") as mock_issue, \
             patch("scripts.openclaw.enforcement.notification.emit") as mock_emit:
            notify(actions, _config())
        # All three surfaces fire.
        mock_issue.assert_called_once()
        mock_wa.assert_called_once()
        mock_emit.assert_called_once()
        # The co-emit carries a well-formed Alert to the bus.
        alert = mock_emit.call_args.args[0]
        assert alert.source == "openclaw-enforcement/drift"
        assert alert.severity == Severity.ERROR  # conflicts present
        assert alert.details["issue_url"] == "https://issue/1"

    def test_co_emit_warn_when_only_factory_transitions(self):
        actions = {"conflicts": [], "factory_transitions": [_make_result(DriftState.OFFICE2_CHANGED)], "deployed": [], "captured": [], "errors": []}
        with patch("scripts.openclaw.enforcement.notification.send_whatsapp"), \
             patch("scripts.openclaw.enforcement.notification.create_drift_issue", return_value=None), \
             patch("scripts.openclaw.enforcement.notification.emit") as mock_emit:
            notify(actions, _config())
        mock_emit.assert_called_once()
        assert mock_emit.call_args.args[0].severity == Severity.WARN

    def test_co_emit_failure_never_breaks_enforcement(self):
        """A bus-layer exception must NOT propagate past enforcement."""
        actions = {"conflicts": [_make_result(DriftState.CONFLICT)], "factory_transitions": [], "deployed": [], "captured": [], "errors": []}
        with patch("scripts.openclaw.enforcement.notification.send_whatsapp") as mock_wa, \
             patch("scripts.openclaw.enforcement.notification.create_drift_issue", return_value="https://issue/1"), \
             patch("scripts.openclaw.enforcement.notification.emit", side_effect=RuntimeError("bus exploded")):
            # Must not raise despite emit() blowing up.
            notify(actions, _config())
        # WhatsApp still fired even though the co-emit raised internally.
        mock_wa.assert_called_once()

    def test_co_emit_skipped_on_dry_run(self):
        actions = {"conflicts": [_make_result(DriftState.CONFLICT)], "factory_transitions": [], "deployed": [], "captured": [], "errors": []}
        with patch("scripts.openclaw.enforcement.notification.send_whatsapp"), \
             patch("scripts.openclaw.enforcement.notification.create_drift_issue", return_value=None), \
             patch("scripts.openclaw.enforcement.notification.emit") as mock_emit:
            notify(actions, _config(), dry_run=True)
        mock_emit.assert_not_called()
