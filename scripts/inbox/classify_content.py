#!/usr/bin/env python3
"""Classify the body of an inbox note into structured blocks.

Reads a note (frontmatter + body), splits the body into semantic blocks
via the documented heuristic, and emits a ``ClassificationOutput`` JSON
object on stdout. Blocks the helper cannot confidently classify are
emitted with ``kind: "ambiguous"`` and ``flag: "needs-llm-disambiguation"``
so the agent prompt can disambiguate them via judgment.

CLI: ``python3 -m scripts.inbox.classify_content --content-file <abs-path>``
(per ``[[feedback_helper_m_invocation_form]]`` — script-path form is forbidden
and has caused two production incidents).

Block kinds (per FR-007):
  - ``journal``       — first-person reflective content
  - ``calendar``      — date/time references with an event verb
  - ``someday``       — aspirational language ("someday", "would like to")
  - ``github_issue``  — explicit ``gh issue:`` / ``bug:`` markers
  - ``vikunja_task``  — ``TODO:`` / ``task:`` / ``[ ]`` markers
  - ``parse_failure`` — felix-capture parse-error callout marker
  - ``ambiguous``     — fallback when no kind matches confidently

Heuristic documentation per FR-014: every regex pattern and keyword list
below carries an inline comment explaining what kind it indicates and why
the heuristic was chosen. The follow-on AGENTS.md rewrite reads these as
the canonical reference.

See ``kitty-specs/capture-d6-helpers-extraction-01KTMS5Q`` for the
authoritative spec, data-model, and contract.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Classification heuristics — documented per FR-014
# ---------------------------------------------------------------------------

# Refusal: C-001 — never read notes under 04-Growth/_private/
PRIVATE_PATH_FRAGMENT = "04-Growth/_private"

# parse_failure: the felix-capture parse-error callout the inject helper
# writes when frontmatter is malformed. Strongest single signal — present
# only when capture has already failed to parse the note.
PARSE_FAILURE_PATTERN = re.compile(
    r"^>\s*\[!error\]\s+felix-capture:", re.IGNORECASE | re.MULTILINE
)

# journal: first-person reflective phrases. Chosen because Kent's inbox
# journal blocks consistently start with one of these constructions
# ("Today I ...", "I feel ...", "noticed that ...", "reflecting on ...").
# All matches are case-insensitive; we look for them anywhere in the block.
JOURNAL_KEYWORDS = (
    "today i",
    "i feel",
    "i felt",
    "i noticed",
    "noticed that",
    "reflecting on",
    "i realized",
    "i am grateful",
    "i'm grateful",
    "grateful for",
    "i think i",
)

# calendar: date/time references combined with an event verb. Two regex
# families capture the two dominant Kent patterns:
#   1. "<weekday> at <time>"  — most common natural phrasing
#   2. "<MM/DD>" or "<MM-DD>" — explicit numeric date
# Either pattern PLUS a calendar verb keyword (meet/lunch/call/etc.) bumps
# confidence to high.
CALENDAR_WEEKDAY_TIME_PATTERN = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r".{0,40}\b(?:at\s+)?\d{1,2}\s*(?:am|pm|:\d{2})",
    re.IGNORECASE,
)
CALENDAR_EXPLICIT_DATE_PATTERN = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b"
)
CALENDAR_EVENT_VERBS = (
    "meet ",
    "meeting",
    "lunch",
    "dinner",
    "breakfast",
    "call with",
    "coffee with",
    "appointment",
    "review with",
    "sync with",
    "1:1",
    "check-in",
    "checkin",
)

# someday: aspirational / non-actionable language. Distinct from
# vikunja_task ("TODO: rotate PAT") in that it has no concrete next action.
# The presence of any of these phrases pushes the block into someday.
SOMEDAY_KEYWORDS = (
    "someday",
    "would like to",
    "maybe ",
    "curious about",
    "should explore",
    "would love to",
    "wish i could",
    "want to learn",
    "eventually",
)

# github_issue: explicit markers at the START of a block. Anchored to start
# (after optional whitespace) so a paragraph mentioning "bug:" mid-sentence
# is NOT misclassified.
GITHUB_ISSUE_PATTERN = re.compile(
    r"^\s*(?:gh\s+issue:|bug:|feature\s+request:|github\s+issue:)",
    re.IGNORECASE,
)

# vikunja_task: TODO/task markers. Like github_issue, anchored to start
# so prose mentions don't trigger. Markdown unchecked checkboxes (`[ ]`)
# are explicitly recognized — common Obsidian capture pattern.
VIKUNJA_TASK_PATTERN = re.compile(
    r"^\s*(?:todo:|task:|action:|-\s*\[\s*\]|\*\s*\[\s*\])",
    re.IGNORECASE,
)
# Imperative leading verb without a time anchor — a soft secondary signal.
# Kept separate from the strong-marker pattern so we can keep confidence
# down when only this matches.
VIKUNJA_IMPERATIVE_LEAD = re.compile(
    r"^\s*(rotate|fix|update|review|send|file|check|write|prepare|deploy)\b",
    re.IGNORECASE,
)

# Block-boundary heuristics per R-003, applied in priority order:
#   1. Markdown heading (`^#+\s`) — strongest signal
#   2. Two-or-more consecutive blank lines
#   3. A topic-leading keyword (`TODO:`, `Calendar:`, `Note to self:`) on
#      its own at the start of a non-blank line
HEADING_LINE_PATTERN = re.compile(r"^#+\s")
TOPIC_LEAD_PATTERN = re.compile(
    r"^\s*(?:todo:|calendar:|someday:|note to self:|gh issue:|bug:|task:|action:)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Note reading
# ---------------------------------------------------------------------------


def read_note(path: Path) -> tuple[dict, str]:
    """Read a note and return (frontmatter_dict, body_text).

    Hand-rolled YAML parser per D-002 (stdlib only). Frontmatter is split
    at the first ``---`` fence pair; the body is everything after the
    closing fence verbatim. A note without ``---`` fences is treated as
    pure body (empty frontmatter).
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=False)
    if not lines or lines[0].lstrip("﻿").strip() != "---":
        return {}, text
    # Find closing fence
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        return {}, text
    fm: dict[str, str] = {}
    for line in lines[1:close_idx]:
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    body = "\n".join(lines[close_idx + 1 :])
    # Strip leading blank lines that immediately follow the fence so
    # downstream block-splitting sees the real body start.
    body = body.lstrip("\n")
    return fm, body


