"""Shared Vikunja HTTP client (mission vikunja-client-and-habits-weekly-report-01KTKSFT).

Stateless, stdlib-only wrapper around Vikunja's REST API. Encapsulates base
URL composition, token loading, request execution, timeout policy, and
typed error semantics.

Per Felix Constitution Directive 6 this is the deterministic
infrastructure layer: no LLM, no global state, no caching. Each method is
a pure function of inputs to parsed JSON OR typed exception.

Authoritative contract:
``kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/vikunja_client.md``.

Consumers
---------
First production caller: ``scripts/habits/query_active_habits_weekly.py``
(WP02 of mission ``vikunja-client-and-habits-weekly-report-01KTKSFT``,
addresses kentonium3/kg-automation#542). Existing scripts under
``scripts/vikunja/`` and ``scripts/inbox/`` may migrate to this client in
follow-on work.

Mission slice context: this module lands at WP01; WP02 immediately
follows in the same mission and is the first production import. By
spec-kitty convention, multi-WP mission slices land as a unit via
``spec-kitty merge``, so this module is not "dead code" within the
mission scope — it is the foundation that the next WP consumes.

Public surface
--------------
Constants: ``DEFAULT_TIMEOUT``
Token resolution: the default token path is **not** a constant here — it is
    resolved at call time through
    :func:`scripts.common.vikunja_config.get_vikunja_token_path` (the single
    token-resolution point, FR-001 of the token-seam mission). Keeping it out of
    this module means no felix-bot token literal survives in the runtime surface
    (SC-001) and a ``VIKUNJA_TOKEN_PATH`` override / default change moves every
    default-constructed ``VikunjaClient()`` with it.
Exceptions: ``VikunjaError``, ``VikunjaHttpError``, ``VikunjaAuthError``,
    ``VikunjaNotFoundError``, ``VikunjaBadRequestError``,
    ``VikunjaServerError``, ``VikunjaTimeoutError``, ``SeriesEndIncomplete``
Constants (v2 seam): ``WRITABLE_TASK_FIELDS``
Class: ``VikunjaClient``

v2 seam (mission felix-rrule-adaptation-01M7TKNX, WP02, #1111)
--------------------------------------------------------------
Contract: ``kitty-specs/felix-rrule-adaptation-01M7TKNX/contracts/vikunja-client-v2.md``.
The configured base URL stays the ``/api/v1`` URL (R-002); the client derives
``v2_base_url`` from it. :meth:`VikunjaClient.patch_task` is the main write
path: ``PATCH /api/v2/tasks/{id}`` with ``application/merge-patch+json`` and
only the changed keys. Server facts (vikunja-harness ``d7e202228`` + huma
autopatch v2.40.0): a merge patch ``null`` deletes a key, so ``None`` values
are refused; a no-op patch answers **304 with an empty body**
(autopatch.go:408-410), returned as ``None``; ``{"repeat": null, "done":
true}`` in one call reopens the task (``pkg/models/tasks.go:1740-1760``), so
:meth:`VikunjaClient.end_series` uses two calls. v2 error bodies carry
Vikunja's numeric ``code`` (``pkg/routes/api/v2/errors.go:116-121``), exposed
as ``exc.code``.

Redaction policy (FR-011, FR-012)
---------------------------------
Default ``str(exc)`` returns ``"<ExceptionClass>: <path>"`` only — never
response body content. ``exc.verbose_message()`` returns the longer
representation including the status code; intended for ad-hoc debugging,
never logged by default. The raw response body text (when available) is
captured on ``exc.body`` for adapter use (see "Return/error semantics"
below) — it is never included in ``str(exc)`` or ``verbose_message()``.

Return/error semantics (WP01, mission retire-vikunja-felix-bot-01KY829X)
--------------------------------------------------------------------------
This is Phase 1 (behavior-preserving consolidation, #860). The raw-HTTP
consumers being migrated in later WPs (WP02-WP06) each hand-roll their own
``urllib``-based helper with subtly different return/error semantics than
this client. This client's contract does **not** change to match them —
instead, each migrating WP adapts its call site. The decision, per
operation family:

- **Empty / 204 success body.** This client returns ``{}`` (uniform
  mapping, existing contract). Raw consumers return ``None``. Both are
  falsy, so a migrated call site that does ``if result:`` needs no change;
  a call site that does ``if result is None:`` must switch to
  ``if not result:`` or an explicit ``== {}`` check.
- **Non-2xx HTTP status.** This client raises a typed
  :class:`VikunjaHttpError` subclass; ``str(exc)`` is redacted (FR-012) to
  ``"<Class>: <path>"``. Raw consumers raise a local exception (``OSError``
  or a domain-specific class) whose *message* embeds
  ``"{method} {url} failed with HTTP {code}: {body!r}"`` verbatim. A
  migrated call site that pattern-matches on that raw message text must
  instead catch the typed exception and read ``exc.status`` /
  ``exc.body`` (adapter path — the raw body text, uncensored, captured at
  raise time) to reconstruct equivalent detail, or (preferred) switch to
  matching on the typed exception class.
- **Non-JSON 2xx body.** This client raises :class:`VikunjaServerError`
  (existing contract — a non-JSON 2xx body is a contract violation).
  Some raw consumers instead *tolerate* a non-JSON 2xx body by returning
  ``None`` (comment-create in particular carries a defensive comment to
  this effect). A migrating WP touching a comment-create call site must
  verify actual server behavior before relying on this client's stricter
  (raising) contract, and use ``exc.body`` if it needs to inspect what
  came back.

No migration happens in this WP (T005 only defines the seam); WP02-WP06
each make the per-call-site adaptation decision explicitly.
"""
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from scripts.common.vikunja_rule import has_rule, rrule_text_to_parts, same_rule

