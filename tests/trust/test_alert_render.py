"""Tests for scripts.trust.alert_render (WP04, #683).

Asserts the Finding -> Alert severity/title mapping matches data-model.md
exactly, that `details` values are all strings, and that `emit_finding`
guards a malformed finding without raising. `scripts.common.alert_bus.emit`
is mocked at the boundary — no real ntfy/office2 calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.common.alert_bus.model import Alert, AlertResult, Severity
from scripts.trust import alert_render
from scripts.trust.assertion_verifier import AssertionFinding
from scripts.trust.cron_drift_detector import CronDriftFinding


def _cron_finding(**overrides) -> CronDriftFinding:
    base = dict(
        kind="unapproved_present",
        name="mystery-cron",
        agent_id="felix-admin-capture",
        cron_id="abc-123",
        schedule_expr="0 17 * * *",
        expected_schedule_expr=None,
        enabled=True,
        created_at_ms=1775153265189,
    )
    base.update(overrides)
    return CronDriftFinding(**base)


def _assertion_finding(**overrides) -> AssertionFinding:
    base = dict(
        kind="artifact_missing",
        agent="main",
        artifact_kind="vikunja_task",
        artifact_id="91",
        claim="Created Vikunja task #91",
    )
    base.update(overrides)
    return AssertionFinding(**base)


# --- render_cron_finding: severity + title mapping ---------------------------


@pytest.mark.parametrize(
    "kind,expected_severity,title_substr",
    [
        ("unapproved_present", Severity.ERROR, "Unrequested cron detected"),
        ("approved_missing", Severity.WARN, "Approved cron missing"),
        ("schedule_mismatch", Severity.WARN, "Approved cron schedule changed"),
        ("enabled_mismatch", Severity.WARN, "Approved cron disabled"),
    ],
)
def test_render_cron_finding_severity_and_title(kind, expected_severity, title_substr):
    finding = _cron_finding(kind=kind, name="my-cron")
    alert = alert_render.render_cron_finding(finding)

    assert isinstance(alert, Alert)
    assert alert.severity == expected_severity
    assert title_substr in alert.title
    assert "my-cron" in alert.title
    assert alert.source == alert_render.SOURCE_CRON


def test_render_cron_finding_details_all_strings():
    finding = _cron_finding(
        kind="unapproved_present",
        cron_id="abc-123",
        schedule_expr="0 17 * * *",
        enabled=True,
        created_at_ms=1775153265189,
    )
    alert = alert_render.render_cron_finding(finding)

    assert alert.details  # non-empty
    for value in alert.details.values():
        assert isinstance(value, str)
    assert alert.details["agent_id"] == "felix-admin-capture"
    assert alert.details["cron_id"] == "abc-123"
    assert alert.details["created_at"] == "1775153265189"
    assert alert.details["enabled"] == "True"


def test_render_cron_finding_none_fields_omitted_from_details():
    finding = _cron_finding(kind="approved_missing", cron_id=None, schedule_expr=None)
    alert = alert_render.render_cron_finding(finding)
    assert "cron_id" not in alert.details
    assert "schedule" not in alert.details


# --- render_assertion_finding: severity + title mapping ----------------------


@pytest.mark.parametrize(
    "kind,expected_severity,title_substr",
    [
        ("artifact_missing", Severity.ERROR, "Completion claim not grounded"),
        ("unverifiable_kind", Severity.WARN, "Completion claim unverifiable"),
    ],
)
def test_render_assertion_finding_severity_and_title(kind, expected_severity, title_substr):
    finding = _assertion_finding(kind=kind, artifact_kind="vikunja_task")
    alert = alert_render.render_assertion_finding(finding)

    assert alert.severity == expected_severity
    assert title_substr in alert.title
    assert "vikunja_task" in alert.title
    assert alert.source == alert_render.SOURCE_ASSERTION


def test_render_assertion_finding_details_all_strings():
    finding = _assertion_finding(
        agent="main", artifact_id="91", claim="Created Vikunja task #91"
    )
    alert = alert_render.render_assertion_finding(finding)

    for value in alert.details.values():
        assert isinstance(value, str)
    assert alert.details["agent"] == "main"
    assert alert.details["artifact_id"] == "91"
    assert alert.details["claim"] == "Created Vikunja task #91"


# --- render_drift_resolved ----------------------------------------------------


def test_render_drift_resolved_is_info_severity():
    alert = alert_render.render_drift_resolved(
        "mystery-cron", "2026-07-01T00:00:00+00:00", "2026-07-10T00:00:00+00:00"
    )
    assert alert.severity == Severity.INFO
    assert "Cron drift cleared" in alert.title
    assert "mystery-cron" in alert.title
    assert alert.details["first_seen"] == "2026-07-01T00:00:00+00:00"
    assert alert.details["cleared_at"] == "2026-07-10T00:00:00+00:00"


# --- emit_finding: calls bus emit, guards malformed input --------------------


def test_emit_finding_calls_bus_emit_with_alert():
    finding = _cron_finding(kind="unapproved_present")
    with patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=True)
        result = alert_render.emit_finding(finding)

    assert result.ok is True
    mock_emit.assert_called_once()
    (called_alert,), _ = mock_emit.call_args
    assert isinstance(called_alert, Alert)
    assert called_alert.severity == Severity.ERROR


def test_emit_finding_accepts_assertion_finding():
    finding = _assertion_finding(kind="unverifiable_kind")
    with patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=True)
        result = alert_render.emit_finding(finding)

    assert result.ok is True
    mock_emit.assert_called_once()


def test_emit_finding_accepts_prebuilt_alert():
    alert = alert_render.render_drift_resolved("x", "2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00")
    with patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=True)
        result = alert_render.emit_finding(alert)

    mock_emit.assert_called_once_with(alert)
    assert result.ok is True


def test_emit_finding_unknown_type_does_not_raise():
    with patch("scripts.trust.alert_render.emit") as mock_emit:
        result = alert_render.emit_finding("not-a-finding")  # type: ignore[arg-type]

    mock_emit.assert_not_called()
    assert result.ok is False
    assert result.reason == "RENDER_UNKNOWN_FINDING_TYPE"


def test_emit_finding_render_failure_does_not_raise():
    """A malformed finding (missing required attrs) must not crash the tick."""

    class _BrokenCronFinding(CronDriftFinding):
        @property
        def name(self):  # type: ignore[override]
            raise RuntimeError("boom")

        @name.setter
        def name(self, value):  # allow dataclass __init__ to set it
            self.__dict__["name"] = value

    broken = _BrokenCronFinding(kind="unapproved_present", name="x", agent_id="main")

    with patch("scripts.trust.alert_render.emit") as mock_emit:
        result = alert_render.emit_finding(broken)

    mock_emit.assert_not_called()
    assert result.ok is False
    assert result.reason.startswith("RENDER_ERROR:")
