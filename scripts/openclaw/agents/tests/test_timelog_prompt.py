"""Fleet-guard test for the WP04 main-prompt time-logging integration.

Mission felix-time-logging-01KX79HT, WP04 (option A: main conducts the
time-logging dialog directly, no sub-agent delegation). Asserts that
``scripts/openclaw/agents/main/AGENTS.md`` contains a terse Time-logging
section that:

* recognizes the ``log ... hrs for ...`` intent shape (FR-001),
* calls the ``timelog`` helper directly via the anchored ``-m`` form and does
  NOT route through ``openclaw agent --agent`` (option A integrity), and
* names the load-bearing typed statuses main must handle, especially the
  truthful-reporting-critical ``client_created_entry_failed`` and ``error``
  (#683).

Also re-asserts the NFR-001 12,000-byte hard cap on ``main/AGENTS.md`` — the
budget forcing function for both the WP04 compression pass (T011) and this
addition (T012). ``test_agents_md_size.py`` already asserts this; this file
adds a second, WP04-scoped assertion so the size guard travels with the
time-logging test intent and is not accidentally decoupled from it.

Contract (authoritative): ``kitty-specs/felix-time-logging-01KX79HT/contracts/timelog-cli.md``
section C1 (the 13-status ``TimelogResult`` union).
"""

from __future__ import annotations

from pathlib import Path

CAP = 12_000

#: Post-F8 headroom floor (Codex post-merge review): main/AGENTS.md must keep
#: real slack under the 12,000-byte cap, not merely squeak under it. The F8
#: compression pass reclaimed >= 400 bytes; this guard requires that headroom
#: be preserved so a future edit that eats it fails loudly instead of silently
#: re-approaching the cap.
MIN_HEADROOM = 400

#: Statuses this test requires the Time-logging section to name explicitly.
#: These are the ones the T013 spec calls out as load-bearing: the
#: recognizer/extraction path (implicitly covered by the invocation string
#: assertions below) plus the truthful-reporting-critical clarification and
#: failure signals.
REQUIRED_STATUSES = (
    "unknown_client",
    "need_field",
    "client_created_entry_failed",
    "error",
)


def _time_logging_section(text: str) -> str:
    """Extract the Time-logging section's text (heading to next ``## ``).

    Scoping the "no delegation" assertion to just this section (rather than
    the whole file) is required because other, pre-existing delegation
    sections in ``main/AGENTS.md`` (inbox/habits/calendar) legitimately use
    ``openclaw agent --agent ...`` — a whole-file assertion would be
    impossible to satisfy and would not test option A's actual invariant
    (this specific path has no delegation).
    """
    start = text.index("## Time-logging")
    rest = text[start + len("## Time-logging"):]
    next_heading = rest.index("\n## ")
    return text[start:start + len("## Time-logging") + next_heading]


def test_time_logging_section_present(repo_root: Path) -> None:
    """The prompt has a Time-logging heading (T012 stable marker)."""
    p = repo_root / "scripts/openclaw/agents/main/AGENTS.md"
    text = p.read_text(encoding="utf-8")
    assert "## Time-logging" in text, "missing Time-logging section heading"


def test_time_logging_recognizes_intent(repo_root: Path) -> None:
    """The section documents the 'log ... hrs for ...' recognizer shape (FR-001)."""
    p = repo_root / "scripts/openclaw/agents/main/AGENTS.md"
    section = _time_logging_section(p.read_text(encoding="utf-8"))
    assert "log <N> hrs for <client>" in section, (
        "Time-logging section should document the recognizer intent shape"
    )
    assert "non-billable" in section, "non-billable variant must be documented"


def test_time_logging_calls_helper_directly_anchored(repo_root: Path) -> None:
    """main calls `timelog` via the anchored -m form under the venv python.

    The Google client libs live ONLY in the felix-calendar venv (office2 system
    python3 lacks them), and timelog.py imports sheets_helper in-process — so the
    interpreter main runs MUST be the venv python, not bare python3. Asserting the
    venv path here is the guard that would have caught the go-live invocation bug.
    """
    p = repo_root / "scripts/openclaw/agents/main/AGENTS.md"
    section = _time_logging_section(p.read_text(encoding="utf-8"))
    assert (
        "cd /home/claude/kg-automation && "
        "/data/services/openclaw/felix-calendar/venv/bin/python "
        "-m scripts.google.timelog"
    ) in section, (
        "Time-logging section must invoke the helper with the anchored "
        "checkout-cd + venv-python + -m module form (system python3 lacks the "
        "Google libs)"
    )
    assert "python3 -m scripts.google.timelog" not in section, (
        "must NOT use bare python3 (no Google libs in the system interpreter)"
    )


def test_time_logging_has_no_sub_agent_delegation(repo_root: Path) -> None:
    """Option A integrity: the time-log path does not delegate to a sub-agent.

    Scoped to the Time-logging section only — other sections of
    main/AGENTS.md (inbox/habits/calendar delegation) legitimately use
    ``openclaw agent --agent ...`` for their own (different) paths.
    """
    p = repo_root / "scripts/openclaw/agents/main/AGENTS.md"
    section = _time_logging_section(p.read_text(encoding="utf-8"))
    assert "openclaw agent --agent" not in section, (
        "Time-logging section must NOT delegate via `openclaw agent --agent` "
        "(option A: main calls the helper directly, no sub-agent)"
    )


def test_time_logging_names_key_typed_statuses(repo_root: Path) -> None:
    """The section names the load-bearing statuses main must handle (#683)."""
    p = repo_root / "scripts/openclaw/agents/main/AGENTS.md"
    section = _time_logging_section(p.read_text(encoding="utf-8"))
    missing = [s for s in REQUIRED_STATUSES if s not in section]
    assert not missing, f"Time-logging section is missing status handling for: {missing}"


def test_main_agents_md_under_12k_budget_guard(repo_root: Path) -> None:
    """Budget guard (NFR-001): main/AGENTS.md stays under the 12,000B cap with
    real headroom (F8).

    Mirrors ``test_agents_md_size.py::test_main_agents_md_under_12k`` — kept
    here too so the WP04 time-logging addition's own test suite gates the
    budget it depends on, not just the fleet-wide size test. The F8 post-merge
    review tightened this from a bare ``< 12000`` to ``>= MIN_HEADROOM`` free
    so the prompt cannot silently creep back to the cap.
    """
    p = repo_root / "scripts/openclaw/agents/main/AGENTS.md"
    assert p.exists(), f"missing: {p}"
    size = p.stat().st_size
    assert size < CAP, f"main/AGENTS.md {size} >= {CAP}"
    headroom = CAP - size
    assert headroom >= MIN_HEADROOM, (
        f"main/AGENTS.md has only {headroom}B free (< {MIN_HEADROOM}B floor); "
        "the F8 compression headroom has eroded — compress before adding prose"
    )
