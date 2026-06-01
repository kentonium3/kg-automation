"""Tests for ``signals.creds_restore`` (T004 #1).

Exercises the shared engine through the creds_restore wrapper using a
small synthetic JSONL fixture plus tmp_path-rooted log files so the
extractor's glob expansion can resolve under each test.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.openclaw.observation.signals.config_loader import (  # noqa: E402
    SignalDefinition,
)
from scripts.openclaw.observation.signals.creds_restore import (  # noqa: E402
    extract,
)
from scripts.openclaw.observation.signals.openclaw_log import (  # noqa: E402
    LogCursor,
    stat_inode,
)


_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "creds_restore.jsonl"
)


def _signal_def(pattern: str, excerpt_lines: int = 5) -> SignalDefinition:
    return SignalDefinition(
        signal_id="whatsapp_creds_restore",
        source_kind="openclaw_log",
        source_path_pattern=pattern,
        match_pattern="restored corrupted WhatsApp creds.json from backup",
        match_kind="substring",
        cycle_threshold=6,
        rolling_window_minutes=60,
        rolling_threshold=18,
        dedup_strategy="open_issue_present",
        dedup_window_hours=24,
        priority="P2",
        area_label="felix-core",
        tier_hypothesis="3",
        excerpt_lines=excerpt_lines,
        enabled=True,
    )


def _stage_fixture(tmp_path: Path) -> Path:
    """Copy the synthetic JSONL into a tmp dir + return the dir glob."""
    target_dir = tmp_path / "logs"
    target_dir.mkdir()
    target = target_dir / "openclaw-2026-06-01.log"
    shutil.copy(_FIXTURE, target)
    return target_dir


def test_extracts_seven_matches_from_fixture(tmp_path: Path):
    log_dir = _stage_fixture(tmp_path)
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    # 7 matching + 3 non-matching lines in the fixture.
    assert result.count_cycle == 7
    assert result.count_rolling == 7
    assert result.signal_id == "whatsapp_creds_restore"
    assert result.new_cursor is not None
    assert result.last_event_at_utc is not None


def test_excerpt_count_capped_by_signal_def(tmp_path: Path):
    log_dir = _stage_fixture(tmp_path)
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"),
                             excerpt_lines=3)
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    assert len(result.excerpts) == 3


def test_no_matching_logs_returns_zero(tmp_path: Path):
    signal_def = _signal_def(str(tmp_path / "logs" / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
        prior_rolling_count=4,
    )
    assert result.count_cycle == 0
    # When no files match, the prior rolling count flows through
    # unchanged so the orchestrator's threshold check stays correct.
    assert result.count_rolling == 4
    assert result.new_cursor is None
    assert result.excerpts == []


def test_prior_rolling_count_accumulates(tmp_path: Path):
    log_dir = _stage_fixture(tmp_path)
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
        prior_rolling_count=5,
    )
    assert result.count_cycle == 7
    assert result.count_rolling == 12


def test_naive_now_raises(tmp_path: Path):
    signal_def = _signal_def(str(tmp_path / "openclaw-*.log"))
    with pytest.raises(ValueError, match="timezone-aware"):
        extract(
            state_dir=tmp_path / "state",
            signal_def=signal_def,
            now_utc=datetime(2026, 6, 1, 12, 0, 0),
        )


def test_long_creds_value_redacted_in_excerpt(tmp_path: Path):
    # Construct a one-line log file with a 200-char fake credential to
    # ensure the excerpt path redacts long values under credential
    # keys (spec C-005).
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    fake_secret = "x" * 200
    target = log_dir / "openclaw-2026-06-01.log"
    target.write_text(
        '{"0":"web-session","1":{"creds":"' + fake_secret + '"},'
        '"2":"restored corrupted WhatsApp creds.json from backup",'
        '"_meta":{"logLevelName":"WARN"},'
        '"time":"2026-06-01T00:00:00+00:00"}\n'
    )
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    assert result.count_cycle == 1
    excerpt = result.excerpts[0]
    assert fake_secret not in excerpt
    assert "<redacted len=200>" in excerpt


# ---------------------------------------------------------------------------
# Cycle-3 regression tests (codex review feedback, 2026-06-01)
# ---------------------------------------------------------------------------
#
# These two tests pin the engine fixes for the two findings the
# reviewer rejected cycle 2 on:
#
# 1. Multi-file cursor scope: a glob like ``openclaw-*.log`` resolving
#    to two files (older + newer) must walk BOTH files in mtime order.
#    The saved cursor applies only to the file it matches; other files
#    are read from byte 0. The new cursor we persist must point at the
#    end of the newest file.
#
# 2. Universal length-based redaction: any string value field longer
#    than 64 chars must be redacted to ``<redacted len=N>``, even when
#    the field's key is NOT in the extractor's ``REDACT_KEYS`` set.
#    The pre-fix engine gated redaction on the key allowlist, which
#    leaked long credential-like values under keys like ``value`` or
#    ``auth``.


def _matching_line(ts: str, padding: str = "") -> str:
    """Build a one-line log entry that matches the creds_restore signal.

    ``padding`` lets us pad each line to a known size so we can compute
    deterministic cursor offsets without relying on the exact JSON
    serialization width.
    """
    msg = "restored corrupted WhatsApp creds.json from backup"
    if padding:
        msg = msg + " " + padding
    return (
        '{"0":"web-session","1":{},"2":"' + msg + '",'
        '"_meta":{"logLevelName":"WARN"},'
        '"time":"' + ts + '"}\n'
    )


def _non_matching_line(ts: str) -> str:
    return (
        '{"0":"web-session","1":{},"2":"unrelated message",'
        '"_meta":{"logLevelName":"INFO"},'
        '"time":"' + ts + '"}\n'
    )


def test_cycle3_multi_file_cursor_scope(tmp_path: Path):
    """Regression: glob expanding to >1 file must read EVERY file.

    Setup:
        - Older log (lower mtime) contains 1 non-matching line (already
          read in the prior cycle, sitting at byte position X), then 3
          matching lines after that cursor position.
        - Newer log (higher mtime) contains 2 matching lines from byte 0.
        - The saved cursor points at the OLDER file's byte X (the
          position after the already-read non-matching line).

    Expected after the fix:
        - count_cycle == 5 (3 from the older file's unread tail + 2
          from the newer file).
        - new_cursor.path == the newer file's path.
        - new_cursor.byte_offset == newer file's size.

    Before the fix, the engine read only ``log_files[-1]`` (the newer
    file), missed the 3 unread matches in the older file, and reported
    ``count_cycle == 2``.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    older = log_dir / "openclaw-2026-05-31.log"
    newer = log_dir / "openclaw-2026-06-01.log"

    # Older file: one already-read non-matching line, then three unread
    # matching lines after the cursor.
    already_read = _non_matching_line("2026-05-31T23:00:00+00:00")
    older_unread = (
        _matching_line("2026-05-31T23:30:00+00:00")
        + _matching_line("2026-05-31T23:45:00+00:00")
        + _matching_line("2026-05-31T23:55:00+00:00")
    )
    older.write_text(already_read + older_unread)
    cursor_byte_offset = len(already_read.encode("utf-8"))

    # Newer file: two matching lines from byte 0.
    newer.write_text(
        _matching_line("2026-06-01T00:00:00+00:00")
        + _matching_line("2026-06-01T00:01:00+00:00")
    )

    # Force older < newer mtime so resolve_log_files orders them
    # correctly regardless of filesystem touch order.
    os.utime(older, (1000.0, 1000.0))
    os.utime(newer, (2000.0, 2000.0))

    cursor = LogCursor(
        path=str(older),
        inode=stat_inode(older),
        byte_offset=cursor_byte_offset,
        mtime=older.stat().st_mtime,
    )

    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
        prior_cursor=cursor,
    )

    # 3 from the older file (past the cursor) + 2 from the newer file.
    assert result.count_cycle == 5, (
        "Multi-file glob must walk all resolved files, not just "
        "log_files[-1]"
    )
    # The persisted cursor must point at the newest file's end so the
    # next cycle resumes correctly without re-reading.
    assert result.new_cursor is not None
    assert result.new_cursor.path == str(newer)
    assert result.new_cursor.byte_offset == newer.stat().st_size
    assert result.new_cursor.inode == stat_inode(newer)


