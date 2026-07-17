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
                           ``/home/kgale/second-brain/agents/logs``; falls
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
DEFAULT_LOG_DIR = Path("/home/kgale/second-brain/agents/logs")


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
    parse_failure_reason: Optional[str] = None  # set when classification == "parse-failure" (#185)
    has_stale_error_marker: bool = False  # True when the body has a felix-capture marker but parses cleanly (#185)

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
class ArchiveAnomaly:
    """An anomalous inbox/archive file surfaced by prescan's health rails.

    Two rails populate this record, both defensive safety rails for the
    silent-content-loss bug class (epic #563, mission #746):

      1. ``scan_archive_anomalies()`` (#568): a file in ``02-Inbox-Processed/``
         whose status is NOT ``processed`` (misfiled note).
      2. ``scan_processed_without_routing_log()`` (#746): a note whose status
         IS ``processed`` but whose filename is absent from the routing log —
         the silent-loss signature (a note marked done without any recorded
         route). Scans BOTH ``01-Inbox/`` and ``02-Inbox-Processed/``.

    Each rail emits one anomaly per anomalous file; the prescan agent (or
    operator) decides what to do based on the visible alarm.
    """

    path: str
    status_raw: Optional[str]
    # "unprocessed" | "needs-review" | "unknown-treated-as-unprocessed"
    # | "parse-failure" | "processed-without-routing-log"
    classification: str
    warning: str


# #568 — module-level constant; operator-tuneable via code edit.
# 5000 is a generous ceiling at 2026-06-08 archive scale (hundreds of files).
ARCHIVE_SCAN_CAP = 5000


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
    # #185 — new fields. Additive; existing consumers that only read
    # unprocessed_paths / archived continue to work.
    parse_failures: list = field(default_factory=list)  # [{"path": ..., "reason": ...}]
    dedup_skipped: list = field(default_factory=list)  # [{"path": ..., "filename": ..., "existing_issue": int|None}]
    marker_cleanup_needed: list = field(default_factory=list)  # [<abs path>]
    # #568 — defensive safety rail for the silent-content-loss bug class (#563).
    archive_anomalies: list = field(default_factory=list)  # [ArchiveAnomaly as dict]


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


def _detect_malformation(text: str) -> Optional[str]:
    """Detect FR-005 frontmatter malformations. Returns reason or None.

    The 4 malformation classes (in detection order, first match wins):

      1. UTF-8 BOM at start of file
      2. Leading non-blank whitespace before the opening `---` (distinct
         from mission-027's leading-blank-line case, which is intentionally
         classified as `unprocessed` for backward compatibility)
      3. Missing closing `---` (the opening fence is present but no
         closing fence is found)

    YAML-parse-error detection happens later in `classify_file` because we
    need the extracted block to feed `yaml.safe_load`.

    See contracts/prescan-classifier.md for the authoritative spec.
    """
    # 1. UTF-8 BOM (Python text-mode read translates the BOM bytes to U+FEFF).
    if text.startswith("﻿"):
        return "UTF-8 BOM at start of file"

    # Find the first non-blank line and its position.
    lines = text.splitlines()
    first_non_blank_idx = next(
        (i for i, line in enumerate(lines) if line.strip()), None
    )
    if first_non_blank_idx is None:
        return None  # entirely blank file — no frontmatter at all, not a malformation

    first_non_blank = lines[first_non_blank_idx].rstrip()

    # 2. If the first non-blank line is not exactly `---` but a standalone
    #    `---` line appears within the first ~10 lines, treat as malformed
    #    leading content. Cases without any standalone `---` fall through
    #    to the "no frontmatter" path and are routed normally — the
    #    routing-log dedup (FR-003) provides the safety net for any
    #    duplicate-issue risk arising from those cases.
    if first_non_blank != "---":
        head_text = "\n".join(lines[: min(10, len(lines))])
        if "\n---\n" in head_text or head_text.endswith("\n---"):
            return "leading whitespace or content before opening --- fence"
        return None  # genuinely no frontmatter

    # 3. Opening `---` found; check for closing `---`.
    for j in range(first_non_blank_idx + 1, len(lines)):
        if lines[j].strip() == "---":
            return None  # frontmatter delimiters complete
    return "missing closing --- (unterminated frontmatter block)"


