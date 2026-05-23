#!/usr/bin/env python3
"""One-shot cleanup script for the broken-pipeline artifact issues.

Closes the 13 ``[doc-audit]`` artifact issues (#378-#390) that were
filed by the broken pre-mission-#391 pipeline replay on
2026-05-22T22:28 UTC. The fixed pipeline (Moment 0 wired at
``signals/drift_event.py`` via ``routing/drift_moment0.py``) processes
subsequent drift events via the LLM judgment path, so these
deterministically-filed artifact issues are no longer the right
surface.

This is **operator-run, once per deploy.** Subsequent runs are no-ops
(an idempotency marker at ``~/.config/doc-audit/cleanup-391.done``
gates re-execution). The marker can be force-overridden via ``--force``
when the operator deliberately wants to re-attempt the cleanup (e.g.,
the first run partial-closed a few issues and the operator wants the
remainder cleaned up).

This script is structurally identical to ``cutover_362.py`` with two
deliberate omissions:

    1. No ``gh issue list`` query — the issue numbers are a STATIC
       list known at code-write time (#378-#390).
    2. No drift-events cursor reset — the new (correct) pipeline
       processes subsequent events via Moment 0 naturally; we do not
       want to re-replay anything.

CLI surface:

    python3 scripts/doc_audit/helpers/cleanup_391.py [--dry-run] [--force]

Exit codes:

    0 — Success (or idempotent no-op)
    1 — GitHub API failure (all gh issue close calls failed)
    2 — Filesystem failure (marker write failed)
    3 — Bad CLI arguments (argparse error)

Importable surface:

    from doc_audit.helpers.cleanup_391 import run, CleanupResult

    result = run(dry_run=False, force=False)

Side effects in non-dry-run mode:

    1. Posts a closing comment + closes each of the 13 known artifact
       issues on ``kentonium3/kg-automation``.
    2. Writes the idempotency marker to
       ``~/.config/doc-audit/cleanup-391.done`` (atomic tempfile +
       rename) carrying the mission slug, mission id, run timestamp,
       and the closed-issue list.

Partial-close behavior: if an individual ``gh issue comment`` or
``gh issue close`` invocation fails, the script logs the failure and
continues with the remaining issues. The marker still records the
issues that *were* closed. The operator can re-run with ``--force`` to
clean up the stragglers. Only if **every** close attempt fails does
the script exit non-zero (1).
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

MARKER_PATH: Path = Path.home() / ".config" / "doc-audit" / "cleanup-391.done"
"""Idempotency marker location. Absent on a fresh deploy; written on success."""

MISSION_SLUG: str = "moment0-integration-fix-01KS8XRM"
"""Mission slug recorded in the marker for traceability."""

MISSION_ID: str = "01KS8XRMC0EQZ8HCJ52GXCJ226"
"""Mission ULID recorded in the marker for traceability."""

REPO: str = "kentonium3/kg-automation"
"""GitHub repository slug used by ``gh issue comment/close``."""

ISSUE_NUMBERS: list[int] = [
    378,
    379,
    380,
    381,
    382,
    383,
    384,
    385,
    386,
    387,
    388,
    389,
    390,
]
"""Static list of artifact issues filed by the broken pipeline (#378-#390)."""

COMMENT_BODY: str = (
    "Closing as part of mission moment0-integration-fix-01KS8XRM (#391). "
    "This issue was filed by the broken #362 pipeline replay on "
    "2026-05-22T22:28 UTC. The fixed pipeline (Moment 0 wired at "
    "signals/drift_event.py via routing/drift_moment0.py) now "
    "processes subsequent drift events via the LLM judgment path."
)
"""Closing comment body. Static per the mission spec — no template substitution."""

GH_RATE_DELAY_SECONDS: float = 0.5
"""Polite spacing between ``gh`` invocations to keep us well under the
authenticated rate limit (5000/hr ≈ 1.4/sec sustained)."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CleanupResult:
    """Outcome of one cleanup invocation.

    Carries enough state for the CLI to print a summary, for the marker
    writer to record what was done, and for tests to assert on each
    component independently.

    Attributes:
        issues_closed: Issue numbers the script successfully closed.
            Partial-close failures are NOT included here (the failures
            are logged; the operator re-runs with ``--force`` to clean
            up the stragglers).
        marker_written: ``True`` iff the idempotency marker was
            successfully written (or would be in dry-run mode).
        dry_run: ``True`` iff the invocation was a dry run (no
            side effects).
        already_done: ``True`` iff the marker pre-existed and the run
            was a no-op (``--force`` not supplied). When True, the
            other fields reflect "nothing was done this invocation".
    """

    issues_closed: list[int]
    marker_written: bool
    dry_run: bool
    already_done: bool


# ---------------------------------------------------------------------------
# Exit-code-shaping argparse subclass (mirrors the cutover_362 pattern)
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser.error()`` so ``main()`` returns 3.

    argparse's default ``error()`` calls ``sys.exit(2)``, but this
    CLI reserves exit-code 2 for filesystem failures — bad flags must
    map to exit 3 instead. The ``--help`` path uses ``parser.exit(0)``,
    not ``error()``, so it still exits cleanly.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """Argparse subclass that raises instead of ``sys.exit(2)`` on bad flags.

    ``--help`` still exits 0 (argparse's help path uses ``parser.exit``,
    not ``error()``). Mirrors the cutover_362 pattern.
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
# GitHub close-with-comment
# ---------------------------------------------------------------------------


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

    In dry-run mode no ``gh`` calls are made. The returned list is
    empty — nothing was actually closed.

    In non-dry-run mode, each issue gets a closing comment + close. If
    one issue fails (network blip, label mismatch, etc.) the failure
    is logged and the remaining issues are still processed. The
    returned list contains only the issue numbers that closed cleanly.

    Args:
        issue_numbers: Issues to close (the static ISSUE_NUMBERS list).
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

    closed: list[int] = []
    for number in issue_numbers:
        try:
            _close_issue(number, COMMENT_BODY)
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Failed to close issue #%d: %s; continuing with remaining issues",
                number,
                exc.stderr.strip() if exc.stderr else exc,
            )
            continue
        closed.append(number)
        logger.info("Closed issue #%d with cleanup comment", number)
    return closed


