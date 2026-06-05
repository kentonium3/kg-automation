# Data Model: Felix-Vikunja Sync — Project Layer and URL Config

**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-06-05

This document defines the entities introduced and modified by #520. The bulk of the data model from #518/#519 stays intact; this document focuses on what's new or changed.

---

## NEW entities

### `FetchedSnapshot` (`scripts/sync/fetch.py`)

```python
@dataclass(frozen=True)
class FetchedSnapshot:
    """Output of one full-poll fetch phase.

    Replaces FetchedDelta. Carries the complete current state of Vikunja's
    task and project layers as observed at fetched_at_utc. Downstream consumers
    (diff, classify) treat this as the source of truth for the current cycle.
    """
    tasks: tuple[dict, ...]              # full task list; every task record returned by GET /tasks/all
    projects: dict[int, dict]            # full project list keyed by project_id; from GET /projects
    vikunja_version: str | None          # carried over from FetchedDelta; informational
    fetched_at_utc: str                  # ISO-8601 UTC; cycle-time anchor
```

**Replaces**: `FetchedDelta` (same module). `FetchedDelta` is removed.

### `PerLayerSummary` (`scripts/sync/state.py`)

```python
@dataclass(frozen=True)
class PerLayerSummary:
    """Per-layer summary of a single cycle's outcomes."""
    polled_at_utc: str                   # when the layer's HTTP call entered
    added: int                            # in_vikunja_only count (new in cache this cycle)
    removed: int                          # in_cache_only count (deleted this cycle)
    updated: int                          # in_both with field changes (tasks) or rename/archive (projects)
    errors: tuple[str, ...]              # structured error tokens (R-009 + D-004 vocabulary)
```

### `LayerSummary` (`scripts/sync/state.py`)

```python
@dataclass(frozen=True)
class LayerSummary:
    """Aggregate of both layers' summaries for the cycle."""
    task_layer: PerLayerSummary
    project_layer: PerLayerSummary
```

**Replaces**: `LayerPointerSnapshot` (and the `layer_pointers` field in `last-tick.json`).

### `ProjectDiffEvent` (`scripts/sync/diff.py`)

```python
EventType = Literal[
    "project_added",
    "project_removed",
    "project_renamed",
    "project_archived",
    "project_unarchived",
]

@dataclass(frozen=True)
class ProjectDiffEvent:
    """A single project-layer change observed in a cycle.

    Project layer is audit/discovery only (spec C-005). These events flow to
    the cycle's log only — no conflict-event emission, no WhatsApp ping.
    """
    type: EventType
    project_id: int
    title: str | None                    # for renamed: new title; for added: current title; for removed: last-known title
    is_archived: bool | None             # for archived/unarchived events
    detected_at_utc: str
```

### `TaskDeletedEvent` (in `scripts/habits/state/habits-history.jsonl`)

JSON-Lines record appended on confirmed task deletion (per FR-003).

```jsonc
{
  "event_type": "task_deleted",            // event-type discriminator (matches habits-history conventions)
  "task_id": 42,
  "title": "Wake at 5:00 AM",              // last-known title from cache before removal
  "detected_at_utc": "2026-06-05T20:00:00Z",
  "schema_version": 1
}
```

**Format details**:
- Matches existing event format in `habits-history.jsonl` (single-line JSON per event, schema_version field present, ISO-8601 UTC timestamps).
- The exact field set is finalized in the WP that implements deletion cleanup (per R-001 D-003), referencing existing event records in the deployed JSONL.

### `VikunjaConfigError` (`scripts/common/vikunja_config.py`)

```python
class VikunjaConfigError(RuntimeError):
    """Raised when neither VIKUNJA_BASE_URL nor the canonical config file is available.

    The error message names both expected sources so the operator can fix one.
    """
```

---

## MODIFIED entities

### `ProjectCacheEntry` (`scripts/sync/state.py`)

