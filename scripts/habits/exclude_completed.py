#!/usr/bin/env python3
"""Filter out habits already addressed today by parsing Vikunja completion comments.

Mission #282 / FR-004. Part of the felix-admin-habits Steps 1-4 refactor
(per Constitution Directive 6 and `docs/design/helper-script-conventions.md`).

This helper exists because the agent's prompt previously encoded the
`[Felix] YYYY-MM-DD | state | optional note` comment-format parser inline
— a high-criticality block (wrong filter → duplicate check-ins to Kent's
WhatsApp for habits already done) that's format-sensitive and
hallucination-prone in-prompt.

For each habit ID, the helper:
  1. GETs the habit's comments from Vikunja
  2. Parses comments matching the `[Felix]` format
  3. Determines if any matching comment with today's date addresses the habit
     (state ∈ {complete, rescheduled, will-not-do})
  4. If multiple matching comments exist for today, picks the one with the
     highest comment_id ("most recent wins")
  5. Returns the habit ID list partitioned into ready_for_checkin and
     already_addressed

Comment format (canonical):

    [Felix] YYYY-MM-DD | state | optional note

State lexicon (case-insensitive match, lowercase output):
  - complete
  - rescheduled
  - will-not-do

A `[Felix]` comment with any OTHER state is treated as malformed: emit
WARN to stderr and skip (habit remains ready for checkin). Non-Felix
comments are skipped silently.

Invocation:

    python3 scripts/habits/exclude_completed.py \\
        --habit-ids 123,124,125 \\
        --today 2026-05-15 \\
        [--vikunja-token-path /data/services/openclaw/secrets/vikunja-api] \\
        [--vikunja-base-url https://office2.tail0f5f56.ts.net/api/v1]

Output (stdout):

    {"ready_for_checkin": [123, 124], "already_addressed": [{"id": 125, "state": "complete", "comment_id": 9876}], "total_checked": 3}
    SUMMARY: total=3 ready=2 addressed=1 complete=1 rescheduled=0 will-not-do=0

Exit codes:
    0 — success (any subset, including all-addressed)
    1 — operational error (Vikunja unreachable, comment fetch failed)
    2 — usage error (malformed --today, malformed habit IDs)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
DEFAULT_BASE_URL = "https://office2.tail0f5f56.ts.net/api/v1"

# Acceptable state values (lowercase). Other states in well-formed Felix
# comments are flagged as malformed and the habit is treated as ready.
ADDRESSED_STATES = frozenset({"complete", "rescheduled", "will-not-do"})

# Validation: --today must be YYYY-MM-DD format.
TODAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Felix comment shape:
#   [Felix] YYYY-MM-DD | state | optional note
#   - state is alphanumeric + hyphen (e.g., "will-not-do")
#   - optional note is everything after the third pipe
FELIX_COMMENT_PATTERN = re.compile(
    r"^\[Felix\]\s+(?P<date>\d{4}-\d{2}-\d{2})\s+\|\s+(?P<state>[\w-]+)"
    r"(?:\s+\|\s+(?P<note>.*))?$",
    re.MULTILINE,
)


def _load_token(path: Path) -> str:
    """Read Vikunja API token from a mode-600 file."""
    return path.read_text(encoding="utf-8").strip()


def _http_get(base_url: str, token: str, path: str, timeout: int = 15) -> object:
    """GET request to Vikunja with bearer-style auth. Returns parsed JSON."""
    req = urllib.request.Request(
        f"{base_url}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_felix_comment(comment_text: str) -> tuple[str, str, str | None] | None:
    """Return (date, state, note_or_none) if comment matches the Felix shape, else None.

    State is lowercased. Caller decides whether the state is in ADDRESSED_STATES
    (treat as addressed) or out-of-vocab (treat as malformed).
    """
    if not isinstance(comment_text, str) or not comment_text.strip():
        return None
    m = FELIX_COMMENT_PATTERN.search(comment_text.strip())
    if not m:
        return None
    return m.group("date"), m.group("state").lower(), m.group("note")


def find_addressed_state(
    comments: list[dict],
    today: str,
    habit_id: int,
) -> dict | None:
    """Scan a habit's comments for an addressed-today entry; return the most-recent.

    Returns {"id": habit_id, "state": state, "comment_id": comment_id} or None.
    Emits WARN to stderr for malformed `[Felix]` comments. Non-Felix comments
    are skipped silently.
    """
    best: dict | None = None  # the highest comment_id matching an addressed state
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        text = comment.get("comment", "")
        comment_id = comment.get("id")
        # Quick filter: if it doesn't start with [Felix], skip silently.
        if not isinstance(text, str) or not text.strip().startswith("[Felix]"):
            continue
        parsed = parse_felix_comment(text)
        if parsed is None:
            # Starts with [Felix] but doesn't parse — malformed.
            print(
                f"WARN: habit {habit_id} comment {comment_id} has malformed "
                f"[Felix] format; treated as not-addressed",
                file=sys.stderr,
            )
            continue
        date, state, _note = parsed
        if date != today:
            continue
        if state not in ADDRESSED_STATES:
            # Felix-formatted but unknown state — malformed.
            print(
                f"WARN: habit {habit_id} comment {comment_id} has unknown "
                f"state {state!r}; expected one of {sorted(ADDRESSED_STATES)}",
                file=sys.stderr,
            )
            continue
        # Match. Keep the highest comment_id (most recent).
        if best is None or (
            isinstance(comment_id, int)
            and isinstance(best.get("comment_id"), int)
            and comment_id > best["comment_id"]
        ):
            best = {"id": habit_id, "state": state, "comment_id": comment_id}
    return best


def parse_habit_ids(comma_separated: str) -> list[int]:
    """Parse comma-separated string of integer IDs. Returns empty list for empty input."""
    if not comma_separated.strip():
        return []
    parts = [p.strip() for p in comma_separated.split(",") if p.strip()]
    return [int(p) for p in parts]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", maxsplit=1)[0],
    )
    parser.add_argument(
        "--habit-ids",
        type=str,
        required=True,
        help="Comma-separated integer habit IDs (e.g., 123,124,125). Empty allowed.",
    )
    parser.add_argument(
        "--today",
        type=str,
        required=True,
        help="Today's date in YYYY-MM-DD (Eastern time)",
    )
    parser.add_argument(
        "--vikunja-token-path",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help="Path to the Vikunja API token (mode-600 file)",
    )
    parser.add_argument(
        "--vikunja-base-url",
        type=str,
        default=DEFAULT_BASE_URL,
        help="Vikunja API base URL",
    )
    args = parser.parse_args(argv)

    if not TODAY_PATTERN.match(args.today):
        print(
            f"ERROR: --today must be YYYY-MM-DD; got {args.today!r}",
            file=sys.stderr,
        )
        return 2

    try:
        habit_ids = parse_habit_ids(args.habit_ids)
    except ValueError as exc:
        print(f"ERROR: --habit-ids parse failure: {exc}", file=sys.stderr)
        return 2

    if not habit_ids:
        result = {"ready_for_checkin": [], "already_addressed": [], "total_checked": 0}
        print(json.dumps(result))
        print("SUMMARY: total=0 ready=0 addressed=0 complete=0 rescheduled=0 will-not-do=0")
        return 0

    try:
        token = _load_token(args.vikunja_token_path)
    except FileNotFoundError:
        print(
            f"ERROR: Vikunja token file not found: {args.vikunja_token_path}",
            file=sys.stderr,
        )
        return 1
    except PermissionError:
        print(
            f"ERROR: permission denied reading Vikunja token: "
            f"{args.vikunja_token_path}",
            file=sys.stderr,
        )
        return 1

    ready: list[int] = []
    addressed: list[dict] = []
    state_counts = {"complete": 0, "rescheduled": 0, "will-not-do": 0}

    for habit_id in habit_ids:
        try:
            comments = _http_get(
                args.vikunja_base_url,
                token,
                f"/tasks/{habit_id}/comments",
            )
        except urllib.error.URLError as exc:
            print(f"ERROR: failed to fetch comments for habit {habit_id}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(comments, list):
            print(
                f"ERROR: unexpected comments response shape for habit {habit_id}: "
                f"{type(comments).__name__}",
                file=sys.stderr,
            )
            return 1
        match = find_addressed_state(comments, args.today, habit_id)
        if match is None:
            ready.append(habit_id)
        else:
            addressed.append(match)
            state_counts[match["state"]] += 1

    ready.sort()

    result = {
        "ready_for_checkin": ready,
        "already_addressed": addressed,
        "total_checked": len(habit_ids),
    }
    print(json.dumps(result))
    print(
        f"SUMMARY: total={len(habit_ids)} ready={len(ready)} addressed={len(addressed)} "
        f"complete={state_counts['complete']} rescheduled={state_counts['rescheduled']} "
        f"will-not-do={state_counts['will-not-do']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
