#!/usr/bin/env python3
"""Inbox pre-scan helper.

Pure-Python classifier and archiver for the Obsidian vault inbox. Reads the
vault path registry (``scripts/vault/paths.json``) to resolve
``{{VAULT_INBOX}}`` and ``{{VAULT_INBOX_PROCESSED}}``, then walks the inbox
directory, classifies each ``.md`` file by YAML frontmatter ``status`` +
filesystem mtime, archives ``processed`` files older than 7 days into
``{{VAULT_INBOX_PROCESSED}}``, and emits a ``PrescanResult`` JSON object on
stdout for agent consumption.

Contract:
    stdin: not read
    stdout: single-line JSON ``PrescanResult`` on success (exit 0), nothing on error
    stderr: human-readable log lines; warnings on non-fatal issues
    side effects: may move stale ``processed`` files; appends to a daily log file
    exit: 0 success, 1 fatal (registry / directory resolution failure)

Modes:
    ``--self-check``: resolve registry, confirm both directories exist, print
    ``{"self_check": "ok", ...}`` on stdout, exit 0. Used by deploy wrapper
    preflight.

Environment overrides (test isolation):
    PRESCAN_REGISTRY_PATH: absolute path to an alternate ``paths.json``
    PRESCAN_LOG_DIR:       directory for daily log files (default
                           ``/home/claude/second-brain/agents/logs``; falls
                           back to ``$TMPDIR`` if missing)

Dependencies: stdlib + PyYAML (``yaml.safe_load`` only, per NFR-004).
No LLM imports, no network, no office2 contact (NFR-002).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALE_AGE_DAYS = 7  # exclusive boundary: age_days > 7 is stale
DEFAULT_LOG_DIR = Path("/home/claude/second-brain/agents/logs")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PrescanError(Exception):
    """Fatal error during pre-scan execution."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class InboxFile:
    path: Path
    mtime_utc: datetime
    status_raw: Optional[str]
    classification: str
    warning: Optional[str] = None

    @property
    def age_days(self) -> float:
        now = datetime.now(timezone.utc)
        return (now - self.mtime_utc).total_seconds() / 86400.0


@dataclass
class ArchiveResult:
    src: str
    dst: str
    age_days: int
    success: bool
    warning: Optional[str] = None


@dataclass
class PrescanResult:
    run_id: str
    started_at_utc: str
    finished_at_utc: str
    inbox_path: str
    inbox_processed_path: str
    unprocessed_count: int
    unprocessed_paths: list
    archived_count: int
    archived: list
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry resolution (T002)
# ---------------------------------------------------------------------------


def _default_registry_path() -> Path:
    """Compute default registry location relative to this helper's own file.

    Works both in repo-root dev/test layouts and on office2 at
    ``/home/claude/kg-automation/scripts/inbox/prescan.py`` because the deploy
    wrapper preserves the ``scripts/{inbox,vault}`` sibling layout.
    """
    return Path(__file__).resolve().parent.parent / "vault" / "paths.json"


def resolve_registry() -> tuple[Path, Path]:
    """Read the vault registry and return ``(inbox, inbox_processed)``.

    Raises:
        PrescanError: on any failure (missing file, unreadable, malformed
            JSON, missing keys, non-existent resolved path, resolved path is
            not a directory).
    """
    override = os.environ.get("PRESCAN_REGISTRY_PATH")
    registry_path = Path(override) if override else _default_registry_path()

    if not registry_path.exists():
        raise PrescanError(f"Vault registry not found at {registry_path}")

    try:
        raw = registry_path.read_text(encoding="utf-8")
    except PermissionError as e:
        raise PrescanError(f"Vault registry unreadable at {registry_path}: {e}") from e
    except OSError as e:
        raise PrescanError(f"Vault registry unreadable at {registry_path}: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PrescanError(
            f"Vault registry is not valid JSON at {registry_path}: {e}"
        ) from e

    paths = data.get("paths")
    if not isinstance(paths, dict):
        raise PrescanError(
            f"Vault registry missing 'paths' object at {registry_path}"
        )

    if "inbox" not in paths:
        raise PrescanError(
            f"Vault registry missing 'paths.inbox' key at {registry_path}"
        )
    if "inbox_processed" not in paths:
        raise PrescanError(
            f"Vault registry missing 'paths.inbox_processed' key at {registry_path}"
        )

    inbox = Path(paths["inbox"])
    inbox_processed = Path(paths["inbox_processed"])

    if not inbox.exists():
        raise PrescanError(f"Inbox path does not exist: {inbox}")
    if not inbox.is_dir():
        raise PrescanError(f"Inbox path is not a directory: {inbox}")
    if not inbox_processed.exists():
        raise PrescanError(f"Inbox-processed path does not exist: {inbox_processed}")
    if not inbox_processed.is_dir():
        raise PrescanError(
            f"Inbox-processed path is not a directory: {inbox_processed}"
        )

    return inbox, inbox_processed


