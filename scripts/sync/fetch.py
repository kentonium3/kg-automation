"""Vikunja full-poll fetch phase for the reconciliation driver (WP03 / T007).

Phase 1 of the 7-phase cycle. Pulls the complete current state of Vikunja's
task and project layers via two HTTP calls. Pure HTTP; no state mutation; no
business logic.

Contract: kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/
contracts/cycle-pipeline.md § Phase 1.
"""
from __future__ import annotations

import json
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from scripts.sync.http import get_json


@dataclass(frozen=True)
class FetchedSnapshot:
    """Full-state snapshot returned by full-poll fetch.

    Both layers (tasks + projects) are observed in one cycle. Downstream
    consumers treat this as the source of truth for the cycle.

    Replaces FetchedDelta from #518.

    Attributes:
        tasks: Full task list from GET /tasks/all. Every task record returned
            by Vikunja for this cycle.
        projects: Full project list from GET /projects, keyed by project_id
            (integer). The complete current project state.
        vikunja_version: Best-effort capture of the Vikunja version string.
            None if the version endpoint failed; not a cycle error.
        fetched_at_utc: Wall-clock at fetch entry (BEFORE the HTTP calls).
            Used as the cycle-time anchor; advanced only after the whole cycle
            succeeds.
    """

    tasks: tuple[dict, ...]
    projects: dict[int, dict]
    vikunja_version: str | None
    fetched_at_utc: str


def vikunja_now_iso() -> str:
    """Return the wall-clock at fetch entry as an ISO-8601 UTC string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_full_poll(
    token: str,
    base_url: str,
    *,
    task_cache_nonempty: bool = False,
    project_cache_nonempty: bool = False,
) -> FetchedSnapshot:
    """Pull the complete current Vikunja state via full poll.

    Makes exactly two HTTP calls: GET /tasks/all (no updated_since) and
    GET /projects. The second call is not made if the first fails.

    Args:
        token: Vikunja bearer token.
        base_url: Fully qualified API base with trailing slash, e.g.,
            "https://office2.tail0f5f56.ts.net/api/v1/"
        task_cache_nonempty: True if the task_cache passed by the caller
            has non-zero entries. Used by FR-012 guard to detect empty
            responses when the cache says we should have tasks.
        project_cache_nonempty: Same for the project cache.

    Returns:
        FetchedSnapshot with current task and project state.

    Raises:
        OSError: on HTTP failure, 4xx/5xx, parse failure, or FR-012
            empty-response-when-cache-nonempty. The OSError message starts
            with a structured token from this set:
              - "vikunja_unreachable: ..."
              - "auth_failure: ..."
              - "vikunja_5xx: ..."
              - "parse_error: ..."
              - "empty_response_when_cache_nonzero: ..."
    """
    # Record fetch entry time BEFORE any HTTP calls.
    fetched_at_utc = vikunja_now_iso()

    # Phase 1a: fetch all tasks (full poll, no updated_since).
    tasks_url = f"{base_url}tasks/all"
    try:
        tasks_raw = get_json(tasks_url, token)
    except OSError as exc:
        raise _classify_oserror(exc) from exc

    if not isinstance(tasks_raw, list):
        raise OSError(
            f"parse_error: GET {tasks_url} returned non-list body: {type(tasks_raw).__name__!r}"
        )

    if task_cache_nonempty and len(tasks_raw) == 0:
        raise OSError(
            "empty_response_when_cache_nonzero: GET tasks/all returned [] "
            "but task cache is non-empty — possible Vikunja data loss; aborting cycle"
        )

    tasks = tuple(tasks_raw)

    # Phase 1b: fetch all projects (full poll).
    projects_url = f"{base_url}projects"
    try:
        projects_raw = get_json(projects_url, token)
    except OSError as exc:
        raise _classify_oserror(exc) from exc

    if not isinstance(projects_raw, list):
        raise OSError(
            f"parse_error: GET {projects_url} returned non-list body: {type(projects_raw).__name__!r}"
        )

    if project_cache_nonempty and len(projects_raw) == 0:
        raise OSError(
            "empty_response_when_cache_nonzero: GET projects returned [] "
            "but project cache is non-empty — possible Vikunja data loss; aborting cycle"
        )

    projects: dict[int, dict] = {}
    for proj in projects_raw:
        if isinstance(proj, dict):
            pid = proj.get("id")
            if isinstance(pid, int):
                projects[pid] = proj

    # Phase 1c: best-effort version capture. Failure is silent.
    vikunja_version: str | None = None
    try:
        info = get_json(f"{base_url}info", token)
        if isinstance(info, dict):
            ver = info.get("version")
            if isinstance(ver, str):
                vikunja_version = ver
    except OSError:
        # /info is informational only; do not propagate.
        pass

    return FetchedSnapshot(
        tasks=tasks,
        projects=projects,
        vikunja_version=vikunja_version,
        fetched_at_utc=fetched_at_utc,
    )


def _classify_oserror(exc: OSError) -> OSError:
    """Map a raw OSError from get_json into a structured-token OSError.

    Dispatches based on the HTTP status code embedded in the message (as
    produced by scripts.sync.http._http_request) or on the error type.

    Token vocabulary (FR-012):
        auth_failure         — HTTP 401 or 403
        vikunja_5xx          — HTTP 5xx
        vikunja_unreachable  — network error or any other OSError
    """
    msg = str(exc)
    # http.py embeds "HTTP <code>" in the message for HTTP errors.
    if "HTTP 401" in msg or "HTTP 403" in msg:
        return OSError(f"auth_failure: {exc}")
    for code in range(500, 600):
        if f"HTTP {code}" in msg:
            return OSError(f"vikunja_5xx: {exc}")
    return OSError(f"vikunja_unreachable: {exc}")
