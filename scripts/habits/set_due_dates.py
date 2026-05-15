#!/usr/bin/env python3
"""Set Vikunja `due_date` to end-of-day Eastern Time on a list of habit IDs.

Mission #282 / FR-003. Part of the felix-admin-habits Steps 1-4 refactor
(per Constitution Directive 6 and `docs/design/helper-script-conventions.md`).

LOAD-BEARING for issue #112 regression-prevention. The bug fixed by #112:
habit due_dates anchored to UTC midnight caused them to appear overdue
the moment the morning cron fires at 7:05 AM ET. The fix is end-of-day-ET
(`23:59:59` with an explicit `-04:00` or `-05:00` offset), NOT UTC `Z`.

This helper rejects any `--iso-eod-et` value ending with `Z` (UTC) at
startup with exit code 2. The helper does NOT auto-convert UTC to ET —
auto-conversion was rejected during design as defeating the regression-
prevention guarantee.

Per-habit-failure resilience: if PUT fails on one habit, the helper
continues with the remaining habits, accumulates failures, and signals
partial-state via exit code 1 (non-zero) with a non-empty `succeeded`
array in the output. The calling agent's failure-handling clause uses
this signal to continue the check-in workflow with the succeeded subset.

Invocation:

    python3 scripts/habits/set_due_dates.py \\
        --habit-ids 123,124,125 \\
        --iso-eod-et 2026-05-15T23:59:59-04:00 \\
        [--vikunja-token-path /data/services/openclaw/secrets/vikunja-api] \\
        [--vikunja-base-url https://office2.tail0f5f56.ts.net/api/v1] \\
        [--dry-run]

Output (stdout):

    {"succeeded": [123, 124], "failed": [{"id": 125, "reason": "HTTP 500: ..."}]}
    SUMMARY: total=3 succeeded=2 failed=1

Exit codes:
    0 — all habits set successfully (or --dry-run completed)
    1 — at least one habit failed (partial state). `succeeded` may still be non-empty.
    2 — usage error (--iso-eod-et ends with Z, malformed timestamp, etc.)
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

# Required shape: YYYY-MM-DDT23:59:59<+/-NN:NN> — explicit ET offset, NOT 'Z'.
# This regex is the regression-prevention backstop for #112.
ISO_EOD_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T23:59:59[+-]\d{2}:\d{2}$")


def validate_iso_eod_et(value: str) -> str | None:
    """Return None if value is acceptable; else an error message describing why.

    The 'Z' suffix check is the critical #112 regression-prevention guard.
    """
    if value.endswith("Z"):
        return (
            "--iso-eod-et ends with 'Z' (UTC). Issue #112 forbids UTC due_date — "
            "must use explicit ET offset (-04:00 EDT or -05:00 EST). "
            "Helper does NOT auto-convert; reject and require correct input."
        )
    if not ISO_EOD_PATTERN.match(value):
        return (
            f"--iso-eod-et {value!r} does not match expected format "
            f"YYYY-MM-DDT23:59:59<+/-NN:NN>"
        )
    return None


def _load_token(path: Path) -> str:
    """Read Vikunja API token from a mode-600 file."""
    return path.read_text(encoding="utf-8").strip()


def _http_put(
    base_url: str,
    token: str,
    path: str,
    body: dict,
    timeout: int = 15,
) -> object:
    """PUT request to Vikunja with bearer auth. Returns parsed JSON response."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method="POST",  # Vikunja /tasks/{id} uses POST for partial updates
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        "--iso-eod-et",
        type=str,
        required=True,
        help=(
            "End-of-day-ET ISO timestamp (e.g., 2026-05-15T23:59:59-04:00). "
            "MUST NOT end with 'Z' (issue #112 regression-prevention)."
        ),
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually PUT; print what would happen. Makes NO HTTP calls.",
    )
    args = parser.parse_args(argv)

    # Critical: validate --iso-eod-et FIRST, before any HTTP setup.
    # This is the #112 regression-prevention guard.
    error = validate_iso_eod_et(args.iso_eod_et)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    try:
        habit_ids = parse_habit_ids(args.habit_ids)
    except ValueError as exc:
        print(f"ERROR: --habit-ids parse failure: {exc}", file=sys.stderr)
        return 2

    # Empty habit list is not an error — just nothing to do.
    if not habit_ids:
        result = {"succeeded": [], "failed": []}
        print(json.dumps(result))
        print("SUMMARY: total=0 succeeded=0 failed=0")
        return 0

    # Load token (skipped in --dry-run since we're not calling Vikunja)
    if args.dry_run:
        token = ""  # unused
    else:
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

    succeeded: list[int] = []
    failed: list[dict] = []
    body = {"due_date": args.iso_eod_et}

    for habit_id in habit_ids:
        if args.dry_run:
            print(
                f"INFO: [dry-run] would PUT habit {habit_id} due_date={args.iso_eod_et}",
                file=sys.stderr,
            )
            succeeded.append(habit_id)
            continue
        try:
            _http_put(
                args.vikunja_base_url,
                token,
                f"/tasks/{habit_id}",
                body,
            )
            succeeded.append(habit_id)
        except urllib.error.HTTPError as exc:
            reason = f"HTTP {exc.code}: {exc.reason}"
            print(f"ERROR: habit {habit_id} PUT failed: {reason}", file=sys.stderr)
            failed.append({"id": habit_id, "reason": reason})
        except urllib.error.URLError as exc:
            reason = f"URLError: {exc.reason}"
            print(f"ERROR: habit {habit_id} PUT failed: {reason}", file=sys.stderr)
            failed.append({"id": habit_id, "reason": reason})
        except Exception as exc:  # pragma: no cover — defensive
            reason = f"{type(exc).__name__}: {exc}"
            print(f"ERROR: habit {habit_id} PUT failed: {reason}", file=sys.stderr)
            failed.append({"id": habit_id, "reason": reason})

    result = {"succeeded": succeeded, "failed": failed}
    print(json.dumps(result))
    dry_marker = " (DRY-RUN)" if args.dry_run else ""
    print(
        f"SUMMARY: total={len(habit_ids)} succeeded={len(succeeded)} "
        f"failed={len(failed)}{dry_marker}"
    )

    # Partial-failure semantics: exit 1 if any habit failed (non-empty failed list).
    # This includes the case "0 succeeded, N failed" (total failure).
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