# ---------------------------------------------------------------------------
# Classification (T003)
# ---------------------------------------------------------------------------


def _extract_frontmatter_block(text: str) -> Optional[str]:
    """Return the text between the first two ``---`` fences, or None.

    Skips leading blank lines before the opening fence. Real-world Obsidian
    inbox files (including those generated by Templater) commonly start with
    one or more blank lines before the YAML frontmatter — the original strict
    rule (``lines[0] == "---"``) missed all of those, discovered during
    mission 027 WP05 live deploy.
    """
    lines = text.splitlines()
    # Skip leading blank lines to find the opening fence.
    start = 0
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    if start >= len(lines) or lines[start].strip() != "---":
        return None
    for idx in range(start + 1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[start + 1 : idx])
    return None  # unterminated fence → no frontmatter


def _parse_processed_at_age(
    raw: object, now_utc: datetime
) -> Optional[float]:
    """Parse a ``processed_at`` frontmatter value and return age in days.

    Returns ``None`` when the value is missing, malformed, or unparseable —
    the caller should fall back to filesystem mtime in that case.
    """
    if isinstance(raw, datetime):
        ts = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    elif isinstance(raw, str):
        try:
            ts = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    else:
        return None
    return (now_utc - ts).total_seconds() / 86400.0


def classify_file(path: Path, now_utc: datetime) -> InboxFile:
    """Classify a single ``.md`` file per the data-model rules."""
    mtime_raw = os.path.getmtime(path)
    mtime_utc = datetime.fromtimestamp(mtime_raw, tz=timezone.utc)
    age_days = (now_utc - mtime_utc).total_seconds() / 86400.0

    status_raw: Optional[str] = None
    warning: Optional[str] = None
    frontmatter: Optional[dict] = None

    try:
        text = path.read_text(encoding="utf-8")
    except (PermissionError, OSError, UnicodeDecodeError) as e:
        warning = f"unreadable file; treated as unprocessed: {e}"
        return InboxFile(
            path=path,
            mtime_utc=mtime_utc,
            status_raw=None,
            classification="unknown-treated-as-unprocessed",
            warning=warning,
        )

    block = _extract_frontmatter_block(text)
    if block is None:
        warning = "no frontmatter block; treated as unprocessed"
        return InboxFile(
            path=path,
            mtime_utc=mtime_utc,
            status_raw=None,
            classification="unknown-treated-as-unprocessed",
            warning=warning,
        )

    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        warning = "malformed YAML frontmatter; treated as unprocessed"
        return InboxFile(
            path=path,
            mtime_utc=mtime_utc,
            status_raw=None,
            classification="unknown-treated-as-unprocessed",
            warning=warning,
        )

    if not isinstance(parsed, dict):
        warning = "frontmatter is not a mapping; treated as unprocessed"
        return InboxFile(
            path=path,
            mtime_utc=mtime_utc,
            status_raw=None,
            classification="unknown-treated-as-unprocessed",
            warning=warning,
        )

    frontmatter = parsed
    status_raw = frontmatter.get("status")
    if status_raw is not None and not isinstance(status_raw, str):
        status_raw = str(status_raw)

    if status_raw is None:
        warning = "frontmatter missing 'status' field; treated as unprocessed"
        classification = "unknown-treated-as-unprocessed"
    elif status_raw == "unprocessed":
        classification = "unprocessed"
    elif status_raw == "processed":
        # Prefer processed_at frontmatter over filesystem mtime (issue #187).
        processed_at_age = _parse_processed_at_age(
            frontmatter.get("processed_at"), now_utc
        )
        if processed_at_age is not None:
            age_days = processed_at_age
        if age_days > STALE_AGE_DAYS:
            classification = "processed-stale"
        else:
            classification = "processed-recent"
    else:
        warning = (
            f"unknown status '{status_raw}'; treated as unprocessed (safety default)"
        )
        classification = "unknown-treated-as-unprocessed"

    return InboxFile(
        path=path,
        mtime_utc=mtime_utc,
        status_raw=status_raw,
        classification=classification,
        warning=warning,
    )


