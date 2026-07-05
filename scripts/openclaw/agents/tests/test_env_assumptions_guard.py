"""Test-CI fleet guard (#658, WP05).

Rides the existing kg-automation Test CI (collected from this tests/ dir) — no
`.github/workflows/` change (FR-003, C-001). Fails on any non-waived
runtime-environment assumption in a deployed agent prompt, with an actionable,
per-finding message (NFR-004). Deterministic + fast (a pure string scan over a
handful of small files — NFR-001/NFR-002).
"""

from __future__ import annotations

from scripts.openclaw.agents.env_assumptions import _default_root, scan_agents_root


def test_fleet_has_no_env_assumptions() -> None:
    findings = scan_agents_root(_default_root())
    assert not findings, "env-assumption violations across the agent fleet:\n" + "\n".join(
        f"  {f.path}:{f.line} {f.kind.value} — {f.remediation}" for f in findings
    )
