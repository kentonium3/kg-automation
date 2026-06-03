"""Tests for ``scripts.openclaw.observation.signals.sweeper_tick`` (#510).

Coverage targets per the mission contract's "Test obligations" table:

- ``success_recent`` — fresh non-dry-run success ⇒ count_cycle=0.
- ``failed_exit`` — non-success exit_status ⇒ count_cycle=1.
- ``errors_non_empty`` — errors[] non-empty even with success ⇒ count_cycle=1.
- ``stale_recent`` — latest started_at_utc beyond 26h ⇒ count_cycle=1.
- ``dry_run_only`` — ledger has only dry-runs ⇒ count_cycle=1.
- ``empty_ledger`` — ledger file exists but empty ⇒ count_cycle=1.
- ``missing_ledger`` — ledger file does not exist ⇒ count_cycle=1.
- ``partial_line_tolerated`` — trailing partial JSON line skipped ⇒ count_cycle=0.

Plus two cross-cutting checks:

- ``rolling_accumulates`` — prior_rolling_count + count_cycle.
- ``signal_id_pass_through`` — returned SignalExtraction.signal_id matches.

The extractor reads a JSONL ledger and is pure: no patches needed beyond
fixture ledger paths.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.openclaw.observation.signals.config_loader import (  # noqa: E402
    SignalDefinition,
)
from scripts.openclaw.observation.signals.sweeper_tick import (  # noqa: E402
    STALE_THRESHOLD_HOURS,
    extract,
)


_NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _signal_def(ledger_path: Path) -> SignalDefinition:
    """Build a SignalDefinition pointing at ``ledger_path``."""
    return SignalDefinition(
        signal_id="sweeper_tick",
        source_kind="sweeper_ledger_jsonl",
        source_path_pattern=str(ledger_path),
        match_pattern="",
        match_kind="substring",
        cycle_threshold=1,
        rolling_window_minutes=60,
        rolling_threshold=1,
        dedup_strategy="open_issue_present",
        dedup_window_hours=24,
        priority="P2",
        area_label="felix-core",
        tier_hypothesis="3",
        excerpt_lines=1,
        enabled=True,
    )


def _write_ledger(path: Path, records: list[dict]) -> None:
    """Write ``records`` to ``path`` as JSONL (one record per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _success_record(
    started_at_utc: str,
    *,
    dry_run: bool = False,
    tick_id: str = "01TEST",
) -> dict:
    """Build a minimal success record per the sweeper-tick contract."""
    return {
        "schema_version": 1,
        "tick_id": tick_id,
        "started_at_utc": started_at_utc,
        "duration_ms": 100,
        "dry_run": dry_run,
        "expired_checkin_dates_evaluated": [],
        "habits_evaluated": [],
        "habits_auto_skipped": [],
        "errors": [],
        "exit_status": "success",
    }


def _iso(dt: datetime) -> str:
    """Format ``dt`` as ISO-8601 UTC with ``Z`` suffix."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _call_extract(ledger_path: Path, *, prior_rolling: int = 0):
    """Helper: call extract() with the standard fixed _NOW and ledger_path."""
    return extract(
        state_dir=ledger_path.parent,
        signal_def=_signal_def(ledger_path),
        now_utc=_NOW,
        prior_cursor=None,
        prior_rolling_count=prior_rolling,
    )


# ---------------------------------------------------------------------------
# Named test cases — per contracts/sweeper-tick-extractor.contract.md
# ---------------------------------------------------------------------------


def test_success_recent(tmp_path: Path):
    """One fresh non-dry-run success ⇒ no trip."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    fresh_ts = _NOW - timedelta(hours=1)
    _write_ledger(ledger, [_success_record(_iso(fresh_ts))])

    result = _call_extract(ledger)

    assert result.count_cycle == 0
    assert result.excerpts == []
    assert result.last_event_at_utc is not None
    assert result.last_event_at_utc.replace(microsecond=0) == fresh_ts.replace(
        microsecond=0
    )


@pytest.mark.parametrize(
    "exit_status",
    [
        "vikunja_unreachable",
        "malformed_schedule_yaml",
        "vikunja_put_failed",
        "aborted",
    ],
)
def test_failed_exit(tmp_path: Path, exit_status: str):
    """Non-success exit_status ⇒ trip; excerpt is the record JSON."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    fresh_ts = _NOW - timedelta(hours=1)
    record = _success_record(_iso(fresh_ts))
    record["exit_status"] = exit_status
    _write_ledger(ledger, [record])

    result = _call_extract(ledger)

    assert result.count_cycle == 1
    assert len(result.excerpts) == 1
    parsed = json.loads(result.excerpts[0])
    assert parsed["exit_status"] == exit_status


def test_errors_non_empty(tmp_path: Path):
    """Errors array non-empty even with success exit_status ⇒ trip."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    fresh_ts = _NOW - timedelta(hours=1)
    record = _success_record(_iso(fresh_ts))
    record["errors"] = [{"task_id": 14, "reason": "vikunja PUT 500"}]
    _write_ledger(ledger, [record])

    result = _call_extract(ledger)

    assert result.count_cycle == 1
    parsed = json.loads(result.excerpts[0])
    assert parsed["errors"] == [{"task_id": 14, "reason": "vikunja PUT 500"}]
    assert parsed["exit_status"] == "success"


def test_stale_recent(tmp_path: Path):
    """Latest started_at_utc beyond 26 hours ⇒ trip with synthetic excerpt."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    stale_ts = _NOW - timedelta(hours=STALE_THRESHOLD_HOURS + 1)
    _write_ledger(ledger, [_success_record(_iso(stale_ts))])

    result = _call_extract(ledger)

    assert result.count_cycle == 1
    parsed = json.loads(result.excerpts[0])
    assert parsed["reason"] == "stale_production_record"
    assert parsed["threshold_hours"] == STALE_THRESHOLD_HOURS
    assert parsed["age_hours"] == STALE_THRESHOLD_HOURS + 1


def test_dry_run_only(tmp_path: Path):
    """Ledger of only dry-runs ⇒ trip with synthetic no-record excerpt."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    fresh_ts = _NOW - timedelta(hours=1)
    records = [
        _success_record(_iso(fresh_ts), dry_run=True, tick_id=f"01DRY{i}")
        for i in range(3)
    ]
    _write_ledger(ledger, records)

    result = _call_extract(ledger)

    assert result.count_cycle == 1
    parsed = json.loads(result.excerpts[0])
    assert parsed["reason"] == "no_production_record"
    assert parsed["ledger_exists"] is True
    assert parsed["ledger_record_count"] == 3
    assert parsed["dry_run_only_count"] == 3
    assert result.last_event_at_utc is None


def test_empty_ledger(tmp_path: Path):
    """Empty ledger file ⇒ trip with synthetic no-record excerpt."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    ledger.touch()

    result = _call_extract(ledger)

    assert result.count_cycle == 1
    parsed = json.loads(result.excerpts[0])
    assert parsed["reason"] == "no_production_record"
    assert parsed["ledger_exists"] is True
    assert parsed["ledger_record_count"] == 0


def test_missing_ledger(tmp_path: Path):
    """Missing ledger file ⇒ trip with synthetic no-record excerpt."""
    ledger = tmp_path / "does-not-exist.jsonl"

    result = _call_extract(ledger)

    assert result.count_cycle == 1
    parsed = json.loads(result.excerpts[0])
    assert parsed["reason"] == "no_production_record"
    assert parsed["ledger_exists"] is False
    assert parsed["ledger_record_count"] == 0


def test_partial_line_tolerated(tmp_path: Path):
    """Trailing partial JSON line is silently skipped; previous line wins."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    fresh_ts = _NOW - timedelta(hours=1)
    good_line = json.dumps(_success_record(_iso(fresh_ts)))
    partial_line = '{"schema_version":1,"tick_id":"01PART","started_at_utc":"2026-06-03'  # noqa: E501
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(good_line + "\n" + partial_line + "\n", encoding="utf-8")

    result = _call_extract(ledger)

    # The partial line is unparseable; the prior complete success record wins.
    assert result.count_cycle == 0
    assert result.excerpts == []


# ---------------------------------------------------------------------------
# Cross-cutting checks
# ---------------------------------------------------------------------------


def test_rolling_accumulates(tmp_path: Path):
    """prior_rolling_count is added to count_cycle for count_rolling."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    fresh_ts = _NOW - timedelta(hours=1)
    record = _success_record(_iso(fresh_ts))
    record["exit_status"] = "vikunja_unreachable"
    _write_ledger(ledger, [record])

    result = _call_extract(ledger, prior_rolling=2)

    assert result.count_cycle == 1
    assert result.count_rolling == 3


def test_signal_id_pass_through(tmp_path: Path):
    """The returned SignalExtraction.signal_id matches the SignalDefinition."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    fresh_ts = _NOW - timedelta(hours=1)
    _write_ledger(ledger, [_success_record(_iso(fresh_ts))])

    result = _call_extract(ledger)

    assert result.signal_id == "sweeper_tick"


def test_extract_rejects_naive_now_utc(tmp_path: Path):
    """now_utc must be tz-aware."""
    ledger = tmp_path / "sweeper-ledger.jsonl"
    fresh_ts = _NOW - timedelta(hours=1)
    _write_ledger(ledger, [_success_record(_iso(fresh_ts))])

    with pytest.raises(ValueError, match="tz-aware|timezone-aware"):
        extract(
            state_dir=ledger.parent,
            signal_def=_signal_def(ledger),
            now_utc=datetime(2026, 6, 3, 12, 0, 0),  # naive
            prior_cursor=None,
            prior_rolling_count=0,
        )
