#!/usr/bin/env python3
"""Change an existing Vikunja task's plain fields, keeping its rule — helper.

Mission felix-rrule-adaptation-01M7TKNX (#1111), WP12 (FR-025). The tasker's
``retroactive_enrichment`` and ``detect_incomplete`` flows change an existing
task's title, description, due date, priority or project only through this
helper (and ``scripts.habits.manage_habit`` pauses and resumes a habit through
:func:`update_task`). It never writes the recurrence rule.

Steps (data-model.md Invariants 1 and 2):

1. The requested changes are validated locally. An empty change set, a value
   of the wrong type, or an unparseable due date is refused before any HTTP
   call. There is no ``--rrule`` (or any rule) flag; an unknown flag is a
   usage error.
2. The task is read over v2 (``get_task_v2``). A **due-date change on a
   recurring task is refused** before any write: the due date is the series
   anchor, so moving it belongs in Vikunja for now.
3. Fields whose stored value already equals the request are dropped. If none
   is left, nothing is written (outcome ``unchanged``).
4. ``VikunjaClient.patch_task`` sends only the changed fields as a v2 merge
   patch. Nothing is ever sent as a JSON ``null``. A 304 answer means the
   server changed nothing.
5. The task is read back. ``vikunja_rule.recurrence_drift`` compares the rule,
   ``repeats_from_current_date`` and the reminder set with the pre-write read;
   any drift is outcome ``unexpected`` (exit 1). Every requested field must
   also read back as sent, or the outcome is ``unexpected`` too.

Invocation (on office2, where the Vikunja base URL and token live)::

    python3 -m scripts.vikunja.update_task --task-id 412 \\
        --project-id 20 --priority 3 --due 2026-11-25T23:59:59-05:00

Output: ``INFO:`` lines for humans, errors on stderr prefixed ``ERROR:``, and
the **last stdout line is a JSON summary**::

    {"ok": true, "outcome": "updated", "task_id": 412,
     "requested": ["due_date", "priority", "project_id"],
     "written": ["due_date", "project_id"], "drift": [], "mismatch": [],
     "error": null, "message": null}

``outcome`` is one of ``updated``, ``unchanged`` (nothing to write, or the
server answered 304), ``refused`` (exit 2, nothing written), ``unexpected``
(written, but the readback shows rule drift or a field that did not stick) or
``error`` (a Vikunja failure; ``write_attempted`` says whether a PATCH was
sent).

Exit codes: 0 ok (``updated`` / ``unchanged``); 1 ``unexpected`` / ``error``;
2 usage error or refusal (no write).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, NoReturn

from scripts.common.et_datetime import parse_vikunja_instant
from scripts.common.vikunja_rule import has_rule, recurrence_drift

__all__ = [
    "EXIT_OK",
    "EXIT_UNEXPECTED",
    "EXIT_USAGE",
    "StoreOnce",
    "UPDATABLE_FIELDS",
    "UpdateRefused",
    "UpdateResult",
    "main",
    "update_task",
    "validate_changes",
]

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2

#: The only task fields this helper writes. The rule (``repeat`` /
#: ``repeats_rrule`` / ``repeats_from_current_date``), ``done`` and
#: ``reminders`` are deliberately absent.
UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {"title", "description", "due_date", "priority", "project_id"}
)

_PRIORITY_MIN = 0
_PRIORITY_MAX = 5


class UpdateRefused(ValueError):
    """The change was refused before any write (exit 2).

    ``code`` is the summary's ``error`` value: ``invalid_input``,
    ``recurring_due_change``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class UpdateResult:
    """What :func:`update_task` did, for the JSON summary and for callers."""

    task_id: int
    outcome: str  # "updated" | "unchanged" | "unexpected" | "error"
    requested: list[str]
    written: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    mismatch: list[str] = field(default_factory=list)
    error: str | None = None
    message: str | None = None
    write_attempted: bool = False
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.outcome in ("updated", "unchanged")

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "outcome": self.outcome,
            "task_id": self.task_id,
            "requested": self.requested,
            "written": self.written,
            "write_attempted": self.write_attempted,
            "drift": self.drift,
            "mismatch": self.mismatch,
            "error": self.error,
            "message": self.message,
        }


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_changes(changes: Mapping[str, Any]) -> dict[str, Any]:
    """Return the validated change set, or raise :class:`UpdateRefused`.

    No HTTP. ``title`` is stripped and must be non-empty; ``description`` is
    any string (``""`` clears it without a null); ``due_date`` must parse as
    an aware instant; ``priority`` is an int 0-5; ``project_id`` a positive
    int. ``None`` is never accepted.
    """
    if not isinstance(changes, Mapping):
        raise UpdateRefused("invalid_input", "changes must be a mapping")
    if not changes:
        raise UpdateRefused("invalid_input", "no change requested")
    unknown = sorted(set(changes) - UPDATABLE_FIELDS)
    if unknown:
        raise UpdateRefused(
            "invalid_input",
            f"cannot change {unknown}; only {sorted(UPDATABLE_FIELDS)} "
            "(rule changes stay in Vikunja)",
        )
    out: dict[str, Any] = {}
    for key, value in changes.items():
        if value is None:
            raise UpdateRefused("invalid_input", f"{key} may not be null")
        if key == "title":
            if not isinstance(value, str) or not value.strip():
                raise UpdateRefused("invalid_input", "title must be a non-empty string")
            out[key] = value.strip()
        elif key == "description":
            if not isinstance(value, str):
                raise UpdateRefused("invalid_input", "description must be a string")
            out[key] = value
        elif key == "due_date":
            if not isinstance(value, str) or parse_vikunja_instant(value) is None:
                raise UpdateRefused(
                    "invalid_input",
                    f"due date must be an ISO-8601 instant with an offset, got {value!r}",
                )
            out[key] = value.strip()
        elif key == "priority":
            if not _is_int(value) or not _PRIORITY_MIN <= value <= _PRIORITY_MAX:
                raise UpdateRefused(
                    "invalid_input",
                    f"priority must be an integer {_PRIORITY_MIN}-{_PRIORITY_MAX}, got {value!r}",
                )
            out[key] = value
        elif key == "project_id":
            if not _is_int(value) or value <= 0:
                raise UpdateRefused(
                    "invalid_input", f"project id must be a positive integer, got {value!r}"
                )
            out[key] = value
    return out


