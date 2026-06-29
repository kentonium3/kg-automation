#!/usr/bin/env python3
"""Mark an inbox note as processed (atomic frontmatter mutation).

Sets `status: processed` and `processed_at: <ISO 8601 UTC>` on the note's
YAML frontmatter, preserving all other fields, key order, and body
verbatim. Idempotent on already-processed notes.

CLI (mandatory `-m` invocation form per NFR-004 /
[[feedback_helper_m_invocation_form]]):

    python3 -m scripts.inbox.mark_processed --path <abs-path-to-note>

Exit codes:
    0  success (including idempotent no-op); stdout carries a single-line
       JSON: {"finalized": true, "already_processed": <bool>, "status":
       "processed", "file_final_path": "<abs-path>"}
    1  validation error (missing file, no frontmatter, outside inbox root,
       unresolvable inbox registry)
    2  filesystem error (perm denied / write race); stderr carries the
       OSError detail as {"error": "fs_error", "detail": "<exc>"}
    3  refusal: --path is under `04-Growth/_private/` (C-001)

Stdlib only (NFR-002): no requests / httpx / pydantic / PyYAML /
python-frontmatter. Frontmatter parsing is a minimal regex-based parser
sufficient for the simple key-value frontmatter used in inbox notes.
`json` is stdlib; no new dependencies are introduced.

Atomic write pattern mirrors `scripts/inbox/inject_parse_error_marker.py`:
write-temp + fsync + os.replace, with the original file mode preserved.
On write failure the original note is left uncorrupted — `_atomic_write`
unlinks its temp file before re-raising, and `mark_processed` catches the
OSError to convert it to a clean exit 2.

References: FR-001, FR-002, FR-003, FR-004, FR-008, FR-009, FR-010, C-001.
"""
from __future__ import annotations

import argparse
import json
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


def read_frontmatter(text: str) -> tuple[dict, str, int]:
    """Parse YAML-ish frontmatter from `text`.

    Returns `(frontmatter_dict, body_string, leading_blank_lines)`. Preserves
    insertion order of keys (built-in dict ordering since 3.7) AND preserves
    the count of leading blank lines before the opening fence so the round-trip
    write can put them back. Raises `ValueError` if no opening or closing fence
    is found.

    Lines inside the frontmatter block that don't match the simple
    `key: value` shape are skipped (not common in our notes; preserving
    them through a round-trip is out of scope).

    Tolerates leading blank lines before the opening fence — Obsidian Templater
    and Wispr Flow emit notes with a single blank line above the frontmatter;
    `prescan.classify_file` already accepts that shape. This fix aligns
    `mark_processed`'s entry guard with the same convention so production
    capture cron ticks don't bounce on real templated inbox files.
    """
    lines = text.split("\n")

    # Skip leading blank lines (count them for round-trip preservation).
    leading_blank = 0
    while leading_blank < len(lines) and not lines[leading_blank].strip():
        leading_blank += 1

    if leading_blank >= len(lines) or lines[leading_blank] != "---":
        raise ValueError("no opening frontmatter fence (`---`)")

    open_idx = leading_blank
    close_idx = None
    for i in range(open_idx + 1, len(lines)):
        if lines[i] == "---":
            close_idx = i
            break
    if close_idx is None:
        raise ValueError("no closing frontmatter fence (`---`)")

    fm: dict[str, str] = {}
    for raw in lines[open_idx + 1:close_idx]:
        m = _FRONTMATTER_LINE_RE.match(raw)
        if m:
            key, value = m.group(1), m.group(2)
            fm[key] = value

    # Body is everything after the closing fence.
    body_lines = lines[close_idx + 1:]
    body = "\n".join(body_lines)
    return fm, body, leading_blank


