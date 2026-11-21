#!/usr/bin/env python3
"""Pause, resume or remove a habit, keeping its history and rule — helper.

Mission felix-rrule-adaptation-01M7TKNX (#1111), WP12 (FR-026; Kent's pause
semantics A, 2026-11-20). felix-admin-habits runs this after it has resolved
the habit by name and Kent has confirmed.

- ``pause`` adds the :data:`PAUSED_PREFIX` to the task description. The
  morning check-in list (``query_active_habits_v2``) and the 48-hour sweeper
  skip a paused habit; both test :func:`is_paused`, the one definition.
- ``resume`` strips the prefix.
- ``remove`` ends the series with ``VikunjaClient.end_series``: the rule is
  cleared, then the task is marked done, each verified by readback. The task
  is **never deleted**, so its history stays.

``pause`` and ``resume`` write through :func:`scripts.vikunja.update_task.update_task`
(in-process, not a subprocess), so the same readback guards apply: the rule,
``repeats_from_current_date`` and the reminders must survive, and the new
description must read back as sent. Both are idempotent: pausing a paused
habit (or resuming an active one) writes nothing and exits 0.

It imports ``VikunjaClient`` for current-state writes only and never reads
completion history from Vikunja (allowlisted in
``tests/architectural/test_habits_history_canonical_read.py``).

Every action first checks that the task is in the Habits project
(``vikunja_scope.habit_project_id``), so a mis-resolved id cannot end an
ordinary task's series.

Invocation (on office2)::

    python3 -m scripts.habits.manage_habit pause --task-id 14

Output: ``INFO:`` lines, errors on stderr prefixed ``ERROR:``, and the last
stdout line is a JSON summary::

    {"ok": true, "action": "pause", "outcome": "paused", "task_id": 14,
     "error": null, "message": null, "state": null}

``outcome``: ``paused`` / ``already_paused``, ``resumed`` / ``not_paused``,
``removed`` (also when it had already ended), ``partial`` (``remove`` stopped
part-way: ``state`` is the ``SeriesEndIncomplete`` state; running ``remove``
again resumes from a fresh read), ``unexpected`` (the readback guard failed),
``refused`` or ``error``.

Exit codes: 0 ok; 1 ``partial`` / ``unexpected`` / ``error``; 2 usage error or
refusal (nothing written).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any, NoReturn

from scripts.vikunja.update_task import (
    EXIT_OK,
    EXIT_UNEXPECTED,
    EXIT_USAGE,
    StoreOnce,
    UpdateRefused,
    print_summary,
    update_task,
)

__all__ = [
    "ACTIONS",
    "PAUSED_PREFIX",
    "add_paused_prefix",
    "is_paused",
    "main",
    "manage_habit",
    "strip_paused_prefix",
]

ACTIONS = ("pause", "resume", "remove")

#: The pause marker, at the very start of the description (semantics A).
PAUSED_PREFIX = "(PAUSED) "

#: The marker as read: at the start, optionally after leading whitespace or
#: the ``<p>`` the Vikunja editor wraps text in, with any spaces after it.
_PAUSED_RE = re.compile(r"^(\s*(?:<p>\s*)?)\(PAUSED\) *")


def is_paused(task: Mapping[str, Any]) -> bool:
    """True when *task*'s description starts with the ``(PAUSED)`` marker.

    The single paused predicate (FR-026). *task* is a v2 task body or a sync
    cache ``fields`` dict; both carry ``description``. Only the description
    prefix counts: a title that contains "PAUSED" does not pause a habit, and
    a missing or non-string description is not paused.
    """
    description = task.get("description")
    return isinstance(description, str) and _PAUSED_RE.match(description) is not None


def add_paused_prefix(description: str | None) -> str:
    """Return *description* with :data:`PAUSED_PREFIX` in front."""
    return PAUSED_PREFIX + (description or "")


def strip_paused_prefix(description: str) -> str:
    """Return *description* without its leading marker (kept ``<p>`` intact)."""
    return _PAUSED_RE.sub(lambda m: m.group(1), description, count=1)


def _summary(action: str, task_id: Any, outcome: str, **extra: Any) -> dict[str, Any]:
    out = {
        "ok": outcome in ("paused", "already_paused", "resumed", "not_paused", "removed"),
        "action": action,
        "outcome": outcome,
        "task_id": task_id,
        "error": None,
        "message": None,
        "state": None,
    }
    out.update(extra)
    return out


def _check_habit(task: Mapping[str, Any], task_id: int) -> None:
    from scripts.common import vikunja_scope

    habits_project = vikunja_scope.habit_project_id()
    if habits_project is None:
        raise UpdateRefused(
            "habits_project_unknown",
            "the Habits project id cannot be resolved (label selector); refusing",
        )
    if task.get("project_id") != habits_project:
        raise UpdateRefused(
            "not_a_habit",
            f"task {task_id} is in project {task.get('project_id')!r}, not the "
            f"Habits project ({habits_project}); refusing",
        )


def manage_habit(client: Any, action: str, task_id: int) -> dict[str, Any]:
    """Run *action* on habit *task_id* and return the JSON summary dict.

    Raises:
        UpdateRefused: unknown action, bad id, or the task is not a habit;
            nothing written.
    """
    from scripts.common.vikunja_client import SeriesEndIncomplete, VikunjaError

    if action not in ACTIONS:
        raise UpdateRefused("invalid_input", f"action must be one of {ACTIONS}, got {action!r}")
    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise UpdateRefused("invalid_input", f"task id must be a positive integer, got {task_id!r}")

    try:
        before = client.get_task_v2(task_id)
    except VikunjaError as exc:
        return _summary(
            action,
            task_id,
            "error",
            error="vikunja_error",
            message=f"could not read task {task_id}: {exc}",
        )
    _check_habit(before, task_id)

    if action == "remove":
        try:
            client.end_series(task_id)
        except SeriesEndIncomplete as exc:
            return _summary(
                action,
                task_id,
                "partial",
                error="series_end_incomplete",
                state=exc.state,
                message=(
                    f"task {task_id}: series end stopped at {exc.state!r}; run remove "
                    "again to resume from a fresh read"
                ),
            )
        except VikunjaError as exc:
            return _summary(
                action,
                task_id,
                "error",
                error="vikunja_error",
                message=f"task {task_id}: series not ended ({exc}); nothing changed",
            )
        return _summary(action, task_id, "removed")

    paused = is_paused(before)
    if action == "pause" and paused:
        return _summary(action, task_id, "already_paused")
    if action == "resume" and not paused:
        return _summary(action, task_id, "not_paused")
    description = before.get("description") or ""
    new_description = (
        add_paused_prefix(description) if action == "pause" else strip_paused_prefix(description)
    )
    result = update_task(client, task_id, {"description": new_description}, before=before)
    if not result.ok:
        return _summary(
            action,
            task_id,
            result.outcome,
            error=result.error,
            message=result.message,
            drift=result.drift,
            mismatch=result.mismatch,
            write_attempted=result.write_attempted,
        )
    after = result.after or {}
    if is_paused(after) != (action == "pause"):
        return _summary(
            action,
            task_id,
            "unexpected",
            error="pause_state_mismatch",
            message=f"task {task_id}: readback paused={is_paused(after)} after {action}",
        )
    return _summary(action, task_id, "paused" if action == "pause" else "resumed")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class UsageError(Exception):
    """An argument the parser rejected; reported through the exit-2 summary."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="scripts.habits.manage_habit",
        description="Pause, resume or remove a habit, keeping its history and rule (#1111).",
        allow_abbrev=False,
    )
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument(
        "--task-id", action=StoreOnce, type=int, required=True, help="Vikunja API task id"
    )
    return parser


