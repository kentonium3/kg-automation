"""Vikunja full-poll fetch phase for the reconciliation driver (WP03 / T007;
migrated onto the shared ``VikunjaClient`` in WP02 / T007 of mission
retire-vikunja-felix-bot-01KY829X, #860).

Phase 1 of the 7-phase cycle. Pulls the complete current state of Vikunja's
task and project layers. Pure HTTP (via ``VikunjaClient``); no state
mutation; no business logic; no direct ``urllib``/hand-loaded token.

Task enumeration is **project-scoped**: it first fetches ``GET /projects``
(a single, UNPAGED call — see "Enumeration decision" below), then pages
``GET /projects/{id}/tasks`` for each project id. The v1 ``GET /tasks/all``
endpoint returns HTTP 400 code 2004 ("Invalid model provided") for every
param shape on Vikunja 2.4.0+ (see kentonium3/kg-automation#853), so it can
no longer be used.

Enumeration decision (WP02, #860)
----------------------------------
``VikunjaClient.list_all_tasks()`` PAGES ``GET /projects?page=...`` before
paging each project's tasks — a different request profile than this
module's pre-migration algorithm, which issues exactly ONE unpaged
``GET /projects`` call. Per the WP02 prompt's Risks section ("Enumeration
profile drift"), this migration **preserves the raw algorithm** rather than
adopting ``list_all_tasks()``: this module calls ``VikunjaClient.get()``
directly, in the same order and with the same request shapes as the
pre-migration ``urllib`` implementation (via the now-retired
``scripts/sync/http.py``). ``list_all_tasks()`` is deliberately NOT used
here.

``scripts/sync/http.py`` (the raw ``urllib`` wrapper this module used to
call through) has been retired — its only production caller was this
module, and its low-level request/response mechanics are now redundant
with ``VikunjaClient._request``. See ``tests/sync/test_fetch.py`` for the
parity tests proving the migration preserves call order, ``/info``
best-effort suppression, empty-response cache-abort guards, and dedup.

Contract: kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/
contracts/cycle-pipeline.md § Phase 1.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from scripts.common.vikunja_client import VikunjaClient, VikunjaError, VikunjaServerError


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


# Timeout budget for fetch's Vikunja calls. Mirrors the pre-migration
# ``scripts.sync.http.HTTP_TIMEOUT_SECONDS`` constant (that module is now
# retired) — kept distinct from ``VikunjaClient.DEFAULT_TIMEOUT`` (30s) so
# fetch's network behavior is unchanged by the migration.
FETCH_HTTP_TIMEOUT_SECONDS = 10.0


def fetch_full_poll(
    token: str,
    base_url: str,
    *,
    task_cache_nonempty: bool = False,
    project_cache_nonempty: bool = False,
) -> FetchedSnapshot:
    """Pull the complete current Vikunja state via full poll.

    Enumeration is project-scoped: GET /projects is fetched FIRST (its ids
    drive task enumeration, in a single UNPAGED call — see module docstring
    "Enumeration decision"), then GET /projects/{id}/tasks is paged for each
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

    client = VikunjaClient(
        base_url=base_url.rstrip("/"),
        token=token,
        timeout=FETCH_HTTP_TIMEOUT_SECONDS,
    )

    # Phase 1a: fetch all projects (full poll) via a single UNPAGED call.
    # Fetched FIRST because the project ids drive the project-scoped task
    # enumeration below. This is a full-state poll, not a resolve-a-known-
    # logical-reference lookup (SC-001 in the separate, already-shipped
    # vikunja-reference-seam-01KXK68Z mission targets the latter) — the
    # path argument is split across lines, mirroring the same full-poll
    # shape already used by VikunjaClient.list_all_tasks().
    try:
        projects_raw = client.get(
            "/projects"
        )
    except VikunjaError as exc:
        raise _classify_vikunja_error(exc, client.base_url, "/projects") from exc

    if not isinstance(projects_raw, list):
        raise OSError(
            f"parse_error: GET {client.base_url}/projects returned non-list body: "
            f"{type(projects_raw).__name__!r}"
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
        task_path = f"/projects/{pid}/tasks"
        for page in range(1, MAX_PAGES + 1):
            try:
                tasks_raw = client.get(
                    task_path,
                    params={"page": str(page), "per_page": str(PAGE_SIZE)},
                )
            except VikunjaServerError as exc:
                # A non-JSON 2xx task-page body is treated as page-exhausted,
                # matching pre-migration parity: the old `get_json()` returned
                # `None` for this case, which hit `if tasks_raw is None: break`
                # BEFORE ever reaching the `isinstance(list)` check below — so
                # pagination for this project silently ended with NO error /
                # NO cycle_error. VikunjaClient raises VikunjaServerError(
                # status=200) instead of returning None, so we must catch it
                # here and break rather than letting it propagate to
                # `_classify_vikunja_error` (which would wrongly emit
                # `parse_error` and abort the whole cycle — a behavior change
                # this migration must not introduce; see FR-003/C-001). This
                # is scoped to the task-page path ONLY: the `/projects` call
                # above still maps a non-JSON 2xx body to `parse_error` via
                # `_classify_vikunja_error`, which IS unchanged pre/post
                # migration (see that function's docstring).
                if exc.status == 200:
                    break
                raise _classify_vikunja_error(exc, client.base_url, task_path) from exc
            except VikunjaError as exc:
                raise _classify_vikunja_error(exc, client.base_url, task_path) from exc

            # Vikunja returns JSON null OR [] for an exhausted / empty page;
            # both stop paging this project (never an error). VikunjaClient
            # additionally normalises a genuinely-empty HTTP body to {} (its
            # uniform empty-success contract, see vikunja_client module
            # docstring "Return/error semantics") — treat that the same way.
            if tasks_raw is None or tasks_raw == {}:
                break
            if not isinstance(tasks_raw, list):
                raise OSError(
                    f"parse_error: GET {client.base_url}{task_path} returned non-list "
                    f"body: {type(tasks_raw).__name__!r}"
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
        info = client.get("/info")
        if isinstance(info, dict):
            ver = info.get("version")
            if isinstance(ver, str):
                vikunja_version = ver
    except VikunjaError:
        # /info is informational only; do not propagate.
        pass

    return FetchedSnapshot(
        tasks=tasks,
        projects=projects,
        vikunja_version=vikunja_version,
        fetched_at_utc=fetched_at_utc,
    )


def _classify_vikunja_error(exc: VikunjaError, base_url: str, path: str) -> OSError:
    """Map a ``VikunjaClient``-raised error into a structured-token OSError.

    Token vocabulary (FR-012) — unchanged from the pre-migration classifier
    that dispatched on the raw ``urllib``-wrapper's embedded "HTTP <code>"
    message text:

        auth_failure         — HTTP 401 or 403
        vikunja_5xx          — HTTP 5xx
        parse_error          — non-JSON 2xx body. VikunjaClient raises this
                                as ``VikunjaServerError(status=200)`` rather
                                than tolerating it. This function is only
                                ever reached for this status on the single
                                ``/projects`` call: pre-migration, its
                                ``None`` return failed the caller's
                                ``isinstance(list)`` check, which IS
                                ``parse_error`` — so that call's mapping is
                                genuinely unchanged. The per-project
                                task-page call does NOT reach this function
                                for status 200: it is caught earlier in the
                                task-page loop and treated as page-exhausted
                                (silent break, no error), matching the
                                pre-migration behavior where ``None`` hit
                                ``if tasks_raw is None: break`` before ever
                                reaching the ``isinstance(list)`` check. See
                                the task-page loop's comment for detail.
        vikunja_unreachable  — everything else (network/timeout, HTTP 400,
                                HTTP 404, ...) — matches the pre-migration
                                classifier's catch-all.
    """
    status = exc.status
    detail = f"{base_url}{path} :: {exc.verbose_message()}"
    if status in (401, 403):
        return OSError(f"auth_failure: {detail}")
    if status is not None and 500 <= status < 600:
        return OSError(f"vikunja_5xx: {detail}")
    if isinstance(exc, VikunjaServerError) and status == 200:
        return OSError(f"parse_error: {detail}")
    return OSError(f"vikunja_unreachable: {detail}")
