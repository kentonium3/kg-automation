#!/usr/bin/env python3
"""Reads from the sync cache at /data/services/openclaw/state/sync/task-cache.json
(see scripts/common/sync_cache.py for the canonical entry point).

Reconciles the local JSONL state log against the sync cache's task state:

    Backfill direction: for every active habit task whose cache ``done``
        is True, derive the completion date from the state log via
        ``read_completion_timestamps``. If no JSONL entry exists for
        ``(task_id, date, state="complete")``, append a backfill
        record with ``source="vikunja-ui"`` (Kent ticked the task done in
        the Vikunja UI -- record_completion was never invoked).

    Drift direction: for every active habit task, if the JSONL has a
        ``state="complete"`` entry for ``today`` but the cache currently
        shows ``done=false``, report the drift on stdout. Drift is NOT
        auto-resolved -- it indicates a conflict between sources of truth.

Exit codes (per contracts/cli.md):
    0 -- reconcile completed (with OR without drift; drift is informational)
    1 -- unrecoverable cache/JSONL failure (could not enumerate tasks)
    2 -- usage error (bad --today value, etc.)
    3 -- cache validation error (stale or missing cache)

Vikunja behaviors honored (now via cache):
    - Enumeration is **project-scoped** to the Habits project: the helper
      filters tasks whose ``project_id`` matches ``HABITS_PROJECT_ID``
      from the cache.

Design references:
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/spec.md
        FR-008, FR-009, NFR-003, C-005, C-006.
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/{api,cli}.md
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/research.md
        D7 (drift handling), D6 (idempotency), D10 (gotchas).
    - scripts/common/state_log.py (Phase 2 library used for append/read).
    - scripts/common/sync_cache.py (Phase 5 cache helper used for reads).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.common import state_log
from scripts.common.sync_cache import (
    SLA_NORMAL,
    SLATier,
    CompletionTimestamps,
    read_cached_tasks,
    read_completion_timestamps,
)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

TOUCHPOINT_SLA: SLATier = SLA_NORMAL
TOUCHPOINT_NAME = "habits.reconcile_completions"

#: Root directory for per-domain JSONL state logs on office2.
STATE_LOG_DIR = Path("/data/services/openclaw/state")

#: Vikunja project id for the Habits project. The sync cache stores
#: ``project_id`` in task fields; we scope enumeration to this id.
#: If the project id ever changes, update this constant.
HABITS_PROJECT_ID = 2

#: Regex for the --today flag (ISO-8601 date).
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current UTC timestamp in ISO-8601 with offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_utc() -> str:
    """Today's date in UTC as ``YYYY-MM-DD``."""
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconcile(
    today: str | None = None,
    state_log_dir: Path | None = None,
) -> dict:
    """Enumerate active habits from cache, backfill missing JSONL entries, report drift.

    Args:
        today: ISO-8601 date for the drift-detection comparison. Defaults
            to the current UTC date.
        state_log_dir: Directory containing per-domain JSONL state logs.
            Defaults to STATE_LOG_DIR.

    Returns:
        Summary dict::

            {
                "tasks_examined": int,
                "backfilled": [
                    {"task_id": ..., "date": ..., "title": ..., ...},
                    ...
                ],
                "drift": [
                    {"task_id": ..., "title": ..., "date": ...},
                    ...
                ],
                "errors": [
                    {"task_id": ..., "message": ...},
                    ...
                ],
            }

    Raises:
        OSError: On unrecoverable cache failure (the helper could not
            enumerate tasks at all).
    """
    today_date = today or _today_utc()
    if not _DATE_RE.match(today_date):
        raise ValueError(
            f"today {today_date!r} must match YYYY-MM-DD"
        )

    slog_dir = state_log_dir or STATE_LOG_DIR

    cached_tasks = read_cached_tasks(
        sla=TOUCHPOINT_SLA,
        touchpoint_name=TOUCHPOINT_NAME,
    )

    result: dict[str, Any] = {
        "tasks_examined": 0,
        "backfilled": [],
        "drift": [],
        "errors": [],
    }

    for task_id, view in cached_tasks.items():
        if view.is_private:
            continue
        if view.fields.get("project_id") != HABITS_PROJECT_ID:
            continue

        result["tasks_examined"] += 1
        title = view.fields.get("title") or ""

        # Backfill direction: cache says done=true but we may lack JSONL.
        if view.fields.get("done") is True:
            ts: CompletionTimestamps = read_completion_timestamps(
                domain="habits",
                task_id=task_id,
                state_log_dir=slog_dir,
            )
            done_date = ts.most_recent_complete_date_et
            if done_date is None:
                # Cache says done but no completion event in state log —
                # operator-side completion happened in the Vikunja UI.
                # We have no date to anchor the backfill record. Surface as
                # an error so the operator can triage.
                result["errors"].append({
                    "task_id": task_id,
                    "title": title,
                    "message": (
                        "task done=true in cache but no completion event "
                        "in state log; cannot derive completion date"
                    ),
                })
            else:
                try:
                    existing = state_log.read(
                        "habits",
                        task_id=task_id,
                        date=done_date,
                        state="complete",
                    )
                except OSError as e:
                    result["errors"].append({
                        "task_id": task_id,
                        "title": title,
                        "message": f"state_log read failed: {e}",
                    })
                    existing = ["sentinel"]  # avoid double-counting
                if not existing:
                    backfill_record = {
                        "domain": "habits",
                        "task_id": task_id,
                        "title": title,
                        "date": done_date,
                        "state": "complete",
                        "source": "vikunja-ui",
                        "timestamp": _now_iso(),
                    }
                    try:
                        state_log.append("habits", backfill_record)
                        result["backfilled"].append({
                            "task_id": task_id,
                            "title": title,
                            "date": done_date,
                            "source": "vikunja-ui",
                        })
                    except (OSError, ValueError) as e:
                        result["errors"].append({
                            "task_id": task_id,
                            "title": title,
                            "message": f"backfill append failed: {e}",
                        })

        # Drift direction: JSONL says complete for today but cache says
        # done=false. Reported but never auto-resolved.
        try:
            today_records = state_log.read(
                "habits",
                task_id=task_id,
                date=today_date,
                state="complete",
            )
        except OSError as e:
            result["errors"].append({
                "task_id": task_id,
                "title": title,
                "message": f"state_log read failed: {e}",
            })
            today_records = []

        if today_records and view.fields.get("done") is False:
            result["drift"].append({
                "task_id": task_id,
                "title": title,
                "date": today_date,
                "jsonl_state": "complete",
                "vikunja_done": False,
            })

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_token(token_file: Path) -> str:
    try:
        content = token_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError as e:
        raise OSError(f"Token file not found: {token_file}") from e
    except PermissionError as e:
        raise OSError(
            f"Token file not readable (permission denied): {token_file}"
        ) from e
    except OSError as e:
        raise OSError(f"Could not read token file {token_file}: {e}") from e
    if not content:
        raise OSError(f"Token file is empty: {token_file}")
    return content


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = argparse.ArgumentParser(
        prog="reconcile_completions",
        description=(
            "ADR-0002 Phase 3 reconciliation helper. Enumerates active "
            "habit tasks from the sync cache, backfills JSONL entries for "
            "Vikunja-UI completions, and reports drift (JSONL says complete, "
            "cache shows done=false). Exits 0 regardless of drift "
            "count (drift is informational). Exits 1 on unrecoverable "
            "cache or JSONL failure. Exits 3 on cache validation error."
        ),
    )
    parser.add_argument(
        "--today",
        default=None,
        help=(
            "Override the drift-comparison date (ISO-8601 YYYY-MM-DD). "
            "Defaults to today's UTC date."
        ),
    )
    parser.add_argument(
        "--state-log-dir",
        type=Path,
        default=STATE_LOG_DIR,
        help=(
            "Directory containing per-domain JSONL state logs "
            f"(default: {STATE_LOG_DIR})."
        ),
    )
    return parser


