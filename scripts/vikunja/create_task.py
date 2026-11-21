#!/usr/bin/env python3
"""Create a Vikunja task — canonical helper (issue #686).

The single sanctioned "create a task" path. Wraps the deterministic
``scripts.common.vikunja_client.VikunjaClient`` (which already handles base-URL
normalization, token loading, and auth) so ad-hoc/agent task creation never has
to re-derive the REST call.

Runs **on office2**, where the base-URL config
(``/data/services/openclaw/config/vikunja-base-url.txt``) and the API token
(``/data/services/openclaw/secrets/vikunja-api-kent``, the kent runtime
credential — see ADR-0007) live. For cross-repo,
cwd-independent invocation from the Mac use the global slash-command
``~/.claude/commands/create-vikunja-task.md``, which SSH-dispatches to this
module (so the token is never copied off office2).

Create uses the v2 API, ``POST /api/v2/projects/{id}/tasks``
(``VikunjaClient.create_task_v2``, mission felix-rrule-adaptation #1111). The
task is then read back over v2 (``get_task_v2``); a requested recurrence rule
must be stored exactly (``vikunja_rule.same_rule``), or the CLI exits 1 naming
the created task id: a recurring create that produced a one-off is never
reported as success. The Vikunja **UI identifier** (e.g. ``#38``) differs from
the **API id** (e.g. ``98``); both are reported.

Invocation:

    python3 -m scripts.vikunja.create_task --title "Review billing" \\
        --project 1 --due 2026-07-16T14:00:00Z

    # Every second week, six times:
    python3 -m scripts.vikunja.create_task --title "Water plants" \\
        --due 2026-07-16T14:00:00Z --rrule "FREQ=WEEKLY;INTERVAL=2;COUNT=6"

Project defaults to Inbox (id 1). ``--project`` accepts an id or a project name
(resolved case-insensitively; the lowest matching id wins — note two "Inbox"
projects exist, id 1 and id 14).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

from scripts.common.et_datetime import parse_vikunja_instant
from scripts.common.vikunja_rule import rrule_text_to_parts, same_rule

__all__ = [
    "DEFAULT_PROJECT_ID",
    "RuleNotStoredError",
    "build_payload",
    "create_task",
    "main",
    "resolve_project_id",
]

DEFAULT_PROJECT_ID = 1  # "Inbox"

_HH_MM = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class RuleNotStoredError(RuntimeError):
    """The task was created, but its readback lacks the requested recurrence."""

    def __init__(self, task_id: Any, detail: str) -> None:
        super().__init__(
            f"created task {task_id} but its rule is missing/different ({detail}) "
            "— fix or delete it"
        )
        self.task_id = task_id


def build_payload(
    title: str,
    *,
    due_date: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    rrule: str | None = None,
    from_completion: bool = False,
    initial_due_time: str | None = None,
) -> dict[str, Any]:
    """Build the v2 task-create fields from CLI inputs, validating the rule early.

    Only non-empty fields are included, so the create never sends stray
    nulls. ``title`` is required (Vikunja rejects an empty title).

    Recurrence is an RFC 5545 rule (``rrule``, sent as ``repeats_rrule`` by
    :func:`create_task`, not part of the returned fields). It is parsed here
    with ``vikunja_rule.rrule_text_to_parts`` so a malformed rule fails before
    any HTTP call; the server still validates its semantics. A recurring task
    needs an anchor: either ``due_date`` or ``initial_due_time`` (``HH:MM``,
    from which the server generates the first due date), not both.
    ``from_completion`` maps to ``repeats_from_current_date: true`` (the next
    occurrence counts from when the task is completed).

    Raises:
        ValueError: empty title, unparseable rule, a rule without an anchor,
            or a recurrence option given without ``rrule``.
    """
    title = title.strip()
    if not title:
        raise ValueError("task title must be non-empty")
    if rrule is None:
        if from_completion or initial_due_time is not None:
            raise ValueError("--from-completion and --initial-due-time need --rrule")
    else:
        rrule_text_to_parts(rrule)  # raises ValueError with the offending part
        if initial_due_time is not None:
            if due_date:
                raise ValueError("give a due date or --initial-due-time, not both")
            if not _HH_MM.match(initial_due_time):
                raise ValueError(
                    f"--initial-due-time must be HH:MM (24h), got {initial_due_time!r}"
                )
        elif not due_date:
            raise ValueError(
                "a recurring task needs a due date or --initial-due-time "
                "(the rule is anchored at its first occurrence)"
            )
    payload: dict[str, Any] = {"title": title}
    if due_date:
        payload["due_date"] = due_date
    if description:
        payload["description"] = description
    if priority is not None:
        payload["priority"] = priority
    if from_completion:
        payload["repeats_from_current_date"] = True
    return payload


def resolve_project_id(client: Any, project: str) -> int:
    """Resolve ``project`` (an id string or a project name) to a numeric id.

    A numeric string is used verbatim. Otherwise the project list is fetched
    (``GET /projects``) and matched case-insensitively by title; the lowest
    matching id wins (deterministic tie-break — two "Inbox" projects exist).
    """
    project = project.strip()
    if project.lstrip("-").isdigit():
        return int(project)

    projects = client.get("/projects")
    if not isinstance(projects, list):
        raise ValueError("unexpected /projects response shape")
    matches = sorted(
        (
            int(p["id"])
            for p in projects
            if isinstance(p, dict)
            and isinstance(p.get("id"), int)
            and p["id"] > 0
            and str(p.get("title", "")).strip().lower() == project.lower()
        )
    )
    if not matches:
        raise ValueError(f"no project matches name {project!r}")
    return matches[0]


def create_task(
    client: Any,
    project_id: int,
    payload: dict[str, Any],
    *,
    rrule: str | None = None,
    initial_due_time: str | None = None,
) -> dict[str, Any]:
    """Create the task over v2, read it back, and verify any requested rule.

    Returns the v2 readback. When ``rrule`` was requested the readback's
    ``repeat`` must be the same rule (``same_rule``), a requested
    ``repeats_from_current_date`` must have stuck, an explicit ``due_date``
    must be stored as the same instant (to the second; WP09: the anchor shown
    by ``preview_rule`` is the one created), and an ``initial_due_time`` must
    have produced a due date; otherwise
    :class:`RuleNotStoredError` names the created task id. The created task
    is left in place either way (the error tells the operator to fix or
    delete it).
    """
    created = client.create_task_v2(
        project_id, payload, rrule=rrule, initial_due_time=initial_due_time
    )
    task_id = created.get("id")
    try:
        readback = client.get_task_v2(task_id)
    except Exception as exc:
        raise RuntimeError(
            f"created task {task_id} but could not read it back ({exc}); check it"
        ) from exc
    if rrule is not None:
        if not same_rule(rrule_text_to_parts(rrule), readback.get("repeat")):
            raise RuleNotStoredError(
                task_id,
                f"asked {rrule!r}, stored {readback.get('repeats_rrule')!r}",
            )
        if payload.get("repeats_from_current_date") and (
            readback.get("repeats_from_current_date") is not True
        ):
            raise RuleNotStoredError(task_id, "repeats_from_current_date not set")
        asked_due = parse_vikunja_instant(payload.get("due_date"))
        if asked_due is not None:
            # The anchor Kent confirmed (preview_rule's due_date) must be the
            # one stored. The server keeps an explicit due date to the second.
            stored_due = parse_vikunja_instant(readback.get("due_date"))
            if stored_due != asked_due.replace(microsecond=0):
                raise RuleNotStoredError(
                    task_id,
                    f"asked due {payload.get('due_date')!r}, "
                    f"stored {readback.get('due_date')!r}",
                )
        if initial_due_time is not None and (
            parse_vikunja_instant(readback.get("due_date")) is None
        ):
            # The server saves the task without a due date when the rule has
            # no instance after now, and says why in ``reason``.
            raise RuleNotStoredError(
                task_id,
                f"no first due date generated (reason {created.get('reason')!r})",
            )
    return readback


def _build_client() -> Any:
    from scripts.common.vikunja_client import VikunjaClient

    return VikunjaClient()


def _emit_completion_assertion(task: dict[str, Any]) -> None:
    """Best-effort completion-assertion auto-emit on a successful create (#683).

    Wrapped in its own ``try/except`` so ANY failure here (import error,
    ledger-write error, agent resolution, ...) is swallowed and never breaks
    task creation — ``main()``'s exit code and printed output are unaffected
    either way. Imported lazily to avoid a hard import-time dependency for
    callers that never hit this path (e.g. on a host missing the trust
    package).
    """
    try:
        from scripts.trust.completion_assertion import record_assertion

        agent = os.environ.get("FELIX_TRUST_AGENT") or os.environ.get("FELIX_AGENT") or "unknown"
        record_assertion(
            agent=agent,
            artifact_kind="vikunja_task",
            artifact_ids=[str(task.get("id"))],
            claim=f"Created Vikunja task #{task.get('identifier')}",
        )
    except Exception:  # noqa: BLE001 - fail-safe: must never break task creation
        pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.vikunja.create_task",
        description="Create a Vikunja task (issue #686).",
    )
    parser.add_argument("--title", required=True, help="task title (required)")
    parser.add_argument(
        "--project",
        default=str(DEFAULT_PROJECT_ID),
        help=f"project id or name (default: {DEFAULT_PROJECT_ID} = Inbox)",
    )
    parser.add_argument("--due", default=None, help="due date, ISO-8601 / RFC3339")
    parser.add_argument("--description", default=None, help="optional task description")
    parser.add_argument(
        "--priority", type=int, default=None, help="optional priority (Vikunja 0-5)"
    )
    parser.add_argument(
        "--rrule",
        default=None,
        help=(
            "recurrence as RFC 5545 RRULE text; needs --due or --initial-due-time. "
            "Examples: daily 'FREQ=DAILY'; fortnightly 'FREQ=WEEKLY;INTERVAL=2'; "
            "monthly on the 15th 'FREQ=MONTHLY;BYMONTHDAY=15'; six times "
            "'FREQ=WEEKLY;COUNT=6'; until a date 'FREQ=DAILY;UNTIL=20261231T235959Z' "
            "(UNTIL must be UTC, ending in Z)"
        ),
    )
    parser.add_argument(
        "--from-completion",
        action="store_true",
        help="repeat from when the task is completed, not from its due date "
        "(repeats_from_current_date); needs --rrule",
    )
    parser.add_argument(
        "--initial-due-time",
        default=None,
        metavar="HH:MM",
        help="with --rrule and no --due: the server picks the first due date "
        "at this local time",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the raw created-task JSON"
    )
    return parser


def main(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint. Returns 0 on success, 1 on any handled failure."""
    args = _build_parser().parse_args(argv)
    try:
        payload = build_payload(
            args.title,
            due_date=args.due,
            description=args.description,
            priority=args.priority,
            rrule=args.rrule,
            from_completion=args.from_completion,
            initial_due_time=args.initial_due_time,
        )
        active_client = client if client is not None else _build_client()
        project_id = resolve_project_id(active_client, args.project)
        task = create_task(
            active_client,
            project_id,
            payload,
            rrule=args.rrule,
            initial_due_time=args.initial_due_time,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, exit 1
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # Fail-safe completion-assertion auto-emit (#683) — never affects the
    # success return value or the printed output below.
    _emit_completion_assertion(task)

    if args.json:
        print(json.dumps(task, ensure_ascii=False))
    else:
        # UI identifier (#NN) differs from API id — report both (#686).
        print(
            f"CREATED task id={task.get('id')} identifier={task.get('identifier')} "
            f"project={project_id} due={task.get('due_date') or '-'}"
        )
        print(f"title: {task.get('title')}")
        if task.get("repeats_rrule"):
            print(f"rule: {task.get('repeats_rrule')}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
