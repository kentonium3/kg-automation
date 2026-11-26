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
import re
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


def _repo_skills(repo_root: Path) -> set[str]:
    return {p.parent.name for p in (repo_root / SKILLS_ROOT).glob("*/SKILL.md")}


def _referenced_skills(text: str, repo: set[str]) -> set[str]:
    """Repo skills an AGENTS.md names: ``<name> skill`` (hyphen or underscore
    form, optionally backticked or possessive) or a ``skills/<name>`` path."""
    found = set()
    for name in repo:
        alt = re.escape(name) + "|" + re.escape(name.replace("-", "_"))
        if re.search(rf"\b(?:{alt})`?(?:'s)?\s+skill\b|skills/(?:{alt})\b", text):
            found.add(name)
    return found


def _announce_skills(repo_root: Path) -> list[str]:
    """Repo skill dirs any announce agent can see: its inventory ``skills``
    list plus any repo skill its AGENTS.md references by name.

    The inventory names skills with underscores, the source dirs with hyphens;
    bundled OpenClaw skills (``github``) have no repo source and are skipped.
    """
    data = json.loads((repo_root / INVENTORY).read_text(encoding="utf-8"))
    repo = _repo_skills(repo_root)
    found: set[str] = set()
    for svc in data["services"]:
        for slug, meta in (svc.get("agents") or {}).items():
            if slug in ANNOUNCE_AGENTS and isinstance(meta, dict):
                found.update(s.replace("_", "-") for s in meta.get("skills") or [])
    for agent in ANNOUNCE_AGENTS:
        found |= _referenced_skills(_text(repo_root, agent), repo)
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
        "then notify Kent on WhatsApp",
        "Tell Kent via WhatsApp",
        "Relay it to main.",
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
        "Message field is included in the JSON sent to Kent.",
        "Post-processing produces the main report.",
        "Relay the helper's stdout verbatim as your final reply to Kent.",
        "Message identity for Kent",
        "| Message | Kent's reply text |",
        "- Post the routing-log entry before the main loop.",
        "error.message(",
        'Tell Kent: "Couldn\'t process that."',
        "tell Kent the rule gives no date",
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
    skills = _announce_skills(repo_root)
    assert {"escalation", "vikunja-api", "task-intelligence"} <= set(skills), skills


def test_skills_referenced_by_name_are_covered(repo_root: Path) -> None:
    """A skill an announce AGENTS.md names (habits -> task-intelligence) is
    scanned even if the inventory skills list omitted it."""
    repo = _repo_skills(repo_root)
    referenced = _referenced_skills(_text(repo_root, "felix-admin-habits"), repo)
    assert "task-intelligence" in referenced
    assert referenced <= set(_announce_skills(repo_root))
    assert _referenced_skills("Run the task-intelligence skill's rules.", repo) == {"task-intelligence"}


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


def test_capture_research_rule_boundary(repo_root: Path) -> None:
    """Only an explicit research ask is parse_failure; one parse_failure halts
    finalize for the whole note, so the boundary must be stated (#1144 r2)."""
    from scripts.inbox.classify_content import classify_block

    text = _text(repo_root, "felix-admin-capture")
    for clause in (
        "Only an explicit ask to research or investigate a topic qualifies",
        '"look into options for X and report back"',
        "a task that merely involves looking something up stays `vikunja_task`",
        '"I should look into Y" stays someday',
        "One `parse_failure` halts finalize for the whole note",
    ):
        assert clause in text, clause
    # The classifier leaves the open-ended form for judgment, never parse_failure.
    assert classify_block("I should look into Y")[0] != "parse_failure"


def test_escalation_records_before_final_reply_and_never_waits(repo_root: Path) -> None:
    text = _text(repo_root, "felix-admin-escalation")
    assert "if WhatsApp delivery failed" not in text
    assert "record only the tasks included in your final reply" in text
    assert text.index("Record events — BEFORE the final reply") < text.index("Deliver — end the turn")
    assert "never call `wait` for a reply" in text


# --- R3b: no record_result (a recorded no_change suppresses the reply) -------


def test_block_forbids_record_result_and_unchanged_retry() -> None:
    """OpenClaw's injected hint says "record no_change"; a recorded no_change
    suppresses unsent content, so the block forbids the call (#1143 r3b)."""
    b = DELIVERY_DOCTRINE_BLOCK
    for clause in (
        "`automations`",
        "`record_result`",
        '"record no_change"',
        "suppresses your final reply",
        "Never repeat an unchanged call that was rejected for invalid input or schema",
        "fix the input from the error, or skip the call",
        "`partial`",
        "`--idempotent`",
    ):
        assert clause in b, clause


@pytest.mark.parametrize(
    "probe",
    [
        'automations({action:"record_result", outcome:"no_change"})',
        'automations({outcome:"no_change", action:"record_result"})',
        'automations({"action": "record_result", "outcome": "no_change"})',
        "automations({'action': 'record_result', 'outcome': 'no_change'})",
        'automations({\n  outcome: "no_change",\n  action: "record_result"\n})',
        "await automations ({ action: 'record_result' })",
        "If the automation tool offers record_result, record no_change without a summary.",
        "Record `no_change` on an idle turn.",
        "record a no_change result",
    ],
)
def test_record_result_probe_outside_block_is_flagged(probe: str) -> None:
    """Each probe, appended to a prompt that KEEPS the block, must be caught."""
    text = "## Steps\n\n" + DELIVERY_DOCTRINE_BLOCK + "\n" + probe + "\n"
    assert delivery_violations(text), f"not flagged: {probe!r}"


@pytest.mark.parametrize(
    "benign",
    [
        '{"status": "no_change", "created": 0}',
        "It prints ONE JSON object; branch on `status`:",
        '`"status": "idle"` → reply IDLE.',
        "outcome `partial`: running remove again resumes it.",
        "The cron automations list is managed by felix-deployer.",
    ],
)
def test_record_result_benign_wording_is_not_flagged(benign: str) -> None:
    text = DELIVERY_DOCTRINE_BLOCK + "\n" + benign + "\n"
    assert delivery_violations(text) == [], benign


def test_observed_malformed_record_result_call_is_flagged(repo_root: Path) -> None:
    """Frozen regression: the call capture made twice at 2026-11-26 22:00Z."""
    call = (repo_root / FIXTURES / "record-result-call-observed-1143.txt").read_text(encoding="utf-8")
    assert 'automations({action:"record_result", status:"no_change"})' in call
    joined = "\n".join(delivery_violations(DELIVERY_DOCTRINE_BLOCK + "\n" + call))
    assert "tool-record-result" in joined and "tool-automations" in joined, joined


def test_escalation_keeps_headroom_after_block_growth(repo_root: Path) -> None:
    """Escalation must end <= 17,900 UTF-16 units (#1143 r3b, Codex finding 4)."""
    from scripts.openclaw.agents.prompt_budgets import chars

    n = chars(repo_root / AGENTS_ROOT / "felix-admin-escalation" / "AGENTS.md")
    assert n <= 17_900, n
