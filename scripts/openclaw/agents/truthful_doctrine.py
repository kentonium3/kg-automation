"""Canonical truthful-reporting doctrine block + fleet verification (#683, WP01).

Single source of truth for the mission ``felix-truthful-reporting-01KX6MN5``
doctrine text and the fleet-composition constants, shared by:

- the repo-source fleet-guard test
  (``scripts/openclaw/agents/tests/test_truthful_doctrine.py``), which asserts
  the block is present byte-for-byte in every repo-source ``AGENTS.md``; and
- the deploy verification (``scripts/deploy/deploy-truthful-reporting.py``),
  which asserts the same block landed in every **deployed** fleet prompt after
  prompt-sync — so the deploy check and the repo test can never drift apart
  (Codex F4).

Deterministic string membership only — no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "TRUTHFUL_DOCTRINE_BLOCK",
    "NO_UNREQUESTED_INFRA_HEADING",
    "FLEET_AGENTS",
    "MAIN_ONLY_AGENT",
    "DoctrineCheck",
    "check_deployed_doctrine",
]

# The single source of truth for the canonical doctrine block text (T001).
# Must appear byte-for-byte identical in all fleet AGENTS.md files.
TRUTHFUL_DOCTRINE_BLOCK = (
    "## Truthful Reporting & Mechanism Fidelity (ABSOLUTE)\n"
    "\n"
    "- **Truthful reporting**: report done **only** if you performed it and "
    "can cite the result; otherwise say exactly what you did/could not do. "
    "**Never** state an assumed or forecast completion as fact.\n"
    "- **Mechanism fidelity**: if a request names a mechanism (e.g. \"create "
    "a Vikunja task\"), fulfil **that** one or say you could not. **Never** "
    "silently substitute another (no \"scheduled a cron instead\").\n"
    "- Bypassed a wrapped creation helper? Record a completion-assertion with "
    "the `scripts.trust.completion_assertion` helper (normal helper paths "
    "auto-emit this).\n"
)

# The no-unrequested-infrastructure guardrail (FR-003), main-only.
NO_UNREQUESTED_INFRA_HEADING = "## No Unrequested Infrastructure (main)"

# The 7 fleet agents that must carry the canonical doctrine block in their
# repo-source AGENTS.md (SC-004). NOTE: ``felix-doc-auditor`` is a retired
# openclaw workspace (scripts-first driver) with no deployed workspace
# AGENTS.md target — the deploy verification below therefore checks only the
# subset of these that have a live deployed prompt (see
# :func:`check_deployed_doctrine`), while the repo-source test asserts all 7.
FLEET_AGENTS = (
    "main",
    "felix-admin-capture",
    "felix-admin-habits",
    "felix-admin-tasker",
    "felix-admin-escalation",
    "felix-admin-calendar",
    "felix-doc-auditor",
)

# The agent that additionally carries the main-only guardrail (FR-003).
MAIN_ONLY_AGENT = "main"


@dataclass(frozen=True)
class DoctrineCheck:
    """Result of verifying deployed fleet prompts against the doctrine block.

    - ``ok`` — every checked prompt carried the canonical block, and the
      main-only prompt additionally carried the no-unrequested-infra block.
    - ``missing_block`` — deployed prompt paths (as strings) that were missing
      the canonical truthful-reporting block (or unreadable).
    - ``missing_main_only`` — deployed main prompt paths missing the
      no-unrequested-infra block (empty unless main is among the checked set).
    - ``checked`` — deployed prompt paths (as strings) that were verified.
    """

    ok: bool
    missing_block: list[str]
    missing_main_only: list[str]
    checked: list[str]


def check_deployed_doctrine(
    deployed_paths: dict[str, Path],
) -> DoctrineCheck:
    """Verify each deployed fleet AGENTS.md carries the canonical doctrine.

    ``deployed_paths`` maps ``agent_slug -> deployed AGENTS.md Path``. For each
    entry the canonical :data:`TRUTHFUL_DOCTRINE_BLOCK` must be present; for the
    :data:`MAIN_ONLY_AGENT` entry (if present) the
    :data:`NO_UNREQUESTED_INFRA_HEADING` must additionally be present. An
    unreadable file counts as missing the block (fail-safe: a verification
    failure fails the deploy self-test, never crashes).

    Deterministic string membership only — no LLM, no substring anchor games:
    it checks the exact canonical block, so it catches drift the old loose
    ``"truthful"`` substring could not (Codex F4).
    """
    missing_block: list[str] = []
    missing_main_only: list[str] = []
    checked: list[str] = []

    for slug, path in deployed_paths.items():
        checked.append(str(path))
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            missing_block.append(str(path))
            continue
        if TRUTHFUL_DOCTRINE_BLOCK not in content:
            missing_block.append(str(path))
        if slug == MAIN_ONLY_AGENT and NO_UNREQUESTED_INFRA_HEADING not in content:
            missing_main_only.append(str(path))

    ok = not missing_block and not missing_main_only
    return DoctrineCheck(
        ok=ok,
        missing_block=missing_block,
        missing_main_only=missing_main_only,
        checked=sorted(checked),
    )
