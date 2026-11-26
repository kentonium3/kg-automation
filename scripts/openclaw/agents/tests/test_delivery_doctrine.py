"""Announce-delivery doctrine guard (#1143, D4).

The three announce-cron agents (capture, escalation, habits) must carry the
canonical ``DELIVERY_DOCTRINE_BLOCK`` byte-for-byte, exactly once, and no
wording outside it may tell the model to send, ship or relay a message itself.
A frozen copy of capture's pre-fix prompt (the text that produced the
2026-11-25/26 cron failures) is asserted to FAIL the same check, so the test is
shown to bite rather than claimed to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.openclaw.agents.delivery_doctrine import (
    ANNOUNCE_AGENTS,
    DELIVERY_DOCTRINE_BLOCK,
    delivery_violations,
)

AGENTS_ROOT = Path("scripts/openclaw/agents")
PRE_FIX_FIXTURE = AGENTS_ROOT / "tests/fixtures/capture-agents-md-pre-1143.md"


def _text(repo_root: Path, agent: str) -> str:
    return (repo_root / AGENTS_ROOT / agent / "AGENTS.md").read_text(encoding="utf-8")


def test_block_names_final_reply_and_forbidden_tools() -> None:
    b = DELIVERY_DOCTRINE_BLOCK
    assert b.startswith("## ") and b.endswith("\n")
    assert "final reply" in b and "ONE final reply" in b
    for name in ("`conversations_*`", "`sessions_*`", "`message`", "`send()`"):
        assert name in b, name


def test_block_itself_passes_the_wording_check() -> None:
    """The block forbids sending; it must not trip its own patterns."""
    assert delivery_violations(DELIVERY_DOCTRINE_BLOCK) == []


@pytest.mark.parametrize("agent", ANNOUNCE_AGENTS)
def test_announce_agent_carries_block_and_no_send_wording(
    repo_root: Path, agent: str
) -> None:
    problems = delivery_violations(_text(repo_root, agent))
    assert problems == [], f"{agent}/AGENTS.md:\n" + "\n".join(problems)


def test_pre_fix_capture_prompt_fails(repo_root: Path) -> None:
    """Red evidence kept green: today's (pre-#1143) capture text must FAIL."""
    problems = delivery_violations((repo_root / PRE_FIX_FIXTURE).read_text(encoding="utf-8"))
    joined = "\n".join(problems)
    assert "delivery block occurrences: 0" in joined
    assert "send-whatsapp" in joined
    assert "this-turns-message" in joined
    assert "payload-to-main" in joined


def test_capture_identity_matches_configured_model(repo_root: Path) -> None:
    """Capture runs sonnet-4-6 (#743); its identity lines must say so."""
    text = _text(repo_root, "felix-admin-capture")
    assert "felix-admin-capture:haiku" not in text
    assert "Sent by felix-admin-capture:sonnet" in text
