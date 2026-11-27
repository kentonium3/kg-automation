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
        "fix the input from the error, or skip it and say so in your final reply",
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


# --- #1146: guard coverage (FR-001), false positives (FR-002), clause scope ---


def _flagged(line: str) -> set[str]:
    """Pattern names reported for ``line`` appended to a prompt with the block."""
    problems = delivery_violations("## Steps\n\n" + DELIVERY_DOCTRINE_BLOCK + "\n" + line + "\n")
    return {p.split(" at line ")[0] for p in problems}


@pytest.mark.parametrize(
    ("line", "pattern"),
    [
        pytest.param("Record **no_change** on an idle turn.", "record-no-change", id="bold-no-change"),
        pytest.param("When nothing changed, use the automations tool.", "tool-automations", id="automations-tool"),
        pytest.param('catalog.search("automations")', "tool-automations", id="catalog-search"),
        pytest.param("automations.record({outcome:'no_change'})", "tool-automations", id="automations-method"),
        pytest.param("Mark the run no_change.", "record-no-change", id="mark-run"),
        pytest.param("Recording no_change is fine on an idle run.", "record-no-change", id="recording"),
        pytest.param("set outcome to no_change", "record-no-change", id="set-outcome"),
        pytest.param("Next, notify Kent via WhatsApp.", "imperative-deliver", id="next-notify"),
    ],
)
def test_fr001_form_is_flagged(line: str, pattern: str) -> None:
    assert pattern in _flagged(line), f"{pattern} not reported for {line!r}"


@pytest.mark.parametrize(
    "line",
    [
        "Process the inbox, then notify Kent via WhatsApp.",
        "Summarise, then notify main.",
        "1. Collect results; then notify main.",
    ],
)
def test_then_notify_with_channel_stays_flagged(line: str) -> None:
    """Ratchet: already caught before #1146; the clause work must keep it."""
    assert "imperative-deliver" in _flagged(line), line


# Each FR-002 case and its positive control come from ONE template: the first
# filling carries the exempting context, the second removes it.
_EXEMPT_PAIRS = [
    pytest.param(
        "The {}automations (inbox-7am, noon) run on announce.", "cron ", "", "tool-automations",
        id="prose-cron-automations",
    ),
    pytest.param(
        "The record_result{} is never set by this agent.", " field", "", "tool-record-result",
        id="field-mention",
    ),
    pytest.param(
        "The `record_result` {} is never set by this agent.", "key", "value", "tool-record-result",
        id="key-mention-backticked",
    ),
    pytest.param(
        "The {}record_result is unused.", "field named ", "", "tool-record-result",
        id="field-named",
    ),
    pytest.param(
        'The schema lists "record_result"{} true.', ":", "", "tool-record-result",
        id="schema-key",
    ),
    pytest.param("{} no_change.", "Do not record", "Record", "record-no-change", id="do-not"),
    pytest.param("{} no_change.", "Never record", "Record", "record-no-change", id="never"),
    pytest.param(
        "{} a no_change result.", "Don't record", "Record", "record-no-change", id="dont"),
    pytest.param(
        "{} no_change.", "Don’t record", "Record", "record-no-change", id="dont-curly"),
    pytest.param(
        "{} **no_change**.", "You must not record", "Record", "record-no-change", id="must-not-bold"),
    pytest.param(
        "{} the run no_change.", "Never mark", "Mark", "record-no-change", id="never-mark"),
    pytest.param(
        "{} the run outcome to no_change.", "Never set", "Set", "record-no-change",
        id="never-set-outcome",
    ),
    pytest.param(
        "{} the `automations` tool.", "Never use", "Use", "tool-automations",
        id="never-use-tool",
    ),
    pytest.param(
        "- {} no_change here", "do not record", "record", "record-no-change", id="list-item"),
    pytest.param(
        "then notify Kent{} when finished", "", " via WhatsApp", "imperative-deliver",
        id="then-notify-no-channel",
    ),
    pytest.param(
        "Relay it to main{}.", " as your final reply", "", "imperative-deliver",
        id="final-reply-same-clause",
    ),
]


@pytest.mark.parametrize(("template", "exempting", "removed", "pattern"), _EXEMPT_PAIRS)
def test_fr002_exempt_form_passes(
    template: str, exempting: str, removed: str, pattern: str
) -> None:
    line = template.format(exempting)
    assert _flagged(line) == set(), f"flagged: {line!r}"


@pytest.mark.parametrize(("template", "exempting", "removed", "pattern"), _EXEMPT_PAIRS)
def test_fr002_positive_control_is_flagged(
    template: str, exempting: str, removed: str, pattern: str
) -> None:
    line = template.format(removed)
    assert pattern in _flagged(line), f"{pattern} not reported for {line!r}"


