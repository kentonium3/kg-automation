"""Architectural ratchet — habits completion history MUST come from JSONL.

This test fails the build if any non-allowlisted script under
``scripts/habits/`` imports ``VikunjaClient`` from
``scripts.common.vikunja_client``. The goal is to prevent the
GitHub issue #605 bug class — reading Vikunja ``done_at`` as if it were
a completion-history record — from silently recurring six months from
now when someone writes the next analysis helper.

The mission `trustworthy-weekly-habit-report-01KV4GZ7` routes the weekly
report's completion-history reads through the canonical
``habits-history.jsonl`` via :mod:`scripts.habits.history`. This test is
the ratchet that keeps the architecture honest.

The allowlist (:data:`VIKUNJA_CURRENT_STATE_ALLOWLIST`) names habits
scripts whose Vikunja usage is **current-state only** — listing the
habits, classifying them, marking today's instance done in Vikunja — i.e.
NOT reading completion history. Each entry must carry a one-line reason
comment; adding a new entry is a code-review decision.

How to add a script to the allowlist:

1. Confirm the script reads CURRENT-STATE only (titles, due dates,
   classification, today's done flag) and does NOT infer historical
   completion from Vikunja.
2. Add the basename + reason comment to
   :data:`VIKUNJA_CURRENT_STATE_ALLOWLIST` (alphabetical order).
3. Add a docstring to the script explaining why it imports
   ``VikunjaClient`` despite the architectural rule.

References:
- GitHub issue #605 (the bug this test prevents from recurring)
- Mission ``trustworthy-weekly-habit-report-01KV4GZ7`` (which introduced
  the canonical-store read path)
- Felix Constitution Directive 6 (deterministic surfaces vs LLM judgment)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


#: Repo root, two levels up from this test file (tests/architectural/<this>).
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Directory whose ``*.py`` files are scanned by the main ratchet.
HABITS_DIR = REPO_ROOT / "scripts" / "habits"


#: Habits scripts allowed to import ``VikunjaClient`` because their use is
#: current-state only (NOT completion history). Each entry MUST carry a
#: one-line reason comment. Adding a new entry is a code-review decision.
VIKUNJA_CURRENT_STATE_ALLOWLIST: frozenset[str] = frozenset({
    "query_active_habits_v2.py",         # current-state: "what habits are due today" list
    "exclude_completed_v2.py",           # current-state: today's already-completed check
    "morning_checkin_list.py",           # invokes query_active_habits_v2; same domain
    "record_completion.py",              # writes completion to Vikunja current state
    "sweeper.py",                        # current-state sweeper for missed day-specific habits
    "set_due_dates.py",                  # current-state mutation
    "identify_workout_task.py",          # current-state query for the day's workout task
    "backfill_jsonl_from_comments.py",   # one-time backfill READS Vikunja COMMENTS (not done_at)
    "query_active_habits_weekly.py",     # current-state ONLY: titles + repeat_after classification
})


def _find_vikunja_client_imports(source: str) -> list[tuple[int, str]]:
    """Return ``[(lineno, source_line), ...]`` for any VikunjaClient import.

    AST-walks ``source`` and reports every import statement that names
    ``VikunjaClient`` directly or pulls in ``scripts.common.vikunja_client``
    as a module (whose attribute access can yield ``VikunjaClient``).

    Handles all canonical forms enumerated in the test contract:

    - ``from scripts.common.vikunja_client import VikunjaClient``
    - ``from scripts.common.vikunja_client import VikunjaError, VikunjaClient``
    - ``from scripts.common.vikunja_client import VikunjaClient as VC``
    - ``import scripts.common.vikunja_client``
    - ``import scripts.common.vikunja_client as vc``
    """
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "scripts.common.vikunja_client":
                for alias in node.names:
                    if alias.name == "VikunjaClient":
                        hits.append((node.lineno, lines[node.lineno - 1]))
                        # One hit per import line is enough; multiple aliases
                        # on the same line should not over-report.
                        break
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "scripts.common.vikunja_client":
                    hits.append((node.lineno, lines[node.lineno - 1]))
                    break
    return hits


# ---------------------------------------------------------------------------
# Negative-control: prove the scanner detects each canonical import form.
# ---------------------------------------------------------------------------


_OFFENDING_FORMS: list[tuple[str, str]] = [
    (
        "from-import-direct",
        "from scripts.common.vikunja_client import VikunjaClient\n",
    ),
    (
        "from-import-multi-name",
        "from scripts.common.vikunja_client import VikunjaError, VikunjaClient\n",
    ),
    (
        "from-import-aliased",
        "from scripts.common.vikunja_client import VikunjaClient as VC\n",
    ),
    (
        "import-module",
        "import scripts.common.vikunja_client\n",
    ),
    (
        "import-module-aliased",
        "import scripts.common.vikunja_client as vc\n",
    ),
]


@pytest.mark.parametrize("form_id,source", _OFFENDING_FORMS, ids=lambda v: v if isinstance(v, str) else None)
def test_scanner_fires_on_unallowed_import(form_id: str, source: str) -> None:
    """Each canonical offending import form is detected by the AST scanner."""
    hits = _find_vikunja_client_imports(source)
    assert hits, f"scanner missed offending form {form_id!r}: {source!r}"
    # Single hit on a single-line source; lineno 1 is the import line.
    assert hits[0][0] == 1
    assert hits[0][1].rstrip("\n") == source.rstrip("\n")


def test_scanner_returns_empty_for_clean_source() -> None:
    """Sanity-check: a habits script without VikunjaClient imports → no hits."""
    clean = (
        "from datetime import datetime\n"
        "from scripts.common import state_log\n"
        "\n"
        "def hello() -> str:\n"
        "    return 'hi'\n"
    )
    assert _find_vikunja_client_imports(clean) == []


def test_scanner_ignores_lookalike_strings() -> None:
    """A string mentioning VikunjaClient (e.g. in a docstring) is NOT an import."""
    docstring_only = (
        '"""This module talks about VikunjaClient but does not import it."""\n'
        "from scripts.common import state_log\n"
    )
    assert _find_vikunja_client_imports(docstring_only) == []


# ---------------------------------------------------------------------------
# Allowlist sanity — every allowlisted basename must point at a real file.
# ---------------------------------------------------------------------------


def test_allowlist_contains_no_stale_entries() -> None:
    """Each allowlist entry must correspond to a real file under scripts/habits/.

    Catches the case where a habits script is deleted but the allowlist
    isn't updated — fails on the next CI run instead of leaving silent
    dead entries that hide a future bug-class recurrence.
    """
    missing = sorted(
        name
        for name in VIKUNJA_CURRENT_STATE_ALLOWLIST
        if not (HABITS_DIR / name).is_file()
    )
    assert not missing, (
        f"Allowlist entries point at non-existent files: {missing}. "
        "Remove stale entries from VIKUNJA_CURRENT_STATE_ALLOWLIST or restore "
        "the missing scripts."
    )


# ---------------------------------------------------------------------------
# The main ratchet — FR-004.
# ---------------------------------------------------------------------------


def test_no_completion_history_reads_through_vikunja() -> None:
    """No non-allowlisted ``scripts/habits/*.py`` imports VikunjaClient.

    This is the FR-004 ratchet. The architectural rule: completion-history
    reads belong on :mod:`scripts.habits.history` via the canonical
    ``habits-history.jsonl``; Vikunja current-state access is permitted
    only via an explicit allowlisted file with a reason comment.
    """
    violations: list[str] = []
    for path in sorted(HABITS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        if path.name in VIKUNJA_CURRENT_STATE_ALLOWLIST:
            continue
        source = path.read_text(encoding="utf-8")
        for lineno, line in _find_vikunja_client_imports(source):
            violations.append(
                f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()} — "
                "VikunjaClient import not allowlisted; completion history must "
                "read habits-history.jsonl via scripts/habits/history.py"
            )
    assert not violations, "\n".join(violations)
