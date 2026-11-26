"""TOOLS.md is retired from every active OpenClaw workspace (#1135).

OpenClaw 2026.11.7 dropped TOOLS.md from ``WORKSPACE_BOOTSTRAP_FILENAMES``, so it
is no longer injected into any agent's prompt. A tool note in TOOLS.md is
invisible to the model, and a pointer telling the model to "see TOOLS.md"
points at text it never receives. The mechanics now live in sections of each
agent's AGENTS.md, which OpenClaw does load (and which is the only file in the
subagent bootstrap allowlist).

Guards:
  * no active workspace (``SUSPENDED_WORKSPACES`` skipped) carries a TOOLS.md;
  * no prompt file agent-prompt-sync deploys for an active workspace mentions
    TOOLS.md;
  * no repo SKILL.md an active agent can see mentions TOOLS.md. An agent with
    no ``skills`` list in the inventory (main) is unscoped and sees every
    deployed repo skill, so it pulls in all of them.

felix-doc-auditor is suspended and out of scope; unsuspending it requires the
same merge.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.openclaw.agents.validate_workspace import discover_workspaces
from scripts.openclaw.deploy.deploy_agent_prompts import IN_SCOPE_FILENAMES

AGENTS_ROOT = Path("scripts/openclaw/agents")
SKILLS_ROOT = Path("scripts/openclaw/skills")
INVENTORY = Path("docs/design/architecture/data/service-inventory.json")
RETIRED = "TOOLS.md"


def _active(repo_root: Path) -> list[Path]:
    workspaces = discover_workspaces(repo_root / AGENTS_ROOT)
    assert workspaces, "no active workspaces discovered"
    return workspaces


#: Repo skills exempt from the mention guard, each with its reason.
SKILL_EXEMPTIONS = {
    # Consumed by felix-doc-auditor, which is suspended (SUSPENDED_WORKSPACES)
    # and out of #1135's scope; main sees it only because main is unscoped.
    # Unsuspending doc-auditor requires the same merge, and this exemption goes.
    "doc-audit": "felix-doc-auditor is suspended; out of scope for #1135",
}


def _repo_skills(repo_root: Path) -> set[str]:
    return {p.parent.name for p in (repo_root / SKILLS_ROOT).glob("*/SKILL.md")}


def _active_agent_skills(repo_root: Path) -> set[str]:
    """Repo skill directory names any active agent can see.

    An explicit ``skills`` list scopes the agent; the inventory names skills
    with underscores (``vikunja_api``), the source directories use hyphens
    (``vikunja-api``). An absent list means unscoped: every repo skill.
    """
    data = json.loads((repo_root / INVENTORY).read_text(encoding="utf-8"))
    active = {d.name for d in _active(repo_root)}
    every = _repo_skills(repo_root)
    skills: set[str] = set()
    for svc in data["services"]:
        for slug, meta in (svc.get("agents") or {}).items():
            if slug not in active or not isinstance(meta, dict):
                continue
            listed = meta.get("skills")
            if listed is None:
                skills |= every
            else:
                skills.update(s.replace("_", "-") for s in listed)
    return skills & every


def test_no_active_workspace_has_tools_md(repo_root: Path) -> None:
    offenders = [
        str((ws / RETIRED).relative_to(repo_root))
        for ws in _active(repo_root)
        if (ws / RETIRED).exists()
    ]
    assert not offenders, f"retired {RETIRED} still present: {offenders}"


def test_no_deployed_prompt_file_mentions_tools_md(repo_root: Path) -> None:
    offenders = []
    for ws in _active(repo_root):
        for name in sorted(IN_SCOPE_FILENAMES):
            p = ws / name
            if p.is_file() and RETIRED in p.read_text(encoding="utf-8"):
                offenders.append(str(p.relative_to(repo_root)))
    assert not offenders, f"prompt files still point at {RETIRED}: {offenders}"


def test_no_active_agent_skill_mentions_tools_md(repo_root: Path) -> None:
    # Only repo-sourced skills (the ones agent-skill-sync deploys); bundled
    # OpenClaw skills such as ``github`` have no source here.
    skills = _active_agent_skills(repo_root) - set(SKILL_EXEMPTIONS)
    assert skills, "no repo-sourced active-agent skills resolved from the inventory"
    offenders = []
    for name in sorted(skills):
        p = repo_root / SKILLS_ROOT / name / "SKILL.md"
        if RETIRED in p.read_text(encoding="utf-8"):
            offenders.append(str(p.relative_to(repo_root)))
    assert not offenders, f"active-agent skills still point at {RETIRED}: {offenders}"


def test_tools_md_not_synced(repo_root: Path) -> None:
    assert RETIRED not in IN_SCOPE_FILENAMES


def test_unscoped_main_sees_every_repo_skill(repo_root: Path) -> None:
    """main has no skills list, so the guard must cover every repo skill."""
    assert _active_agent_skills(repo_root) == _repo_skills(repo_root)


def test_skill_exemptions_are_real_and_still_needed(repo_root: Path) -> None:
    for name in SKILL_EXEMPTIONS:
        p = repo_root / SKILLS_ROOT / name / "SKILL.md"
        assert p.is_file(), f"stale exemption: {name}"
        assert RETIRED in p.read_text(encoding="utf-8"), f"exemption no longer needed: {name}"