@pytest.mark.parametrize(
    ("line", "pattern"),
    [
        pytest.param(
            "Notify Kent via WhatsApp; include errors in your final reply.",
            "imperative-deliver", id="semicolon",
        ),
        pytest.param(
            "Relay it as your final reply; then notify Kent via WhatsApp.",
            "imperative-deliver", id="second-clause-after-exempt-one",
        ),
        pytest.param(
            "Notify Kent via WhatsApp, and include errors in your final reply.",
            "imperative-deliver", id="comma-and",
        ),
        pytest.param(
            "Send Kent the digest — errors go in your final reply.",
            "imperative-send", id="em-dash",
        ),
        pytest.param(
            "Notify Kent via WhatsApp. Put errors in your final reply.",
            "imperative-deliver", id="sentence-end",
        ),
        pytest.param(
            "| Notify Kent via WhatsApp | errors go in the final reply |",
            "imperative-deliver", id="table-cells",
        ),
        pytest.param("Use the cron automations tool.", "tool-automations", id="cron-automations-tool"),
    ],
)
def test_exempt_clause_does_not_cover_its_neighbour(line: str, pattern: str) -> None:
    assert pattern in _flagged(line), f"{pattern} not reported for {line!r}"


@pytest.mark.parametrize(
    ("line", "pattern"),
    [
        ("Do not skip this: record no_change.", "record-no-change"),
        ("Never record no_change twice; record no_change once.", "record-no-change"),
        ("Do not forget to record no_change.", "record-no-change"),
        ("Never fail to record no_change.", "record-no-change"),
        ("Never record anything but no_change.", "record-no-change"),
        ("Never record no_change unless the run is idle.", "record-no-change"),
        ("Never record the run twice, mark it no_change.", "record-no-change"),
        ("Don't record a total, always record no_change.", "record-no-change"),
        ("Don't record the run as ok when it should be no_change.", "record-no-change"),
        ("Never mark a run ok if no_change applies.", "record-no-change"),
        ("Do not record anything and just report no_change.", "record-no-change"),
        ("Never use the automations tool except to log.", "tool-automations"),
        ("Do not skip this: use the automations tool.", "tool-automations"),
        ('Never call automations({action: "list"}).', "tool-automations"),
        ("Never forget the automations tool.", "tool-automations"),
        ("Set the record_result field to no_change.", "tool-record-result"),
        ("await cron automations ({action: 'list'})", "tool-automations"),
        ("cron automations.list()", "tool-automations"),
        ('{"record_result": "no_change"}', "tool-record-result"),
        ("cron automations (outcome: idle)", "tool-automations"),
    ],
)
def test_exemption_does_not_widen(line: str, pattern: str) -> None:
    assert pattern in _flagged(line), f"{pattern} not reported for {line!r}"


@pytest.mark.parametrize(
    ("line", "pattern"),
    [
        pytest.param("**Record** no_change when idle.", "record-no-change", id="bold-verb"),
        pytest.param("Mark the run **no_change**.", "record-no-change", id="bold"),
        pytest.param("Record *no_change* when idle.", "record-no-change", id="italic"),
        pytest.param("Record _no_change_ when idle.", "record-no-change", id="underscore-italic"),
        pytest.param("__Mark__ the run __no_change__.", "record-no-change", id="underscore-bold"),
        pytest.param("Record ***no_change*** when idle.", "record-no-change", id="bold-italic"),
        pytest.param("Use the **automations** tool.", "tool-automations", id="bold-between-words"),
        pytest.param("Use the *automations* tool.", "tool-automations", id="italic-between-words"),
        pytest.param(
            "Use the ***automations*** tool.", "tool-automations", id="bold-italic-between-words"),
        pytest.param("Use the `automations` tool.", "tool-automations", id="backtick"),
        pytest.param("catalog.search(`automations`)", "tool-automations", id="backtick-search"),
        pytest.param("| idle | mark the run `no_change` |", "record-no-change", id="table-cell"),
        pytest.param("Mark the run\nno_change.", "record-no-change", id="soft-wrap"),
    ],
)
def test_formatting_does_not_hide_wording(line: str, pattern: str) -> None:
    assert pattern in _flagged(line), f"{pattern} not reported for {line!r}"


@pytest.mark.parametrize(
    ("line", "pattern"),
    [
        ("Call _conversations_send_ now.", "tool-conversations"),
        ("Call `sessions_*` now.", "tool-sessions"),
        ("_Then use sessions_*_ now.", "tool-sessions"),
        ("***use sessions_**.", "tool-sessions"),
        ("**Never use conversations_***", "tool-conversations"),
        ("__x_ record `no_change`_.", "record-no-change"),
        ("If offered, _record_result_ it.", "tool-record-result"),
        ("Note **send the report** now.", "imperative-send"),
        ("Idle turn **notify Kent via WhatsApp**", "imperative-deliver"),
    ],
)
def test_normalisation_keeps_identifiers_and_instruction_starts(
    line: str, pattern: str
) -> None:
    """Stripping delimiters keeps identifiers whole and loses no existing catch."""
    assert pattern in _flagged(line), f"{pattern} not reported for {line!r}"