def _build_client() -> Any:
    from scripts.common.vikunja_client import VikunjaClient

    return VikunjaClient()


def _first(argv: Sequence[str]) -> str | None:
    return argv[0] if argv and argv[0] in ACTIONS else None


def main(argv: Sequence[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint; see the module docstring for output and exit codes."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _build_parser().parse_args(raw_argv)
        if args.task_id <= 0:
            raise UpdateRefused(
                "invalid_input", f"task id must be a positive integer, got {args.task_id}"
            )
    except (UsageError, UpdateRefused) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        code = exc.code if isinstance(exc, UpdateRefused) else "invalid_input"
        print_summary(
            _summary(_first(raw_argv) or "", None, "refused", error=code, message=str(exc))
        )
        return EXIT_USAGE

    try:
        active = client if client is not None else _build_client()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print_summary(
            _summary(args.action, args.task_id, "error", error="config_error", message=str(exc))
        )
        return EXIT_UNEXPECTED

    try:
        summary = manage_habit(active, args.action, args.task_id)
    except UpdateRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print_summary(
            _summary(args.action, args.task_id, "refused", error=exc.code, message=str(exc))
        )
        return EXIT_USAGE

    if summary["ok"]:
        print(f"INFO: habit {args.task_id} {summary['outcome']}")
    else:
        print(f"ERROR: {summary['message']}", file=sys.stderr)
    print_summary(summary)
    return EXIT_OK if summary["ok"] else EXIT_UNEXPECTED


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
