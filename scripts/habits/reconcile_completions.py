#!/usr/bin/env python3
"""ADR-0002 Phase 3 reconcile_completions helper.

Reconciles the local JSONL state log against Vikunja's task state:

    Backfill direction: for every active habit task whose Vikunja ``done``
        is True, parse ``done_at`` -> UTC date string. If no JSONL entry
        exists for ``(task_id, date, state="complete")``, append a backfill
        record with ``source="vikunja-ui"`` (Kent ticked the task done in
        the Vikunja UI -- record_completion was never invoked).

    Drift direction: for every active habit task, if the JSONL has a
        ``state="complete"`` entry for ``today`` but Vikunja currently
        shows ``done=false``, report the drift on stdout. Drift is NOT
        auto-resolved -- it indicates a conflict between sources of truth.

Exit codes (per contracts/cli.md):
    0 -- reconcile completed (with OR without drift; drift is informational)
    1 -- unrecoverable Vikunja API failure (could not enumerate tasks)
    2 -- usage error (bad --today value, etc.)

Vikunja behaviors honored:
    - Zero-sentinel ``done_at``: Vikunja returns ``"0001-01-01T00:00:00Z"``
      for tasks with no completion timestamp set. Treat as "no date".
    - Enumeration is **project-scoped** to the Habits project: the helper
      resolves the project by title (mirroring
      ``scripts/habits/query_active_habits.py``) and calls
      ``GET /projects/<id>/tasks?filter=is_archived=false``. This is
      critical for FR-008 / Phase 2 state_log contract -- a cross-project
      ``/tasks/all`` enumeration would let non-habit completions (Inbox,
      Goals, etc.) leak into the habits JSONL during backfill.

Design references:
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/spec.md
        FR-008, FR-009, NFR-003, C-005, C-006.
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/{api,cli}.md
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/research.md
        D7 (drift handling), D6 (idempotency), D10 (gotchas).
    - scripts/common/state_log.py (Phase 2 library used for append/read).
    - scripts/habits/migrate_schedule.py (urllib HTTP pattern reference).
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

from scripts.common import state_log


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

#: Vikunja's "unset" sentinel value for ``done_at``. A literal 1AD timestamp.
ZERO_DATE_SENTINEL = "0001-01-01T00:00:00Z"

#: Title of the Vikunja project that holds all habit tasks. Enumeration is
#: scoped to this project so non-habit completions (Inbox, Goals, etc.)
#: cannot leak into the habits JSONL log during backfill (FR-008).
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


def _http_request(
    method: str,
    url: str,
    token: str,
) -> tuple[int, Any]:
    """Issue an authenticated HTTP request via urllib (no body)."""
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, headers=headers, method=method)
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
            f"{method} {url} failed with HTTP {e.code}: {err_body!r}"
        ) from e
    except urllib.error.URLError as e:
        raise OSError(f"{method} {url} network failure: {e}") from e

    if status < 200 or status >= 300:
        raise OSError(f"{method} {url} returned HTTP {status}: {raw!r}")

    parsed: Any = None
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise OSError(
                f"{method} {url} returned non-JSON body: {raw!r} ({e})"
            ) from e
    return status, parsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_habits_project_id(api_base_url: str, token: str) -> int:
    """Resolve the Vikunja project id of the Habits project by title.

    Mirrors ``scripts/habits/query_active_habits.py::find_habits_project_id``
    so both helpers locate the project the same way (no hardcoded ID).

    Returns:
        The integer project id.

    Raises:
        OSError: On network/HTTP failure or if no project titled
            ``HABITS_PROJECT_TITLE`` is found.
    """
    url = _join_url(api_base_url, "projects")
    _status, payload = _http_request("GET", url, token)
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


def _enumerate_active_habits(api_base_url: str, token: str) -> list[dict]:
    """Enumerate active tasks **in the Habits project only**.

    Scoping to the Habits project is essential: a cross-project enumeration
    via ``GET /tasks/all`` would let non-habit completions (Inbox, Goals,
    Recurring-events, etc.) be backfilled into the habits JSONL, violating
    FR-008 and the Phase 2 state_log contract (one domain per log).

    The helper:
      1. Resolves the Habits project id by title (no hardcoded id) --
         mirrors ``scripts/habits/query_active_habits.py``.
      2. Calls ``GET /projects/<id>/tasks`` and client-side filters
         on ``is_archived``. Per Verified API Gotcha G5
         (``docs/design/research/vikunja-task-model-research.md``),
         Vikunja v0.24.6's filter syntax does not accept
         ``is_archived`` as a filterable field — server-side filtering
         returns HTTP 400. Client-side filter is the workaround.

    Returns:
        List of task dicts (excluding archived ones). Empty list if
        the project has no active tasks.

    Raises:
        OSError: On network/HTTP failure, or if the Habits project cannot
            be resolved.
    """
    project_id = _resolve_habits_project_id(api_base_url, token)
    url = _join_url(api_base_url, f"projects/{project_id}/tasks")
    _status, payload = _http_request("GET", url, token)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise OSError(
            f"GET {url} returned non-list payload "
            f"(got {type(payload).__name__})"
        )
    out: list[dict] = []
    for item in payload:
        if isinstance(item, dict) and not item.get("is_archived", False):
            out.append(item)
    return out


def _done_at_date(task: dict) -> str | None:
    """Extract the UTC date portion of ``task["done_at"]``.

    Vikunja returns ``"0001-01-01T00:00:00Z"`` as a sentinel "unset" value
    -- treat as None. Empty strings / missing keys also map to None.

    Returns:
        ISO-8601 ``YYYY-MM-DD`` string, or ``None`` if no usable timestamp.
    """
    raw = task.get("done_at")
    if not raw or not isinstance(raw, str):
        return None
    if raw == ZERO_DATE_SENTINEL:
        return None
    # Accept the trailing ``Z`` form by normalizing to +00:00 for parsing.
    normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Assume UTC if no tz on a Vikunja timestamp.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date().isoformat()


def _now_iso() -> str:
    """Current UTC timestamp in ISO-8601 with offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_utc() -> str:
    """Today's date in UTC as ``YYYY-MM-DD``."""
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconcile(
    api_base_url: str,
    token: str,
    today: str | None = None,
) -> dict:
    """Enumerate active habits, backfill missing JSONL entries, report drift.

    See ``contracts/api.md`` for the full contract.

    Args:
        api_base_url: Vikunja API base URL.
        token: Vikunja bearer token (felix-bot per Phase 1).
        today: ISO-8601 date for the drift-detection comparison. Defaults
            to the current UTC date.

    Returns:
        Summary dict::

            {
                "tasks_examined": int,
                "backfilled": [
                    {"task_id": ..., "date": ..., "title": ..., ...},
                    ...
                ],
                "drift": [
                    {"task_id": ..., "title": ..., "date": ...},
                    ...
                ],
                "errors": [
                    {"task_id": ..., "message": ...},
                    ...
                ],
            }

    Raises:
        OSError: On unrecoverable Vikunja API failure (the helper could not
            enumerate tasks at all).
    """
    today_date = today or _today_utc()
    if not _DATE_RE.match(today_date):
        raise ValueError(
            f"today {today_date!r} must match YYYY-MM-DD"
        )

    tasks = _enumerate_active_habits(api_base_url, token)

    result: dict[str, Any] = {
        "tasks_examined": 0,
        "backfilled": [],
        "drift": [],
        "errors": [],
    }

    for task in tasks:
        result["tasks_examined"] += 1
        task_id = task.get("id")
        title = task.get("title") or ""
        if not isinstance(task_id, int) or task_id <= 0:
            # Defensive: skip malformed tasks rather than abort the run.
            result["errors"].append({
                "task_id": task_id,
                "message": "task missing or invalid 'id' field",
            })
            continue

        # Backfill direction: Vikunja says done=true but we may lack JSONL.
        if task.get("done") is True:
            done_date = _done_at_date(task)
            if done_date is None:
                result["errors"].append({
                    "task_id": task_id,
                    "title": title,
                    "message": (
                        "task done=true but done_at missing/invalid "
                        f"({task.get('done_at')!r})"
                    ),
                })
            else:
                try:
                    existing = state_log.read(
                        "habits",
                        task_id=task_id,
                        date=done_date,
                        state="complete",
                    )
                except OSError as e:
                    result["errors"].append({
                        "task_id": task_id,
                        "title": title,
                        "message": f"state_log read failed: {e}",
                    })
                    existing = ["sentinel"]  # avoid double-counting
                if not existing:
                    backfill_record = {
                        "domain": "habits",
                        "task_id": task_id,
                        "title": title,
                        "date": done_date,
                        "state": "complete",
                        "source": "vikunja-ui",
                        "timestamp": _now_iso(),
                    }
                    try:
                        state_log.append("habits", backfill_record)
                        result["backfilled"].append({
                            "task_id": task_id,
                            "title": title,
                            "date": done_date,
                            "source": "vikunja-ui",
                        })
                    except (OSError, ValueError) as e:
                        result["errors"].append({
                            "task_id": task_id,
                            "title": title,
                            "message": f"backfill append failed: {e}",
                        })

        # Drift direction: JSONL says complete for today but Vikunja says
        # done=false. Reported but never auto-resolved.
        try:
            today_records = state_log.read(
                "habits",
                task_id=task_id,
                date=today_date,
                state="complete",
            )
        except OSError as e:
            result["errors"].append({
                "task_id": task_id,
                "title": title,
                "message": f"state_log read failed: {e}",
            })
            today_records = []

        if today_records and task.get("done") is False:
            result["drift"].append({
                "task_id": task_id,
                "title": title,
                "date": today_date,
                "jsonl_state": "complete",
                "vikunja_done": False,
            })

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_token(token_file: Path) -> str:
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
        prog="reconcile_completions",
        description=(
            "ADR-0002 Phase 3 reconciliation helper. Enumerates active "
            "habit tasks, backfills JSONL entries for Vikunja-UI "
            "completions, and reports drift (JSONL says complete, "
            "Vikunja says done=false). Exits 0 regardless of drift "
            "count (drift is informational). Exits 1 on unrecoverable "
            "Vikunja API failure."
        ),
    )
    parser.add_argument(
        "--today",
        default=None,
        help=(
            "Override the drift-comparison date (ISO-8601 YYYY-MM-DD). "
            "Defaults to today's UTC date."
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


def _format_summary(result: dict, today: str) -> str:
    """Render the human-readable summary block for stdout."""
    lines: list[str] = []
    lines.append(f"=== reconcile_completions {_now_iso()} ===")
    lines.append(f"tasks_examined: {result['tasks_examined']}")
    lines.append(f"backfilled: {len(result['backfilled'])}")
    for entry in result["backfilled"]:
        lines.append(
            f"  - task_id={entry['task_id']} date={entry['date']} "
            f"source={entry['source']}"
        )
    lines.append(f"drift: {len(result['drift'])}")
    for entry in result["drift"]:
        title = entry.get("title") or ""
        lines.append(
            f"  - DRIFT: task_id={entry['task_id']} ({title}): "
            f"JSONL says complete for {entry['date']} but Vikunja shows "
            "done=false"
        )
    lines.append(f"errors: {len(result['errors'])}")
    for entry in result["errors"]:
        lines.append(
            f"  - task_id={entry.get('task_id')}: {entry.get('message')}"
        )
    return "\n".join(lines)


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
        result = reconcile(args.base_url, token, today=args.today)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ERROR: reconcile failed: {e}", file=sys.stderr)
        return 1

    today_used = args.today or _today_utc()
    print(_format_summary(result, today_used))
    # Drift is informational only -- always exit 0 when reconcile completed
    # (even if drift count > 0).
    return 0


if __name__ == "__main__":
    sys.exit(main())
