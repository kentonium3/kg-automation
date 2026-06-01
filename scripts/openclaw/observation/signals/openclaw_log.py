"""Shared OpenClaw log helpers.

The signal extractors share three primitives:

1. :func:`resolve_log_files` — expand a glob like
   ``/tmp/openclaw/openclaw-*.log`` (or a literal path with
   ``{YYYY-MM-DD}`` substitution) and return matching files sorted by
   mtime (newest last so iteration ends on the live log).
2. :func:`iter_lines_since` — open a log file, seek to a prior cursor
   when its ``path`` + ``inode`` match, and yield ``(parsed_dict,
   new_byte_offset)`` per line. Returns the inode change as a sentinel
   so callers can cold-start replay the last hour.
3. :func:`extract_event_time` — parse the ``time`` field that OpenClaw
   emits at the top of every log line. Handles both the canonical
   ``+00:00`` suffix and bare ``Z``.

The format target is the real OpenClaw log shape:

    {"0": "{\\"module\\":\\"web-session\\"}",
     "1": {"credsPath": "..."},
     "2": "restored corrupted WhatsApp creds.json from backup",
     "_meta": {..., "logLevelName": "WARN", ...},
     "time": "2026-06-01T00:00:58.289+00:00"}

Malformed lines are skipped with a stderr warning; the helper does
NOT raise.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Union

__all__ = [
    "LogCursor",
    "INODE_CHANGED",
    "extract_event_time",
    "iter_lines_since",
    "iter_raw_lines_since",
    "resolve_log_files",
    "stat_inode",
]


@dataclass(frozen=True)
class LogCursor:
    """Cursor into one OpenClaw log file.

    Mirrors the ``last_log_position`` shape stored in
    :class:`SignalState` (data-model.md §E2). The combination
    ``(path, inode)`` uniquely identifies a log file even across
    rotations.
    """

    path: str
    inode: int
    byte_offset: int
    mtime: float


# Sentinel used by :func:`iter_lines_since` to flag that the file's
# inode no longer matches the cursor (rotation). Yielded as a
# ``(dict, int)`` tuple where the dict is the literal sentinel so the
# caller can short-circuit without parsing real lines.
INODE_CHANGED: dict = {"__cursor_event__": "inode_changed"}


def _expand_date_template(pattern: str, now_utc: datetime) -> list[str]:
    """Expand ``{YYYY-MM-DD}`` placeholders into today + yesterday paths.

    If the pattern does not contain the placeholder, returns ``[pattern]``
    untouched so glob-only patterns flow through.
    """
    if "{YYYY-MM-DD}" not in pattern:
        return [pattern]
    today = now_utc.strftime("%Y-%m-%d")
    # "Yesterday" handled by subtracting 86_400s before strftime so we
    # don't introduce a timezone helper just for this.
    yesterday_dt = datetime.fromtimestamp(
        now_utc.timestamp() - 86_400, tz=timezone.utc
    )
    yesterday = yesterday_dt.strftime("%Y-%m-%d")
    return [
        pattern.replace("{YYYY-MM-DD}", today),
        pattern.replace("{YYYY-MM-DD}", yesterday),
    ]


def resolve_log_files(
    pattern: str, now_utc: datetime
) -> list[Path]:
    """Expand ``pattern`` to matching files, sorted oldest → newest.

    Sorting by mtime (ascending) ensures the LIVE log is last in the
    list — extractors that tail the newest file iterate to the tail
    naturally without an explicit ``[-1]`` lookup.

    Args:
        pattern: Either a glob like ``/tmp/openclaw/openclaw-*.log`` or
            a literal-with-template like
            ``/tmp/openclaw/openclaw-{YYYY-MM-DD}.log``.
        now_utc: Current UTC clock, used to expand ``{YYYY-MM-DD}``.

    Returns:
        List of resolved :class:`Path` objects that exist on disk.
        Empty list when nothing matches (extractors treat this as a
        warning, not an error — see FR-005 validation rule).
    """
    if now_utc.tzinfo is None:
        raise ValueError(
            "resolve_log_files: now_utc must be timezone-aware"
        )

    candidate_patterns = _expand_date_template(pattern, now_utc)
    matched: set[Path] = set()
    for candidate in candidate_patterns:
        # ``glob.glob`` handles both literal paths (returns a single
        # element when the file exists) and wildcards.
        for match in glob.glob(candidate):
            path = Path(match)
            if path.is_file():
                matched.add(path)

    return sorted(matched, key=lambda p: p.stat().st_mtime)


def _cursor_matches(cursor: LogCursor, path: Path) -> bool:
    """Return True iff ``cursor`` was taken on the file at ``path``.

    We compare both path and inode so that rotation (same path, new
    inode) is detected as a mismatch.
    """
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False
    return cursor.path == str(path) and cursor.inode == stat.st_ino


def iter_lines_since(
    log_path: Union[Path, str],
    cursor: Optional[LogCursor],
) -> Iterator[tuple[dict, int]]:
    """Yield parsed JSON lines past ``cursor``, plus new byte offsets.

    Yields:
        ``(parsed_dict, new_byte_offset)`` for each successfully-parsed
        line. The byte offset is the position AFTER the yielded line
        (suitable for storing as the next cursor).

        If ``cursor`` references a different inode than the file
        currently at ``log_path`` (log rotated), yields exactly one
        sentinel tuple ``(INODE_CHANGED, 0)`` and then continues from
        byte 0 so the caller can cold-start the new file in the same
        iteration. The caller is responsible for re-reading the last
        hour of content if needed (helper does not own retention
        policy).

    Malformed JSON lines are skipped with a stderr warning. Reads that
    encounter ``UnicodeDecodeError`` are also skipped — operational
    logs can carry the occasional non-UTF-8 byte sequence (e.g., from
    a forked subprocess writing partial output).
    """
    path = Path(log_path)
    if not path.exists():
        return

    start_offset = 0
    inode_changed = False
    if cursor is not None:
        if _cursor_matches(cursor, path):
            start_offset = cursor.byte_offset
        else:
            # Either the file at ``path`` has rotated or the cursor
            # was taken on a different file. Signal the caller and
            # restart from byte 0 below.
            inode_changed = True

    with path.open("rb") as fp:
        if inode_changed:
            yield (INODE_CHANGED, 0)
        else:
            fp.seek(start_offset)

        offset = fp.tell()
        for raw_line in fp:
            offset += len(raw_line)
            try:
                text = raw_line.decode("utf-8")
            except UnicodeDecodeError as exc:
                print(
                    f"WARN: openclaw_log: non-UTF8 line at {path}:"
                    f"{offset}: {exc}",
                    file=sys.stderr,
                )
                continue
            stripped = text.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                print(
                    f"WARN: openclaw_log: malformed JSON at {path}:"
                    f"{offset}: {exc}",
                    file=sys.stderr,
                )
                continue
            yield (parsed, offset)


def iter_raw_lines_since(
    log_path: Union[Path, str],
    cursor: Optional[LogCursor],
) -> Iterator[tuple[str, dict, int]]:
    """Yield ``(raw_text, parsed_dict, new_byte_offset)`` per line.

    Twin of :func:`iter_lines_since` for callers that need the raw
    line text (e.g., substring matches against fields like
    ``"logLevelName":"ERROR"`` that live in nested objects and so
    don't surface in the assembled message body).

    Semantics match :func:`iter_lines_since`:
    - Yields ``("", INODE_CHANGED, 0)`` on rotation.
    - Skips malformed JSON / non-UTF-8 with a stderr warning.
    """
    path = Path(log_path)
    if not path.exists():
        return

    start_offset = 0
    inode_changed = False
    if cursor is not None:
        if _cursor_matches(cursor, path):
            start_offset = cursor.byte_offset
        else:
            inode_changed = True

    with path.open("rb") as fp:
        if inode_changed:
            yield ("", INODE_CHANGED, 0)
        else:
            fp.seek(start_offset)

        offset = fp.tell()
        for raw_line in fp:
            offset += len(raw_line)
            try:
                text = raw_line.decode("utf-8")
            except UnicodeDecodeError as exc:
                print(
                    f"WARN: openclaw_log: non-UTF8 line at {path}:"
                    f"{offset}: {exc}",
                    file=sys.stderr,
                )
                continue
            stripped = text.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                print(
                    f"WARN: openclaw_log: malformed JSON at {path}:"
                    f"{offset}: {exc}",
                    file=sys.stderr,
                )
                continue
            yield (stripped, parsed, offset)


def extract_event_time(
    line_dict: dict,
) -> Optional[datetime]:
    """Parse the top-level ``time`` field from an OpenClaw log line.

    OpenClaw emits ``"time": "2026-06-01T00:00:58.289+00:00"`` for
    every line. We also accept the ``Z`` suffix for forward-compat
    with any future OpenClaw release that switches notation.

    Returns:
        ``datetime`` in UTC, or ``None`` if the field is missing /
        unparseable. The extractors treat ``None`` as "use the
        previous event's time" so a stray malformed line never
        derails the cycle clock.
    """
    raw = line_dict.get("time")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:  # pragma: no branch — defensive
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def stat_inode(path: Union[Path, str]) -> int:
    """Return the inode of ``path`` (helper exported for tests).

    Wrapping ``os.stat`` here makes the inode-rotation test path easy
    to monkeypatch and keeps the cursor construction code in the
    extractors small.
    """
    return os.stat(path).st_ino
