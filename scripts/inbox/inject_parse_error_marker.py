#!/usr/bin/env python3
"""Inject (or refresh) the felix-capture parse-error callout marker.

The marker is an Obsidian admonition the agent writes into a malformed note
so the human reading it in Obsidian sees a clear "I tried, here's why":

    > [!error] felix-capture: could not parse frontmatter on 2026-05-12.
    > See issue #1234 ("Inbox quality" issue for this run).

Insertion rules:
  - If the file starts with `---` and a closing `---` is detectable, insert
    immediately after the closing fence (and a single trailing blank line).
  - Otherwise, insert at the very top.
  - Idempotent: if a marker already exists in the top of the body, replace
    that line in place rather than stacking duplicates.

Atomic write: write to a tempfile in the same directory then os.replace.

See kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/contracts/
callout-marker.md for the authoritative contract.
"""
from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MARKER_PREFIX = "> [!error] felix-capture:"


def _build_marker_line(issue_number: int, date_str: str) -> str:
    return (
        f"> [!error] felix-capture: could not parse frontmatter on {date_str}. "
        f'See issue #{issue_number} ("Inbox quality" issue for this run).'
    )


def _find_frontmatter_close_idx(lines: list[str]) -> int | None:
    """Return the index of the closing `---` line if frontmatter is detected.

    Detection: first non-blank line is exactly `---` (BOM-prefixed forms
    are recognized), then a later line is also exactly `---`. Returns the
    index of the closing fence; None if no usable frontmatter pair is found.
    """
    first_non_blank_idx = next(
        (i for i, line in enumerate(lines) if line.strip()), None
    )
    if first_non_blank_idx is None:
        return None
    if lines[first_non_blank_idx].lstrip("﻿").strip() != "---":
        return None
    for j in range(first_non_blank_idx + 1, len(lines)):
        if lines[j].strip() == "---":
            return j
    return None


def _insertion_point(lines: list[str]) -> int:
    """Return the line index at which the marker should be inserted.

    After-frontmatter: the first non-blank line after the closing `---`
    (i.e., body start). The original blank line(s) between fence and body
    stay between fence and marker; we'll add a trailing blank as needed.

    No-frontmatter: 0.
    """
    close_idx = _find_frontmatter_close_idx(lines)
    if close_idx is None:
        return 0
    insert_at = close_idx + 1
    while insert_at < len(lines) and not lines[insert_at].strip():
        insert_at += 1
    return insert_at


def _existing_marker_idx(lines: list[str], scan_start: int) -> int | None:
    """Find an existing marker line within ~3 lines of scan_start.

    Bounded so user content deeper in the body cannot be clobbered.
    Pairs with `_insertion_point`, which advances scan_start past all
    blank lines after the closing fence so a marker at the actual
    body-start is inside the window.
    """
    for k in range(scan_start, min(scan_start + 3, len(lines))):
        if lines[k].startswith(MARKER_PREFIX):
            return k
    return None


def inject_marker(path: Path, issue_number: int, date_str: str) -> bool:
    """Insert or refresh the marker. Returns True if the file changed.

    Idempotency: if a marker exists at the expected location, replace it in
    place (same line index) so repeated invocations don't stack.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    has_trailing_newline = text.endswith("\n")

    insert_at = _insertion_point(lines)
    new_marker = _build_marker_line(issue_number, date_str)
    existing = _existing_marker_idx(lines, insert_at)

    if existing is not None:
        if lines[existing] == new_marker:
            return False
        lines[existing] = new_marker
    else:
        lines.insert(insert_at, new_marker)
        if insert_at + 1 < len(lines) and lines[insert_at + 1].strip():
            lines.insert(insert_at + 1, "")

    new_text = "\n".join(lines)
    if has_trailing_newline:
        new_text += "\n"
    _atomic_write(path, new_text)
    return True


def _atomic_write(path: Path, content: str) -> None:
    """Write to a tempfile in the same directory, then os.replace.

    Preserves the original target file's mode (or applies 0o664 for new
    files) so that cross-user access (e.g. ob sync running as a different
    user) is not broken by the temp file's umask-derived 0o600.
    """
    parent = path.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
            kind = "preserved"
        except FileNotFoundError:
            mode = 0o664
            kind = "new"
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        print(
            f"INFO: atomic_write {path} mode={oct(mode)} ({kind})",
            file=sys.stderr,
        )
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inject the felix-capture parse-error callout marker."
    )
    parser.add_argument("filename", help="Absolute path to the note.")
    parser.add_argument(
        "issue", type=int, help="GitHub issue number for the Inbox quality issue."
    )
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Marker date (YYYY-MM-DD). Defaults to UTC today.",
    )
    args = parser.parse_args(argv)

    path = Path(args.filename)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1
    try:
        changed = inject_marker(path, args.issue, args.date)
    except OSError as exc:
        print(f"ERROR: write failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"inject_parse_error_marker: {'updated' if changed else 'no change'} {path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
