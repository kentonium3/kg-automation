"""Fleet-guard test for the truthful-reporting + mechanism-fidelity doctrine
(mission felix-truthful-reporting-01KX6MN5, WP01, fixes kentonium3/kg-automation#683).

Asserts SC-004: the canonical Truthful Reporting & Mechanism Fidelity block is
present, byte-for-byte identical, in all 7 fleet agent ``AGENTS.md`` files, and
that the no-unrequested-infrastructure guardrail (FR-003) is present in ``main``
only and absent from the other 6 agents. (The ``.tmpl`` render variants this
test also covered were removed when the render mechanism was retired in #752 —
the committed ``AGENTS.md`` files are now the sole source.) Also re-asserts
each budgeted agent's AGENTS.md prompt budget (``prompt_budgets``, UTF-16
units) as a belt-and-suspenders check alongside the sibling
``test_agents_md_size.py``.

This WP is doctrine/prompt only (C-001/C-003) — no OpenClaw runtime, no
detector code, no ``openclaw.json`` changes. These are pure file-content
assertions.
"""

from __future__ import annotations

from pathlib import Path

from scripts.openclaw.agents.prompt_budgets import BUDGETS, chars
from scripts.openclaw.agents.truthful_doctrine import (
    NO_UNREQUESTED_INFRA_HEADING,
    TRUTHFUL_DOCTRINE_BLOCK,
)
from scripts.openclaw.agents.truthful_doctrine import FLEET_AGENTS as _FLEET_AGENTS

# The canonical doctrine block text + fleet composition now live in the shared
# scripts.openclaw.agents.truthful_doctrine module (single source of truth) so
# this repo-source test and the deploy verification (Codex F4) cannot drift.
FLEET_AGENTS = list(_FLEET_AGENTS)

def _agents_md(repo_root: Path, agent: str) -> Path:
    return repo_root / "scripts/openclaw/agents" / agent / "AGENTS.md"


def test_doctrine_block_present_in_all_seven_agents(repo_root: Path) -> None:
    """SC-004: the canonical block must be present, verbatim, in all 7 agents."""
    for agent in FLEET_AGENTS:
        p = _agents_md(repo_root, agent)
        assert p.exists(), f"missing: {p}"
        text = p.read_text(encoding="utf-8")
        assert TRUTHFUL_DOCTRINE_BLOCK in text, (
            f"{agent}/AGENTS.md is missing the canonical Truthful Reporting & "
            "Mechanism Fidelity block (or the text has drifted from the "
            "canonical literal)"
        )


def test_doctrine_block_identical_across_all_seven_insertions(
    repo_root: Path,
) -> None:
    """Belt-and-suspenders: every one of the 7 AGENTS.md insertions must match
    the exact same literal (guards against copy-paste drift that a substring
    check alone might not catch if surrounding text also matched)."""
    paths = [_agents_md(repo_root, agent) for agent in FLEET_AGENTS]
    for p in paths:
        text = p.read_text(encoding="utf-8")
        count = text.count(TRUTHFUL_DOCTRINE_BLOCK)
        assert count == 1, (
            f"{p} expected exactly one occurrence of the canonical doctrine "
            f"block, found {count}"
        )


def test_no_unrequested_infrastructure_present_in_main_only(
    repo_root: Path,
) -> None:
    """FR-003: the no-unrequested-infrastructure guardrail is main-only."""
    main_text = _agents_md(repo_root, "main").read_text(encoding="utf-8")
    assert NO_UNREQUESTED_INFRA_HEADING in main_text, (
        "main/AGENTS.md is missing the No Unrequested Infrastructure block"
    )

    other_agents = [a for a in FLEET_AGENTS if a != "main"]
    for agent in other_agents:
        p = _agents_md(repo_root, agent)
        text = p.read_text(encoding="utf-8")
        assert NO_UNREQUESTED_INFRA_HEADING not in text, (
            f"{agent}/AGENTS.md must NOT contain the No Unrequested "
            "Infrastructure block — it is scoped to main only (C-001/C-003)"
        )


def test_budgeted_agents_still_under_prompt_budget(repo_root: Path) -> None:
    """NFR-003: every budgeted fleet agent stays within its AGENTS.md budget
    after the doctrine additions land. Budgets and the UTF-16 measure come
    from ``prompt_budgets`` (the single source, #1135); felix-doc-auditor is
    suspended and carries no budget. See test_agents_md_size.py for the
    canonical size guard."""
    budgeted = [a for a in FLEET_AGENTS if a in BUDGETS]
    assert budgeted, "no fleet agent is budgeted"
    for agent in budgeted:
        n = chars(_agents_md(repo_root, agent))
        assert n <= BUDGETS[agent], f"{agent}/AGENTS.md {n} > {BUDGETS[agent]}"
