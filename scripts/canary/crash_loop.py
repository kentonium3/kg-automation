"""Pure crash-loop decision core (mission crash-loop-unit-alerting, #1133, WP02).

Turns per-unit restart-count observations into crash-loop ``alert``,
``reremind`` and ``cleared`` events, runs the per-unit episode state machine,
plans the per-tick emissions (the cap plus one bounded aggregate) and renders
the alert-bus :class:`~scripts.common.alert_bus.model.Alert` payloads.

**Pure** (NFR-006, INV-CL-8): no I/O, no clock reads, no child process, no model
call and no randomness. ``now`` and ``boot_id`` are injected; every rendered
``Alert`` carries an explicit ``timestamp`` so the bus default (a clock read) is
never used. :func:`evaluate_tick` never mutates its ``prior_state``.

The per-unit order within one tick follows data-model.md exactly:

1. clock check (INV-CL-9);
2. boot change: rebase and close any episode silently (INV-CL-2);
3. reset (container-ID change or a decrease): rebase; inside an episode the
   tick counts as quiet and may emit ``cleared``, never ``alert``/``reremind``;
4. ``rose``;
5. proof: the tightest holding proof and the tightest unverified candidate
   over every history entry (research R-05, pigeonhole);
6. the episode state machine (INV-CL-3/4/5);
7. history maintenance by dominance compaction (research R-07).

References: data-model.md (invariants INV-CL-1..10), research.md R-04..R-08,
R-13, R-15, contracts/crash-loop-alert.md §1-§4.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Final

from scripts.canary.crash_loop_model import (
    HISTORY_MAX,
    HISTORY_RETENTION,
    SCOPES,
    CrashLoopConfig,
    CrashLoopEvent,
    Proof,
    RestartObservation,
    ScopeReading,
    UnverifiedRise,
)
from scripts.canary.crash_loop_state import CrashLoopState, Episode, UnitState
from scripts.canary.dedup import DEFAULT_WINDOW
from scripts.common.alert_bus.model import Alert, Severity

__all__ = [
    "AGGREGATE_DESCRIPTION_BUDGET",
    "AGGREGATE_SOURCE",
    "COUNT_KEYS",
    "Emission",
    "TickOutcome",
    "evaluate_tick",
    "plan_emissions",
    "prove",
    "render_aggregate",
    "render_alert",
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
    "clock_skipped",
    "rebased_on_boot",
)

_ONE_MICROSECOND: Final[timedelta] = timedelta(microseconds=1)
_MICROS_PER_SECOND: Final[int] = 1_000_000
_KIND_ORDER: Final[Mapping[str, int]] = {"alert": 0, "reremind": 1, "cleared": 2}


# --------------------------------------------------------------------------- #
# Outputs.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TickOutcome:
    """Everything one tick decided (data-model.md "Decision function")."""

    new_state: CrashLoopState
    events: list[CrashLoopEvent]
    unverified: list[UnverifiedRise]
    scope_status: dict[str, tuple[str, str]]
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Emission:
    """One alert-bus call and the events it carries (one, or the aggregate's)."""

    alert: Alert
    events: tuple[CrashLoopEvent, ...]


# --------------------------------------------------------------------------- #
# T006 — the proven-crossing rule (R-05).
# --------------------------------------------------------------------------- #
def _micros(delta: timedelta) -> int:
    """*delta* as an exact integer number of microseconds."""
    return delta // _ONE_MICROSECOND


def _make_proof(
    baseline: tuple[datetime, int], current: int, now: datetime, config: CrashLoopConfig
) -> Proof:
    baseline_at, baseline_count = baseline
    period_us = _micros(now - baseline_at)
    window_us = config.window_seconds * _MICROS_PER_SECOND
    # Exact integer ceiling: a float error can never cross a window boundary.
    m = max(1, -(-period_us // window_us))
    return Proof(
        baseline_at=baseline_at,
        baseline_count=baseline_count,
        current_count=current,
        observed_at=now,
        delta=current - baseline_count,
        period_seconds=period_us / _MICROS_PER_SECOND,
        m=m,
        bound=m * (config.threshold - 1) + 1,
    )


def prove(
    candidates: Sequence[tuple[datetime, int]],
    current_count: int,
    now: datetime,
    config: CrashLoopConfig,
) -> tuple[Proof | None, Proof | None]:
    """Return ``(best_holding_proof, tightest_unverified)`` over *candidates*.

    Each candidate ``b`` (strictly before *now*) gives ``m = ceil(L / window)``
    with ``m ≥ 1`` and ``bound = m·(N − 1) + 1``; ``Δ ≥ bound`` proves at least
    N restarts within one window-length interval (pigeonhole). The best holding
    proof has the smallest ``L`` (ties: the larger ``Δ``). The tightest
    unverified candidate (``Δ ≥ N`` but no holding proof at all) is returned
    only when no proof holds.
    """
    best: Proof | None = None
    unverified: Proof | None = None
    for baseline in candidates:
        if baseline[0] >= now:
            continue
        proof = _make_proof(baseline, current_count, now, config)
        if proof.holds:
            if (
                best is None
                or proof.period_seconds < best.period_seconds
                or (
                    proof.period_seconds == best.period_seconds
                    and proof.delta > best.delta
                )
            ):
                best = proof
        elif proof.delta >= config.threshold and (
            unverified is None or proof.period_seconds < unverified.period_seconds
        ):
            unverified = proof
    if best is not None:
        return best, None
    return None, unverified


def _maintain_history(
    history: Sequence[tuple[datetime, int]],
    stored_at: datetime,
    now: datetime,
    current: int,
    window_seconds: int,
) -> list[tuple[datetime, int]]:
    """Dominance compaction then pruning (research R-07).

    The current observation is stored at *stored_at*, the earliest instant the
    counter can have been sampled (post-merge review: a baseline must never be
    later than its true sample time, or a later proof under-states ``L``).
    An equal count replaces the newest entry (a later baseline with the same
    count dominates); otherwise ``(stored_at, current)`` is appended. Every
    entry with ``at ≥ now − window`` is kept (round-4 M1). Older entries older
    than ``HISTORY_RETENTION`` are dropped, and at most ``HISTORY_MAX`` of them
    are kept, dropping the oldest. The newest entry is always kept.
    """
    entries = list(history)
    if entries and entries[-1][1] == current:
        entries[-1] = (stored_at, current)
    else:
        entries.append((stored_at, current))
    window_start = now - timedelta(seconds=window_seconds)
    retention_start = now - HISTORY_RETENTION
    newest = entries[-1]
    body = entries[:-1]
    in_window = [entry for entry in body if entry[0] >= window_start]
    older = [entry for entry in body if retention_start <= entry[0] < window_start][
        -HISTORY_MAX:
    ]
    return [*older, *in_window, newest]


# --------------------------------------------------------------------------- #
# T007/T008 — per-unit evaluation and the episode state machine.
# --------------------------------------------------------------------------- #
def _copy_unit(unit: UnitState) -> UnitState:
    episode = unit.episode
    return UnitState(
        generation=unit.generation,
        boot_id=unit.boot_id,
        history=list(unit.history),
        episode=None
        if episode is None
        else Episode(
            started_utc=episode.started_utc,
            last_alert_utc=episode.last_alert_utc,
            quiet_ticks=episode.quiet_ticks,
            peak_delta=episode.peak_delta,
        ),
    )


@dataclass
class _UnitResult:
    state: UnitState
    event: CrashLoopEvent | None = None
    unverified: UnverifiedRise | None = None
    counter: str | None = None  # a COUNT_KEYS entry this unit adds to


def _event(
    kind: str, obs: RestartObservation, episode: Episode, proof: Proof
) -> CrashLoopEvent:
    return CrashLoopEvent(
        kind=kind,
        key=obs.key,
        scope=obs.scope,
        name=obs.name,
        state=obs.state,
        episode_started_utc=episode.started_utc,
        proof=proof,
    )


def _evaluate_unit(
    obs: RestartObservation,
    prior: UnitState | None,
    config: CrashLoopConfig,
    now: datetime,
    boot_id: str,
    observed_from: datetime,
) -> _UnitResult:
    current = obs.restart_count

    # First sight (FR-010, INV-CL-1): baseline only.
    if prior is None:
        return _UnitResult(
            state=UnitState(
                generation=obs.generation,
                boot_id=boot_id,
                history=[(observed_from, current)],
                episode=None,
            ),
            counter="first_seen",
        )

    # 1. Clock (INV-CL-9): runs before any other check, against *now*, the
    # LATEST possible sampling instant.
    last_at, last_count = prior.history[-1]
    if now <= last_at:
        return _UnitResult(state=_copy_unit(prior), counter="clock_skipped")

    # The stored time is the earliest possible sample time, kept strictly after
    # the previous entry so history stays strictly ascending. This sample was
    # taken strictly after the previous one, which was taken at or after
    # ``last_at``, so ``last_at + 1 µs`` is still a lower bound; and because
    # ``now > last_at``, ``stored_at ≤ now``.
    stored_at = max(observed_from, last_at + _ONE_MICROSECOND)
    rebased = [(stored_at, current)]

    # 2. Boot change (INV-CL-2, round-3 HIGH): rebase, close silently.
    if prior.boot_id != boot_id:
        return _UnitResult(
            state=UnitState(
                generation=obs.generation,
                boot_id=boot_id,
                history=rebased,
                episode=None,
            ),
            counter="rebased_on_boot",
        )

    episode = None if prior.episode is None else _copy_unit(prior).episode
    last_interval = _make_proof(prior.history[-1], current, now, config)

    # 3. Reset (FR-009): container-ID change or a decrease.
    if obs.generation != prior.generation or current < last_count:
        state = UnitState(
            generation=obs.generation, boot_id=boot_id, history=rebased, episode=None
        )
        if episode is None:
            return _UnitResult(state=state, counter="resets")
        # Inside an episode the reset tick counts as quiet (round-3 M1).
        episode.quiet_ticks += 1
        result = _UnitResult(state=state, counter="resets")
        if episode.quiet_ticks >= config.quiet_ticks_to_clear:
            result.event = _event("cleared", obs, episode, last_interval)
        else:
            state.episode = episode
        return result

    # 4. Rise, 5. proof.
    rose = current > last_count
    holding, unverified = prove(prior.history, current, now, config)
    result = _UnitResult(
        state=UnitState(
            generation=obs.generation,
            boot_id=boot_id,
            history=list(prior.history),
            episode=episode,
        )
    )

    # 6. Episode state machine.
    if episode is None:
        if holding is not None:
            new_episode = Episode(
                started_utc=now,
                last_alert_utc=now,
                quiet_ticks=0,
                peak_delta=holding.delta,
            )
            result.state.episode = new_episode
            result.event = _event("alert", obs, new_episode, holding)
        elif unverified is not None:
            result.unverified = UnverifiedRise(
                key=obs.key,
                scope=obs.scope,
                name=obs.name,
                state=obs.state,
                proof=unverified,
            )
    else:
        episode.quiet_ticks = 0 if rose else episode.quiet_ticks + 1
        if episode.quiet_ticks >= config.quiet_ticks_to_clear:
            # INV-CL-5: cleared once, episode closed, history rebased (CX-2).
            result.event = _event("cleared", obs, episode, last_interval)
            result.state.episode = None
            result.state.history = rebased
            return result
        if holding is not None:
            if now - episode.last_alert_utc >= DEFAULT_WINDOW:
                # INV-CL-4 ruling (WP02 review cycle 1): a re-remind needs fresh
                # evidence, a baseline observed at or after the last page. An
                # old burst's baseline can never re-page a slowly rising unit.
                fresh, _ = prove(
                    [b for b in prior.history if b[0] >= episode.last_alert_utc],
                    current,
                    now,
                    config,
                )
                if fresh is not None:
                    result.event = _event("reremind", obs, episode, fresh)
                    episode.last_alert_utc = now
            episode.peak_delta = max(episode.peak_delta, holding.delta)

    # 7. History maintenance (dominance compaction, R-07).
    result.state.history = _maintain_history(
        result.state.history, stored_at, now, current, config.window_seconds
    )
    return result


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
    *,
    observed_from: datetime | None = None,
) -> TickOutcome:
    """Decide one tick. Pure; never mutates *prior_state*.

    The counters were sampled somewhere in ``[observed_from, now]`` (the
    caller brackets the read with two wall-clock readings; *observed_from*
    defaults to *now*). The bracket keeps every proof sound (NFR-004,
    post-merge review): the observation is **stored** at *observed_from*, the
    earliest possible sample time, and every candidate interval is
    **computed** as ``L = now − baseline.at`` with *now* the latest possible
    sampling instant. ``L`` is therefore never less than the true interval, so
    ``m`` can only be over-estimated. The clock rule (INV-CL-9), episode times,
    the re-remind gap and every event's ``observed_at`` use *now*.

    Scopes are processed in ``SCOPES`` order and observations in reading
    order, so the event list is deterministic. A ``None`` *boot_id* makes every
    scope ``unknown`` and carries all state forward (WP03 already fails every
    scope when the boot ID is unreadable; this is the same fail-safe here).
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("evaluate_tick: now must be timezone-aware")
    if observed_from is None:
        observed_from = now
    elif observed_from.tzinfo is None or observed_from.utcoffset() is None:
        raise ValueError("evaluate_tick: observed_from must be timezone-aware")
    elif observed_from > now:
        raise ValueError("evaluate_tick: observed_from must not be after now")
    by_scope = _readings_by_scope(readings)
    prior_units = prior_state.units
    units: dict[str, UnitState] = {}
    events: list[CrashLoopEvent] = []
    unverified: list[UnverifiedRise] = []
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
            result = _evaluate_unit(
                obs, prior_units.get(obs.key), config, now, boot_id, observed_from
            )
            units[obs.key] = result.state
            if result.counter is not None:
                counts[result.counter] += 1
            if result.event is not None:
                events.append(result.event)
            if result.unverified is not None:
                unverified.append(result.unverified)
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
        unverified=unverified,
        scope_status=scope_status,
        counts=counts,
    )


# --------------------------------------------------------------------------- #
# T009 — emission plan and rendering (contracts/crash-loop-alert.md §1-§4).
# --------------------------------------------------------------------------- #
def _minutes(seconds: float) -> int:
    """Whole minutes, rounded up, minimum 1."""
    micros = round(seconds * _MICROS_PER_SECOND)
    return max(1, -(-micros // (60 * _MICROS_PER_SECOND)))


def _period(seconds: float) -> str:
    return f"{_minutes(seconds)} min"


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _details(event: CrashLoopEvent) -> dict[str, str]:
    proof = event.proof
    return {
        "component_id": f"crash-loop:{event.key}",
        "kind": event.kind,
        "scope": event.scope,
        "unit": event.name,
        "delta": str(proof.delta),
        "period_seconds": str(round(proof.period_seconds)),
        "baseline_count": str(proof.baseline_count),
        "current_count": str(proof.current_count),
        "m": str(proof.m),
        "bound": str(proof.bound),
        "state": event.state,
        "episode_started_utc": _iso(event.episode_started_utc),
    }


def render_alert(event: CrashLoopEvent, config: CrashLoopConfig) -> Alert:
    """Render one event as its alert-bus payload (contract §1-§3)."""
    proof = event.proof
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
            timestamp=proof.observed_at,
        )
    title = (
        f"{event.name} crash-looping: {proof.delta} restarts in "
        f"{_period(proof.period_seconds)}"
    )
    description = (
        f"{event.scope} unit {event.name} restarted {proof.delta} times between "
        f"{_iso(proof.baseline_at)} and {_iso(proof.observed_at)} "
        f"(restart count {proof.baseline_count} -> {proof.current_count}), which "
        f"proves at least {config.threshold} restarts within "
        f"{_period(config.window_seconds)}. Current state: {event.state}."
    )
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
        timestamp=proof.observed_at,
    )


def _aggregate_entry(event: CrashLoopEvent) -> str:
    proof = event.proof
    return (
        f"{event.key} {event.kind} +{proof.delta}/{_period(proof.period_seconds)} "
        f"{event.state}"
    )


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
    observed = max(event.proof.observed_at for event in events)
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
    events: Iterable[CrashLoopEvent], config: CrashLoopConfig
) -> list[Emission]:
    """Order the tick's events and apply the per-tick cap (R-15).

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
        emissions.append(Emission(alert=render_aggregate(rest), events=tuple(rest)))
    return emissions
