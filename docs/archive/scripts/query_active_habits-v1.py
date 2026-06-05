#!/usr/bin/env python3
# ARCHIVED 2026-06-05 — superseded by scripts/habits/query_active_habits_v2.py
# (mission #520 / issue #526). Zero callers confirmed before archival. Do not invoke.
"""Query Vikunja Habits project and return tasks scheduled for the input day.

Mission #282 / FR-002. Part of the felix-admin-habits Steps 1-4 refactor
(per Constitution Directive 6 and `docs/design/helper-script-conventions.md`).

This helper exists because the agent's prompt previously encoded a markdown
frequency-table parser inline — a high-criticality block (wrong filter →
wrong habits in Kent's WhatsApp) that's hallucination-prone in-prompt.

The helper:
  1. Reads the Vikunja API token from a mode-600 file
  2. Resolves the "Habits" project by title (no hardcoded project ID)
  3. Fetches all tasks in the project
  4. Excludes tasks marked done OR (PAUSED) in description
  5. Parses each task's frequency descriptor and filters to scheduled-today
  6. Returns the matching habit list as JSON

Frequency lexicon (canonical, from felix-admin-habits AGENTS.md):
  - Empty description           → all 7 days (the current production convention;
                                  production habits have empty `description` fields
                                  and were always treated as daily by the prior agent)
  - Daily (or "Daily (evening)")  → all 7 days
  - Mon-Sat  (or "Mon–Sat" with en-dash) → Mon, Tue, Wed, Thu, Fri, Sat
  - Mon/Wed/Fri                          → Mon, Wed, Fri
  - Anything else (non-empty + non-matching) → stderr WARN + skipped (out of vocabulary)

Note: the empty-description-→-daily rule was added after WP02 implementation
when local validation against production Vikunja showed every habit has an
empty `description` field. This was the implicit convention the prior Sonnet
agent followed at runtime. Future habits MAY use the explicit lexicon above
to encode non-daily schedules; the helper supports both shapes.

Invocation:

    python3 scripts/habits/query_active_habits.py --day Wed
        [--vikunja-token-path /data/services/openclaw/secrets/vikunja-api]
        [--vikunja-base-url https://office2.tail0f5f56.ts.net/api/v1]

Output (stdout):

    {"habits": [...], "total_in_project": 12, "scheduled_today": 4}
    SUMMARY: total=12 scheduled=4 paused=3 done=5 unrecognized_freq=0

Exit codes:
    0 — success (any number of habits returned, including zero)
    1 — operational error (Vikunja unreachable, project not found)
    2 — usage error (invalid --day value)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
DEFAULT_BASE_URL = "https://office2.tail0f5f56.ts.net/api/v1"

VALID_DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
ALL_DAYS = frozenset(VALID_DAYS)

# Frequency lexicon — matched against description (case-insensitive, stripped of (PAUSED))
# Order matters: check more-specific patterns first (e.g., "Daily (evening)" before "Daily").
FREQUENCY_LEXICON = [
    ("daily (evening)", ALL_DAYS),
    ("daily", ALL_DAYS),
    # Both en-dash (–, U+2013) and ascii dash (-)
    ("mon–sat", frozenset({"Mon", "Tue", "Wed", "Thu", "Fri", "Sat"})),
    ("mon-sat", frozenset({"Mon", "Tue", "Wed", "Thu", "Fri", "Sat"})),
    ("mon/wed/fri", frozenset({"Mon", "Wed", "Fri"})),
]

PAUSED_PATTERN = re.compile(r"\(PAUSED\)", re.IGNORECASE)


def _load_token(path: Path) -> str:
    """Read Vikunja API token from a mode-600 file. Returns the token string."""
    return path.read_text(encoding="utf-8").strip()


def _http_get(base_url: str, token: str, path: str, timeout: int = 15) -> object:
    """GET request to Vikunja with bearer-style auth. Returns parsed JSON."""
    req = urllib.request.Request(
        f"{base_url}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_frequency(description: str) -> tuple[frozenset[str] | None, bool]:
    """Parse a task description.

    Returns (scheduled_days, is_paused). `scheduled_days` is None for
    non-empty but unrecognized frequencies (caller emits WARN + skips).

    Production convention: empty descriptions mean daily. The prior Sonnet
    agent followed this implicitly; we encode it explicitly here.
    """
    is_paused = bool(PAUSED_PATTERN.search(description or ""))
    cleaned = PAUSED_PATTERN.sub("", description or "").strip().lower()
    # Empty (or whitespace-only after removing PAUSED) → daily by convention.
    if not cleaned:
        return ALL_DAYS, is_paused
    for pattern, days in FREQUENCY_LEXICON:
        if pattern in cleaned:
            return days, is_paused
    return None, is_paused


def find_habits_project_id(base_url: str, token: str) -> int:
    """Resolve the Habits project by title. Raises if not found."""
    projects = _http_get(base_url, token, "/projects")
    if not isinstance(projects, list):
        raise RuntimeError(f"Unexpected /projects response shape: {type(projects).__name__}")
    for project in projects:
        if isinstance(project, dict) and project.get("title") == "Habits":
            project_id = project.get("id")
            if isinstance(project_id, int):
                return project_id
            raise RuntimeError(f"Habits project found but has no integer id: {project!r}")
    raise RuntimeError("No project titled 'Habits' found in Vikunja")


def fetch_habits_tasks(base_url: str, token: str, project_id: int) -> list[dict]:
    """Fetch all tasks in the Habits project. Returns a list of task dicts."""
    # /projects/{id}/tasks may paginate; per_page=200 is a safe upper bound for habits.
    tasks = _http_get(base_url, token, f"/projects/{project_id}/tasks?per_page=200")
    if not isinstance(tasks, list):
        raise RuntimeError(f"Unexpected tasks response shape: {type(tasks).__name__}")
    return tasks


def filter_habits_for_day(
    tasks: list[dict],
    day: str,
) -> tuple[list[dict], dict[str, int]]:
    """Filter tasks down to those scheduled today; return (scheduled_list, counts).

    counts has keys: paused, done, unrecognized_freq.
    """
    scheduled: list[dict] = []
    counts = {"paused": 0, "done": 0, "unrecognized_freq": 0}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if task.get("done") is True:
            counts["done"] += 1
            continue
        description = task.get("description") or ""
        days, is_paused = parse_frequency(description)
        if is_paused:
            counts["paused"] += 1
            continue
        if days is None:
            counts["unrecognized_freq"] += 1
            print(
                f"WARN: task {task.get('id')} {task.get('title')!r} has "
                f"unrecognized frequency in description; skipped",
                file=sys.stderr,
            )
            continue
        if day in days:
            scheduled.append({
                "id": task.get("id"),
                "title": task.get("title"),
                "description": description,
                "due_date": task.get("due_date"),
            })
    scheduled.sort(key=lambda h: h.get("id") or 0)
    return scheduled, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", maxsplit=1)[0],
    )
    parser.add_argument(
        "--day",
        type=str,
        required=True,
        help="Three-letter day-of-week (Mon, Tue, Wed, Thu, Fri, Sat, Sun)",
    )
    parser.add_argument(
        "--vikunja-token-path",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help="Path to the Vikunja API token (mode-600 file)",
    )
    parser.add_argument(
        "--vikunja-base-url",
        type=str,
        default=DEFAULT_BASE_URL,
        help="Vikunja API base URL",
    )
    args = parser.parse_args(argv)

    if args.day not in VALID_DAYS:
        print(
            f"ERROR: --day must be one of {sorted(VALID_DAYS)}; got {args.day!r}",
            file=sys.stderr,
        )
        return 2

    try:
        token = _load_token(args.vikunja_token_path)
    except FileNotFoundError:
        print(
            f"ERROR: Vikunja token file not found: {args.vikunja_token_path}",
            file=sys.stderr,
        )
        return 1
    except PermissionError:
        print(
            f"ERROR: permission denied reading Vikunja token: {args.vikunja_token_path}",
            file=sys.stderr,
        )
        return 1

    try:
        project_id = find_habits_project_id(args.vikunja_base_url, token)
        tasks = fetch_habits_tasks(args.vikunja_base_url, token, project_id)
    except urllib.error.URLError as exc:
        print(f"ERROR: Vikunja API unreachable: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    scheduled, counts = filter_habits_for_day(tasks, args.day)

    result = {
        "habits": scheduled,
        "total_in_project": len(tasks),
        "scheduled_today": len(scheduled),
    }
    print(json.dumps(result))
    print(
        f"SUMMARY: total={len(tasks)} scheduled={len(scheduled)} "
        f"paused={counts['paused']} done={counts['done']} "
        f"unrecognized_freq={counts['unrecognized_freq']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