@pytest.mark.parametrize(
    "benign",
    [
        "- Record the totals\n- status stays no_change",
        "| Record | no_change count |",
        "Record the totals.\n\nThe status no_change means nothing to do.",
    ],
)
def test_list_cell_and_paragraph_boundaries_stop_a_match(benign: str) -> None:
    assert _flagged(benign) == set(), benign


def test_longer_identifier_is_not_no_change() -> None:
    assert _flagged("Record the no_change_count in the summary.") == set()


def test_violation_cites_the_original_line() -> None:
    rest = "intro\n\n| a | b |\nRecord **no_change** on idle.\n"
    problems = delivery_violations(DELIVERY_DOCTRINE_BLOCK + rest)
    assert problems == ["record-no-change at line ~4: Record **no_change** on idle."]


def test_one_message_per_pattern_per_clause() -> None:
    line = "Record no_change and mark the run no_change"
    problems = delivery_violations(DELIVERY_DOCTRINE_BLOCK + line + "\n")
    assert len(problems) == 1, problems
    two = delivery_violations(DELIVERY_DOCTRINE_BLOCK + "Record no_change; mark it no_change\n")
    assert len(two) == 2, two


# --- #1146 review round 1: soft wraps, exception context, structured values ---


def _check(line: str, pattern: str | None) -> None:
    """``pattern`` is reported for ``line``; ``None`` means nothing is."""
    found = _flagged(line)
    if pattern is None:
        assert found == set(), f"flagged: {line!r}"
    else:
        assert pattern in found, f"{pattern} not reported for {line!r}"


# Review item 1: an exception cancels the negation wherever it sits in the
# sentence. Same fixture, with and without the exception.
@pytest.mark.parametrize(
    ("template", "tail", "pattern"),
    [
        ("Do not record no_change{}.", "", None),
        ("Do not record no_change{}.", "\nunless the run is idle", "record-no-change"),
        ("Do not record no_change{}.", ", but do so when idle", "record-no-change"),
        ("Do not record no_change{}.", ";\nexcept on errors", "record-no-change"),
        ("Do not record no_change{}.", " (e.g. after errors) unless idle", "record-no-change"),
        ("Do not record\nno_change{}.", "", None),
        ("Do not record\nno_change{}.", ", but\ndo so when idle", "record-no-change"),
        ("Never use the automations tool{}.", "", None),
        ("Never use the automations tool{}.", "\nunless asked", "tool-automations"),
        ("Never use the automations tool{}.", ", but call it when idle", "tool-automations"),
        ("Do not record no_change{}.", ".\nReport errors, but briefly", None),
        ("Do not record no_change{}.", ". Except when idle", "record-no-change"),
        ("Do not record no_change{}.", ".\nUnless the run is idle", "record-no-change"),
        ("Do not record no_change{}.", ". Report any exception", None),
    ],
)
def test_review1_negation_exception_context(template: str, tail: str, pattern: str | None) -> None:
    _check(template.format(tail), pattern)


# Review item 2: a soft wrap is a space; a blank line, list item, table row or
# heading is a boundary. Same sentence, different separator.
@pytest.mark.parametrize(
    ("separator", "pattern"),
    [
        (" ", "imperative-deliver"),
        ("\n", "imperative-deliver"),
        ("\n  ", "imperative-deliver"),
        ("\n\n", None),
        ("\n- ", None),
        ("\n2. ", None),
        (" |\n| ", None),
        ("\n## ", None),
        ("\n```\n", None),
    ],
)
def test_review2_soft_wrap_joins_a_paragraph_only(separator: str, pattern: str | None) -> None:
    _check(f"Process the inbox, then notify Kent{separator}via WhatsApp.", pattern)


