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
from scripts.trust.unit_drift_detector import UnitDriftFinding


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


def test_render_unit_finding_severity_and_details():
    finding = UnitDriftFinding(
        kind="content_drift",
        name="felix-canary.service",
        repo_source="scripts/office2/felix-canary.service",
        detail="deployed unit content differs from repo canonical (whitespace-normalized)",
    )
    alert = alert_render.render_unit_finding(finding)
    assert alert.source == alert_render.SOURCE_UNIT
    assert alert.severity == Severity.WARN
    assert "felix-canary.service" in alert.title
    assert alert.details["repo_source"] == "scripts/office2/felix-canary.service"
    assert all(isinstance(v, str) for v in alert.details.values())


def test_emit_finding_accepts_unit_finding():
    finding = UnitDriftFinding(
        kind="content_drift",
        name="felix-trust-scan.service",
        repo_source="scripts/office2/felix-trust-scan.service",
    )
    with patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=True)
        result = alert_render.emit_finding(finding)

    assert result.ok is True
    mock_emit.assert_called_once()
    (called_alert,), _ = mock_emit.call_args
    assert called_alert.source == alert_render.SOURCE_UNIT


def test_render_drift_resolved_unit_source():
    alert = alert_render.render_drift_resolved(
        "felix-canary.service",
        "2026-01-01T00:00:00+00:00",
        "2026-01-02T00:00:00+00:00",
        source="unit-drift",
    )
    assert alert.source == alert_render.SOURCE_UNIT
    assert alert.severity == Severity.INFO
    assert "cleared" in alert.title.lower()


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


# --- #1124: null-agent (plugin-managed) cron findings ------------------------


@pytest.mark.parametrize(
    "kind", ["unapproved_present", "approved_missing", "schedule_mismatch", "enabled_mismatch", "weird"]
)
def test_render_null_agent_cron_finding_has_no_literal_none(kind):
    finding = _cron_finding(
        kind=kind,
        name="Memory Dreaming Promotion",
        agent_id=None,
        declaration_key="memory-core:memory-dreaming-promotion",
    )
    alert = alert_render.render_cron_finding(finding)

    assert "None" not in alert.title
    assert "None" not in alert.description
    assert "plugin-managed or unowned" in alert.description
    assert alert.details["agent_id"] == "<none>"
    assert alert.details["declaration_key"] == "memory-core:memory-dreaming-promotion"
    for value in alert.details.values():
        assert isinstance(value, str)
        assert value != "None"


def test_render_str_agent_description_unchanged():
    """Existing copy for a str-agent finding stays byte-identical."""
    alert = alert_render.render_cron_finding(_cron_finding(kind="unapproved_present"))
    assert alert.description == (
        "A live OpenClaw cron named 'mystery-cron' (agent 'felix-admin-capture') is not in "
        "the approved-cron baseline. This may be standing infrastructure "
        "nobody approved."
    )
    assert "declaration_key" not in alert.details


def test_emit_null_agent_cron_finding_reaches_bus():
    finding = _cron_finding(name="Memory Dreaming Promotion", agent_id=None)
    with patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=True)
        result = alert_render.emit_finding(finding)
    assert result.ok is True
    mock_emit.assert_called_once()


# --- #1127: enabled_mismatch copy distinguishes disabled from unconfirmed -----


def test_render_enabled_mismatch_false_keeps_existing_copy():
    alert = alert_render.render_cron_finding(
        _cron_finding(kind="enabled_mismatch", name="inbox-5pm", enabled=False, enabled_state="false")
    )
    assert alert.title == "Approved cron disabled: inbox-5pm"
    assert alert.description == (
        "The approved cron 'inbox-5pm' (agent 'felix-admin-capture') is unexpectedly "
        "disabled."
    )
    assert alert.details["enabled_state"] == "false"
    assert "enabled_raw" not in alert.details


def test_render_enabled_mismatch_absent_is_not_confirmed_enabled():
    alert = alert_render.render_cron_finding(
        _cron_finding(kind="enabled_mismatch", name="inbox-5pm", enabled=None, enabled_state="absent")
    )
    assert alert.severity == Severity.WARN
    assert alert.title == "Approved cron not confirmed enabled: inbox-5pm"
    assert "enabled=absent" in alert.description
    assert alert.details["enabled_state"] == "absent"


