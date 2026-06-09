#!/usr/bin/env python3
"""Route a journal entry into the dated daily journal file.

Mission: capture-d6-helpers-extraction-01KTMS5Q (WP02).
FRs covered:
  - FR-003: append content as a level-2 section to
    ``<paths.journal>/Journal YYYY-MM-DD HHmm.md`` (filename derived from
    ``--datetime``); create the file with canonical frontmatter if absent.
  - FR-010: atomic write (write-temp + fsync + ``os.replace``).
  - FR-011: path resolution via ``scripts.vault.resolver`` (the canonical
    interface to ``scripts/vault/paths.json``).

Mandatory invocation form (NFR-004, ``[[feedback_helper_m_invocation_form]]``):

    python3 -m scripts.inbox.route_journal_entry \\
        --content-file <abs-path> --datetime <ISO 8601 local>

The script-path form (``python3 scripts/inbox/route_journal_entry.py ...``)
is forbidden — it has caused two production failures with
``ModuleNotFoundError``.

Exit codes:
  - 0: success
  - 1: invalid input (missing content file, malformed datetime, write
    failure)

Stdlib only. No third-party deps.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Path resolution — bridge to scripts.vault.resolver
# ---------------------------------------------------------------------------
#
# The helper itself only depends on a single function: "given a logical
# vault name, return an absolute path". We thread that through a private
# module-level shim ``_get_vault_path`` so tests can monkeypatch it
# without touching the real registry on disk. The shim defers import of
# scripts.vault.resolver so simply importing this module from
# ``tests/inbox/conftest.py`` (which only adds scripts/inbox/ to
# sys.path) does not fail when the repo root is not yet on sys.path.

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_vault_path(name: str) -> str:
    """Return the absolute vault path for ``name`` via the registry.

    Defers import of ``scripts.vault.resolver`` until first call so the
    module is importable in test environments that only add
    ``scripts/inbox/`` to sys.path. Adds the repo root to sys.path on
    demand if needed.
    """
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts.vault.resolver import get_vault_path  # noqa: WPS433

    return get_vault_path(name)


def resolve_journal_dir() -> Path:
    """Return the journal directory as a :class:`pathlib.Path`."""
    return Path(_get_vault_path("journal"))


# ---------------------------------------------------------------------------
# Filename + heading shapes (FR-003)
# ---------------------------------------------------------------------------

SHORT_CONTENT_THRESHOLD = 8  # chars; below this -> heading is bare timestamp
HEADING_EXCERPT_LIMIT = 60  # chars of trimmed body shown after the em-dash


def target_filename(dt: datetime) -> str:
    """Return the ``Journal YYYY-MM-DD HHmm.md`` filename for ``dt``."""
    return dt.strftime("Journal %Y-%m-%d %H%M.md")


def _excerpt(content: str, limit: int = HEADING_EXCERPT_LIMIT) -> str:
    """Return a single-line trimmed excerpt of ``content``.

    Collapses internal whitespace, strips leading/trailing whitespace,
    and truncates to ``limit`` characters. Used for the level-2 heading
    after the em-dash.
    """
    flat = " ".join(content.split())
    return flat[:limit].strip()


def make_heading(dt: datetime, content: str) -> str:
    """Return the level-2 heading line for a journal section.

    - ``## HH:mm`` when ``content`` is shorter than
      :data:`SHORT_CONTENT_THRESHOLD` chars (after stripping).
    - ``## HH:mm — <excerpt>`` otherwise.
    """
    timestamp = dt.strftime("## %H:%M")
    stripped = content.strip()
    if len(stripped) < SHORT_CONTENT_THRESHOLD:
        return timestamp
    excerpt = _excerpt(stripped)
    return f"{timestamp} — {excerpt}"


# ---------------------------------------------------------------------------
# Frontmatter helper
# ---------------------------------------------------------------------------


def _frontmatter(dt: datetime) -> str:
    """Return canonical journal frontmatter as a string ending in ``---\\n``.

    Shape (per WP DoD / contracts/helper-cli.md):
        id              — short random id, stable per-file
        doc_type        — fixed "journal"
        created         — YYYY-MM-DD (date of dt, local)
        last_validated  — YYYY-MM-DD (same as created at creation time)
    """
    note_id = "j" + secrets.token_hex(4)
    created = dt.strftime("%Y-%m-%d")
    return (
        "---\n"
        f"id: {note_id}\n"
        "doc_type: journal\n"
        f"created: {created}\n"
        f"last_validated: {created}\n"
        "---\n"
    )


# ---------------------------------------------------------------------------
# Atomic write (FR-010) — mirrors scripts/inbox/inject_parse_error_marker.py
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically via tempfile + ``os.replace``.

    Pattern:
      1. ``mkstemp`` in the target directory so ``os.replace`` is on the
         same filesystem (rename atomicity).
      2. Write the body, ``flush`` + ``fsync`` so the page cache is
         flushed before the rename.
      3. ``os.replace`` swaps the tempfile into place atomically.
      4. On exception, unlink the tempfile.

    Sets mode 0o664 on new files (no need to preserve mode here — the
    journal file is owned by the same writer across runs; preservation
    is unnecessary because the file is always created or rewritten with
    the same intended mode).
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, 0o664)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# File mutation primitives
# ---------------------------------------------------------------------------


def ensure_journal_file(path: Path, dt: datetime) -> None:
    """Create the journal file with canonical frontmatter if absent.

    Idempotent: if the file already exists, do nothing.
    """
    if path.exists():
        return
    _atomic_write(path, _frontmatter(dt) + "\n")


def append_section(path: Path, heading: str, content: str) -> None:
    """Append a new ``heading`` + ``content`` block to an existing journal.

    Reads the whole file, appends ``\\n<heading>\\n\\n<content>\\n``,
    then atomic-writes the result. Preserves all existing frontmatter
    and prior sections verbatim.
    """
    existing = path.read_text(encoding="utf-8")
    # Guarantee a blank line before the new heading.
    if not existing.endswith("\n"):
        existing += "\n"
    if not existing.endswith("\n\n"):
        existing += "\n"
    section = f"{heading}\n\n{content}\n"
    _atomic_write(path, existing + section)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _emit_error(kind: str, detail: str) -> None:
    """Emit a structured JSON error line to stderr (NFR-005)."""
    print(json.dumps({"error": kind, "detail": detail}), file=sys.stderr)


def _parse_iso_datetime(raw: str) -> datetime:
    """Parse an ISO 8601 datetime; raise ``ValueError`` on failure.

    Accepts both ``+HH:MM`` offsets (``2026-06-08T07:32:00-04:00``) and
    the legacy ``Z`` suffix (``2026-06-08T07:32:00Z``).
    """
    raw = raw.strip()
    # Python 3.11 fromisoformat handles "Z"; for safety on 3.10 swap manually.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.inbox.route_journal_entry",
        description=(
            "Append journal content to a dated 08-Journal/Journal "
            "YYYY-MM-DD HHmm.md file, creating it (with canonical "
            "frontmatter) if absent."
        ),
    )
    parser.add_argument(
        "--content-file",
        required=True,
        help="Absolute path to a file containing the journal content (raw text).",
    )
    parser.add_argument(
        "--datetime",
        dest="datetime_iso",
        required=True,
        help="ISO 8601 datetime with timezone (e.g., 2026-06-08T07:32:00-04:00).",
    )
    args = parser.parse_args(argv)

    # --- Parse + validate inputs -------------------------------------------
    try:
        dt = _parse_iso_datetime(args.datetime_iso)
    except ValueError as exc:
        _emit_error("invalid_datetime", f"{args.datetime_iso!r}: {exc}")
        return 1

    content_path = Path(args.content_file)
    if not content_path.exists():
        _emit_error("missing_content_file", f"content_file not found: {content_path}")
        return 1

    try:
        content = content_path.read_text(encoding="utf-8")
    except OSError as exc:
        _emit_error("read_failed", f"could not read {content_path}: {exc}")
        return 1

    # --- Resolve + ensure target -------------------------------------------
    try:
        journal_dir = resolve_journal_dir()
    except Exception as exc:  # registry / unknown name
        _emit_error("vault_resolve_failed", str(exc))
        return 1

    target = journal_dir / target_filename(dt)
    heading = make_heading(dt, content)

    try:
        ensure_journal_file(target, dt)
        append_section(target, heading, content.rstrip("\n"))
    except OSError as exc:
        _emit_error("write_failed", f"{target}: {exc}")
        return 1

    print(f"journal_path={target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
