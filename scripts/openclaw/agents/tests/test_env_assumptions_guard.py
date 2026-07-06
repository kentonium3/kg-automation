"""Test-CI fleet guard (#662, corrects #658).

Rides the existing kg-automation Test CI (collected from this tests/ dir) — no
`.github/workflows/` change (FR-003, C-001). Fails on any non-waived
runtime-environment assumption in a deployed agent prompt, with an actionable,
per-finding message (NFR-004). Deterministic + fast (a pure string scan over a
handful of small files — NFR-001/NFR-002).

This asserts the INVERTED policy (compliant = the exact checkout-`cd` form). It is
EXPECTED to be RED until WP02/WP03 swap the live fleet prompts off the old
`${PYTHONPATH:?}` form — that red state is the intended gate for those WPs. Do not
weaken this assertion to make it pass before the fleet is migrated.
"""

from __future__ import annotations

from scripts.openclaw.agents.env_assumptions import _default_root, scan_agents_root


def test_fleet_has_no_env_assumptions() -> None:
    findings = scan_agents_root(_default_root())
    assert not findings, "env-assumption violations across the agent fleet:\n" + "\n".join(
        f"  {f.path}:{f.line} {f.kind.value} — {f.remediation}" for f in findings
    )
