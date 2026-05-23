#!/usr/bin/env python3
"""One-shot cutover script for mission #310 (ADR-0002 Phase 7 — tasker JSONL).

Deploys the task-intelligence SKILL.md (closing the pre-existing gap surfaced
during #310 spec-readiness), deploys the cut tasker AGENTS.md to
``/data/services/openclaw/tasker-agent/``, runs ``reconcile_completions`` to
backfill the JSONL ledger from historic ``[Felix] enrichment`` Vikunja
comments, and writes an idempotency marker preventing accidental re-run.

This is **operator-run, once per deploy.** Subsequent runs are no-ops (the
marker at ``~/.config/openclaw/cutover-310.done`` gates re-execution).
``--force`` re-runs the cutover when the operator deliberately wants to retry
(e.g., the first run partial-deployed and the operator wants to clean up).

CLI surface (per ``contracts/cli.md`` § cutover_tasker):

    python3 scripts/openclaw/helpers/cutover_tasker.py [--dry-run] [--force]

Exit codes:

    0 — Success (or idempotent no-op)
    1 — Filesystem failure (SKILL or AGENTS deploy, or marker write)
    2 — Reconcile failure (``scripts.enrichment.reconcile_completions``
        subprocess returned non-zero)
    3 — Bad CLI arguments (argparse error)

Importable surface:

    from openclaw.helpers.cutover_tasker import run, CutoverResult

    result = run(dry_run=False, force=False)

Side effects in non-dry-run mode:

    1. Copies the SKILL.md from the repo to the deployed skills directory
       (``mkdir -p`` on the parent first).
    2. Copies the AGENTS.md from the repo to the deployed agent workspace.
    3. Invokes ``python3 -m scripts.enrichment.reconcile_completions`` to
       backfill the JSONL ledger from any existing ``[Felix] enrichment``
       Vikunja comments.
    4. Writes the idempotency marker (atomic tempfile + rename) carrying the
       mission slug, mission id, run timestamp, deployed-source paths, and
       reconcile exit status.

Pattern source: ``scripts/doc_audit/helpers/cutover_362.py``. Mirrors the
``_StructuredArgumentParser`` + dataclass result + marker idempotency shape.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

MARKER_PATH: Path = Path.home() / ".config" / "openclaw" / "cutover-310.done"
"""Idempotency marker location. Absent on a fresh deploy; written on success."""

MISSION_SLUG: str = "tasker-jsonl-migration-01KSB5XV"
"""Mission slug recorded in the marker for traceability."""

MISSION_ID: str = "01KSB5XVGW5WRDQFR17JSA52M5"
"""Mission ULID recorded in the marker for traceability."""

SKILL_SOURCE: Path = (
    Path(__file__).resolve().parents[2]
    / "openclaw"
    / "skills"
    / "task-intelligence"
    / "SKILL.md"
)
"""Repo-relative path to the task-intelligence SKILL.md source-of-truth."""

SKILL_TARGET: Path = Path(
    "/home/claude/.openclaw/skills/task-intelligence/SKILL.md"
)
"""Deployed location of the task-intelligence skill on office2."""

AGENTS_SOURCE: Path = (
    Path(__file__).resolve().parents[2]
    / "openclaw"
    / "agents"
    / "felix-admin-tasker"
    / "AGENTS.md"
)
"""Repo-relative path to the cut tasker AGENTS.md source-of-truth."""

AGENTS_TARGET: Path = Path("/data/services/openclaw/tasker-agent/AGENTS.md")
"""Deployed location of the tasker agent's AGENTS.md on office2."""

RECONCILE_MODULE: str = "scripts.enrichment.reconcile_completions"
"""Python module path for the reconcile helper invoked at step 3."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CutoverResult:
    """Outcome of one cutover invocation.

    Attributes:
        skill_deployed: True iff SKILL.md was copied (or would be, in dry-run).
        agents_deployed: True iff AGENTS.md was copied (or would be).
        reconcile_invoked: True iff the reconcile subprocess ran (or would).
        marker_written: True iff the idempotency marker was written (or would).
        dry_run: True iff the invocation was a dry run (no side effects).
        already_done: True iff the marker pre-existed and the run was a no-op
            (``--force`` not supplied). When True, the other fields reflect
            "nothing was done this invocation".
    """

    skill_deployed: bool
    agents_deployed: bool
    reconcile_invoked: bool
    marker_written: bool
    dry_run: bool
    already_done: bool


# ---------------------------------------------------------------------------
# Exit-code-shaping argparse subclass (mirrors cutover_362 pattern)
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser.error()`` so ``main()`` returns 3.

    argparse's default ``error()`` calls ``sys.exit(2)``, but this CLI reserves
    exit code 2 for reconcile failures — bad flags must map to exit 3 instead.
    ``--help`` still exits 0 (argparse routes ``--help`` through ``parser.exit``,
    not ``error()``).
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """Argparse subclass that raises instead of ``sys.exit(2)`` on bad flags.

    Mirrors the WP05 ``cutover_362.py`` pattern + the WP02 ``rotate_main_session.py``
    pattern. ``--help`` still exits 0 cleanly.
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
# Deployment helpers
# ---------------------------------------------------------------------------


