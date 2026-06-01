"""Shared engine for OpenClaw-log signal extractors.

The three FR-006 extractors (creds_restore, watchdog_reconnect,
unhandled_error) all walk OpenClaw logs the same way; they differ only
in:

- The match strategy (substring against the raw JSON line vs against
  the human-readable message body assembled from numeric keys).
- (Historically) a set of dict keys flagged as "definitely credential
  material." Redaction is now driven primarily by VALUE LENGTH per
  WP-01 T004 / spec C-005, so the per-extractor key set is retained
  only as defense-in-depth documentation and no longer gates
  redaction (see :func:`redact_dict` below).

This module factors out the cycle-walking + cursor-update + excerpt
collection so each extractor module stays a thin signature wrapper.
That keeps line counts close to the WP-01 prompt's "~60 lines each"
target and avoids three near-identical copies of the same loop.

Multi-file iteration (FR-001):
    When the source pattern resolves to multiple log files (e.g., the
    live ``openclaw-2026-06-01.log`` plus yesterday's
    ``openclaw-2026-05-31.log`` that still has unread tail beyond the
    saved cursor), we walk EVERY resolved file in mtime order on cold
    start (no prior cursor). Once a cursor exists, we filter resolved
    files to ONLY those still in scope this cycle:

    - The cursor file itself (matched by path + inode) — read from
      ``cursor.byte_offset``.
    - Any file strictly newer than the cursor (``mtime >
      cursor.mtime``) — read from byte 0.

    Files that are neither the cursor file nor strictly newer than
    ``cursor.mtime`` were already fully consumed in a prior cycle and
    are SKIPPED. Without this filter, older retained logs (e.g.,
    yesterday's file after the cursor advanced to today's) would be
    re-read from byte 0 every cycle and double-count their events
    forever (codex review cycle 4).

    The new cursor persisted at the end of the cycle reflects the LAST
    file iterated so the next cycle picks up exactly where we left off
    in the live log.
"""

from __future__ import annotations

import json
import re as _re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from scripts.openclaw.observation.signals.config_loader import (
    SignalDefinition,
)
from scripts.openclaw.observation.signals.openclaw_log import (
    INODE_CHANGED,
    LogCursor,
    extract_event_time,
    iter_raw_lines_since,
    resolve_log_files,
    stat_inode,
)
from scripts.openclaw.observation.signals.types import SignalExtraction

__all__ = [
    "REDACT_MAX_VALUE_LEN",
    "assemble_message_body",
    "redact_dict",
    "run_extraction",
]


# Per WP-01 T004 / spec C-005: ANY string value field longer than this
# ceiling is replaced with ``<redacted len=N>`` before going into an
# excerpt. The redaction is universal (not gated on the key name) so
# long credential-looking values under arbitrary keys (``value``,
# ``auth``, future OpenClaw fields) cannot leak through. The OpenClaw
# log lines we routinely match include path-shaped values that are <
# 64 chars, so this leaves operational fields readable while
# collapsing real secrets.
REDACT_MAX_VALUE_LEN = 64


def assemble_message_body(parsed: dict) -> str:
    """Concatenate string values under numeric keys.

    OpenClaw log lines carry the human-readable message in the keys
    ``"0"``, ``"1"``, ``"2"`` (the message text typically lives in
    ``"2"``). We assemble them in sorted order so substring matches
    survive future shape tweaks.
    """
    parts: list[str] = []
    for key in sorted(parsed.keys()):
        if key.isdigit():
            value = parsed[key]
            if isinstance(value, str):
                parts.append(value)
    return " ".join(parts)


def redact_dict(
    value: object, redact_keys: Iterable[str] = ()
) -> object:
    """Recursively redact long string values before excerpt emission.

    Implements WP-01 T004 / spec C-005: any string value longer than
    :data:`REDACT_MAX_VALUE_LEN` (64) chars is replaced with
    ``<redacted len=N>``. Redaction is gated on **length only** so
    long credential-looking values under unlisted keys (e.g.,
    ``value``, ``auth``, or any future OpenClaw field) still get
    scrubbed.

    The ``redact_keys`` parameter is retained for backward API
    compatibility and documentation (each extractor publishes its
    "definitely credential" key list as defense-in-depth), but it no
    longer gates redaction — length alone is sufficient.
    """
    _ = redact_keys  # API anchor — see docstring.
    return _redact_walk(value)


