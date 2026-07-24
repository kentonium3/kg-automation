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
Constants: ``DEFAULT_TOKEN_PATH``, ``DEFAULT_TIMEOUT``
Exceptions: ``VikunjaError``, ``VikunjaHttpError``, ``VikunjaAuthError``,
    ``VikunjaNotFoundError``, ``VikunjaBadRequestError``,
    ``VikunjaServerError``, ``VikunjaTimeoutError``
Class: ``VikunjaClient``

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
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_TOKEN_PATH",
    "DEFAULT_TIMEOUT",
    "VikunjaError",
    "VikunjaHttpError",
    "VikunjaAuthError",
    "VikunjaNotFoundError",
    "VikunjaBadRequestError",
    "VikunjaServerError",
    "VikunjaTimeoutError",
    "VikunjaClient",
]

DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
DEFAULT_TIMEOUT = 30.0

_BASE_URL_PATTERN = re.compile(r"^https?://[^/]+/api/v1$")


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
        self, path: str, status: int | None = None, *, body: str | None = None
    ) -> None:
        self.path = path
        self.status = status
        #: Raw response body text, when captured (adapter path — see the
        #: module-level "Return/error semantics" note). Never included in
        #: ``str(exc)`` or :meth:`verbose_message`; a WP migrating a raw
        #: consumer reads this directly when it must reconstruct raw-style
        #: error detail.
        self.body = body
        super().__init__(f"{type(self).__name__}: {path}")

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
        self.token = token
        self.timeout = float(timeout)

    @staticmethod
    def _load_default_token() -> str:
        try:
            return DEFAULT_TOKEN_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(
                f"Vikunja token file {DEFAULT_TOKEN_PATH} could not be read: {exc}"
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

    def replace_task_fields(
        self, task_id: int, body: dict, *, timeout: float | None = None
    ) -> Any:
        """POST ``body`` to ``/tasks/{task_id}`` verbatim — a raw **replace**.

        Vikunja v0.24.6 uses POST (not PATCH) for partial task field
        updates, and **zeroes any field not present in ``body``**
        server-side (the POST-partial-replace quirk — see
        ``habits/record_completion.py`` #524 for the reproducer). Use this
        method only when the caller deliberately wants replace semantics
        (e.g. ``habits/migrate_schedule.py`` narrow patch/retire/rollback
        bodies). Callers that need to preserve unspecified fields (like
        ``repeat_after``/``repeat_mode``) MUST use
        :meth:`update_task_fields` instead — the two are kept intentionally
        distinct (see module docstring "Risks": do not collapse into one
        generic partial-update method).
        """
        return self.post(f"/tasks/{task_id}", json=body, timeout=timeout)

    def update_task_fields(
        self, task_id: int, changes: dict, *, timeout: float | None = None
    ) -> Any:
        """Safe read-modify-write update: GET the task, merge ``changes``, POST.

        Defeats the POST-partial-replace zeroing quirk (see
        :meth:`replace_task_fields`) by echoing every current field back
        alongside ``changes`` — so ``repeat_after``, ``repeat_mode``, and
        any other unspecified field survive the write. Mirrors
        ``habits/record_completion.py``'s GET-then-POST pattern.

        Args:
            task_id: Vikunja task id.
            changes: Fields to override on top of the current task state.
            timeout: Optional per-call timeout override (applied to both
                the GET and the POST).

        Returns:
            The parsed POST response body.

        Raises:
            VikunjaError: If the GET response body is not a JSON object
                (contract violation — nothing to merge onto).
        """
        current = self.get_task(task_id, timeout=timeout)
        if not isinstance(current, dict):
            raise VikunjaError(path=f"/tasks/{task_id}", status=200)
        merged = dict(current)
        merged.update(changes)
        return self.replace_task_fields(task_id, merged, timeout=timeout)

    def create_task_in_project(
        self, project_id: int, body: dict, *, timeout: float | None = None
    ) -> Any:
        """PUT ``body`` to ``/projects/{project_id}/tasks`` — create a task.

        Shared by ``habits/migrate_schedule.py`` and
        ``security/credential_health_check/vikunja_writer.py``, both of
        which create tasks via ``PUT /projects/{id}/tasks`` (Vikunja's
        task-create verb — PUT, not POST).
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
    ) -> Any:
        url = self._compose_url(path, params)

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
            headers["Content-Type"] = "application/json"

        effective_timeout = timeout if timeout is not None else self.timeout
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as response:
                body = response.read()
        except socket.timeout:
            raise VikunjaTimeoutError(path=path, status=None) from None
        except urllib.error.HTTPError as exc:
            # Capture the raw error body for the adapter path (module
            # docstring "Return/error semantics") — never surfaced via
            # str(exc)/verbose_message(), only via exc.body.
            try:
                raw_error_body: str | None = exc.read().decode(
                    "utf-8", errors="replace"
                )
            except Exception:  # pragma: no cover — purely defensive
                raw_error_body = None
            raise self._map_http_error(path, exc.code, body=raw_error_body) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise VikunjaTimeoutError(path=path, status=None) from None
            raise VikunjaServerError(path=path, status=None) from None

        # Per contract + data-model: empty-body successes (DELETE 204, etc.)
        # parse to an empty dict, not None. Callers that key into the result
        # then get a uniform mapping type.
        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise VikunjaServerError(
                path=path, status=200, body=body.decode("utf-8", errors="replace")
            ) from None

    def _compose_url(
        self, path: str, params: dict[str, str] | None
    ) -> str:
        """Compose the request URL, merging ``params`` with any embedded query string in ``path``.

        Callers occasionally pass paths that already contain a query string
        (e.g. ``"/projects/13/tasks?filter=done=true"``). Naive ``?`` appending
        would produce ``...?filter=done=true?per_page=200`` — the new param is
        swallowed into the prior value. Use ``urllib.parse`` to split the
        existing query, merge the caller's ``params`` dict, and re-encode.

        ``params`` provided to this method override any same-keyed value
        embedded in ``path``.
        """
        url = f"{self.base_url}{path}"
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
        path: str, status: int, *, body: str | None = None
    ) -> VikunjaHttpError:
        if status == 401:
            return VikunjaAuthError(path=path, status=status, body=body)
        if status == 404:
            return VikunjaNotFoundError(path=path, status=status, body=body)
        if status == 400:
            return VikunjaBadRequestError(path=path, status=status, body=body)
        if 500 <= status < 600:
            return VikunjaServerError(path=path, status=status, body=body)
        return VikunjaHttpError(path=path, status=status, body=body)