# ---------------------------------------------------------------------------
# Block splitting
# ---------------------------------------------------------------------------


def split_blocks(body: str) -> list[str]:
    """Split body into blocks via the documented heuristic (R-003).

    Boundary signals, in priority order:
      1. A markdown heading line starts a new block.
      2. Two-or-more consecutive blank lines separate blocks.
      3. A topic-leading keyword line (e.g., "TODO:", "Calendar:") starts
         a new block even without intervening whitespace.

    Returns the list of block texts with leading/trailing whitespace
    stripped. Empty input → empty list.
    """
    if not body.strip():
        return []

    lines = body.splitlines()
    blocks: list[list[str]] = [[]]
    blank_run = 0

    for line in lines:
        stripped = line.strip()
        is_blank = stripped == ""

        # Heading or topic-lead start a new block when the current block
        # already has content.
        starts_new = False
        if not is_blank:
            if HEADING_LINE_PATTERN.match(line) and blocks[-1]:
                starts_new = True
            elif TOPIC_LEAD_PATTERN.match(line) and blocks[-1]:
                starts_new = True
            elif blank_run >= 2 and blocks[-1]:
                # Two-or-more blank lines → flush current block.
                starts_new = True

        if starts_new:
            blocks.append([])

        if not is_blank:
            blocks[-1].append(line)
            blank_run = 0
        else:
            blank_run += 1

    # Render each block to a stripped string and drop empties.
    rendered = ["\n".join(b).strip() for b in blocks if b]
    return [b for b in rendered if b]


# ---------------------------------------------------------------------------
# Per-block classification
# ---------------------------------------------------------------------------


def _contains_any(text_lower: str, needles: tuple[str, ...]) -> bool:
    return any(n in text_lower for n in needles)