def scan_directory(inbox_dir: Path, now_utc: datetime) -> list[InboxFile]:
    """List ``.md`` files directly under ``inbox_dir`` and classify them.

    Non-recursive. Skips any path containing ``_private`` as a path component
    (defense-in-depth for C-001 privacy boundary; the inbox should never
    contain such a subdirectory but this is belt-and-suspenders).
    """
    results: list[InboxFile] = []
    try:
        entries = sorted(inbox_dir.iterdir(), key=lambda p: p.name)
    except OSError as e:
        raise PrescanError(f"Unable to list inbox directory {inbox_dir}: {e}") from e

    for entry in entries:
        # Defense-in-depth: never walk a _private subdirectory.
        if "_private" in entry.parts:
            continue
        if not entry.is_file():
            continue
        if entry.suffix.lower() != ".md":
            continue
        # Extra guard: resolve symlinks and verify they don't land in _private.
        try:
            resolved = entry.resolve()
            if "_private" in resolved.parts:
                continue
        except OSError:
            continue
        results.append(classify_file(entry, now_utc))

    return results


# ---------------------------------------------------------------------------
# Archive stale (T004)
# ---------------------------------------------------------------------------


def archive_stale(
    stale_files: list[InboxFile], inbox_processed_dir: Path
) -> list[ArchiveResult]:
    """Move ``processed-stale`` files into ``inbox_processed_dir``.

    Skips (with warning) if destination already exists or the move fails
    with a ``PermissionError`` or ``OSError``. Never raises.
    """
    results: list[ArchiveResult] = []
    for f in stale_files:
        dst = inbox_processed_dir / f.path.name
        age_days_int = int(f.age_days)
        if dst.exists():
            results.append(
                ArchiveResult(
                    src=str(f.path),
                    dst=str(dst),
                    age_days=age_days_int,
                    success=False,
                    warning=f"destination already exists: {dst}; skipping move",
                )
            )
            continue
        try:
            shutil.move(str(f.path), str(dst))
            results.append(
                ArchiveResult(
                    src=str(f.path),
                    dst=str(dst),
                    age_days=age_days_int,
                    success=True,
                    warning=None,
                )
            )
        except (PermissionError, OSError) as e:
            results.append(
                ArchiveResult(
                    src=str(f.path),
                    dst=str(dst),
                    age_days=age_days_int,
                    success=False,
                    warning=f"move failed: {e}",
                )
            )
    return results


# ---------------------------------------------------------------------------
# Output layer (T005)
# ---------------------------------------------------------------------------


def _make_run_id(now_utc: datetime) -> str:
    suffix = secrets.token_hex(3)
    return now_utc.strftime("%Y-%m-%dT%H:%M:%SZ-") + suffix


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_dir() -> tuple[Path, Optional[str]]:
    """Return (directory, fallback_warning). Ensures directory exists."""
    override = os.environ.get("PRESCAN_LOG_DIR")
    if override:
        d = Path(override)
    else:
        d = DEFAULT_LOG_DIR
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d, None
    except (PermissionError, OSError):
        fallback = Path(tempfile.gettempdir())
        warning = (
            f"primary log dir {d} unavailable; falling back to {fallback}"
        )
        return fallback, warning


