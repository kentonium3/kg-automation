#!/usr/bin/env python3
"""Strip the felix-capture parse-error callout marker if present.

No-op when no marker is detected. Atomic write via tempfile + os.replace.
See contracts/callout-marker.md for the contract; FR-010 for auto-cleanup
semantics.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

MARKER_PREFIX = "> [!error] felix-capture:"


def _find_frontmatter_close_idx(lines: list[str]) -> int | None:
    first_non_blank_idx = next(
        (i for i, line in enumerate(lines) if line.strip()), None
    )
    if first_non_blank_idx is None:
        return None
    # BOM-prefixed `﻿---` is still legitimate opening frontmatter.
    if lines[first_non_blank_idx].lstrip("﻿").strip() != "---":
        return None
    for j in range(first_non_blank_idx + 1, len(lines)):
        if lines[j].strip() == "---":
            return j
    return None


def _marker_scan_start(lines: list[str]) -> int:
    """Return the line index from which to look for a marker.

    For a note with frontmatter: the first non-blank line after the
    closing `---`. For a note without frontmatter: line 0.
    """
    close_idx = _find_frontmatter_close_idx(lines)
    if close_idx is None:
        return 0
    start = close_idx + 1
    while start < len(lines) and not lines[start].strip():
        start += 1
    return start


def strip_marker(path: Path) -> bool:
    """Remove a marker line if present. Returns True if the file changed.

    Scans a bounded window (~3 lines from scan_start) so deeper content
    a user may have written cannot be clobbered.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    has_trailing_newline = text.endswith("\n")

    scan_start = _marker_scan_start(lines)
    target_idx: int | None = None
    for k in range(scan_start, min(scan_start + 3, len(lines))):
        if lines[k].startswith(MARKER_PREFIX):
            target_idx = k
            break
    if target_idx is None:
        return False

    del lines[target_idx]
    if target_idx < len(lines) and not lines[target_idx].strip():
        del lines[target_idx]

    new_text = "\n".join(lines)
    if has_trailing_newline:
        new_text += "\n"
    _atomic_write(path, new_text)
    return True


def _atomic_write(path: Path, content: str) -> None:
    parent = path.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strip the felix-capture parse-error callout marker."
    )
    parser.add_argument("filename", help="Absolute path to the note.")
    args = parser.parse_args(argv)

    path = Path(args.filename)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1
    try:
        changed = strip_marker(path)
    except OSError as exc:
        print(f"ERROR: write failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"strip_parse_error_marker: {'stripped' if changed else 'no marker'} {path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
