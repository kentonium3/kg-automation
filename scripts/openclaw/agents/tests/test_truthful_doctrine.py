"""Fleet-guard test for the truthful-reporting + mechanism-fidelity doctrine
(mission felix-truthful-reporting-01KX6MN5, WP01, fixes kentonium3/kg-automation#683).

Asserts SC-004: the canonical Truthful Reporting & Mechanism Fidelity block is
present, byte-for-byte identical, in all 7 fleet agent ``AGENTS.md`` files (plus
the 2 existing ``.tmpl`` variants), and that the no-unrequested-infrastructure
guardrail (FR-003) is present in ``main`` only and absent from the other 6
agents. Also re-asserts the 12,000-byte prompt-budget cap on the two at-cap
agents (``main``, ``felix-admin-calendar``) as a belt-and-suspenders check
alongside the sibling ``test_agents_md_size.py``.

This WP is doctrine/prompt only (C-001/C-003) — no OpenClaw runtime, no
detector code, no ``openclaw.json`` changes. These are pure file-content
assertions.
"""

from __future__ import annotations

from pathlib import Path

CAP = 12_000

# The single source of truth for the canonical doctrine block text (T001).
# Must appear byte-for-byte identical in all 7 AGENTS.md files and both
# existing .tmpl variants (capture, tasker).
TRUTHFUL_DOCTRINE_BLOCK = (
    "## Truthful Reporting & Mechanism Fidelity (ABSOLUTE)\n"
    "\n"
    "- **Truthful reporting**: report done **only** if you performed it and "
    "can cite the result; otherwise say exactly what you did/could not do. "
    "**Never** state an assumed or forecast completion as fact.\n"
    "- **Mechanism fidelity**: if a request names a mechanism (e.g. \"create "
    "a Vikunja task\"), fulfil **that** one or say you could not. **Never** "
    "silently substitute another (no \"scheduled a cron instead\").\n"
    "- Bypassed a wrapped creation helper? Record a completion-assertion via "
    "`python3 -m scripts.trust.completion_assertion` (normal helper paths "
    "auto-emit this).\n"
)

# The no-unrequested-infrastructure guardrail (FR-003), main-only.
NO_UNREQUESTED_INFRA_HEADING = "## No Unrequested Infrastructure (main)"

FLEET_AGENTS = [
    "main",
    "felix-admin-capture",
    "felix-admin-habits",
    "felix-admin-tasker",
    "felix-admin-escalation",
    "felix-admin-calendar",
    "felix-doc-auditor",
]

TMPL_VARIANTS = [
    "felix-admin-capture",
    "felix-admin-tasker",
]

AT_CAP_AGENTS = [
    "main",
    "felix-admin-calendar",
]


def _agents_md(repo_root: Path, agent: str) -> Path:
    return repo_root / "scripts/openclaw/agents" / agent / "AGENTS.md"


def _agents_md_tmpl(repo_root: Path, agent: str) -> Path:
    return repo_root / "scripts/openclaw/agents" / agent / "AGENTS.md.tmpl"


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


def test_doctrine_block_present_in_tmpl_variants(repo_root: Path) -> None:
    """The 2 existing .tmpl variants (capture, tasker) must not drift from
    their deployed AGENTS.md counterpart."""
    for agent in TMPL_VARIANTS:
        p = _agents_md_tmpl(repo_root, agent)
        assert p.exists(), f"missing: {p}"
        text = p.read_text(encoding="utf-8")
        assert TRUTHFUL_DOCTRINE_BLOCK in text, (
            f"{agent}/AGENTS.md.tmpl is missing the canonical Truthful "
            "Reporting & Mechanism Fidelity block"
        )


def test_doctrine_block_identical_across_all_nine_insertions(
    repo_root: Path,
) -> None:
    """Belt-and-suspenders: every one of the 7 md + 2 tmpl insertions must
    match the exact same literal (guards against copy-paste drift that a
    substring check alone might not catch if surrounding text also matched)."""
    paths = [_agents_md(repo_root, agent) for agent in FLEET_AGENTS] + [
        _agents_md_tmpl(repo_root, agent) for agent in TMPL_VARIANTS
    ]
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

    # Also confirm it's absent from both .tmpl variants (neither is main's).
    for agent in TMPL_VARIANTS:
        p = _agents_md_tmpl(repo_root, agent)
        text = p.read_text(encoding="utf-8")
        assert NO_UNREQUESTED_INFRA_HEADING not in text, (
            f"{agent}/AGENTS.md.tmpl must NOT contain the No Unrequested "
            "Infrastructure block — it is scoped to main only"
        )


def test_at_cap_agents_still_under_prompt_budget(repo_root: Path) -> None:
    """NFR-003: main and felix-admin-calendar must remain < 12,000 bytes
    after the doctrine additions land. Mirrors test_agents_md_size.py's
    approach (raw byte size via st_size) as a belt-and-suspenders check
    scoped to this WP's edits. The 12,000-byte hard cap (NFR-001/NFR-004,
    mission felix-calendar-subagent-extraction-01KTTA33) applies only to
    these two agents — the other 5 fleet agents have larger effective
    prompt budgets and are intentionally NOT asserted against this cap
    here (see test_agents_md_size.py for the canonical size guard)."""
    for agent in AT_CAP_AGENTS:
        p = _agents_md(repo_root, agent)
        size = p.stat().st_size
        assert size < CAP, f"{agent}/AGENTS.md {size} >= {CAP}"