def classify_block(content: str) -> tuple[str, str, str | None]:
    """Classify a single block.

    Returns ``(kind, confidence, flag)``. ``flag`` is non-None only for
    the ``ambiguous`` kind (always ``"needs-llm-disambiguation"`` in this
    mission's emission).

    Classification logic — in priority order:
      1. parse_failure callout marker (strongest single signal).
      2. Explicit start-anchored markers: github_issue, vikunja_task.
      3. Keyword/pattern scoring across journal/calendar/someday. If
         exactly one of those scores positive → that kind at high confidence.
         If two-or-more score positive → ambiguous (mixed signals).
      4. Soft imperative-lead (vikunja_task at medium confidence) when no
         other signal fires.
      5. Otherwise → ambiguous with low confidence + flag.

    Heuristics are intentionally simple; the prompt-side LLM handles the
    long tail of ambiguous blocks.
    """
    text_lower = content.lower()

    # 1. parse_failure — strongest single signal.
    if PARSE_FAILURE_PATTERN.search(content):
        return "parse_failure", "high", None

    # 2. Explicit start-anchored markers.
    if GITHUB_ISSUE_PATTERN.match(content):
        return "github_issue", "high", None
    if VIKUNJA_TASK_PATTERN.match(content):
        return "vikunja_task", "high", None

    # 3. Score journal / calendar / someday independently.
    has_journal = _contains_any(text_lower, JOURNAL_KEYWORDS)
    has_someday = _contains_any(text_lower, SOMEDAY_KEYWORDS)
    has_calendar_verb = _contains_any(text_lower, CALENDAR_EVENT_VERBS)
    has_weekday_time = bool(CALENDAR_WEEKDAY_TIME_PATTERN.search(content))
    has_explicit_date = bool(CALENDAR_EXPLICIT_DATE_PATTERN.search(content))
    has_calendar = has_calendar_verb and (has_weekday_time or has_explicit_date)

    positive = [k for k, v in (
        ("journal", has_journal),
        ("calendar", has_calendar),
        ("someday", has_someday),
    ) if v]

    if len(positive) == 1:
        return positive[0], "high", None
    if len(positive) >= 2:
        # Mixed signals — defer to the LLM disambiguation pass.
        return "ambiguous", "low", "needs-llm-disambiguation"

    # 4. Soft imperative lead — e.g. "Rotate the PAT" without a time anchor.
    if VIKUNJA_IMPERATIVE_LEAD.match(content) and not has_weekday_time and not has_explicit_date:
        return "vikunja_task", "medium", None

    # 5. Fallback: ambiguous with the disambiguation flag.
    return "ambiguous", "low", "needs-llm-disambiguation"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def classify_note(note_filename: str, body: str) -> dict:
    """Build the full ClassificationOutput dict for a note."""
    block_texts = split_blocks(body)
    blocks_out: list[dict] = []
    for index, text in enumerate(block_texts):
        kind, confidence, flag = classify_block(text)
        entry: dict = {
            "index": index,
            "kind": kind,
            "content": text,
            "confidence": confidence,
        }
        if flag is not None:
            entry["flag"] = flag
        blocks_out.append(entry)
    return {"note_filename": note_filename, "blocks": blocks_out}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit_error(kind: str, detail: str) -> None:
    sys.stderr.write(json.dumps({"error": kind, "detail": detail}) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.inbox.classify_content",
        description=(
            "Classify the body of an inbox note into structured blocks "
            "(journal/calendar/someday/github_issue/vikunja_task/parse_failure/ambiguous). "
            "Emits ClassificationOutput JSON on stdout."
        ),
    )
    parser.add_argument(
        "--content-file",
        required=True,
        help="Absolute path to the inbox note (frontmatter + body).",
    )
    args = parser.parse_args(argv)

    path = Path(args.content_file)

    # C-001 refusal: never read notes under 04-Growth/_private/.
    if PRIVATE_PATH_FRAGMENT in str(path):
        _emit_error("private_path_refused", str(path))
        return 3

    if not path.exists():
        _emit_error("file_not_found", str(path))
        return 1
    if not path.is_file():
        _emit_error("invalid_input", f"not a regular file: {path}")
        return 1

    try:  # pragma: no branch
        # Defensive OSError handler: after `.exists()` and `.is_file()` succeed,
        # `Path.read_text` can still fail (e.g., permission revoked mid-tick).
        # Not reachable from unit tests; the branch exists so production
        # invocations report a structured error rather than crashing.
        _frontmatter, body = read_note(path)
    except OSError as exc:  # pragma: no cover
        _emit_error("read_failed", str(exc))
        return 1

    output = classify_note(path.name, body)
    sys.stdout.write(json.dumps(output) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
