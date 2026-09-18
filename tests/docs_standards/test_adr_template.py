"""The ADR authoring template must emit a conforming document (#987 FR-007).

A new ADR should satisfy the contract at creation rather than being migrated
later. This template was missed entirely in the first decomposition: it emitted
`doc_type: guide` and carried no decision log, so every ADR created from it
would have violated the contract the moment it was written.

The template is Templater-driven, so the emitted frontmatter is the SECOND
`---` block (the first describes the template file itself). These tests assert
the static parts of what gets emitted; the dynamic parts (`id`, `title`, date)
are Templater expressions and are checked for presence only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "docs" / "_templates" / "decision.md"
sys.path.insert(0, str(REPO / "tooling" / "scripts"))

from doc_taxonomy import load_taxonomy  # noqa: E402


@pytest.fixture(scope="module")
def emitted() -> str:
    """The frontmatter block a new ADR receives."""
    text = TEMPLATE.read_text(encoding="utf-8")
    blocks = re.findall(r"^---\n(.*?)\n---", text, re.S | re.M)
    assert len(blocks) >= 2, "expected a template block and an emitted block"
    return blocks[1]


@pytest.fixture(scope="module")
def body() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_template_exists():
    assert TEMPLATE.exists(), "the ADR authoring template must not be renamed silently"


def test_emits_doc_type_decision(emitted):
    """It emitted `guide`, so ADRs were born with the wrong type."""
    assert re.search(r"^doc_type:\s*decision\s*$", emitted, re.M), emitted


def test_emits_a_status_valid_for_a_decision(emitted):
    m = re.search(r"^status:\s*(\S+)\s*$", emitted, re.M)
    assert m, emitted
    assert m.group(1) in load_taxonomy().statuses_for("decision")


def test_emits_a_decision_log_section(body):
    assert "## Decision log" in body


def test_the_emitted_log_is_the_valid_empty_form(body):
    """`*No entries.*` is a distinct valid grammar — absence is not."""
    tail = body.split("## Decision log", 1)[1]
    assert "*No entries.*" in tail


def test_decision_log_is_the_last_section(body):
    """The validator requires it last; the template must not teach otherwise."""
    tail = body.split("## Decision log", 1)[1]
    assert not re.search(r"^#{1,6}\s", tail, re.M), f"heading after the log: {tail[:80]}"


def test_emits_no_body_status_line(body):
    """Frontmatter is authoritative (Kent, 2026-09-18); two sources disagree."""
    after_fm = body.split("---", 4)[-1]
    assert not re.search(r"^\*\*Status\*\*:", after_fm, re.M)


def test_template_teaches_the_type_vocabulary(body):
    """An author choosing a Type should not have to find the contract."""
    for kind in ("erratum", "amendment", "superseded-by", "context"):
        assert kind in body, kind


def test_template_teaches_the_pipe_escape(body):
    """The narrowed grammar only works if the author is told about it."""
    assert r"\|" in body