def test_render_enabled_mismatch_malformed_dict_raw_with_braces_does_not_raise():
    """Debbie #3: a brace in a raw repr must never be interpolated into a
    format template (it would raise KeyError/ValueError)."""
    from scripts.trust.cron_baseline import ApprovedCron
    from scripts.trust.cron_drift_detector import detect_cron_drift

    baseline = [
        ApprovedCron(
            name="inbox-5pm",
            agent_id="felix-admin-capture",
            schedule_expr="0 17 * * *",
            tz="",
            purpose="p",
            approved_by="kent",
            approved_at="2026-07-10",
        )
    ]
    live = [
        {
            "id": "c1",
            "name": "inbox-5pm",
            "agentId": "felix-admin-capture",
            "enabled": {"a": 1},
            "schedule": {"kind": "cron", "expr": "0 17 * * *"},
        }
    ]
    (finding,) = detect_cron_drift(live, baseline)
    alert = alert_render.render_cron_finding(finding)

    assert alert.title == "Approved cron not confirmed enabled: inbox-5pm"
    assert "enabled=malformed:{'a': 1}" in alert.description
    assert alert.details["enabled_state"] == "malformed"
    assert alert.details["enabled_raw"] == "{'a': 1}"
    assert all(isinstance(v, str) for v in alert.details.values())


def test_render_name_with_braces_does_not_raise():
    alert = alert_render.render_cron_finding(
        _cron_finding(kind="duplicate_present", name="{x}{0}", primary_cron_id="p")
    )
    assert "{x}{0}" in alert.title


# --- #1126: duplicate_present -------------------------------------------------


def test_render_duplicate_present():
    alert = alert_render.render_cron_finding(
        _cron_finding(
            kind="duplicate_present",
            name="inbox-5pm",
            cron_id="dup-2",
            primary_cron_id="prim-1",
            enabled=True,
            enabled_state="true",
            primary_enabled_state="false",
        )
    )
    assert alert.severity == Severity.ERROR
    assert alert.title == "Duplicate cron detected: inbox-5pm"
    assert "'felix-admin-capture'" in alert.description
    assert "dup-2" in alert.description
    assert "prim-1" in alert.description
    assert "enabled=true" in alert.description
    assert "enabled=false" in alert.description
    assert alert.details["primary_cron_id"] == "prim-1"
    assert alert.details["cron_id"] == "dup-2"
    assert alert.details["enabled_state"] == "true"


def test_render_duplicate_present_null_agent_and_no_id():
    alert = alert_render.render_cron_finding(
        _cron_finding(
            kind="duplicate_present",
            name="Memory Dreaming Promotion",
            agent_id=None,
            cron_id=None,
            primary_cron_id=None,
        )
    )
    assert "None" not in alert.title
    assert "None" not in alert.description
    assert "plugin-managed or unowned" in alert.description


# --- A5: registration guard ----------------------------------------------------


def _detector_kinds() -> list[str]:
    from scripts.trust import cron_drift_detector as detector

    return [
        getattr(detector, name) for name in detector.__all__ if name.startswith("KIND_")
    ]


def test_every_detector_kind_registered_in_all_render_maps():
    kinds = _detector_kinds()
    assert "duplicate_present" in kinds
    for kind in kinds:
        assert kind in alert_render._CRON_SEVERITY, kind
        assert kind in alert_render._CRON_TITLE, kind
        assert kind in alert_render._CRON_DESCRIPTION, kind
    assert set(alert_render._CRON_SEVERITY) == set(kinds)
    assert set(alert_render._CRON_TITLE) == set(kinds)
    assert set(alert_render._CRON_DESCRIPTION) == set(kinds)


def test_every_detector_kind_documented_in_runbook_tables():
    from pathlib import Path

    runbook = (
        Path(__file__).resolve().parents[2] / "docs" / "runbooks" / "trust-reporting-detector.md"
    ).read_text(encoding="utf-8")
    kind_section = runbook.split("### 2. Completion-assertion", 1)[0]
    alert_section = runbook.split("## How to read its alerts", 1)[1].split("\n## ", 1)[0]
    for kind in _detector_kinds():
        assert f"| `{kind}` |" in kind_section, f"kind table missing {kind}"
        severity = alert_render._CRON_SEVERITY[kind].value
        assert f"| `{kind}` | {severity} |" in alert_section, f"alert table missing {kind}"
