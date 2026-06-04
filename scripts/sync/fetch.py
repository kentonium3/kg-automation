"""Vikunja delta-poll fetch phase for the reconciliation driver (WP02 / T006).

Phase 1 of the 6-phase cycle. Pulls all tasks changed since the freshness
pointer plus any newly-referenced project metadata. Pure HTTP; no state
mutation; no business logic.

Contract: kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/
contracts/cycle-pipeline.md § Phase 1.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from scripts.sync.http import get_json


@dataclass(frozen=True)
class FetchedDelta:
    """Output of one fetch phase.

    Attributes:
        tasks: Vikunja task JSON payloads returned by the delta poll.
        projects: Project metadata for every project_id referenced by ``tasks``
            that was not already in the driver's project cache. Failures on
            individual project fetches degrade to a stub entry per project
            (logged to stderr but not aborting the cycle).
        vikunja_version: Best-effort capture of the Vikunja version string.
            ``None`` if the version endpoint failed; not a cycle error.
        fetched_at_utc: Wall-clock at fetch entry. Used as the candidate
            next-pointer value; advanced only after the whole cycle succeeds.
    """

    tasks: tuple[dict, ...]
    projects: dict[int, dict]
    vikunja_version: str | None
    fetched_at_utc: str


def vikunja_now_iso() -> str:
    """Return the wall-clock at fetch entry as an ISO-8601 UTC string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_delta(
    token: str,
    base_url: str,
    since_utc: str,
    known_project_ids: set[int],
) -> FetchedDelta:
    """Pull the Vikunja delta since ``since_utc``.

    Args:
        token: Vikunja bearer token (the ``vikunja-api`` credential value).
        base_url: Fully qualified API base, e.g.
            ``https://office2.tail0f5f56.ts.net/api/v1/``. Trailing slash
            required.
        since_utc: ISO-8601 UTC string. Passed verbatim as the ``updated_since``
            parameter; no clock-skew adjustment.
        known_project_ids: project_ids the driver already has cached. Tasks
            whose project_id is in this set do NOT trigger a per-project fetch.

    Returns:
        FetchedDelta with the changed tasks + just-in-time-fetched projects.

    Raises:
        OSError: If the main ``/tasks/all`` call fails. Per-project and
            ``/info`` failures degrade gracefully — they do NOT raise.
    """
    fetched_at_utc = vikunja_now_iso()

    # Phase 1a: main delta poll. Failures here propagate.
    tasks_url = f"{base_url}tasks/all?updated_since={since_utc}"
    parsed = get_json(tasks_url, token)
    tasks_list: list[dict] = parsed if isinstance(parsed, list) else []
    tasks = tuple(tasks_list)

    # Phase 1b: just-in-time project fetch for any unknown project_id.
    referenced: set[int] = set()
    for task in tasks:
        pid = task.get("project_id")
        if isinstance(pid, int):
            referenced.add(pid)

    projects: dict[int, dict] = {}
    for pid in referenced - known_project_ids:
        try:
            proj = get_json(f"{base_url}projects/{pid}", token)
            if isinstance(proj, dict):
                projects[pid] = proj
            else:
                projects[pid] = _project_stub(pid)
        except OSError as e:
            # Per-project fetch failure is logged but does NOT abort the cycle.
            sys.stderr.write(
                f"[sync fetch] WARNING: project {pid} fetch failed: {e}\n"
            )
            projects[pid] = _project_stub(pid)

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

    return FetchedDelta(
        tasks=tasks,
        projects=projects,
        vikunja_version=vikunja_version,
        fetched_at_utc=fetched_at_utc,
    )


def _project_stub(pid: int) -> dict:
    """Stub project payload used when an individual project fetch fails.

    The downstream classifier treats unknown projects as ``"<unknown>"`` —
    UC-3 evaluation gracefully degrades without firing for tasks in unknown
    projects.
    """
    return {"id": pid, "title": "<unknown>", "is_archived": False}
