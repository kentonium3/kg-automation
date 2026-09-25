"""The registered §3.2 prompt (rubric Amendment A3/A4; spec FR-011; research.md D-14).

``REGISTERED_TEXT`` is the rubric's fenced text, byte for byte, with its two
literal slots. ``REGISTERED_DIGEST`` is the constant the design lead recorded
in §3.2; it is never computed here and then treated as authoritative — the
gate compares this module's text to that constant, and a one-character change
refuses the run.

Only a :class:`~scripts.research.arms849.text.Block` can be rendered into the
slot, so an arm cannot hand the prompt a string it built some other way.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from scripts.research.arms849.text import Block

__all__ = [
    "REGISTERED_DIGEST",
    "REGISTERED_TEXT",
    "SLOT_CONTEXT",
    "SLOT_QUESTION",
    "Prompt",
    "PromptDriftError",
    "digest",
    "normalise",
    "verify",
]

SLOT_CONTEXT = "{assembled_context}"
SLOT_QUESTION = "{question_text}"

#: Rubric §3.2, verbatim (16 lines). Do not reflow.
REGISTERED_TEXT = (
    "You are the assistant of the person whose records follow. You are reviewing their own\n"
    "calendar, tasks, messages and notes to answer one question they have asked.\n"
    "\n"
    "Use only the material provided below. Do not rely on outside knowledge about them, and do\n"
    "not invent events, dates or people that the material does not contain.\n"
    "\n"
    "Answer the question directly. State each finding as a specific claim, with the dates, times,\n"
    "counts and names the material supports. Where the material does not establish something,\n"
    "say \"the material does not establish this\" rather than guessing. Then say what you would\n"
    "do next, and why, in their terms.\n"
    "\n"
    "=== MATERIAL ===\n"
    "{assembled_context}\n"
    "=== END MATERIAL ===\n"
    "\n"
    "Question: {question_text}\n"
)

#: Registered in rubric §3.2 (A4). A constant, cited — never derived.
REGISTERED_DIGEST = "0aa7ee77560b1f5cbbb04a6c3dfa90749dfd79305b4207134c62d9fdd733af45"


class PromptDriftError(RuntimeError):
    """The shipped prompt text no longer digests to the registered constant."""


def normalise(text: str) -> bytes:
    """A4's normalisation: UTF-8, CRLF→LF, per-line trailing whitespace stripped, one trailing LF."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return ("\n".join(lines) + "\n").encode("utf-8")


def digest(text: str) -> str:
    return hashlib.sha256(normalise(text)).hexdigest()


def verify() -> tuple[bool, str]:
    """For the gate: does the shipped text digest to the registered constant?"""
    got = digest(REGISTERED_TEXT)
    if got == REGISTERED_DIGEST:
        return True, f"prompt digest {got} == registered"
    return False, f"prompt digest {got} != registered {REGISTERED_DIGEST}"


@dataclass(frozen=True)
class Prompt:
    """The registered prompt, asserted against its digest on construction."""

    text: str = REGISTERED_TEXT

    def __post_init__(self) -> None:
        got = digest(self.text)
        if got != REGISTERED_DIGEST:
            raise PromptDriftError(
                f"prompt text digests to {got}, registered is {REGISTERED_DIGEST}")
        if self.text.count(SLOT_CONTEXT) != 1 or self.text.count(SLOT_QUESTION) != 1:
            raise PromptDriftError("registered text must contain each slot exactly once")

    def render(self, block: Block, question_text: str) -> bytes:
        """Fill both slots in ONE pass over the registered template.

        A sequential replace would search the already-inserted material for the
        second slot: a block that happens to contain the literal question slot
        would be altered while the real slot stayed unfilled (Codex, WP01 cycle
        1). Splitting the template on both markers first means the inserted
        text is never searched.
        """
        if not isinstance(block, Block):
            raise TypeError("Prompt.render takes a Block, not a string — build it with render_block")
        head, rest = self.text.split(SLOT_CONTEXT, 1)
        mid, tail = rest.split(SLOT_QUESTION, 1)
        body = head + block.data.decode("utf-8") + mid + question_text + tail
        return body.encode("utf-8")