def _redact_walk(value: object) -> object:
    if isinstance(value, dict):
        return {k: _redact_walk(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_walk(item) for item in value]
    if isinstance(value, str) and len(value) > REDACT_MAX_VALUE_LEN:
        return f"<redacted len={len(value)}>"
    return value


def _make_matcher(signal_def: SignalDefinition, match_target: str):
    """Build a closure matching a line per the signal's strategy.

    ``match_target`` controls whether the match runs against the
    assembled message body (``"body"``) or against the raw JSON line
    (``"raw"``). Substring against raw is the cheaper path; we use it
    for ``"logLevelName":"ERROR"`` style matches that hit nested
    fields not present in the message body.
    """
    if signal_def.match_kind == "substring":
        needle = signal_def.match_pattern
        if match_target == "raw":
            return lambda raw, _body: needle in raw
        return lambda _raw, body: needle in body
    # regex
    pattern = _re.compile(signal_def.match_pattern)
    if match_target == "raw":
        return lambda raw, _body: pattern.search(raw) is not None
    return lambda _raw, body: pattern.search(body) is not None


def _cursor_matches_path(
    cursor: Optional[LogCursor], path: Path
) -> bool:
    """Return True iff ``cursor`` was taken on the file at ``path``.

    Mirrors ``openclaw_log._cursor_matches`` but exposed at the engine
    layer so the multi-file iteration can decide per file whether to
    apply the saved cursor or cold-start from byte 0.
    """
    if cursor is None:
        return False
    try:
        inode = stat_inode(path)
    except FileNotFoundError:  # pragma: no cover — file vanished mid-cycle
        return False
    return cursor.path == str(path) and cursor.inode == inode


def _select_files_to_process(
    resolved_files: list[Path], cursor: Optional[LogCursor]
) -> list[Path]:
    """Return the subset of ``resolved_files`` this cycle should walk.

    Selection contract (codex review cycle 4):

    - Cold start (``cursor is None``): all resolved files are in scope.
      They will be read from byte 0 — caller persists a cursor at the
      end of the newest file so subsequent cycles narrow scope.
    - Cursor present:
        * The cursor file itself (path + inode match) is ALWAYS in
          scope regardless of mtime, so we can resume mid-file.
        * Any file strictly newer than the cursor (``mtime >
          cursor.mtime``) is in scope — it didn't exist (or hadn't
          rolled over) when the cursor was persisted.
        * Everything else was fully consumed in a prior cycle and is
          SKIPPED. This prevents re-reading older retained logs on
          every cycle after the cursor advanced to a newer file.

    Edge case — cursor file no longer resolves (rotated away or
    deleted): no path+inode match anywhere in ``resolved_files``. We
    treat this as a partial cold start on the strictly-newer subset;
    the older subset is still skipped (those events were already
    consumed and are not worth replaying). If NOTHING qualifies
    (``selected`` is empty), the caller falls back to preserving the
    prior cursor — the next cycle will retry once the live file
    reappears or rotation completes.
    """
    if cursor is None:
        return list(resolved_files)

    selected: list[Path] = []
    for path in resolved_files:
        if _cursor_matches_path(cursor, path):
            selected.append(path)
            continue
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:  # pragma: no cover — file vanished mid-cycle
            continue
        if mtime > cursor.mtime:
            selected.append(path)
    return selected


def run_extraction(
    signal_def: SignalDefinition,
    now_utc: datetime,
    prior_cursor: Optional[LogCursor],
    prior_rolling_count: int,
    *,
    match_target: str,
    redact_keys: Iterable[str],
) -> SignalExtraction:
    """Walk every resolved log file and emit a :class:`SignalExtraction`.

    Shared engine called by the per-signal extractor modules. See the
    module docstring of any of them (``creds_restore.py`` etc.) for
    the per-signal redaction policy + match strategy.

    Multi-file iteration (FR-001):
        :func:`resolve_log_files` returns paths sorted oldest → newest
        by mtime. On cold start (no prior cursor) we iterate every
        resolved file from byte 0 so a glob like
        ``/tmp/openclaw/openclaw-*.log`` cannot drop unread tail from
        yesterday's log when today's file is also present. With a
        saved cursor we apply :func:`_select_files_to_process` to keep
        only the cursor file plus strictly-newer files; older files
        were already consumed and would otherwise be re-counted every
        cycle (codex review cycle 4 fix). The cursor we persist points
        at the end of the LAST file iterated so the next cycle resumes
        there.
    """
    if now_utc.tzinfo is None:
        raise ValueError("run_extraction: now_utc must be timezone-aware")

    log_files = resolve_log_files(signal_def.source_path_pattern, now_utc)
    if not log_files:
        return SignalExtraction(
            signal_id=signal_def.signal_id,
            count_cycle=0,
            count_rolling=prior_rolling_count,
            excerpts=[],
            last_event_at_utc=None,
            new_cursor=prior_cursor,
        )

    # Narrow the resolved set to files still in scope this cycle: the
    # cursor file plus any strictly-newer files. This is the cycle-4
    # fix — without it, older retained logs (e.g., yesterday's file
    # after the cursor advanced to today's) get re-read from byte 0 on
    # every cycle and inflate ``count_cycle`` forever.
    selected_files = _select_files_to_process(log_files, prior_cursor)
    if not selected_files:
        # Nothing in scope (e.g., cursor file rotated away and no newer
        # file has appeared yet). Hold the cursor steady so the next
        # cycle can retry without losing position.
        return SignalExtraction(
            signal_id=signal_def.signal_id,
            count_cycle=0,
            count_rolling=prior_rolling_count,
            excerpts=[],
            last_event_at_utc=None,
            new_cursor=prior_cursor,
        )

    matcher = _make_matcher(signal_def, match_target)
    count_cycle = 0
    excerpts: list[str] = []
    last_event_at: Optional[datetime] = None
    final_offset = 0

    # Walk the in-scope files in mtime order (oldest → newest). The
    # cursor applies only to its matching file; other files read from
    # byte 0. ``final_offset`` is overwritten by each file so it ends
    # up holding the byte position after the LAST line of the LAST
    # file — which is exactly the cursor we want to persist.
    for log_path in selected_files:
        cursor_for_file = (
            prior_cursor
            if _cursor_matches_path(prior_cursor, log_path)
            else None
        )
        # For files this cursor doesn't claim, start at byte 0 so we
        # don't skip the head of files we've never seen.
        final_offset = (
            cursor_for_file.byte_offset
            if cursor_for_file is not None
            else 0
        )

        for raw_text, parsed, new_offset in iter_raw_lines_since(
            log_path, cursor_for_file
        ):
            if parsed is INODE_CHANGED:  # pragma: no cover
                # Defensive: ``_select_files_to_process`` +
                # ``_cursor_matches_path`` already ensure we only pass
                # a cursor to ``iter_raw_lines_since`` when its
                # path+inode still match, so the iterator's
                # ``INODE_CHANGED`` sentinel is unreachable here in
                # normal operation. This branch handles a
                # rotation-mid-cycle race (file's inode flips between
                # our stat call and the iterator's open) — restart
                # this file from byte 0.
                cursor_for_file = None
                final_offset = 0
                continue

            final_offset = new_offset
            body = assemble_message_body(parsed)
            if not matcher(raw_text, body):
                continue
            count_cycle += 1
            event_time = extract_event_time(parsed)
            if event_time is not None:
                last_event_at = event_time
            if len(excerpts) < signal_def.excerpt_lines:
                excerpts.append(
                    json.dumps(
                        redact_dict(parsed, redact_keys),
                        sort_keys=True,
                    )
                )

    # The cursor we persist always reflects the LAST (newest) file we
    # iterated — that's where the next cycle should resume. We use
    # ``selected_files`` (not ``log_files``) so that when the prior
    # cursor was on the only in-scope file and no newer file exists,
    # we persist a fresh cursor at that file's tail rather than
    # accidentally jumping to a not-yet-iterated newest path.
    last_log = selected_files[-1]
    new_cursor = LogCursor(
        path=str(last_log),
        inode=stat_inode(last_log),
        byte_offset=final_offset,
        mtime=last_log.stat().st_mtime,
    )

    return SignalExtraction(
        signal_id=signal_def.signal_id,
        count_cycle=count_cycle,
        count_rolling=prior_rolling_count + count_cycle,
        excerpts=excerpts,
        last_event_at_utc=last_event_at,
        new_cursor=new_cursor,
    )


