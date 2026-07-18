#!/usr/bin/env python3
"""One-time migration: normalize date-only Vikunja due-dates to end-of-day ET (#736).

Vikunja stores every ``due_date`` as a UTC instant. A **date-only** pick (the
user chose a date, no time) is stored as midnight in some timezone —
``<date>T00:00:00Z`` (UTC midnight) or ``<date>T04:00:00Z`` / ``<date>T05:00:00Z``
(ET midnight, EDT/EST). The escalation read-side converts the stored instant to
an **America/New_York calendar date**, so a midnight-UTC value reads as the
*prior* ET day: a task "due June 15" stored ``2026-06-15T00:00:00Z`` reads as
June 14 and escalates a day early (#736).

Felix's own reschedule/intake writes already use end-of-day ET (which round-trips
correctly). This migrates the **legacy / UI-set** date-only values to the same
convention so every due-date reads back on its intended day.

Key insight: for a date-only value the intended calendar date IS the value's
**date component** (the UI stores ``<intended-date>T<midnight-in-its-tz>``), so we
rewrite it to end-of-day ET of that date via
:func:`scripts.common.et_datetime.et_end_of_day`. Genuine datetimes (a real time
of day) and values already at EOD-ET are left untouched — the migration is
**idempotent** (a re-run is a no-op).

Dry-run by default; ``--apply`` executes. Writes go through the **kent token**
(``vikunja-api-kent``) via an allowlisted read-modify-write with an instant-based
readback check (Vikunja normalizes due_date to UTC ``Z``, so a string compare
false-fails, #757). Mirrors ``scripts/vikunja/migrate_tasks.py``.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Optional

from scripts.common import et_datetime
from scripts.common.vikunja_client import VikunjaClient, VikunjaError
from scripts.common.vikunja_config import get_vikunja_base_url
from scripts.vikunja.migrate_tasks import (
    DEFAULT_KENT_TOKEN_FILE,
    _WRITABLE_FIELDS,
    _read_token_file,
    _writable_payload,
    list_all_tasks,
)

#: Vikunja's "no due date" sentinel prefix (year-1).
_UNSET_DUE_PREFIX = "0001-01-01"


class MigrationError(Exception):
    """Fail-loud migration error (readback mismatch, Vikunja error)."""


def _is_date_only(due_str: str) -> bool:
    """True iff the due-date is a date-only pick (midnight in UTC or Eastern).

    A calendar-date pick has no time-of-day and is stored as midnight in some
    timezone; a genuine timed event has a non-midnight time and is left alone.
    """
    instant = et_datetime.parse_vikunja_instant(due_str)  # aware UTC | None
    if instant is None:
        return False
    if instant.hour == 0 and instant.minute == 0 and instant.second == 0:
        return True  # midnight UTC (e.g. T00:00:00Z)
    et = et_datetime.to_et(instant)
    return et.hour == 0 and et.minute == 0 and et.second == 0  # midnight ET


def plan_migration(tasks: list[dict]) -> list[dict]:
    """Return planned changes for date-only due-dates.

    Each entry: ``{task_id, title, old_due, new_due}``. Skips tasks with no due,
    the unset sentinel, genuine datetimes, un-normalizable dates, and values
    already equal to the EOD-ET target (idempotent).
    """
    plan: list[dict] = []
    for task in tasks:
        due = task.get("due_date")
        if (
            not isinstance(due, str)
            or not due
            or due.startswith(_UNSET_DUE_PREFIX)
        ):
            continue
        if not _is_date_only(due):
            continue
        # Intended calendar date = the value's date component (the UI stores
        # <intended-date>T<midnight-in-its-tz>). Normalize to EOD-ET of that date.
        try:
            new_due = et_datetime.et_end_of_day(due[:10])
        except ValueError:
            continue  # non-standard / pre-modern date — never a real due date
        # Idempotent: same instant → nothing to do.
        if et_datetime.parse_vikunja_instant(due) == et_datetime.parse_vikunja_instant(new_due):
            continue
        plan.append(
            {
                "task_id": task["id"],
                "title": task.get("title", ""),
                "old_due": due,
                "new_due": new_due,
            }
        )
    return plan


def apply_change(client: Any, task: dict, new_due: str) -> None:
    """RMW the task's ``due_date`` to *new_due*; readback-verify the INSTANT.

    Echoes the writable-field allowlist so Vikunja's partial-replace can't zero
    an unstated field (#524), then compares the readback due_date by *instant*
    (Vikunja returns it as UTC ``Z``, so a string compare of our ET-offset write
    false-fails, #757). Other allowlisted fields must be byte-unchanged.
    """
    task_id = task["id"]
    payload = _writable_payload(task)
    payload["due_date"] = new_due
    client.post(f"/tasks/{task_id}", json=payload)

    readback = client.get(f"/tasks/{task_id}")
    if not isinstance(readback, dict):
        raise MigrationError(f"task {task_id}: readback returned a non-object")
    if et_datetime.parse_vikunja_instant(
        readback.get("due_date")
    ) != et_datetime.parse_vikunja_instant(new_due):
        raise MigrationError(
            f"task {task_id}: due_date readback instant is "
            f"{readback.get('due_date')!r}, expected {new_due!r}"
        )
    for name in _WRITABLE_FIELDS:
        if name == "due_date":
            continue
        if name in payload and readback.get(name) != payload[name]:
            raise MigrationError(
                f"task {task_id}: field {name!r} drifted from {payload[name]!r} "
                f"to {readback.get(name)!r} (partial-replace, #524)"
            )


def _print_plan(plan: list[dict]) -> None:
    for change in plan:
        title = str(change["title"])[:50]
        print(
            f"  task {change['task_id']}: {title!r}\n"
            f"      {change['old_due']}  ->  {change['new_due']}"
        )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="migrate_date_only_due_dates",
        description=(
            "Normalize legacy/UI date-only Vikunja due-dates to end-of-day ET "
            "(#736). Dry-run by default; --apply writes."
        ),
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Execute the writes (default is a read-only dry-run).",
    )
    p.add_argument(
        "--token-file",
        default=DEFAULT_KENT_TOKEN_FILE,
        help=f"Kent-token file (default {DEFAULT_KENT_TOKEN_FILE}).",
    )
    p.add_argument(
        "--base-url",
        default=None,
        help="Vikunja base URL (default: config-resolved).",
    )
    return p


def main(argv: Optional[list[str]] = None, *, client: Any | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if client is None:
        token = _read_token_file(args.token_file)
        base_url = args.base_url or get_vikunja_base_url()
        client = VikunjaClient(base_url=base_url, token=token)

    try:
        tasks = list_all_tasks(client)
    except VikunjaError as exc:
        print(f"error: could not list tasks: {exc}", file=sys.stderr)
        return 1

    plan = plan_migration(tasks)
    _print_plan(plan)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"{mode}: {len(plan)} date-only due-date(s) to normalize to end-of-day ET "
        f"(of {len(tasks)} tasks scanned)"
    )

    if not args.apply:
        print("(dry-run — no changes written; re-run with --apply)")
        return 0

    by_id = {t["id"]: t for t in tasks}
    applied = 0
    try:
        for change in plan:
            apply_change(client, by_id[change["task_id"]], change["new_due"])
            applied += 1
    except (MigrationError, VikunjaError) as exc:
        print(
            f"error after {applied} applied: {exc}", file=sys.stderr
        )
        return 1
    print(f"applied={applied}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
