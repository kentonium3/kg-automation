"""Unit tests for the cron-drift detector (WP02, #683).

Feeds canned JSON dicts (the C1 shape from
``kitty-specs/felix-truthful-reporting-01KX6MN5/contracts/detector-cli.md``)
and small in-memory baselines to ``detect_cron_drift``, asserting the finding
set for each scenario: exact match, each of the four finding kinds
(including the owner-mismatch variant of ``unapproved_present``), tolerant
parsing of unknown/missing fields, and the ``enumerate_live_crons`` fail-safe
wrapper (mocked subprocess boundary — never calls office2/openclaw).
"""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.trust.cron_baseline import ApprovedCron
from scripts.trust.cron_drift_detector import (
    KIND_APPROVED_MISSING,
    KIND_ENABLED_MISMATCH,
    KIND_SCHEDULE_MISMATCH,
    KIND_UNAPPROVED_PRESENT,
    CronEnumerationError,
    detect_cron_drift,
    enumerate_live_crons,
)

BASELINE_ENTRY = ApprovedCron(
    name="inbox-5pm",
    agent_id="felix-admin-capture",
    schedule_expr="0 17 * * *",
    tz="America/New_York",
    purpose="Scheduled inbox processing run.",
    approved_by="kent",
    approved_at="2026-07-10",
)


def _live_job(**overrides: object) -> dict:
    job = {
        "id": "4ea46768-fac9-4620-825e-5d0f8214238b",
        "name": "inbox-5pm",
        "enabled": True,
        "createdAtMs": 1775153265189,
        "agentId": "felix-admin-capture",
        "schedule": {"kind": "cron", "expr": "0 17 * * *", "tz": "America/New_York"},
    }
    job.update(overrides)
    return job


# --- exact-match / no drift --------------------------------------------------


def test_exact_match_produces_no_findings() -> None:
    findings = detect_cron_drift([_live_job()], [BASELINE_ENTRY])

    assert findings == []


def test_empty_live_and_empty_baseline_produces_no_findings() -> None:
    assert detect_cron_drift([], []) == []


# --- unapproved_present ------------------------------------------------------


def test_unapproved_present_for_live_cron_not_in_baseline() -> None:
    """A rogue cron alongside its baseline's own matched pair (so the only
    finding is the unapproved one — no unrelated approved_missing noise)."""
    approved_live = _live_job()
    rogue = _live_job(name="rogue-cron", id="rogue-id", agentId="felix-admin-capture")

    findings = detect_cron_drift([approved_live, rogue], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_UNAPPROVED_PRESENT
    assert finding.name == "rogue-cron"
    assert finding.agent_id == "felix-admin-capture"
    assert finding.cron_id == "rogue-id"
    assert finding.schedule_expr == "0 17 * * *"
    assert finding.enabled is True
    assert finding.created_at_ms == 1775153265189


def test_owner_mismatch_is_unapproved_present_not_schedule_mismatch() -> None:
    """An approved `name` running under a *different* `agent_id` must be
    reported as `unapproved_present` (the incident-relevant owner-mismatch
    case), never silently passed or misreported as `schedule_mismatch`.

    Because the match key is `(name, agent_id)`, the hijacked job no longer
    matches the baseline entry by key, so the baseline entry also correctly
    reports `approved_missing` (its own approved `(name, agent_id)` truly
    has no live match) — assert on the `unapproved_present` finding
    specifically rather than asserting it is the only finding.
    """
    hijacked = _live_job(agentId="some-other-agent")

    findings = detect_cron_drift([hijacked], [BASELINE_ENTRY])

    unapproved = [f for f in findings if f.kind == KIND_UNAPPROVED_PRESENT]
    assert len(unapproved) == 1
    finding = unapproved[0]
    assert finding.name == "inbox-5pm"
    assert finding.agent_id == "some-other-agent"

    # And no schedule_mismatch was fabricated for the hijacked job — the
    # owner-mismatch path must not fall through to the matched-pair diff.
    assert all(f.kind != KIND_SCHEDULE_MISMATCH for f in findings)


# --- approved_missing ---------------------------------------------------------


def test_approved_missing_for_baseline_entry_with_no_live_match() -> None:
    findings = detect_cron_drift([], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_APPROVED_MISSING
    assert finding.name == "inbox-5pm"
    assert finding.agent_id == "felix-admin-capture"
    assert finding.expected_schedule_expr == "0 17 * * *"


# --- schedule_mismatch --------------------------------------------------------


def test_schedule_mismatch_on_differing_expr() -> None:
    live = _live_job(schedule={"kind": "cron", "expr": "0 18 * * *", "tz": "America/New_York"})

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_SCHEDULE_MISMATCH
    assert finding.schedule_expr == "0 18 * * *"
    assert finding.expected_schedule_expr == "0 17 * * *"


def test_schedule_mismatch_on_differing_tz_only() -> None:
    live = _live_job(schedule={"kind": "cron", "expr": "0 17 * * *", "tz": "America/Chicago"})

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_SCHEDULE_MISMATCH
    # expr unchanged; tz drift alone still triggers schedule_mismatch.
    assert finding.schedule_expr == "0 17 * * *"
    assert finding.expected_schedule_expr == "0 17 * * *"


# --- enabled_mismatch ----------------------------------------------------------


def test_enabled_mismatch_when_live_disabled() -> None:
    live = _live_job(enabled=False)

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_ENABLED_MISMATCH
    assert finding.enabled is False


def test_schedule_and_enabled_mismatch_both_reported_independently() -> None:
    """A matched pair may legitimately produce both findings at once."""
    live = _live_job(
        enabled=False,
        schedule={"kind": "cron", "expr": "0 18 * * *", "tz": "America/New_York"},
    )

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    kinds = {finding.kind for finding in findings}
    assert kinds == {KIND_SCHEDULE_MISMATCH, KIND_ENABLED_MISMATCH}
    assert len(findings) == 2


# --- tolerant parse ------------------------------------------------------------


def test_tolerant_parse_extra_fields_and_missing_tz() -> None:
    live = {
        "id": "some-id",
        "name": "inbox-5pm",
        "enabled": True,
        "createdAtMs": 1775153265189,
        "agentId": "felix-admin-capture",
        "schedule": {"kind": "cron", "expr": "0 17 * * *"},  # no tz key
        "unknownField": {"nested": "value"},
        "state": {"lastRunStatus": "ok"},
    }

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    # Baseline tz is "America/New_York"; live tz is None (missing key) which
    # differs from the baseline, so this is a legitimate schedule_mismatch —
    # the point of this test is that parsing does not raise/crash on the
    # missing key or the unknown extra fields.
    assert len(findings) == 1
    assert findings[0].kind == KIND_SCHEDULE_MISMATCH


def test_tolerant_parse_missing_schedule_object_entirely() -> None:
    live = {
        "id": "some-id",
        "name": "rogue-no-schedule",
        "enabled": True,
        "createdAtMs": 1775153265189,
        "agentId": "felix-admin-capture",
    }

    # Must not raise despite the wholly-absent `schedule` key.
    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    kinds_by_name = {f.name: f.kind for f in findings}
    assert kinds_by_name["rogue-no-schedule"] == KIND_UNAPPROVED_PRESENT


# --- deterministic ordering ----------------------------------------------------


def test_findings_are_sorted_deterministically() -> None:
    baseline = [
        BASELINE_ENTRY,
        ApprovedCron(
            name="zzz-approved",
            agent_id="felix-admin-capture",
            schedule_expr="0 0 * * *",
            tz="America/New_York",
            purpose="test",
            approved_by="kent",
            approved_at="2026-07-10",
        ),
    ]
    live = [_live_job(name="aaa-rogue", agentId="felix-admin-capture")]

    findings = detect_cron_drift(live, baseline)

    keys = [(f.kind, f.name, f.agent_id) for f in findings]
    assert keys == sorted(keys)


# --- enumerate_live_crons: fail-safe wrapper ------------------------------------


def _mock_completed(returncode: int, stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["openclaw", "cron", "list", "--json"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_enumerate_live_crons_returns_jobs_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"jobs": [_live_job()]})
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, payload),
    )

    jobs = enumerate_live_crons()

    assert jobs == [_live_job()]