def _is_recurring(task: Mapping[str, Any]) -> bool:
    """A rule in either shape counts, so a half-shaped read never looks one-off."""
    return has_rule(task) or bool(task.get("repeats_rrule"))


def _same_value(key: str, stored: Any, wanted: Any) -> bool:
    """True when the stored *key* already holds *wanted* (due dates by instant)."""
    if key == "due_date":
        stored_at = parse_vikunja_instant(stored)
        wanted_at = parse_vikunja_instant(wanted)
        return (
            stored_at is not None
            and wanted_at is not None
            and stored_at == wanted_at.replace(microsecond=0)
        )
    if key == "description":
        return (stored or "") == wanted
    return stored == wanted


def update_task(
    client: Any,
    task_id: int,
    changes: Mapping[str, Any],
    *,
    before: Mapping[str, Any] | None = None,
) -> UpdateResult:
    """Apply *changes* to task *task_id* with a v2 PATCH and verify the readback.

    *before* is an optional fresh ``get_task_v2`` read the caller already
    made (``manage_habit`` computes the new description from it); otherwise
    the task is read here. The readback is always compared against that
    same pre-write read.

    Raises:
        UpdateRefused: invalid input or a due-date change on a recurring task;
            nothing was written (exit 2). Validation runs before any read.

    Returns an :class:`UpdateResult`; a Vikunja failure is ``outcome="error"``
    rather than an exception, so the caller can report ``write_attempted``.
    """
    from scripts.common.vikunja_client import VikunjaError

    if not _is_int(task_id) or task_id <= 0:
        raise UpdateRefused("invalid_input", f"task id must be a positive integer, got {task_id!r}")
    wanted = validate_changes(changes)
    result = UpdateResult(task_id=task_id, outcome="error", requested=sorted(wanted))

    if before is None:
        try:
            before = client.get_task_v2(task_id)
        except VikunjaError as exc:
            result.error = "vikunja_error"
            result.message = f"could not read task {task_id}: {exc}"
            return result
    before = dict(before)
    result.before = before

    if "due_date" in wanted and _is_recurring(before):
        raise UpdateRefused(
            "recurring_due_change",
            f"task {task_id} repeats ({before.get('repeats_rrule')!r}); its due date "
            "anchors the series, so change it in Vikunja",
        )

    to_write = {k: v for k, v in wanted.items() if not _same_value(k, before.get(k), v)}
    if not to_write:
        result.outcome = "unchanged"
        result.message = "every requested field already has that value; nothing written"
        result.after = before
        return result

    result.written = sorted(to_write)
    result.write_attempted = True
    try:
        answer = client.patch_task(task_id, to_write)
    except VikunjaError as exc:
        result.error = "vikunja_error"
        result.message = (
            f"PATCH failed ({exc}); the write may or may not have landed, "
            f"so read task {task_id} before retrying"
        )
        return result
    not_modified = answer is None

    try:
        after = client.get_task_v2(task_id)
    except VikunjaError as exc:
        result.outcome = "unexpected"
        result.error = "readback_failed"
        result.message = f"written, but the readback failed ({exc}); check task {task_id}"
        return result
    result.after = after

    result.drift = recurrence_drift(before, after)
    result.mismatch = sorted(k for k, v in wanted.items() if not _same_value(k, after.get(k), v))
    if result.drift or result.mismatch:
        result.outcome = "unexpected"
        parts = []
        if result.drift:
            parts.append(f"{', '.join(result.drift)} changed across the write")
        if result.mismatch:
            parts.append(f"{', '.join(result.mismatch)} did not read back as sent")
        result.error = "rule_drift" if result.drift else "field_mismatch"
        result.message = f"task {task_id}: " + "; ".join(parts)
        return result

    result.outcome = "unchanged" if not_modified else "updated"
    if not_modified:
        result.message = "server answered 304: nothing changed"
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class UsageError(Exception):
    """An argument the parser rejected; reported through the exit-2 summary."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


class StoreOnce(argparse.Action):
    """Store a flag's value, refusing a second copy (no silent last-one-wins)."""

    def __call__(self, parser, namespace, values, option_string=None):  # type: ignore[no-untyped-def]
        if getattr(namespace, f"_seen_{self.dest}", False):
            parser.error(f"{option_string} given more than once")
        setattr(namespace, f"_seen_{self.dest}", True)
        setattr(namespace, self.dest, values)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="scripts.vikunja.update_task",
        description=(
            "Change an existing task's title, description, due date, priority or "
            "project, keeping its recurrence rule (#1111). Rule changes, and due "
            "changes on a recurring task, stay in Vikunja."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--task-id", action=StoreOnce, type=int, required=True, help="Vikunja API task id"
    )
    parser.add_argument("--title", action=StoreOnce, default=None, help="new title")
    parser.add_argument(
        "--description", action=StoreOnce, default=None, help='new description ("" clears it)'
    )
    parser.add_argument(
        "--due",
        action=StoreOnce,
        default=None,
        help="new due date, ISO-8601 with an offset (one-off tasks only)",
    )
    parser.add_argument(
        "--priority",
        action=StoreOnce,
        type=int,
        default=None,
        help=f"priority {_PRIORITY_MIN}-{_PRIORITY_MAX}",
    )
    parser.add_argument(
        "--project-id", action=StoreOnce, type=int, default=None, help="move to this project id"
    )
    return parser


