#!/usr/bin/env python3
"""One-shot cutover script for the #362 backlog replay.

Closes the 13 known pre-#362 ``[doc-audit]`` P3 issues, resets the
drift-events cursor (so the new Moment 0 pipeline reprocesses the
originating drift events on the next cron tick), and writes an
idempotency marker preventing accidental re-run.

This is **operator-run, once per deploy.** Subsequent runs are no-ops
(an idempotency marker at ``~/.config/doc-audit/cutover-362.done``
gates re-execution). The marker can be force-overridden via ``--force``
when the operator deliberately wants to re-attempt the cutover (e.g.,
the first run partial-closed a few issues and the operator wants the
remainder cleaned up).

CLI surface (per ``contracts/cli.md`` § cutover_362):

    python3 scripts/doc_audit/helpers/cutover_362.py [--dry-run] [--force]

Exit codes:

    0 — Success (or idempotent no-op)
    1 — GitHub API failure (gh list returned non-zero or unparseable)
    2 — Filesystem failure (cursor reset or marker write failed)
    3 — Bad CLI arguments (argparse error)

Importable surface (per ``contracts/api.md`` § cutover_362.run):

    from doc_audit.helpers.cutover_362 import run, CutoverResult

    result = run(dry_run=False, force=False)

Side effects in non-dry-run mode:

    1. Posts a closing comment + closes each open
       ``label:P3-candidate "[doc-audit]"`` issue on
       ``kentonium3/kg-automation``.
    2. Invokes ``handle_drift_events.py --reset-cursor`` to set the
       drift-events cursor back to ``0`` (so the new pipeline
       reprocesses the originating drift events on the next tick).
    3. Writes the idempotency marker to
       ``~/.config/doc-audit/cutover-362.done`` (atomic tempfile +
       rename) carrying the mission slug, mission id, run timestamp,
       closed issue numbers, and the cursor reset target.

Partial-close behavior: if an individual ``gh issue comment`` or
``gh issue close`` invocation fails, the script logs the failure and
continues with the remaining issues. The marker still records the
issues that *were* closed. The operator can re-run with ``--force`` to
clean up the stragglers.

No live GitHub calls are made in dry-run mode (only the ``gh issue
list`` query needs to know what would be closed, so the list query
remains so the operator can preview the impact).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

MARKER_PATH: Path = Path.home() / ".config" / "doc-audit" / "cutover-362.done"
"""Idempotency marker location. Absent on a fresh deploy; written on success."""

MISSION_SLUG: str = "drift-event-auto-resolution-01KS8J32"
"""Mission slug recorded in the marker for traceability."""

MISSION_ID: str = "01KS8J321F8KE7369R3DA02329"
"""Mission ULID recorded in the marker for traceability."""

REPO: str = "kentonium3/kg-automation"
"""GitHub repository slug used by ``gh issue list/comment/close``."""

GH_QUERY: str = 'is:issue is:open label:P3-candidate "[doc-audit]" in:title'
"""Search query matching the pre-#362 P3 candidate ``[doc-audit]`` issues."""

COMMENT_BODY: str = (
    "Closing as part of mission {mission_slug} (#362). "
    "The new drift-interpretation pipeline will reprocess this drift event "
    "on the next cron tick. See quickstart.md in the mission folder for "
    "details."
)
"""Closing comment template. ``{mission_slug}`` substituted at run time."""

GH_RATE_DELAY_SECONDS: float = 0.5
"""Polite spacing between ``gh`` invocations to keep us well under the
authenticated rate limit (5000/hr ≈ 1.4/sec sustained)."""

# Default path to the drift-events cursor file. Resolved at run time from
# the driver config when available, else falls back to the well-known
# deployment path documented in ``scripts/doc_audit/config.toml``.
_DEFAULT_CURSOR_PATH: str = "/data/services/security-monitor/.drift-events.cursor"


# ---------------------------------------------------------------------------
# Result dataclass (per contracts/api.md)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CutoverResult:
    """Outcome of one cutover invocation.

    Carries enough state for the CLI to print a summary, for the
    marker writer to record what was done, and for tests to assert on
    each component independently.

    Attributes:
        issues_closed: Issue numbers the script successfully closed.
            Partial-close failures are NOT included here (the failures
            are logged; the operator re-runs with ``--force`` to clean
            up the stragglers).
        cursor_reset: ``True`` iff the cursor was successfully reset to
            ``0`` (or would be in dry-run mode).
        marker_written: ``True`` iff the idempotency marker was
            successfully written (or would be in dry-run mode).
        dry_run: ``True`` iff the invocation was a dry run (no
            side effects).
        already_done: ``True`` iff the marker pre-existed and the run
            was a no-op (``--force`` not supplied). When True, the
            other fields reflect "nothing was done this invocation".
    """

    issues_closed: list[int]
    cursor_reset: bool
    marker_written: bool
    dry_run: bool
    already_done: bool


