"""Value-comparison diff phase for the reconciliation driver (WP02 / T007).

Phase 2 of the 6-phase cycle. Pure function from (FetchedDelta, TaskCacheRecord)
to a list of DivergenceCandidate tuples for the downstream classify phase.

Contract: kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/
contracts/cycle-pipeline.md § Phase 2.

Research finding (research.md § Unknown 3): Vikunja v0.24.6 returns
``updated_by: null`` on tasks. UC-1/UC-2 authorship is inferred from cache
divergence — the cache is the authoritative "what Felix expected" reference.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from scripts.sync.fetch import FetchedDelta
from scripts.sync.state import TaskCacheRecord


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


TRACKED_TASK_FIELDS: frozenset[str] = frozenset({
    "title",
    "done",
    "due_date",
    "project_id",
    "repeat_after",
    "repeat_mode",
    "labels",
})


# Operator-configurable set of project_ids treated as "private". Default empty;
# downstream WPs may override via the driver's config surface. Tasks in these
# projects produce NO DivergenceCandidate rows from this phase (privacy
# boundary applied at diff time).
PRIVATE_PROJECT_IDS: frozenset[int] = frozenset()


# ---------------------------------------------------------------------------
# DivergenceCandidate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DivergenceCandidate:
    """One (task, field) pair whose Vikunja value differs from the cache."""

    vikunja_entity_id: int
    field: str
    vikunja_value: Any
    felix_cached_value: Any
    vikunja_updated_at: str
    ts_observed_utc: str


# ---------------------------------------------------------------------------
# Canonical normalization
# ---------------------------------------------------------------------------


_DATETIME_FIELDS: frozenset[str] = frozenset({"due_date"})
_LIST_FIELDS: frozenset[str] = frozenset({"labels"})

_ISO_FRACTIONAL_RE = re.compile(r"^(.*?)(\.\d+)([Zz]|[+-]\d{2}:?\d{2})$")


def _normalize_datetime(value: Any) -> Any:
    """Normalize an ISO-8601 string for compare.

    Strips fractional seconds and normalizes the trailing offset to ``Z``. Vikunja
    sometimes returns ``2026-06-04T17:00:00.000000Z``; Felix's cache may have
    ``2026-06-04T17:00:00Z`` from a prior canonical write. Both must compare
    equal.

    Non-string values pass through unchanged.
    """
    if not isinstance(value, str):
        return value
    m = _ISO_FRACTIONAL_RE.match(value)
    if m:
        prefix, _frac, _offset = m.groups()
        return prefix + "Z"
    # Already canonical or unrecognized; return as-is.
    return value


def _normalize_list(value: Any) -> Any:
    """Sort a list of dicts by ``id`` for order-insensitive compare.

    Non-list values pass through unchanged. Items without an ``id`` key sort
    last (deterministic by JSON representation).
    """
    if not isinstance(value, list):
        return value

    def _sort_key(item):
        if isinstance(item, dict) and "id" in item:
            return (0, item["id"])
        return (1, json.dumps(item, sort_keys=True))

    return sorted(value, key=_sort_key)


def _canonicalize(field: str, value: Any) -> Any:
    """Apply per-field canonical normalization before compare."""
    if field in _DATETIME_FIELDS:
        return _normalize_datetime(value)
    if field in _LIST_FIELDS:
        return _normalize_list(value)
    return value


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def compute_divergences(
    delta: FetchedDelta,
    task_cache: TaskCacheRecord,
    ts_observed_utc: str,
    private_project_ids: frozenset[int] = PRIVATE_PROJECT_IDS,
) -> tuple[list[DivergenceCandidate], list[int]]:
    """Compute divergences between Vikunja delta and Felix's cache.

    Args:
        delta: The FetchedDelta from phase 1.
        task_cache: Driver's current TaskCacheRecord.
        ts_observed_utc: Cycle's ``started_at_utc`` (ISO-8601 UTC).
        private_project_ids: Tasks whose ``project_id`` is in this set produce
            no DivergenceCandidate rows (privacy boundary).

    Returns:
        ``(divergences, first_observation_ids)`` where ``first_observation_ids``
        is the list of integer task IDs that were NOT in the cache (signalling
        the update phase to create a fresh cache entry without classify/emit).

    Pure function. No I/O.
    """
    divergences: list[DivergenceCandidate] = []
    first_observations: list[int] = []

    for task in delta.tasks:
        task_id = task.get("id")
        if not isinstance(task_id, int):
            # Defensive: skip malformed entries; do not abort the cycle.
            continue

        # Privacy boundary applied at diff time: private tasks produce no
        # divergences (their cache entry has empty ``fields`` anyway).
        if task.get("project_id") in private_project_ids:
            continue

        cache_key = str(task_id)
        cache_entry = task_cache.tasks.get(cache_key)
        if cache_entry is None:
            first_observations.append(task_id)
            continue

        cached_fields = cache_entry.fields
        for field_name in TRACKED_TASK_FIELDS:
            vikunja_raw = task.get(field_name)
            cached_raw = cached_fields.get(field_name)
            vikunja_canonical = _canonicalize(field_name, vikunja_raw)
            cached_canonical = _canonicalize(field_name, cached_raw)
            if vikunja_canonical == cached_canonical:
                continue
            divergences.append(
                DivergenceCandidate(
                    vikunja_entity_id=task_id,
                    field=field_name,
                    vikunja_value=vikunja_raw,
                    felix_cached_value=cached_raw,
                    vikunja_updated_at=str(task.get("updated") or ""),
                    ts_observed_utc=ts_observed_utc,
                )
            )

    return divergences, first_observations
