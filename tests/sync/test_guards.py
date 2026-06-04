"""Tests for scripts/sync/guards.py (WP03 / T013).

Pure tests over the three guards + apply order + event_id_stem + day rollover.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from scripts.sync import guards as g
from scripts.sync.diff import DivergenceCandidate
from scripts.sync.state import (
    G3DailyCap,
    GuardState,
    TaskCacheEntry,
    TaskCacheRecord,
)


CYCLE_STARTED = datetime(2026, 6, 4, 19, 25, 30, tzinfo=timezone.utc)
TODAY_ET = "2026-06-04"


def _candidate(field: str = "title", entity_id: int = 14) -> DivergenceCandidate:
    return DivergenceCandidate(
        vikunja_entity_id=entity_id,
        field=field,
        vikunja_value="new",
        felix_cached_value="old",
        vikunja_updated_at="2026-06-04T18:32:00Z",
        ts_observed_utc="2026-06-04T19:25:30Z",
    )


def _guard_state(*, count: int = 0, cap: int = 5, day: str = TODAY_ET) -> GuardState:
    return GuardState(
        g3_daily_cap=G3DailyCap(
            calendar_day_et=day,
            unsafe_pings_sent_today=count,
            cap=cap,
        ),
    )


def _task_cache(*, last_observed: str | None = None, task_id: int = 14) -> TaskCacheRecord:
    if last_observed is None:
        return TaskCacheRecord(last_updated_utc="2026-06-04T19:20:30Z", tasks={})
    return TaskCacheRecord(
        last_updated_utc="2026-06-04T19:20:30Z",
        tasks={
            str(task_id): TaskCacheEntry(
                vikunja_task_id=task_id,
                fields={},
                vikunja_updated_at="2026-06-04T18:32:00Z",
                felix_last_observed_at=last_observed,
            ),
        },
    )


# ===========================================================================
# Group 1 — event_id_stem
# ===========================================================================


class TestEventIdStem:
    def test_returns_16_char_lowercase_hex(self):
        stem = g.event_id_stem("status_and_task", 14, "due_date")
        assert len(stem) == 16
        assert all(ch in "0123456789abcdef" for ch in stem)

    def test_deterministic(self):
        a = g.event_id_stem("status_and_task", 14, "due_date")
        b = g.event_id_stem("status_and_task", 14, "due_date")
        assert a == b

    def test_different_fields_differ(self):
        a = g.event_id_stem("status_and_task", 14, "due_date")
        b = g.event_id_stem("status_and_task", 14, "title")
        assert a != b

    def test_different_entities_differ(self):
        a = g.event_id_stem("status_and_task", 14, "title")
        b = g.event_id_stem("status_and_task", 15, "title")
        assert a != b


# ===========================================================================
# Group 2 — now_et_day + roll
# ===========================================================================


class TestNowEtDay:
    def test_utc_morning_is_previous_day_et(self):
        # 2026-06-04T03:00:00Z = 2026-06-03T23:00:00 EDT (UTC-4 in June)
        now = datetime(2026, 6, 4, 3, 0, 0, tzinfo=timezone.utc)
        assert g.now_et_day(now) == "2026-06-03"

    def test_utc_evening_same_day_et(self):
        now = datetime(2026, 6, 4, 19, 25, 30, tzinfo=timezone.utc)
        assert g.now_et_day(now) == "2026-06-04"


class TestRollG3Day:
    def test_same_day_returns_unchanged(self):
        gs = _guard_state(count=3, day=TODAY_ET)
        result = g.roll_g3_day_if_needed(gs, TODAY_ET)
        assert result == gs

    def test_different_day_resets_count(self):
        gs = _guard_state(count=4, cap=5, day="2026-06-03")
        result = g.roll_g3_day_if_needed(gs, TODAY_ET)
        assert result.g3_daily_cap.calendar_day_et == TODAY_ET
        assert result.g3_daily_cap.unsafe_pings_sent_today == 0
        assert result.g3_daily_cap.cap == 5  # cap preserved

    def test_input_not_mutated(self):
        gs = _guard_state(count=4, cap=5, day="2026-06-03")
        g.roll_g3_day_if_needed(gs, TODAY_ET)
        assert gs.g3_daily_cap.unsafe_pings_sent_today == 4
        assert gs.g3_daily_cap.calendar_day_et == "2026-06-03"


# ===========================================================================
# Group 3 — G-3 (daily cap)
# ===========================================================================


class TestApplyG3:
    def test_under_cap_does_not_suppress(self):
        gs = _guard_state(count=2, cap=5)
        assert g.apply_g3(gs, TODAY_ET) is None

    def test_at_cap_suppresses(self):
        gs = _guard_state(count=5, cap=5)
        decision = g.apply_g3(gs, TODAY_ET)
        assert decision is not None
        assert decision.decision == "suppress"
        assert decision.suppressed_by == "g3"

    def test_over_cap_suppresses(self):
        gs = _guard_state(count=10, cap=5)
        decision = g.apply_g3(gs, TODAY_ET)
        assert decision.suppressed_by == "g3"

    def test_different_day_does_not_suppress_even_if_count_high(self):
        # Stored state is from yesterday; today's first ping is allowed.
        gs = _guard_state(count=10, cap=5, day="2026-06-03")
        assert g.apply_g3(gs, TODAY_ET) is None


# ===========================================================================
# Group 4 — G-2 (post-Felix-write suppression)
# ===========================================================================


class TestApplyG2:
    def test_within_30_min_suppresses(self):
        # 5 minutes before cycle start.
        cache = _task_cache(last_observed=(CYCLE_STARTED - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        decision = g.apply_g2(_candidate(), cache, CYCLE_STARTED)
        assert decision is not None
        assert decision.suppressed_by == "g2"

    def test_at_30_min_boundary_suppresses(self):
        cache = _task_cache(last_observed=(CYCLE_STARTED - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        decision = g.apply_g2(_candidate(), cache, CYCLE_STARTED)
        assert decision is not None
        assert decision.suppressed_by == "g2"

    def test_just_outside_window_does_not_suppress(self):
        # 31 minutes before cycle start.
        cache = _task_cache(last_observed=(CYCLE_STARTED - timedelta(minutes=31)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        assert g.apply_g2(_candidate(), cache, CYCLE_STARTED) is None

    def test_missing_cache_entry_does_not_suppress(self):
        cache = _task_cache(last_observed=None)
        assert g.apply_g2(_candidate(), cache, CYCLE_STARTED) is None

    def test_unparseable_timestamp_does_not_suppress(self):
        cache = _task_cache(last_observed="not-an-iso-string")
        assert g.apply_g2(_candidate(), cache, CYCLE_STARTED) is None


# ===========================================================================
# Group 5 — G-1 (24h event-id-stem dedup)
# ===========================================================================


class TestApplyG1:
    def test_no_recent_events_does_not_suppress(self):
        assert g.apply_g1(_candidate(), recent_events=[]) is None

    def test_matching_stem_delivered_suppresses(self):
        cand = _candidate(field="title", entity_id=14)
        stem = g.event_id_stem("status_and_task", 14, "title")
        recent = [{"event_id": stem + "abc1", "delivery_status": "delivered"}]
        decision = g.apply_g1(cand, recent_events=recent)
        assert decision is not None
        assert decision.suppressed_by == "g1"

    def test_matching_stem_not_unsafe_suppresses(self):
        # auto_resolved events also count toward G-1 dedup.
        cand = _candidate(field="title", entity_id=14)
        stem = g.event_id_stem("status_and_task", 14, "title")
        recent = [{"event_id": stem + "abc1", "delivery_status": "not_unsafe"}]
        decision = g.apply_g1(cand, recent_events=recent)
        assert decision is not None
        assert decision.suppressed_by == "g1"

    def test_matching_stem_suppressed_g3_does_not_count(self):
        # A prior G-3-suppressed event should NOT count toward G-1 dedup.
        cand = _candidate(field="title", entity_id=14)
        stem = g.event_id_stem("status_and_task", 14, "title")
        recent = [{"event_id": stem + "abc1", "delivery_status": "suppressed_by_g3"}]
        assert g.apply_g1(cand, recent_events=recent) is None

    def test_different_field_stem_does_not_match(self):
        cand = _candidate(field="title", entity_id=14)
        wrong_stem = g.event_id_stem("status_and_task", 14, "due_date")
        recent = [{"event_id": wrong_stem + "abc1", "delivery_status": "delivered"}]
        assert g.apply_g1(cand, recent_events=recent) is None

    def test_different_entity_does_not_match(self):
        cand = _candidate(field="title", entity_id=14)
        wrong_stem = g.event_id_stem("status_and_task", 15, "title")
        recent = [{"event_id": wrong_stem + "abc1", "delivery_status": "delivered"}]
        assert g.apply_g1(cand, recent_events=recent) is None

    def test_event_without_event_id_skipped(self):
        cand = _candidate()
        recent = [{"delivery_status": "delivered"}]  # malformed: missing event_id
        assert g.apply_g1(cand, recent_events=recent) is None


# ===========================================================================
# Group 6 — apply_guards (order is the contract)
# ===========================================================================


class TestApplyGuardsOrder:
    def test_approve_when_no_guard_fires(self):
        gs = _guard_state(count=0, cap=5)
        cache = _task_cache(last_observed=None)
        decision = g.apply_guards(
            _candidate(),
            cache,
            gs,
            recent_events=[],
            cycle_started_at=CYCLE_STARTED,
            now_et_day_str=TODAY_ET,
        )
        assert decision.decision == "approve"
        assert decision.suppressed_by is None

    def test_g3_fires_first_even_if_g2_g1_would_also(self):
        # All three guards would fire; G-3 wins per the contract.
        gs = _guard_state(count=5, cap=5)
        cache = _task_cache(
            last_observed=(CYCLE_STARTED - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        cand = _candidate()
        stem = g.event_id_stem("status_and_task", 14, "title")
        recent = [{"event_id": stem + "x", "delivery_status": "delivered"}]
        decision = g.apply_guards(
            cand, cache, gs, recent, CYCLE_STARTED, TODAY_ET
        )
        assert decision.suppressed_by == "g3"

    def test_g2_fires_before_g1_when_g3_does_not(self):
        gs = _guard_state(count=0, cap=5)
        cache = _task_cache(
            last_observed=(CYCLE_STARTED - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        cand = _candidate()
        stem = g.event_id_stem("status_and_task", 14, "title")
        recent = [{"event_id": stem + "x", "delivery_status": "delivered"}]
        decision = g.apply_guards(cand, cache, gs, recent, CYCLE_STARTED, TODAY_ET)
        assert decision.suppressed_by == "g2"

    def test_g1_fires_when_g3_and_g2_do_not(self):
        gs = _guard_state(count=0, cap=5)
        # Felix wrote more than 30 min ago → G-2 does NOT fire.
        cache = _task_cache(
            last_observed=(CYCLE_STARTED - timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        cand = _candidate()
        stem = g.event_id_stem("status_and_task", 14, "title")
        recent = [{"event_id": stem + "x", "delivery_status": "delivered"}]
        decision = g.apply_guards(cand, cache, gs, recent, CYCLE_STARTED, TODAY_ET)
        assert decision.suppressed_by == "g1"


# ===========================================================================
# Group 7 — Module sanity
# ===========================================================================


class TestModuleConstants:
    def test_defaults(self):
        assert g.G1_LOOKBACK_HOURS == 24
        assert g.G2_POST_WRITE_SUPPRESSION_MINUTES == 30
        assert g.G3_DAILY_CAP_DEFAULT == 5
