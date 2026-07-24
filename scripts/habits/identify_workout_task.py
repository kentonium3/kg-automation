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
        [--token-file /data/services/openclaw/secrets/vikunja-api-kent] \\
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
from pathlib import Path
from typing import Any

from scripts.common.vikunja_client import (
    VikunjaClient,
    VikunjaError,
    VikunjaTimeoutError,
)
from scripts.common.vikunja_config import (
    get_vikunja_base_url,
    get_vikunja_token_path,
)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Sentinel; resolved at call-time via get_vikunja_base_url().
DEFAULT_BASE_URL: str = ""

#: Sentinel; resolved at call-time via get_vikunja_token_path().
DEFAULT_TOKEN_PATH: str = ""

#: The 8 known production habit task IDs as of Phase 3 (see spec.md).
DEFAULT_CANDIDATE_IDS: list[int] = [14, 15, 16, 17, 18, 19, 20, 65]

HTTP_TIMEOUT_SECONDS = 30

#: Regex used to identify the workout task by title (case-insensitive).
WORKOUT_TITLE_REGEX = re.compile(r"workout", re.IGNORECASE)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _get_task_or_oserror(client: VikunjaClient, task_id: int, url: str) -> Any:
    """GET one task via :meth:`VikunjaClient.get_task`, adapted to ``OSError``.

    Migrated onto the shared client (WP05, mission #860). The client raises
    typed :class:`~scripts.common.vikunja_client.VikunjaError` subclasses;
    this adapter re-raises as ``OSError`` so the pre-migration return/error
    contract (documented in this module's docstring: "Raises: OSError") is
    preserved verbatim for callers and tests.

    Raises:
        OSError: On network failure, HTTP error response, or timeout. The
            message includes the URL and — for HTTP errors — the status
            code, mirroring the original hand-rolled urllib message shape.
    """
    try:
        return client.get_task(task_id)
    except VikunjaTimeoutError as e:
        raise OSError(f"Timeout on GET {url}: {e}") from e
    except VikunjaError as e:
        if e.status is None:
            # Network-layer failure (URLError, not a timeout) — no HTTP
            # status to report.
            raise OSError(f"Network failure on GET {url}: {e}") from e
        # exc.body carries the raw (uncensored) response text, when
        # captured, mirroring the pre-migration message that surfaced the
        # HTTP status + body verbatim.
        raise OSError(f"HTTP {e.status} from {url}: {e.body!r}") from e


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

    # Migrated onto the shared client (WP05, mission #860) — one instance
    # reused across all candidate lookups, still one GET per candidate.
    client = VikunjaClient(base_url=api_base_url, token=token)

    matches: list[dict] = []
    for task_id in candidate_ids:
        url = f"{client.base_url}/tasks/{task_id}"
        payload: Any = _get_task_or_oserror(client, task_id, url)
        if not isinstance(payload, dict):
            raise OSError(
                f"Expected JSON object from {url}, got {type(payload).__name__}: {payload!r}"
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
        default=None,
        help=(
            "Path to the Vikunja API token file (default: resolved via "
            "VIKUNJA_TOKEN_PATH env or the kent-owned runtime credential)."
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
        token = _read_token(args.token_file or get_vikunja_token_path())
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
