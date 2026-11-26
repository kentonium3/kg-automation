"""Architectural guard: agent and skill docs never tell an agent to write a Vikunja task.

Mission felix-rrule-adaptation-01M7TKNX, WP04 (FR-006, research.md R-005).
The escalation agent's ``N done`` procedure used to start with a bare
``POST /api/v1/tasks/{id}`` with ``{"done": true}``. On the RRULE server a
v1 narrow write strips the recurrence rule. Task writes belong to the Felix
helpers, which write through ``VikunjaClient.patch_task`` on v2 and check
the rule afterwards.

This test scans ``scripts/openclaw/agents/**/*.md`` and
``scripts/openclaw/skills/**/SKILL.md``. It fails on any logical line (a
shell line continued with ``\\`` is joined first, so a multi-line ``curl``
counts as one line) that combines a write verb (``POST``, ``PUT``,
``PATCH``, or ``curl -X POST|PUT|PATCH``) with a **task resource** path:
``/tasks/{id}``, ``/tasks/<id>``, ``/tasks/:id``, ``/tasks/TASK_ID``,
``/tasks/123`` or ``/tasks/...``, under ``/api/v1``, ``/api/v2`` or bare.

Not matched, on purpose:

- sub-resources (``/tasks/{id}/comments``, ``/labels``, ``/relations``).
  They carry no rule (research.md audit "missed but harmless").
- a line that is a negative example: ``Never`` / ``Do not`` / ``DO NOT`` /
  ``Don't`` appears **before** the write verb on the same line.

The allowlist names files that may still match, each with a reason. An
entry may only be **removed** (WP09 removes the two it rewrites); adding one
is a review decision.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENCLAW = REPO_ROOT / "scripts" / "openclaw"

#: repo-relative path -> reason. Removing an entry is always allowed.
ALLOWLIST: dict[str, str] = {}

_VERB = re.compile(r"(?:curl\b[^\n]*?-X\s*(?:POST|PUT|PATCH)\b|\b(?:POST|PUT|PATCH)\b)")
_TASK_RESOURCE = re.compile(
    r"(?:/api/v[12])?/tasks/"
    r"(?:\{[^}/]*\}|<[^>/]*>|:id\b|\$\{?\w+\}?|[A-Z][A-Z_]*\b|\d+|\.\.\.)"
    r"(?=$|[\s`\"')?,;|\]])"
)
_NEGATION = re.compile(r"\b(?:never|do not|don't)\b", re.IGNORECASE)


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Return ``(first_line_number, text)`` with ``\\`` continuations joined."""
    out: list[tuple[int, str]] = []
    buffer: list[str] = []
    start = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        if not buffer:
            start = number
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buffer.append(stripped[:-1])
            continue
        buffer.append(stripped)
        out.append((start, " ".join(part.strip() for part in buffer)))
        buffer = []
    if buffer:
        out.append((start, " ".join(part.strip() for part in buffer)))
    return out


def direct_task_writes(text: str) -> list[tuple[int, str]]:
    """Return the offending logical lines of *text* (empty when clean)."""
    hits: list[tuple[int, str]] = []
    for number, line in _logical_lines(text):
        verb = _VERB.search(line)
        if verb is None or _TASK_RESOURCE.search(line) is None:
            continue
        negation = _NEGATION.search(line)
        if negation is not None and negation.start() < verb.start():
            continue
        hits.append((number, line))
    return hits


def _scanned_docs() -> list[Path]:
    agents = sorted((OPENCLAW / "agents").rglob("*.md"))
    skills = sorted((OPENCLAW / "skills").rglob("SKILL.md"))
    return agents + skills


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------


def test_docs_are_scanned() -> None:
    docs = {p.relative_to(REPO_ROOT).as_posix() for p in _scanned_docs()}
    assert "scripts/openclaw/agents/felix-admin-escalation/AGENTS.md" in docs
    # Escalation's Vikunja mechanics live in its AGENTS.md since #1135 (TOOLS.md retired).
    assert "scripts/openclaw/agents/main/AGENTS.md" in docs
    assert "scripts/openclaw/skills/escalation/SKILL.md" in docs


@pytest.mark.parametrize(
    "doc",
    _scanned_docs(),
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_doc_has_no_direct_task_write(doc: Path) -> None:
    rel = doc.relative_to(REPO_ROOT).as_posix()
    if rel in ALLOWLIST:
        pytest.skip(f"allowlisted: {ALLOWLIST[rel]}")
    hits = direct_task_writes(doc.read_text(encoding="utf-8"))
    assert not hits, (
        f"{rel} tells an agent to write a Vikunja task directly; route the "
        "write through the Felix helper instead:\n"
        + "\n".join(f"  L{n}: {line}" for n, line in hits)
    )


def test_allowlist_entries_exist_and_have_reasons() -> None:
    for rel, reason in ALLOWLIST.items():
        assert (REPO_ROOT / rel).is_file(), f"stale allowlist entry: {rel}"
        assert reason.strip(), f"allowlist entry without a reason: {rel}"


# ---------------------------------------------------------------------------
# Guard self-tests (positive and negative synthetic docs)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        '1. Mark task complete: `POST /api/v1/tasks/{id}` with `{"done": true}`',
        "POST /api/v1/tasks/{id}\nContent-Type: application/json",
        "PATCH /api/v2/tasks/<task_id> with the new due date",
        "POST /tasks/{TASK_ID}",
        "PUT /tasks/:id",
        "curl -s -X POST \\\n  -H 'Auth: x' \\\n  https://h.test/api/v1/tasks/TASK_ID",
        "curl -X PATCH https://h.test/api/v2/tasks/1234",
        "POST /api/v1/tasks/{id} — never omit the repeat fields",
    ],
)
def test_guard_flags_direct_write(text: str) -> None:
    assert direct_task_writes(text)


@pytest.mark.parametrize(
    "text",
    [
        "GET /api/v1/tasks/{id}",
        "curl -s -H 'Auth: x' https://h.test/api/v1/tasks/TASK_ID",
        "PUT /tasks/{id}/comments with a [Felix] prefix",
        "PUT /tasks/{task_id}/labels with the label id",
        "PUT /projects/{id}/tasks with title",
        "**Never POST, PUT or PATCH a Vikunja task directly.** e.g. `POST /api/v1/tasks/{id}`",
        "DO NOT make inline `POST /api/v1/tasks/...` calls. The helper owns those writes.",
        "Do not `POST`/`PATCH` `due_date` directly.",
    ],
)
def test_guard_ignores_reads_subresources_and_negative_examples(text: str) -> None:
    assert direct_task_writes(text) == []