__all__ = [
    "DEFAULT_TIMEOUT",
    "WRITABLE_TASK_FIELDS",
    "SeriesEndIncomplete",
    "VikunjaAuthError",
    "VikunjaBadRequestError",
    "VikunjaClient",
    "VikunjaError",
    "VikunjaHttpError",
    "VikunjaNotFoundError",
    "VikunjaServerError",
    "VikunjaTimeoutError",
]

DEFAULT_TIMEOUT = 30.0

_BASE_URL_PATTERN = re.compile(r"^https?://[^/]+/api/v1$")

#: Task keys :meth:`VikunjaClient.patch_task` may send. The fork's update
#: column list (vikunja-harness d7e202228 ``pkg/models/tasks.go:1518-1533``)
#: plus the rule text and reminders, minus ``bucket_id`` and
#: ``cover_image_attachment_id``, which Felix does not use.
WRITABLE_TASK_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "description",
        "done",
        "due_date",
        "repeat",
        "repeats_rrule",
        "repeats_from_current_date",
        "priority",
        "start_date",
        "end_date",
        "hex_color",
        "percent_done",
        "project_id",
        "reminders",
        "is_favorite",
    }
)

_MERGE_PATCH_CONTENT_TYPE = "application/merge-patch+json"
_JSON_CONTENT_TYPE = "application/json"

#: Returned by ``_request`` when the server answers 304 Not Modified and the
#: caller opted in (only :meth:`VikunjaClient.patch_task` does).
_NOT_MODIFIED = object()

_OCCURRENCES_COUNT_MIN = 1
_OCCURRENCES_COUNT_MAX = 100  # server bound, task_occurrences.go taskOccurrencesInput


# ---------------------------------------------------------------------------
# Exception hierarchy (per data-model.md + contracts/vikunja_client.md)
# ---------------------------------------------------------------------------


class VikunjaError(Exception):
    """Base exception for all Vikunja-client failures.

    Carries ``path`` (the request path that triggered the error) and
    ``status`` (HTTP status code, or None for network-layer failures like
    timeouts).

    Default ``str(exc)`` redacts response body content per FR-012 — only
    the class name and the request path appear. Use
    :meth:`verbose_message` for ad-hoc debugging.
    """

    def __init__(
        self,
        path: str,
        status: int | None = None,
        *,
        body: str | None = None,
        detail: str | None = None,
        code: int | None = None,
    ) -> None:
        self.path = path
        self.status = status
        #: Vikunja's numeric error code from a v2 error body, when present
        #: (e.g. 2002 invalid rule, 2003 invalid time zone, 11 permission).
        self.code = code
        #: Raw response body text, when captured (adapter path — see the
        #: module-level "Return/error semantics" note). Never included in
        #: ``str(exc)`` or :meth:`verbose_message`; a WP migrating a raw
        #: consumer reads this directly when it must reconstruct raw-style
        #: error detail.
        self.body = body
        #: Short, client-authored hint (never server text, never the token).
        self.detail = detail
        message = f"{type(self).__name__}: {path}"
        if detail:
            message = f"{message} ({detail})"
        super().__init__(message)

    def verbose_message(self) -> str:
        """Detailed representation for ad-hoc operator debugging.

        Includes status code; never logged by default.
        """
        return f"{type(self).__name__}(path={self.path!r}, status={self.status!r})"


class VikunjaHttpError(VikunjaError):
    """Base for HTTP-status-derived failures (non-2xx that don't match a specific subclass)."""


class VikunjaAuthError(VikunjaHttpError):
    """HTTP 401 — token expired or invalid."""


class VikunjaNotFoundError(VikunjaHttpError):
    """HTTP 404 — resource not found."""


class VikunjaBadRequestError(VikunjaHttpError):
    """HTTP 400 — malformed request (e.g. invalid filter syntax)."""


class VikunjaServerError(VikunjaHttpError):
    """HTTP 5xx, network-layer URL errors that are not timeouts, and non-JSON response bodies."""


class VikunjaTimeoutError(VikunjaError):
    """Request exceeded the timeout budget (socket.timeout or URLError(timeout))."""


