"""NFR-001 ratchet: the retired Vikunja interval fields stay out of active Felix code.

Mission felix-rrule-adaptation-01M7TKNX (#1111), WP08 T039. Vikunja now models
recurrence as an RFC 5545 rule (``repeat`` / ``repeats_rrule``); the v1
interval pair ``repeat_after`` / ``repeat_mode`` and the schedule YAML's
``repeat_after_seconds`` are dead. This test walks ``scripts/**/*.py`` and the
agent guidance ``scripts/openclaw/**/*.md`` and fails, naming ``file:line``, on
any mention outside the scoped exclusions below.

Two kinds of exception, each with a reason:

- :data:`EXCLUDED` — whole trees out of scope (release tooling that reads the
  database columns, history). Never scanned.
- :data:`ALLOWED_HITS` — a file allowed an **exact** number of matching
  lines. More fail (a new use), fewer fail too (the entry is stale and must
  shrink), so the list can only ratchet down.

``phase3-schedule.yaml`` is checked structurally: its frozen ``operations:``
block is history (C-005), but no entry of the live ``habits:`` block may carry
a retired key.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = REPO_ROOT / "scripts"
SCHEDULE_YAML = SCRIPTS / "habits" / "migrations" / "phase3-schedule.yaml"

RETIRED = re.compile(r"\brepeat_after\b|\brepeat_mode\b|repeat_after_seconds")
RETIRED_KEYS = frozenset({"repeat_after", "repeat_mode", "repeat_after_seconds"})

#: Repo-relative paths (a directory excludes everything under it) never scanned.
EXCLUDED: dict[str, str] = {
    "scripts/deploy/vikunja_release": (
        "release tooling: reads and migrates the database columns by name"
    ),
    "scripts/vikunja/rollback_release.py": (
        "release tooling: restores the pre-RRULE columns on rollback"
    ),
}

#: Repo-relative file -> (exact matching-line count, reason). Shrink as files
#: are cleaned.
ALLOWED_HITS: dict[str, tuple[int, str]] = {
    "scripts/habits/schedule_loader.py": (
        3,
        (
            "the loader refuses a habit that still carries repeat_after_seconds "
            "(a retirement guard, not a use)"
        ),
    ),
    "scripts/sync/cleanup.py": (1, "retirement note in a WP07-owned docstring"),
    "scripts/sync/classify.py": (1, "retirement note: the pair no longer drives classification"),
    "scripts/sync/diff.py": (1, "retirement note: the pair is no longer diffed"),
    "scripts/habits/query_active_habits_v2.py": (2, "retirement note: no longer emitted"),
    "scripts/habits/query_active_habits_weekly.py": (1, "retirement note: never read"),
    "scripts/intake/apply_reply.py": (1, "retirement note in a docstring"),
}


def _is_excluded(rel: str) -> bool:
    return any(rel == ex or rel.startswith(ex + "/") for ex in EXCLUDED)


def _scanned_files(root: Path) -> Iterable[Path]:
    yield from sorted(root.glob("scripts/**/*.py"))
    yield from sorted(root.glob("scripts/openclaw/**/*.md"))


def find_hits(root: Path) -> dict[str, list[str]]:
    """Map each scanned file to its ``file:line`` hits (one per matching line)."""
    hits: dict[str, list[str]] = {}
    for path in _scanned_files(root):
        rel = path.relative_to(root).as_posix()
        if _is_excluded(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if RETIRED.search(line):
                hits.setdefault(rel, []).append(f"{rel}:{lineno}: {line.strip()}")
    return hits


def ratchet_violations(
    hits: dict[str, list[str]], allowed: dict[str, tuple[int, str]]
) -> list[str]:
    """Human-readable violations: unexpected hits, and stale allowlist counts."""
    problems: list[str] = []
    for rel, lines in sorted(hits.items()):
        expected = allowed.get(rel, (0, ""))[0]
        if len(lines) > expected:
            problems.append(
                f"{rel}: {len(lines)} retired-field mention(s), {expected} allowed:\n  "
                + "\n  ".join(lines)
            )
    for rel, (expected, _reason) in sorted(allowed.items()):
        found = len(hits.get(rel, []))
        if found < expected:
            problems.append(
                f"{rel}: ALLOWED_HITS says {expected} but {found} remain; "
                "lower (or delete) the entry"
            )
    return problems


def habit_retired_keys(schedule: dict) -> list[str]:
    """``habits[i] (title): key`` for each live habit carrying a retired key."""
    found: list[str] = []
    for index, habit in enumerate(schedule.get("habits") or []):
        if not isinstance(habit, dict):
            continue
        for key in sorted(RETIRED_KEYS & habit.keys()):
            found.append(f"habits[{index}] ({habit.get('title')!r}): {key}")
    return found


# ---------------------------------------------------------------------------
# The ratchet itself
# ---------------------------------------------------------------------------


def test_no_retired_repeat_fields_in_active_code_and_agent_docs() -> None:
    problems = ratchet_violations(find_hits(REPO_ROOT), ALLOWED_HITS)
    assert not problems, "NFR-001 (#1111):\n" + "\n".join(problems)


def test_live_habits_schedule_has_no_retired_keys() -> None:
    schedule = yaml.safe_load(SCHEDULE_YAML.read_text(encoding="utf-8"))
    assert schedule.get("habits"), "phase3-schedule.yaml has no habits: block"
    assert habit_retired_keys(schedule) == []


def test_every_exclusion_and_allowance_names_a_real_path_with_a_reason() -> None:
    for rel, reason in EXCLUDED.items():
        assert (REPO_ROOT / rel).exists(), f"stale exclusion {rel}"
        assert reason.strip()
    for rel, (count, reason) in ALLOWED_HITS.items():
        assert (REPO_ROOT / rel).is_file(), f"stale allowance {rel}"
        assert count > 0 and reason.strip()
        assert not _is_excluded(rel)


# ---------------------------------------------------------------------------
# Controls: the checks can fail
# ---------------------------------------------------------------------------


def _plant(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("rel", "text", "where"),
    [
        ("scripts/x/use.py", "a = 1\nbody['repeat_after'] = 86400\n", "scripts/x/use.py:2"),
        ("scripts/x/mode.py", "repeat_mode = 0\n", "scripts/x/mode.py:1"),
        ("scripts/x/yaml_key.py", "k = 'repeat_after_seconds'\n", "scripts/x/yaml_key.py:1"),
        (
            "scripts/openclaw/agents/a/AGENTS.md",
            "# Guide\nSet `repeat_after` to 604800.\n",
            "scripts/openclaw/agents/a/AGENTS.md:2",
        ),
    ],
)
def test_control_planted_hit_is_reported_with_file_and_line(
    tmp_path: Path, rel: str, text: str, where: str
) -> None:
    _plant(tmp_path, rel, text)
    problems = ratchet_violations(find_hits(tmp_path), {})
    assert len(problems) == 1
    assert where in problems[0]


def test_control_word_boundaries_and_exclusions(tmp_path: Path) -> None:
    _plant(tmp_path, "scripts/x/ok.py", "repeat_after_x = 1\nrepeats_from_current_date = True\n")
    _plant(tmp_path, "scripts/deploy/vikunja_release/db.py", "repeat_after = 1\n")
    _plant(tmp_path, "scripts/vikunja/rollback_release.py", "repeat_mode = 1\n")
    _plant(tmp_path, "docs/archive/old.py", "repeat_after = 1\n")
    _plant(tmp_path, "scripts/x/notes.txt", "repeat_after\n")
    assert find_hits(tmp_path) == {}


def test_control_allowance_is_exact_both_ways(tmp_path: Path) -> None:
    _plant(tmp_path, "scripts/x/guard.py", "if 'repeat_after_seconds' in raw:\n    pass\n")
    hits = find_hits(tmp_path)
    assert ratchet_violations(hits, {"scripts/x/guard.py": (1, "guard")}) == []
    # A new mention in an allowed file fails...
    _plant(tmp_path, "scripts/x/guard.py", "repeat_after_seconds\nrepeat_mode\n")
    assert ratchet_violations(find_hits(tmp_path), {"scripts/x/guard.py": (1, "g")})
    # ...and so does an allowance larger than what remains (stale entry).
    _plant(tmp_path, "scripts/x/guard.py", "clean = True\n")
    stale = ratchet_violations(find_hits(tmp_path), {"scripts/x/guard.py": (1, "g")})
    assert stale and "lower (or delete) the entry" in stale[0]


def test_control_live_habit_with_retired_key_is_reported() -> None:
    schedule = {
        "operations": [{"op": "patch", "target": {"repeat_after": 86400}}],
        "habits": [
            {"task_id": 14, "title": "Wake", "rrule": "FREQ=DAILY;INTERVAL=1"},
            {"task_id": 15, "title": "Read", "repeat_after_seconds": 86400},
        ],
    }
    assert habit_retired_keys(schedule) == ["habits[1] ('Read'): repeat_after_seconds"]
