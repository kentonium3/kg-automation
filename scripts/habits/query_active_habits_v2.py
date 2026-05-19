#!/usr/bin/env python3
"""Phase 5 cutover variant of query_active_habits using Vikunja-native filter.

Replaces the comment-parsing / day-of-week descriptor approach of the v1
sibling (``scripts/habits/query_active_habits.py``) with a single Vikunja
filter expression: ``due_date <= now/d AND done = false`` (FR-010). The
v1 sibling continues to drive the felix-admin-habits cron until Phase 5
cutover (#308); both files coexist until then.

The helper:
  1. Reads the Vikunja API token from a mode-600 file
  2. Resolves the "Habits" project by title (mirroring the v1 sibling +
     ``reconcile_completions.py`` — no hardcoded project ID)
  3. Calls ``GET /projects/<id>/tasks?filter=<expr>`` with the native
     filter expression
  4. Returns the list of matching task dicts on stdout as JSONL

Scoping the enumeration to the Habits project is essential: a
cross-project filter via ``/tasks/all`` would let non-habit tasks (Inbox,
Goals, recurring meetings) match the filter expression and leak into the
Phase 5 check-in flow.

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
import urllib.parse
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


def _build_filter_expression(today: str) -> str:
    """Build the Vikunja native filter expression for active-today habits.

    Per FR-010 / contracts/cli.md the filter is::

        due_date <= now/d AND done = false

    The ``now/d`` token is Vikunja's "today" shorthand — equivalent to
    ``today + 23:59:59Z`` in literal form. We pass ``now/d`` directly so
    Vikunja interprets it relative to its own clock (callers can override
    by passing ``today`` explicitly, which encodes a literal date instead).

    When ``today`` is an explicit ISO-8601 date, we emit a literal end-of-day
    timestamp so the comparison is unambiguous regardless of server timezone.
    """
    # Use literal end-of-day timestamp so tests + canary deploys see a
    # deterministic filter. ``now/d`` shorthand is documented in cli.md as
    # the equivalent form; we encode the literal expansion so callers with
    # an explicit ``today`` override get an exact date boundary.
    return f"due_date <= {today}T23:59:59Z AND done = false"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_active_today(
    api_base_url: str,
    token: str,
    today: str | None = None,
) -> list[dict]:
    """Return habit tasks active for today via Vikunja's native filter.

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
    filter_expr = _build_filter_expression(today_date)
    query = urllib.parse.urlencode({"filter": filter_expr})
    url = _join_url(api_base_url, f"projects/{project_id}/tasks?{query}")
    _status, payload = _http_get(url, token)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise OSError(
            f"GET {url} returned non-list payload "
            f"(got {type(payload).__name__})"
        )
    out: list[dict] = []
    for item in payload:
        if isinstance(item, dict):
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
            "Phase 5 cutover variant of query_active_habits using Vikunja's "
            "native filter expression `due_date <= now/d AND done = false`. "
            "Scoped to the Habits project. Emits one JSON object per active "
            "task on stdout (newline-delimited). Exits 0 on success (empty "
            "result OK), 1 on Vikunja API failure, 2 on usage error."
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