def write_frontmatter(fm: dict, body: str, leading_blank: int = 0) -> str:
    """Serialize `fm` + `body` back into the on-disk form.

    Output shape: `<leading-blank-lines>---\\n<key: value>\\n...\\n---\\n<body>`.
    Key order is preserved from `fm`'s insertion order. `leading_blank` is the
    count of blank lines to preserve before the opening fence (from the
    `read_frontmatter` return value); defaults to 0 for backward compatibility.
    """
    fm_lines = [f"{k}: {v}" for k, v in fm.items()]
    fm_block = "---\n" + "\n".join(fm_lines) + "\n---\n"
    return ("\n" * leading_blank) + fm_block + body


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

    Returns the exit code per the CLI contract (0/1/2/3).

    Exit 2 is returned on a write-phase OSError (permission denied, write
    race); the original note is guaranteed uncorrupted because _atomic_write
    unlinks its temp file before re-raising and the except scope is limited
    to the write call only.
    """
    if not path.exists():
        print(
            json.dumps(
                {"error": "missing_file", "detail": f"{path} does not exist"}
            ),
            file=sys.stderr,
        )
        return 1

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        # Read failure is a validation concern (exit 1), not a write failure.
        print(
            json.dumps({"error": "read_failed", "detail": str(exc)}),
            file=sys.stderr,
        )
        return 1

    try:
        fm, body, leading_blank = read_frontmatter(text)
    except ValueError as exc:
        print(
            json.dumps({"error": "no_frontmatter", "detail": str(exc)}),
            file=sys.stderr,
        )
        return 1

    abs_path = str(path.resolve())

    # Idempotency check (FR-002): if already processed, emit success JSON
    # and return 0 without writing.
    if fm.get("status") == "processed":
        print(
            json.dumps(
                {
                    "finalized": True,
                    "already_processed": True,
                    "status": "processed",
                    "file_final_path": abs_path,
                }
            )
        )
        return 0

    # Mutate. Keep existing keys, only modify/add the two we own.
    fm["status"] = "processed"
    fm["processed_at"] = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    new_text = write_frontmatter(fm, body, leading_blank=leading_blank)

    # T002 (FR-001): catch write-phase OSError and return 2.
    # Scope is strictly the write — the read/validation paths above use exit 1.
    # _atomic_write unlinks its temp on failure so the original note is
    # never left partial or corrupted.
    try:
        _atomic_write(path, new_text)
    except OSError as exc:
        print(
            json.dumps({"error": "fs_error", "detail": str(exc)}),
            file=sys.stderr,
        )
        return 2

    # T003 (FR-002): emit single-line success JSON on stdout.
    print(
        json.dumps(
            {
                "finalized": True,
                "already_processed": False,
                "status": "processed",
                "file_final_path": abs_path,
            }
        )
    )
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
            json.dumps(
                {
                    "error": "refused",
                    "detail": "path is under 04-Growth/_private/",
                }
            ),
            file=sys.stderr,
        )
        return 3

    # T001 (FR-003): inbox-root validation. Resolve the inbox root from the
    # vault registry (honoring PRESCAN_REGISTRY_PATH for test isolation) and
    # reject any path that does not live under it.
    try:
        from scripts.inbox.prescan import resolve_registry  # lazy import

        inbox_root, _inbox_processed = resolve_registry()
        # Resolve the root too (Codex review): comparing a resolved candidate
        # against an unresolved root caused false `outside_inbox_root` on macOS
        # (`/var` registry vs `/private/var` resolved). Normalize both sides.
        inbox_root = inbox_root.resolve()
    except Exception as exc:
        print(
            json.dumps(
                {"error": "inbox_root_unresolvable", "detail": str(exc)}
            ),
            file=sys.stderr,
        )
        return 1

    candidate = Path(args.path).resolve()
    if not candidate.is_relative_to(inbox_root):
        print(
            json.dumps(
                {"error": "outside_inbox_root", "detail": str(candidate)}
            ),
            file=sys.stderr,
        )
        return 1

    # Operate on the canonical resolved path end-to-end (Codex review): passing
    # the raw symlink path would have os.replace() replace the symlink itself,
    # leaving the real target `unprocessed` while the helper exits 0 with success
    # JSON — re-introducing the silent-failure class this WP exists to close.
    return mark_processed(candidate)


if __name__ == "__main__":
    sys.exit(main())
