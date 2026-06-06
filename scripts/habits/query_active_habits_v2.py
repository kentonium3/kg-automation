#!/usr/bin/env python3
"""Reads active habit tasks from the sync cache at
/data/services/openclaw/state/sync/task-cache.json
(see scripts/common/sync_cache.py for the canonical entry point).

Replaces the comment-parsing / day-of-week descriptor approach of the v1
sibling (``scripts/habits/query_active_habits.py``) with a project-scoped
task enumeration + a Python-side filter equivalent to
``due_date <= <today>T23:59:59Z AND done == false``. The v1 sibling
continues to drive the felix-admin-habits cron until Phase 5 cutover
(#308); both files coexist until then.

The helper:
  1. Reads all tasks from the Felix sync cache (``scripts/common/sync_cache``).
  2. Applies a Python-side filter equivalent to
     ``done == False AND due_date <= <today>T23:59:59Z`` scoped to the
     Habits project. The cache is populated and kept fresh by the
     felix-vikunja-sync driver (mission #518).
  3. Returns the list of matching task dicts on stdout as JSONL.

Cache reads surface ``OSError`` with a structured message when the cache
is missing or stale beyond SLA_NORMAL. The CLI maps this to exit code 3.

Per Q1's locked decision this is a clean cutover — no Vikunja HTTP
fallback path. When the cache cannot serve a read the touchpoint surfaces
a structured stderr error and exits non-zero.

Scoping the enumeration to the Habits project is essential: a
cross-project enumeration via the cache would let non-habit tasks
(Inbox, Goals, recurring meetings) leak into the Phase 5 check-in flow.

See contracts/api.md + contracts/cli.md for the contract.

Invocation::

    python3 -m scripts.habits.query_active_habits_v2 \\
        [--today YYYY-MM-DD] \\
        [--schedule-path /path/to/schedule.yaml]

Output (stdout): one JSON object per active habit task, newline-delimited.

Exit codes (per contracts/cli.md):
    0 -- success (empty result OK)
    2 -- usage error (bad --today value)
    3 -- cache error (missing, stale, or corrupt cache)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.common.sync_cache import (
    SLA_NORMAL,
    SLATier,
    read_cached_tasks,
)

try:
    from scripts.habits.schedule_loader import (
        ScheduleConfigError,
        ScheduleEntry,
        is_active_today,
        load_schedule,
    )
except ImportError:
    # Fallback for direct-script invocation (`python3 scripts/habits/query_active_habits_v2.py`).
    # The absolute-package import above resolves only under `python3 -m scripts.habits.query_active_habits_v2`;
    # both invocation forms exist in production callers.
    # Precedent: scripts/openclaw/observation/summarize.py:36-38.
    from schedule_loader import (  # type: ignore[no-redef]
        ScheduleConfigError,
        ScheduleEntry,
        is_active_today,
        load_schedule,
    )


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Touchpoint SLA tier (all habits touchpoints land on SLA_NORMAL per research.md §Unknown 1).
TOUCHPOINT_SLA: SLATier = SLA_NORMAL

#: Touchpoint name used in structured error messages.
TOUCHPOINT_NAME = "habits.query_active_habits_v2"

#: Vikunja project_id for the Habits project on office2. The sync driver
#: records ``project_id`` in the cache for every task; this constant lets
#: the touchpoint scope the enumeration to habits without a live API call.
#: Value is the well-known project_id from the production Vikunja instance.
#: See research.md § TP-03 for the field-availability confirmation. If
#: the project_id ever changes, update this constant (dynamic resolution
#: via HABITS_PROJECT_TITLE was scoped but not implemented).
HABITS_PROJECT_ID: int = 13

#: Title of the Vikunja project holding all habit tasks.  Used as fallback
#: project-scoping mechanism when HABITS_PROJECT_ID is None.
HABITS_PROJECT_TITLE = "Habits"

#: Regex for the --today flag (ISO-8601 date).
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Map Python ``datetime.weekday()`` ints (Mon=0..Sun=6) to 3-letter names.
_WEEKDAY_BY_INDEX: tuple[str, ...] = (
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today_utc() -> str:
    """Today's date in UTC as ``YYYY-MM-DD``."""
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _weekday_name_for_date(date_str: str) -> str:
    """Return the 3-letter ISO weekday name for a ``YYYY-MM-DD`` string.

    Used by the day-of-week filter in :func:`query_active_today` so callers
    only need to pass ``today`` once. Mirrors the ``day`` field emitted by
    ``scripts.habits.compute_today``.

    Raises:
        ValueError: ``date_str`` is not parseable as ISO-8601.
    """
    parsed = datetime.fromisoformat(date_str).date()
    return _WEEKDAY_BY_INDEX[parsed.weekday()]


