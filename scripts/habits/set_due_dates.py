#!/usr/bin/env python3
"""Set Vikunja `due_date` to end-of-day Eastern Time on a list of habit IDs.

Each habit is written with a v2 merge patch that carries only `due_date`
(`VikunjaClient.patch_task`, #1111), so the recurrence rule survives; the
rule, the `repeats_from_current_date` flag and the reminder set are read
before and after the write and must be unchanged (`recurrence_drift`).

Mission #282 / FR-003. Part of the felix-admin-habits Steps 1-4 refactor
(per Constitution Directive 6 and `docs/design/helper-script-conventions.md`).
The former `--reconcile-schedule` mode was retired by #1111: the sweeper
moves day-specific habits by their own Vikunja rule, so a schedule-driven
reconcile is redundant.

LOAD-BEARING for issue #112 regression-prevention. The bug fixed by #112:
habit due_dates anchored to UTC midnight caused them to appear overdue
the moment the morning cron fires at 7:05 AM ET. The fix is end-of-day-ET
(`23:59:59` with an explicit `-04:00` or `-05:00` offset), NOT UTC `Z`.

This helper rejects any `--iso-eod-et` value ending with `Z` (UTC) at
startup with exit code 2. The helper does NOT auto-convert UTC to ET —
auto-conversion was rejected during design as defeating the regression-
prevention guarantee.

Per-habit-failure resilience: if the write fails on one habit, the helper
continues with the remaining habits, accumulates failures, and signals
partial-state via exit code 1 (non-zero) with a non-empty `succeeded`
array in the output. The calling agent's failure-handling clause uses
this signal to continue the check-in workflow with the succeeded subset.

Invocation:

    python3 scripts/habits/set_due_dates.py \\
        --habit-ids 123,124,125 \\
        --iso-eod-et 2026-05-15T23:59:59-04:00 \\
        [--vikunja-token-path /data/services/openclaw/secrets/vikunja-api-kent] \\
        [--vikunja-base-url <url>] \\
        [--dry-run]

Output (stdout):

    {"succeeded": [123, 124], "failed": [{"id": 125, "reason": "HTTP 500: ..."}]}
    SUMMARY: total=3 succeeded=2 failed=1

A habit whose rule, flag or reminders change across the write is reported in
`failed` with a `rule_changed: ...` reason.

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
from pathlib import Path

try:
    from scripts.common.vikunja_client import VikunjaClient, VikunjaError
    from scripts.common.vikunja_config import (
        get_vikunja_base_url,
        get_vikunja_token_path,
    )
    from scripts.common.vikunja_rule import recurrence_drift
except ImportError:
    # Fallback for direct-script invocation (`python3 scripts/habits/set_due_dates.py`).
    # Under that form only scripts/habits/ is on sys.path, so the absolute-package
    # import above fails. Insert the repo root (two levels up from scripts/habits/)
    # so that ``scripts.common.*`` resolves.
    # Precedent: scripts/openclaw/observation/summarize.py:36-38.
    import sys as _sys
    _repo_root = str(Path(__file__).resolve().parent.parent.parent)
    if _repo_root not in _sys.path:
        _sys.path.insert(0, _repo_root)
    from scripts.common.vikunja_client import (  # type: ignore[no-redef]
        VikunjaClient,
        VikunjaError,
    )
    from scripts.common.vikunja_config import (  # type: ignore[no-redef]
        get_vikunja_base_url,
        get_vikunja_token_path,
    )
    from scripts.common.vikunja_rule import (  # type: ignore[no-redef]
        recurrence_drift,
    )


#: Sentinel; resolved at call-time via get_vikunja_token_path().
DEFAULT_TOKEN_PATH: str = ""

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


def _format_vikunja_put_error(exc: VikunjaError) -> str:
    """Render a ``VikunjaClient`` exception as this module's write-failure reason string.

    Adapts the client's typed ``exc.status``/``exc.body`` (see the
    ``vikunja_client`` module docstring "Return/error semantics") into a
    short message compatible with this module's existing
    ``{"id": ..., "reason": ...}`` / ``{"error_type": "vikunja_put",
    "error_message": ...}`` shapes. HTTP-derived failures show status +
    captured body; network/timeout failures show the exception's redacted
    verbose form.
    """
    if exc.status is not None:
        return f"HTTP {exc.status}: {exc.body!r}"
    return exc.verbose_message()


def _set_due_date(client: VikunjaClient, habit_id: int, iso_eod_et: str) -> str | None:
    """Write one habit's ``due_date`` and verify its rule survived.

    Reads the v2 task, PATCHes only ``due_date`` (a 304 means it was already
    set), then reads back. Returns ``None`` on success, or a
    ``rule_changed: ...`` reason naming what :func:`recurrence_drift` found
    (rule, ``repeats_from_current_date``, reminders).

    Raises:
        VikunjaError: any client failure.
    """
    before = client.get_task_v2(habit_id)
    client.patch_task(habit_id, {"due_date": iso_eod_et})
    after = client.get_task_v2(habit_id)
    drift = recurrence_drift(before, after)
    if not drift:
        return None
    return f"rule_changed: {', '.join(drift)} changed across the due_date write"


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
        required=False,
        default=None,
        help=(
            "Comma-separated integer habit IDs (e.g., 123,124,125). Empty "
            "allowed. Required."
        ),
    )
    parser.add_argument(
        "--iso-eod-et",
        type=str,
        required=False,
        default=None,
        help=(
            "End-of-day-ET ISO timestamp (e.g., 2026-05-15T23:59:59-04:00). "
            "MUST NOT end with 'Z' (issue #112 regression-prevention). "
            "Required."
        ),
    )
    parser.add_argument(
        "--vikunja-token-path",
        type=Path,
        default=None,
        help="Path to the Vikunja API token (mode-600 file)",
    )
    parser.add_argument(
        "--vikunja-base-url",
        type=str,
        default=None,
        help="Vikunja API base URL (default: from vikunja_config helper)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually write; print what would happen. Makes NO HTTP calls.",
    )
    args = parser.parse_args(argv)
    # Lazy URL resolution: read from vikunja_config when not explicitly provided.
    if args.vikunja_base_url is None:
        args.vikunja_base_url = get_vikunja_base_url()

    if args.iso_eod_et is None or args.habit_ids is None:
        print(
            "ERROR: --iso-eod-et and --habit-ids are required",
            file=sys.stderr,
        )
        return 2

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
        result: dict[str, list] = {"succeeded": [], "failed": []}
        print(json.dumps(result))
        print("SUMMARY: total=0 succeeded=0 failed=0")
        return 0

    # Load token (skipped in --dry-run since we're not calling Vikunja)
    if args.dry_run:
        token = ""  # unused
    else:
        try:
            token = _load_token(args.vikunja_token_path or get_vikunja_token_path())
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
    client: VikunjaClient | None = None

    for habit_id in habit_ids:
        if args.dry_run:
            print(
                f"INFO: [dry-run] would set habit {habit_id} due_date={args.iso_eod_et}",
                file=sys.stderr,
            )
            succeeded.append(habit_id)
            continue
        try:
            if client is None:
                client = VikunjaClient(
                    base_url=args.vikunja_base_url, token=token, timeout=15
                )
            reason = _set_due_date(client, habit_id, args.iso_eod_et)
        except VikunjaError as exc:
            reason = _format_vikunja_put_error(exc)
        except Exception as exc:  # pragma: no cover — defensive
            reason = f"{type(exc).__name__}: {exc}"
        if reason is None:
            succeeded.append(habit_id)
            continue
        print(f"ERROR: habit {habit_id} write failed: {reason}", file=sys.stderr)
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