def _changes_from_args(args: argparse.Namespace) -> dict[str, Any]:
    pairs = {
        "title": args.title,
        "description": args.description,
        "due_date": args.due,
        "priority": args.priority,
        "project_id": args.project_id,
    }
    return {k: v for k, v in pairs.items() if v is not None}


def _task_id_from_argv(argv: Sequence[str]) -> int | None:
    items = list(argv)
    for index, item in enumerate(items):
        raw = None
        if item == "--task-id" and index + 1 < len(items):
            raw = items[index + 1]
        elif item.startswith("--task-id="):
            raw = item.split("=", 1)[1]
        if raw is not None:
            try:
                return int(raw)
            except ValueError:
                return None
    return None


def print_summary(summary: Mapping[str, Any]) -> None:
    """Print the final stdout line: the JSON summary."""
    print(json.dumps(dict(summary), ensure_ascii=False, sort_keys=True))


def _refusal(task_id: int | None, code: str, message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    print_summary(
        {
            "ok": False,
            "outcome": "refused",
            "task_id": task_id,
            "requested": [],
            "written": [],
            "write_attempted": False,
            "drift": [],
            "mismatch": [],
            "error": code,
            "message": message,
        }
    )
    return EXIT_USAGE


def _build_client() -> Any:
    from scripts.common.vikunja_client import VikunjaClient

    return VikunjaClient()


def main(argv: Sequence[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint; see the module docstring for output and exit codes."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _build_parser().parse_args(raw_argv)
        changes = validate_changes(_changes_from_args(args))
        if args.task_id <= 0:
            raise UpdateRefused(
                "invalid_input", f"task id must be a positive integer, got {args.task_id}"
            )
    except UsageError as exc:
        return _refusal(_task_id_from_argv(raw_argv), "invalid_input", str(exc))
    except UpdateRefused as exc:
        return _refusal(_task_id_from_argv(raw_argv), exc.code, str(exc))

    try:
        active = client if client is not None else _build_client()
    except (OSError, ValueError, RuntimeError) as exc:
        # Missing base-URL config or token file (VikunjaConfigError).
        print(f"ERROR: {exc}", file=sys.stderr)
        print_summary(
            UpdateResult(
                task_id=args.task_id,
                outcome="error",
                requested=sorted(changes),
                error="config_error",
                message=str(exc),
            ).summary()
        )
        return EXIT_UNEXPECTED
    try:
        result = update_task(active, args.task_id, changes)
    except UpdateRefused as exc:
        return _refusal(args.task_id, exc.code, str(exc))

    if result.ok:
        for name in result.written:
            print(f"INFO: {name} -> {changes[name]!r}")
        print(f"INFO: task {args.task_id} {result.outcome}; rule, flag and reminders kept")
    else:
        print(f"ERROR: {result.message}", file=sys.stderr)
    print_summary(result.summary())
    return EXIT_OK if result.ok else EXIT_UNEXPECTED


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