def query_active_today(
    today: str | None = None,
    *,
    schedule_path: Path | str | None = None,
    today_weekday: str | None = None,
) -> list[dict]:
    """Return habit tasks active for today from the Felix sync cache.

    Reads all tasks from the sync cache at
    /data/services/openclaw/state/sync/task-cache.json and filters
    client-side for ``done == False`` AND
    ``due_date <= <today>T23:59:59Z``, scoped to the Habits project
    (``project_id`` field in the cached task fields).

    **Day-of-week filter (mission #408)**: when ``schedule_path`` is
    supplied, the function loads the habit schedule via
    :func:`scripts.habits.schedule_loader.load_schedule` and excludes any
    candidate whose ``ScheduleEntry`` has ``designated_weekdays`` set AND
    today's weekday is NOT in that list. Habits in Vikunja that are not in
    the schedule are passed through unchanged (daily-default fallback) with
    a single stderr warning per missing task — this preserves existing
    behavior for tests that do not configure a schedule.

    See ``contracts/api.md`` for the full contract.

    Args:
        today: ISO-8601 date for the filter boundary. Defaults to UTC today.
        schedule_path: Optional path to the habits schedule YAML. When None
            (the default), no day-of-week filter is applied — preserves
            pre-#408 behavior for tests that do not exercise the filter.
        today_weekday: Optional 3-letter ISO weekday name (e.g. ``"Wed"``).
            Used in conjunction with ``schedule_path`` for the day-of-week
            filter. If None, derived from ``today``.

    Returns:
        List of task dicts. Each dict contains at least ``id``, ``title``,
        ``due_date``, ``done``, ``repeat_after``, ``project_id``, ``labels``.
        Empty list if no habits are active.

    Raises:
        ValueError: If ``today`` is set but not YYYY-MM-DD, or ``today_weekday``
            is provided but invalid.
        OSError: On cache read failure (cache missing, stale, or corrupt).
            Message format: ``[habits.query_active_habits_v2] <detail>``.
        ScheduleConfigError: If ``schedule_path`` is supplied but the schedule
            YAML fails validation.
    """
    today_date = today or _today_utc()
    if not _DATE_RE.match(today_date):
        raise ValueError(f"today {today_date!r} must match YYYY-MM-DD")

    # Read all tasks from the sync cache (raises OSError on missing/stale).
    cached_tasks = read_cached_tasks(
        sla=TOUCHPOINT_SLA,
        touchpoint_name=TOUCHPOINT_NAME,
    )

    # Client-side filter — equivalent to the rejected server-side filter
    # ``due_date <= <today>T23:59:59Z AND done = false``:
    #   - exclude tasks with ``done == True``
    #   - include tasks where ``due_date`` (string lex compare) is
    #     non-empty AND ``<= boundary``. Vikunja's unset-due-date
    #     sentinel ``"0001-01-01T00:00:00Z"`` lex-compares less than the
    #     boundary, so unset-due-date tasks are INCLUDED (same behavior
    #     the server-side filter would have produced). An empty-string
    #     ``due_date`` (truly absent field) is excluded.
    boundary = f"{today_date}T23:59:59Z"
    candidates: list[dict] = []
    for task_id, view in cached_tasks.items():
        if view.is_private:
            continue  # private-project task — skip (see EC-7 in migration-pattern.md)
        fields = view.fields
        if fields.get("project_id") != HABITS_PROJECT_ID:
            continue  # not in the Habits project — skip (#556)
        if fields.get("done", False):
            continue
        due = fields.get("due_date") or ""
        if not due or due > boundary:
            continue
        # Reconstruct the dict shape callers expect (same fields as the old
        # Vikunja GET /projects/<id>/tasks response body).
        candidates.append({
            "id": task_id,
            "title": fields.get("title"),
            "due_date": fields.get("due_date"),
            "done": fields.get("done", False),
            "repeat_after": fields.get("repeat_after"),
            "repeat_mode": fields.get("repeat_mode"),
            "project_id": fields.get("project_id"),
            "labels": fields.get("labels") or [],
        })

    # Day-of-week filter (mission #408 / FR-002) — opt-in via schedule_path.
    if schedule_path is None:
        return candidates

    entries = load_schedule(schedule_path)
    by_task_id: dict[int, ScheduleEntry] = {e.task_id: e for e in entries}
    resolved_weekday = today_weekday or _weekday_name_for_date(today_date)

    filtered: list[dict] = []
    for item in candidates:
        tid = item.get("id")
        if not isinstance(tid, int):
            # Unexpected — pass through; the morning-checkin helper will
            # surface a structured error if any item lacks an integer id.
            filtered.append(item)
            continue
        entry = by_task_id.get(tid)
        if entry is None:
            # Habit in Vikunja but not in schedule.yaml: include by default
            # (daily fallback). Log a single stderr warning so the operator
            # notices the drift on the next morning's journal scrape.
            print(
                f"WARN: habit task_id={tid} title={item.get('title')!r} not "
                f"in schedule.yaml — treating as daily (passthrough)",
                file=sys.stderr,
            )
            filtered.append(item)
            continue
        if is_active_today(entry, resolved_weekday):
            filtered.append(item)
        # else: day-specific habit not designated for today — exclude.
    return filtered


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = argparse.ArgumentParser(
        prog="query_active_habits_v2",
        description=(
            "Reads active habit tasks from the Felix sync cache at "
            "/data/services/openclaw/state/sync/task-cache.json. "
            "Applies a Python-side filter equivalent to "
            "`due_date <= <today>T23:59:59Z AND done == false`. "
            "Emits one JSON object per active task on stdout (newline-delimited). "
            "Exits 0 on success (empty result OK), 2 on usage error, "
            "3 on cache error (missing or stale cache)."
        ),
    )
    parser.add_argument(
        "--today",
        default=None,
        help=(
            "Override the filter date (ISO-8601 YYYY-MM-DD). Defaults to "
            "today's UTC date."
        ),
    )
    parser.add_argument(
        "--schedule-path",
        type=Path,
        default=None,
        help=(
            "Optional path to the habits schedule YAML. When supplied, the "
            "day-of-week filter from mission #408 is applied: day-specific "
            "habits whose designated weekdays do not include today's ET "
            "weekday are excluded. Default: filter disabled (preserves "
            "pre-#408 behavior)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See contracts/cli.md for exit codes 0/2/3."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.today is not None and not _DATE_RE.match(args.today):
        print(
            f"ERROR: --today must match YYYY-MM-DD (got {args.today!r})",
            file=sys.stderr,
        )
        return 2

    try:
        tasks = query_active_today(
            args.today,
            schedule_path=args.schedule_path,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except ScheduleConfigError as e:
        print(f"ERROR: schedule config: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"[{TOUCHPOINT_NAME}] {e}", file=sys.stderr)
        return 3

    out = sys.stdout
    for task in tasks:
        out.write(json.dumps(task, ensure_ascii=False, sort_keys=False))
        out.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
