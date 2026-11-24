"""Tests for the pure crash-loop decision core (mission #1133, WP02 T010).

``now`` is injected everywhere; nothing here reads the clock. Tick sequences
are written as ``(minute, restart_count)`` pairs from ``T0`` unless stated.
"""

from __future__ import annotations

import bisect
import copy
import itertools
import random
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType

import pytest

from scripts.canary import crash_loop
from scripts.canary.crash_loop import (
    AGGREGATE_SOURCE,
    COUNT_KEYS,
    TickOutcome,
    _maintain_history,
    evaluate_tick,
    plan_emissions,
    prove,
    render_aggregate,
    render_alert,
)
from scripts.canary.crash_loop_model import (
    HISTORY_MAX,
    SCOPES,
    CrashLoopConfig,
    CrashLoopEvent,
    Proof,
    RestartObservation,
    ScopeReading,
)
from scripts.canary.crash_loop_state import CrashLoopState, Episode, UnitState
from scripts.common.alert_bus.model import Alert, Severity
from scripts.common.alert_bus.render import DESCRIPTION_MAX, DETAIL_VALUE_MAX

T0 = datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC)
BOOT_A = "boot-aaaa"
BOOT_B = "boot-bbbb"
OBSIDIAN = "system:obsidian-sync.service"
RUNNING = "active (running)"


def cfg(
    *,
    threshold: int = 3,
    window_seconds: int = 900,
    quiet_ticks_to_clear: int = 2,
    max_alerts_per_tick: int = 3,
    ignore: Iterable[str] = (),
) -> CrashLoopConfig:
    ignored = frozenset(ignore)
    return CrashLoopConfig(
        threshold=threshold,
        window_seconds=window_seconds,
        quiet_ticks_to_clear=quiet_ticks_to_clear,
        max_alerts_per_tick=max_alerts_per_tick,
        read_budget_seconds=6,
        ignore=ignored,
        ignore_reasons=MappingProxyType(dict.fromkeys(ignored, "test")),
    )


CFG = cfg()


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def obs(
    key: str,
    count: int,
    *,
    generation: str | None = None,
    state: str = RUNNING,
    boot: str = BOOT_A,
) -> RestartObservation:
    scope, name = key.split(":", 1)
    if generation is None:
        generation = "cid-1" if scope == "container" else boot
    policy = "unless-stopped" if scope == "container" else "always"
    return RestartObservation(
        scope=scope,
        name=name,
        restart_policy=policy,
        restart_count=count,
        state=state,
        generation=generation,
    )


def readings(
    observations: Iterable[RestartObservation],
    *,
    incomplete: Iterable[str] = (),
    missing: Iterable[str] = (),
) -> list[ScopeReading]:
    observations = list(observations)
    failed = set(incomplete)
    absent = set(missing)
    out: list[ScopeReading] = []
    for scope in SCOPES:
        if scope in absent:
            continue
        if scope in failed:
            out.append(ScopeReading.failed(scope, f"{scope} read failed", 7))
        else:
            mine = tuple(o for o in observations if o.scope == scope)
            out.append(ScopeReading.ok(scope, mine, excluded=1, elapsed_ms=5))
    return out


class Sim:
    """Runs successive ticks, threading the state through."""

    def __init__(self, config: CrashLoopConfig = CFG) -> None:
        self.config = config
        self.state = CrashLoopState.empty()
        self.outcomes: list[TickOutcome] = []

    def tick(
        self,
        now: datetime,
        observations: Iterable[RestartObservation],
        *,
        boot: str | None = BOOT_A,
        incomplete: Iterable[str] = (),
        missing: Iterable[str] = (),
    ) -> TickOutcome:
        outcome = evaluate_tick(
            readings(observations, incomplete=incomplete, missing=missing),
            self.state,
            self.config,
            now,
            boot,
        )
        self.state = outcome.new_state
        self.outcomes.append(outcome)
        return outcome

    def unit(
        self,
        minute: float,
        count: int,
        key: str = OBSIDIAN,
        *,
        generation: str | None = None,
        boot: str = BOOT_A,
    ) -> TickOutcome:
        return self.tick(
            at(minute),
            [obs(key, count, generation=generation, boot=boot)],
            boot=boot,
        )

    def series(
        self, samples: Sequence[tuple[float, int]], key: str = OBSIDIAN
    ) -> list[TickOutcome]:
        return [self.unit(minute, count, key) for minute, count in samples]

    def all_events(self) -> list[CrashLoopEvent]:
        return [event for outcome in self.outcomes for event in outcome.events]


def kinds(outcome: TickOutcome) -> list[str]:
    return [event.kind for event in outcome.events]


def event_kinds(sim: Sim) -> list[str]:
    return [event.kind for event in sim.all_events()]


# --------------------------------------------------------------------------- #
# US1 / SC-001: the incident, user units, containers, between-tick loops.
# --------------------------------------------------------------------------- #
def test_incident_replay_obsidian_sync_39_restarts() -> None:
    sim = Sim()
    first, second = sim.series([(0, 0), (16, 39)])
    assert first.events == []
    assert first.counts["first_seen"] == 1
    assert len(second.events) == 1
    event = second.events[0]
    assert event.kind == "alert"
    assert event.key == OBSIDIAN
    assert event.state == RUNNING
    assert event.proof.delta == 39
    assert event.proof.period_seconds == 960
    assert event.proof.m == 2
    assert event.proof.bound == 5
    assert event.proof.holds
    assert event.episode_started_utc == at(16)
    assert sim.state.units[OBSIDIAN].episode is not None


