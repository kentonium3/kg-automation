#!/usr/bin/env python3
"""Phase 5 cutover variant of exclude_completed using JSONL state_log.

Replaces the ``[Felix] YYYY-MM-DD | state | note`` comment-parsing approach
of the v1 sibling (``scripts/habits/exclude_completed.py``) with a single
``state_log.read("habits", task_id=..., date=today, state="complete")``
query per task. The v1 sibling continues to drive the felix-admin-habits
cron until Phase 5 cutover (#308); both files coexist until then.

The helper:
  1. Reads a list of active habit tasks from stdin (newline-delimited
     JSON, one task per line — typically piped from
     ``query_active_habits_v2.py``)
  2. For each task, queries the habits JSONL state log for a
     ``state="complete"`` record for today's date
  3. **Mission #408 / WP-02 extension**: additionally scans
     ``habits-history.jsonl`` directly for ``event_type="auto_skipped"``
     records targeting the task at today's date and excludes those too
     (per ``contracts/history-event-auto-skipped.contract.md`` reader-
     behavior: ``auto_skipped`` is exclusion-eligible).
  4. Emits the subset of tasks WITHOUT such a record to stdout

The auto_skipped scan uses a permit-list approach (only known schema
extensions trigger exclusion), keeping the function forward-compatible:
genuinely unknown event_types are treated as no-op rather than
accidentally hiding tasks from Kent.

See contracts/api.md + contracts/cli.md for the contract.

Invocation::

    python3 -m scripts.habits.query_active_habits_v2 \\
        | python3 -m scripts.habits.exclude_completed_v2 \\
        [--today YYYY-MM-DD]

Exit codes (per contracts/cli.md):
    0 -- success (empty result OK)
    1 -- state_log read failure (rare; the log file is local)
    2 -- usage / malformed stdin
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.common import state_log


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Regex for the --today flag (ISO-8601 date).
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today_utc() -> str:
    """Today's date in UTC as ``YYYY-MM-DD``."""
    return datetime.now(timezone.utc).date().isoformat()


def _has_auto_skipped_event(history_path: Path, task_id: int, today: str) -> bool:
    """Return True iff an ``auto_skipped`` event exists for the pair today.

    Mission #408 / WP-02. The sweeper writes ``auto_skipped`` events with
    shape ``{"event_type": "auto_skipped", "task_id": ..., "original_checkin_date_et": ...}``
    directly to ``habits-history.jsonl`` (bypassing the state_log API
    because the canonical state enum only permits ``complete`` /
    ``incomplete`` / ``skipped``). This helper does the targeted scan so
    the exclude filter recognizes auto-skipped instances as
    exclusion-eligible per the reader-behavior contract.

    Tolerates missing file and malformed lines silently — never raises.
    A genuinely unreadable file is the caller's problem to surface;
    this helper biases toward "include the task" (no exclusion) so
    Kent never misses a habit because of a parse glitch.
    """
    if not history_path.exists():
        return False
    try:
        with history_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("event_type") != "auto_skipped":
                    continue
                if obj.get("task_id") != task_id:
                    continue
                if obj.get("original_checkin_date_et") != today:
                    continue
                return True
    except OSError:
        return False
    return False