def _deploy_file(
    *,
    source: Path,
    target: Path,
    dry_run: bool,
    label: str,
) -> bool:
    """Copy ``source`` → ``target``, creating parent dirs as needed.

    Args:
        source: Repo-side source path. Must exist.
        target: Deployment-side target path. Parent is mkdir-p'd if missing.
        dry_run: If True, log what would happen and return True without
            touching the filesystem.
        label: Human-readable label for log messages (e.g., "SKILL.md").

    Returns:
        True iff the copy completed (or would have, in dry-run).

    Raises:
        FileNotFoundError: When ``source`` does not exist.
        OSError: On any filesystem error during mkdir or copy.
    """
    if not source.exists():
        raise FileNotFoundError(
            f"{label} source does not exist: {source}"
        )

    if dry_run:
        logger.info(
            "[dry-run] would deploy %s: %s -> %s", label, source, target
        )
        return True

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    logger.info("Deployed %s: %s -> %s", label, source, target)
    return True


def _run_reconcile(dry_run: bool) -> bool:
    """Invoke the reconcile backfill via ``python3 -m`` subprocess.

    The reconcile helper is idempotent (per Phase 7 spec FR-009) — a no-op
    re-run is safe. The subprocess is the integration boundary; this script
    does not import the reconcile module so a missing/import-broken reconcile
    surfaces cleanly as a non-zero subprocess exit (mapped to exit 2).

    Args:
        dry_run: If True, log what would happen and return True without
            invoking the subprocess.

    Returns:
        True iff the subprocess ran with exit 0 (or would have, in dry-run).

    Raises:
        subprocess.CalledProcessError: When the subprocess fails (caller maps
            to exit 2).
    """
    if dry_run:
        logger.info(
            "[dry-run] would invoke python3 -m %s for backfill",
            RECONCILE_MODULE,
        )
        return True

    subprocess.run(
        ["python3", "-m", RECONCILE_MODULE],
        check=True,
        capture_output=True,
        text=True,
    )
    logger.info("Invoked %s for JSONL backfill", RECONCILE_MODULE)
    return True


# ---------------------------------------------------------------------------
# Marker helpers
# ---------------------------------------------------------------------------


def _marker_exists(marker_path: Optional[Path] = None) -> bool:
    """Return True if the idempotency marker is present.

    Args:
        marker_path: Override (tests pass ``tmp_path``).
    """
    target = marker_path if marker_path is not None else MARKER_PATH
    return target.exists()


