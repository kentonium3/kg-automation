"""Pure crash-loop decision core (mission crash-loop-unit-alerting, #1133, WP02).

Turns per-unit restart-count observations into crash-loop ``alert``,
``reremind`` and ``cleared`` events, runs the per-unit episode state machine,
plans the per-tick emissions (the cap plus one bounded aggregate) and renders
the alert-bus :class:`~scripts.common.alert_bus.model.Alert` payloads.

**Kent's 2026-11-24 ruling (research R-16): count ticks, not the clock.** For each
watched unit, on each complete tick, ``Δ = current − last_count``. The trigger
holds when ``Δ ≥ threshold``, or when ``Δ ≥ 1`` on this tick and on each of the
previous ``consecutive_rise_ticks − 1`` ticks. No wall-clock value is an input
to any decision (INV-CL-9′): ``now`` only fills alert text, ledger lines and
the informational ``last_seen_at`` / episode stamps.

**Pure** (NFR-006, INV-CL-8): no I/O, no clock reads, no child process, no model
call and no randomness. ``now`` and ``boot_id`` are injected; every rendered
``Alert`` carries an explicit ``timestamp`` so the bus default (a clock read) is
never used. :func:`evaluate_tick` never mutates its ``prior_state``.

The per-unit order within one tick follows data-model.md "Tick-counting model":

1. boot change: rebase and close any episode silently (INV-CL-2);
2. reset (container-ID change or a decrease): rebase with no event; inside an
   episode the tick counts as quiet and may emit ``cleared``, never
   ``alert``/``reremind``; the rise run restarts;
3. no episode: the trigger opens one and emits ``alert``;
4. episode open: count the tick; a rise resets the quiet count, a quiet tick
   adds to it; K quiet ticks emit ``cleared`` and restart the rise run, so a
   new episode needs fresh rises; otherwise the trigger re-reminds once
   ``reremind_ticks`` ticks have passed since the last page;
5. store ``last_count``, the rise run and ``last_seen_at``.

References: data-model.md (invariants INV-CL-1..10, INV-CL-3′, INV-CL-9′),
research.md R-06, R-08, R-13, R-15, R-16, contracts/crash-loop-alert.md §1-§4.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Final

from scripts.canary.crash_loop_model import (
    SCOPES,
    CrashLoopConfig,
    CrashLoopEvent,
    RestartObservation,
    ScopeReading,
    TickInterval,
)
from scripts.canary.crash_loop_state import CrashLoopState, Episode, UnitState
from scripts.common.alert_bus.model import Alert, Severity

__all__ = [
    "AGGREGATE_DESCRIPTION_BUDGET",
    "AGGREGATE_SOURCE",
    "COUNT_KEYS",
    "Emission",
    "TickOutcome",
    "evaluate_tick",
    "plan_emissions",
    "render_aggregate",
    "render_alert",
    "triggers",
]

SOURCE_PREFIX: Final[str] = "felix-canary:crash-loop:"
AGGREGATE_SOURCE: Final[str] = "felix-canary:crash-loop:aggregate"

# The aggregate description stays within this budget, under the bus's
# DESCRIPTION_MAX (1000), so the bus never truncates it silently (R-15).
AGGREGATE_DESCRIPTION_BUDGET: Final[int] = 900

# Every key of TickOutcome.counts, always present.
COUNT_KEYS: Final[tuple[str, ...]] = (
    "watched",
    "ignored",
    "first_seen",
    "resets",
    "in_episode",
    "rebased_on_boot",
)

_KIND_ORDER: Final[Mapping[str, int]] = {"alert": 0, "reremind": 1, "cleared": 2}


# --------------------------------------------------------------------------- #
# Outputs.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TickOutcome:
    """Everything one tick decided (data-model.md "Decision function")."""

    new_state: CrashLoopState
    events: list[CrashLoopEvent]
    scope_status: dict[str, tuple[str, str]]
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Emission:
    """One alert-bus call and the events it carries (one, or the aggregate's)."""

    alert: Alert
    events: tuple[CrashLoopEvent, ...]


# --------------------------------------------------------------------------- #
# The tick rule (R-16).
# --------------------------------------------------------------------------- #
def triggers(delta: int, prior_rises: Sequence[int], config: CrashLoopConfig) -> bool:
    """Kent's rule: ``Δ ≥ threshold``, or ``Δ ≥ 1`` on N consecutive ticks.

    *prior_rises* is the run of consecutive positive deltas ending at the
    previous complete tick (empty when it did not rise). With the default
    ``consecutive_rise_ticks = 2`` the second clause is "rose on this tick and
    on the previous one".
    """
    if delta >= config.threshold:
        return True
    return delta >= 1 and len(prior_rises) >= config.consecutive_rise_ticks - 1


# --------------------------------------------------------------------------- #
# Per-unit evaluation and the episode state machine.
# --------------------------------------------------------------------------- #
def _copy_episode(episode: Episode | None) -> Episode | None:
    if episode is None:
        return None
    return Episode(
        started_utc=episode.started_utc,
        last_alert_utc=episode.last_alert_utc,
        ticks_since_alert=episode.ticks_since_alert,
        quiet_ticks=episode.quiet_ticks,
        peak_delta=episode.peak_delta,
    )


def _copy_unit(unit: UnitState) -> UnitState:
    return UnitState(
        generation=unit.generation,
        boot_id=unit.boot_id,
        last_count=unit.last_count,
        recent_rises=unit.recent_rises,
        last_seen_at=unit.last_seen_at,
        episode=_copy_episode(unit.episode),
    )


def _baseline(obs: RestartObservation, boot_id: str, now: datetime) -> UnitState:
    """A fresh baseline: this tick's count, no rise run, no episode."""
    return UnitState(
        generation=obs.generation,
        boot_id=boot_id,
        last_count=obs.restart_count,
        recent_rises=(),
        last_seen_at=now,
        episode=None,
    )


@dataclass
class _UnitResult:
    state: UnitState
    event: CrashLoopEvent | None = None
    counter: str | None = None  # a COUNT_KEYS entry this unit adds to


def _event(
    kind: str, obs: RestartObservation, episode: Episode, interval: TickInterval
) -> CrashLoopEvent:
    return CrashLoopEvent(
        kind=kind,
        key=obs.key,
        scope=obs.scope,
        name=obs.name,
        state=obs.state,
        episode_started_utc=episode.started_utc,
        interval=interval,
    )


def _evaluate_unit(
    obs: RestartObservation,
    prior: UnitState | None,
    config: CrashLoopConfig,
    now: datetime,
    boot_id: str,
) -> _UnitResult:
    current = obs.restart_count

    # First sight (FR-010, INV-CL-1): baseline only.
    if prior is None:
        return _UnitResult(state=_baseline(obs, boot_id, now), counter="first_seen")

    # 1. Boot change (INV-CL-2, round-3 HIGH): rebase, close silently.
    if prior.boot_id != boot_id:
        return _UnitResult(
            state=_baseline(obs, boot_id, now), counter="rebased_on_boot"
        )

    delta = current - prior.last_count
    episode = _copy_episode(prior.episode)

    def interval(rises: tuple[int, ...]) -> TickInterval:
        return TickInterval(
            previous_count=prior.last_count,
            current_count=current,
            delta=delta,
            rose_last_tick=prior.rose_last_tick,
            previous_seen_at=prior.last_seen_at,
            observed_at=now,
            rises=rises,
        )

    # 2. Reset (FR-009): container-ID change or a decrease. Rebase with no
    # event; the rise run restarts. Inside an episode the tick is quiet.
    if obs.generation != prior.generation or current < prior.last_count:
        result = _UnitResult(state=_baseline(obs, boot_id, now), counter="resets")
        if episode is not None:
            episode.ticks_since_alert += 1
            episode.quiet_ticks += 1
            if episode.quiet_ticks >= config.quiet_ticks_to_clear:
                result.event = _event("cleared", obs, episode, interval(()))
            else:
                result.state.episode = episode
        return result

    # The run of consecutive rises ending at this tick, this tick included.
    run = (*prior.recent_rises, delta) if delta >= 1 else ()
    fired = triggers(delta, prior.recent_rises, config)
    event: CrashLoopEvent | None = None

    if episode is None:
        # 3. No episode: the trigger opens one (INV-CL-3′).
        if fired:
            episode = Episode(
                started_utc=now,
                last_alert_utc=now,
                ticks_since_alert=0,
                quiet_ticks=0,
                peak_delta=delta,
            )
            event = _event("alert", obs, episode, interval(run))
    else:
        # 4. Episode open (INV-CL-4/5).
        episode.ticks_since_alert += 1
        episode.quiet_ticks = 0 if delta >= 1 else episode.quiet_ticks + 1
        if episode.quiet_ticks >= config.quiet_ticks_to_clear:
            # Cleared once; the rise run restarts, so a new episode needs
            # fresh rises (CX-2).
            event = _event("cleared", obs, episode, interval(()))
            episode = None
            run = ()
        else:
            if fired and episode.ticks_since_alert >= config.reremind_ticks:
                event = _event("reremind", obs, episode, interval(run))
                episode.ticks_since_alert = 0
                episode.last_alert_utc = now
            episode.peak_delta = max(episode.peak_delta, delta)

    # 5. Store this tick. The run is capped: N − 1 prior rises decide the rule.
    keep = config.consecutive_rise_ticks - 1
    return _UnitResult(
        state=UnitState(
            generation=obs.generation,
            boot_id=boot_id,
            last_count=current,
            recent_rises=run[-keep:],
            last_seen_at=now,
            episode=episode,
        ),
        event=event,
    )


def _readings_by_scope(readings: Iterable[ScopeReading]) -> dict[str, ScopeReading]:
    by_scope: dict[str, ScopeReading] = {}
    for reading in readings:
        if reading.scope in by_scope:
            raise ValueError(f"evaluate_tick: duplicate reading for {reading.scope!r}")
        by_scope[reading.scope] = reading
    return by_scope


def evaluate_tick(
    readings: Iterable[ScopeReading],
    prior_state: CrashLoopState,
    config: CrashLoopConfig,
    now: datetime,
    boot_id: str | None,
) -> TickOutcome:
    """Decide one tick. Pure; never mutates *prior_state*.

    *now* is informational only (INV-CL-9′): it stamps ``last_seen_at``,
    episode times and each event's ``observed_at``, and is never compared with
    a stored value. It must be timezone-aware so the state serialises.

    Scopes are processed in ``SCOPES`` order and observations in reading
    order, so the event list is deterministic. A ``None`` *boot_id* makes every
    scope ``unknown`` and carries all state forward (WP03 already fails every
    scope when the boot ID is unreadable; this is the same fail-safe here).
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("evaluate_tick: now must be timezone-aware")
    by_scope = _readings_by_scope(readings)
    prior_units = prior_state.units
    units: dict[str, UnitState] = {}
    events: list[CrashLoopEvent] = []
    scope_status: dict[str, tuple[str, str]] = {}
    counts = dict.fromkeys(COUNT_KEYS, 0)

    for scope in SCOPES:
        reading = by_scope.get(scope)
        prefix = f"{scope}:"
        if reading is None or not reading.complete or boot_id is None:
            # INV-CL-7: an unread or incomplete scope keeps its state.
            for key, unit in prior_units.items():
                if key.startswith(prefix):
                    units[key] = _copy_unit(unit)
            if reading is None:
                reason = "not read"
            elif not reading.complete:
                reason = reading.error or "incomplete read"
            else:
                reason = "boot id unreadable"
            scope_status[scope] = ("unknown", f"could not check: {reason}")
            continue

        watched = ignored = 0
        seen: set[str] = set()
        for obs in reading.observations:
            if obs.key in seen:
                raise ValueError(f"evaluate_tick: duplicate observation {obs.key!r}")
            seen.add(obs.key)
            if obs.key in config.ignore:
                # INV-CL-6: never stored, never alerts.
                ignored += 1
                continue
            watched += 1
            result = _evaluate_unit(obs, prior_units.get(obs.key), config, now, boot_id)
            units[obs.key] = result.state
            if result.counter is not None:
                counts[result.counter] += 1
            if result.event is not None:
                events.append(result.event)
        # Prior units of this scope absent from the complete reading are dropped
        # (they are simply not copied); an open episode ends silently.
        counts["watched"] += watched
        counts["ignored"] += ignored
        scope_status[scope] = (
            "healthy",
            (
                f"{watched} watched, {ignored} ignored, {reading.excluded} excluded, "
                f"{reading.elapsed_ms} ms"
            ),
        )

    counts["in_episode"] = sum(1 for unit in units.values() if unit.episode is not None)
    new_state = CrashLoopState(
        updated_at_utc=now,
        boot_id=boot_id if boot_id is not None else prior_state.boot_id,
        units=units,
    )
    return TickOutcome(
        new_state=new_state,
        events=events,
        scope_status=scope_status,
        counts=counts,
    )


# --------------------------------------------------------------------------- #
# Emission plan and rendering (contracts/crash-loop-alert.md §1-§4).
# --------------------------------------------------------------------------- #
def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _since_previous(interval: TickInterval) -> str:
    """When the previous tick ran, for the reader. Informational only."""
    seconds = (interval.observed_at - interval.previous_seen_at).total_seconds()
    if seconds <= 0:
        # The wall clock stepped back; the decision never looked at it.
        return f"previous tick stamped {_iso(interval.previous_seen_at)}"
    minutes = max(1, -(-int(seconds) // 60))
    return f"{minutes} min ago"


def _rises_text(rises: Sequence[int]) -> str:
    return ", ".join(f"+{rise}" for rise in rises)


def _details(event: CrashLoopEvent) -> dict[str, str]:
    interval = event.interval
    return {
        "component_id": f"crash-loop:{event.key}",
        "kind": event.kind,
        "scope": event.scope,
        "unit": event.name,
        "previous_count": str(interval.previous_count),
        "current_count": str(interval.current_count),
        "delta": str(interval.delta),
        "rose_last_tick": "true" if interval.rose_last_tick else "false",
        "previous_seen_at": _iso(interval.previous_seen_at),
        "observed_at": _iso(interval.observed_at),
        "state": event.state,
        "episode_started_utc": _iso(event.episode_started_utc),
    }


def render_alert(event: CrashLoopEvent, config: CrashLoopConfig) -> Alert:
    """Render one event as its alert-bus payload (contract §1-§3).

    An event whose rise reached the threshold is described as a single-tick
    rise; otherwise it fired on consecutive rises and lists them. The time
    mentioned ("16 min ago") is information only.
    """
    interval = event.interval
    source = f"{SOURCE_PREFIX}{event.key}"
    if event.kind == "cleared":
        return Alert(
            source=source,
            severity=Severity.INFO,
            title=f"{event.name} crash loop cleared",
            description=(
                f"{event.scope} unit {event.name} has not restarted for "
                f"{config.quiet_ticks_to_clear} consecutive canary ticks; the episode "
                f"that began {_iso(event.episode_started_utc)} has ended. "
                f"Current state: {event.state}."
            ),
            action=None,
            details=_details(event),
            timestamp=interval.observed_at,
        )
    counts = f"restart count {interval.previous_count} -> {interval.current_count}"
    if interval.delta >= config.threshold:
        title = (
            f"{event.name} crash-looping: {interval.delta} restarts since the "
            "previous canary tick"
        )
        description = (
            f"{event.scope} unit {event.name} restarted {interval.delta} times "
            f"since the previous canary tick ({_since_previous(interval)}; {counts})."
        )
    else:
        ticks = len(interval.rises)
        rises = _rises_text(interval.rises)
        title = (
            f"{event.name} crash-looping: restarted on {ticks} consecutive canary "
            f"ticks ({rises})"
        )
        description = (
            f"{event.scope} unit {event.name} has restarted on {ticks} consecutive "
            f"canary ticks ({rises}; previous tick {_since_previous(interval)}; "
            f"{counts})."
        )
    description = f"{description} Current state: {event.state}."
    if event.kind == "reremind":
        title = f"still {title}"
        description = (
            f"{description} The episode began {_iso(event.episode_started_utc)}."
        )
    return Alert(
        source=source,
        severity=Severity.ERROR,
        title=title,
        description=description,
        action=None,
        details=_details(event),
        timestamp=interval.observed_at,
    )


def _aggregate_entry(event: CrashLoopEvent) -> str:
    return f"{event.key} {event.kind} {event.interval.delta:+d} {event.state}"


def _more_suffix(remaining: int, ledger_date: date) -> str:
    return f"... and {remaining} more - see canary ledger {ledger_date.isoformat()}"


def render_aggregate(
    events: Sequence[CrashLoopEvent], ledger_date: date | None = None
) -> Alert:
    """Fold *events* into one bounded aggregate alert (contract §4, R-15).

    Entries are listed while the whole description stays within
    ``AGGREGATE_DESCRIPTION_BUDGET``; the rest are summarised as
    ``"... and <k> more - see canary ledger <date>"``. *ledger_date* defaults
    to the UTC date of the latest ``observed_at`` (the canary ledger's file
    date for this tick).
    """
    if not events:
        raise ValueError("render_aggregate: no events")
    observed = max(event.interval.observed_at for event in events)
    day = ledger_date if ledger_date is not None else observed.astimezone(UTC).date()
    entries = [_aggregate_entry(event) for event in events]
    total = len(entries)

    description = ""
    listed = 0
    for shown in range(total, -1, -1):
        body = "; ".join(entries[:shown])
        if shown < total:
            suffix = _more_suffix(total - shown, day)
            body = f"{body}; {suffix}" if body else suffix
        if len(body) <= AGGREGATE_DESCRIPTION_BUDGET:
            description, listed = body, shown
            break

    paging = any(event.kind in ("alert", "reremind") for event in events)
    return Alert(
        source=AGGREGATE_SOURCE,
        severity=Severity.ERROR if paging else Severity.INFO,
        title=f"{total} more crash-loop events this tick",
        description=description,
        action=None,
        details={"kind": "aggregate", "count": str(total), "units_listed": str(listed)},
        timestamp=observed,
    )


def plan_emissions(
    events: Iterable[CrashLoopEvent],
    config: CrashLoopConfig,
    ledger_date: date | None = None,
) -> list[Emission]:
    """Order the tick's events and apply the per-tick cap (R-15).

    *ledger_date* is the date of the canary ledger file the caller writes this
    tick's event lines to; the aggregate cites it (see :func:`render_aggregate`).

    Sorted alert, reremind, cleared, then by key. The first
    ``max_alerts_per_tick`` are individual emissions; **all** the rest fold
    into one aggregate, so a tick makes at most ``max_alerts_per_tick + 1``
    alert-bus calls.
    """
    ordered = sorted(events, key=lambda e: (_KIND_ORDER[e.kind], e.key))
    cap = config.max_alerts_per_tick
    emissions = [
        Emission(alert=render_alert(event, config), events=(event,))
        for event in ordered[:cap]
    ]
    rest = ordered[cap:]
    if rest:
        emissions.append(
            Emission(alert=render_aggregate(rest, ledger_date), events=tuple(rest))
        )
    return emissions