def test_cycle3_long_value_redacted_under_unlisted_key(tmp_path: Path):
    """Regression: length-based redaction must apply under ANY key.

    Setup:
        - One matching log line whose ``"1"`` block carries a 65-char
          fake credential under the key ``"auth"`` — NOT one of
          ``creds_restore.REDACT_KEYS``.

    Expected after the fix:
        - Excerpt does NOT contain the raw 65-char value.
        - Excerpt contains ``<redacted len=65>``.

    Before the fix, ``redact_dict`` gated truncation on the key
    allowlist, so the 65-char value under ``auth`` slipped through
    verbatim — violating WP-01 T004 / spec C-005.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    fake_secret = "y" * 65  # 65 > REDACT_MAX_VALUE_LEN (64)
    assert len(fake_secret) == 65

    target = log_dir / "openclaw-2026-06-01.log"
    target.write_text(
        '{"0":"web-session","1":{"auth":"' + fake_secret + '"},'
        '"2":"restored corrupted WhatsApp creds.json from backup",'
        '"_meta":{"logLevelName":"WARN"},'
        '"time":"2026-06-01T00:00:00+00:00"}\n'
    )

    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )

    assert result.count_cycle == 1
    assert len(result.excerpts) == 1
    excerpt = result.excerpts[0]
    assert fake_secret not in excerpt, (
        "Long string under an unlisted key must still be redacted"
    )
    assert "<redacted len=65>" in excerpt


# ---------------------------------------------------------------------------
# Cycle-4 regression tests (codex review feedback, 2026-06-01)
# ---------------------------------------------------------------------------
#
# Cycle 3 added multi-file iteration but did NOT filter older files by
# mtime. That meant once the cursor advanced to today's log, yesterday's
# log was still re-read from byte 0 on every subsequent cycle and its
# events were double-counted forever.
#
# The cycle-4 fix narrows the per-cycle file set to the cursor file plus
# any file strictly newer than ``cursor.mtime``. The regression test
# below pins that contract: a second extraction using the first
# extraction's ``new_cursor`` (with no new writes) MUST return
# ``count_cycle == 0``.


def test_cycle4_second_pass_returns_zero_with_no_new_writes(tmp_path: Path):
    """Regression: persisted cursor must skip already-consumed older logs.

    Setup mirrors codex's review reproduction:
        - Older log with 2 matching lines.
        - Newer log with 1 matching line.
        - Pass 1 runs with NO prior cursor; engine reads both files
          from byte 0, returns count_cycle=3, and persists a cursor
          pointing at the newer file's tail.
        - Pass 2 runs with that cursor and no new writes.

    Expected:
        - Pass 1: count_cycle == 3.
        - Pass 2: count_cycle == 0. The older file's mtime is <=
          cursor.mtime (which equals the newer file's mtime), so the
          new mtime-based file filter skips it. The newer file IS the
          cursor file; reading from its persisted offset yields zero
          new lines.

    Before the fix, pass 2 returned 2 (the older file's two matches,
    re-counted from byte 0).
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    older = log_dir / "openclaw-2026-05-31.log"
    newer = log_dir / "openclaw-2026-06-01.log"

    older.write_text(
        _matching_line("2026-05-31T22:00:00+00:00")
        + _matching_line("2026-05-31T23:00:00+00:00")
    )
    newer.write_text(
        _matching_line("2026-06-01T00:00:00+00:00")
    )

    # Force older < newer mtime so resolve_log_files orders them
    # correctly regardless of filesystem touch order.
    os.utime(older, (1000.0, 1000.0))
    os.utime(newer, (2000.0, 2000.0))

    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))

    # Pass 1: no cursor → both files read from byte 0 → 3 matches.
    pass_one = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    assert pass_one.count_cycle == 3, (
        "Cold start must walk both files and count every match"
    )
    assert pass_one.new_cursor is not None
    assert pass_one.new_cursor.path == str(newer)
    # The persisted cursor must carry the NEWER file's mtime so the
    # next-cycle filter recognizes the older file as already consumed.
    assert pass_one.new_cursor.mtime == newer.stat().st_mtime

    # Pass 2: identical inputs, no new writes, using pass 1's cursor.
    # The older file must be filtered out by mtime; the newer file
    # is the cursor file and reads from EOF → no lines → 0 matches.
    pass_two = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
        prior_cursor=pass_one.new_cursor,
    )
    assert pass_two.count_cycle == 0, (
        "Second pass with persisted cursor + no new writes must "
        "return 0; older files must NOT be re-counted every cycle"
    )
    # Cursor stays anchored on the newer file at the same offset.
    assert pass_two.new_cursor is not None
    assert pass_two.new_cursor.path == str(newer)
    assert (
        pass_two.new_cursor.byte_offset
        == pass_one.new_cursor.byte_offset
    )


