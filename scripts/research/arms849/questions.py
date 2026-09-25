"""The answer-key-free question manifest (rubric §3, Amendment A4; research.md D-14).

Eight rows, verbatim from the rubric's table, in protocol order (ask_time
ascending). The harness never passes a bare question id to an arm; it passes a
:class:`Question`. ``MANIFEST_DIGEST`` is the constant the design lead
re-registered on 2026-09-25 (rubric @c8237d27) after both hands reproduced it;
``verify`` compares this module's rows to it and never records a computed
value in its place.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

__all__ = ["MANIFEST_DIGEST", "QUESTIONS", "Question", "ask_time_dt", "by_id", "manifest_bytes", "verify"]


@dataclass(frozen=True)
class Question:
    id: str
    arc: str
    ask_time: str
    text: str


#: Rubric §3 table, verbatim, in order.
QUESTIONS: tuple[Question, ...] = (
    Question("C1", "C", "2026-04-28T09:06:00-04:00",
             "Fred just sent this. What is he referring to, and what do I owe him?"),
    Question("A", "A", "2026-06-09T09:15:00-04:00",
             "Marcus just moved our Friday 1:1 to Thursday. Is that a problem, and what should I do?"),
    Question("F1", "F", "2026-08-10T09:00:00-04:00",
             "Am I keeping my non-negotiables?"),
    Question("B1", "B", "2026-08-17T09:00:00-04:00",
             "Am I on track for the October 5K?"),
    Question("E2", "E", "2026-09-04T17:00:00-04:00",
             "For this week's email across all three accounts: which should reach me, which become "
             "to-dos, which are digested, which are filed, and which are dropped?"),
    Question("E1", "E", "2026-09-21T09:00:00-04:00",
             "What recurring manual work am I doing that should be automated?"),
    Question("F2", "F", "2026-09-25T09:00:00-04:00",
             "When should this have been caught?"),
    Question("B2", "B", "2026-10-16T09:00:00-04:00",
             "Why did I miss sub-10?"),
)

#: Registered in rubric §3 (A4, re-registered 2026-09-25 00:22Z @c8237d27). A constant, cited.
MANIFEST_DIGEST = "fe17beef263777261e5d623ed8362ebaaada60ffbb0fd20b10b1f4d7a820c462"


def manifest_bytes() -> bytes:
    """A4's serialisation rule, exactly.

    Per row ``{"question": id, "ask_time": <T-form ISO>, "question_text": text}``
    rendered with ``json.dumps(row, sort_keys=True, ensure_ascii=False)``; the
    eight lines joined with LF plus one trailing LF; UTF-8.
    """
    lines = [
        json.dumps({"question": q.id, "ask_time": q.ask_time, "question_text": q.text},
                   sort_keys=True, ensure_ascii=False)
        for q in QUESTIONS
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def verify() -> tuple[bool, str]:
    got = hashlib.sha256(manifest_bytes()).hexdigest()
    if got == MANIFEST_DIGEST:
        return True, f"manifest digest {got} == registered"
    return False, f"manifest digest {got} != registered {MANIFEST_DIGEST}"


def by_id(question_id: str) -> Question:
    for q in QUESTIONS:
        if q.id == question_id:
            return q
    raise KeyError(f"unknown question id {question_id!r}")


def ask_time_dt(question: Question | str) -> datetime:
    q = question if isinstance(question, Question) else by_id(question)
    return datetime.fromisoformat(q.ask_time)
