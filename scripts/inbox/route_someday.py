"""Route a captured note's "someday" block to the Vikunja ``Someday`` project.

CLI (mandatory ``-m`` form per NFR-004 / ``[[feedback_helper_m_invocation_form]]``):

    python3 -m scripts.inbox.route_someday \
        --title "<title>" --body "<body>" --note-filename <name>

Contract: ``kitty-specs/capture-d6-helpers-extraction-01KTMS5Q/contracts/helper-cli.md``
§ ``route_someday``. FR-004; constraint C-006.

Behavior
--------
1. Instantiate :class:`scripts.common.vikunja_client.VikunjaClient` (token + base
   URL loaded from the canonical secret + config paths).
2. Resolve the ``Someday`` project by listing projects via ``GET /projects`` and
   filtering by ``title == "Someday"``.
3. Create the task via ``PUT /projects/<id>/tasks`` with ``{title, description}``
   where description = ``<body>\n\nSource: <note-filename>``. This is Vikunja's
   CREATE endpoint (see ``scripts/habits/record_completion.py`` + the contract
   in ``scripts/openclaw/skills/vikunja-api/SKILL.md`` line 434). Per C-006 and
   ``[[feedback_vikunja_post_partial_replace]]`` we MUST NOT use ``POST
   /tasks/<id>`` on a pre-existing task — that endpoint partial-replaces and
   was the root cause of #524.
4. Emit ``task_id=<int>`` to stdout on success. Errors go to stderr as
   JSON: ``{"error": "<kind>", "detail": "..."}``. Exit 2 for any Vikunja-side
   failure (per the helper-cli convention).

Stdlib only. Imports the shared ``VikunjaClient`` (also stdlib-only).
"""
from __future__ import annotations

import argparse
import json
import sys

from scripts.common.vikunja_client import VikunjaClient, VikunjaError

__all__ = [
    "RouteSomedayError",
    "find_someday_project",
    "route_someday",
    "main",
]

SOMEDAY_PROJECT_TITLE = "Someday"


class RouteSomedayError(Exception):
    """Domain exception for failures within ``route_someday``.

    Surfaced to the caller via exit 2 + structured stderr. Wrapping
    :class:`VikunjaError` and :class:`ConnectionError` keeps the CLI's
    error contract uniform regardless of which layer detected the
    failure.
    """


def find_someday_project(client: VikunjaClient) -> int:
    """Return the integer project id of the ``Someday`` project.

    Calls ``GET /projects`` (Vikunja returns the full project list for the
    authenticated user). Filters by exact case-sensitive title match per
    the WP03 risk note in the prompt — the live ``Someday`` project's
    canonical title is exactly that string.

    Raises :class:`RouteSomedayError` if the response isn't a list or the
    project isn't present.
    """
    projects = client.get("/projects")
    if not isinstance(projects, list):
        raise RouteSomedayError(
            f"GET /projects did not return a list (got {type(projects).__name__})"
        )
    matches = [
        p
        for p in projects
        if isinstance(p, dict) and p.get("title") == SOMEDAY_PROJECT_TITLE
    ]
    if not matches:
        raise RouteSomedayError(
            f"Vikunja project titled {SOMEDAY_PROJECT_TITLE!r} not found "
            f"in /projects response."
        )
    # If multiple match (shouldn't happen but defensive), prefer the lowest id
    # for determinism — same convention as ``vikunja_writer.lookup_inbox_project_id``.
    return min(int(p["id"]) for p in matches)


def route_someday(
    title: str, body: str, note_filename: str
) -> int:
    """Create a Vikunja task in the Someday project and return its id.

    Returns the created task id on success. Raises
    :class:`RouteSomedayError` (wrapping any underlying Vikunja or network
    failure) on any error path so the CLI ``main`` can map to a single
    exit code + structured stderr.
    """
    try:
        client = VikunjaClient()
    except ValueError as exc:
        # Token/base-url config errors surface here. Treat as vikunja_error.
        raise RouteSomedayError(f"VikunjaClient construction failed: {exc}") from exc

    try:
        project_id = find_someday_project(client)
    except (VikunjaError, ConnectionError) as exc:
        raise RouteSomedayError(f"Failed to list Vikunja projects: {exc}") from exc

    description = f"{body}\n\nSource: {note_filename}"
    payload = {
        "title": title,
        "description": description,
    }
    try:
        response = client.put(f"/projects/{project_id}/tasks", json=payload)
    except (VikunjaError, ConnectionError) as exc:
        raise RouteSomedayError(
            f"Failed to create Vikunja task in project {project_id}: {exc}"
        ) from exc

    if not isinstance(response, dict) or "id" not in response:
        raise RouteSomedayError(
            f"Vikunja create-task response missing 'id': {str(response)[:200]}"
        )
    return int(response["id"])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="route_someday",
        description=(
            "Create a Vikunja task in the Someday project for a captured "
            "note block. Uses Vikunja's CREATE endpoint (PUT "
            "/projects/<id>/tasks); per C-006 must NOT partial-replace an "
            "existing task."
        ),
    )
    parser.add_argument("--title", required=True, help="Task title.")
    parser.add_argument("--body", required=True, help="Task body / description.")
    parser.add_argument(
        "--note-filename",
        required=True,
        help="Source note filename; recorded as 'Source: <name>' footer in description.",
    )
    return parser


def _emit_error(detail: str) -> None:
    """Write a structured error envelope to stderr."""
    print(
        json.dumps({"error": "vikunja_error", "detail": detail}),
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        task_id = route_someday(
            title=args.title,
            body=args.body,
            note_filename=args.note_filename,
        )
    except RouteSomedayError as exc:
        _emit_error(str(exc))
        return 2

    print(f"task_id={task_id}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
