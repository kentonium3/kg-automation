#!/usr/bin/env python3
"""Identify the current "workout" habit task in Vikunja — ADR-0002 Phase 3.

One-shot lookup helper. Queries Vikunja for each of the known production
habit task IDs and returns the one whose title matches ``r"workout"``
(case-insensitive). The operator runs this once during Phase 3 pre-flight
to discover the workout task ID, then edits ``habits-schedule.yaml`` with
the result.

Read-only: this helper issues only ``GET /tasks/<id>`` calls. It never
writes anything to Vikunja.

Invocation:

    python3 -m scripts.habits.identify_workout_task \\
        [--token-file /data/services/openclaw/secrets/vikunja-api] \\
        [--base-url http://100.92.197.90:3456/api/v1/] \\
        [--candidate-ids 14,15,16,17,18,19,20,65]

Output (stdout):

    Single match — one JSON object describing the workout task:
        {"task_id": 17, "title": "Workout", "project_id": 1,
         "labels": ["personal"], "repeat_after": 0,
         "due_date": "2026-05-19T08:00:00Z"}

    No match — the literal token ``null``:
        null

Exit codes:
    0 — single match (or null reported clearly) — no error
    1 — multiple workout-like tasks found (operator must disambiguate)
    2 — I/O error (token file missing, network/HTTP failure, etc.)

Design references:
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/api.md
        (``find_workout_task`` signature)
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/cli.md
        (CLI surface, exit codes)
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/research.md
        (D1: per-helper urllib wrapper; D2: lookup-only operator helper)
    - scripts/vikunja/provision_felix_bot.py (canonical urllib pattern)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from scripts.common.vikunja_config import get_vikunja_base_url


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Sentinel; resolved at call-time via get_vikunja_base_url().
DEFAULT_BASE_URL: str = ""

#: Default location for the felix-bot Vikunja API token on office2 (mode 0600).
DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"

#: The 8 known production habit task IDs as of Phase 3 (see spec.md).
DEFAULT_CANDIDATE_IDS: list[int] = [14, 15, 16, 17, 18, 19, 20, 65]

HTTP_TIMEOUT_SECONDS = 30

#: Regex used to identify the workout task by title (case-insensitive).
WORKOUT_TITLE_REGEX = re.compile(r"workout", re.IGNORECASE)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _join_url(base: str, path: str) -> str:
    if not base.endswith("/"):
        base = base + "/"
    return base + path.lstrip("/")


def _http_get(url: str, token: str) -> tuple[int, str]:
    """Issue an authenticated GET to ``url`` via urllib.

    Args:
        url: Fully qualified URL.
        token: Bearer token (Vikunja API token).

    Returns:
        Tuple ``(status_code, body_text)``.

    Raises:
        OSError: On network failure, HTTP error response, or non-2xx status.
            The message includes the URL for triage.
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
        # Surface the HTTP status + body so a missing candidate ID is loud.
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise OSError(
            f"HTTP {e.code} from {url}: {body!r}"
        ) from e
    except urllib.error.URLError as e:
        raise OSError(f"Network failure on GET {url}: {e}") from e

    if status < 200 or status >= 300:
        raise OSError(f"HTTP {status} from {url}: {raw!r}")
    return status, raw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_workout_task(
    api_base_url: str,
    token: str,
    candidate_ids: list[int] | None = None,
) -> dict | None:
    """Find the current 'workout' habit task among known candidate IDs.

    Args:
        api_base_url: Vikunja API base
            (e.g., ``"http://100.92.197.90:3456/api/v1/"``).
        token: Vikunja API token (felix-bot or kent — read-only).
        candidate_ids: List of task IDs to search among.
            Default: ``[14, 15, 16, 17, 18, 19, 20, 65]``.

    Returns:
        Dict with keys ``{task_id, title, project_id, labels, repeat_after,
        due_date}`` for the matching task. ``None`` if no candidate's title
        matches the workout regex.

    Raises:
        OSError: On network or HTTP error.
        ValueError: If more than one candidate matches (operator must
            disambiguate manually).
    """
    if candidate_ids is None:
        candidate_ids = list(DEFAULT_CANDIDATE_IDS)

    matches: list[dict] = []
    for task_id in candidate_ids:
        url = _join_url(api_base_url, f"tasks/{task_id}")
        _status, raw = _http_get(url, token)
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as e:
            raise OSError(
                f"Non-JSON response from {url}: {raw!r}"
            ) from e
        if not isinstance(payload, dict):
            raise OSError(
                f"Expected JSON object from {url}, got {type(payload).__name__}: {raw!r}"
            )
        title = payload.get("title", "")
        if not isinstance(title, str):
            # Defensive: Vikunja should always return a string title.
            continue
        if WORKOUT_TITLE_REGEX.search(title):
            matches.append(
                {
                    "task_id": task_id,
                    "title": title,
                    "project_id": payload.get("project_id"),
                    "labels": payload.get("labels") or [],
                    "repeat_after": payload.get("repeat_after"),
                    "due_date": payload.get("due_date"),
                }
            )

    if len(matches) == 0:
        return None
    if len(matches) == 1:
        return matches[0]
    matched_ids = [m["task_id"] for m in matches]
    raise ValueError(
        f"Multiple workout-like tasks found: {matched_ids}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_candidate_ids(raw: str) -> list[int]:
    """Parse a comma-separated list of task IDs.

    Raises ``argparse.ArgumentTypeError`` on malformed input so argparse
    reports a clean usage error (exit 2) without a stack trace.
    """
    items = [p.strip() for p in raw.split(",") if p.strip()]
    if not items:
        raise argparse.ArgumentTypeError(
            "--candidate-ids must contain at least one integer"
        )
    out: list[int] = []
    for item in items:
        try:
            out.append(int(item))
        except ValueError as e:
            raise argparse.ArgumentTypeError(
                f"--candidate-ids contains non-integer {item!r}"
            ) from e
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="identify_workout_task",
        description=(
            "Locate the 'workout' habit task among the known production "
            "habit task IDs. Prints a JSON object on stdout (or null if no "
            "match). Read-only — issues only GET /tasks/<id> calls."
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
        default=None,
        help="Vikunja API base URL (default: from VIKUNJA_BASE_URL env or config file).",
    )
    parser.add_argument(
        "--candidate-ids",
        type=_parse_candidate_ids,
        default=list(DEFAULT_CANDIDATE_IDS),
        help=(
            "Comma-separated task IDs to search (default: "
            f"{','.join(str(i) for i in DEFAULT_CANDIDATE_IDS)})."
        ),
    )
    return parser


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    args.base_url = args.base_url or get_vikunja_base_url()

    # Read token (exit 2 on I/O error per CLI contract).
    try:
        token = _read_token(args.token_file)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(
        f"Searching for workout task among IDs: "
        f"{','.join(str(i) for i in args.candidate_ids)}",
        file=sys.stderr,
    )

    try:
        result = find_workout_task(
            api_base_url=args.base_url,
            token=token,
            candidate_ids=args.candidate_ids,
        )
    except ValueError as e:
        # Multiple matches — exit 1.
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        # Network / HTTP / file I/O — exit 2.
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if result is None:
        print("null")
        print("No workout task found among the candidate IDs.", file=sys.stderr)
        return 0

    print(json.dumps(result))
    print(
        f"Found workout task: id={result['task_id']} title={result['title']!r}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
