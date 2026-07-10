#!/usr/bin/env python3
"""Create a Vikunja task — canonical helper (issue #686).

The single sanctioned "create a task" path. Wraps the deterministic
``scripts.common.vikunja_client.VikunjaClient`` (which already handles base-URL
normalization, token loading, and auth) so ad-hoc/agent task creation never has
to re-derive the REST call.

Runs **on office2**, where the base-URL config
(``/data/services/openclaw/config/vikunja-base-url.txt``) and the API token
(``/data/services/openclaw/secrets/vikunja-api``) live. For cross-repo,
cwd-independent invocation from the Mac use the global slash-command
``~/.claude/commands/create-vikunja-task.md``, which SSH-dispatches to this
module (so the token is never copied off office2).

Create uses ``PUT /projects/{id}/tasks`` — NOT ``POST /tasks/{id}`` (which zeroes
unstated fields; see #524). The Vikunja **UI identifier** (e.g. ``#38``) differs
from the **API id** (e.g. ``98``); both are reported.

Invocation:

    python3 -m scripts.vikunja.create_task --title "Review billing" \\
        --project 1 --due 2026-07-16T14:00:00Z

Project defaults to Inbox (id 1). ``--project`` accepts an id or a project name
(resolved case-insensitively; the lowest matching id wins — note two "Inbox"
projects exist, id 1 and id 14).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

__all__ = [
    "DEFAULT_PROJECT_ID",
    "build_payload",
    "resolve_project_id",
    "create_task",
    "main",
]

DEFAULT_PROJECT_ID = 1  # "Inbox"


def build_payload(
    title: str,
    *,
    due_date: str | None = None,
    description: str | None = None,
    priority: int | None = None,
) -> dict[str, Any]:
    """Build the Vikunja task-create body from CLI inputs.

    Only non-empty fields are included, so the create never sends stray
    nulls. ``title`` is required (Vikunja rejects an empty title).
    """
    title = title.strip()
    if not title:
        raise ValueError("task title must be non-empty")
    payload: dict[str, Any] = {"title": title}
    if due_date:
        payload["due_date"] = due_date
    if description:
        payload["description"] = description
    if priority is not None:
        payload["priority"] = priority
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


def create_task(client: Any, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """PUT the task under ``project_id`` and return the created task JSON."""
    result = client.put(f"/projects/{project_id}/tasks", json=payload)
    if not isinstance(result, dict):
        raise ValueError("unexpected task-create response shape")
    return result


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
        )
        active_client = client if client is not None else _build_client()
        project_id = resolve_project_id(active_client, args.project)
        task = create_task(active_client, project_id, payload)
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
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