def _append_daily_log(
    log_dir: Path,
    result: PrescanResult,
    duration_ms: int,
    archived: list[ArchiveResult],
    unprocessed: list[InboxFile],
) -> Path:
    date_str = result.started_at_utc[:10]
    log_path = log_dir / f"inbox-prescan-{date_str}.md"
    lines: list[str] = []
    lines.append(f"## Run {result.started_at_utc} — run_id={result.run_id}")
    lines.append("")
    lines.append(f"- inbox: {result.inbox_path}")
    lines.append(f"- inbox_processed: {result.inbox_processed_path}")
    lines.append(f"- unprocessed: {result.unprocessed_count}")
    lines.append(f"- archived: {result.archived_count}")
    lines.append(f"- warnings: {len(result.warnings)}")
    lines.append(f"- duration_ms: {duration_ms}")
    if archived:
        lines.append("")
        lines.append("### Archived")
        for a in archived:
            note = "" if a.success else f" (skipped: {a.warning})"
            lines.append(f"- {Path(a.src).name} (age {a.age_days}d){note}")
    if unprocessed:
        lines.append("")
        lines.append("### Unprocessed handed to agent")
        for u in unprocessed:
            lines.append(f"- {u.path.name}")
    lines.append("")
    lines.append("")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return log_path


def _emit_stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def run_prescan() -> int:
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    try:
        inbox, inbox_processed = resolve_registry()
    except PrescanError as e:
        _emit_stderr(f"prescan: ERROR {e}")
        return 1

    _emit_stderr(f"prescan: scanning inbox {inbox}")
    try:
        classified = scan_directory(inbox, started)
    except PrescanError as e:
        _emit_stderr(f"prescan: ERROR {e}")
        return 1
    _emit_stderr(f"prescan: classified {len(classified)} files")

    stale = [f for f in classified if f.classification == "processed-stale"]
    unprocessed = [
        f
        for f in classified
        if f.classification in ("unprocessed", "unknown-treated-as-unprocessed")
    ]

    _emit_stderr(f"prescan: archiving {len(stale)} stale files")
    archived = archive_stale(stale, inbox_processed)

    warnings: list[dict] = []
    for f in classified:
        if f.warning and f.classification == "unknown-treated-as-unprocessed":
            warnings.append({"path": str(f.path), "reason": f.warning})
    for a in archived:
        if not a.success and a.warning:
            warnings.append({"path": a.src, "reason": a.warning})

    finished = datetime.now(timezone.utc)
    duration_ms = int((time.monotonic() - t0) * 1000)

    archived_json = [
        {"src": a.src, "dst": a.dst, "age_days": a.age_days}
        for a in archived
        if a.success
    ]

    result = PrescanResult(
        run_id=_make_run_id(started),
        started_at_utc=_iso(started),
        finished_at_utc=_iso(finished),
        inbox_path=str(inbox),
        inbox_processed_path=str(inbox_processed),
        unprocessed_count=len(unprocessed),
        unprocessed_paths=sorted(str(f.path) for f in unprocessed),
        archived_count=len(archived_json),
        archived=archived_json,
        warnings=warnings,
    )

    _emit_stderr("prescan: writing daily log")
    log_dir, fallback_warning = _log_dir()
    if fallback_warning:
        _emit_stderr(f"prescan: WARN {fallback_warning}")
    try:
        _append_daily_log(log_dir, result, duration_ms, archived, unprocessed)
    except OSError as e:
        _emit_stderr(f"prescan: WARN daily log write failed: {e}")

    sys.stdout.write(json.dumps(asdict(result)) + "\n")
    sys.stdout.flush()
    _emit_stderr(
        f"prescan: done unprocessed={result.unprocessed_count} "
        f"archived={result.archived_count} warnings={len(result.warnings)} "
        f"duration_ms={duration_ms}"
    )
    return 0


def run_self_check() -> int:
    try:
        inbox, inbox_processed = resolve_registry()
    except PrescanError as e:
        _emit_stderr(f"prescan: self-check FAILED {e}")
        return 1
    payload = {
        "self_check": "ok",
        "inbox": str(inbox),
        "inbox_processed": str(inbox_processed),
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prescan",
        description=(
            "Pre-scan the Obsidian vault inbox: classify files, archive "
            "stale processed notes, emit a JSON PrescanResult on stdout."
        ),
    )
    parser.add_argument(
        "--self-check",
        dest="self_check",
        action="store_true",
        help=(
            "Resolve registry and verify both inbox directories exist. "
            "Prints a minimal JSON ack and exits 0 on success."
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.self_check:
        return run_self_check()
    return run_prescan()


if __name__ == "__main__":
    sys.exit(main())
