"""Golden fingerprints pinned BEFORE the #1126/#1127/#1128 changes.

Seen-state on office2 keys outstanding findings by fingerprint: a changed
fingerprint re-alerts once and orphans the old entry. Every value below was
computed on the unmodified code (main @ bfcdc4bc7, 2026-11-23) and hard-coded
as a literal, so these tests never recompute the expected value through the
code under test.

Coverage: every cron kind that exists today (each finding carrying a
``cron_id``, which must NOT enter the 4-field cron identity), a null-agent
plugin cron (#1124 sentinel), an assertion finding, a unit-drift finding, and
the detector path for a genuinely disabled approved cron (#1127: a literal
``enabled: False`` must keep today's ``enabled_mismatch`` fingerprint).

#1130: only cron findings are baseline-versioned. ``GOLDEN_ASSERTION`` pins the
state-level encoding of an assertion under a non-empty hash (the
``fingerprint_finding`` API still accepts one); ``GOLDEN_ASSERTION_UNVERSIONED``
is the production shape — the runner always passes ``""`` for an assertion, so
that is the key seen-state actually holds. It was computed on main @ ee1bb31fa
(state.py unchanged by #1130) and hard-coded as a literal.
"""

from __future__ import annotations

import pytest

from scripts.trust import run_trust_scan as rts
from scripts.trust import state as state_mod
from scripts.trust.assertion_verifier import AssertionFinding
from scripts.trust.cron_baseline import ApprovedCron
from scripts.trust.cron_drift_detector import CronDriftFinding, detect_cron_drift
from scripts.trust.unit_drift_detector import UnitDriftFinding

# A realistic 64-hex baseline hash (literal; not derived from any baseline).
GOLDEN_BASELINE_HASH = "6f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0"

CRON_ID = "4ea46768-fac9-4620-825e-5d0f8214238b"

GOLDEN_CRON = {
    "unapproved_present": "423bfe846d6ca832a11b633f95ae62690bea24ec7a5ce7f31bd76100db376524",
    "approved_missing": "28a80c4901cde89f4c8394d8bfd9deebf6a54dd23b380ce08376a9333e1af567",
    "schedule_mismatch": "e7d77c5460ca465474e2664dab11bee7d89c5798ae601fc3489d60cf3ac4f125",
    "enabled_mismatch": "7e61e7ea1e37ab5409e956ab6095eb3f98676bd0390252f456edc365d053d0e5",
}
GOLDEN_NULL_AGENT_CRON = "fc2c6a9a3b2a6e715cc1f292b11e3cdc5712f4698f14bfd0e81eaed50ee8d5ef"
# State-API encoding pin: an assertion fingerprinted under a non-empty hash.
GOLDEN_ASSERTION = "2e93aea3cbfebb23a9ae26acb11dab9de4980e04fb383a1561d11ea7f20e9c2d"
# Production shape (#1130): assertion fingerprints are not baseline-versioned.
GOLDEN_ASSERTION_UNVERSIONED = "e662c5805ae48036b99edee06d78abd082229049e0f3984ded8816b1c7956838"
GOLDEN_UNIT = "bd1b7676792d5d50878b38ee02bd8d0be4390bea020bd0e8f2c94701f3a1c5b6"


def _cron(kind: str) -> CronDriftFinding:
    return CronDriftFinding(
        kind=kind,
        name="inbox-5pm",
        agent_id="felix-admin-capture",
        cron_id=CRON_ID,
        schedule_expr="0 17 * * *",
        enabled=False,
        created_at_ms=1775153265189,
    )


@pytest.mark.parametrize("kind", sorted(GOLDEN_CRON))
def test_cron_fingerprint_golden_four_field_identity_with_cron_id(kind: str) -> None:
    """The finding carries a cron_id, but the identity stays 4-field."""
    assert state_mod.fingerprint_finding(_cron(kind), GOLDEN_BASELINE_HASH) == GOLDEN_CRON[kind]


def test_null_agent_cron_fingerprint_golden() -> None:
    finding = CronDriftFinding(
        kind="unapproved_present",
        name="Memory Dreaming Promotion",
        agent_id=None,
        cron_id="7d1c",
        declaration_key="memory-core:x",
    )
    assert state_mod.fingerprint_finding(finding, GOLDEN_BASELINE_HASH) == GOLDEN_NULL_AGENT_CRON


def _golden_assertion() -> AssertionFinding:
    return AssertionFinding(
        kind="artifact_missing",
        agent="main",
        artifact_kind="vikunja_task",
        artifact_id="91",
        claim="Created Vikunja task #91",
    )


def test_assertion_fingerprint_golden() -> None:
    """State-API encoding pin (not the production key since #1130)."""
    assert (
        state_mod.fingerprint_finding(_golden_assertion(), GOLDEN_BASELINE_HASH)
        == GOLDEN_ASSERTION
    )


def test_assertion_fingerprint_golden_unversioned() -> None:
    assert state_mod.fingerprint_finding(_golden_assertion(), "") == GOLDEN_ASSERTION_UNVERSIONED


def test_assertion_fingerprint_golden_production_shape_ignores_the_baseline() -> None:
    """#1130: the runner's per-type rule gives an assertion no baseline hash, so
    the key seen-state holds is the unversioned golden whatever the baseline."""
    finding = _golden_assertion()
    runner_hash = rts._finding_baseline_hash(finding, GOLDEN_BASELINE_HASH)
    assert state_mod.fingerprint_finding(finding, runner_hash) == GOLDEN_ASSERTION_UNVERSIONED


def test_unit_fingerprint_golden() -> None:
    finding = UnitDriftFinding(
        kind="content_drift",
        name="felix-canary.service",
        repo_source="scripts/office2/felix-canary.service",
    )
    assert state_mod.fingerprint_finding(finding, "") == GOLDEN_UNIT


def test_detector_disabled_approved_cron_keeps_golden_enabled_mismatch_fingerprint() -> None:
    """A genuinely disabled (literal False) approved cron, end to end through
    the detector, fingerprints exactly as it did before #1127."""
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
            "id": CRON_ID,
            "name": "inbox-5pm",
            "agentId": "felix-admin-capture",
            "enabled": False,
            "createdAtMs": 1775153265189,
            "schedule": {"kind": "cron", "expr": "0 17 * * *", "tz": "America/New_York"},
        }
    ]
    findings = detect_cron_drift(live, baseline)
    assert [f.kind for f in findings] == ["enabled_mismatch"]
    assert (
        state_mod.fingerprint_finding(findings[0], GOLDEN_BASELINE_HASH)
        == GOLDEN_CRON["enabled_mismatch"]
    )