# ---------------------------------------------------------------------------
# Marker write
# ---------------------------------------------------------------------------


def _write_marker(
    closed_issues: list[int],
    dry_run: bool,
    marker_path: Optional[Path] = None,
) -> bool:
    """Write the idempotency marker (atomic tempfile + rename).

    Marker contents (key:value lines for human readability + simple
    parsing):

        mission: moment0-integration-fix-01KS8XRM
        mission_id: 01KS8XRMC0EQZ8HCJ52GXCJ226
        run_at_utc: <ISO 8601>
        closed_issues: [378, 379, ...]

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
            "[dry-run] would write cleanup marker to %s with closed=%s",
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

    logger.info("Wrote cleanup marker to %s", target)
    return True


def _marker_exists(marker_path: Optional[Path] = None) -> bool:
    """Return True if the idempotency marker is present.

    Args:
        marker_path: Override (tests pass ``tmp_path``).
    """
    target = marker_path if marker_path is not None else MARKER_PATH
    return target.exists()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run(
    *,
    dry_run: bool = False,
    force: bool = False,
    marker_path: Optional[Path] = None,
) -> CleanupResult:
    """Idempotent one-shot cleanup.

    Closes the 13 broken-pipeline ``[doc-audit]`` artifact issues
    (#378-#390) and writes the marker on success.

    Order of operations:

        1. Check marker (unless ``force``): if present, no-op.
        2. Close each known artifact issue (comment + close),
           tolerating per-issue failures.
        3. Write the idempotency marker.

    Args:
        dry_run: If True, print what would happen and make no
            GitHub/filesystem mutations.
        force: If True, ignore the marker and re-run the cleanup even
            if it was already done.
        marker_path: Override marker path (test hook). Defaults to
            ``MARKER_PATH``.

    Returns:
        :class:`CleanupResult` carrying the per-step outcome.

    Raises:
        subprocess.CalledProcessError: Only when EVERY close attempt
            failed (caller maps to exit 1). Per-issue failures are
            tolerated and surface only via the empty ``issues_closed``
            list.
        OSError: Marker write failure (caller maps to exit 2).
    """
    if _marker_exists(marker_path) and not force:
        logger.info(
            "Cleanup marker already present at %s; nothing to do "
            "(re-run with --force to override)",
            marker_path if marker_path is not None else MARKER_PATH,
        )
        return CleanupResult(
            issues_closed=[],
            marker_written=False,
            dry_run=dry_run,
            already_done=True,
        )

    logger.info(
        "Cleaning up %d broken-pipeline artifact issue(s): %s",
        len(ISSUE_NUMBERS),
        ", ".join(f"#{n}" for n in ISSUE_NUMBERS),
    )

    closed = _close_all_issues(ISSUE_NUMBERS, dry_run=dry_run)

    # If we attempted real closes and EVERY single one failed, escalate
    # to a GitHub API failure (exit 1) so the operator notices something
    # systemic. A single straggler is fine — it shows up as a partial
    # close and the operator re-runs with --force.
    if not dry_run and not closed and ISSUE_NUMBERS:
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "issue", "close"],
            output="",
            stderr="all close attempts failed",
        )

    marker_written = _write_marker(
        closed_issues=closed if not dry_run else ISSUE_NUMBERS,
        dry_run=dry_run,
        marker_path=marker_path,
    )

    return CleanupResult(
        issues_closed=closed,
        marker_written=marker_written,
        dry_run=dry_run,
        already_done=False,
    )


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        prog="cleanup_391",
        description=(
            "One-shot cleanup for mission "
            f"{MISSION_SLUG} (#391). Closes the 13 broken-pipeline "
            "[doc-audit] artifact issues (#378-#390) filed by the "
            "broken #362 pipeline replay on 2026-05-22T22:28 UTC, "
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
            "mutations."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "Override the idempotency marker; re-run the cleanup even "
            "if it was already completed."
        ),
    )
    return parser


def _print_summary(result: CleanupResult) -> None:
    """Emit a human-readable summary to stdout."""
    if result.already_done:
        print(
            "SUMMARY: cleanup already complete (marker present); no-op. "
            "Use --force to re-run."
        )
        return

    label = "would close" if result.dry_run else "closed"
    print(
        f"SUMMARY: {label}={len(result.issues_closed)} issues "
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
        1 — GitHub API failure (every close attempt failed)
        2 — Filesystem failure (marker write)
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
    except subprocess.CalledProcessError as exc:
        logger.error("GitHub API failure: %s", exc)
        return 1
    except OSError as exc:
        logger.error("Filesystem failure writing marker: %s", exc)
        return 2

    _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