def _default_history_path() -> Path:
    """Return the canonical ``habits-history.jsonl`` path.

    Mirrors ``state_log._state_file("habits")`` resolution so the same
    ``FELIX_STATE_LOG_DIR`` env override applies — tests using
    ``mock_state_log_dir`` continue to work because the env var routes
    both this scan and the state_log calls to the same sandbox directory.
    """
    return state_log.STATE_DIR / "habits-history.jsonl"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def exclude_completed_for_today(
    active_tasks: list[dict],
    today: str | None = None,
    history_path: Path | None = None,
) -> list[dict]:
    """Filter the input list to tasks already addressed in today's window.

    See ``contracts/api.md`` for the original (mission #371) contract.
    **Mission #408 / WP-02 extension**: also excludes tasks with an
    ``auto_skipped`` event in ``habits-history.jsonl`` whose
    ``original_checkin_date_et`` equals ``today`` (per
    ``contracts/history-event-auto-skipped.contract.md`` — auto-skipped
    is exclusion-eligible analogously to ``state=complete``).

    Args:
        active_tasks: Iterable of task dicts. Only the ``id`` field is
            consulted; other fields are passed through unchanged.
        today: ISO-8601 date for the JSONL filter. Defaults to UTC today.
        history_path: Override for the habits-history.jsonl path. Defaults
            to ``state_log.STATE_DIR / "habits-history.jsonl"`` so the
            mock_state_log_dir test fixture routes both scans to the same
            sandbox.

    Returns:
        Subset of ``active_tasks`` where neither
        ``state_log.read("habits", task_id=X, date=today, state="complete")``
        nor a matching ``auto_skipped`` event is present. Order is
        preserved from the input.

    Raises:
        ValueError: If ``today`` is set but not YYYY-MM-DD.
        OSError: If a state_log read fails (rare; the log file is local).
    """
    today_date = today or _today_utc()
    if not _DATE_RE.match(today_date):
        raise ValueError(f"today {today_date!r} must match YYYY-MM-DD")

    effective_history_path = history_path or _default_history_path()

    result: list[dict] = []
    for task in active_tasks:
        if not isinstance(task, dict):
            # Defensive: skip non-dict entries silently. CLI parser already
            # rejects malformed JSON lines.
            continue
        task_id = task.get("id")
        if not isinstance(task_id, int):
            # No id => can't query state_log; conservatively include the
            # task (assume not-yet-completed). The agent / downstream can
            # decide what to do with malformed entries.
            result.append(task)
            continue
        existing = state_log.read(
            "habits",
            task_id=task_id,
            date=today_date,
            state="complete",
        )
        if existing:
            continue
        # Mission #408 / WP-02: also exclude auto_skipped instances.
        if _has_auto_skipped_event(
            effective_history_path, task_id, today_date
        ):
            continue
        result.append(task)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = argparse.ArgumentParser(
        prog="exclude_completed_v2",
        description=(
            "Phase 5 cutover variant of exclude_completed. Reads JSONL "
            "active-habit tasks on stdin (one JSON object per line), and "
            "emits the subset without a `state=complete` entry in the "
            "habits state log for today. Exits 0 on success (empty result "
            "OK), 1 on state_log read failure, 2 on malformed stdin."
        ),
    )
    parser.add_argument(
        "--today",
        default=None,
        help=(
            "Override today's date (ISO-8601 YYYY-MM-DD). Defaults to "
            "today's UTC date."
        ),
    )
    return parser


def _read_stdin_tasks() -> list[dict]:
    """Read newline-delimited JSON tasks from stdin.

    Skips empty/whitespace-only lines. Raises ValueError on the first
    malformed line so the CLI can map to exit 2.
    """
    tasks: list[dict] = []
    for line_num, raw_line in enumerate(sys.stdin, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"malformed JSON on stdin line {line_num}: {e}"
            ) from e
        if not isinstance(obj, dict):
            raise ValueError(
                f"stdin line {line_num} is not a JSON object "
                f"(got {type(obj).__name__})"
            )
        tasks.append(obj)
    return tasks


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See contracts/cli.md for exit codes 0/1/2."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.today is not None and not _DATE_RE.match(args.today):
        print(
            f"ERROR: --today must match YYYY-MM-DD (got {args.today!r})",
            file=sys.stderr,
        )
        return 2

    try:
        tasks = _read_stdin_tasks()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        filtered = exclude_completed_for_today(tasks, today=args.today)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ERROR: state_log read failed: {e}", file=sys.stderr)
        return 1

    out = sys.stdout
    for task in filtered:
        out.write(json.dumps(task, ensure_ascii=False, sort_keys=False))
        out.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
