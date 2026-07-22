"""Vikunja full-poll fetch phase for the reconciliation driver (WP03 / T007).

Phase 1 of the 7-phase cycle. Pulls the complete current state of Vikunja's
task and project layers. Pure HTTP; no state mutation; no business logic.

Task enumeration is **project-scoped**: it first fetches ``GET /projects``,
then pages ``GET /projects/{id}/tasks`` for each project id. The v1
``GET /tasks/all`` endpoint returns HTTP 400 code 2004 ("Invalid model
provided") for every param shape on Vikunja 2.4.0+ (see
kentonium3/kg-automation#853), so it can no longer be used.

Contract: kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/
contracts/cycle-pipeline.md § Phase 1.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from scripts.sync.http import get_json


@dataclass(frozen=True)
class FetchedSnapshot:
    """Full-state snapshot returned by full-poll fetch.

    Both layers (tasks + projects) are observed in one cycle. Downstream
    consumers treat this as the source of truth for the cycle.

    Replaces FetchedDelta from #518.

    Attributes:
        tasks: Full task list from project-scoped enumeration (GET /projects
            then GET /projects/{id}/tasks per project). Every task record
            returned by Vikunja for this cycle, deduplicated by integer id.
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

    Enumeration is project-scoped: GET /projects is fetched FIRST (its ids
    drive task enumeration), then GET /projects/{id}/tasks is paged for each
    project id, then GET /info (best-effort version). The v1 GET /tasks/all
    endpoint is unusable on Vikunja 2.4.0+ (HTTP 400 code 2004), so it is no
    longer called.

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

    PAGE_SIZE = 50
    MAX_PAGES = 200

    # Phase 1a: fetch all projects (full poll). Fetched FIRST because the
    # project ids drive the project-scoped task enumeration below.
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

    # Phase 1b: fetch tasks project-scoped. For each project id, page
    # GET /projects/{id}/tasks (Vikunja caps per_page at 50) until a partial /
    # empty page. MAX_PAGES is a per-project runaway-loop bound. Accumulate and
    # dedup by integer id (a task belongs to exactly one project, so dedup is a
    # defensive measure).
    all_tasks: list = []
    seen_ids: set[int] = set()
    for pid in projects:
        for page in range(1, MAX_PAGES + 1):
            tasks_url = f"{base_url}projects/{pid}/tasks?page={page}&per_page={PAGE_SIZE}"
            try:
                tasks_raw = get_json(tasks_url, token)
            except OSError as exc:
                raise _classify_oserror(exc) from exc

            # Vikunja returns JSON null OR [] for an exhausted / empty page;
            # both stop paging this project (never an error).
            if tasks_raw is None:
                break
            if not isinstance(tasks_raw, list):
                raise OSError(
                    f"parse_error: GET {tasks_url} returned non-list body: {type(tasks_raw).__name__!r}"
                )

            if not tasks_raw:
                break
            for task in tasks_raw:
                if isinstance(task, dict):
                    tid = task.get("id")
                    if isinstance(tid, int) and not isinstance(tid, bool):
                        if tid in seen_ids:
                            continue
                        seen_ids.add(tid)
                all_tasks.append(task)
            if len(tasks_raw) < PAGE_SIZE:
                break
        else:
            raise OSError(
                f"pagination_exceeded: GET projects/{pid}/tasks hit page cap "
                f"({MAX_PAGES}); increase MAX_PAGES or investigate runaway"
            )

    if task_cache_nonempty and len(all_tasks) == 0:
        raise OSError(
            "empty_response_when_cache_nonzero: project-scoped task enumeration "
            "returned [] but task cache is non-empty — possible Vikunja data "
            "loss; aborting cycle"
        )

    tasks = tuple(all_tasks)

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