def test_user_unit_and_container_alert() -> None:
    user_key = "user:openclaw-gateway.service"
    container_key = "container:vikunja"
    sim = Sim()
    sim.tick(at(0), [obs(user_key, 0), obs(container_key, 2)])
    outcome = sim.tick(at(16), [obs(user_key, 20), obs(container_key, 30)])
    assert sorted((e.key, e.kind) for e in outcome.events) == [
        (container_key, "alert"),
        (user_key, "alert"),
    ]
    by_key = {e.key: e for e in outcome.events}
    assert by_key[container_key].proof.delta == 28
    assert by_key[container_key].scope == "container"
    assert by_key[user_key].scope == "user"
    alert = render_alert(by_key[container_key], CFG)
    assert alert.source == "felix-canary:crash-loop:container:vikunja"
    assert alert.details["component_id"] == "crash-loop:container:vikunja"


def test_between_tick_loop_caught() -> None:
    # The loop started and ended between ticks; the unit is running again, but
    # the persistent counter kept every restart (FR-005).
    sim = Sim()
    sim.unit(0, 4)
    outcome = sim.tick(at(15), [obs(OBSIDIAN, 12, state=RUNNING)])
    assert kinds(outcome) == ["alert"]
    assert outcome.events[0].proof.m == 1
    assert outcome.events[0].proof.delta == 8


# --------------------------------------------------------------------------- #
# US2: the episode lifecycle.
# --------------------------------------------------------------------------- #
def test_five_tick_episode_one_alert_then_one_cleared() -> None:
    sim = Sim()
    sim.unit(0, 0)
    for tick in range(1, 6):
        sim.unit(16 * tick, 10 * tick)
    assert event_kinds(sim) == ["alert"]
    for tick in range(6, 6 + CFG.quiet_ticks_to_clear):
        sim.unit(16 * tick, 50)
    assert event_kinds(sim) == ["alert", "cleared"]
    assert sim.state.units[OBSIDIAN].episode is None
    assert sim.state.units[OBSIDIAN].history == [(at(16 * 7), 50)]


def test_reremind_after_six_hours_only_with_proof() -> None:
    sim = Sim()
    sim.unit(0, 0)
    # A sustained loop: +10 per 16-minute tick, proven every tick.
    remind_ticks = []
    for tick in range(1, 31):
        outcome = sim.unit(16 * tick, 10 * tick)
        if "reremind" in kinds(outcome):
            remind_ticks.append(tick)
    assert event_kinds(sim).count("alert") == 1
    # Alert at tick 1 (minute 16); 6 h later is minute 376 → first tick ≥ is 24.
    assert remind_ticks == [24]
    remind = next(e for e in sim.all_events() if e.kind == "reremind")
    assert remind.proof.holds
    assert remind.episode_started_utc == at(16)
    assert sim.state.units[OBSIDIAN].episode.last_alert_utc == at(16 * 24)  # type: ignore[union-attr]


def test_no_reremind_when_rise_unproven() -> None:
    sim = Sim()
    sim.series([(0, 0), (16, 5)])  # Δ = 5 = bound for m = 2: alert
    assert event_kinds(sim) == ["alert"]
    # +1 per tick for 6 h 40 min: the unit keeps rising (no clear) but no pair
    # ever proves N restarts in one window, so no re-remind is due.
    for tick in range(2, 27):
        sim.unit(16 * tick, 5 + (tick - 1))
    assert event_kinds(sim) == ["alert"]
    assert sim.state.units[OBSIDIAN].episode is not None
    # A proven rise once ≥ 6 h have passed re-reminds immediately.
    outcome = sim.unit(16 * 27, 5 + 26 + 10)
    assert kinds(outcome) == ["reremind"]


def test_reremind_needs_fresh_evidence_not_the_original_burst() -> None:
    # WP02 review cycle 1 (MAJOR), INV-CL-4 ruling: (0,0),(16,39) alerts, then
    # +1 every 16 min. The minute-0 baseline still "proves" (minute 384:
    # Δ = 62, m = 26, bound = 53), but it predates the last page, so it must
    # never re-page — up to the 24 h retention limit.
    sim = Sim()
    sim.series([(0, 0), (16, 39)])
    assert event_kinds(sim) == ["alert"]
    last_tick = (16 + 24 * 60) // 16  # minute 1456: the baseline's 24 h limit
    count = 39
    for tick in range(2, last_tick + 1):
        count += 1
        outcome = sim.unit(16 * tick, count)
        assert outcome.events == [], tick
        episode = sim.state.units[OBSIDIAN].episode
        assert episode is not None
        assert episode.last_alert_utc == at(16), tick
    # Minute 384 really had a stale holding proof (the case the fix closes).
    stale, _ = prove([(at(0), 0)], 39 + 23, at(384), CFG)
    assert stale is not None and stale.m == 26 and stale.bound == 53
    # A fresh qualifying burst after the 6 h mark re-reminds, from fresh evidence.
    outcome = sim.unit(16 * (last_tick + 1), count + 10)
    assert kinds(outcome) == ["reremind"]
    proof = outcome.events[0].proof
    assert proof.holds
    assert proof.baseline_at >= at(16)
    assert proof.baseline_at == at(16 * last_tick)
    episode = sim.state.units[OBSIDIAN].episode
    assert episode is not None and episode.last_alert_utc == at(16 * (last_tick + 1))


def test_new_episode_after_clear_alerts_again() -> None:
    sim = Sim()
    sim.series([(0, 0), (16, 20), (32, 20), (48, 20)])
    assert event_kinds(sim) == ["alert", "cleared"]
    outcome = sim.unit(64, 40)
    assert kinds(outcome) == ["alert"]
    assert outcome.events[0].episode_started_utc == at(64)
    assert outcome.events[0].proof.baseline_at == at(48)


