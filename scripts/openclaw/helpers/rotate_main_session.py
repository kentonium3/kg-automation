#!/usr/bin/env python3
"""Operator-driven rotation of the OpenClaw ``main`` agent's active sessions.

When the operator changes ``/data/services/openclaw/data/AGENTS.md`` (the
main agent's standing orders), any already-running session keeps its
cached system prompt and never sees the new content. This script forces
all active sessions to rotate so the next ``openclaw agent --agent main
--message ...`` invocation starts a fresh session that re-loads
``AGENTS.md`` from disk.

Mechanism — mirrors the existing auto-rotation pattern observed on
office2: each ``<uuid>.jsonl`` active session file is renamed to
``<uuid>.jsonl.reset.<timestamp>``. Sessions that have already been
rotated (already carry the ``.reset.`` suffix) are skipped. A marker
file at ``~/.config/openclaw/main-rotation-<timestamp>.done`` is
written carrying the mission slug and the list of rotated sessions for
operator audit.

CLI surface (per ``contracts/rotation-helper.md``):

    python3 scripts/openclaw/helpers/rotate_main_session.py [--dry-run] [--force]

Exit codes:

    0 — Success (or dry-run completed)
    1 — Filesystem error (rename failed, marker write failed)
    3 — Bad CLI arguments (argparse error)

Importable surface (mirroring the WP05 #362 cutover pattern):

    from openclaw.helpers.rotate_main_session import run, RotationResult

    result = run(dry_run=False, force=False)

Idempotency: Each invocation produces a uniquely-timestamped marker and
each rotated file carries a unique ``.reset.<timestamp>`` suffix, so
re-running is naturally safe — a second run simply rotates whatever
fresh sessions exist (typically none if no traffic has hit the agent
since the first run). ``--force`` is reserved for future use; current
behavior treats ``--force`` identically to a normal run beyond
``dry_run``.
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

SESSIONS_DIR: Path = Path("/home/claude/.openclaw/agents/main/sessions")
"""Default directory where the main agent's active ``*.jsonl`` session files
live on office2. Tests override via the ``sessions_dir`` keyword arg to
``run()`` so we never touch the real path."""

MARKER_DIR: Path = Path.home() / ".config" / "openclaw"
"""Default directory where rotation markers are written
(``main-rotation-<timestamp>.done``). Tests override via the
``marker_dir`` keyword arg."""

MISSION_SLUG: str = "main-verbatim-passthrough-01KSATRP"
"""Mission slug recorded in the marker file for traceability."""


# ---------------------------------------------------------------------------
# Result dataclass (per contracts/rotation-helper.md § post-conditions)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RotationResult:
    """Outcome of one rotation invocation.

    Attributes:
        rotated: Filenames (basenames, not full paths) of the active
            ``*.jsonl`` sessions that were rotated this invocation. In
            dry-run mode this lists the sessions that *would* be
            rotated.
        marker_path: Path to the marker file that was written (or that
            would be written, in dry-run mode). ``None`` if no sessions
            were eligible for rotation (no marker is written in that
            case — there's nothing to record).
        dry_run: ``True`` iff the invocation was a dry run (no
            filesystem mutations).
    """

    rotated: list[str]
    marker_path: Optional[Path]
    dry_run: bool


# ---------------------------------------------------------------------------
# Exit-code-shaping argparse subclass (mirrors cutover_362 pattern)
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser.error()`` so ``main()`` returns 3.

    argparse's default ``error()`` calls ``sys.exit(2)``, but the
    contract for this CLI reserves exit-code 1 for filesystem failures
    and exit-code 3 for bad flags. ``--help`` still exits 0 (argparse
    routes ``--help`` through ``parser.exit()`` not ``error()``).
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """Argparse subclass that raises instead of ``sys.exit(2)`` on bad flags.

    Mirrors the cutover_362.py pattern so the CLI contract surface is
    consistent across operator helpers.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _now_timestamp() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH-MM-SS.mmmZ``.

    Uses hyphens instead of colons so the value is safe to embed in a
    filename on every platform. Includes millisecond precision so two
    rotations executed within the same second still produce distinct
    suffixes (this matches the format observed in the existing
    auto-rotated files on office2).
    """
    now = datetime.now(timezone.utc)
    # %f gives microseconds (6 digits); trim to milliseconds (3 digits).
    millis = f"{now.microsecond // 1000:03d}"
    return now.strftime(f"%Y-%m-%dT%H-%M-%S.{millis}Z")


def _list_active_sessions(sessions_dir: Path) -> list[Path]:
    """Return all active ``*.jsonl`` session files in ``sessions_dir``.

    Filters out files whose name contains ``.jsonl.reset.`` — those are
    already-rotated sessions left as historical records.

    Args:
        sessions_dir: Directory to scan. Pass the real
            ``SESSIONS_DIR`` in production; tests pass ``tmp_path``.

    Returns:
        Sorted list of ``Path`` objects (one per active session file).
        Sorted for deterministic ordering in tests + output.
    """
    if not sessions_dir.is_dir():
        return []
    actives: list[Path] = []
    for entry in sessions_dir.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        # Skip anything that's already a ``.reset.`` rotated artifact.
        if ".jsonl.reset." in name:
            continue
        # Only consider true ``.jsonl`` active sessions.
        if not name.endswith(".jsonl"):
            continue
        actives.append(entry)
    return sorted(actives, key=lambda p: p.name)


def _rotate_session(path: Path, timestamp: str) -> Path:
    """Rename ``<original>.jsonl`` to ``<original>.jsonl.reset.<timestamp>``.

    Args:
        path: Path to the active ``*.jsonl`` file to rotate.
        timestamp: Timestamp suffix (produced by :func:`_now_timestamp`).

    Returns:
        The new ``Path`` carrying the ``.reset.<timestamp>`` suffix.

    Raises:
        OSError: If the underlying rename fails (caller maps to exit 1).
    """
    new_path = path.with_name(f"{path.name}.reset.{timestamp}")
    path.rename(new_path)
    return new_path


def _write_marker(
    rotated: list[str],
    timestamp: str,
    marker_dir: Path,
) -> Path:
    """Write the rotation marker file to ``marker_dir``.

    Marker contents (key:value lines for human readability + simple
    parsing if we ever need to)::

        mission: main-verbatim-passthrough-01KSATRP
        run_at_utc: <timestamp>
        rotated: <name1>, <name2>, ...

    Args:
        rotated: Filenames (basenames) of the sessions that were
            rotated. Empty list is valid (we still write the marker for
            audit, though :func:`run` short-circuits the call when
            nothing was rotated).
        timestamp: Timestamp suffix to embed in the marker filename and
            the ``run_at_utc`` field.
        marker_dir: Directory where the marker is written. Created if
            absent.

    Returns:
        The full ``Path`` of the marker file that was created.

    Raises:
        OSError: If ``mkdir`` or the file write fails (caller maps to
            exit 1).
    """
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker_path = marker_dir / f"main-rotation-{timestamp}.done"

    rotated_csv = ", ".join(rotated) if rotated else "(none)"
    body_lines = [
        f"mission: {MISSION_SLUG}",
        f"run_at_utc: {timestamp}",
        f"rotated: {rotated_csv}",
    ]
    marker_path.write_text("\n".join(body_lines) + "\n", encoding="utf-8")
    return marker_path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run(
    *,
    dry_run: bool = False,
    force: bool = False,
    sessions_dir: Optional[Path] = None,
    marker_dir: Optional[Path] = None,
) -> RotationResult:
    """Rotate all active main-agent sessions and write a marker.

    Order of operations:

        1. List active ``*.jsonl`` files in ``sessions_dir``
           (excluding already-rotated ``.reset.*`` artifacts).
        2. If ``dry_run`` is True: log the intended rotations + intended
           marker path; return a ``RotationResult`` describing what
           *would* happen. No filesystem mutations.
        3. Otherwise: rotate each session, then write a single marker
           file recording the timestamp + list of rotated sessions.

    The operation is naturally idempotent in the no-traffic case — a
    second invocation finds zero active ``*.jsonl`` files (the first
    invocation already renamed them all) and returns immediately. The
    ``force`` parameter is reserved for future use; today the script
    has no marker-gated short-circuit so ``force`` has no extra effect
    beyond a normal run.

    Args:
        dry_run: If True, log what would happen and make no filesystem
            mutations.
        force: Reserved for future use (currently has no extra effect).
        sessions_dir: Directory to scan for active sessions. Tests pass
            ``tmp_path``; production defaults to the module-level
            :data:`SESSIONS_DIR` (resolved at call time so
            ``monkeypatch.setattr`` on the constant takes effect).
        marker_dir: Directory where the marker is written. Tests pass
            ``tmp_path``; production defaults to the module-level
            :data:`MARKER_DIR` (resolved at call time).

    Returns:
        :class:`RotationResult` carrying the per-invocation outcome.

    Raises:
        OSError: When a rename or marker write fails (caller maps to
            exit 1). Partial state is acceptable — some files may have
            been renamed before the failure surfaced.
    """
    del force  # currently unused; documented as "reserved for future use"

    # Resolve module constants at call time so monkeypatching them in
    # tests (and any future env-driven override) takes effect.
    if sessions_dir is None:
        sessions_dir = SESSIONS_DIR
    if marker_dir is None:
        marker_dir = MARKER_DIR

    active_paths = _list_active_sessions(sessions_dir)
    active_names = [p.name for p in active_paths]
    timestamp = _now_timestamp()

    if dry_run:
        if active_names:
            logger.info(
                "[dry-run] would rotate %d main session(s):", len(active_names)
            )
            for name in active_names:
                logger.info(
                    "  %s -> %s.reset.%s", name, name, timestamp
                )
            intended_marker = marker_dir / f"main-rotation-{timestamp}.done"
            logger.info(
                "[dry-run] would write marker: %s", intended_marker
            )
            return RotationResult(
                rotated=active_names,
                marker_path=intended_marker,
                dry_run=True,
            )
        logger.info(
            "[dry-run] no active main sessions to rotate "
            "(scanned %s)",
            sessions_dir,
        )
        return RotationResult(rotated=[], marker_path=None, dry_run=True)

    if not active_names:
        logger.info(
            "No active main sessions to rotate (scanned %s); nothing to do",
            sessions_dir,
        )
        return RotationResult(rotated=[], marker_path=None, dry_run=False)

    rotated_names: list[str] = []
    for path in active_paths:
        new_path = _rotate_session(path, timestamp)
        rotated_names.append(path.name)
        logger.info("Rotated %s -> %s", path.name, new_path.name)

    marker_path = _write_marker(
        rotated=rotated_names,
        timestamp=timestamp,
        marker_dir=marker_dir,
    )
    logger.info(
        "Wrote rotation marker to %s (rotated=%d session(s))",
        marker_path,
        len(rotated_names),
    )

    return RotationResult(
        rotated=rotated_names,
        marker_path=marker_path,
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        prog="rotate_main_session",
        description=(
            "Rotate the OpenClaw main agent's active sessions so the next "
            "invocation re-loads /data/services/openclaw/data/AGENTS.md. "
            f"Mission: {MISSION_SLUG}. "
            "Idempotent: each call produces a uniquely-timestamped marker "
            "and reset-suffixed file."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Print what would happen; make no filesystem mutations "
            "(no renames, no marker)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "Reserved for future use; current behavior treats --force "
            "identically to a normal run beyond --dry-run."
        ),
    )
    return parser


def _print_summary(result: RotationResult) -> None:
    """Emit a human-readable summary to stdout."""
    label = "Would rotate" if result.dry_run else "Rotated"
    count = len(result.rotated)
    print(f"SUMMARY: {label} {count} main session(s) dry_run={result.dry_run}")
    if result.rotated:
        for name in result.rotated:
            print(f"  - {name}")
    if result.marker_path is not None:
        marker_label = "Would write marker" if result.dry_run else "Marker"
        print(f"  {marker_label}: {result.marker_path}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code.

    Exit codes:
        0 — Success (or dry-run completed)
        1 — Filesystem failure (rename or marker write)
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
    except OSError as exc:
        logger.error("Filesystem failure during rotation: %s", exc)
        return 1

    _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
