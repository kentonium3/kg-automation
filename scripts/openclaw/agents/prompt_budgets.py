"""Single source of truth for OpenClaw agent prompt-size limits and budgets.

OpenClaw 2026.11.7 truncates a workspace bootstrap file that exceeds its
per-file injection limit (gateway log: "workspace bootstrap file <name> is N
chars (limit L); truncating in injected context"), so the model never sees part
of it. The limit is measured in characters as JavaScript ``String.length``
counts them (UTF-16 code units), not bytes, and applies to every agent (#1134;
re-verified on office2 for #1135: no agent overrides it).

Budgets keep headroom under the limit:
  * AGENTS.md: 18,000 for every agent except felix-admin-calendar, which keeps
    its original 12,000 (NFR-004). main moved from 12,000 to 18,000 when
    TOOLS.md was folded into AGENTS.md (Kent's ruling on #1135, 2026-11-26); the
    18,000 figure is capture's #1134 budget.
  * main/USER.md: 3,700 under USER.md's 4,000 limit (Kent, 2026-11-23: absolute
    dates in place of relative ages).

Every prompt-size test imports from here. Change a budget here and nowhere else.
"""

from __future__ import annotations

from pathlib import Path

#: OpenClaw per-file bootstrap injection limit, UTF-16 code units.
INJECTION_LIMIT = 20_000

#: USER.md injection limit (#1134).
USER_MD_INJECTION_LIMIT = 4_000

#: Default AGENTS.md budget for an active agent.
DEFAULT_AGENTS_MD_BUDGET = 18_000

#: Per-agent AGENTS.md budgets, keyed by workspace directory name.
BUDGETS: dict[str, int] = {
    "main": DEFAULT_AGENTS_MD_BUDGET,
    "felix-admin-capture": DEFAULT_AGENTS_MD_BUDGET,
    "felix-admin-calendar": 12_000,
    "felix-admin-escalation": DEFAULT_AGENTS_MD_BUDGET,
    "felix-admin-habits": DEFAULT_AGENTS_MD_BUDGET,
    "felix-admin-tasker": DEFAULT_AGENTS_MD_BUDGET,
}

#: main/USER.md budget (#1134).
MAIN_USER_MD_BUDGET = 3_700


def chars(p: Path) -> int:
    """Length as JavaScript ``String.length`` counts it (UTF-16 code units).

    OpenClaw is JavaScript, so its limit is ``.length``. That is never smaller
    than the code-point count, so this is the conservative measure.
    """
    return len(p.read_text(encoding="utf-8").encode("utf-16-le")) // 2


def agents_md_budget(agent: str) -> int:
    """AGENTS.md budget for ``agent``; an unlisted active agent gets the default."""
    return BUDGETS.get(agent, DEFAULT_AGENTS_MD_BUDGET)