@pytest.mark.parametrize("window_seconds", [900, 3600])
def test_clear_does_not_replay_burst(window_seconds: int) -> None:
    sim = Sim(cfg(window_seconds=window_seconds))
    outcomes = sim.series([(0, 0), (5, 3), (6, 3), (7, 3), (8, 3)])
    assert [kinds(o) for o in outcomes] == [[], ["alert"], [], ["cleared"], []]
    assert all(o.unverified == [] for o in outcomes)
    assert sim.state.units[OBSIDIAN].history == [(at(8), 3)]


# --------------------------------------------------------------------------- #
# The proven-crossing rule (R-05).
# --------------------------------------------------------------------------- #
def test_dense_observations_prove_within_one_window() -> None:
    sim = Sim()
    outcomes = sim.series([(0, 0), (1, 1), (14, 3)])
    assert [kinds(o) for o in outcomes] == [[], [], ["alert"]]
    proof = outcomes[2].events[0].proof
    assert proof.m == 1
    assert proof.bound == 3
    assert proof.baseline_at == at(0)


def test_three_restarts_over_sixteen_minutes_is_unverified() -> None:
    # plan.md judgment call 1: accepted limit.
    sim = Sim()
    outcomes = sim.series([(0, 0), (16, 3)])
    assert outcomes[1].events == []
    assert len(outcomes[1].unverified) == 1
    rise = outcomes[1].unverified[0]
    assert rise.key == OBSIDIAN
    assert rise.proof.m == 2
    assert rise.proof.bound == 5
    assert rise.proof.delta == 3
    assert not rise.proof.holds


def test_three_restarts_in_spread_minutes_not_paged() -> None:
    # Codex round 2: restarts at minutes 0.1, 8 and 15.9 — no 15-minute window
    # holds 3 of them, and sampling at 0 and 16 must not page.
    restarts = [0.1, 8.0, 15.9]
    assert max(restarts) - min(restarts) > 15
    sim = Sim()
    sim.unit(0, 0)
    outcome = sim.unit(16, sum(1 for r in restarts if r <= 16))
    assert outcome.events == []
    assert [u.proof.delta for u in outcome.unverified] == [3]


def test_long_gap_requires_scaled_bound() -> None:
    slow = Sim()
    outcome = slow.series([(0, 0), (180, 3)])[1]
    assert outcome.events == []
    assert outcome.unverified[0].proof.m == 12
    assert outcome.unverified[0].proof.bound == 25

    fast = Sim()
    outcome = fast.series([(0, 0), (180, 25)])[1]
    assert kinds(outcome) == ["alert"]
    assert outcome.events[0].proof.m == 12
    assert outcome.events[0].proof.bound == 25


def test_late_tick_still_catches_real_loop() -> None:
    outcome = Sim().series([(0, 0), (17, 39)])[1]
    assert kinds(outcome) == ["alert"]
    assert outcome.events[0].proof.m == 2


def test_straddled_burst_limit_documented() -> None:
    # plan.md judgment call 2: 4 restarts split 2 + 2 across a tick boundary.
    outcomes = Sim().series([(0, 0), (15, 2), (30, 4)])
    assert all(o.events == [] for o in outcomes)


def test_boundary_exactly_one_window() -> None:
    exact = T0 + timedelta(seconds=900)
    past = T0 + timedelta(seconds=900, microseconds=1)
    holding, unverified = prove([(T0, 0)], 3, exact, CFG)
    assert holding is not None and unverified is None
    assert holding.m == 1 and holding.bound == 3
    holding, unverified = prove([(T0, 0)], 3, past, CFG)
    assert holding is None and unverified is not None
    assert unverified.m == 2 and unverified.bound == 5

    sim = Sim()
    sim.tick(T0, [obs(OBSIDIAN, 0)])
    assert kinds(sim.tick(exact, [obs(OBSIDIAN, 3)])) == ["alert"]
    sim = Sim()
    sim.tick(T0, [obs(OBSIDIAN, 0)])
    outcome = sim.tick(past, [obs(OBSIDIAN, 3)])
    assert outcome.events == [] and len(outcome.unverified) == 1


def test_prove_prefers_tightest_holding_interval() -> None:
    history = [(at(0), 0), (at(10), 5), (at(14), 6)]
    holding, unverified = prove(history, 9, at(15), CFG)
    assert unverified is None
    assert holding is not None
    # (14, 6): Δ = 3 over 1 min holds and is tighter than (10, 5) or (0, 0).
    assert holding.baseline_at == at(14)
    assert holding.delta == 3


def test_prove_reports_tightest_unverified_only_without_proof() -> None:
    history = [(at(0), 0), (at(20), 1)]
    holding, unverified = prove(history, 4, at(36), CFG)
    assert holding is None
    assert unverified is not None
    # (20, 1): Δ = 3 over 16 min (m = 2) is tighter than (0, 0) Δ = 4 over 36.
    assert unverified.baseline_at == at(20)


