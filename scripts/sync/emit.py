"""Conflict-event emit phase for the reconciliation driver (WP04 / T015).

Phase 4 of the 6-phase cycle. Orchestrates: deterministic event_id
computation → guard application (G-3 → G-2 → G-1 per WP03) → JSONL append
→ optional WhatsApp delivery.

Contract: kitty-specs/.../contracts/conflict-event-schema.md (15-field row)
         + kitty-specs/.../contracts/cycle-pipeline.md § Phase 4 (orchestration)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.sync.classify import (
    CLASS_AUTO_RESOLVED,
    CLASS_UNSAFE,
    ClassifiedConflict,
)
from scripts.sync.guards import apply_guards
from scripts.sync.send_whatsapp import (
    REDACTED_LITERAL,
    SendResult,
    format_message,
)
from scripts.sync.state import (
    G3DailyCap,
    GuardState,
    TaskCacheRecord,
    append_jsonl,
)


SCHEMA_VERSION: int = 1
LAYER_STATUS_AND_TASK: str = "status_and_task"
G1_LOOKBACK_HOURS: int = 24


# Delivery status enum values.
DS_DELIVERED: str = "delivered"
DS_NOT_UNSAFE: str = "not_unsafe"
DS_SUPPRESSED_G1: str = "suppressed_by_g1"
DS_SUPPRESSED_G2: str = "suppressed_by_g2"
DS_SUPPRESSED_G3: str = "suppressed_by_g3"
DS_ERROR: str = "error"

_DELIVERY_STATUS_VALUES: frozenset[str] = frozenset({
    DS_DELIVERED,
    DS_NOT_UNSAFE,
    DS_SUPPRESSED_G1,
    DS_SUPPRESSED_G2,
    DS_SUPPRESSED_G3,
    DS_ERROR,
})

_CLASS_VALUES: frozenset[str] = frozenset({
    CLASS_AUTO_RESOLVED,
    CLASS_UNSAFE,
})


# ---------------------------------------------------------------------------
# ConflictEvent (15 fields per conflict-event-schema.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConflictEvent:
    """One conflict-event row. 15 fields per the schema contract."""

    # Identity (4)
    event_id: str
    schema_version: int
    tick_id: str
    ts_observed_utc: str
    # Subject (3)
    layer: str
    vikunja_entity_id: int
    diff_field: str
    # Values (2)
    vikunja_value: Any
    felix_cached_value: Any
    # Classification (2)
    class_: str
    unsafe_reasons: tuple[str, ...]
    # Routing (2)
    router_route_set: tuple[str, ...]
    delivery_status: str
    # Diagnostics (2)
    vikunja_updated_at: str
    delivery_error: str | None


# ---------------------------------------------------------------------------
# event_id (deterministic)
# ---------------------------------------------------------------------------


def compute_event_id(
    layer: str,
    entity_id: int,
    field: str,
    ts_observed_utc: str,
    vikunja_value: Any,
) -> str:
    """Deterministic 16-char hex event identifier.

    ``sha256(layer | entity_id | field | ts_observed_utc | canonical_json(value))[:16]``

    Re-runs with identical inputs produce identical event_id, enabling
    idempotent JSONL appends and stable G-1 dedup matching.
    """
    canonical_value = json.dumps(vikunja_value, sort_keys=True, separators=(",", ":"))
    payload = f"{layer}|{entity_id}|{field}|{ts_observed_utc}|{canonical_value}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


_HEX_RE_CHARS = set("0123456789abcdef")


def validate_event(event: ConflictEvent) -> None:
    """Verify the row meets the schema contract.

    Raises OSError on the first failure. The caller treats this as a cycle
    error (exit code 2 per spec FR-010) — an invalid event must NOT land in
    the log.
    """
    if not isinstance(event.event_id, str) or len(event.event_id) != 16:
        raise OSError(f"event_id must be a 16-char string (got {event.event_id!r})")
    if any(ch not in _HEX_RE_CHARS for ch in event.event_id):
        raise OSError(f"event_id must be lowercase hex (got {event.event_id!r})")
    if event.schema_version != SCHEMA_VERSION:
        raise OSError(
            f"schema_version must be {SCHEMA_VERSION} (got {event.schema_version})"
        )
    if event.class_ not in _CLASS_VALUES:
        raise OSError(f"class_ {event.class_!r} not in {sorted(_CLASS_VALUES)}")
    if event.delivery_status not in _DELIVERY_STATUS_VALUES:
        raise OSError(
            f"delivery_status {event.delivery_status!r} not in "
            f"{sorted(_DELIVERY_STATUS_VALUES)}"
        )
    if event.delivery_status == DS_ERROR and event.delivery_error is None:
        raise OSError("delivery_status='error' requires delivery_error to be non-null")
    if event.delivery_status != DS_ERROR and event.delivery_error is not None:
        raise OSError(
            f"delivery_status={event.delivery_status!r} requires delivery_error "
            f"to be None (got {event.delivery_error!r})"
        )


# ---------------------------------------------------------------------------
# Row serialization
# ---------------------------------------------------------------------------


def event_to_row(event: ConflictEvent) -> dict:
    """Return the event as a JSON-serializable dict (preserves field names)."""
    return {
        "event_id": event.event_id,
        "schema_version": event.schema_version,
        "tick_id": event.tick_id,
        "ts_observed_utc": event.ts_observed_utc,
        "layer": event.layer,
        "vikunja_entity_id": event.vikunja_entity_id,
        "diff_field": event.diff_field,
        "vikunja_value": event.vikunja_value,
        "felix_cached_value": event.felix_cached_value,
        "class": event.class_,
        "unsafe_reasons": list(event.unsafe_reasons),
        "router_route_set": list(event.router_route_set),
        "delivery_status": event.delivery_status,
        "vikunja_updated_at": event.vikunja_updated_at,
        "delivery_error": event.delivery_error,
    }


# ---------------------------------------------------------------------------
# read_recent_events (G-1 substrate)
# ---------------------------------------------------------------------------


def read_recent_events(
    jsonl_path: Path,
    now_utc: datetime,
    lookback_hours: int = G1_LOOKBACK_HOURS,
) -> list[dict]:
    """Load conflict-event rows within the lookback window.

    Returns rows as raw dicts (not ConflictEvent) since this slice is consumed
    by ``guards.apply_g1`` which reads ``event_id`` and ``delivery_status`` only.
    Defensive: skips malformed lines.
    """
    if not jsonl_path.exists():
        return []
    cutoff = now_utc - timedelta(hours=lookback_hours)
    out: list[dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = row.get("ts_observed_utc")
            if not isinstance(ts, str):
                continue
            try:
                observed = _parse_iso_utc(ts)
            except ValueError:
                continue
            if observed >= cutoff:
                out.append(row)
    return out


# ---------------------------------------------------------------------------
# build_event
# ---------------------------------------------------------------------------


def build_event(
    *,
    classified: ClassifiedConflict,
    tick_id: str,
    ts_observed_utc: str,
    delivery_status: str,
    delivery_error: str | None,
) -> ConflictEvent:
    """Construct a ConflictEvent from a ClassifiedConflict + delivery outcome."""
    cand = classified.candidate
    event_id = compute_event_id(
        layer=LAYER_STATUS_AND_TASK,
        entity_id=cand.vikunja_entity_id,
        field=cand.field,
        ts_observed_utc=ts_observed_utc,
        vikunja_value=cand.vikunja_value,
    )
    router_route_set: tuple[str, ...] = (
        ("whatsapp",) if classified.class_ == CLASS_UNSAFE else ()
    )
    return ConflictEvent(
        event_id=event_id,
        schema_version=SCHEMA_VERSION,
        tick_id=tick_id,
        ts_observed_utc=ts_observed_utc,
        layer=LAYER_STATUS_AND_TASK,
        vikunja_entity_id=cand.vikunja_entity_id,
        diff_field=cand.field,
        vikunja_value=cand.vikunja_value,
        felix_cached_value=cand.felix_cached_value,
        class_=classified.class_,
        unsafe_reasons=classified.unsafe_reasons,
        router_route_set=router_route_set,
        delivery_status=delivery_status,
        vikunja_updated_at=cand.vikunja_updated_at,
        delivery_error=delivery_error,
    )


# ---------------------------------------------------------------------------
# Privacy redaction
# ---------------------------------------------------------------------------


def _redact_event(event: ConflictEvent) -> ConflictEvent:
    """Replace value-bearing fields with the redacted literal."""
    return ConflictEvent(
        event_id=event.event_id,
        schema_version=event.schema_version,
        tick_id=event.tick_id,
        ts_observed_utc=event.ts_observed_utc,
        layer=event.layer,
        vikunja_entity_id=event.vikunja_entity_id,
        diff_field=REDACTED_LITERAL,
        vikunja_value=REDACTED_LITERAL,
        felix_cached_value=REDACTED_LITERAL,
        class_=event.class_,
        unsafe_reasons=event.unsafe_reasons,
        router_route_set=event.router_route_set,
        delivery_status=event.delivery_status,
        vikunja_updated_at=event.vikunja_updated_at,
        delivery_error=event.delivery_error,
    )


# ---------------------------------------------------------------------------
# emit_events (the orchestrator)
# ---------------------------------------------------------------------------


# Type alias for the WhatsApp send callable (matches send_whatsapp.send).
SendCallable = Callable[..., SendResult]


def emit_events(
    *,
    classified_conflicts: list[ClassifiedConflict],
    tick_id: str,
    ts_observed_utc: str,
    jsonl_path: Path,
    task_cache: TaskCacheRecord,
    guard_state: GuardState,
    recent_events: list[dict],
    send_callable: SendCallable,
    recipient: str,
    cycle_started_at: datetime,
    now_et_day_str: str,
    private_project_ids: frozenset[int] = frozenset(),
    task_lookup: dict[int, dict] | None = None,
) -> tuple[list[ConflictEvent], GuardState]:
    """Apply guards + emit conflict events + dispatch WhatsApp deliveries.

    Returns ``(committed_events, updated_guard_state)``.

    Processing order: classified_conflicts sorted by
    ``candidate.vikunja_updated_at`` ascending (stable G-1 behavior on
    multi-field divergences within one cycle).

    On JSONL append failure: raises OSError (cycle error → exit 2 per FR-010).

    ``task_lookup`` is a dict ``task_id → vikunja task payload`` used to
    populate the WhatsApp message's task title. None or missing entries
    fall back to "<unknown task>".
    """
    if task_lookup is None:
        task_lookup = {}

    sorted_conflicts = sorted(
        classified_conflicts,
        key=lambda c: c.candidate.vikunja_updated_at,
    )

    committed: list[ConflictEvent] = []
    g3_count = guard_state.g3_daily_cap.unsafe_pings_sent_today
    g3_cap = guard_state.g3_daily_cap.cap
    g3_day = guard_state.g3_daily_cap.calendar_day_et

    for classified in sorted_conflicts:
        cand = classified.candidate
        is_private = cand.vikunja_entity_id in _private_task_ids(
            task_lookup, private_project_ids
        )

        if classified.class_ == CLASS_AUTO_RESOLVED:
            event = build_event(
                classified=classified,
                tick_id=tick_id,
                ts_observed_utc=ts_observed_utc,
                delivery_status=DS_NOT_UNSAFE,
                delivery_error=None,
            )
            if is_private:
                event = _redact_event(event)
            _commit(event, jsonl_path)
            committed.append(event)
            continue

        # Unsafe path: apply guards using the current g3 count snapshot.
        rolling_guard_state = GuardState(
            g3_daily_cap=G3DailyCap(
                calendar_day_et=g3_day,
                unsafe_pings_sent_today=g3_count,
                cap=g3_cap,
            ),
        )
        decision = apply_guards(
            candidate=cand,
            task_cache=task_cache,
            guard_state=rolling_guard_state,
            recent_events=recent_events,
            cycle_started_at=cycle_started_at,
            now_et_day_str=now_et_day_str,
        )

        if decision.decision == "suppress":
            status_map = {
                "g1": DS_SUPPRESSED_G1,
                "g2": DS_SUPPRESSED_G2,
                "g3": DS_SUPPRESSED_G3,
            }
            status = status_map[decision.suppressed_by]
            event = build_event(
                classified=classified,
                tick_id=tick_id,
                ts_observed_utc=ts_observed_utc,
                delivery_status=status,
                delivery_error=None,
            )
            if is_private:
                event = _redact_event(event)
            _commit(event, jsonl_path)
            committed.append(event)
            continue

        # Approved: deliver via WhatsApp.
        task = task_lookup.get(cand.vikunja_entity_id, {})
        is_downstream = "uc3_downstream_behavior" in classified.unsafe_reasons
        message = format_message(
            diff_field=cand.field,
            vikunja_value=cand.vikunja_value,
            felix_cached_value=cand.felix_cached_value,
            vikunja_entity_id=cand.vikunja_entity_id,
            task_title=task.get("title"),
            is_downstream=is_downstream,
            is_private=is_private,
        )
        send_result = send_callable(message=message, recipient=recipient)
        if send_result.success:
            event = build_event(
                classified=classified,
                tick_id=tick_id,
                ts_observed_utc=ts_observed_utc,
                delivery_status=DS_DELIVERED,
                delivery_error=None,
            )
            g3_count += 1  # only on successful delivery, per spec FR-007
        else:
            event = build_event(
                classified=classified,
                tick_id=tick_id,
                ts_observed_utc=ts_observed_utc,
                delivery_status=DS_ERROR,
                delivery_error=send_result.stderr or f"exit={send_result.exit_code}",
            )
        if is_private:
            event = _redact_event(event)
        _commit(event, jsonl_path)
        committed.append(event)

    updated_state = GuardState(
        g3_daily_cap=G3DailyCap(
            calendar_day_et=g3_day,
            unsafe_pings_sent_today=g3_count,
            cap=g3_cap,
        ),
    )
    return committed, updated_state


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _commit(event: ConflictEvent, jsonl_path: Path) -> None:
    """Validate then append the event row. Raises OSError on validation
    failure (caller treats as cycle error)."""
    validate_event(event)
    append_jsonl(jsonl_path, event_to_row(event))


def _private_task_ids(
    task_lookup: dict[int, dict],
    private_project_ids: frozenset[int],
) -> frozenset[int]:
    """Subset of task IDs in task_lookup whose project_id is private."""
    if not private_project_ids:
        return frozenset()
    return frozenset(
        tid
        for tid, t in task_lookup.items()
        if t.get("project_id") in private_project_ids
    )


def _parse_iso_utc(value: str) -> datetime:
    """Parse a Vikunja/Felix ISO-8601 UTC string. Handles trailing 'Z'."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