@pytest.mark.parametrize(
    ("line", "pattern"),
    [
        ("Notify\nKent\nvia\nWhatsApp.", "imperative-deliver"),
        ("- Then relay the digest\n  to main.", "imperative-deliver"),
        ("> Then notify Kent\n> via WhatsApp.", "imperative-deliver"),
        ("Send Kent one\nWhatsApp.", "send-whatsapp"),
        ("_Record\nno_change_ on idle.", "record-no-change"),
        ("__Mark the\nrun__ no_change.", "record-no-change"),
        ("_Record\nthe totals_ only.", None),
        ("_Record\n\nno_change_ on idle.", None),
        ("Relay it to main\nas your final reply.", None),
        ("Relay it to main.", "imperative-deliver"),
        ("Relay the stdout to main as your final\nreply.", None),
        ("Runs from the cron automations (inbox-7am,\nnoon) only.", None),
        ("Runs from the automations (inbox-7am,\nnoon) only.", "tool-automations"),
        # An unpunctuated line that starts a new instruction keeps its own clause.
        ("Collect the results\nSend the digest now.", "imperative-send"),
        ("Return it as your final reply\nSend the digest now.", "imperative-send"),
        ("Notify Kent via WhatsApp\nRecord the rest in your final reply.", "imperative-deliver"),
        ("Notify Kent via WhatsApp;\ninclude errors in your final reply.", "imperative-deliver"),
    ],
)
def test_review2_wrapped_wording(line: str, pattern: str | None) -> None:
    _check(line, pattern)


def test_review2_cites_the_line_where_the_match_starts() -> None:
    rest = "intro\n\nProcess the inbox, then\nnotify Kent\nvia WhatsApp.\n"
    problems = delivery_violations(DELIVERY_DOCTRINE_BLOCK + rest)
    assert problems == ["imperative-deliver at line ~4: notify Kent"]


# Review item 3: the whole structured value decides, however it is wrapped.
@pytest.mark.parametrize("value", ["true", '"no_change"'])
@pytest.mark.parametrize(
    "template",
    [
        'If idle, emit {{"record_result": {}}}.',
        'If idle, emit {{"record_result":\n{}}}.',
        '```json\n{{\n  "record_result": true,\n\n  "outcome": {}\n}}\n```',
        '{{"record_result": true,\n "detail": {{"outcome": {}}}}}',
        "Set the record_result field to\n{}.",
        "Fill the record_result field. Use {} when idle.",
        "Fill the record_result field. Use\n{} when idle.",
        "The record_result field\nis required.\nIt takes {}.",
    ],
)
def test_review3_structured_value(template: str, value: str) -> None:
    pattern = "tool-record-result" if "no_change" in value else None
    _check(template.format(value), pattern)


# Review item 4: explicit routing after a colon covers its own lead-in only.
@pytest.mark.parametrize(
    ("template", "after", "pattern"),
    [
        ("Send the digest: {}.", "it is your final reply", None),
        ("Send the digest:\n{}.", "it is your final reply", None),
        ("Send the digest: {}.", "as your final reply", None),
        ("Send the digest: {}.", "put it in your final reply", None),
        ("Send the digest: {}.", "it is urgent", "imperative-send"),
        ("Send the digest: {}.", "it is not your final reply", "imperative-send"),
        ("Notify Kent via WhatsApp: {}.", "include errors in your final reply", "imperative-deliver"),
        ("Notify Kent via WhatsApp: {}.", "in your final reply say so", "imperative-deliver"),
        ("Do not skip this: {}.", "record no_change", "record-no-change"),
    ],
)
def test_review4_routing_across_a_colon(template: str, after: str, pattern: str | None) -> None:
    _check(template.format(after), pattern)


# --- #1146 review round 2: a new sentence on the next line keeps its own waiver ---


# One fixture: a delivery instruction, a line end, then the words that mention the
# final reply. A capitalised first word starts a new sentence, so the waiver does
# not reach back; a lower-case one continues the sentence, so it does.
@pytest.mark.parametrize(
    ("separator", "first", "pattern"),
    [
        ("\n", "Include", "imperative-deliver"),
        ("\n", "Put", "imperative-deliver"),
        ("\n", "Return", "imperative-deliver"),
        ("\n", "Record", "imperative-deliver"),
        ("\n", "Any", "imperative-deliver"),
        ("\n  ", "Record", "imperative-deliver"),
        ("\n  ", "Include", "imperative-deliver"),
        ("\n\t", "Include", "imperative-deliver"),
        ("\n", '"Include', "imperative-deliver"),
        ("\n", "(Include", "imperative-deliver"),
        ("\n", "**Include**", "imperative-deliver"),
        ("\n  ", "**Send** the", "imperative-deliver"),
        ("\n", "include", None),
        ("\n  ", "include", None),
        ("\n", "and include", None),
        (" and ", "Include", None),
    ],
)
def test_review5_next_sentence_does_not_waive(
    separator: str, first: str, pattern: str | None
) -> None:
    _check(f"Notify Kent via WhatsApp{separator}{first} errors in your final reply.", pattern)


@pytest.mark.parametrize(
    "line",
    [
        "Send the digest: it is your final reply.",
        "Send the digest:\nIt is your final reply.",
        "Send the digest:\n  It is your final reply.",
        "Relay it to main\nas your final reply.",
    ],
)
def test_review5_routing_still_waives(line: str) -> None:
    _check(line, None)
