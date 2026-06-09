#!/usr/bin/env python3
"""Mark an inbox note as processed (atomic frontmatter mutation).

Sets `status: processed` and `processed_at: <ISO 8601 UTC>` on the note's
YAML frontmatter, preserving all other fields, key order, and body
verbatim. Idempotent on already-processed notes.

CLI (mandatory `-m` invocation form per NFR-004 /
[[feedback_helper_m_invocation_form]]):

    python3 -m scripts.inbox.mark_processed --path <abs-path-to-note>

Exit codes:
    0  success (including idempotent no-op)
    1  validation error (missing file, no frontmatter)
    3  refusal: --path is under `04-Growth/_private/` (C-001)

Stdlib only (NFR-002): no requests / httpx / pydantic / PyYAML /
python-frontmatter. Frontmatter parsing is a minimal regex-based parser
sufficient for the simple key-value frontmatter used in inbox notes.

Atomic write pattern mirrors `scripts/inbox/inject_parse_error_marker.py`:
write-temp + fsync + os.replace, with the original file mode preserved.

References: FR-001, FR-002, FR-008, FR-009, FR-010, C-001.
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PRIVATE_PATH_MARKER = "04-Growth/_private"

# Frontmatter line shape: `key: value` (whitespace-tolerant). The values
# we round-trip in inbox notes are simple scalars or single-line lists
# (e.g. `tags: [inbox, mobile]`); multi-line YAML values are out of scope
# for this helper (documented in WP01 Risks).
_FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_\-]*)\s*:\s*(.*)$")


def read_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-ish frontmatter from `text`.

    Returns `(frontmatter_dict, body_string)`. Preserves insertion order
    of keys (built-in dict ordering since 3.7). Raises `ValueError` if
    the file does not start with `---\\n` or has no closing `---`.

    Lines inside the frontmatter block that don't match the simple
    `key: value` shape are skipped (not common in our notes; preserving
    them through a round-trip is out of scope).
    """
    if not text.startswith("---\n"):
        raise ValueError("no opening frontmatter fence (`---`)")

    lines = text.split("\n")
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            close_idx = i
            break
    if close_idx is None:
        raise ValueError("no closing frontmatter fence (`---`)")

    fm: dict[str, str] = {}
    for raw in lines[1:close_idx]:
        m = _FRONTMATTER_LINE_RE.match(raw)
        if m:
            key, value = m.group(1), m.group(2)
            fm[key] = value

    # Body is everything after the closing fence and its newline.
    body_lines = lines[close_idx + 1:]
    body = "\n".join(body_lines)
    return fm, body


def write_frontmatter(fm: dict, body: str) -> str:
    """Serialize `fm` + `body` back into the on-disk form.

    Output shape: `---\\n<key: value>\\n...\\n---\\n<body>`. Key order is
    preserved from `fm`'s insertion order.
    """
    fm_lines = [f"{k}: {v}" for k, v in fm.items()]
    fm_block = "---\n" + "\n".join(fm_lines) + "\n---\n"
    return fm_block + body


def _atomic_write(path: Path, content: str) -> None:
    """Write to a tempfile in the same directory, then os.replace.

    Mirrors `scripts/inbox/inject_parse_error_marker.py::_atomic_write`:
    preserves the original target file's mode (or applies 0o664 for new
    files) so cross-user access (e.g. ob sync running as a different
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
            fh.flush()
            os.fsync(fh.fileno())
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
            kind = "preserved"
        except FileNotFoundError:  # pragma: no branch
            # Defensive: mark_processed always operates on an existing
            # file (callers validate via Path.exists() before invoking),
            # so this branch is practically unreachable. Mirrors the
            # precedent helper which has the same defensive `(new)` arm.
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
        except OSError:  # pragma: no cover
            # If the tmp was already moved or never existed, the unlink
            # failure is benign — the caller's exception is the signal.
            pass
        raise


def mark_processed(path: Path) -> int:
    """Atomically set `status: processed` + `processed_at` on `path`.

    Returns the exit code per the CLI contract (0/1/3).
    """
    if not path.exists():
        print(
            f'{{"error": "missing_file", "detail": "{path} does not exist"}}',
            file=sys.stderr,
        )
        return 1

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f'{{"error": "read_failed", "detail": "{exc}"}}',
            file=sys.stderr,
        )
        return 1

    try:
        fm, body = read_frontmatter(text)
    except ValueError as exc:
        print(
            f'{{"error": "no_frontmatter", "detail": "{exc}"}}',
            file=sys.stderr,
        )
        return 1

    # Idempotency check (FR-002): if already processed, no-op.
    if fm.get("status") == "processed":
        return 0

    # Mutate. Keep existing keys, only modify/add the two we own.
    fm["status"] = "processed"
    fm["processed_at"] = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    new_text = write_frontmatter(fm, body)
    _atomic_write(path, new_text)
    return 0


def _is_private_path(path_str: str) -> bool:
    """Return True if `path_str` is under `04-Growth/_private/` (C-001)."""
    return PRIVATE_PATH_MARKER in path_str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mark an inbox note as processed by atomically writing "
            "`status: processed` + `processed_at` to its frontmatter."
        )
    )
    parser.add_argument(
        "--path",
        required=True,
        help="Absolute path to the note in `01-Inbox/`.",
    )
    args = parser.parse_args(argv)

    # Refusal check (C-001) happens BEFORE any disk read.
    if _is_private_path(args.path):
        print(
            '{"error": "refused", "detail": "path is under 04-Growth/_private/"}',
            file=sys.stderr,
        )
        return 3

    return mark_processed(Path(args.path))


if __name__ == "__main__":
    sys.exit(main())
