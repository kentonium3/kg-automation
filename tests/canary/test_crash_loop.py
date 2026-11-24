"""Tests for the pure crash-loop decision core (mission #1133, WP02 T010).

Kent's 2026-11-24 ruling (research R-16): count ticks, not time. A unit pages
when its counter rose by ``threshold`` (3) since the previous complete tick, or
rose by at least 1 on ``consecutive_rise_ticks`` (2) consecutive ticks.

``now`` is injected everywhere; nothing here reads the clock. Ticks are
written as counts, one per canary tick, 15 minutes apart from ``T0`` unless a
test is about the clock, where it proves the clock does not matter.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from scripts.canary import crash_loop
from scripts.canary.crash_loop import (
    AGGREGATE_SOURCE,
    COUNT_KEYS,
    TickOutcome,
    evaluate_tick,
    plan_emissions,
    render_aggregate,
    render_alert,
    triggers,
)
from scripts.canary.crash_loop_model import (
    SCOPES,
    CrashLoopConfig,
    CrashLoopEvent,
    RestartObservation,
    ScopeReading,
    TickInterval,
)
from scripts.canary.crash_loop_state import (
    CrashLoopState,
    Episode,
    UnitState,
    load_state,
    save_state,
)
from scripts.common.alert_bus.model import Alert, Severity
from scripts.common.alert_bus.render import DESCRIPTION_MAX, DETAIL_VALUE_MAX

T0 = datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC)
TICK = timedelta(minutes=15)
BOOT_A = "boot-aaaa"
BOOT_B = "boot-bbbb"
OBSIDIAN = "system:obsidian-sync.service"
RUNNING = "active (running)"


def cfg(
    *,
    threshold: int = 3,
    consecutive_rise_ticks: int = 2,
    quiet_ticks_to_clear: int = 2,
    reremind_ticks: int = 24,
    max_alerts_per_tick: int = 3,
    ignore: Iterable[str] = (),
) -> CrashLoopConfig:
    ignored = frozenset(ignore)
    return CrashLoopConfig(
        threshold=threshold,
        consecutive_rise_ticks=consecutive_rise_ticks,
        quiet_ticks_to_clear=quiet_ticks_to_clear,
        reremind_ticks=reremind_ticks,
        max_alerts_per_tick=max_alerts_per_tick,
        read_budget_seconds=6,
        ignore=ignored,
        ignore_reasons=MappingProxyType(dict.fromkeys(ignored, "test")),
    )


CFG = cfg()


def at(tick: float) -> datetime:
    """The wall-clock stamp of canary tick *tick* on the normal cadence."""
    return T0 + tick * TICK


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
    """Runs successive ticks, threading the state through.

    Each call to :meth:`unit` or :meth:`tick` without an explicit ``now`` is the
    next canary tick on the normal 15-minute cadence.
    """

    def __init__(self, config: CrashLoopConfig = CFG) -> None:
        self.config = config
        self.state = CrashLoopState.empty()
        self.outcomes: list[TickOutcome] = []

    def tick(
        self,
        observations: Iterable[RestartObservation],
        *,
        now: datetime | None = None,
        boot: str | None = BOOT_A,
        incomplete: Iterable[str] = (),
        missing: Iterable[str] = (),
    ) -> TickOutcome:
        outcome = evaluate_tick(
            readings(observations, incomplete=incomplete, missing=missing),
            self.state,
            self.config,
            now if now is not None else at(len(self.outcomes)),
            boot,
        )
        self.state = outcome.new_state
        self.outcomes.append(outcome)
        return outcome

    def unit(
        self,
        count: int,
        key: str = OBSIDIAN,
        *,
        generation: str | None = None,
        boot: str = BOOT_A,
        now: datetime | None = None,
    ) -> TickOutcome:
        return self.tick(
            [obs(key, count, generation=generation, boot=boot)], boot=boot, now=now
        )

    def series(self, counts: Sequence[int], key: str = OBSIDIAN) -> list[TickOutcome]:
        return [self.unit(count, key) for count in counts]

    def all_events(self) -> list[CrashLoopEvent]:
        return [event for outcome in self.outcomes for event in outcome.events]


def kinds(outcome: TickOutcome) -> list[str]:
    return [event.kind for event in outcome.events]


def event_kinds(sim: Sim) -> list[str]:
    return [event.kind for event in sim.all_events()]


def per_tick(outcomes: Sequence[TickOutcome]) -> list[list[str]]:
    return [kinds(outcome) for outcome in outcomes]


# --------------------------------------------------------------------------- #
# The rule itself.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("delta", "prior_rises", "fires"),
    [
        (3, (), True),  # Δ ≥ threshold
        (39, (), True),
        (2, (), False),  # below threshold, no previous rise
        (1, (), False),
        (1, (1,), True),  # rose on this tick and the previous one
        (2, (2,), True),
        (0, (5,), False),  # quiet tick
        (-4, (5,), False),
    ],
)
def test_triggers_is_kents_rule(
    delta: int, prior_rises: tuple[int, ...], fires: bool
) -> None:
    assert triggers(delta, prior_rises, CFG) is fires


def test_triggers_general_n() -> None:
    three = cfg(consecutive_rise_ticks=3)
    assert triggers(1, (1,), three) is False
    assert triggers(1, (1, 1), three) is True
    assert triggers(3, (), three) is True


# --------------------------------------------------------------------------- #
# US1 / SC-001: the incident, user units, containers, between-tick loops.
# --------------------------------------------------------------------------- #
def test_sc001_incident_replay_0_to_39_gives_exactly_one_alert() -> None:
    sim = Sim()
    first, second = sim.series([0, 39])
    assert first.events == []
    assert first.counts["first_seen"] == 1
    assert kinds(second) == ["alert"]
    event = second.events[0]
    assert event.key == OBSIDIAN
    assert event.state == RUNNING
    assert event.interval == TickInterval(
        previous_count=0,
        current_count=39,
        delta=39,
        rose_last_tick=False,
        previous_seen_at=at(0),
        observed_at=at(1),
        rises=(39,),
    )
    assert event.episode_started_utc == at(1)
    episode = sim.state.units[OBSIDIAN].episode
    assert episode is not None
    assert (episode.ticks_since_alert, episode.quiet_ticks, episode.peak_delta) == (
        0,
        0,
        39,
    )
    # Still looping on the next tick: no second alert (one per episode).
    assert sim.unit(60).events == []
    assert event_kinds(sim) == ["alert"]


def test_user_unit_and_container_alert() -> None:
    user_key = "user:openclaw-gateway.service"
    container_key = "container:vikunja"
    sim = Sim()
    sim.tick([obs(user_key, 0), obs(container_key, 2)])
    outcome = sim.tick([obs(user_key, 20), obs(container_key, 30)])
    assert sorted((e.key, e.kind) for e in outcome.events) == [
        (container_key, "alert"),
        (user_key, "alert"),
    ]
    by_key = {e.key: e for e in outcome.events}
    assert by_key[container_key].interval.delta == 28
    assert by_key[container_key].scope == "container"
    assert by_key[user_key].scope == "user"
    alert = render_alert(by_key[container_key], CFG)
    assert alert.source == "felix-canary:crash-loop:container:vikunja"
    assert alert.details["component_id"] == "crash-loop:container:vikunja"


def test_between_tick_loop_caught() -> None:
    # The loop started and ended between ticks; the unit is running again, but
    # the persistent counter kept every restart (FR-005).
    sim = Sim()
    sim.unit(4)
    outcome = sim.tick([obs(OBSIDIAN, 12, state=RUNNING)])
    assert kinds(outcome) == ["alert"]
    assert outcome.events[0].interval.delta == 8


# --------------------------------------------------------------------------- #
# Sensitivity: the expected outcomes Kent named (replaces the pigeonhole and
# "unverified rise" tests: there is no unverified outcome any more).
# --------------------------------------------------------------------------- #
def test_steady_two_per_tick_pages_on_its_second_tick() -> None:
    outcomes = Sim().series([0, 2, 4, 6])
    assert per_tick(outcomes) == [[], [], ["alert"], []]
    interval = outcomes[2].events[0].interval
    assert (interval.delta, interval.rose_last_tick, interval.rises) == (
        2,
        True,
        (2, 2),
    )


def test_steady_one_per_tick_pages_on_its_second_rising_tick() -> None:
    outcomes = Sim().series([0, 1, 2, 3])
    assert per_tick(outcomes) == [[], [], ["alert"], []]
    assert outcomes[2].events[0].interval.rises == (1, 1)


def test_single_restart_never_pages() -> None:
    outcomes = Sim().series([0, 1, 1, 1, 1, 1])
    assert all(o.events == [] for o in outcomes)


def test_single_restart_paired_control_rise_then_rise_pages() -> None:
    outcomes = Sim().series([0, 1, 2])
    assert per_tick(outcomes) == [[], [], ["alert"]]


def test_rise_of_two_then_quiet_never_pages() -> None:
    outcomes = Sim().series([0, 2, 2, 2, 2])
    assert all(o.events == [] for o in outcomes)


def test_rise_of_three_pages() -> None:
    outcomes = Sim().series([0, 3])
    assert per_tick(outcomes) == [[], ["alert"]]
    assert outcomes[1].events[0].interval.rose_last_tick is False


def test_non_consecutive_rises_never_page() -> None:
    # +1, quiet, +1, quiet, ...: every rise follows a quiet tick.
    outcomes = Sim().series([0, 1, 1, 2, 2, 3, 3, 4])
    assert all(o.events == [] for o in outcomes)


def test_long_canary_outage_counts_as_one_interval() -> None:
    # R-16: a tick is any complete read, so hours without one are one interval;
    # a rise of 3 across it pages (the conservative direction).
    sim = Sim()
    sim.unit(0, now=T0)
    assert kinds(sim.unit(3, now=T0 + timedelta(hours=5))) == ["alert"]


def test_consecutive_rise_ticks_three_needs_three_rising_ticks() -> None:
    sim = Sim(cfg(consecutive_rise_ticks=3))
    outcomes = sim.series([0, 1, 2, 3])
    assert per_tick(outcomes) == [[], [], [], ["alert"]]
    assert outcomes[3].events[0].interval.rises == (1, 1, 1)
    # The stored run is capped at N - 1 prior rises.
    assert sim.state.units[OBSIDIAN].recent_rises == (1, 1)


def test_stored_rise_run_is_capped() -> None:
    sim = Sim()
    sim.series([0, 1, 2, 3, 4, 5])
    assert sim.state.units[OBSIDIAN].recent_rises == (1,)
    assert sim.state.units[OBSIDIAN].rose_last_tick is True
    sim.unit(5)
    assert sim.state.units[OBSIDIAN].recent_rises == ()
    assert sim.state.units[OBSIDIAN].rose_last_tick is False


# --------------------------------------------------------------------------- #
# US2: the episode lifecycle.
# --------------------------------------------------------------------------- #
def test_episode_one_alert_then_k_quiet_ticks_then_exactly_one_cleared() -> None:
    sim = Sim()
    sim.series([0, 10, 20, 30, 40, 50])
    assert event_kinds(sim) == ["alert"]
    first_quiet = sim.unit(50)
    assert first_quiet.events == []
    assert sim.state.units[OBSIDIAN].episode is not None
    second_quiet = sim.unit(50)
    assert kinds(second_quiet) == ["cleared"]
    assert sim.state.units[OBSIDIAN].episode is None
    # Further quiet ticks say nothing more.
    sim.series([50, 50, 50])
    assert event_kinds(sim) == ["alert", "cleared"]


def test_a_rise_inside_the_episode_resets_the_quiet_count() -> None:
    sim = Sim()
    sim.series([0, 39, 39, 40, 40])
    assert event_kinds(sim) == ["alert"]
    assert sim.state.units[OBSIDIAN].episode is not None
    assert kinds(sim.unit(40)) == ["cleared"]


def test_fresh_episode_after_clear_needs_fresh_rises() -> None:
    sim = Sim()
    sim.series([0, 20, 20, 20])
    assert event_kinds(sim) == ["alert", "cleared"]
    assert sim.state.units[OBSIDIAN].rose_last_tick is False
    assert sim.unit(21).events == []  # one rise is not enough
    outcome = sim.unit(22)  # the second consecutive rise is
    assert kinds(outcome) == ["alert"]
    assert outcome.events[0].episode_started_utc == at(5)
    assert outcome.events[0].interval.previous_count == 21


def test_fresh_episode_after_clear_on_a_threshold_rise() -> None:
    sim = Sim()
    sim.series([0, 20, 20, 20])
    assert kinds(sim.unit(23)) == ["alert"]


def test_clear_then_unchanged_count_gives_no_event() -> None:
    # The CX-2 replay case, per tick: clearing must not replay the old burst.
    outcomes = Sim().series([0, 3, 3, 3, 3, 3])
    assert per_tick(outcomes) == [[], ["alert"], [], ["cleared"], [], []]


# --------------------------------------------------------------------------- #
# Re-remind (FR-007): 24 ticks, fresh evidence (WP02 ruling, R-16).
# --------------------------------------------------------------------------- #
def test_reremind_after_24_ticks_while_the_trigger_holds() -> None:
    sim = Sim()
    sim.unit(0)
    remind_ticks = []
    for tick in range(1, 60):
        outcome = sim.unit(10 * tick)  # +10 per tick: the trigger holds every tick
        if "reremind" in kinds(outcome):
            remind_ticks.append(tick)
    assert event_kinds(sim).count("alert") == 1
    # Alert at tick 1; re-reminds 24 and 48 ticks after it.
    assert remind_ticks == [25, 49]
    remind = next(e for e in sim.all_events() if e.kind == "reremind")
    assert remind.episode_started_utc == at(1)
    episode = sim.state.units[OBSIDIAN].episode
    assert episode is not None
    assert episode.last_alert_utc == at(49)
    assert episode.ticks_since_alert == 59 - 49


def test_no_reremind_unless_the_trigger_holds_on_fresh_ticks() -> None:
    sim = Sim()
    sim.series([0, 39])
    assert event_kinds(sim) == ["alert"]
    # +1, quiet, +1, quiet, ... keeps the episode open (never 2 quiet ticks in
    # a row) but never meets the rule (every rise follows a quiet tick).
    count = 39
    for tick in range(2, 40):
        if tick % 2 == 0:
            count += 1
        assert sim.unit(count).events == [], tick
    episode = sim.state.units[OBSIDIAN].episode
    assert episode is not None and episode.ticks_since_alert >= 24
    # A fresh qualifying rise past the 24-tick mark re-reminds at once.
    outcome = sim.unit(count + 3)
    assert kinds(outcome) == ["reremind"]
    assert outcome.events[0].interval.delta == 3


def test_slow_one_per_tick_inside_episode_rereminds_after_24_ticks() -> None:
    # 0 -> 39 pages, then +1 per tick. Every +1 tick follows another +1 tick,
    # so Kent's rule ("risen on 2 consecutive ticks") holds afresh on each of
    # them. The episode therefore stays open and re-reminds 24 ticks after the
    # alert. This follows Kent's rule as written; it is not the old proof
    # model's behaviour, which suppressed this case.
    sim = Sim()
    sim.series([0, 39])
    remind_ticks = []
    for tick in range(2, 30):
        outcome = sim.unit(39 + tick - 1)
        if "reremind" in kinds(outcome):
            remind_ticks.append(tick)
    assert remind_ticks == [25]
    assert event_kinds(sim) == ["alert", "reremind"]
    remind = next(e for e in sim.all_events() if e.kind == "reremind")
    assert (remind.interval.delta, remind.interval.rises) == (1, (1, 1))


def test_reremind_ticks_is_configurable() -> None:
    sim = Sim(cfg(reremind_ticks=3))
    outcomes = sim.series([0, 10, 20, 30, 40, 50, 60, 70])
    assert per_tick(outcomes) == [
        [],
        ["alert"],
        [],
        [],
        ["reremind"],
        [],
        [],
        ["reremind"],
    ]


# --------------------------------------------------------------------------- #
# US3: resets, generations, first sight, ignore.
# --------------------------------------------------------------------------- #
def test_first_seen_is_baseline() -> None:
    sim = Sim()
    outcome = sim.unit(500)
    assert outcome.events == []
    assert outcome.counts["first_seen"] == 1
    unit = sim.state.units[OBSIDIAN]
    assert (unit.last_count, unit.recent_rises, unit.episode) == (500, (), None)
    assert unit.boot_id == BOOT_A
    assert unit.last_seen_at == at(0)


def test_decrease_is_reset_no_alert() -> None:
    sim = Sim()
    outcomes = sim.series([10, 11, 2, 4])
    # Without the reset the 11 -> 2 -> 4 run would be a rise after a rise.
    assert all(o.events == [] for o in outcomes)
    assert outcomes[2].counts["resets"] == 1
    unit = sim.state.units[OBSIDIAN]
    assert (unit.last_count, unit.recent_rises) == (4, (2,))


def test_decrease_breaks_the_rise_run() -> None:
    sim = Sim()
    sim.series([0, 1])
    assert sim.state.units[OBSIDIAN].rose_last_tick is True
    sim.unit(0)  # operator restart
    assert sim.state.units[OBSIDIAN].rose_last_tick is False
    assert sim.unit(1).events == []


def test_container_id_change_is_reset_no_alert() -> None:
    key = "container:vikunja"
    sim = Sim()
    sim.unit(0, key, generation="cid-old")
    outcome = sim.unit(39, key, generation="cid-new")
    assert outcome.events == []
    assert outcome.counts["resets"] == 1
    unit = sim.state.units[key]
    assert unit.generation == "cid-new"
    assert (unit.last_count, unit.recent_rises) == (39, ())


def test_boot_change_rebases_all_scopes_including_containers() -> None:
    keys = ["system:a.service", "user:b.service", "container:c"]
    sim = Sim()
    sim.tick([obs(k, 1, boot=BOOT_A) for k in keys], boot=BOOT_A)
    outcome = sim.tick([obs(k, 40, boot=BOOT_B) for k in keys], boot=BOOT_B)
    assert outcome.events == []
    assert outcome.counts["rebased_on_boot"] == 3
    for key in keys:
        unit = sim.state.units[key]
        assert unit.boot_id == BOOT_B
        assert (unit.last_count, unit.recent_rises) == (40, ())
    assert sim.state.boot_id == BOOT_B


def test_reset_during_episode_counts_quiet() -> None:
    sim = Sim()
    sim.series([0, 39])
    outcome = sim.unit(2)  # operator restart: decrease
    assert outcome.events == []
    episode = sim.state.units[OBSIDIAN].episode
    assert episode is not None and episode.quiet_ticks == 1
    assert episode.ticks_since_alert == 1
    outcome = sim.unit(2)
    assert kinds(outcome) == ["cleared"]
    assert sim.state.units[OBSIDIAN].episode is None
    assert outcome.events[0].interval.delta == 0


def test_reset_in_episode_may_clear_but_never_alerts() -> None:
    key = "container:vikunja"
    sim = Sim(cfg(quiet_ticks_to_clear=1))
    sim.unit(0, key, generation="cid-1")
    sim.unit(39, key, generation="cid-1")
    assert event_kinds(sim) == ["alert"]
    # Re-created container with a much higher count: a reset, counted quiet.
    outcome = sim.unit(500, key, generation="cid-2")
    assert kinds(outcome) == ["cleared"]
    assert outcome.events[0].interval.delta == 461
    unit = sim.state.units[key]
    assert (unit.last_count, unit.recent_rises, unit.episode) == (500, (), None)
    # Even past the re-remind mark, a reset inside an episode never pages.
    sim2 = Sim(cfg(quiet_ticks_to_clear=5, reremind_ticks=1))
    sim2.series([0, 39])
    for count in (1, 0):
        assert sim2.unit(count).events == []


def test_boot_change_closes_episode_silently() -> None:
    sim = Sim()
    sim.series([0, 39])
    outcome = sim.unit(60, boot=BOOT_B)
    assert outcome.events == []
    assert outcome.counts["rebased_on_boot"] == 1
    assert sim.state.units[OBSIDIAN].episode is None


def test_reboot_during_unreadable_scope_still_rebases() -> None:
    key = "container:vikunja"
    sim = Sim()
    sim.tick([obs(key, 0)], boot=BOOT_A)
    outcome = sim.tick([], boot=BOOT_B, incomplete=["container"])
    assert outcome.scope_status["container"][0] == "unknown"
    assert sim.state.units[key].boot_id == BOOT_A
    outcome = sim.tick([obs(key, 39)], boot=BOOT_B)
    assert outcome.events == []
    assert outcome.counts["rebased_on_boot"] == 1
    unit = sim.state.units[key]
    assert (unit.last_count, unit.boot_id) == (39, BOOT_B)


def test_ignored_unit_never_alerts() -> None:
    noisy = "system:noisy.service"
    sim = Sim(cfg(ignore={noisy}))
    outcomes = sim.series([0, 39, 80], key=noisy)
    assert all(o.events == [] for o in outcomes)
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
    outcomes = sim.series([0, 39], key=noisy)
    assert kinds(outcomes[1]) == ["alert"]


def test_ignoring_a_stored_unit_drops_its_state() -> None:
    sim = Sim()
    sim.series([0, 39])
    assert sim.state.units[OBSIDIAN].episode is not None
    sim.config = cfg(ignore={OBSIDIAN})
    outcome = sim.unit(80)
    assert outcome.events == []
    assert OBSIDIAN not in sim.state.units


# --------------------------------------------------------------------------- #
# Scopes and removal.
# --------------------------------------------------------------------------- #
def test_incomplete_scope_preserves_state_and_reports_unknown() -> None:
    key = "container:vikunja"
    sim = Sim()
    sim.series([0, 39], key=key)
    before = copy.deepcopy(sim.state.units[key])
    outcome = sim.tick([], incomplete=["container"])
    assert outcome.events == []
    assert sim.state.units[key] == before
    assert outcome.scope_status["container"] == (
        "unknown",
        "could not check: container read failed",
    )
    assert outcome.scope_status["system"][0] == "healthy"

    outcome = sim.tick([], missing=["container"])
    assert sim.state.units[key] == before
    assert outcome.scope_status["container"] == ("unknown", "could not check: not read")


def test_incomplete_tick_is_not_a_tick_for_the_rule() -> None:
    # A rise, an unreadable tick, then a rise: still two consecutive complete
    # ticks with a rise, so it pages; the unread tick changed nothing.
    key = "container:vikunja"
    sim = Sim()
    sim.series([0, 1], key=key)
    sim.tick([], incomplete=["container"])
    assert kinds(sim.unit(2, key)) == ["alert"]


def test_none_boot_id_carries_every_scope_forward() -> None:
    sim = Sim()
    sim.series([0, 39])
    before = copy.deepcopy(sim.state)
    outcome = sim.tick([obs(OBSIDIAN, 99)], boot=None)
    assert outcome.events == []
    assert {s for s, (o, _) in outcome.scope_status.items() if o == "unknown"} == set(
        SCOPES
    )
    assert sim.state.units == before.units
    assert sim.state.boot_id == BOOT_A


def test_complete_scope_drops_removed_unit_silently() -> None:
    sim = Sim()
    sim.series([0, 39])
    assert sim.state.units[OBSIDIAN].episode is not None
    outcome = sim.tick([obs("system:other.service", 0)])
    assert outcome.events == []
    assert OBSIDIAN not in sim.state.units
    assert "system:other.service" in sim.state.units


def test_counts_and_scope_status_cover_every_scope() -> None:
    outcome = Sim().tick([obs(OBSIDIAN, 0)])
    assert set(outcome.counts) == set(COUNT_KEYS)
    assert "clock_rebased" not in outcome.counts
    assert set(outcome.scope_status) == set(SCOPES)
    assert outcome.scope_status["system"] == (
        "healthy",
        "1 watched, 0 ignored, 1 excluded, 5 ms",
    )


# --------------------------------------------------------------------------- #
# Time is never an input (INV-CL-9′). Replaces the clock-regression, bracket,
# dominance-compaction and rollback tests of the proof model.
# --------------------------------------------------------------------------- #
CONTAINER = "container:vikunja"

# One scripted run that exercises every branch: first sight, a single
# restart, a consecutive-rise alert, a quiet tick, a clear, a threshold
# alert, a decrease, a container re-creation and a reboot.
_SCRIPT: list[tuple[int, int, str, str]] = [
    # (obsidian count, container count, container id, boot)
    (0, 0, "cid-1", BOOT_A),
    (1, 0, "cid-1", BOOT_A),
    (2, 5, "cid-1", BOOT_A),
    (2, 5, "cid-1", BOOT_A),
    (2, 5, "cid-1", BOOT_A),
    (9, 1, "cid-1", BOOT_A),
    (9, 7, "cid-2", BOOT_A),
    (10, 8, "cid-2", BOOT_A),
    (3, 9, "cid-2", BOOT_B),
    (4, 9, "cid-2", BOOT_B),
    (5, 9, "cid-2", BOOT_B),
    (5, 9, "cid-2", BOOT_B),
]


def _fingerprint(outcome: TickOutcome) -> tuple[Any, ...]:
    """Every decision of one tick, with every time value stripped out."""
    events = tuple(
        (
            e.kind,
            e.key,
            e.interval.previous_count,
            e.interval.current_count,
            e.interval.delta,
            e.interval.rose_last_tick,
            e.interval.rises,
        )
        for e in outcome.events
    )
    units = tuple(
        sorted(
            (
                key,
                unit.generation,
                unit.boot_id,
                unit.last_count,
                unit.recent_rises,
                None
                if unit.episode is None
                else (
                    unit.episode.ticks_since_alert,
                    unit.episode.quiet_ticks,
                    unit.episode.peak_delta,
                ),
            )
            for key, unit in outcome.new_state.units.items()
        )
    )
    return events, units, tuple(sorted(outcome.counts.items()))


def _run_script(stamps: Sequence[datetime], config: CrashLoopConfig = CFG) -> list:
    assert len(stamps) == len(_SCRIPT)
    sim = Sim(config)
    for (count, ccount, cid, boot), now in zip(_SCRIPT, stamps, strict=True):
        sim.tick(
            [
                obs(OBSIDIAN, count, boot=boot),
                obs(CONTAINER, ccount, generation=cid, boot=boot),
            ],
            now=now,
            boot=boot,
        )
    return [_fingerprint(o) for o in sim.outcomes]


_NORMAL = [at(i) for i in range(len(_SCRIPT))]
_SECONDS = [T0 + timedelta(seconds=s) for s in (0, 1, 1, 1800, 1799)]


@pytest.mark.parametrize(
    "stamps",
    [
        [at(-i) for i in range(len(_SCRIPT))],  # every step backward
        [T0 + timedelta(hours=7 * i) for i in range(len(_SCRIPT))],  # hours apart
        [T0] * len(_SCRIPT),  # held equal
        [at(i) + timedelta(minutes=(-1) ** i * 40) for i in range(len(_SCRIPT))],
        [T0 - timedelta(days=365 * i) for i in range(len(_SCRIPT))],
        [T0 + timedelta(microseconds=i) for i in range(len(_SCRIPT))],
    ],
    ids=["backward", "hours-forward", "equal", "zigzag", "years-back", "microseconds"],
)
def test_clock_steps_never_change_a_decision(stamps: list[datetime]) -> None:
    normal = _run_script(_NORMAL)
    assert _run_script(stamps) == normal
    # The script really exercises the state machine.
    kinds_seen = {e[0] for tick in normal for e in tick[0]}
    assert kinds_seen == {"alert", "cleared"}


@pytest.mark.parametrize(
    "seconds",
    [(1, 1, 1800), (1, 1, 1799), (1, 1, 1800.000001)],
    ids=["codex-round-3", "codex-round-4", "codex-round-2"],
)
def test_codex_rollback_sequences_decide_as_normal_ticks(
    seconds: tuple[float, ...],
) -> None:
    # Codex's post-merge counterexamples, (observed_from, now) bracket gone:
    # counts 0, 0, 5 at pass stamps around a clock rollback. Under tick
    # counting the stamps are irrelevant: a rise of 5 since the previous tick
    # pages, exactly as it does on normal 15-minute ticks.
    def run(stamps: Sequence[datetime]) -> list:
        sim = Sim()
        for count, now in zip((0, 0, 5), stamps, strict=True):
            sim.unit(count, now=now)
        return [_fingerprint(o) for o in sim.outcomes]

    rollback = run([T0 + timedelta(seconds=s) for s in seconds])
    normal = run([at(0), at(1), at(2)])
    assert rollback == normal
    assert [len(tick[0]) for tick in normal] == [0, 0, 1]
    assert normal[2][0][0][0] == "alert"


def test_rollback_stamps_only_change_the_informational_text() -> None:
    sim = Sim()
    sim.unit(0, now=T0 + timedelta(seconds=1))
    sim.unit(0, now=T0 - timedelta(seconds=1))
    outcome = sim.unit(5, now=T0 - timedelta(seconds=2))
    event = outcome.events[0]
    assert event.interval.previous_seen_at == T0 - timedelta(seconds=1)
    assert event.interval.observed_at == T0 - timedelta(seconds=2)
    alert = render_alert(event, CFG)
    assert "previous tick stamped 2026-11-23T11:59:59+00:00" in alert.description


def test_tick_rule_property_random_counts_and_clocks() -> None:
    """Property (INV-CL-3′, INV-CL-9′), 2000 seeded cases.

    For random count sequences: an ``alert`` or ``reremind`` fires only when
    the tick rule holds on that tick; a threshold rise with no episode open
    always alerts; and a run with random wall-clock stamps makes exactly the
    decisions of the same run on the normal cadence. Replaces the pigeonhole
    property test.
    """
    rng = random.Random(1133)
    pages = 0
    for _case in range(2000):
        threshold = rng.randint(2, 6)
        n = rng.randint(2, 4)
        config = cfg(
            threshold=threshold,
            consecutive_rise_ticks=n,
            quiet_ticks_to_clear=rng.randint(1, 3),
            reremind_ticks=rng.randint(1, 6),
        )
        count = rng.randint(0, 50)
        counts = [count]
        for _ in range(rng.randint(1, 40)):
            step = rng.choice([0, 0, 0, 1, 1, 2, 3, 5, 40, -1])
            count = max(0, count + step) if step >= 0 else rng.randint(0, count)
            counts.append(count)

        sim = Sim(config)
        deltas_since_rebase: list[int] = []
        previous: int | None = None
        for index, value in enumerate(counts):
            unit_before = sim.state.units.get(OBSIDIAN)
            open_before = unit_before is not None and unit_before.episode is not None
            outcome = sim.unit(value)
            if previous is None or value < previous:
                deltas_since_rebase = []  # first sight or a reset: a baseline
                assert outcome.events == [] or kinds(outcome) == ["cleared"]
                previous = value
                continue
            delta = value - previous
            run = 0
            for past in reversed(deltas_since_rebase):
                if past < 1:
                    break
                run += 1
            rule = delta >= threshold or (delta >= 1 and run >= n - 1)
            for event in outcome.events:
                if event.kind in ("alert", "reremind"):
                    pages += 1
                    assert rule, (index, counts, config)
                    assert event.interval.delta == delta
            if not open_before and delta >= threshold:
                assert kinds(outcome) == ["alert"], (index, counts)
            deltas_since_rebase.append(delta)
            previous = value

        normal = [_fingerprint(o) for o in sim.outcomes]
        scrambled = Sim(config)
        for value in counts:
            jitter = timedelta(seconds=rng.randint(-(10**7), 10**7))
            scrambled.unit(value, now=T0 + jitter)
        assert [_fingerprint(o) for o in scrambled.outcomes] == normal
    assert pages > 500  # the property is not vacuous


def test_state_round_trips_through_disk_mid_episode(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    sim = Sim()
    sim.series([0, 1, 2])
    save_state(sim.state, path, now=at(2))
    loaded, diagnostics = load_state(path)
    assert diagnostics == []
    assert loaded.units == sim.state.units
    resumed = Sim()
    resumed.state = loaded
    resumed.outcomes = list(sim.outcomes)
    assert resumed.unit(2).events == [] and sim.unit(2).events == []
    assert resumed.state.units == sim.state.units


# --------------------------------------------------------------------------- #
# Emission plan and rendering (contract §1-§4, R-15).
# --------------------------------------------------------------------------- #
def _event(
    key: str,
    kind: str = "alert",
    delta: int = 39,
    observed: datetime | None = None,
) -> CrashLoopEvent:
    observed = observed or at(1)
    scope, name = key.split(":", 1)
    interval = TickInterval(
        previous_count=0,
        current_count=delta,
        delta=delta,
        rose_last_tick=False,
        previous_seen_at=at(0),
        observed_at=observed,
        rises=(delta,) if delta >= 1 else (),
    )
    return CrashLoopEvent(
        kind=kind,
        key=key,
        scope=scope,
        name=name,
        state=RUNNING,
        episode_started_utc=at(1),
        interval=interval,
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
    assert description.count("; ") == listed
    assert all(len(v) <= DETAIL_VALUE_MAX for v in aggregate.details.values())
    assert description.startswith(
        "system:some-fairly-long-unit-name-03.service alert +39 active (running)"
    )


def test_aggregate_lists_everything_when_it_fits() -> None:
    events = [_event(f"system:u{i}.service", kind="cleared", delta=0) for i in range(2)]
    aggregate = render_aggregate(events)
    assert aggregate.severity is Severity.INFO
    assert "more - see canary ledger" not in aggregate.description
    assert aggregate.details["units_listed"] == "2"
    assert aggregate.description == (
        "system:u0.service cleared +0 active (running); "
        "system:u1.service cleared +0 active (running)"
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


def test_threshold_alert_text_and_details_match_contract() -> None:
    sim = Sim()
    outcome = sim.series([0, 39])[1]
    alert = render_alert(outcome.events[0], CFG)
    assert isinstance(alert, Alert)
    assert alert.source == "felix-canary:crash-loop:system:obsidian-sync.service"
    assert alert.severity is Severity.ERROR
    assert alert.action is None
    assert alert.timestamp == at(1)
    assert alert.title == (
        "obsidian-sync.service crash-looping: 39 restarts since the previous "
        "canary tick"
    )
    assert alert.description == (
        "system unit obsidian-sync.service restarted 39 times since the previous "
        "canary tick (15 min ago; restart count 0 -> 39). "
        "Current state: active (running)."
    )
    assert alert.details == {
        "component_id": "crash-loop:system:obsidian-sync.service",
        "kind": "alert",
        "scope": "system",
        "unit": "obsidian-sync.service",
        "previous_count": "0",
        "current_count": "39",
        "delta": "39",
        "rose_last_tick": "false",
        "previous_seen_at": "2026-11-23T12:00:00+00:00",
        "observed_at": "2026-11-23T12:15:00+00:00",
        "state": "active (running)",
        "episode_started_utc": "2026-11-23T12:15:00+00:00",
    }
    assert all(isinstance(v, str) for v in alert.details.values())

    # The cleared entry from the same episode.
    sim.unit(39)
    cleared_event = sim.unit(39).events[0]
    assert cleared_event.kind == "cleared"
    cleared = render_alert(cleared_event, CFG)
    assert cleared.severity is Severity.INFO
    assert cleared.title == "obsidian-sync.service crash loop cleared"
    assert cleared.description == (
        "system unit obsidian-sync.service has not restarted for 2 consecutive "
        "canary ticks; the episode that began 2026-11-23T12:15:00+00:00 has ended. "
        "Current state: active (running)."
    )
    assert cleared.details["kind"] == "cleared"
    assert cleared.details["delta"] == "0"
    assert all(isinstance(v, str) for v in cleared.details.values())


def test_consecutive_rise_alert_text() -> None:
    sim = Sim()
    outcome = sim.series([0, 2, 4])[2]
    alert = render_alert(outcome.events[0], CFG)
    assert alert.title == (
        "obsidian-sync.service crash-looping: restarted on 2 consecutive canary "
        "ticks (+2, +2)"
    )
    assert alert.description == (
        "system unit obsidian-sync.service has restarted on 2 consecutive canary "
        "ticks (+2, +2; previous tick 15 min ago; restart count 2 -> 4). "
        "Current state: active (running)."
    )
    assert alert.details["rose_last_tick"] == "true"
    assert alert.details["delta"] == "2"


def test_reremind_text() -> None:
    remind = render_alert(_event(OBSIDIAN, "reremind"), CFG)
    assert remind.severity is Severity.ERROR
    assert remind.title.startswith("still obsidian-sync.service crash-looping: ")
    assert remind.description.endswith("The episode began 2026-11-23T12:15:00+00:00.")
    assert remind.details["kind"] == "reremind"


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (1, "1 min ago"),
        (60, "1 min ago"),
        (61, "2 min ago"),
        (900, "15 min ago"),
        (960, "16 min ago"),
        (0, "previous tick stamped 2026-11-23T12:00:00+00:00"),
        (-30, "previous tick stamped 2026-11-23T12:00:00+00:00"),
    ],
)
def test_time_since_previous_tick_is_text_only(seconds: int, text: str) -> None:
    interval = TickInterval(0, 5, 5, False, T0, T0 + timedelta(seconds=seconds))
    assert crash_loop._since_previous(interval) == text


# --------------------------------------------------------------------------- #
# Purity.
# --------------------------------------------------------------------------- #
def test_evaluate_tick_does_not_mutate_prior_state() -> None:
    config = cfg(ignore={"system:ignored.service"}, reremind_ticks=3)

    def unit(
        count: int, rises: tuple[int, ...] = (), episode: Episode | None = None
    ) -> UnitState:
        return UnitState(BOOT_A, BOOT_A, count, rises, at(0), episode)

    prior = CrashLoopState(
        updated_at_utc=at(0),
        boot_id=BOOT_A,
        units={
            OBSIDIAN: unit(
                5,
                (5,),
                Episode(
                    started_utc=at(-10),
                    last_alert_utc=at(-3),
                    ticks_since_alert=3,
                    quiet_ticks=1,
                    peak_delta=5,
                ),
            ),
            "system:quiet.service": unit(0),
            "system:ignored.service": unit(1),
            "system:gone.service": unit(1),
            "container:vikunja": UnitState(
                "cid-1",
                BOOT_A,
                3,
                (),
                at(0),
                Episode(at(0), at(0), 0, 0, 3),
            ),
            "user:x.service": unit(9),
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
            readings(observations, incomplete=["user"]), prior, config, at(1), BOOT_A
        )
        assert prior == snapshot
        assert outcome.new_state is not prior
        for key, new_unit in outcome.new_state.units.items():
            if key in prior.units:
                assert new_unit is not prior.units[key]
                if new_unit.episode is not None:
                    assert new_unit.episode is not prior.units[key].episode
    # The scenarios really exercised the state machine.
    first = evaluate_tick(
        readings(scenarios[0], incomplete=["user"]), prior, config, at(1), BOOT_A
    )
    assert sorted(kinds(first)) == ["alert", "reremind"]
    second = evaluate_tick(
        readings(scenarios[1], incomplete=["user"]), prior, config, at(1), BOOT_A
    )
    assert kinds(second) == ["cleared"]
    # And the same inputs give the same outputs (determinism).
    again = evaluate_tick(
        readings(scenarios[0], incomplete=["user"]), prior, config, at(1), BOOT_A
    )
    assert again == first


def test_module_is_pure() -> None:
    source = crash_loop.__file__
    assert source is not None
    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    for forbidden in ("open(", "subprocess", "datetime.now", "time.", "import random"):
        assert forbidden not in text, forbidden


def test_proof_machinery_is_gone() -> None:
    for retired in ("prove", "_maintain_history", "_make_proof", "UnverifiedRise"):
        assert not hasattr(crash_loop, retired), retired
    with open(crash_loop.__file__, encoding="utf-8") as fh:
        text = fh.read()
    for word in ("observed_from", "window_seconds", "DEFAULT_WINDOW", "unverified"):
        assert word not in text, word


def test_evaluate_tick_takes_no_bracket() -> None:
    with pytest.raises(TypeError):
        evaluate_tick(  # type: ignore[call-arg]
            [], CrashLoopState.empty(), CFG, at(0), BOOT_A, observed_from=at(0)
        )


def test_naive_now_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_tick([], CrashLoopState.empty(), CFG, datetime(2026, 1, 1), BOOT_A)
