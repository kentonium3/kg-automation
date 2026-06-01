"""Tests for ``state.py`` — per-signal state persistence.

Covers WP-01 T002's validation checklist:

- ``load_state`` returns ``None`` for missing file.
- Round-trip ``save_state`` → ``load_state`` returns equal state.
- Atomic write (no partial-read window).
- ``evict_old_buckets`` drops only buckets older than the cutoff.
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

from scripts.openclaw.observation.state import (  # noqa: E402
    COLD_START_RECOVERY_CYCLES,
    CYCLE_DURATION_SECONDS,
    RollingBucket,
    SignalState,
    cold_start_recovery_window_seconds,
    evict_old_buckets,
    load_state,
    save_state,
)


def _bucket(started_at: str, count: int = 1) -> RollingBucket:
    return RollingBucket(
        cycle_id=f"cycle-{started_at}",
        started_at=started_at,
        count=count,
    )


def test_load_state_returns_none_for_missing_file(tmp_path: Path):
    assert load_state(tmp_path, "missing_signal") is None


def test_round_trip(tmp_path: Path):
    state = SignalState(
        signal_id="creds_restore",
        cycle_id="cycle-01",
        last_cycle_count=4,
        rolling_buckets=[
            _bucket("2026-06-01T00:00:00Z", 2),
            _bucket("2026-06-01T00:15:00Z", 3),
        ],
        last_event_at_utc="2026-06-01T00:14:00Z",
        last_filed_issue_ref=490,
        last_filed_at_utc="2026-06-01T00:15:00Z",
        last_log_position={
            "path": "/tmp/openclaw/openclaw-2026-06-01.log",
            "byte_offset": 1024,
            "mtime": 1717200000.0,
            "inode": 999,
        },
    )
    save_state(tmp_path, state)
    loaded = load_state(tmp_path, "creds_restore")
    assert loaded == state


def test_round_trip_minimal_state(tmp_path: Path):
    state = SignalState(
        signal_id="minimal",
        cycle_id="cycle-00",
        last_cycle_count=0,
    )
    save_state(tmp_path, state)
    loaded = load_state(tmp_path, "minimal")
    assert loaded == state
    # Optional fields stay None
    assert loaded.last_event_at_utc is None
    assert loaded.last_filed_issue_ref is None
    assert loaded.last_filed_at_utc is None
    assert loaded.last_log_position is None
    assert loaded.rolling_buckets == []


def test_save_state_writes_atomically_via_rename(tmp_path: Path):
    """The temp file must not survive a successful rename."""
    state = SignalState(
        signal_id="atomic_signal",
        cycle_id="cycle-00",
        last_cycle_count=0,
    )
    save_state(tmp_path, state)
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["atomic_signal.json"]
    # No ``.tmp`` orphan remains.
    assert not any(p.suffix == ".tmp" for p in tmp_path.iterdir())


def test_save_state_overwrites_prior_version_atomically(tmp_path: Path):
    state_v1 = SignalState(
        signal_id="atomic_signal",
        cycle_id="cycle-00",
        last_cycle_count=1,
    )
    save_state(tmp_path, state_v1)

    state_v2 = SignalState(
        signal_id="atomic_signal",
        cycle_id="cycle-01",
        last_cycle_count=7,
    )
    save_state(tmp_path, state_v2)
    loaded = load_state(tmp_path, "atomic_signal")
    assert loaded == state_v2


def test_load_state_raises_on_invalid_json(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_state(tmp_path, "broken")


def test_load_state_raises_on_missing_required_field(tmp_path: Path):
    path = tmp_path / "halfbaked.json"
    path.write_text(json.dumps({"signal_id": "halfbaked"}))
    with pytest.raises(ValueError, match="missing"):
        load_state(tmp_path, "halfbaked")


def test_evict_old_buckets_keeps_recent_drops_stale():
    now = datetime(2026, 6, 1, 1, 0, 0, tzinfo=timezone.utc)
    state = SignalState(
        signal_id="evict_signal",
        cycle_id="cycle-04",
        last_cycle_count=0,
        rolling_buckets=[
            _bucket("2026-05-31T23:30:00Z", 1),  # 90 min old — drop
            _bucket("2026-05-31T23:55:00Z", 2),  # 65 min old — drop
            _bucket("2026-06-01T00:15:00Z", 3),  # 45 min old — keep
            _bucket("2026-06-01T00:55:00Z", 4),  # 5 min old — keep
        ],
    )
    evicted = evict_old_buckets(state, window_minutes=60, now_utc=now)
    assert [b.count for b in evicted.rolling_buckets] == [3, 4]
    # Returned object is a new instance; caller decides whether to
    # overwrite the prior reference.
    assert evicted is not state


def test_evict_old_buckets_rejects_naive_now():
    state = SignalState(
        signal_id="naive_now",
        cycle_id="cycle-00",
        last_cycle_count=0,
        rolling_buckets=[_bucket("2026-06-01T00:00:00Z", 1)],
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        evict_old_buckets(
            state, window_minutes=60, now_utc=datetime(2026, 6, 1, 0, 30)
        )


def test_evict_old_buckets_drops_malformed_timestamp():
    """Bucket with junk in started_at is dropped, not raised on."""
    state = SignalState(
        signal_id="malformed_bucket",
        cycle_id="cycle-00",
        last_cycle_count=0,
        rolling_buckets=[
            RollingBucket(cycle_id="x", started_at="not-a-date", count=9),
            _bucket("2026-06-01T00:55:00Z", 1),
        ],
    )
    now = datetime(2026, 6, 1, 1, 0, 0, tzinfo=timezone.utc)
    evicted = evict_old_buckets(state, window_minutes=60, now_utc=now)
    assert len(evicted.rolling_buckets) == 1
    assert evicted.rolling_buckets[0].count == 1


def test_cold_start_recovery_window_seconds_is_one_hour():
    # 4 cycles × 900s = 3600s, per data-model.md §E2.
    assert COLD_START_RECOVERY_CYCLES * CYCLE_DURATION_SECONDS == 3600
    assert cold_start_recovery_window_seconds() == 3600


def test_save_then_load_preserves_field_order(tmp_path: Path):
    """Defensive: dict ordering should not affect equality."""
    state = SignalState(
        signal_id="order_test",
        cycle_id="cycle-00",
        last_cycle_count=1,
        rolling_buckets=[
            _bucket("2026-06-01T00:00:00Z", 1),
            _bucket("2026-06-01T00:15:00Z", 2),
        ],
        last_event_at_utc="2026-06-01T00:14:00Z",
    )
    save_state(tmp_path, state)
    loaded = load_state(tmp_path, "order_test")
    assert loaded.rolling_buckets == state.rolling_buckets


def test_evict_at_exact_cutoff_keeps_bucket():
    """A bucket exactly at the cutoff stays — boundary is inclusive."""
    now = datetime(2026, 6, 1, 1, 0, 0, tzinfo=timezone.utc)
    sixty_min_ago = (now - timedelta(minutes=60)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    state = SignalState(
        signal_id="boundary",
        cycle_id="cycle-00",
        last_cycle_count=0,
        rolling_buckets=[_bucket(sixty_min_ago, 1)],
    )
    evicted = evict_old_buckets(state, window_minutes=60, now_utc=now)
    assert len(evicted.rolling_buckets) == 1
