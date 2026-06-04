"""Delivery guards (G-1, G-2, G-3) for unsafe-class events (WP03 / T011).

Phase 4 sub-component of the 6-phase cycle. Determines whether to deliver an
``unsafe_to_auto_resolve`` event via WhatsApp or suppress it (and which guard
fired). Guards apply in order: G-3 (cap), G-2 (post-write window), G-1
(24h event-id-stem dedup).

Contract: kitty-specs/.../contracts/cycle-pipeline.md § Phase 4.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from scripts.sync.diff import DivergenceCandidate
from scripts.sync.state import G3DailyCap, GuardState, TaskCacheRecord


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


G1_LOOKBACK_HOURS: int = 24
G2_POST_WRITE_SUPPRESSION_MINUTES: int = 30
G3_DAILY_CAP_DEFAULT: int = 5

_ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# GuardDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardDecision:
    """Outcome of guard application for one unsafe-class event."""

    decision: str           # "approve" | "suppress"
    suppressed_by: str | None  # "g1" | "g2" | "g3" | None


_APPROVE = GuardDecision(decision="approve", suppressed_by=None)


# ---------------------------------------------------------------------------
# event_id helpers
# ---------------------------------------------------------------------------


def event_id_stem(layer: str, entity_id: int, diff_field: str) -> str:
    """Compute the 16-char stem used by G-1 dedup.

    ``sha256(f"{layer}|{entity_id}|{diff_field}")[:16]`` (lowercase hex).

    G-1 looks up prior events by this stem; the full ``event_id`` (computed
    in WP04's emit.py) appends the timestamp and value.
    """
    payload = f"{layer}|{entity_id}|{diff_field}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Calendar-day helpers (Eastern Time)
# ---------------------------------------------------------------------------


def now_et_day(now_utc: datetime) -> str:
    """Return the ET calendar day for the given UTC instant as ``YYYY-MM-DD``."""
    return now_utc.astimezone(_ET).strftime("%Y-%m-%d")


def roll_g3_day_if_needed(guard_state: GuardState, current_et_day: str) -> GuardState:
    """Return a GuardState with G-3 cap state reset if the day has rolled.

    If ``guard_state.g3_daily_cap.calendar_day_et`` differs from
    ``current_et_day``, return a new GuardState with the day updated and
    ``unsafe_pings_sent_today`` reset to 0 (cap unchanged). Otherwise return
    the input unchanged.

    Pure function (no mutation of the input).
    """
    if guard_state.g3_daily_cap.calendar_day_et == current_et_day:
        return guard_state
    return GuardState(
        g3_daily_cap=G3DailyCap(
            calendar_day_et=current_et_day,
            unsafe_pings_sent_today=0,
            cap=guard_state.g3_daily_cap.cap,
        ),
    )


# ---------------------------------------------------------------------------
# Individual guards
# ---------------------------------------------------------------------------


def apply_g3(guard_state: GuardState, now_et_day_str: str) -> GuardDecision | None:
    """G-3: hard daily cap on unsafe-class WhatsApp deliveries.

    Returns ``GuardDecision(suppress, "g3")`` if today's count is already at
    the cap. ``None`` otherwise (caller proceeds to G-2).
    """
    cap_state = guard_state.g3_daily_cap
    if (
        cap_state.calendar_day_et == now_et_day_str
        and cap_state.unsafe_pings_sent_today >= cap_state.cap
    ):
        return GuardDecision(decision="suppress", suppressed_by="g3")
    return None


def apply_g2(
    candidate: DivergenceCandidate,
    task_cache: TaskCacheRecord,
    cycle_started_at: datetime,
) -> GuardDecision | None:
    """G-2: suppress unsafe events within 30 min of Felix's last write.

    Reads ``task_cache.tasks[entity_id].felix_last_observed_at``. If the gap
    between ``cycle_started_at`` and that timestamp is ≤
    ``G2_POST_WRITE_SUPPRESSION_MINUTES``, suppress.

    Missing-cache-entry case: no suppression (defaults to safe-to-classify).
    """
    cache_key = str(candidate.vikunja_entity_id)
    entry = task_cache.tasks.get(cache_key)
    if entry is None:
        return None
    try:
        last_observed = _parse_iso_utc(entry.felix_last_observed_at)
    except ValueError:
        return None
    gap = cycle_started_at - last_observed
    if gap <= timedelta(minutes=G2_POST_WRITE_SUPPRESSION_MINUTES):
        return GuardDecision(decision="suppress", suppressed_by="g2")
    return None


def apply_g1(
    candidate: DivergenceCandidate,
    recent_events: list[dict],
) -> GuardDecision | None:
    """G-1: suppress unsafe events matching a (layer, entity, field) stem
    seen in the last 24h.

    Looks at ``recent_events`` — a list of conflict-event dicts from the
    JSONL log — for any row whose ``event_id`` starts with the candidate's
    stem AND whose ``delivery_status`` is ``delivered`` or ``not_unsafe``
    (auto_resolved). Suppressed/error rows do NOT count toward dedup.

    The caller (emit phase) is responsible for filtering ``recent_events``
    to the 24h window before calling.
    """
    stem = event_id_stem(
        layer="status_and_task",
        entity_id=candidate.vikunja_entity_id,
        diff_field=candidate.field,
    )
    for ev in recent_events:
        ev_id = ev.get("event_id")
        if not isinstance(ev_id, str) or not ev_id.startswith(stem):
            continue
        status = ev.get("delivery_status")
        if status in ("delivered", "not_unsafe"):
            return GuardDecision(decision="suppress", suppressed_by="g1")
    return None


# ---------------------------------------------------------------------------
# apply_guards (the order is the contract)
# ---------------------------------------------------------------------------


def apply_guards(
    candidate: DivergenceCandidate,
    task_cache: TaskCacheRecord,
    guard_state: GuardState,
    recent_events: list[dict],
    cycle_started_at: datetime,
    now_et_day_str: str,
) -> GuardDecision:
    """Apply G-3 → G-2 → G-1 in order; return the first suppression or
    ``approve`` if none fire.

    The order is part of the contract per ``contracts/cycle-pipeline.md``:
    G-3 first (cheapest check), then G-2 (cache lookup), then G-1 (log scan).
    """
    decision = apply_g3(guard_state, now_et_day_str)
    if decision is not None:
        return decision
    decision = apply_g2(candidate, task_cache, cycle_started_at)
    if decision is not None:
        return decision
    decision = apply_g1(candidate, recent_events)
    if decision is not None:
        return decision
    return _APPROVE


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_iso_utc(value: str) -> datetime:
    """Parse a Vikunja/Felix ISO-8601 UTC string. Handles trailing 'Z'."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
