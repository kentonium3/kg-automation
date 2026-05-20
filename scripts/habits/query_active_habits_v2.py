#!/usr/bin/env python3
"""Phase 5 cutover variant of query_active_habits with a client-side filter.

Replaces the comment-parsing / day-of-week descriptor approach of the v1
sibling (``scripts/habits/query_active_habits.py``) with a project-scoped
task enumeration + a Python-side filter equivalent to
``due_date <= <today>T23:59:59Z AND done == false``. The v1 sibling
continues to drive the felix-admin-habits cron until Phase 5 cutover
(#308); both files coexist until then.

The helper:
  1. Reads the Vikunja API token from a mode-600 file
  2. Resolves the "Habits" project by title (mirroring the v1 sibling +
     ``reconcile_completions.py`` — no hardcoded project ID)
  3. Calls ``GET /projects/<id>/tasks`` (no server-side filter) and
     applies the equivalent filter in Python over the returned task list
  4. Returns the list of matching task dicts on stdout as JSONL

Why client-side filter: Vikunja v0.24.6 rejects the compound server-side
expression ``due_date <= <iso> AND done = false`` with HTTP 400 — see G7
in ``docs/design/research/vikunja-task-model-research.md``. The
client-side workaround mirrors the G6 (#333) fix in
``reconcile_completions.py``.

Scoping the enumeration to the Habits project is essential: a
cross-project enumeration via ``/tasks/all`` would let non-habit tasks
(Inbox, Goals, recurring meetings) leak into the Phase 5 check-in flow.

See contracts/api.md + contracts/cli.md for the contract.

Invocation::

    python3 -m scripts.habits.query_active_habits_v2 \\
        [--today YYYY-MM-DD] \\
        [--token-file /data/services/openclaw/secrets/vikunja-api] \\
        [--base-url http://100.92.197.90:3456/api/v1/]

Output (stdout): one JSON object per active habit task, newline-delimited.

Exit codes (per contracts/cli.md):
    0 -- success (empty result OK)
    1 -- Vikunja API failure
    2 -- usage error (bad --today value)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Default Vikunja API base. Tailscale IP keeps the helper functional
#: without DNS resolution of the public hostname.
DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"

#: Default location of the felix-bot Vikunja API token on office2 (mode 0600).
DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"

#: HTTP socket timeout in seconds for every Vikunja API call.
HTTP_TIMEOUT_SECONDS = 30

#: Title of the Vikunja project holding all habit tasks. Enumeration is
#: scoped to this project so non-habit tasks cannot leak into the result
#: even if they match the native filter expression.
HABITS_PROJECT_TITLE = "Habits"

#: Regex for the --today flag (ISO-8601 date).
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _join_url(base: str, path: str) -> str:
    if not base.endswith("/"):
        base = base + "/"
    return base + path.lstrip("/")


def _http_get(url: str, token: str) -> tuple[int, Any]:
    """GET request to Vikunja with bearer auth. Returns (status, parsed_json).

    Raises:
        OSError: On network failure, non-2xx status, or non-JSON body.
    """
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover -- defensive
            err_body = ""
        raise OSError(
            f"GET {url} failed with HTTP {e.code}: {err_body!r}"
        ) from e
    except urllib.error.URLError as e:
        raise OSError(f"GET {url} network failure: {e}") from e

    if status < 200 or status >= 300:
        raise OSError(f"GET {url} returned HTTP {status}: {raw!r}")

    parsed: Any = None
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise OSError(
                f"GET {url} returned non-JSON body: {raw!r} ({e})"
            ) from e
    return status, parsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_habits_project_id(api_base_url: str, token: str) -> int:
    """Resolve the Vikunja project id of the Habits project by title.

    Mirrors ``scripts/habits/query_active_habits.py::find_habits_project_id``
    and ``scripts/habits/reconcile_completions.py::_resolve_habits_project_id``
    so all three helpers locate the project the same way (no hardcoded ID).

    Raises:
        OSError: On network/HTTP failure or if no project titled
            ``HABITS_PROJECT_TITLE`` is found.
    """
    url = _join_url(api_base_url, "projects")
    _status, payload = _http_get(url, token)
    if not isinstance(payload, list):
        raise OSError(
            f"GET {url} returned non-list payload "
            f"(got {type(payload).__name__})"
        )
    for project in payload:
        if (
            isinstance(project, dict)
            and project.get("title") == HABITS_PROJECT_TITLE
        ):
            project_id = project.get("id")
            if isinstance(project_id, int):
                return project_id
            raise OSError(
                f"Project {HABITS_PROJECT_TITLE!r} found but has no integer "
                f"id: {project!r}"
            )
    raise OSError(
        f"No project titled {HABITS_PROJECT_TITLE!r} found in Vikunja"
    )


def _today_utc() -> str:
    """Today's date in UTC as ``YYYY-MM-DD``."""
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_active_today(
    api_base_url: str,
    token: str,
    today: str | None = None,
) -> list[dict]:
    """Return habit tasks active for today via a project-scoped client-side filter.

    Fetches all habit tasks in the Habits project (no server-side filter)
    and filters client-side for ``done == False`` AND
    ``due_date <= <today>T23:59:59Z``. The native server-side filter
    pattern (``due_date <= <iso> AND done = false``) is rejected by
    Vikunja v0.24.6 with HTTP 400 — see G7 in
    ``docs/design/research/vikunja-task-model-research.md``. The
    client-side workaround mirrors the G6 (#333) fix in
    ``reconcile_completions.py``.

    See ``contracts/api.md`` for the full contract.

    Args:
        api_base_url: Vikunja API base URL.
        token: Vikunja bearer token (felix-bot per Phase 1).
        today: ISO-8601 date for the filter boundary. Defaults to UTC today.

    Returns:
        List of task dicts. Each dict contains at least ``id``, ``title``,
        ``due_date``, ``done``, ``repeat_after``, ``project_id``, ``labels``.
        Empty list if no habits are active.

    Raises:
        ValueError: If ``today`` is set but not YYYY-MM-DD.
        OSError: On Vikunja API failure (network, non-2xx HTTP, bad body,
            or Habits project not found).
    """
    today_date = today or _today_utc()
    if not _DATE_RE.match(today_date):
        raise ValueError(f"today {today_date!r} must match YYYY-MM-DD")

    project_id = _resolve_habits_project_id(api_base_url, token)
    url = _join_url(api_base_url, f"projects/{project_id}/tasks")
    _status, payload = _http_get(url, token)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise OSError(
            f"GET {url} returned non-list payload "
            f"(got {type(payload).__name__})"
        )

    # Client-side filter — mirror reconcile_completions.py G6 (#333) pattern.
    # Semantics match the rejected server-side filter
    # ``due_date <= <today>T23:59:59Z AND done = false``:
    #   - exclude tasks with ``done == True``
    #   - include tasks where ``due_date`` (string lex compare) is
    #     non-empty AND ``<= boundary``. Vikunja's unset-due-date
    #     sentinel ``"0001-01-01T00:00:00Z"`` lex-compares less than the
    #     boundary, so unset-due-date tasks are INCLUDED (same behavior
    #     the server-side filter would have produced). An empty-string
    #     ``due_date`` (truly absent field) is excluded.
    boundary = f"{today_date}T23:59:59Z"
    out: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("done", False):
            continue
        due = item.get("due_date") or ""
        if not due or due > boundary:
            continue
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_token(token_file: Path) -> str:
    """Read a Vikunja API token from a mode-600 file.

    Raises:
        OSError: On missing / unreadable / empty token file.
    """
    try:
        content = token_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError as e:
        raise OSError(f"Token file not found: {token_file}") from e
    except PermissionError as e:
        raise OSError(
            f"Token file not readable (permission denied): {token_file}"
        ) from e
    except OSError as e:
        raise OSError(f"Could not read token file {token_file}: {e}") from e
    if not content:
        raise OSError(f"Token file is empty: {token_file}")
    return content


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = argparse.ArgumentParser(
        prog="query_active_habits_v2",
        description=(
            "Phase 5 cutover variant of query_active_habits. Enumerates the "
            "Habits project and applies a client-side filter equivalent to "
            "`due_date <= <today>T23:59:59Z AND done == false` (Vikunja "
            "v0.24.6 rejects the server-side form — see G7 in "
            "vikunja-task-model-research.md). Emits one JSON object per "
            "active task on stdout (newline-delimited). Exits 0 on success "
            "(empty result OK), 1 on Vikunja API failure, 2 on usage error."
        ),
    )
    parser.add_argument(
        "--today",
        default=None,
        help=(
            "Override the filter date (ISO-8601 YYYY-MM-DD). Defaults to "
            "today's UTC date."
        ),
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path(DEFAULT_TOKEN_PATH),
        help=(
            "Path to the Vikunja API token file "
            f"(default: {DEFAULT_TOKEN_PATH})."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Vikunja API base URL (default: {DEFAULT_BASE_URL}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See contracts/cli.md for exit codes 0/1/2."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.today is not None and not _DATE_RE.match(args.today):
        print(
            f"ERROR: --today must match YYYY-MM-DD (got {args.today!r})",
            file=sys.stderr,
        )
        return 2

    try:
        token = _read_token(args.token_file)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    try:
        tasks = query_active_today(args.base_url, token, today=args.today)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ERROR: query failed: {e}", file=sys.stderr)
        return 1

    out = sys.stdout
    for task in tasks:
        out.write(json.dumps(task, ensure_ascii=False, sort_keys=False))
        out.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