def test_cycle4_third_pass_picks_up_new_writes_to_cursor_file(
    tmp_path: Path,
):
    """Once new lines are appended to the cursor file, they ARE counted.

    Guards against an over-aggressive fix that skips the cursor file
    when its mtime doesn't strictly advance past the persisted
    cursor.mtime: the cursor file is always in scope regardless of
    mtime so we can resume mid-file.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    older = log_dir / "openclaw-2026-05-31.log"
    newer = log_dir / "openclaw-2026-06-01.log"
    older.write_text(_matching_line("2026-05-31T22:00:00+00:00"))
    newer.write_text(_matching_line("2026-06-01T00:00:00+00:00"))
    os.utime(older, (1000.0, 1000.0))
    os.utime(newer, (2000.0, 2000.0))

    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))

    pass_one = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    assert pass_one.count_cycle == 2

    # Append two new matching lines to the cursor (newer) file.
    with newer.open("a") as fp:
        fp.write(_matching_line("2026-06-01T00:05:00+00:00"))
        fp.write(_matching_line("2026-06-01T00:10:00+00:00"))

    pass_two = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
        prior_cursor=pass_one.new_cursor,
    )
    # Only the two newly appended lines — the older file is still
    # filtered out and the prior cursor lines aren't re-read.
    assert pass_two.count_cycle == 2


def test_cycle4_skips_processing_when_only_older_files_resolve(
    tmp_path: Path,
):
    """Cursor file rotated away + only older files remain → no work.

    Defensive edge case from the cycle-4 fix's selection contract: if
    the cursor's file no longer exists at its path AND every resolved
    file is older than the cursor's mtime, the cycle returns 0 and
    preserves the cursor so a later cycle can resume once the live
    log reappears.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    older = log_dir / "openclaw-2026-05-31.log"
    older.write_text(_matching_line("2026-05-31T22:00:00+00:00"))
    os.utime(older, (1000.0, 1000.0))

    # Cursor refers to a file that no longer exists, with mtime > the
    # only resolved file.
    ghost_cursor = LogCursor(
        path=str(log_dir / "openclaw-2026-06-01.log"),
        inode=99999998,
        byte_offset=0,
        mtime=5000.0,
    )

    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
        prior_cursor=ghost_cursor,
    )
    assert result.count_cycle == 0
    # Cursor is held steady (selection produced empty list → engine
    # returns the prior cursor unchanged).
    assert result.new_cursor == ghost_cursor