def _write_marker(
    *,
    skill_deployed: bool,
    agents_deployed: bool,
    reconcile_invoked: bool,
    dry_run: bool,
    marker_path: Optional[Path] = None,
) -> bool:
    """Write the idempotency marker (atomic tempfile + rename).

    Marker contents (key:value lines for human readability + simple parsing):

        mission: tasker-jsonl-migration-01KSB5XV
        mission_id: 01KSB5XVGW5WRDQFR17JSA52M5
        run_at_utc: <ISO 8601>
        skill_source: scripts/openclaw/skills/task-intelligence/SKILL.md
        skill_target: /home/claude/.openclaw/skills/task-intelligence/SKILL.md
        agents_source: scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
        agents_target: /data/services/openclaw/tasker-agent/AGENTS.md
        skill_deployed: true|false
        agents_deployed: true|false
        reconcile_invoked: true|false

    Args:
        skill_deployed: Whether SKILL.md was actually copied.
        agents_deployed: Whether AGENTS.md was actually copied.
        reconcile_invoked: Whether reconcile_completions ran to completion.
        dry_run: If True, log what would happen and return True without
            mutating anything.
        marker_path: Override (tests pass ``tmp_path``).

    Returns:
        True iff the marker was written (or would be) successfully.

    Raises:
        OSError: When the write fails (caller maps to exit 1).
    """
    target = marker_path if marker_path is not None else MARKER_PATH
    if dry_run:
        logger.info(
            "[dry-run] would write cutover marker to %s "
            "(skill=%s, agents=%s, reconcile=%s)",
            target,
            skill_deployed,
            agents_deployed,
            reconcile_invoked,
        )
        return True

    target.parent.mkdir(parents=True, exist_ok=True)

    content_lines = [
        f"mission: {MISSION_SLUG}",
        f"mission_id: {MISSION_ID}",
        f"run_at_utc: {_now_utc_iso()}",
        f"skill_source: {SKILL_SOURCE}",
        f"skill_target: {SKILL_TARGET}",
        f"agents_source: {AGENTS_SOURCE}",
        f"agents_target: {AGENTS_TARGET}",
        f"skill_deployed: {json.dumps(skill_deployed)}",
        f"agents_deployed: {json.dumps(agents_deployed)}",
        f"reconcile_invoked: {json.dumps(reconcile_invoked)}",
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


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run(
    *,
    dry_run: bool = False,
    force: bool = False,
    marker_path: Optional[Path] = None,
) -> CutoverResult:
    """Idempotent one-shot cutover.

    Order of operations:

        1. Check marker (unless ``force``): if present, return no-op result.
        2. Deploy SKILL.md (closes the pre-existing skill deployment gap).
        3. Deploy AGENTS.md (cut to ≤14K chars by WP03 T007).
        4. Invoke ``python3 -m scripts.enrichment.reconcile_completions`` to
           backfill the JSONL ledger from historic Vikunja comments.
        5. Write the idempotency marker.

    Args:
        dry_run: If True, print what would happen and make no filesystem
            mutations.
        force: If True, ignore the marker and re-run the cutover even if it
            was already completed.
        marker_path: Override marker path (test hook). Defaults to
            ``MARKER_PATH``.

    Returns:
        :class:`CutoverResult` carrying the per-step outcome.

    Raises:
        FileNotFoundError: SKILL.md or AGENTS.md source missing (caller maps
            to exit 1).
        OSError: Deploy or marker-write filesystem failure (caller maps to
            exit 1).
        subprocess.CalledProcessError: Reconcile failure (caller maps to
            exit 2).
    """
    if _marker_exists(marker_path) and not force:
        logger.info(
            "Cutover marker already present at %s; nothing to do "
            "(re-run with --force to override)",
            marker_path if marker_path is not None else MARKER_PATH,
        )
        return CutoverResult(
            skill_deployed=False,
            agents_deployed=False,
            reconcile_invoked=False,
            marker_written=False,
            dry_run=dry_run,
            already_done=True,
        )

    skill_deployed = _deploy_file(
        source=SKILL_SOURCE,
        target=SKILL_TARGET,
        dry_run=dry_run,
        label="task-intelligence SKILL.md",
    )

    agents_deployed = _deploy_file(
        source=AGENTS_SOURCE,
        target=AGENTS_TARGET,
        dry_run=dry_run,
        label="tasker AGENTS.md",
    )

    reconcile_invoked = _run_reconcile(dry_run=dry_run)

    marker_written = _write_marker(
        skill_deployed=skill_deployed,
        agents_deployed=agents_deployed,
        reconcile_invoked=reconcile_invoked,
        dry_run=dry_run,
        marker_path=marker_path,
    )

    return CutoverResult(
        skill_deployed=skill_deployed,
        agents_deployed=agents_deployed,
        reconcile_invoked=reconcile_invoked,
        marker_written=marker_written,
        dry_run=dry_run,
        already_done=False,
    )


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        prog="cutover_tasker",
        description=(
            "One-shot cutover for mission "
            f"{MISSION_SLUG} (#310, ADR-0002 Phase 7). Deploys the "
            "task-intelligence SKILL.md and the cut tasker AGENTS.md to "
            "office2, runs reconcile_completions to backfill the JSONL "
            "ledger from historic Vikunja comments, and writes an "
            "idempotency marker. Re-run with --force to override the "
            "marker after partial deploys."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would happen; make no filesystem mutations or subprocess invocations.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Override the idempotency marker; re-run even if already completed.",
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

    label = "would deploy" if result.dry_run else "deployed"
    print(
        f"SUMMARY: {label} skill={result.skill_deployed} "
        f"agents={result.agents_deployed} "
        f"reconcile_invoked={result.reconcile_invoked} "
        f"marker_written={result.marker_written} "
        f"dry_run={result.dry_run}"
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code.

    Exit codes:
        0 — Success (or idempotent no-op)
        1 — Filesystem failure (deploy or marker write)
        2 — Reconcile subprocess failure
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
        logger.error(
            "Reconcile subprocess failed: %s; stderr: %s",
            exc,
            (exc.stderr or "").strip() if exc.stderr else "",
        )
        return 2
    except FileNotFoundError as exc:
        logger.error("Source file missing: %s", exc)
        return 1
    except OSError as exc:
        logger.error("Filesystem failure: %s", exc)
        return 1

    _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
