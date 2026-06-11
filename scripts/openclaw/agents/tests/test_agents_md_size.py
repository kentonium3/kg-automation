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
