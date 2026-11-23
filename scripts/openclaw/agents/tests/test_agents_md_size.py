"""NFR-001 and NFR-004 file-size assertions for OpenClaw agent prompts.

These tests enforce the 12,000-character hard cap on
``main/AGENTS.md`` (NFR-001) and ``felix-admin-calendar/AGENTS.md``
(NFR-004) authored during mission
felix-calendar-subagent-extraction-01KTTA33.

Initial (RED) state at WP01 landing:
    * ``test_main_agents_md_under_12k`` FAILS — main is ~25,982 chars.
    * ``test_felix_admin_calendar_agents_md_under_12k`` FAILS — the
      felix-admin-calendar directory does not yet exist.

WP02 lands felix-admin-calendar/AGENTS.md to flip the second test to
GREEN. WP03 tightens main/AGENTS.md to flip the first test to GREEN.
"""

from __future__ import annotations

from pathlib import Path

CAP = 12_000


def test_main_agents_md_under_12k(repo_root: Path) -> None:
    """main/AGENTS.md must stay below the 12K hard cap (NFR-001)."""
    p = repo_root / "scripts/openclaw/agents/main/AGENTS.md"
    assert p.exists(), f"missing: {p}"
    size = p.stat().st_size
    assert size < CAP, f"main/AGENTS.md {size} >= {CAP}"


def test_felix_admin_calendar_agents_md_under_12k(repo_root: Path) -> None:
    """felix-admin-calendar/AGENTS.md must stay below the 12K hard cap (NFR-004)."""
    p = repo_root / "scripts/openclaw/agents/felix-admin-calendar/AGENTS.md"
    assert p.exists(), f"missing: {p}"
    size = p.stat().st_size
    assert size < CAP, f"felix-admin-calendar/AGENTS.md {size} >= {CAP}"


# --- OpenClaw bootstrap injection limits (#1134) ------------------------------
#
# OpenClaw 2026.11.7 truncates a workspace bootstrap file that exceeds its
# per-file injection limit (gateway log: "workspace bootstrap file <name> is N
# chars (limit L); truncating in injected context"), so the model never sees
# part of it. Limits are measured in characters (UTF-16 code units here),
# not bytes. Budgets below keep ~10% headroom under each limit
# (Kent, 2026-11-23: trim the sources, do not raise the limits).

AGENTS_MD_INJECTION_LIMIT = 20_000
USER_MD_INJECTION_LIMIT = 4_000
CAPTURE_AGENTS_MD_BUDGET = 18_000
MAIN_USER_MD_BUDGET = 3_600


def _chars(p: Path) -> int:
    """Length as JavaScript ``String.length`` counts it (UTF-16 code units).

    OpenClaw is JavaScript, so its limit is most likely ``.length``. That is
    never smaller than the code-point count, so this is the conservative
    measure.
    """
    assert p.exists(), f"missing: {p}"
    return len(p.read_text(encoding="utf-8").encode("utf-16-le")) // 2


def test_capture_agents_md_within_bootstrap_budget(repo_root: Path) -> None:
    """felix-admin-capture/AGENTS.md must fit the 20,000-char limit with headroom (#1134)."""
    n = _chars(repo_root / "scripts/openclaw/agents/felix-admin-capture/AGENTS.md")
    assert n <= CAPTURE_AGENTS_MD_BUDGET < AGENTS_MD_INJECTION_LIMIT, (
        f"felix-admin-capture/AGENTS.md is {n} chars > budget {CAPTURE_AGENTS_MD_BUDGET}"
    )


def test_main_user_md_within_bootstrap_budget(repo_root: Path) -> None:
    """main/USER.md must fit the 4,000-char limit with headroom (#1134)."""
    n = _chars(repo_root / "scripts/openclaw/agents/main/USER.md")
    assert n <= MAIN_USER_MD_BUDGET < USER_MD_INJECTION_LIMIT, (
        f"main/USER.md is {n} chars > budget {MAIN_USER_MD_BUDGET}"
    )
