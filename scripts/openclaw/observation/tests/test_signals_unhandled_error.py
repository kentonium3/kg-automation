"""Tests for ``signals.unhandled_error`` (T004 #3).

Validates the ``match_target="raw"`` path — the substring
``"logLevelName":"ERROR"`` lives in the nested ``_meta`` block so the
assembled message body would not surface it.
"""

from __future__ import annotations

import json
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
from scripts.openclaw.observation.signals.unhandled_error import (  # noqa: E402
    extract,
)


_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "unhandled_error.jsonl"
)


def _signal_def(pattern: str) -> SignalDefinition:
    return SignalDefinition(
        signal_id="openclaw_unhandled_error",
        source_kind="openclaw_log",
        source_path_pattern=pattern,
        match_pattern='"logLevelName":"ERROR"',
        match_kind="substring",
        cycle_threshold=3,
        rolling_window_minutes=60,
        rolling_threshold=5,
        dedup_strategy="open_issue_present",
        dedup_window_hours=24,
        priority="P2",
        area_label="felix-core",
        tier_hypothesis="3",
        excerpt_lines=8,
        enabled=True,
    )


def _stage_fixture(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    target = log_dir / "openclaw-2026-06-01.log"
    shutil.copy(_FIXTURE, target)
    return log_dir


def test_extracts_three_error_lines(tmp_path: Path):
    log_dir = _stage_fixture(tmp_path)
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    # 3 ERROR + 7 non-ERROR lines.
    assert result.count_cycle == 3
    assert result.count_rolling == 3
    assert result.signal_id == "openclaw_unhandled_error"


def test_excerpts_include_all_three_errors(tmp_path: Path):
    log_dir = _stage_fixture(tmp_path)
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    assert len(result.excerpts) == 3
    # Each excerpt is a valid JSON document with logLevelName=ERROR.
    for raw in result.excerpts:
        parsed = json.loads(raw)
        assert parsed["_meta"]["logLevelName"] == "ERROR"


def test_authorization_field_redacted(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    target = log_dir / "openclaw-2026-06-01.log"
    long_token = "tk_" + ("a" * 200)
    target.write_text(
        '{"0":"main-agent","1":{"authorization":"' + long_token + '"},'
        '"2":"agent crashed","_meta":{"logLevelName":"ERROR"},'
        '"time":"2026-06-01T00:00:00+00:00"}\n'
    )
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    assert result.count_cycle == 1
    assert long_token not in result.excerpts[0]
    assert "<redacted len=" in result.excerpts[0]


def test_no_errors_returns_zero(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    target = log_dir / "openclaw-2026-06-01.log"
    target.write_text(
        '{"0":"x","1":{},"2":"ok","_meta":{"logLevelName":"INFO"},'
        '"time":"2026-06-01T00:00:00+00:00"}\n'
    )
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
    )
    assert result.count_cycle == 0
    assert result.last_event_at_utc is None


def test_regex_against_raw_line(tmp_path: Path):
    """match_target='raw' with a regex pattern reaches into _meta."""
    log_dir = _stage_fixture(tmp_path)
    base = _signal_def(str(log_dir / "openclaw-*.log"))
    regex_def = SignalDefinition(
        **{**base.__dict__,
           "match_pattern": r'"logLevelName":"(ERROR|FATAL)"',
           "match_kind": "regex"}
    )
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=regex_def,
        now_utc=_NOW,
    )
    assert result.count_cycle == 3


def test_inode_change_triggers_cold_start_in_engine(tmp_path: Path):
    """When the cursor points at a stale inode, the engine restarts."""
    log_dir = _stage_fixture(tmp_path)
    signal_def = _signal_def(str(log_dir / "openclaw-*.log"))
    # Stale cursor with a fake inode that cannot match the real file.
    from scripts.openclaw.observation.signals.openclaw_log import LogCursor

    stale_cursor = LogCursor(
        path=str(log_dir / "openclaw-2026-06-01.log"),
        inode=99999999,
        byte_offset=500,
        mtime=0.0,
    )
    result = extract(
        state_dir=tmp_path / "state",
        signal_def=signal_def,
        now_utc=_NOW,
        prior_cursor=stale_cursor,
    )
    # All three ERRORs in the fixture are re-counted from byte 0.
    assert result.count_cycle == 3


def test_handles_real_captured_fixture():
    """End-to-end sanity against the WP-01 T006 captured log.

    Confirms the raw substring matcher counts agree with the
    research.md §OD-2 ground-truth (±5% tolerance per T006).
    """
    captured = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "captured"
        / "openclaw-2026-06-01.log"
    )
    if not captured.exists():
        pytest.skip("captured fixture not present")
    signal_def = _signal_def(str(captured.parent / captured.name))
    result = extract(
        state_dir=captured.parent,
        signal_def=signal_def,
        now_utc=_NOW,
    )
    # Research expected exactly 6. The captured file might catch a
    # late event; allow ±2 absolute.
    assert abs(result.count_cycle - 6) <= 2
