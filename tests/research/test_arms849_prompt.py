"""The registered prompt digests to the A4 constant and refuses drift (WP01 T002)."""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import prompt as P
from scripts.research.arms849.text import Block

RUBRIC = REPO_ROOT / "docs" / "design" / "research" / "849-rubric.md"


def test_shipped_text_digests_to_the_registered_constant():
    ok, detail = P.verify()
    assert ok, detail
    assert P.digest(P.REGISTERED_TEXT) == P.REGISTERED_DIGEST


def test_a_one_character_change_is_refused():
    drifted = P.REGISTERED_TEXT.replace("Answer the question directly.", "Answer the question directly!")
    assert P.digest(drifted) != P.REGISTERED_DIGEST
    with pytest.raises(P.PromptDriftError):
        P.Prompt(text=drifted)


@pytest.mark.skipif(not RUBRIC.exists(), reason="rubric not present in this environment")
def test_shipped_text_equals_the_rubric_fenced_text():
    """Guards the transcription itself, not just the digest."""
    rub = RUBRIC.read_text(encoding="utf-8")
    m = re.search(r"### 3\.2 .*?```text\n(.*?)```", rub, re.DOTALL)
    assert m, "rubric §3.2 fenced block not found"
    assert P.normalise(m.group(1)) == P.normalise(P.REGISTERED_TEXT)


def test_normalisation_rules():
    assert P.normalise("a \r\nb\n\n\n") == b"a\nb\n"
    assert P.normalise("a\nb") == b"a\nb\n"


def test_render_substitutes_each_slot_exactly_once():
    block = Block(event_refs=("e1",), record_keys=(), data=b'{"ref": "e1", "text": "x {braces} y"}\n')
    out = P.Prompt().render(block, "Why?").decode("utf-8")
    assert out.count(P.SLOT_CONTEXT) == 0 and out.count(P.SLOT_QUESTION) == 0
    assert '{"ref": "e1", "text": "x {braces} y"}\n' in out
    assert out.endswith("Question: Why?\n")
    head = P.REGISTERED_TEXT.split("=== MATERIAL ===")[0]
    assert out.startswith(head)


def test_render_refuses_a_string():
    with pytest.raises(TypeError):
        P.Prompt().render("raw text", "Why?")  # type: ignore[arg-type]


def test_a_block_containing_the_question_slot_literal_is_inserted_untouched():
    """Codex WP01 cycle 1: sequential replace altered material containing the literal slot."""
    block = Block(event_refs=("e1",), record_keys=(), data=b'{"text": "see {question_text} and {assembled_context}"}\n')
    out = P.Prompt().render(block, "Why?").decode("utf-8")
    assert '{"text": "see {question_text} and {assembled_context}"}\n' in out
    assert out.endswith("Question: Why?\n")
    assert out.count("Question: ") == 1