class SeriesEndIncomplete(VikunjaError):
    """:meth:`VikunjaClient.end_series` could not verify the series ended.

    ``state`` is one of :attr:`STATES`:

    - ``rule_cleared_not_done``: the rule was cleared but the task is not
      (verifiably) done. Running ``end_series`` again resumes.
    - ``rule_reappeared``: a rule was present again after it was cleared.
    - ``not_ended``: the final readback is not ``done`` with no rule.
    - ``unknown``: a write timed out and the re-read failed too.

    Callers record it as a partial outcome and alert (data-model.md
    "End-series recovery contract").
    """

    STATES = frozenset(
        {"rule_cleared_not_done", "rule_reappeared", "not_ended", "unknown"}
    )

    def __init__(self, task_id: int, state: str) -> None:
        if state not in self.STATES:
            raise ValueError(f"unknown SeriesEndIncomplete state {state!r}")
        self.task_id = task_id
        self.state = state
        super().__init__(
            path=f"/tasks/{task_id}", status=None, detail=f"series end {state}"
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class VikunjaClient:
    """Stdlib-only HTTP wrapper around Vikunja's REST API.

    Stateless per-instance: each instantiation captures ``base_url``,
    ``token``, ``timeout`` at construct time. No retries, no caching, no
    pagination iteration helpers — callers handle those concerns.

    Parameters are keyword-only to keep the contract self-documenting.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if base_url is None:
            from scripts.common.vikunja_config import get_vikunja_base_url

            base_url = get_vikunja_base_url()
        normalized_base_url = base_url.rstrip("/")
        if not _BASE_URL_PATTERN.match(normalized_base_url):
            raise ValueError(
                f"Invalid Vikunja base_url {base_url!r}: expected "
                f"https?://<host>/api/v1[/]"
            )

        if token is None:
            token = self._load_default_token()
        token = token.strip()
        if not token:
            raise ValueError("Vikunja token must be a non-empty string")

        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError(f"Vikunja timeout must be positive, got {timeout!r}")

        self.base_url = normalized_base_url
        #: Derived v2 root (R-002); the configured URL stays the v1 one.
        self.v2_base_url = normalized_base_url[: -len("/api/v1")] + "/api/v2"
        self.token = token
        self.timeout = float(timeout)

    @staticmethod
    def _load_default_token() -> str:
        # Resolve the token path at *call time* (never import time) through the
        # single config seam (FR-001). A VIKUNJA_TOKEN_PATH override — or a
        # change to the one module default in vikunja_config — then moves every
        # default-constructed VikunjaClient() with it. The import is local to
        # keep resolution call-time (mirrors the base_url seam in __init__) and
        # to avoid an import-time coupling to vikunja_config.
        from scripts.common.vikunja_config import get_vikunja_token_path

        # A missing/unreadable token file fails loud here as the single
        # VikunjaConfigError (NFR-002); the OSError guard below is a defensive
        # TOCTOU backstop only.
        token_path = get_vikunja_token_path()
        try:
            return token_path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover — helper already gates access
            raise ValueError(
                f"Vikunja token file {token_path} could not be read: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public HTTP surface
    # ------------------------------------------------------------------

    def get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self._request("GET", path, params=params, json_body=None, timeout=timeout)

    def post(
        self,
        path: str,
        *,
        json: dict | None = None,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self._request("POST", path, params=params, json_body=json, timeout=timeout)

    def put(
        self,
        path: str,
        *,
        json: dict | None = None,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self._request("PUT", path, params=params, json_body=json, timeout=timeout)

    def patch(
        self,
        path: str,
        *,
        json: dict | None = None,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """PATCH request. Mirrors :meth:`put` — same contract, PATCH verb.

        Added for the escalation domain (``PATCH /tasks/{id}`` for
        ``done``/``due_date`` updates — WP01, #860).
        """
        return self._request("PATCH", path, params=params, json_body=json, timeout=timeout)

    def delete(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self._request("DELETE", path, params=params, json_body=None, timeout=timeout)

    # ------------------------------------------------------------------
    # High-level enumeration helper
    # ------------------------------------------------------------------

    def list_all_tasks(
        self,
        *,
        updated_since: str | None = None,
        per_page: int = 50,
        max_pages_per_project: int = 200,
    ) -> list[dict]:
        """Return every task via project-scoped enumeration (all projects × their tasks).

        This is the drop-in replacement for the v1 ``GET /tasks/all`` endpoint,
        which returns HTTP 400 ``code 2004 "Invalid model provided"`` for every
        param shape on Vikunja 2.4.0+ (see kentonium3/kg-automation#853). Instead
        of the (broken) global task endpoint, this method:

        1. Enumerates all projects by paging ``GET /projects``.
        2. For each project id, pages ``GET /projects/{id}/tasks``.

        Behavior notes:

        - **Done-inclusive.** No ``filter`` is sent, so the project-scoped
          listing returns both done and not-done tasks — matching the
          done-inclusive semantics of the old ``/tasks/all``. Callers keep
          their own ``done`` filtering.
        - **``updated_since`` passthrough.** When provided, it is sent on every
          per-project task request; omitted entirely when ``None``.
        - **Deduplicated by int ``id``.** A defensive measure — a task belongs
          to exactly one project, but a set guards against any overlap.
        - **No domain filtering / no per-element validation.** Raw task dicts
          are returned in a flat list; malformed elements are passed through
          unchanged so each caller can apply its own validation.

        Empty collections: Vikunja returns JSON ``null`` OR ``[]`` for an
        exhausted / empty page; both stop paging (never an error). A short page
        (fewer than ``per_page`` items) also stops paging. A non-list, non-None
        page body is a contract violation → :class:`VikunjaError`. Both the
        project loop and each per-project task loop are bounded by
        ``max_pages_per_project`` (a runaway-loop guard) → :class:`VikunjaError`
        if exceeded.

        Known limitation: tasks in projects NOT returned by ``GET /projects``
        (e.g. archived projects, if the server excludes them) are not
        enumerated. This is acceptable for current consumers, and for the sync
        driver it yields desirable task/project-layer consistency (a task is
        only observed if its project is).
        """
        project_ids: list[int] = []
        for page in range(1, max_pages_per_project + 1):
            batch = self.get(
                "/projects",
                params={"page": str(page), "per_page": str(per_page)},
            )
            if batch is None:
                break
            if not isinstance(batch, list):
                raise VikunjaError(path="/projects", status=200)
            for element in batch:
                if not isinstance(element, dict):
                    continue
                pid = element.get("id")
                if isinstance(pid, int) and not isinstance(pid, bool):
                    project_ids.append(pid)
            if len(batch) < per_page:
                break
        else:
            raise VikunjaError(path="/projects", status=None)

        tasks: list[dict] = []
        seen_ids: set[int] = set()
        for pid in project_ids:
            path = f"/projects/{pid}/tasks"
            for page in range(1, max_pages_per_project + 1):
                params = {"page": str(page), "per_page": str(per_page)}
                if updated_since is not None:
                    params["updated_since"] = updated_since
                batch = self.get(path, params=params)
                if batch is None:
                    break
                if not isinstance(batch, list):
                    raise VikunjaError(path=path, status=200)
                for element in batch:
                    if isinstance(element, dict):
                        tid = element.get("id")
                        if isinstance(tid, int) and not isinstance(tid, bool):
                            if tid in seen_ids:
                                continue
                            seen_ids.add(tid)
                    tasks.append(element)
                if len(batch) < per_page:
                    break
            else:
                raise VikunjaError(path=path, status=None)
        return tasks

    # ------------------------------------------------------------------
    # Shared task/comment operations (WP01, mission #860 — inventory-driven
    # from the raw-HTTP consumers in scripts/sync, scripts/escalation,
    # scripts/enrichment, scripts/habits, scripts/security/credential_health_check)
    # ------------------------------------------------------------------

    def get_task(
        self, task_id: int, *, timeout: float | None = None
    ) -> Any:
        """GET a single task by id.

        Shared single-task read used directly (e.g.
        ``habits/identify_workout_task.py``) and internally by
        :meth:`update_task_fields`.
        """
        return self.get(f"/tasks/{task_id}", timeout=timeout)

    def update_task_fields(
        self,
        task_id: int,
        changes: dict,
        *,
        allow_rule_change: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """Guarded v1 read-modify-write: GET the task, merge ``changes``, POST.

        Kept only as the v1 full-echo fallback; :meth:`patch_task` is the
        write path. Defeats the v1 POST-partial-replace zeroing quirk (a v1
        ``POST /tasks/{id}`` zeroes any field the body omits, #524) by
        echoing every current field back
        alongside ``changes``, so ``repeat``, ``repeats_from_current_date``,
        ``reminders`` and any other unspecified field survive the write.

        **Guard** (post-plan review finding 10): when the current task has a
        rule, ``repeats_from_current_date=True`` or non-empty reminders, and
        the merged body would drop or alter any of them (``same_rule`` false,
        a changed ``repeats_rrule`` text, a changed flag, or different
        reminders), it raises ``ValueError`` before the POST unless
        ``allow_rule_change=True``.

        Args:
            task_id: Vikunja task id.
            changes: Fields to override on top of the current task state.
            allow_rule_change: Explicit override of the guard.
            timeout: Optional per-call timeout override (applied to both
                the GET and the POST).

        Returns:
            The parsed POST response body.

        Raises:
            ValueError: The guard refused a destructive change.
            VikunjaError: If the GET response body is not a JSON object
                (contract violation — nothing to merge onto).
        """
        current = self.get_task(task_id, timeout=timeout)
        if not isinstance(current, dict):
            raise VikunjaError(path=f"/tasks/{task_id}", status=200)
        merged = dict(current)
        merged.update(changes)
        if not allow_rule_change:
            altered = _altered_rule_fields(current, merged, changes)
            if altered:
                raise ValueError(
                    f"update_task_fields would drop or alter {', '.join(altered)} "
                    f"on task {task_id}; pass allow_rule_change=True to override"
                )
        return self.post(f"/tasks/{task_id}", json=merged, timeout=timeout)

    def create_task_in_project(
        self, project_id: int, body: dict, *, timeout: float | None = None
    ) -> Any:
        """PUT ``body`` to ``/projects/{project_id}/tasks`` — create a task.

        Used by ``security/credential_health_check/vikunja_writer.py``, which
        creates tasks via ``PUT /projects/{id}/tasks`` (Vikunja's v1
        task-create verb — PUT, not POST). A recurring task is created with
        :meth:`create_task_v2` instead (``vikunja/create_task.py``).
        """
        return self.put(f"/projects/{project_id}/tasks", json=body, timeout=timeout)

    def create_comment(
        self, task_id: int, comment: str, *, timeout: float | None = None
    ) -> Any:
        """Create a comment on a task via ``PUT /tasks/{task_id}/comments``.

        Vikunja's comment-create endpoint is PUT, not POST (the "G4" gotcha
        documented in ``docs/design/research/vikunja-task-model-research.md``
        and relied on by ``habits/record_completion.py`` and
        ``enrichment/record_completion.py``). Passing POST here would be
        wrong, not merely inconsistent.
        """
        return self.put(
            f"/tasks/{task_id}/comments", json={"comment": comment}, timeout=timeout
        )

    def list_task_comments(
        self, task_id: int, *, timeout: float | None = None
    ) -> Any:
        """GET the list of comments on a task.

        Used by ``habits/exclude_completed.py``,
        ``enrichment/reconcile_completions.py``, and
        ``habits/backfill_jsonl_from_comments.py`` to parse ``[Felix] ...``
        completion comments.
        """
        return self.get(f"/tasks/{task_id}/comments", timeout=timeout)

    # ------------------------------------------------------------------
    # v2 seam (mission felix-rrule-adaptation-01M7TKNX, WP02)
    # ------------------------------------------------------------------

    def _request_v2(
        self,
        method: str,
        path: str,
        *,
        permission: str,
        params: dict[str, str] | None = None,
        json_body: dict | None = None,
        content_type: str = _JSON_CONTENT_TYPE,
        allow_not_modified: bool = False,
        timeout: float | None = None,
    ) -> Any:
        return self._request(
            method,
            path,
            params=params,
            json_body=json_body,
            timeout=timeout,
            api_root=self.v2_base_url,
            content_type=content_type,
            allow_not_modified=allow_not_modified,
            permission=permission,
        )

    @staticmethod
    def _expect_dict(result: Any, path: str) -> dict:
        if not isinstance(result, dict):
            raise VikunjaServerError(path=path, status=200, detail="v2; not an object")
        return result

    def patch_task(
        self,
        task_id: int,
        changes: Mapping[str, Any],
        *,
        timeout: float | None = None,
        _allow_null: frozenset[str] = frozenset(),
    ) -> dict | None:
        """PATCH ``/api/v2/tasks/{id}`` with an RFC 7396 merge patch.

        Sends exactly ``changes`` with ``Content-Type:
        application/merge-patch+json`` (huma autopatch v2.40.0
        autopatch.go:345). Omitted fields survive.

        Raises ``ValueError`` before any network call when ``changes`` is
        empty, has a key outside :data:`WRITABLE_TASK_FIELDS`, or holds a
        ``None`` anywhere (a merge-patch ``null`` deletes the key, nested
        ones included).

        ``_allow_null`` is **internal**: only :meth:`end_series` and the WP10
        restore path pass it, naming top-level keys whose ``None`` value is a
        sanctioned delete. Even then ``{"repeat": None}`` may not share a
        body with ``done`` (that combination reopens the task, R-001 hazard 3).

        Returns:
            The task dict on 200, or ``None`` on 304 (no change; the server
            answers 304 with an empty body, autopatch.go:408-410).
        """
        _check_task_id(task_id)
        if not isinstance(changes, Mapping):
            raise TypeError("patch_task: changes must be a mapping")
        if not changes:
            raise ValueError("patch_task: changes must be non-empty")
        unknown = sorted(set(changes) - WRITABLE_TASK_FIELDS)
        if unknown:
            raise ValueError(f"patch_task: keys not writable: {unknown}")
        for key, value in changes.items():
            if value is None and key in _allow_null:
                continue
            found = _find_null(value, key)
            if found:
                raise ValueError(
                    f"patch_task: refusing null at {found} (a merge-patch null deletes it)"
                )
        if changes.get("repeat", ...) is None and "done" in changes:
            raise ValueError(
                "patch_task: clearing repeat and setting done in one body reopens the task"
            )
        path = f"/tasks/{task_id}"
        result = self._request_v2(
            "PATCH",
            path,
            permission="tasks.update",
            json_body=dict(changes),
            content_type=_MERGE_PATCH_CONTENT_TYPE,
            allow_not_modified=True,
            timeout=timeout,
        )
        if result is _NOT_MODIFIED:
            return None
        return self._expect_dict(result, path)

    def get_task_v2(self, task_id: int, *, timeout: float | None = None) -> dict:
        """GET ``/api/v2/tasks/{id}``; the body includes ``repeats_rrule``."""
        _check_task_id(task_id)
        path = f"/tasks/{task_id}"
        result = self._request_v2(
            "GET", path, permission="tasks.read_one", timeout=timeout
        )
        return self._expect_dict(result, path)

    def create_task_v2(
        self,
        project_id: int,
        fields: Mapping[str, Any],
        *,
        rrule: str | None = None,
        initial_due_time: str | None = None,
        timeout: float | None = None,
    ) -> dict:
        """POST ``/api/v2/projects/{id}/tasks``.

        Merges ``repeats_rrule`` and ``initial_due_time`` into the body when
        given. Refuses ``None`` values and a key given both in ``fields`` and
        as a keyword. Does **not** verify the stored rule; the caller asserts
        ``same_rule(created, expected)``.
        """
        _check_task_id(project_id, "project_id")
        if not isinstance(fields, Mapping):
            raise TypeError("create_task_v2: fields must be a mapping")
        body = dict(fields)
        for key, value in (("repeats_rrule", rrule), ("initial_due_time", initial_due_time)):
            if value is None:
                continue
            if key in body:
                raise ValueError(f"create_task_v2: {key} given twice")
            body[key] = value
        for key, value in body.items():
            found = _find_null(value, key)
            if found:
                raise ValueError(f"create_task_v2: refusing null at {found}")
        path = f"/projects/{project_id}/tasks"
        result = self._request_v2(
            "POST", path, permission="tasks.create", json_body=body, timeout=timeout
        )
        return self._expect_dict(result, path)

    def occurrences(
        self, task_id: int, *, count: int = 1, timeout: float | None = None
    ) -> dict:
        """GET ``/api/v2/tasks/{id}/occurrences?count=N`` (N in 1..100).

        Returns ``{"occurrences": [...], "reason"?: str}``. A 401 raises
        :class:`VikunjaAuthError` naming the ``tasks.occurrences``
        permission (R-004).
        """
        _check_task_id(task_id)
        _check_count(count)
        path = f"/tasks/{task_id}/occurrences"
        result = self._request_v2(
            "GET",
            path,
            permission="tasks.occurrences",
            params={"count": str(count)},
            timeout=timeout,
        )
        return self._expect_dict(result, path)

    def preview_occurrences(
        self,
        *,
        rrule: str | None = None,
        repeat: Mapping[str, Any] | None = None,
        due_date: str | None = None,
        initial_due_time: str | None = None,
        timezone: str = "America/New_York",
        repeats_from_current_date: bool = False,
        count: int = 3,
        timeout: float | None = None,
    ) -> dict:
        """POST ``/api/v2/tasks/occurrences/preview`` for an unsaved rule.

        Exactly one of ``rrule``/``repeat`` and exactly one of
        ``due_date``/``initial_due_time``, else ``ValueError`` before any
        call. A 400 raises :class:`VikunjaBadRequestError` with ``exc.code``
        2002 (invalid rule) or 2003 (invalid time zone); a 401 names the
        ``tasks.occurrences_preview`` permission.
        """
        if (rrule is None) == (repeat is None):
            raise ValueError("preview_occurrences: give exactly one of rrule, repeat")
        if (due_date is None) == (initial_due_time is None):
            raise ValueError(
                "preview_occurrences: give exactly one of due_date, initial_due_time"
            )
        _check_count(count)
        body: dict[str, Any] = {}
        if rrule is not None:
            body["repeats_rrule"] = rrule
        else:
            body["repeat"] = dict(repeat)  # type: ignore[arg-type]
        if due_date is not None:
            body["due_date"] = due_date
        else:
            body["initial_due_time"] = initial_due_time
        body["timezone"] = timezone
        body["repeats_from_current_date"] = bool(repeats_from_current_date)
        body["count"] = count
        path = "/tasks/occurrences/preview"
        result = self._request_v2(
            "POST",
            path,
            permission="tasks.occurrences_preview",
            json_body=body,
            timeout=timeout,
        )
        return self._expect_dict(result, path)

    def end_series(self, task_id: int, *, timeout: float | None = None) -> dict:
        """End a series: final state ``done=True`` with no rule, verified.

        Implements data-model.md "End-series recovery contract" from a fresh
        read, so it is resumable and idempotent:

        - open, rule: PATCH ``{"repeat": null}``, read back (a rule still
          present -> ``rule_reappeared``), then continue as open, no rule;
        - open, no rule: PATCH ``{"done": true}``, read back;
        - done, rule: PATCH ``{"repeat": null}`` (done unchanged, so it does
          not reopen), read back;
        - done, no rule: no-op.

        ``repeat`` and ``done`` never share a body: together they reopen the
        task (vikunja-harness d7e202228 ``pkg/models/tasks.go:1740-1760``).
        The final readback must show ``done is True`` and no rule, else
        ``not_ended``.

        Errors: a write whose outcome is **uncertain** (timeout, 5xx,
        transport failure, or an invalid 2xx response body, any of which can
        follow a write the server committed) re-reads once and decides from
        the fresh state; if that read fails too, ``unknown``. An uncertain
        write whose re-read shows nothing changed re-raises the original
        error (no partial progress). A definite refusal (4xx) of the first
        write propagates unchanged; any failure after the rule was cleared
        raises ``rule_cleared_not_done`` (chained).

        Raises:
            SeriesEndIncomplete: with ``state`` as above.
        """
        task = self._end_series_read(task_id, timeout)
        if _series_ended(task):
            return task

        rule_cleared = False
        if has_rule(task):
            try:
                self.patch_task(
                    task_id,
                    {"repeat": None},
                    timeout=timeout,
                    _allow_null=frozenset({"repeat"}),
                )
            except VikunjaError as exc:
                if not _write_outcome_uncertain(exc):
                    raise
                task = self._end_series_reread(task_id, timeout)
                if has_rule(task):
                    raise
            else:
                try:
                    task = self._end_series_read(task_id, timeout)
                except VikunjaError as exc:
                    raise SeriesEndIncomplete(task_id, "rule_cleared_not_done") from exc
                if has_rule(task):
                    raise SeriesEndIncomplete(task_id, "rule_reappeared")
            rule_cleared = True

        if task.get("done") is not True:
            try:
                self.patch_task(task_id, {"done": True}, timeout=timeout)
            except VikunjaError as exc:
                if not _write_outcome_uncertain(exc):
                    if rule_cleared:
                        raise SeriesEndIncomplete(
                            task_id, "rule_cleared_not_done"
                        ) from exc
                    raise
                task = self._end_series_reread(task_id, timeout)
                if not _series_ended(task):
                    if has_rule(task):
                        raise SeriesEndIncomplete(task_id, "rule_reappeared") from exc
                    if rule_cleared:
                        raise SeriesEndIncomplete(
                            task_id, "rule_cleared_not_done"
                        ) from exc
                    raise
            else:
                try:
                    task = self._end_series_read(task_id, timeout)
                except VikunjaError as exc:
                    raise SeriesEndIncomplete(task_id, "unknown") from exc

        if not _series_ended(task):
            if has_rule(task) and rule_cleared:
                raise SeriesEndIncomplete(task_id, "rule_reappeared")
            raise SeriesEndIncomplete(task_id, "not_ended")
        return task

    def _end_series_reread(self, task_id: int, timeout: float | None) -> dict:
        """Re-read once after an uncertain write; ``unknown`` if that fails."""
        try:
            return self._end_series_read(task_id, timeout)
        except VikunjaError as exc:
            raise SeriesEndIncomplete(task_id, "unknown") from exc

    def _end_series_read(self, task_id: int, timeout: float | None) -> dict:
        """``get_task_v2`` plus a strict shape check, so state reads cannot escape.

        A read whose recurrence shape is malformed or self-contradictory
        (:func:`_recurrence_shape_error`) raises :class:`VikunjaServerError`
        here, still inside ``end_series``'s recovery handling (review cycle 2;
        WP02 arbiter, tightened in WP08). Interpreting such a read would be a
        guess: ``repeat=[]`` beside ``repeats_rrule="FREQ=DAILY"`` would
        otherwise read as "no rule" and let a live series look ended. Later
        ``has_rule`` calls on the same dict are then safe.
        """
        task = self.get_task_v2(task_id, timeout=timeout)
        problem = _recurrence_shape_error(task)
        if problem is not None:
            raise VikunjaServerError(
                path=f"/tasks/{task_id}",
                status=None,
                detail=f"v2; malformed task ({problem})",
            )
        return task

    # ------------------------------------------------------------------
    # Private request execution + error mapping
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None,
        json_body: dict | None,
        timeout: float | None,
        api_root: str | None = None,
        content_type: str = _JSON_CONTENT_TYPE,
        allow_not_modified: bool = False,
        permission: str | None = None,
    ) -> Any:
        """Execute one request.

        The keyword-only extras are for the v2 seam and default to the v1
        behaviour: ``api_root`` (default ``base_url``), ``content_type`` for
        POST/PUT/PATCH, ``allow_not_modified`` (a 304 returns
        ``_NOT_MODIFIED`` instead of raising; urllib raises ``HTTPError`` for
        304) and ``permission`` (named in the message of a 401, and v2 error
        bodies are parsed for Vikunja's numeric ``code``).
        """
        is_v2 = api_root is not None
        url = self._compose_url(path, params, root=api_root)

        headers = {"Authorization": f"Bearer {self.token}"}
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
        # Per contract: Content-Type: application/json is method-driven.
        # POST, PUT, and PATCH always advertise a JSON content type, even
        # when the caller sends no body (e.g. bulk endpoints that take only
        # query parameters), so the server's content negotiation is
        # unambiguous.
        if method in ("POST", "PUT", "PATCH"):
            headers["Content-Type"] = content_type

        effective_timeout = timeout if timeout is not None else self.timeout
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as response:
                body = response.read()
                status = getattr(response, "status", None)
        except socket.timeout:
            raise VikunjaTimeoutError(path=path, status=None) from None
        except urllib.error.HTTPError as exc:
            if allow_not_modified and exc.code == 304:
                return _NOT_MODIFIED
            # Capture the raw error body for the adapter path (module
            # docstring "Return/error semantics") — never surfaced via
            # str(exc)/verbose_message(), only via exc.body.
            try:
                raw_error_body: str | None = exc.read().decode(
                    "utf-8", errors="replace"
                )
            except Exception:  # pragma: no cover — purely defensive
                raw_error_body = None
            if not is_v2:
                raise self._map_http_error(path, exc.code, body=raw_error_body) from None
            detail = "v2"
            if exc.code == 401 and permission:
                detail = f"v2; token may lack permission {permission}"
            raise self._map_http_error(
                path,
                exc.code,
                body=raw_error_body,
                detail=detail,
                code=_error_code(raw_error_body),
            ) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise VikunjaTimeoutError(path=path, status=None) from None
            raise VikunjaServerError(path=path, status=None) from None
        except Exception as exc:  # v2 closes the class; v1 re-raises
            # Any other failure while sending or reading: a truncated body
            # (http.client.IncompleteRead), a reset connection or TLS error
            # (OSError), a read on a closed file (ValueError), and so on.
            # v1 keeps its historical behaviour (the raw exception). v2 maps
            # every one to VikunjaServerError(status=None), so callers such
            # as end_series always see an uncertain write as a VikunjaError
            # (WP02 review cycles 1 and 2). A pre-send fault (bad URL or
            # header) would also land here, but the initial read in
            # end_series hits the same fault before any write is attempted.
            if not is_v2:
                raise
            raise VikunjaServerError(
                path=path, status=None, detail="v2; transport error"
            ) from exc

        if allow_not_modified and status == 304:
            return _NOT_MODIFIED
        # Per contract + data-model: empty-body successes (DELETE 204, etc.)
        # parse to an empty dict, not None. Callers that key into the result
        # then get a uniform mapping type.
        if not body:
            return {}
        if is_v2:
            try:
                return json.loads(body)
            except Exception as exc:  # every decoding failure
                # JSONDecodeError and UnicodeDecodeError (both ValueError),
                # LookupError, RecursionError on deep nesting, and anything
                # else json may raise: an undecodable body is a server fault
                # whose write may still have committed (review cycle 2).
                raise VikunjaServerError(
                    path=path,
                    status=None,
                    body=body.decode("utf-8", errors="replace"),
                    detail="v2; undecodable body",
                ) from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise VikunjaServerError(
                path=path, status=200, body=body.decode("utf-8", errors="replace")
            ) from None

    def _compose_url(
        self,
        path: str,
        params: dict[str, str] | None,
        *,
        root: str | None = None,
    ) -> str:
        """Compose the request URL, merging ``params`` with any embedded query string in ``path``.

        Callers occasionally pass paths that already contain a query string
        (e.g. ``"/projects/13/tasks?filter=done=true"``). Naive ``?`` appending
        would produce ``...?filter=done=true?per_page=200`` — the new param is
        swallowed into the prior value. Use ``urllib.parse`` to split the
        existing query, merge the caller's ``params`` dict, and re-encode.

        ``params`` provided to this method override any same-keyed value
        embedded in ``path``. ``root`` defaults to ``base_url`` (v1).
        """
        url = f"{root if root is not None else self.base_url}{path}"
        if not params:
            return url
        parsed = urllib.parse.urlparse(url)
        existing = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        merged: list[tuple[str, str]] = []
        override_keys = set(params.keys())
        for key, value in existing:
            if key not in override_keys:
                merged.append((key, value))
        for key, value in params.items():
            merged.append((key, value))
        new_query = urllib.parse.urlencode(merged)
        return urllib.parse.urlunparse(parsed._replace(query=new_query))

    @staticmethod
    def _map_http_error(
        path: str,
        status: int,
        *,
        body: str | None = None,
        detail: str | None = None,
        code: int | None = None,
    ) -> VikunjaHttpError:
        extra: dict[str, Any] = {"body": body, "detail": detail, "code": code}
        if status == 401:
            return VikunjaAuthError(path=path, status=status, **extra)
        if status == 404:
            return VikunjaNotFoundError(path=path, status=status, **extra)
        if status == 400:
            return VikunjaBadRequestError(path=path, status=status, **extra)
        if 500 <= status < 600:
            return VikunjaServerError(path=path, status=status, **extra)
        return VikunjaHttpError(path=path, status=status, **extra)


def _error_code(raw_body: str | None) -> int | None:
    """Vikunja's numeric ``code`` from a v2 error body, or None.

    v2 errors are RFC 9457 bodies extended with ``code``
    (vikunja-harness d7e202228 ``pkg/routes/api/v2/errors.go:116-121``).
    """
    if not raw_body:
        return None
    try:
        parsed = json.loads(raw_body)
    except Exception:  # noqa: BLE001 — the code is optional; never mask the HTTP error
        return None
    if not isinstance(parsed, dict):
        return None
    code = parsed.get("code")
    if isinstance(code, int) and not isinstance(code, bool):
        return code
    return None


def _find_null(value: Any, where: str) -> str | None:
    """Return the location of the first ``None`` inside *value*, or None."""
    if value is None:
        return where
    if isinstance(value, Mapping):
        for key, item in value.items():
            found = _find_null(item, f"{where}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _find_null(item, f"{where}[{index}]")
            if found:
                return found
    return None


def _check_count(count: Any) -> None:
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or not _OCCURRENCES_COUNT_MIN <= count <= _OCCURRENCES_COUNT_MAX
    ):
        raise ValueError(
            f"count must be an int in {_OCCURRENCES_COUNT_MIN}..{_OCCURRENCES_COUNT_MAX}, "
            f"got {count!r}"
        )


def _write_outcome_uncertain(exc: VikunjaError) -> bool:
    """True unless *exc* is a definite refusal (an HTTP 4xx status).

    Timeouts, 5xx, transport failures (``status=None``) and invalid 2xx
    bodies (``status=200``) can all follow a write the server committed.
    """
    status = exc.status
    return not (isinstance(exc, VikunjaHttpError) and status is not None and 400 <= status < 500)


def _recurrence_shape_error(task: Mapping[str, Any]) -> str | None:
    """Why a single-task v2 read's recurrence fields cannot be trusted, or None.

    The server's single-task read carries ``repeats_rrule`` as "the stored
    rule exactly; absent when the task does not repeat" (vikunja-harness
    d7e202228 pkg/routes/api/v2/tasks.go:156), beside the structured
    ``repeat`` (``omitempty``, tasks.go:97). So, strictly:

    - ``repeat`` is absent/``None`` or a mapping (never ``[]``, ``False``,
      ``0``, ``""`` or a string);
    - ``repeats_rrule`` is absent/``None`` or a string;
    - a non-empty ``repeats_rrule`` needs a ``repeat`` that is a rule, and
      the two must denote the same rule (:func:`same_rule`), unless the server
      marks the projection ``read_only`` (it cannot represent the stored
      rule, so only shape and presence are checked);
    - a ``repeat`` that is a rule needs a non-empty ``repeats_rrule``.
    """
    repeat = task.get("repeat")
    if repeat is not None and not isinstance(repeat, Mapping):
        return f"repeat is {type(repeat).__name__}, not an object"
    rrule = task.get("repeats_rrule")
    if rrule is not None and not isinstance(rrule, str):
        return f"repeats_rrule is {type(rrule).__name__}, not a string"
    try:
        rule_present = has_rule(task)
    except Exception as exc:  # noqa: BLE001 - any malformed part
        return f"repeat unreadable ({type(exc).__name__})"
    if rrule:
        if not rule_present:
            return "repeats_rrule set but repeat is not a rule"
        if repeat.get("read_only") is True:  # type: ignore[union-attr]
            # The server marks a projection that cannot hold the stored rule
            # (BYEASTER, a CalDAV DTSTART): "Such a rule cannot be edited
            # through the structured form; it can be replaced or cleared
            # through repeats_rrule on v2, or removed with repeat: null"
            # (d7e202228 pkg/models/task_repeat.go:63, set by projectionLoses
            # at :449). Text and projection legitimately differ, and the text
            # may hold parts the local parser does not know: shape and
            # presence are checked above, equality is not.
            return None
        try:
            parts = rrule_text_to_parts(rrule)
        except ValueError as exc:
            return f"repeats_rrule unparseable ({exc})"
        if not same_rule(parts, repeat):
            return "repeats_rrule and repeat disagree"
    elif rule_present:
        return "repeat is a rule but repeats_rrule is missing"
    return None


def _series_ended(task: Mapping[str, Any]) -> bool:
    return task.get("done") is True and not has_rule(task)


def _altered_rule_fields(
    current: Mapping[str, Any], merged: Mapping[str, Any], changes: Mapping[str, Any]
) -> list[str]:
    """Rule-bearing fields a full-echo write would drop or alter (guard)."""
    protected = (
        has_rule(current)
        or current.get("repeats_from_current_date") is True
        or bool(current.get("reminders"))
    )
    if not protected:
        return []
    altered: list[str] = []
    if not same_rule(current.get("repeat"), merged.get("repeat")):
        altered.append("repeat")
    if "repeats_rrule" in changes and changes["repeats_rrule"] != current.get(
        "repeats_rrule"
    ):
        altered.append("repeats_rrule")
    if bool(current.get("repeats_from_current_date")) != bool(
        merged.get("repeats_from_current_date")
    ):
        altered.append("repeats_from_current_date")
    if (current.get("reminders") or []) != (merged.get("reminders") or []):
        altered.append("reminders")
    return altered


def _check_task_id(task_id: Any, name: str = "task_id") -> None:
    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise ValueError(f"{name} must be a positive int, got {task_id!r}")
