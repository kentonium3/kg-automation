"""Every skill an announce agent reads stays free of delivery wording (#1146).

FR-005 is verify-and-pin: no such skill instructs a send today, and this module
keeps it that way by running the wording check, in skill mode, over each one.
FR-004 is pinned here too: the escalation skill's daily-dedup text must describe
the check ``derive_state`` leaves to its caller.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.openclaw.agents.delivery_doctrine import ANNOUNCE_AGENTS, delivery_violations
from scripts.openclaw.agents.tests.test_delivery_doctrine import (
    INVENTORY,
    SKILLS_ROOT,
    _referenced_skills,
    _repo_skills,
    _text,
)

# Mirror of office2's ``agents.entries.<id>.skills``, plus any repo skill an
# agent's AGENTS.md tells it to run (habits -> task_intelligence). The live
# config is the authority; the post-deploy canary re-checks this mirror.
ANNOUNCE_AGENT_SKILLS: dict[str, tuple[str, ...]] = {
    "felix-admin-capture": ("vikunja_api", "github"),
    "felix-admin-escalation": ("escalation", "vikunja_api"),
    "felix-admin-habits": ("vikunja_api", "task_intelligence"),
}
# Skill id -> source directory under scripts/openclaw/skills/.
SKILL_SOURCES: dict[str, str] = {
    "escalation": "escalation",
    "task_intelligence": "task-intelligence",
    "vikunja_api": "vikunja-api",
}
# Mirrored skills with nothing in this repository to check, and why.
NO_REPO_SOURCE: dict[str, str] = {
    "github": "bundled with OpenClaw; this repository holds no source for it",
}

READ_BY_ANNOUNCE_AGENT = [
    pytest.param(agent, skill, id=f"{agent}-{skill}")
    for agent, skills in ANNOUNCE_AGENT_SKILLS.items()
    for skill in skills
    if skill in SKILL_SOURCES
]
SEND_ON_FAILURE = "Send Kent a WhatsApp if delivery fails."


def _skill_text(repo_root: Path, skill: str) -> str:
    return (repo_root / SKILLS_ROOT / SKILL_SOURCES[skill] / "SKILL.md").read_text(encoding="utf-8")


def test_mirror_covers_exactly_the_announce_agents() -> None:
    assert set(ANNOUNCE_AGENT_SKILLS) == set(ANNOUNCE_AGENTS)


def test_every_mirrored_skill_is_checked_or_explained(repo_root: Path) -> None:
    mirrored = {skill for skills in ANNOUNCE_AGENT_SKILLS.values() for skill in skills}
    assert mirrored == set(SKILL_SOURCES) | set(NO_REPO_SOURCE)
    assert not set(SKILL_SOURCES) & set(NO_REPO_SOURCE)
    for skill in SKILL_SOURCES:
        assert f"\nname: {skill}\n" in _skill_text(repo_root, skill), skill
    for skill, reason in NO_REPO_SOURCE.items():
        assert reason and skill.replace("_", "-") not in _repo_skills(repo_root), skill


@pytest.mark.parametrize("agent", ANNOUNCE_AGENTS)
def test_mirror_matches_the_committed_inventory_and_prompt(repo_root: Path, agent: str) -> None:
    """The mirror is the inventory's skill list plus the repo skills the prompt names."""
    data = json.loads((repo_root / INVENTORY).read_text(encoding="utf-8"))
    listed = [
        meta["skills"]
        for service in data["services"]
        for slug, meta in (service.get("agents") or {}).items()
        if slug == agent and isinstance(meta, dict)
    ]
    assert listed, f"{agent} is not in {INVENTORY}"
    referenced = _referenced_skills(_text(repo_root, agent), _repo_skills(repo_root))
    expected = {s for skills in listed for s in skills} | {r.replace("-", "_") for r in referenced}
    assert set(ANNOUNCE_AGENT_SKILLS[agent]) == expected


@pytest.mark.parametrize(("agent", "skill"), READ_BY_ANNOUNCE_AGENT)
def test_skill_has_no_delivery_wording(repo_root: Path, agent: str, skill: str) -> None:
    problems = delivery_violations(_skill_text(repo_root, skill), require_block=False)
    assert problems == [], f"{agent} reads {skill}:\n" + "\n".join(problems)


@pytest.mark.parametrize(("agent", "skill"), READ_BY_ANNOUNCE_AGENT)
def test_same_skill_with_a_send_on_failure_is_flagged(
    repo_root: Path, agent: str, skill: str
) -> None:
    """Positive control: the probe above can see a violation in this very text."""
    text = _skill_text(repo_root, skill) + "\n\n" + SEND_ON_FAILURE + "\n"
    problems = delivery_violations(text, require_block=False)
    assert any(p.startswith("send-whatsapp ") for p in problems), f"{agent}/{skill}: {problems}"


# --- FR-004: the escalation skill's daily-dedup text --------------------------
# The code fact it rests on (a Level 2 sent today still yields next level 2) is
# pinned by tests/escalation/test_derive_state.py::test_level_2_sent.


def _dedup_section(repo_root: Path) -> str:
    text = _skill_text(repo_root, "escalation")
    match = re.search(r"^## 7\. Daily Deduplication\n(.*?)(?=^## |^---$)", text, re.M | re.S)
    assert match, "section 7 not found"
    return " ".join(match.group(1).split())


def test_escalation_skill_has_no_comment_based_dedup(repo_root: Path) -> None:
    assert not re.search(r"level-[12N] \| sent", _skill_text(repo_root, "escalation"))


@pytest.mark.parametrize(
    "clause",
    [
        "per task per level per calendar day (America/New_York)",
        "`derive_state`",
        "per-project JSONL history",
        "Do not query task comments",
        "`last_event.state` is `level_sent`",
        "`last_event.level`",
        "`last_event.date` is today",
        "`next_eligible_level: 2`",
    ],
)
def test_escalation_dedup_text_describes_the_jsonl_check(repo_root: Path, clause: str) -> None:
    assert clause in _dedup_section(repo_root)