**Current schema** (#518):
```python
@dataclass(frozen=True)
class ProjectCacheEntry:
    title: str
    is_archived: bool
```

**Modified schema** (#520, pending WP01 design per R-001 D-002):
- May add `owner_id: int | None` to support future use cases. Decision deferred to WP01.
- All existing consumers must accept additional fields gracefully.

The schema_version on `ProjectCacheRecord` increments to 2 if the entry shape changes; existing project-cache.json on office2 will be migrated automatically by the cycle's next write (read-with-defaults, write-canonical).

### `PerTickHealthRecord` (`scripts/sync/state.py`)

**Current schema** (#518) — has a `layer_pointers: dict[str, LayerPointerSnapshot]` field.

**Modified schema** (#520) — replace `layer_pointers` with `layer_summary: LayerSummary`. The `LayerPointerSnapshot` dataclass is deleted (no longer referenced).

The on-disk `last-tick.json` schema_version increments accordingly; the reader code handles both schema_version 1 (old `layer_pointers`) and schema_version 2 (new `layer_summary`) during the first cycle after deployment, then writes only schema_version 2.

### `TaskCacheRecord` and `TaskCacheEntry` (`scripts/sync/state.py`)

**Unchanged structurally**. The schema for cache entries stays identical to #519's contract; only the update mechanism changes (delta-apply → set-diff). NFR-004 requires byte-for-byte identical output from the cache-read helpers.

---

## UNCHANGED entities from #518 / #519

- `TaskCacheRecord`, `TaskCacheEntry` — schema stable
- `FreshnessPointer`, `FreshnessLayer` — schema stable (full-poll updates `last_polled_utc` per cycle, no other change)
- `GuardState`, `G3DailyCap` — guard mechanism unchanged
- `PerTickErrorRecord` — error JSONL record unchanged
- `DivergenceCandidate` (`scripts/sync/diff.py`) — kept as the conflict-event input type for the classify phase
- `TaskCacheView`, `CompletionTimestamps`, `SLATier` (`scripts/common/sync_cache.py`) — the cache-read contract from #519 is preserved
- `MissingTaskError` (`scripts/common/sync_cache.py`) — the exception consumers use to detect deletion is preserved (now triggered by the set-diff removal path instead of the delta-apply absence path)

---

## State files on disk (schema changes)

| File | Current schema | New schema | Migration |
|---|---|---|---|
| `task-cache.json` | v1 | v1 (unchanged) | none |
| `project-cache.json` | v1 | v1 or v2 (depends on ProjectCacheEntry decision) | first-write migration if schema changes |
| `freshness.json` | v1 | v1 (unchanged) | none |
| `guard-state.json` | v1 | v1 (unchanged) | none |
| `last-tick.json` | v1 (`layer_pointers`) | v2 (`layer_summary`) | first-write migration on first cycle post-deploy |
| `last-tick.errors.jsonl` | v1 | v1 (unchanged) | none |
| `conflict-events.jsonl` | v1 | v1 (unchanged) | none |
| `scripts/habits/state/habits-history.jsonl` | v1 (existing event types) | v1 (new event_type "task_deleted" added) | additive only; backward-compatible |

---

## Validation rules

- `FetchedSnapshot.tasks` must be non-None (empty tuple is valid only if Vikunja returned `[]` AND the cache is empty; otherwise → R-009 abort)
- `FetchedSnapshot.projects` must be non-None
- `PerLayerSummary.errors` empty tuple iff the layer succeeded
- `ProjectDiffEvent.detected_at_utc` matches the cycle's `started_at_utc`
- `TaskDeletedEvent.task_id` must be a positive integer
- `get_vikunja_base_url()` return value must match `^https?://[^/]+/api/v1/?$` (basic URL shape validation in the helper)

---

## State transitions

### Per-cycle state evolution (task layer)

```
Phase 0: read task_cache (snapshot at t0)
Phase 1: fetch_full_poll() → FetchedSnapshot (snapshot at t1)
Phase 2: compute_divergences(snapshot, task_cache) →
           in_vikunja_only (additions),
           in_cache_only (deletions),
           in_both with field diffs (updates)
Phase 5: new_task_cache = task_cache + additions - deletions + updates
Phase 5b: for each task_id in in_cache_only: cleanup
Phase 6: write_task_cache(new_task_cache) atomically
```

Cache state transitions are atomic at the file level (write-to-temp + rename).

### Per-cycle state evolution (project layer)

```
Phase 0: read project_cache (snapshot at t0)
Phase 1: fetch_full_poll() → FetchedSnapshot.projects (snapshot at t1)
Phase 2: compute project diff →
           in_vikunja_only (project_added events),
           in_cache_only (project_removed events),
           in_both with title diff (project_renamed),
           in_both with is_archived diff (project_archived/unarchived)
Phase 5: new_project_cache = current projects from snapshot (canonical replacement, NOT merge)
Phase 6: write_project_cache(new_project_cache) atomically
```

Note the asymmetry: tasks keep history-aware merging (because cache entries carry observation metadata like `first_observation_id`). Projects don't carry such metadata, so the new cache is the canonical snapshot from this cycle.
