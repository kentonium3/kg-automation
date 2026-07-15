"""3-way set-diff phase for the reconciliation driver (WP03 / T008).

Phase 2 of the 7-phase cycle. Pure function from (FetchedSnapshot,
TaskCacheRecord, ProjectCacheRecord) to five output streams: task content
changes, first-observation task IDs, deleted task IDs, project diff events,
and a LayerSummary aggregate.

Contract: kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/
contracts/set-diff.md + contracts/cycle-pipeline.md § Phase 2.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from scripts.common import vikunja_refs
from scripts.sync.fetch import FetchedSnapshot
from scripts.sync.state import LayerSummary, PerLayerSummary, ProjectCacheRecord, TaskCacheRecord

# Re-export for backward compatibility — any code that imported these
# from diff.py before WP04 will continue to work.
__all__ = [
    "LayerSummary",
    "PerLayerSummary",
    "DivergenceCandidate",
    "ProjectDiffEvent",
    "compute_divergences",
    "TRACKED_TASK_FIELDS",
    "PRIVATE_PROJECT_IDS",
]


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


# Operator-configurable set of project_ids treated as "private". The default is
# now sourced from the declared Vikunja reference registry (WP01 seam) via
# ``vikunja_refs.private_project_ids()`` — the single declared home for the
# privacy set (finding #4). It is empty today (no private project is
# provisioned), so behavior is identical to the prior bare ``frozenset()``.
# Callers may still override via the function parameter / driver config surface;
# only the DEFAULT source moved onto the seam. Resolved at import time — the
# registry load is a pure, network-free file+JSON read (NFR-001/NFR-003). A
# malformed registry fails loud here (as it should), never silently.
#
# Tasks in private projects produce NO DivergenceCandidate rows from the in_both
# diff path (privacy boundary applied at diff time). Structural operations
# (additions and deletions) are NOT gated by this filter.
PRIVATE_PROJECT_IDS: frozenset[int] = vikunja_refs.private_project_ids()


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
# ProjectDiffEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectDiffEvent:
    """A single project-layer change observed in a cycle.

    Project layer is audit/discovery only (spec C-005). These events flow to
    the cycle's log only — no conflict-event emission, no WhatsApp ping.

    Attributes:
        type: One of "project_added", "project_removed", "project_renamed",
            "project_archived", "project_unarchived".
        project_id: Vikunja project identifier.
        title: For renamed: new title; for added: current title; for removed:
            last-known title from cache. None if not applicable.
        is_archived: For archived/unarchived events; None otherwise.
        detected_at_utc: Cycle's ts_observed_utc value.
    """

    type: str
    project_id: int
    title: str | None
    is_archived: bool | None
    detected_at_utc: str


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
    snapshot: FetchedSnapshot,
    task_cache: TaskCacheRecord,
    project_cache: ProjectCacheRecord,
    ts_observed_utc: str,
    private_project_ids: frozenset[int] = PRIVATE_PROJECT_IDS,
) -> tuple[
    list[DivergenceCandidate],
    set[int],
    set[int],
    list[ProjectDiffEvent],
    LayerSummary,
]:
    """Compute the full set-diff for one cycle. Pure function.

    Args:
        snapshot: The FetchedSnapshot from phase 1. Contains the complete
            current Vikunja task and project state.
        task_cache: Driver's current TaskCacheRecord (Felix's prior state).
        project_cache: Driver's current ProjectCacheRecord (Felix's prior state).
        ts_observed_utc: Cycle's ``started_at_utc`` (ISO-8601 UTC). Used as
            ``detected_at_utc`` on emitted events.
        private_project_ids: Tasks whose ``project_id`` is in this set produce
            no DivergenceCandidate rows (privacy boundary for content events).
            Structural operations (additions and deletions) are NOT filtered.

    Returns:
        A 5-tuple:
          - divergences: list[DivergenceCandidate] — task content changes
            (in_both tasks with changed TRACKED_TASK_FIELDS), sorted by
            vikunja_entity_id ascending.
          - first_observation_task_ids: set[int] — task IDs new in this cycle
            (in_vikunja_only). Includes private tasks.
          - deleted_task_ids: set[int] — task IDs removed from Vikunja
            (in_cache_only). Includes private tasks.
          - project_events: list[ProjectDiffEvent] — project-layer changes,
            sorted by (project_id, type).
          - layer_summary: LayerSummary — per-layer aggregate counts.

    Pure function. No I/O.
    """
    # -----------------------------------------------------------------------
    # Task layer — 3-way set partition
    # -----------------------------------------------------------------------
    snapshot_task_ids: set[int] = {
        t["id"] for t in snapshot.tasks if isinstance(t.get("id"), int)
    }
    cache_task_ids: set[int] = set(int(k) for k in task_cache.tasks.keys())

    in_vikunja_only: set[int] = snapshot_task_ids - cache_task_ids  # additions
    in_cache_only: set[int] = cache_task_ids - snapshot_task_ids     # deletions
    in_both: set[int] = snapshot_task_ids & cache_task_ids           # potential updates

    # Build a lookup from the snapshot for the in_both comparison.
    snapshot_by_id: dict[int, dict] = {
        t["id"]: t
        for t in snapshot.tasks
        if isinstance(t.get("id"), int)
    }

    divergences: list[DivergenceCandidate] = []
    for task_id in in_both:
        task = snapshot_by_id[task_id]

        # Privacy boundary: content events only. Private tasks in in_both
        # produce no DivergenceCandidate rows, but they ARE included in
        # in_vikunja_only / in_cache_only if applicable.
        if task.get("project_id") in private_project_ids:
            continue

        cache_key = str(task_id)
        cache_entry = task_cache.tasks.get(cache_key)
        if cache_entry is None:
            # Defensive: key should exist (it's in in_both), but guard anyway.
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

    # Sort divergences by task ID ascending (deterministic output).
    divergences.sort(key=lambda c: (c.vikunja_entity_id, c.field))

    first_observation_task_ids: set[int] = in_vikunja_only
    deleted_task_ids: set[int] = in_cache_only

    # -----------------------------------------------------------------------
    # Project layer — 3-way set partition
    # -----------------------------------------------------------------------
    snapshot_project_ids: set[int] = set(snapshot.projects.keys())
    cache_project_ids: set[int] = {
        int(pid) for pid in project_cache.projects.keys()
    }

    proj_in_vikunja_only: set[int] = snapshot_project_ids - cache_project_ids
    proj_in_cache_only: set[int] = cache_project_ids - snapshot_project_ids
    proj_in_both: set[int] = snapshot_project_ids & cache_project_ids

    project_events: list[ProjectDiffEvent] = []

    for pid in proj_in_vikunja_only:
        proj = snapshot.projects[pid]
        project_events.append(
            ProjectDiffEvent(
                type="project_added",
                project_id=pid,
                title=str(proj.get("title", "<unknown>")),
                is_archived=None,
                detected_at_utc=ts_observed_utc,
            )
        )

    for pid in proj_in_cache_only:
        cache_entry = project_cache.projects.get(str(pid))
        last_known_title = cache_entry.title if cache_entry is not None else None
        project_events.append(
            ProjectDiffEvent(
                type="project_removed",
                project_id=pid,
                title=last_known_title,
                is_archived=None,
                detected_at_utc=ts_observed_utc,
            )
        )

    for pid in proj_in_both:
        snap_proj = snapshot.projects[pid]
        cache_entry = project_cache.projects.get(str(pid))
        if cache_entry is None:
            continue

        snap_title = str(snap_proj.get("title", "<unknown>"))
        cache_title = cache_entry.title
        if snap_title != cache_title:
            project_events.append(
                ProjectDiffEvent(
                    type="project_renamed",
                    project_id=pid,
                    title=snap_title,
                    is_archived=None,
                    detected_at_utc=ts_observed_utc,
                )
            )

        snap_archived = bool(snap_proj.get("is_archived", False))
        cache_archived = cache_entry.is_archived
        if snap_archived != cache_archived:
            event_type = "project_archived" if snap_archived else "project_unarchived"
            project_events.append(
                ProjectDiffEvent(
                    type=event_type,
                    project_id=pid,
                    title=None,
                    is_archived=snap_archived,
                    detected_at_utc=ts_observed_utc,
                )
            )

    # Sort project events by (project_id, type) for deterministic output.
    project_events.sort(key=lambda e: (e.project_id, e.type))

    # -----------------------------------------------------------------------
    # LayerSummary aggregate counts
    # -----------------------------------------------------------------------
    # Count distinct tasks with at least one field divergence (not field-level rows).
    tasks_with_changes = len({c.vikunja_entity_id for c in divergences})
    task_layer_summary = PerLayerSummary(
        polled_at_utc=snapshot.fetched_at_utc,
        added=len(first_observation_task_ids),
        removed=len(deleted_task_ids),
        updated=tasks_with_changes,
        errors=(),
    )
    project_layer_summary = PerLayerSummary(
        polled_at_utc=snapshot.fetched_at_utc,
        added=sum(1 for e in project_events if e.type == "project_added"),
        removed=sum(1 for e in project_events if e.type == "project_removed"),
        updated=sum(
            1 for e in project_events
            if e.type in {"project_renamed", "project_archived", "project_unarchived"}
        ),
        errors=(),
    )
    layer_summary = LayerSummary(
        task_layer=task_layer_summary,
        project_layer=project_layer_summary,
    )

    return (
        divergences,
        first_observation_task_ids,
        deleted_task_ids,
        project_events,
        layer_summary,
    )
