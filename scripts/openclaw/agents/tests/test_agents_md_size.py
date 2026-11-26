"""Prompt-size guards for OpenClaw agent prompts.

Limits and budgets come from ``scripts/openclaw/agents/prompt_budgets.py``, the
single source of truth; sizes are UTF-16 code units (``prompt_budgets.chars``),
the unit OpenClaw's injection limit counts.

History: NFR-001/NFR-004 (mission felix-calendar-subagent-extraction-01KTTA33)
set a 12,000 cap on main and felix-admin-calendar. #1134 added capture's 18,000
budget under OpenClaw's 20,000 injection limit. #1135 folded TOOLS.md into each
AGENTS.md (OpenClaw 2026.11.7 no longer loads TOOLS.md) and moved main to
18,000; calendar keeps 12,000.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.openclaw.agents.prompt_budgets import (
    BUDGETS,
    INJECTION_LIMIT,
    MAIN_USER_MD_BUDGET,
    USER_MD_INJECTION_LIMIT,
    agents_md_budget,
    chars,
)
from scripts.openclaw.agents.validate_workspace import discover_workspaces

AGENTS_ROOT = Path("scripts/openclaw/agents")


def _agents_md(repo_root: Path, agent: str) -> Path:
    p = repo_root / AGENTS_ROOT / agent / "AGENTS.md"
    assert p.exists(), f"missing: {p}"
    return p


def test_budgets_keep_headroom_under_injection_limit() -> None:
    for agent, budget in BUDGETS.items():
        assert budget < INJECTION_LIMIT, f"{agent} budget {budget} >= {INJECTION_LIMIT}"
    assert MAIN_USER_MD_BUDGET < USER_MD_INJECTION_LIMIT


def test_every_active_agent_has_a_budget(repo_root: Path) -> None:
    active = {d.name for d in discover_workspaces(repo_root / AGENTS_ROOT)}
    assert active == set(BUDGETS), (
        f"active workspaces {sorted(active)} != budgeted {sorted(BUDGETS)}"
    )


@pytest.mark.parametrize("agent", sorted(BUDGETS))
def test_agents_md_within_budget(repo_root: Path, agent: str) -> None:
    """Fleet guard: every active AGENTS.md fits its budget (#1135)."""
    n = chars(_agents_md(repo_root, agent))
    budget = agents_md_budget(agent)
    assert n <= budget, f"{agent}/AGENTS.md is {n} chars > budget {budget}"


def test_main_user_md_within_bootstrap_budget(repo_root: Path) -> None:
    """main/USER.md must fit the 4,000-char limit with headroom (#1134)."""
    p = repo_root / AGENTS_ROOT / "main" / "USER.md"
    n = chars(p)
    assert n <= MAIN_USER_MD_BUDGET, f"main/USER.md is {n} chars > budget {MAIN_USER_MD_BUDGET}"