def test_every_page_is_a_proven_crossing_property() -> None:
    """Property (INV-CL-3, NFR-004): every alert/reremind is backed by ≥ N real
    restarts inside some window-length interval. 2000 seeded cases."""
    rng = random.Random(1133)
    pages = 0
    for _case in range(2000):
        threshold = rng.randint(2, 6)
        window = rng.choice([60, 900, 3600])
        window_us = window * 1_000_000
        config = cfg(
            threshold=threshold,
            window_seconds=window,
            quiet_ticks_to_clear=rng.randint(1, 3),
        )
        horizon_us = rng.choice([1, 4, 12]) * 3600 * 1_000_000
        restarts: list[int] = []
        for _burst in range(rng.randint(0, 5)):
            start = rng.randrange(horizon_us)
            spread = rng.choice([window_us // 10, window_us, 3 * window_us])
            restarts.extend(
                start + rng.randrange(max(1, spread))
                for _ in range(rng.randint(1, 3 * threshold))
            )
        restarts.sort()
        # Half the sample times are whole seconds, so exact window multiples
        # (the m boundary) occur; the rest have microsecond precision.
        whole_seconds = rng.random() < 0.5
        samples = sorted(
            {
                rng.randrange(horizon_us // 1_000_000) * 1_000_000
                if whole_seconds
                else rng.randrange(horizon_us)
                for _ in range(rng.randint(2, 25))
            }
        )
        sim = Sim(config)
        for sample in samples:
            count = bisect.bisect_right(restarts, sample)
            outcome = sim.tick(
                T0 + timedelta(microseconds=sample), [obs(OBSIDIAN, count)]
            )
            for event in outcome.events:
                if event.kind not in ("alert", "reremind"):
                    continue
                pages += 1
                proof = event.proof
                assert proof.holds
                lo = (proof.baseline_at - T0) // timedelta(microseconds=1)
                hi = (proof.observed_at - T0) // timedelta(microseconds=1)
                inside = [r for r in restarts if lo < r <= hi]
                assert len(inside) == proof.delta
                assert any(
                    inside[i + threshold - 1] - inside[i] <= window_us
                    for i in range(len(inside) - threshold + 1)
                ), (threshold, window, proof)
    assert pages > 200  # the property is not vacuous


# --------------------------------------------------------------------------- #
# US3: false-positive guards, resets, generations, first sight.
# --------------------------------------------------------------------------- #
def test_single_restart_no_alert() -> None:
    outcomes = Sim().series([(0, 0), (5, 1), (10, 1)])
    assert all(o.events == [] and o.unverified == [] for o in outcomes)


def test_threshold_restarts_alert() -> None:
    outcomes = Sim().series([(0, 0), (5, 1), (10, 3)])
    assert [kinds(o) for o in outcomes] == [[], [], ["alert"]]
    assert outcomes[2].events[0].proof.m == 1


def test_ignored_unit_never_alerts() -> None:
    noisy = "system:noisy.service"
    sim = Sim(cfg(ignore={noisy}))
    outcomes = sim.series([(0, 0), (16, 39), (32, 80)], key=noisy)
    assert all(o.events == [] and o.unverified == [] for o in outcomes)
    assert noisy not in sim.state.units
    assert outcomes[1].counts["ignored"] == 1
    assert outcomes[1].counts["watched"] == 0
    assert outcomes[1].scope_status["system"] == (
        "healthy",
        "0 watched, 1 ignored, 1 excluded, 5 ms",
    )


def test_not_ignored_control_alerts() -> None:
    noisy = "system:noisy.service"
    sim = Sim(cfg(ignore={"system:other.service"}))
    outcomes = sim.series([(0, 0), (16, 39)], key=noisy)
    assert kinds(outcomes[1]) == ["alert"]


def test_ignoring_a_stored_unit_drops_its_state() -> None:
    sim = Sim()
    sim.series([(0, 0), (16, 39)])
    assert sim.state.units[OBSIDIAN].episode is not None
    sim.config = cfg(ignore={OBSIDIAN})
    outcome = sim.unit(32, 80)
    assert outcome.events == []
    assert OBSIDIAN not in sim.state.units


def test_decrease_is_reset_no_alert() -> None:
    sim = Sim()
    outcomes = sim.series([(0, 10), (16, 2), (17, 4)])
    assert all(o.events == [] for o in outcomes)
    assert outcomes[1].counts["resets"] == 1
    assert sim.state.units[OBSIDIAN].history == [(at(16), 2), (at(17), 4)]


def test_container_id_change_is_reset_no_alert() -> None:
    key = "container:vikunja"
    sim = Sim()
    sim.unit(0, 0, key, generation="cid-old")
    outcome = sim.unit(16, 39, key, generation="cid-new")
    assert outcome.events == [] and outcome.unverified == []
    assert outcome.counts["resets"] == 1
    unit = sim.state.units[key]
    assert unit.generation == "cid-new"
    assert unit.history == [(at(16), 39)]


def test_boot_change_rebases_all_scopes_including_containers() -> None:
    keys = ["system:a.service", "user:b.service", "container:c"]
    sim = Sim()
    sim.tick(at(0), [obs(k, 1, boot=BOOT_A) for k in keys], boot=BOOT_A)
    outcome = sim.tick(at(16), [obs(k, 40, boot=BOOT_B) for k in keys], boot=BOOT_B)
    assert outcome.events == [] and outcome.unverified == []
    assert outcome.counts["rebased_on_boot"] == 3
    for key in keys:
        unit = sim.state.units[key]
        assert unit.boot_id == BOOT_B
        assert unit.history == [(at(16), 40)]
    assert sim.state.boot_id == BOOT_B


def test_first_seen_is_baseline() -> None:
    sim = Sim()
    outcome = sim.unit(0, 500)
    assert outcome.events == [] and outcome.unverified == []
    assert outcome.counts["first_seen"] == 1
    unit = sim.state.units[OBSIDIAN]
    assert unit.history == [(at(0), 500)]
    assert unit.episode is None
    assert unit.boot_id == BOOT_A


def test_reset_during_episode_counts_quiet() -> None:
    sim = Sim()
    sim.series([(0, 0), (16, 39)])
    outcome = sim.unit(32, 2)  # operator restart: decrease
    assert outcome.events == []
    episode = sim.state.units[OBSIDIAN].episode
    assert episode is not None and episode.quiet_ticks == 1
    outcome = sim.unit(48, 2)
    assert kinds(outcome) == ["cleared"]
    assert sim.state.units[OBSIDIAN].episode is None


def test_reset_in_episode_may_clear_but_never_alerts() -> None:
    key = "container:vikunja"
    sim = Sim(cfg(quiet_ticks_to_clear=1))
    sim.unit(0, 0, key, generation="cid-1")
    assert event_kinds(sim) == []
    sim.unit(16, 39, key, generation="cid-1")
    assert event_kinds(sim) == ["alert"]
    # Re-created container with a much higher count: a reset, counted quiet.
    outcome = sim.unit(32, 500, key, generation="cid-2")
    assert kinds(outcome) == ["cleared"]
    assert sim.state.units[key].history == [(at(32), 500)]
    # Even ≥ 6 h later a reset inside an episode never alerts or re-reminds.
    sim2 = Sim(cfg(quiet_ticks_to_clear=5))
    sim2.series([(0, 0), (16, 39)])
    for minute, count in [(400, 1), (416, 0)]:
        outcome = sim2.unit(minute, count)
        assert outcome.events == []


def test_boot_change_closes_episode_silently() -> None:
    sim = Sim()
    sim.series([(0, 0), (16, 39)])
    outcome = sim.unit(32, 60, boot=BOOT_B)
    assert outcome.events == []
    assert outcome.counts["rebased_on_boot"] == 1
    assert sim.state.units[OBSIDIAN].episode is None


def test_reboot_during_unreadable_scope_still_rebases() -> None:
    key = "container:vikunja"
    sim = Sim()
    sim.tick(at(0), [obs(key, 0)], boot=BOOT_A)
    outcome = sim.tick(at(16), [], boot=BOOT_B, incomplete=["container"])
    assert outcome.scope_status["container"][0] == "unknown"
    assert sim.state.units[key].boot_id == BOOT_A
    outcome = sim.tick(at(32), [obs(key, 39)], boot=BOOT_B)
    assert outcome.events == [] and outcome.unverified == []
    assert outcome.counts["rebased_on_boot"] == 1
    assert sim.state.units[key].history == [(at(32), 39)]
    assert sim.state.units[key].boot_id == BOOT_B


# --------------------------------------------------------------------------- #
# Scopes, removal, clock.
# --------------------------------------------------------------------------- #
def test_incomplete_scope_preserves_state_and_reports_unknown() -> None:
    key = "container:vikunja"
    sim = Sim()
    sim.series([(0, 0), (16, 39)], key=key)
    before = copy.deepcopy(sim.state.units[key])
    outcome = sim.tick(at(32), [], incomplete=["container"])
    assert outcome.events == []
    assert sim.state.units[key] == before
    assert outcome.scope_status["container"] == (
        "unknown",
        "could not check: container read failed",
    )
    assert outcome.scope_status["system"][0] == "healthy"

    outcome = sim.tick(at(48), [], missing=["container"])
    assert sim.state.units[key] == before
    assert outcome.scope_status["container"] == ("unknown", "could not check: not read")


def test_none_boot_id_carries_every_scope_forward() -> None:
    sim = Sim()
    sim.series([(0, 0), (16, 39)])
    before = copy.deepcopy(sim.state)
    outcome = sim.tick(at(32), [obs(OBSIDIAN, 99)], boot=None)
    assert outcome.events == []
    assert {s for s, (o, _) in outcome.scope_status.items() if o == "unknown"} == set(
        SCOPES
    )
    assert sim.state.units == before.units
    assert sim.state.boot_id == BOOT_A


def test_complete_scope_drops_removed_unit_silently() -> None:
    sim = Sim()
    sim.series([(0, 0), (16, 39)])
    assert sim.state.units[OBSIDIAN].episode is not None
    outcome = sim.tick(at(32), [obs("system:other.service", 0)])
    assert outcome.events == []
    assert OBSIDIAN not in sim.state.units
    assert "system:other.service" in sim.state.units


def test_clock_not_advanced_skips_unit() -> None:
    sim = Sim()
    sim.series([(0, 0), (16, 39)])
    before = copy.deepcopy(sim.state.units[OBSIDIAN])
    for minute in (16, 10):
        outcome = sim.unit(minute, 200)
        assert outcome.events == [] and outcome.unverified == []
        assert outcome.counts["clock_skipped"] == 1
        assert sim.state.units[OBSIDIAN] == before


@pytest.mark.parametrize("offset_minutes", [0, -6])
def test_clock_check_precedes_boot_generation_and_reset(offset_minutes: int) -> None:
    # WP02 review cycle 1 (MINOR), INV-CL-9: at an equal or backward timestamp,
    # a changed boot ID, a changed container generation and a decreased counter
    # all lose to the clock check.
    key = "container:vikunja"
    sim = Sim()
    sim.unit(0, 0, key, generation="cid-1")
    sim.unit(16, 39, key, generation="cid-1")
    assert event_kinds(sim) == ["alert"]
    before = copy.deepcopy(sim.state.units[key])
    outcome = sim.unit(16 + offset_minutes, 2, key, generation="cid-2", boot=BOOT_B)
    assert outcome.events == [] and outcome.unverified == []
    assert sim.state.units[key] == before
    assert outcome.counts == {
        "watched": 1,
        "ignored": 0,
        "first_seen": 0,
        "resets": 0,
        "in_episode": 1,
        "clock_skipped": 1,
        "rebased_on_boot": 0,
    }


def test_counts_and_scope_status_cover_every_scope() -> None:
    outcome = Sim().tick(at(0), [obs(OBSIDIAN, 0)])
    assert set(outcome.counts) == set(COUNT_KEYS)
    assert set(outcome.scope_status) == set(SCOPES)
    assert outcome.scope_status["system"] == (
        "healthy",
        "1 watched, 0 ignored, 1 excluded, 5 ms",
    )


# --------------------------------------------------------------------------- #
# History (R-07).
# --------------------------------------------------------------------------- #
def test_history_dominance_compaction() -> None:
    # Equal count replaces the newest entry; a higher count appends.
    assert _maintain_history([(at(0), 0)], at(1), at(1), 0, 900) == [(at(1), 0)]
    assert _maintain_history([(at(0), 0)], at(1), at(1), 2, 900) == [
        (at(0), 0),
        (at(1), 2),
    ]

    # Codex round 3: (0,0),(30,0),(60,2),(915,3) in seconds alerts at 915.
    sim = Sim()
    outcome = None
    for second, count in [(0, 0), (30, 0), (60, 2), (915, 3)]:
        outcome = sim.tick(T0 + timedelta(seconds=second), [obs(OBSIDIAN, count)])
    assert outcome is not None
    assert kinds(outcome) == ["alert"]
    assert outcome.events[0].proof.baseline_at == T0 + timedelta(seconds=30)
    assert outcome.events[0].proof.m == 1

    # Entries older than 24 h are pruned; the newest is always kept.
    now = at(0) + timedelta(hours=30)
    old = [(at(0), 0), (at(0) + timedelta(hours=7), 1), (now - timedelta(hours=1), 2)]
    assert _maintain_history(old, now, now, 3, 900) == [
        (at(0) + timedelta(hours=7), 1),
        (now - timedelta(hours=1), 2),
        (now, 3),
    ]
    assert _maintain_history([(now - timedelta(hours=48), 5)], now, now, 5, 900) == [
        (now, 5)
    ]

    # The 64-entry cap drops the oldest pre-window entries only.
    now = at(600)
    pre_window = [(at(i), i) for i in range(100)]  # minutes 0..99, all pre-window
    in_window = [(now - timedelta(seconds=300 - i), 100 + i) for i in range(100)]
    kept = _maintain_history(pre_window + in_window, now, now, 500, 900)
    assert kept[:HISTORY_MAX] == pre_window[-HISTORY_MAX:]
    assert kept[HISTORY_MAX:-1] == in_window
    assert kept[-1] == (now, 500)

    # Codex round 4: N = 100, observations (i, i) for i = 0..64 s, then
    # (65, 100). In-window entries are never pruned, so the m = 1 proof holds.
    sim = Sim(cfg(threshold=100))
    for second in range(65):
        outcome = sim.tick(T0 + timedelta(seconds=second), [obs(OBSIDIAN, second)])
        assert outcome.events == []
    assert len(sim.state.units[OBSIDIAN].history) == 65
    outcome = sim.tick(T0 + timedelta(seconds=65), [obs(OBSIDIAN, 100)])
    assert kinds(outcome) == ["alert"]
    assert outcome.events[0].proof.baseline_at == T0
    assert outcome.events[0].proof.m == 1


def test_history_stays_strictly_increasing() -> None:
    sim = Sim()
    sim.series([(0, 0), (1, 0), (2, 1), (3, 1), (4, 1), (5, 2)])
    history = sim.state.units[OBSIDIAN].history
    assert history == [(at(1), 0), (at(4), 1), (at(5), 2)]
    assert all(a[0] < b[0] and a[1] < b[1] for a, b in itertools.pairwise(history))


# --------------------------------------------------------------------------- #
# Emission plan and rendering (contract §1-§4, R-15).
# --------------------------------------------------------------------------- #
def _event(
    key: str,
    kind: str = "alert",
    delta: int = 39,
    observed: datetime | None = None,
) -> CrashLoopEvent:
    observed = observed or at(16)
    scope, name = key.split(":", 1)
    proof = Proof(
        baseline_at=at(0),
        baseline_count=0,
        current_count=delta,
        observed_at=observed,
        delta=delta,
        period_seconds=(observed - at(0)).total_seconds(),
        m=2,
        bound=5,
    )
    return CrashLoopEvent(
        kind=kind,
        key=key,
        scope=scope,
        name=name,
        state=RUNNING,
        episode_started_utc=at(16),
        proof=proof,
    )


def test_cap_folds_all_extra_events_into_one_bounded_aggregate() -> None:
    events = [
        _event(f"system:some-fairly-long-unit-name-{i:02d}.service") for i in range(50)
    ]
    emissions = plan_emissions(events, CFG)
    assert len(emissions) == 4
    assert [len(e.events) for e in emissions] == [1, 1, 1, 47]
    aggregate = emissions[3].alert
    assert aggregate.source == AGGREGATE_SOURCE
    assert aggregate.severity is Severity.ERROR
    assert aggregate.title == "47 more crash-loop events this tick"
    description = aggregate.description
    assert len(description) <= 900
    assert len(description) <= DESCRIPTION_MAX
    assert len(description) <= 1000
    listed = int(aggregate.details["units_listed"])
    remaining = 47 - listed
    assert remaining > 0
    assert description.endswith(
        f"... and {remaining} more - see canary ledger 2026-11-23"
    )
    assert aggregate.details == {
        "kind": "aggregate",
        "count": "47",
        "units_listed": str(listed),
    }
    assert listed + remaining == 47
    assert description.count("; ") == listed
    assert all(len(v) <= DETAIL_VALUE_MAX for v in aggregate.details.values())
    assert description.startswith(
        "system:some-fairly-long-unit-name-03.service alert +39/16 min active (running)"
    )


def test_aggregate_lists_everything_when_it_fits() -> None:
    events = [_event(f"system:u{i}.service", kind="cleared", delta=0) for i in range(2)]
    aggregate = render_aggregate(events)
    assert aggregate.severity is Severity.INFO
    assert "more - see canary ledger" not in aggregate.description
    assert aggregate.details["units_listed"] == "2"
    assert aggregate.description == (
        "system:u0.service cleared +0/16 min active (running); "
        "system:u1.service cleared +0/16 min active (running)"
    )
    assert render_aggregate(events, date(2026, 1, 2)).description == (
        aggregate.description
    )


def test_plan_emissions_orders_alert_reremind_cleared_then_key() -> None:
    events = [
        _event("system:z.service", "cleared", 0),
        _event("system:b.service", "reremind"),
        _event("system:y.service", "alert"),
        _event("system:a.service", "alert"),
    ]
    emissions = plan_emissions(events, cfg(max_alerts_per_tick=10))
    assert [(e.events[0].kind, e.events[0].key) for e in emissions] == [
        ("alert", "system:a.service"),
        ("alert", "system:y.service"),
        ("reremind", "system:b.service"),
        ("cleared", "system:z.service"),
    ]
    assert plan_emissions([], CFG) == []
    capped = plan_emissions(events, cfg(max_alerts_per_tick=3))
    assert len(capped) == 4
    assert capped[3].alert.severity is Severity.INFO  # only a cleared folded


def test_alert_text_and_details_match_contract() -> None:
    sim = Sim()
    outcome = sim.series([(0, 0), (16, 39)])[1]
    alert = render_alert(outcome.events[0], CFG)
    assert isinstance(alert, Alert)
    assert alert.source == "felix-canary:crash-loop:system:obsidian-sync.service"
    assert alert.severity is Severity.ERROR
    assert alert.action is None
    assert alert.timestamp == at(16)
    assert alert.title == "obsidian-sync.service crash-looping: 39 restarts in 16 min"
    assert alert.description == (
        "system unit obsidian-sync.service restarted 39 times between "
        "2026-11-23T12:00:00+00:00 and 2026-11-23T12:16:00+00:00 "
        "(restart count 0 -> 39), which proves at least 3 restarts within 15 min. "
        "Current state: active (running)."
    )
    assert alert.details == {
        "component_id": "crash-loop:system:obsidian-sync.service",
        "kind": "alert",
        "scope": "system",
        "unit": "obsidian-sync.service",
        "delta": "39",
        "period_seconds": "960",
        "baseline_count": "0",
        "current_count": "39",
        "m": "2",
        "bound": "5",
        "state": "active (running)",
        "episode_started_utc": "2026-11-23T12:16:00+00:00",
    }
    assert all(isinstance(v, str) for v in alert.details.values())

    remind = render_alert(_event(OBSIDIAN, "reremind"), CFG)
    assert remind.severity is Severity.ERROR
    assert remind.title.startswith("still obsidian-sync.service crash-looping: ")
    assert "2026-11-23T12:16:00+00:00" in remind.description
    assert remind.details["kind"] == "reremind"

    # The cleared entry from a real episode.
    for minute in (32, 48):
        cleared_outcome = sim.unit(minute, 39)
    cleared_event = cleared_outcome.events[0]
    assert cleared_event.kind == "cleared"
    cleared = render_alert(cleared_event, CFG)
    assert cleared.severity is Severity.INFO
    assert cleared.title == "obsidian-sync.service crash loop cleared"
    assert cleared.description == (
        "system unit obsidian-sync.service has not restarted for 2 consecutive "
        "canary ticks; the episode that began 2026-11-23T12:16:00+00:00 has ended. "
        "Current state: active (running)."
    )
    assert cleared.details["kind"] == "cleared"
    assert cleared.details["delta"] == "0"
    assert all(isinstance(v, str) for v in cleared.details.values())


def test_period_renders_whole_minutes_rounded_up() -> None:
    assert crash_loop._period(1) == "1 min"
    assert crash_loop._period(60) == "1 min"
    assert crash_loop._period(61) == "2 min"
    assert crash_loop._period(960) == "16 min"
    assert crash_loop._period(0) == "1 min"


# --------------------------------------------------------------------------- #
# Purity.
# --------------------------------------------------------------------------- #
def test_evaluate_tick_does_not_mutate_prior_state() -> None:
    config = cfg(ignore={"system:ignored.service"}, quiet_ticks_to_clear=2)
    prior = CrashLoopState(
        updated_at_utc=at(0),
        boot_id=BOOT_A,
        units={
            OBSIDIAN: UnitState(
                generation=BOOT_A,
                boot_id=BOOT_A,
                history=[(at(0), 0), (at(10), 5)],
                episode=Episode(
                    started_utc=at(10),
                    last_alert_utc=at(10) - timedelta(hours=7),
                    quiet_ticks=1,
                    peak_delta=5,
                ),
            ),
            "system:quiet.service": UnitState(
                generation=BOOT_A,
                boot_id=BOOT_A,
                history=[(at(0), 0)],
                episode=None,
            ),
            "system:ignored.service": UnitState(
                generation=BOOT_A, boot_id=BOOT_A, history=[(at(0), 1)], episode=None
            ),
            "system:gone.service": UnitState(
                generation=BOOT_A, boot_id=BOOT_A, history=[(at(0), 1)], episode=None
            ),
            "container:vikunja": UnitState(
                generation="cid-1",
                boot_id=BOOT_A,
                history=[(at(0), 3)],
                episode=Episode(
                    started_utc=at(0), last_alert_utc=at(0), quiet_ticks=0, peak_delta=3
                ),
            ),
            "user:x.service": UnitState(
                generation=BOOT_A, boot_id=BOOT_A, history=[(at(0), 9)], episode=None
            ),
        },
    )
    snapshot = copy.deepcopy(prior)
    scenarios = [
        [obs(OBSIDIAN, 30), obs("system:quiet.service", 40)],  # reremind + alert
        [obs(OBSIDIAN, 5), obs("system:ignored.service", 9)],  # cleared
        [obs(OBSIDIAN, 1), obs("container:vikunja", 1)],  # resets
    ]
    for observations in scenarios:
        outcome = evaluate_tick(
            readings(observations, incomplete=["user"]), prior, config, at(16), BOOT_A
        )
        assert prior == snapshot
        assert outcome.new_state is not prior
        for key, unit in outcome.new_state.units.items():
            if key in prior.units:
                assert unit is not prior.units[key]
                assert unit.history is not prior.units[key].history
    # The scenarios really exercised the state machine.
    first = evaluate_tick(
        readings(scenarios[0], incomplete=["user"]), prior, config, at(16), BOOT_A
    )
    assert sorted(kinds(first)) == ["alert", "reremind"]
    second = evaluate_tick(
        readings(scenarios[1], incomplete=["user"]), prior, config, at(16), BOOT_A
    )
    assert kinds(second) == ["cleared"]
    # And the same inputs give the same outputs (determinism).
    again = evaluate_tick(
        readings(scenarios[0], incomplete=["user"]), prior, config, at(16), BOOT_A
    )
    assert again == first


# --------------------------------------------------------------------------- #
# The read bracket (NFR-004, post-merge review).
# --------------------------------------------------------------------------- #
def test_observation_is_stored_at_observed_from_and_proved_to_now() -> None:
    first = evaluate_tick(
        readings([obs(OBSIDIAN, 0)]),
        CrashLoopState.empty(),
        CFG,
        at(0.5),
        BOOT_A,
        observed_from=at(0),
    )
    assert first.new_state.units[OBSIDIAN].history == [(at(0), 0)]

    second = evaluate_tick(
        readings([obs(OBSIDIAN, 39)]),
        first.new_state,
        CFG,
        at(16),
        BOOT_A,
        observed_from=at(15.5),
    )
    assert kinds(second) == ["alert"]
    proof = second.events[0].proof
    assert proof.baseline_at == at(0)  # the stored (earliest) time
    assert proof.observed_at == at(16)  # the latest possible sampling instant
    assert proof.period_seconds == 960.0
    assert second.new_state.units[OBSIDIAN].history == [(at(0), 0), (at(15.5), 39)]
    episode = second.new_state.units[OBSIDIAN].episode
    assert episode is not None
    assert episode.started_utc == at(16)
    assert episode.last_alert_utc == at(16)


def test_observed_from_defaults_to_now() -> None:
    outcome = evaluate_tick(
        readings([obs(OBSIDIAN, 0)]), CrashLoopState.empty(), CFG, at(1), BOOT_A
    )
    assert outcome.new_state.units[OBSIDIAN].history == [(at(1), 0)]


def test_observed_from_at_previous_entry_is_clock_skipped() -> None:
    first = evaluate_tick(
        readings([obs(OBSIDIAN, 0)]), CrashLoopState.empty(), CFG, at(0), BOOT_A
    )
    second = evaluate_tick(
        readings([obs(OBSIDIAN, 2)]),
        first.new_state,
        CFG,
        at(1),
        BOOT_A,
        observed_from=at(0),
    )
    assert second.counts["clock_skipped"] == 1
    assert second.events == [] and second.unverified == []
    assert second.new_state.units[OBSIDIAN] == first.new_state.units[OBSIDIAN]


def test_clock_rollback_never_clamps_a_lower_bound_forward() -> None:
    """Round-2 review: (observed_from, now, count) = (0,1,0), (-1,1,0), (1800.000001,1800.000001,5).

    A clamp of the second tick's stored time to ``last_at + 1 µs`` would put a
    "lower bound" after the real sample and page with period 1800, m 2,
    bound 5. The second tick must be skipped instead, so the third proves
    against the first tick's baseline at 0 s only.
    """

    def sec(seconds: float) -> datetime:
        return T0 + timedelta(seconds=seconds)

    sim_state = CrashLoopState.empty()
    outcomes = []
    for frm, now, count in [(0, 1, 0), (-1, 1, 0), (1800.000001, 1800.000001, 5)]:
        outcome = evaluate_tick(
            readings([obs(OBSIDIAN, count)]),
            sim_state,
            CFG,
            sec(now),
            BOOT_A,
            observed_from=sec(frm),
        )
        outcomes.append(outcome)
        sim_state = outcome.new_state
    assert outcomes[1].counts["clock_skipped"] == 1
    assert kinds(outcomes[2]) == []
    assert sim_state.units[OBSIDIAN].history[0] == (sec(0), 0)
    rise = outcomes[2].unverified[0].proof
    assert rise.baseline_at == sec(0)
    assert rise.m == 3 and rise.bound == 7 and rise.delta == 5


def test_now_at_previous_entry_is_still_clock_skipped() -> None:
    first = evaluate_tick(
        readings([obs(OBSIDIAN, 0)]), CrashLoopState.empty(), CFG, at(5), BOOT_A
    )
    second = evaluate_tick(
        readings([obs(OBSIDIAN, 9)]),
        first.new_state,
        CFG,
        at(5),
        BOOT_A,
        observed_from=at(4),
    )
    assert second.counts["clock_skipped"] == 1
    assert second.new_state.units[OBSIDIAN] == first.new_state.units[OBSIDIAN]


def test_observed_from_after_now_rejected() -> None:
    with pytest.raises(ValueError, match="observed_from"):
        evaluate_tick(
            [], CrashLoopState.empty(), CFG, at(0), BOOT_A, observed_from=at(1)
        )


def test_naive_observed_from_rejected() -> None:
    with pytest.raises(ValueError, match="observed_from"):
        evaluate_tick(
            [],
            CrashLoopState.empty(),
            CFG,
            at(0),
            BOOT_A,
            observed_from=datetime(2026, 1, 1),
        )


def test_module_is_pure() -> None:
    source = crash_loop.__file__
    assert source is not None
    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    for forbidden in ("open(", "subprocess", "datetime.now", "time.", "import random"):
        assert forbidden not in text, forbidden


def test_naive_now_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_tick([], CrashLoopState.empty(), CFG, datetime(2026, 1, 1), BOOT_A)