def test_enumerate_live_crons_genuinely_empty_jobs_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuinely empty `jobs: []` payload must return `[]` — this is the
    valid "no crons" case, distinct from every failure case below."""
    payload = json.dumps({"jobs": []})
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, payload),
    )

    jobs = enumerate_live_crons()

    assert jobs == []


def test_enumerate_live_crons_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(1, "", stderr="openclaw: command failed"),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_non_json_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, "not json at all"),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_missing_jobs_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, json.dumps({"total": 0})),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_jobs_not_a_list_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, json.dumps({"jobs": "not-a-list"})),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["openclaw"], timeout=30)

    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run", _raise_timeout
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_os_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_os_error(*args: object, **kwargs: object) -> None:
        raise OSError("openclaw binary not found")

    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run", _raise_os_error
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_response_not_a_dict_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, json.dumps([1, 2, 3])),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_tz_omitted_in_live_payload_is_not_schedule_mismatch() -> None:
    """A host default-tz cron (baseline tz="" + live payload omits schedule.tz)
    must NOT be flagged as schedule_mismatch (#683 deploy regression)."""
    from scripts.trust.cron_baseline import ApprovedCron

    baseline = [
        ApprovedCron(
            name="escalation-daily",
            agent_id="felix-admin-escalation",
            schedule_expr="0 12 * * *",
            tz="",
            purpose="p",
            approved_by="kent",
            approved_at="2026-07-10",
        )
    ]
    live = [
        {
            "id": "abc",
            "name": "escalation-daily",
            "agentId": "felix-admin-escalation",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 12 * * *"},  # no tz key
        }
    ]
    assert detect_cron_drift(live, baseline) == []


def test_genuine_tz_change_still_flagged() -> None:
    """A real tz change (baseline America/New_York vs live omitting tz) IS drift."""
    from scripts.trust.cron_baseline import ApprovedCron

    baseline = [
        ApprovedCron(
            name="inbox-5pm",
            agent_id="felix-admin-capture",
            schedule_expr="0 17 * * *",
            tz="America/New_York",
            purpose="p",
            approved_by="kent",
            approved_at="2026-07-10",
        )
    ]
    live = [
        {
            "id": "abc",
            "name": "inbox-5pm",
            "agentId": "felix-admin-capture",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 17 * * *"},  # tz dropped → change
        }
    ]
    findings = detect_cron_drift(live, baseline)
    assert [f.kind for f in findings] == ["schedule_mismatch"]