def _format_summary(result: dict, today: str) -> str:
    """Render the human-readable summary block for stdout."""
    lines: list[str] = []
    lines.append(f"=== reconcile_completions {_now_iso()} ===")
    lines.append(f"tasks_examined: {result['tasks_examined']}")
    lines.append(f"backfilled: {len(result['backfilled'])}")
    for entry in result["backfilled"]:
        lines.append(
            f"  - task_id={entry['task_id']} date={entry['date']} "
            f"source={entry['source']}"
        )
    lines.append(f"drift: {len(result['drift'])}")
    for entry in result["drift"]:
        title = entry.get("title") or ""
        lines.append(
            f"  - DRIFT: task_id={entry['task_id']} ({title}): "
            f"JSONL says complete for {entry['date']} but Vikunja shows "
            "done=false"
        )
    lines.append(f"errors: {len(result['errors'])}")
    for entry in result["errors"]:
        lines.append(
            f"  - task_id={entry.get('task_id')}: {entry.get('message')}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See contracts/cli.md for exit codes 0/1/2/3."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.today is not None and not _DATE_RE.match(args.today):
        print(
            f"ERROR: --today must match YYYY-MM-DD (got {args.today!r})",
            file=sys.stderr,
        )
        return 2

    try:
        result = reconcile(
            today=args.today,
            state_log_dir=args.state_log_dir,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ERROR: reconcile failed: {e}", file=sys.stderr)
        return 1

    today_used = args.today or _today_utc()
    print(_format_summary(result, today_used))
    # Drift is informational only -- always exit 0 when reconcile completed
    # (even if drift count > 0).
    return 0


if __name__ == "__main__":
    sys.exit(main())
