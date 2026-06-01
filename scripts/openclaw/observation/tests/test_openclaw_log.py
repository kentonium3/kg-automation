"""Tests for ``signals.openclaw_log`` (T003).

Covers:

- ``resolve_log_files`` glob expansion + date template substitution.
- ``iter_lines_since`` with ``cursor=None`` reads from byte 0.
- ``iter_lines_since`` with a cursor seeks past already-read content.
- Inode change emits the sentinel and continues from byte 0.
- Malformed JSON lines are skipped, not raised.
- ``extract_event_time`` parses both ``+00:00`` and ``Z`` suffixes.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.openclaw.observation.signals.openclaw_log import (  # noqa: E402
    INODE_CHANGED,
    LogCursor,
    extract_event_time,
    iter_lines_since,
    iter_raw_lines_since,
    resolve_log_files,
    stat_inode,
)


_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n")


def _line(time_str: str, msg: str) -> str:
    """Build a synthetic OpenClaw-shaped JSON log line via json.dumps."""
    import json as _json

    return _json.dumps(
        {
            "0": '{"module":"test"}',
            "1": {},
            "2": msg,
            "_meta": {"logLevelName": "INFO"},
            "time": time_str,
        }
    )


def test_resolve_log_files_glob(tmp_path: Path):
    (tmp_path / "openclaw-2026-06-01.log").write_text("a")
    (tmp_path / "openclaw-2026-05-31.log").write_text("b")
    (tmp_path / "other.txt").write_text("c")
    files = resolve_log_files(str(tmp_path / "openclaw-*.log"), _NOW)
    names = sorted(p.name for p in files)
    assert names == ["openclaw-2026-05-31.log", "openclaw-2026-06-01.log"]


def test_resolve_log_files_date_template(tmp_path: Path):
    today = _NOW.strftime("%Y-%m-%d")
    (tmp_path / f"openclaw-{today}.log").write_text("a")
    pattern = str(tmp_path / "openclaw-{YYYY-MM-DD}.log")
    files = resolve_log_files(pattern, _NOW)
    assert len(files) == 1
    assert files[0].name == f"openclaw-{today}.log"


def test_resolve_log_files_empty_when_nothing_matches(tmp_path: Path):
    assert resolve_log_files(str(tmp_path / "nothing-*.log"), _NOW) == []


def test_resolve_log_files_sorted_by_mtime(tmp_path: Path):
    older = tmp_path / "openclaw-2026-05-31.log"
    newer = tmp_path / "openclaw-2026-06-01.log"
    older.write_text("a")
    newer.write_text("b")
    # Force older mtime
    os.utime(older, (1000.0, 1000.0))
    os.utime(newer, (2000.0, 2000.0))
    files = resolve_log_files(str(tmp_path / "openclaw-*.log"), _NOW)
    assert [p.name for p in files] == [older.name, newer.name]


def test_resolve_log_files_rejects_naive_now(tmp_path: Path):
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_log_files(
            str(tmp_path / "*.log"), datetime(2026, 6, 1)
        )


def test_iter_lines_since_cold_start(tmp_path: Path):
    log = tmp_path / "openclaw.log"
    _write_log(
        log,
        [
            _line("2026-06-01T00:00:00+00:00", "first"),
            _line("2026-06-01T00:01:00+00:00", "second"),
        ],
    )
    results = list(iter_lines_since(log, None))
    assert len(results) == 2
    parsed_first, offset_first = results[0]
    parsed_second, offset_second = results[1]
    assert parsed_first["2"] == "first"
    assert parsed_second["2"] == "second"
    assert offset_second > offset_first
    # The final offset should match the file size.
    assert offset_second == log.stat().st_size


def test_iter_lines_since_resume_at_cursor(tmp_path: Path):
    log = tmp_path / "openclaw.log"
    _write_log(
        log,
        [
            _line("2026-06-01T00:00:00+00:00", "first"),
            _line("2026-06-01T00:01:00+00:00", "second"),
            _line("2026-06-01T00:02:00+00:00", "third"),
        ],
    )
    # First pass: read everything.
    results = list(iter_lines_since(log, None))
    _, final_offset = results[-1]
    inode = stat_inode(log)
    cursor = LogCursor(
        path=str(log),
        inode=inode,
        byte_offset=final_offset,
        mtime=log.stat().st_mtime,
    )
    # Append a new line.
    with log.open("a") as fp:
        fp.write(_line("2026-06-01T00:03:00+00:00", "fourth") + "\n")
    second_pass = list(iter_lines_since(log, cursor))
    assert len(second_pass) == 1
    assert second_pass[0][0]["2"] == "fourth"


def test_iter_lines_since_inode_change_emits_sentinel(tmp_path: Path):
    log = tmp_path / "openclaw.log"
    _write_log(log, [_line("2026-06-01T00:00:00+00:00", "first")])
    cursor = LogCursor(
        path=str(log),
        inode=99999999,  # not the real inode — forces mismatch
        byte_offset=0,
        mtime=log.stat().st_mtime,
    )
    results = list(iter_lines_since(log, cursor))
    assert results
    # First yield is the sentinel; subsequent yields are real lines
    # restarted from byte 0.
    first_parsed, first_offset = results[0]
    assert first_parsed is INODE_CHANGED
    assert first_offset == 0
    assert results[-1][0]["2"] == "first"


def test_iter_lines_since_skips_malformed(tmp_path: Path, capsys):
    log = tmp_path / "openclaw.log"
    log.write_text(
        _line("2026-06-01T00:00:00+00:00", "ok") + "\n"
        "this is not json\n"
        + _line("2026-06-01T00:02:00+00:00", "also ok") + "\n"
    )
    results = list(iter_lines_since(log, None))
    assert len(results) == 2
    captured = capsys.readouterr()
    assert "malformed JSON" in captured.err


def test_iter_lines_since_skips_blank_lines(tmp_path: Path):
    log = tmp_path / "openclaw.log"
    log.write_text(
        _line("2026-06-01T00:00:00+00:00", "a") + "\n"
        "\n"
        + _line("2026-06-01T00:01:00+00:00", "b") + "\n"
    )
    results = list(iter_lines_since(log, None))
    assert len(results) == 2


def test_iter_lines_since_missing_file_yields_nothing(tmp_path: Path):
    assert list(iter_lines_since(tmp_path / "missing.log", None)) == []


def test_iter_raw_lines_since_includes_raw_text(tmp_path: Path):
    log = tmp_path / "openclaw.log"
    raw_line = _line("2026-06-01T00:00:00+00:00", "x")
    log.write_text(raw_line + "\n")
    results = list(iter_raw_lines_since(log, None))
    assert len(results) == 1
    raw, parsed, _ = results[0]
    assert raw == raw_line
    assert parsed["2"] == "x"


def test_iter_raw_lines_since_inode_change(tmp_path: Path):
    log = tmp_path / "openclaw.log"
    log.write_text(_line("2026-06-01T00:00:00+00:00", "x") + "\n")
    cursor = LogCursor(
        path=str(log),
        inode=12345678,
        byte_offset=0,
        mtime=log.stat().st_mtime,
    )
    results = list(iter_raw_lines_since(log, cursor))
    raw, parsed, offset = results[0]
    assert parsed is INODE_CHANGED
    assert raw == ""
    assert offset == 0


def test_extract_event_time_offset_suffix():
    parsed = {"time": "2026-06-01T00:00:58.289+00:00"}
    dt = extract_event_time(parsed)
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2026 and dt.month == 6 and dt.day == 1


def test_extract_event_time_zulu_suffix():
    parsed = {"time": "2026-06-01T00:00:58Z"}
    dt = extract_event_time(parsed)
    assert dt is not None
    assert dt.tzinfo == timezone.utc


def test_extract_event_time_missing_returns_none():
    assert extract_event_time({}) is None


def test_extract_event_time_malformed_returns_none():
    assert extract_event_time({"time": "not-a-date"}) is None


def test_extract_event_time_non_string_returns_none():
    assert extract_event_time({"time": 12345}) is None


def test_iter_raw_lines_since_missing_file_yields_nothing(tmp_path: Path):
    assert list(iter_raw_lines_since(tmp_path / "missing.log", None)) == []


def test_iter_raw_lines_since_skips_malformed(tmp_path: Path, capsys):
    log = tmp_path / "openclaw.log"
    log.write_text(
        _line("2026-06-01T00:00:00+00:00", "ok") + "\n"
        "garbage line\n"
        + _line("2026-06-01T00:02:00+00:00", "ok again") + "\n"
    )
    results = list(iter_raw_lines_since(log, None))
    assert len(results) == 2
    assert "malformed JSON" in capsys.readouterr().err


def test_iter_raw_lines_since_skips_blank_lines(tmp_path: Path):
    log = tmp_path / "openclaw.log"
    log.write_text(
        _line("2026-06-01T00:00:00+00:00", "a") + "\n"
        "\n"
        + _line("2026-06-01T00:01:00+00:00", "b") + "\n"
    )
    results = list(iter_raw_lines_since(log, None))
    assert len(results) == 2


def test_iter_raw_lines_since_resume_from_cursor(tmp_path: Path):
    log = tmp_path / "openclaw.log"
    _write_log(
        log,
        [
            _line("2026-06-01T00:00:00+00:00", "one"),
            _line("2026-06-01T00:01:00+00:00", "two"),
        ],
    )
    first = list(iter_raw_lines_since(log, None))
    _, _, last_offset = first[-1]
    cursor = LogCursor(
        path=str(log),
        inode=stat_inode(log),
        byte_offset=last_offset,
        mtime=log.stat().st_mtime,
    )
    with log.open("a") as fp:
        fp.write(_line("2026-06-01T00:02:00+00:00", "three") + "\n")
    second = list(iter_raw_lines_since(log, cursor))
    assert len(second) == 1
    assert second[0][1]["2"] == "three"


def test_iter_raw_lines_since_handles_non_utf8(tmp_path: Path, capsys):
    log = tmp_path / "openclaw.log"
    good = _line("2026-06-01T00:00:00+00:00", "ok") + "\n"
    with log.open("wb") as fp:
        fp.write(good.encode("utf-8"))
        fp.write(b"\xff\xfe junk \xff\xfe\n")
        fp.write(good.encode("utf-8"))
    results = list(iter_raw_lines_since(log, None))
    assert len(results) == 2
    assert "non-UTF8" in capsys.readouterr().err


def test_stat_inode_returns_real_inode(tmp_path: Path):
    log = tmp_path / "f.log"
    log.write_text("a")
    inode = stat_inode(log)
    assert inode == log.stat().st_ino


def test_iter_lines_since_handles_non_utf8(tmp_path: Path, capsys):
    log = tmp_path / "openclaw.log"
    good = _line("2026-06-01T00:00:00+00:00", "ok") + "\n"
    bad = b"\xff\xfe not utf-8 \xff\xfe\n"
    with log.open("wb") as fp:
        fp.write(good.encode("utf-8"))
        fp.write(bad)
        fp.write(good.encode("utf-8"))
    results = list(iter_lines_since(log, None))
    # The two well-formed lines come through; the binary garbage is
    # logged and skipped.
    assert len(results) == 2
    captured = capsys.readouterr()
    assert "non-UTF8" in captured.err