# ---------------------------------------------------------------------------
# Exit-code-shaping argparse subclass (mirrors the WP01 pattern)
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser.error()`` so ``main()`` returns 3.

    argparse's default ``error()`` calls ``sys.exit(2)``, but
    ``contracts/cli.md`` reserves exit-code 2 for filesystem failures
    on this CLI — bad flags must map to exit 3 instead. The
    ``--help`` path uses ``parser.exit(0)``, not ``error()``, so it
    still exits cleanly.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """Argparse subclass that raises instead of ``sys.exit(2)`` on bad flags.

    ``--help`` still exits 0 (argparse's help path uses ``parser.exit``,
    not ``error()``). Mirrors the WP01/WP02 ``drift_interpretation``
    and ``drift_ledger`` pattern.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


# ---------------------------------------------------------------------------
# Time helper
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 ``Z``-suffixed string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# GitHub close-with-comment (T025)
# ---------------------------------------------------------------------------


def _list_open_issues() -> list[int]:
    """Query GitHub for the open pre-#362 ``[doc-audit]`` P3 issues.

    Returns:
        List of issue numbers matching ``GH_QUERY`` on ``REPO``.

    Raises:
        subprocess.CalledProcessError: If ``gh issue list`` fails.
        ValueError: If ``gh`` returns output we can't parse as JSON.
    """
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            REPO,
            "--state",
            "open",
            "--search",
            GH_QUERY,
            "--json",
            "number",
            "--limit",
            "30",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"gh issue list returned unparseable JSON: {exc}"
        ) from exc
    if not isinstance(payload, list):
        raise ValueError(
            f"gh issue list returned non-list payload: {type(payload).__name__}"
        )
    numbers: list[int] = []
    for row in payload:
        if not isinstance(row, dict) or "number" not in row:
            raise ValueError(
                f"gh issue list row missing 'number': {row!r}"
            )
        try:
            numbers.append(int(row["number"]))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"gh issue list row has non-integer number: {row!r}"
            ) from exc
    return numbers


def _close_issue(issue_number: int, comment: str) -> None:
    """Post a closing comment + close one issue. Raises on subprocess error.

    Sleeps ``GH_RATE_DELAY_SECONDS`` between the two ``gh`` calls so
    we don't hammer the API in a tight loop. Callers handle errors
    (the partial-close-tolerance lives in ``_close_all_issues``).

    Raises:
        subprocess.CalledProcessError: If either ``gh`` call fails.
    """
    subprocess.run(
        [
            "gh",
            "issue",
            "comment",
            str(issue_number),
            "--repo",
            REPO,
            "--body",
            comment,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    time.sleep(GH_RATE_DELAY_SECONDS)
    subprocess.run(
        [
            "gh",
            "issue",
            "close",
            str(issue_number),
            "--repo",
            REPO,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    time.sleep(GH_RATE_DELAY_SECONDS)


def _close_all_issues(
    issue_numbers: list[int],
    dry_run: bool,
) -> list[int]:
    """Close each issue, tolerating per-issue failures.

    In dry-run mode no ``gh`` calls are made beyond the list query
    (which the caller has already done). The returned list is empty —
    nothing was actually closed.

    In non-dry-run mode, each issue gets a closing comment + close. If
    one issue fails (network blip, label mismatch, etc.) the failure
    is logged and the remaining issues are still processed. The
    returned list contains only the issue numbers that closed cleanly.

    Args:
        issue_numbers: Issues to close (returned from ``_list_open_issues``).
        dry_run: If True, log what would happen and return ``[]``.

    Returns:
        List of issue numbers that were closed successfully.
    """
    if dry_run:
        for number in issue_numbers:
            logger.info(
                "[dry-run] would comment + close issue #%d", number
            )
        return []

    comment = COMMENT_BODY.format(mission_slug=MISSION_SLUG)
    closed: list[int] = []
    for number in issue_numbers:
        try:
            _close_issue(number, comment)
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to close issue #%d: %s; continuing with remaining issues",
                number,
                exc.stderr.strip() if exc.stderr else exc,
            )
            continue
        closed.append(number)
        logger.info("Closed issue #%d with cutover comment", number)
    return closed


# ---------------------------------------------------------------------------
# Cursor reset + marker write (T026)
# ---------------------------------------------------------------------------


def _resolve_cursor_path() -> str:
    """Return the absolute path of the drift-events cursor file.

    Loads the driver config (``scripts/doc_audit/config.toml``) and
    returns ``paths.drift_cursor``. Falls back to the well-known
    deployment path (``_DEFAULT_CURSOR_PATH``) if the config is
    unavailable for any reason — this keeps the cutover script robust
    against partial deploys (e.g., the operator ran ``git pull`` but
    hasn't yet rolled config changes).
    """
    try:
        from doc_audit.config import load_config

        config = load_config()
        return str(config.paths.drift_cursor)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Could not load driver config (%s); using fallback cursor path %s",
            exc,
            _DEFAULT_CURSOR_PATH,
        )
        return _DEFAULT_CURSOR_PATH


def _reset_cursor(dry_run: bool) -> bool:
    """Reset the drift-events cursor to 0 via ``handle_drift_events``.

    Invokes the WP04 ``--reset-cursor`` flag as a subprocess. The
    invocation goes through the existing CLI surface so we exercise
    the same code path the WP04 tests verify (rather than re-writing
    the cursor file ourselves and risking drift).

    Args:
        dry_run: If True, log what would happen and return True without
            mutating anything.

    Returns:
        True iff the cursor was reset successfully (or would be).

    Raises:
        subprocess.CalledProcessError: When the subprocess fails (caller
            maps to exit 2).
    """
    if dry_run:
        logger.info(
            "[dry-run] would reset drift-events cursor to 0 via "
            "handle_drift_events --reset-cursor"
        )
        return True

    cursor_path = _resolve_cursor_path()
    subprocess.run(
        [
            "python3",
            "-m",
            "scripts.doc_audit.helpers.handle_drift_events",
            "--reset-cursor",
            "--cursor",
            cursor_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    logger.info("Reset drift-events cursor to 0 at %s", cursor_path)
    return True


def _write_marker(
    closed_issues: list[int],
    dry_run: bool,
    marker_path: Optional[Path] = None,
) -> bool:
    """Write the idempotency marker (atomic tempfile + rename).

    Marker contents (key:value lines for human readability + simple
    parsing if we ever need to):

        mission: drift-event-auto-resolution-01KS8J32
        mission_id: 01KS8J321F8KE7369R3DA02329
        run_at_utc: <ISO 8601>
        closed_issues: [351, 352, ...]
        cursor_reset_to: 0

    Args:
        closed_issues: Issue numbers actually closed (recorded in the marker).
        dry_run: If True, log what would happen and return True without
            mutating anything.
        marker_path: Override marker path (tests pass ``tmp_path`` to
            avoid touching ``~/.config``).

    Returns:
        True iff the marker was written (or would be) successfully.

    Raises:
        OSError: When the write fails (caller maps to exit 2).
    """
    target = marker_path if marker_path is not None else MARKER_PATH
    if dry_run:
        logger.info(
            "[dry-run] would write cutover marker to %s with closed=%s",
            target,
            closed_issues,
        )
        return True

    target.parent.mkdir(parents=True, exist_ok=True)

    content_lines = [
        f"mission: {MISSION_SLUG}",
        f"mission_id: {MISSION_ID}",
        f"run_at_utc: {_now_utc_iso()}",
        f"closed_issues: {json.dumps(sorted(closed_issues))}",
        "cursor_reset_to: 0",
    ]
    content = "\n".join(content_lines) + "\n"

    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    logger.info("Wrote cutover marker to %s", target)
    return True


def _marker_exists(marker_path: Optional[Path] = None) -> bool:
    """Return True if the idempotency marker is present.

    Args:
        marker_path: Override (tests pass ``tmp_path``).
    """
    target = marker_path if marker_path is not None else MARKER_PATH
    return target.exists()


# ---------------------------------------------------------------------------
# Orchestrator (T027)
# ---------------------------------------------------------------------------


def run(
    *,
    dry_run: bool = False,
    force: bool = False,
    marker_path: Optional[Path] = None,
) -> CutoverResult:
    """Idempotent one-shot cutover.

    Closes the 13 known pre-#362 ``[doc-audit]`` P3 issues and resets
    the drift-events cursor. Writes the marker on success.

    Order of operations:

        1. Check marker (unless ``force``): if present, no-op.
        2. List open issues matching ``GH_QUERY``.
        3. Close each (comment + close), tolerating per-issue failures.
        4. Reset the drift-events cursor to 0 via WP04's flag.
        5. Write the idempotency marker.

    Args:
        dry_run: If True, print what would happen and make no
            GitHub/filesystem mutations (beyond the list query that
            the operator needs to preview the impact).
        force: If True, ignore the marker and re-run the cutover even
            if it was already done.
        marker_path: Override marker path (test hook). Defaults to
            ``MARKER_PATH``.

    Returns:
        :class:`CutoverResult` carrying the per-step outcome.

    Raises:
        subprocess.CalledProcessError: GitHub list failure (caller maps
            to exit 1) or cursor reset failure (exit 2).
        ValueError: Malformed GitHub output (caller maps to exit 1).
        OSError: Marker write failure (caller maps to exit 2).
    """
    if _marker_exists(marker_path) and not force:
        logger.info(
            "Cutover marker already present at %s; nothing to do "
            "(re-run with --force to override)",
            marker_path if marker_path is not None else MARKER_PATH,
        )
        return CutoverResult(
            issues_closed=[],
            cursor_reset=False,
            marker_written=False,
            dry_run=dry_run,
            already_done=True,
        )

    issue_numbers = _list_open_issues()
    logger.info("Found %d open pre-#362 issue(s) to close", len(issue_numbers))

    closed = _close_all_issues(issue_numbers, dry_run=dry_run)

    cursor_reset = _reset_cursor(dry_run=dry_run)

    marker_written = _write_marker(
        closed_issues=closed if not dry_run else issue_numbers,
        dry_run=dry_run,
        marker_path=marker_path,
    )

    return CutoverResult(
        issues_closed=closed,
        cursor_reset=cursor_reset,
        marker_written=marker_written,
        dry_run=dry_run,
        already_done=False,
    )


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        prog="cutover_362",
        description=(
            "One-shot cutover for mission "
            f"{MISSION_SLUG} (#362). Closes the open pre-#362 "
            "[doc-audit] P3 issues, resets the drift-events cursor, "
            "and writes an idempotency marker. Re-run with --force to "
            "override the marker after partial-close failures."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Print what would happen; make no GitHub or filesystem "
            "mutations beyond the gh issue list query."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "Override the idempotency marker; re-run the cutover even "
            "if it was already completed."
        ),
    )
    return parser


def _print_summary(result: CutoverResult) -> None:
    """Emit a human-readable summary to stdout."""
    if result.already_done:
        print(
            "SUMMARY: cutover already complete (marker present); no-op. "
            "Use --force to re-run."
        )
        return

    label = "would close" if result.dry_run else "closed"
    print(
        f"SUMMARY: {label}={len(result.issues_closed)} issues "
        f"cursor_reset={result.cursor_reset} "
        f"marker_written={result.marker_written} "
        f"dry_run={result.dry_run}"
    )
    if result.issues_closed:
        formatted = ", ".join(f"#{n}" for n in sorted(result.issues_closed))
        print(f"  Issues: {formatted}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code.

    Exit codes:
        0 — Success (or idempotent no-op)
        1 — GitHub API failure
        2 — Filesystem failure (cursor reset or marker write)
        3 — Bad CLI arguments
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    try:
        result = run(dry_run=args.dry_run, force=args.force)
    except (subprocess.CalledProcessError, ValueError) as exc:
        # _list_open_issues failures (gh list non-zero, unparseable JSON)
        # AND _reset_cursor failures (handle_drift_events subprocess
        # error) both surface here; distinguish via the cmd that failed
        # so we map to the contract's exit codes (1 = github, 2 = fs).
        if isinstance(exc, subprocess.CalledProcessError):
            cmd = exc.cmd if isinstance(exc.cmd, (list, tuple)) else [str(exc.cmd)]
            if cmd and str(cmd[0]) == "gh":
                logger.error("GitHub API failure: %s", exc)
                return 1
            # python3 -m handle_drift_events failed → filesystem-class
            logger.error("Cursor reset failed: %s", exc)
            return 2
        # ValueError from _list_open_issues → GH-class failure
        logger.error("GitHub API failure: %s", exc)
        return 1
    except OSError as exc:
        logger.error("Filesystem failure writing marker: %s", exc)
        return 2

    _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