# Stable prefix for the felix-capture parse-error callout marker.
# Defined here for the cleanup-detection path; the marker WRITER lives in
# scripts/inbox/inject_parse_error_marker.py (WP03).
_FELIX_CAPTURE_MARKER_PREFIX = "> [!error] felix-capture:"


def _has_parse_error_marker(text: str) -> bool:
    """Return True if the note body has a felix-capture parse-error marker
    near the top.

    Used to flag files for `marker_cleanup_needed` when the file now parses
    cleanly but a stale marker from a previous run is still in place
    (FR-010 auto-cleanup).
    """
    # Skip leading whitespace, then frontmatter (if present), then look at
    # the next few body lines.
    lines = text.splitlines()
    # Walk past leading blanks.
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    # Walk past frontmatter (opening fence + body + closing fence) if present.
    if i < len(lines) and lines[i].strip() == "---":
        j = i + 1
        while j < len(lines) and lines[j].strip() != "---":
            j += 1
        if j < len(lines):
            i = j + 1  # skip past closing fence
    # Skip blank lines after frontmatter close.
    while i < len(lines) and not lines[i].strip():
        i += 1
    # Look at the next ~3 body lines.
    for k in range(i, min(i + 3, len(lines))):
        if lines[k].startswith(_FELIX_CAPTURE_MARKER_PREFIX):
            return True
    return False


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

    # FR-005: detect non-YAML malformations before the existing parse path.
    malformation = _detect_malformation(text)
    if malformation is not None:
        return InboxFile(
            path=path,
            mtime_utc=mtime_utc,
            status_raw=None,
            classification="parse-failure",
            warning=malformation,
            parse_failure_reason=malformation,
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
    except yaml.YAMLError as exc:
        # FR-005 (d): invalid YAML inside frontmatter block.
        reason = f"invalid YAML inside frontmatter block: {str(exc)[:200]}"
        return InboxFile(
            path=path,
            mtime_utc=mtime_utc,
            status_raw=None,
            classification="parse-failure",
            warning=reason,
            parse_failure_reason=reason,
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
    elif status_raw == "needs-review":
        # #746 (FR-008 / D13): ``needs-review`` is a TERMINAL inbox state. The
        # note has been triaged and deliberately parked for human attention; it
        # must NOT reprocess every tick. Kept out of ``unprocessed`` (below) and
        # out of the ``processed-without-routing-log`` health rail (not
        # ``processed``). Distinct classification so it drops out of every
        # actionable list without being mistaken for a routable note.
        classification = "needs-review"
    else:
        warning = (
            f"unknown status '{status_raw}'; treated as unprocessed (safety default)"
        )
        classification = "unknown-treated-as-unprocessed"

    # FR-010 marker cleanup detection: if the file parses cleanly but has a
    # stale felix-capture parse-error marker in its body, flag it so the
    # downstream consumer can strip the marker.
    has_stale_error_marker = _has_parse_error_marker(text)

    return InboxFile(
        path=path,
        mtime_utc=mtime_utc,
        status_raw=status_raw,
        classification=classification,
        warning=warning,
        has_stale_error_marker=has_stale_error_marker,
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
# Archive anomaly scan (#568) — defensive safety rail
# ---------------------------------------------------------------------------


def scan_archive_anomalies(
    processed_dir: Path,
    now_utc: datetime,
) -> tuple[list[ArchiveAnomaly], list[str]]:
    """Scan ``02-Inbox-Processed/`` for files whose status is NOT 'processed'.

    Defensive safety rail per #568: converts the silent-content-loss bug class
    (#563) from invisible to visible. Read-only — no remediation.

    Returns ``(anomalies, warnings)``:
      - ``anomalies``: one ``ArchiveAnomaly`` per non-``processed`` ``.md`` file
        (excluding daily logs by filename prefix)
      - ``warnings``: missing-dir warning OR cap-applied warning when triggered;
        appended to ``PrescanResult.warnings`` by the caller

    Filters daily-log files by filename prefix ``inbox-processing-`` (these are
    pre-existing pipeline outputs, not routed inbox notes).

    Caps the scan at ``ARCHIVE_SCAN_CAP`` files (mtime descending) when the
    archive contains more — protects the latency budget.

    Safe on a missing ``processed_dir`` — returns ``([], [<warning>])``.
    """
    warnings: list[str] = []
    if not processed_dir.exists():
        warnings.append(
            f"archive scan: processed_dir does not exist at {processed_dir}"
        )
        return [], warnings

    # Collect .md files non-recursively, exclude daily logs by filename prefix.
    candidates = [
        p
        for p in processed_dir.iterdir()
        if p.is_file()
        and p.suffix == ".md"
        and not p.name.startswith("inbox-processing-")
    ]

    # Apply cap (most-recent mtime first) when archive grows beyond the ceiling.
    if len(candidates) > ARCHIVE_SCAN_CAP:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        skipped = len(candidates) - ARCHIVE_SCAN_CAP
        candidates = candidates[:ARCHIVE_SCAN_CAP]
        warnings.append(
            f"archive scan: cap_applied (scanned {ARCHIVE_SCAN_CAP} most-recent; "
            f"skipped {skipped} older files)"
        )

    anomalies: list[ArchiveAnomaly] = []
    for path in candidates:
        info = classify_file(path, now_utc)
        # Healthy case — exact 'processed' status, nothing to report.
        if info.status_raw == "processed":
            continue

        # Anomaly classification (mirrors the existing prescan vocabulary):
        if info.classification == "parse-failure":
            kind = "parse-failure"
            warning = (
                f"parse-failure in archive: {info.parse_failure_reason or info.warning}"
            )
        elif info.status_raw == "unprocessed":
            kind = "unprocessed"
            warning = "status:unprocessed found in 02-Inbox-Processed/"
        elif info.status_raw == "needs-review":
            kind = "needs-review"
            warning = (
                "status:needs-review found in 02-Inbox-Processed/ "
                "(belongs in 01-Inbox/)"
            )
        elif info.status_raw is None:
            kind = "unknown-treated-as-unprocessed"
            warning = "no status field; treated as unprocessed"
        else:
            kind = "unknown-treated-as-unprocessed"
            warning = (
                f"unknown status:{info.status_raw}; treated as unprocessed"
            )

        anomalies.append(
            ArchiveAnomaly(
                path=str(path),
                status_raw=info.status_raw,
                classification=kind,
                warning=warning,
            )
        )

    return anomalies, warnings


# ---------------------------------------------------------------------------
# processed-without-routing-log health rail (#746) — silent-loss signature
# ---------------------------------------------------------------------------

# Warning text is load-bearing: the agent's Step 1 IDLE gate (WP04) surfaces it
# verbatim, so keep it stable.
_SILENT_LOSS_WARNING = (
    "status:processed but no routing-log entry (silent-loss signature #746)"
)


def _md_candidates(directory: Path) -> list[Path]:
    """Non-recursive ``.md`` files in ``directory``, excluding daily logs.

    Mirrors ``scan_archive_anomalies``' collection rule: skips the
    ``inbox-processing-`` daily-log outputs (pipeline artifacts, not notes).
    Returns ``[]`` for a missing/unreadable directory.
    """
    try:
        return [
            p
            for p in directory.iterdir()
            if p.is_file()
            and p.suffix == ".md"
            and not p.name.startswith("inbox-processing-")
        ]
    except OSError:
        return []


def scan_processed_without_routing_log(
    inbox_dir: Path,
    processed_dir: Path,
    now_utc: datetime,
    reader,
) -> tuple[list[ArchiveAnomaly], list[str]]:
    """Flag ``status:processed`` notes whose filename is absent from the log.

    The #746 health rail. A note is marked ``processed`` only after every block
    is routed AND its routing-log entry is written (FR-001/FR-011 log-before-mark;
    ``empty`` notes get a ``kind=empty`` entry). So a ``processed`` note with no
    routing-log entry is the **silent-loss signature**: it was marked done
    without any recorded route. This rail makes that visible (read-only; no
    remediation) so WP04's IDLE gate can alarm.

    Scans BOTH ``01-Inbox/`` (processed notes await the 7-day archive there) and
    ``02-Inbox-Processed/``. Reuses ``ARCHIVE_SCAN_CAP`` and the
    ``inbox-processing-`` daily-log exclusion.

    Presence is checked with WP01's note-level ``reader.has(filename)`` — any
    routing-log entry (block-keyed or legacy) satisfies it, so correctly
    finalized notes (including ``empty``-disposition notes) never trip the rail.

    ``needs-review`` and ``unprocessed`` notes are ignored (not ``processed``);
    parse-failure notes are likewise skipped (no reliable ``status``).

    Returns ``(anomalies, warnings)``. ``warnings`` carries a cap-applied notice
    when the combined candidate set exceeds ``ARCHIVE_SCAN_CAP``.
    """
    warnings: list[str] = []

    # Combine candidates from both directories (each tagged with its source so
    # the cap can bound total work across the pair).
    candidates = _md_candidates(inbox_dir) + _md_candidates(processed_dir)

    # Apply the shared cap (most-recent mtime first) to protect the latency
    # budget when the corpus grows large.
    if len(candidates) > ARCHIVE_SCAN_CAP:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        skipped = len(candidates) - ARCHIVE_SCAN_CAP
        candidates = candidates[:ARCHIVE_SCAN_CAP]
        warnings.append(
            f"health rail: cap_applied (scanned {ARCHIVE_SCAN_CAP} most-recent; "
            f"skipped {skipped} older files)"
        )

    anomalies: list[ArchiveAnomaly] = []
    for path in candidates:
        info = classify_file(path, now_utc)
        # Only 'processed' notes can exhibit the silent-loss signature. Every
        # other state (unprocessed / needs-review / unknown / parse-failure) is
        # out of scope for this rail.
        if info.status_raw != "processed":
            continue
        if reader.has(path.name):
            continue  # correctly finalized — has ≥1 routing-log entry.
        anomalies.append(
            ArchiveAnomaly(
                path=str(path),
                status_raw=info.status_raw,
                classification="processed-without-routing-log",
                warning=_SILENT_LOSS_WARNING,
            )
        )

    return anomalies, warnings


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
    # #568 — defensive safety rail. Section is OMITTED when no anomalies
    # to avoid log noise on healthy ticks (the common case).
    if result.archive_anomalies:
        lines.append("")
        lines.append(f"### archive_anomalies (count={len(result.archive_anomalies)})")
        for a in result.archive_anomalies:
            # a is either an ArchiveAnomaly instance OR an asdict() dict
            # (depending on call site); handle both shapes defensively.
            path = a["path"] if isinstance(a, dict) else a.path
            warning = a["warning"] if isinstance(a, dict) else a.warning
            lines.append(f"- {path}: {warning}")
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
    parse_failed = [f for f in classified if f.classification == "parse-failure"]

    _emit_stderr(f"prescan: archiving {len(stale)} stale files")
    archived = archive_stale(stale, inbox_processed)

    warnings: list[dict] = []
    for f in classified:
        if f.warning and f.classification == "unknown-treated-as-unprocessed":
            warnings.append({"path": str(f.path), "reason": f.warning})
    for a in archived:
        if not a.success and a.warning:
            warnings.append({"path": a.src, "reason": a.warning})

    # #746 (D9) — routing-log READER for the health rail. The note-level
    # routing-log DEDUP that used to filter ``unprocessed`` notes here is
    # REMOVED. Per D9 a note is treated as done by its terminal *status*
    # (``processed``/``needs-review``, resolved upstream in classification), not
    # by routing-log filename presence. Per-block idempotency now lives in
    # finalize (WP02's block-keyed ``has_block``), so an ``unprocessed`` note
    # whose blocks are mid-flight — some already logged from a prior failed tick
    # — MUST still be handed to the agent so finalize can reconcile the
    # remaining blocks. Filtering it out on filename presence would strand it
    # (the old silent-loss vector this mission closes).
    #
    # The reader is still built (fail-safe) for the processed-without-routing-log
    # health rail below; ``reader is None`` means the log module is unavailable
    # and the rail is skipped rather than emitting false positives.
    dedup_skipped: list[dict] = []  # retained (always empty) for JSON-shape stability
    reader = None
    try:
        # Local import keeps prescan importable when routing_log is missing
        # (e.g., during partial deploys).
        # Deduplicate module loading: if routing_log is already in sys.modules
        # (e.g. scripts/inbox/ on sys.path), reuse that object so any
        # monkeypatching of DEFAULT_ROUTING_LOG_PATH applies correctly.
        import sys as _prescan_sys
        _bare_rl = _prescan_sys.modules.get("routing_log")
        if _bare_rl is not None:
            _prescan_sys.modules.setdefault("scripts.inbox.routing_log", _bare_rl)
        from scripts.inbox.routing_log import RoutingLogReader  # type: ignore[import-not-found]
        reader = RoutingLogReader()
    except ImportError:
        warnings.append({
            "path": "scripts/inbox/routing_log.py",
            "reason": (
                "routing_log module not importable; "
                "processed-without-routing-log health rail disabled this run"
            ),
        })
        reader = None
    except Exception as exc:  # pragma: no cover — defensive
        warnings.append({
            "path": "routing-log",
            "reason": f"routing log reader init failed: {exc}; health rail disabled this run",
        })
        reader = None

    # Dedup shift (D9): unprocessed notes are handed to the agent every tick
    # regardless of routing-log presence. Terminal status removes a note from
    # this list upstream (via classification), not a filename filter here.
    unprocessed_filtered: list[InboxFile] = list(unprocessed)

    # #185 — FR-005 parse_failures list.
    parse_failures_json = [
        {"path": str(f.path), "reason": f.parse_failure_reason or (f.warning or "")}
        for f in parse_failed
    ]

    # #185 — FR-010 marker_cleanup_needed list. Files that parse cleanly now
    # but still have a stale felix-capture marker in their body.
    # Exclude successfully-archived files: their inbox path no longer exists
    # for the strip helper, and once archived they are not user-facing.
    archived_src_paths = {a.src for a in archived if a.success}
    marker_cleanup_needed = [
        str(f.path)
        for f in classified
        if f.has_stale_error_marker and str(f.path) not in archived_src_paths
    ]

    # #568 — defensive archive-anomaly scan. Read-only; converts any silent
    # regression of the #563 bug class into a visible alarm. Runs AFTER
    # archive_stale so freshly-moved files (which we just put in 'processed'
    # state) aren't double-checked.
    archive_anomalies, archive_scan_warnings = scan_archive_anomalies(
        inbox_processed, started
    )
    for w in archive_scan_warnings:
        warnings.append({"path": "archive-scan", "reason": w})

    # #746 — processed-without-routing-log health rail. Read-only; surfaces the
    # silent-loss signature (a note marked ``processed`` with no routing-log
    # entry) so WP04's Step 1 IDLE gate can alarm. Scans BOTH the inbox and the
    # archive. Runs AFTER archive_stale so a freshly-moved processed note is
    # checked in its new home. Skipped (fail-safe) when the routing log is
    # unreadable, to avoid a false-positive storm.
    if reader is not None:
        silent_loss_anomalies, health_rail_warnings = (
            scan_processed_without_routing_log(inbox, inbox_processed, started, reader)
        )
        archive_anomalies.extend(silent_loss_anomalies)
        for w in health_rail_warnings:
            warnings.append({"path": "health-rail", "reason": w})
    else:
        warnings.append({
            "path": "health-rail",
            "reason": (
                "routing log unreadable; processed-without-routing-log rail "
                "skipped this run"
            ),
        })

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
        unprocessed_count=len(unprocessed_filtered),
        unprocessed_paths=sorted(str(f.path) for f in unprocessed_filtered),
        archived_count=len(archived_json),
        archived=archived_json,
        warnings=warnings,
        parse_failures=parse_failures_json,
        dedup_skipped=dedup_skipped,
        marker_cleanup_needed=marker_cleanup_needed,
        archive_anomalies=[asdict(a) for a in archive_anomalies],
    )

    _emit_stderr("prescan: writing daily log")
    log_dir, fallback_warning = _log_dir()
    if fallback_warning:
        _emit_stderr(f"prescan: WARN {fallback_warning}")
    try:
        _append_daily_log(log_dir, result, duration_ms, archived, unprocessed_filtered)
    except OSError as e:
        _emit_stderr(f"prescan: WARN daily log write failed: {e}")

    sys.stdout.write(json.dumps(asdict(result)) + "\n")
    sys.stdout.flush()
    _emit_stderr(
        f"prescan: done unprocessed={result.unprocessed_count} "
        f"archived={result.archived_count} "
        f"archive_anomalies={len(result.archive_anomalies)} "
        f"warnings={len(result.warnings)} "
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
