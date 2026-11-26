"""Announce-delivery doctrine guard (#1143, D4).

The three announce-cron agents (capture, escalation, habits) must carry the
canonical ``DELIVERY_DOCTRINE_BLOCK`` byte-for-byte, exactly once, and no
wording outside it may tell the model to send, ship, notify or relay a message
itself, or name a send/agent tool. The repo skills those agents read are held
to the same wording check. Frozen pre-fix copies (the text that produced the
2026-11-25/26 cron failures) are asserted to FAIL, so the test is shown to bite
rather than claimed to.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.openclaw.agents.delivery_doctrine import (
    ANNOUNCE_AGENTS,
    DELIVERY_DOCTRINE_BLOCK,
    delivery_violations,
)

AGENTS_ROOT = Path("scripts/openclaw/agents")
SKILLS_ROOT = Path("scripts/openclaw/skills")
INVENTORY = Path("docs/design/architecture/data/service-inventory.json")
FIXTURES = AGENTS_ROOT / "tests/fixtures"


def _text(repo_root: Path, agent: str) -> str:
    return (repo_root / AGENTS_ROOT / agent / "AGENTS.md").read_text(encoding="utf-8")


def _announce_skills(repo_root: Path) -> list[str]:
    """Repo skill dirs any announce agent can see (inventory ``skills`` lists).

    The inventory names skills with underscores, the source dirs with hyphens;
    bundled OpenClaw skills (``github``) have no repo source and are skipped.
    """
    data = json.loads((repo_root / INVENTORY).read_text(encoding="utf-8"))
    repo = {p.parent.name for p in (repo_root / SKILLS_ROOT).glob("*/SKILL.md")}
    found: set[str] = set()
    for svc in data["services"]:
        for slug, meta in (svc.get("agents") or {}).items():
            if slug in ANNOUNCE_AGENTS and isinstance(meta, dict):
                found.update(s.replace("_", "-") for s in meta.get("skills") or [])
    return sorted(found & repo)


def test_block_names_final_reply_and_forbidden_tools() -> None:
    b = DELIVERY_DOCTRINE_BLOCK
    assert b.startswith("## ") and b.endswith("\n")
    assert "final reply" in b and "ONE final reply" in b
    for name in ("`conversations_*`", "`sessions_*`", "`message`", "`send()`"):
        assert name in b, name


def test_block_itself_passes_the_wording_check() -> None:
    """The block forbids sending; it must not trip its own patterns."""
    assert delivery_violations(DELIVERY_DOCTRINE_BLOCK) == []


@pytest.mark.parametrize(
    "probe",
    [
        "Ship the alert via WhatsApp.",
        "Notify Kent via WhatsApp.",
        "message Kent via WhatsApp",
        "Post the alert to WhatsApp",
        "Call conversations_send to deliver the alert.",
        "forward to main with sessions_send",
        "run `openclaw agent`",
    ],
)
def test_send_probe_outside_block_is_flagged(probe: str) -> None:
    """Each probe, appended to a prompt that KEEPS the block, must be caught."""
    text = "## Steps\n\n" + DELIVERY_DOCTRINE_BLOCK + "\n" + probe + "\n"
    assert delivery_violations(text), f"not flagged: {probe!r}"


@pytest.mark.parametrize(
    "benign",
    [
        "Sent by felix-admin-habits:sonnet",
        "When Kent sends a reply, parse it.",
        "quote the JSON `message` field",
        "The slug prefix attributes the message (observability).",
    ],
)
def test_benign_wording_is_not_flagged(benign: str) -> None:
    text = DELIVERY_DOCTRINE_BLOCK + "\n" + benign + "\n"
    assert delivery_violations(text) == [], benign


@pytest.mark.parametrize("agent", ANNOUNCE_AGENTS)
def test_announce_agent_carries_block_and_no_send_wording(
    repo_root: Path, agent: str
) -> None:
    problems = delivery_violations(_text(repo_root, agent))
    assert problems == [], f"{agent}/AGENTS.md:\n" + "\n".join(problems)


def test_announce_skills_resolved(repo_root: Path) -> None:
    assert "escalation" in _announce_skills(repo_root)


def test_announce_agent_skills_have_no_send_wording(repo_root: Path) -> None:
    offenders = {}
    for name in _announce_skills(repo_root):
        text = (repo_root / SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
        problems = delivery_violations(text, require_block=False)
        if problems:
            offenders[name] = problems
    assert not offenders, json.dumps(offenders, indent=2)


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        (
            "capture-agents-md-pre-1143.txt",
            ["delivery block occurrences: 0", "send-whatsapp", "this-turns-message",
             "payload-to-main", "tool-sessions", "tool-openclaw-agent"],
        ),
        (
            "escalation-agents-md-pre-1143.txt",
            ["delivery block occurrences: 0", "ship-message", "whatsapp-skill"],
        ),
        (
            "habits-agents-md-pre-1143.txt",
            ["delivery block occurrences: 0", "imperative-send"],
        ),
    ],
)
def test_pre_fix_prompts_fail(repo_root: Path, fixture: str, expected: list[str]) -> None:
    """Red evidence kept green: each pre-#1143 announce prompt must FAIL."""
    joined = "\n".join(delivery_violations((repo_root / FIXTURES / fixture).read_text(encoding="utf-8")))
    for kind in expected:
        assert kind in joined, f"{fixture}: expected {kind!r} in\n{joined}"


def test_pre_fix_escalation_skill_fails(repo_root: Path) -> None:
    text = (repo_root / FIXTURES / "escalation-skill-md-pre-1143.txt").read_text(encoding="utf-8")
    assert any("imperative-send" in p for p in delivery_violations(text, require_block=False))


def test_capture_identity_matches_configured_model(repo_root: Path) -> None:
    """Capture runs sonnet-4-6 (#743); its identity lines must say so."""
    text = _text(repo_root, "felix-admin-capture")
    assert "felix-admin-capture:haiku" not in text
    assert "Sent by felix-admin-capture:sonnet" in text


def test_capture_research_rule_covers_every_block(repo_root: Path) -> None:
    """classify_content returns "TODO: research heat pumps" as vikunja_task/high
    with no ambiguity flag, so the research rule must not be scoped to
    ambiguous blocks (#1144 review)."""
    from scripts.inbox.classify_content import classify_block

    got = classify_block("TODO: research heat pumps")
    kind = got["kind"] if isinstance(got, dict) else got[0]
    assert kind == "vikunja_task"
    text = _text(repo_root, "felix-admin-capture")
    assert "ANY block whose intent is a research request becomes `parse_failure`" in text


def test_escalation_records_before_final_reply_and_never_waits(repo_root: Path) -> None:
    text = _text(repo_root, "felix-admin-escalation")
    assert "if WhatsApp delivery failed" not in text
    assert "record only the tasks included in your final reply" in text
    assert text.index("Record events — BEFORE the final reply") < text.index("Deliver — end the turn")
    assert "never call `wait` for a reply" in text
