"""Tests for ``signals.watchdog_reconnect`` (T004 #2).

Mirrors ``test_signals_creds_restore.py`` but matches against the
``web reconnect: connection closed`` substring per FR-006 #2.
"""

from __future__ import annotations

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
from scripts.openclaw.observation.signals.watchdog_reconnect import (  # noqa: E402
    extract,
)


_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "watchdog_reconnect.jsonl"
)


def _signal_def(pattern: str) -> SignalDefinition:
    return SignalDefinition(
        signal_id="web_watchdog_reconnect",
        source_kind="openclaw_log",
        source_path_pattern=pattern,
        match_pattern="web reconnect: connection closed",
        match_kind="substring",
        cycle_threshold=10,
        rolling_window_minutes=60,
        rolling_threshold=25,
        dedup_strategy="open_issue_present",
        dedup_window_hours=24,
        priority="P2",
        area_label="felix-core",
        tier_hypothesis="3",
        excerpt_lines=5,
        enabled=True,
    )


def _stage_fixture(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    target = log_dir / "openclaw-2026-06-01.log"
    shutil.copy(_FIXTURE, target)
    return log_dir


def test_extracts_five_matches_from_fixture(tmp_path: Path):
    log_dir = _stage_fixture(tmp_path)
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    # 5 matching + 5 non-matching lines.
    assert result.count_cycle == 5
    assert result.count_rolling == 5
    assert result.signal_id == "web_watchdog_reconnect"
    assert result.last_event_at_utc is not None


def test_resume_from_cursor_doesnt_double_count(tmp_path: Path):
    log_dir = _stage_fixture(tmp_path)
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    first = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    # Re-run with the cursor from the first pass — no new lines, so
    # nothing should be re-counted.
    second = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
        prior_cursor=first.new_cursor,
    )
    assert second.count_cycle == 0
    assert second.new_cursor.byte_offset == first.new_cursor.byte_offset


def test_regex_match_kind(tmp_path: Path):
    log_dir = _stage_fixture(tmp_path)
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    # Patch the pattern to a regex covering both ``reconnect`` and the
    # closure message — should still match all five.
    regex_def = SignalDefinition(
        **{**signal_def.__dict__,
           "match_pattern": r"web reconnect.*closed",
           "match_kind": "regex"}
    )
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=regex_def,
        now_utc=_NOW,
    )
    assert result.count_cycle == 5


def test_no_logs_returns_prior_rolling(tmp_path: Path):
    signal_def = _signal_def(str(tmp_path / "no-such-dir" / "*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
        prior_rolling_count=3,
    )
    assert result.count_cycle == 0
    assert result.count_rolling == 3
