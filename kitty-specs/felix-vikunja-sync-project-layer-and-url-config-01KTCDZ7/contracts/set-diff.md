# Contract: 3-Way Set Diff Algorithm

**Spec FRs**: FR-001, FR-002, FR-003, FR-004
**Spec Constraints**: C-003, C-004
**Source module**: `scripts/sync/diff.py`

## Definition

Given two collections — a `FetchedSnapshot` (Vikunja's current state) and a `Cache` (Felix's prior state) — the 3-way set diff partitions all observed identifiers into three disjoint sets:

- **`in_vikunja_only`**: identifiers in snapshot but not in cache (new additions)
- **`in_cache_only`**: identifiers in cache but not in snapshot (deletions)
- **`in_both`**: identifiers in both (potential field changes; require field-level comparison)

Each set drives a specific downstream action.

## Task-layer application

**Input**:
- `snapshot_task_ids = {t["id"] for t in snapshot.tasks if isinstance(t.get("id"), int)}`
- `cache_task_ids = set(task_cache.tasks.keys())`

**Partition**:
- `in_vikunja_only = snapshot_task_ids - cache_task_ids` → adds (new tasks)
- `in_cache_only = cache_task_ids - snapshot_task_ids` → deletes (gone from Vikunja)
- `in_both = snapshot_task_ids & cache_task_ids` → candidates for field-level diff

**Field-level diff (for `in_both`)**:
For each task in `in_both`, compare TRACKED_TASK_FIELDS (the same set used in #518's `diff.py:33`). If any tracked field differs, emit a `DivergenceCandidate` for the conflict-event pipeline.

**Privacy filter**:
Tasks with `project_id ∈ private_project_ids` produce no `DivergenceCandidate` rows from `in_both`. However, they ARE eligible for `in_vikunja_only` (new task add) and `in_cache_only` (deletion) handling — those are structural operations that the privacy filter does not gate. (Verify this interpretation in WP01 design; if privacy must also gate structural operations, adjust accordingly.)

## Project-layer application

**Input**:
- `snapshot_project_ids = set(snapshot.projects.keys())`
- `cache_project_ids = {int(pid) for pid in project_cache.projects.keys()}`

**Partition**:
- `in_vikunja_only` → `project_added` events
- `in_cache_only` → `project_removed` events
- `in_both` → check for `title` change → `project_renamed`; check for `is_archived` change → `project_archived` or `project_unarchived`

**Asymmetric cache update**:
Unlike task cache (which preserves observation history), the new project cache is the **canonical snapshot** for the cycle:

```python
new_project_cache = ProjectCacheRecord(
    last_refreshed_utc=ts_observed_utc,
    projects={
        str(pid): ProjectCacheEntry(
            title=str(snapshot.projects[pid].get("title", "<unknown>")),
            is_archived=bool(snapshot.projects[pid].get("is_archived", False)),
        )
        for pid in snapshot.projects
    },
)
```

This is intentional — projects don't have observation-metadata equivalents to tasks' `first_observation_id`.

## Atomicity guarantees

- The set-diff function is **pure**: same inputs always produce the same outputs. No side effects, no I/O, no clock reads.
- Both layers' set-diffs run within the same `compute_divergences` call, against the same `FetchedSnapshot`. There is no chance of cross-layer staleness.
- The cycle's atomic-commit guarantee (Phase 6) ensures that downstream consumers observe both layers' new state together.

## Failure modes (and protections)

- **Empty snapshot, non-empty cache**: per FR-012, the cycle aborts BEFORE the set-diff runs (in Phase 1). The set-diff function trusts that its inputs are valid.
- **Malformed task records** (missing `id` field): excluded from `snapshot_task_ids` via the `isinstance(t.get("id"), int)` filter. They produce no events; if a previously-cached task_id is missing from the snapshot due to malformation (rather than deletion), it will appear in `in_cache_only` and be classified as deleted. This is operator-recoverable (re-running the cycle after Vikunja heals re-creates the cache entry).
- **Type coercion**: `project_cache.projects` keys are strings (JSON deserialization); `snapshot.projects` keys are ints. The function normalizes by converting cache keys to int before set ops.

## Output stability

The function returns deterministic, sorted outputs where set membership matters:

- `divergences` is sorted by `vikunja_entity_id` ascending (matches #518 convention)
- `first_observation_task_ids` and `deleted_task_ids` are returned as sets (caller must accept unordered)
- `project_events` is sorted by `project_id` then `type` (deterministic ordering for test assertions)

## Field-level diff details (TRACKED_TASK_FIELDS)

The fields compared for `in_both` tasks:

```python
TRACKED_TASK_FIELDS = (
    "title",
    "done",
    "done_at",
    "due_date",
    "project_id",
    "labels",
    "repeat_after",
)
```

This set matches #519's `TRACKED_TASK_FIELDS` (verified in research). Per spec FR-008, this set is NOT widened in this mission. If a future mission needs additional fields (e.g., `start_date`, `description`), it must explicitly widen the set in `diff.py` and audit consumers.

## Test contract

Unit tests in `tests/sync/test_diff.py` (rewritten) must cover:

1. **Empty inputs**: empty snapshot + empty cache → empty divergences, empty event sets
2. **Pure additions**: tasks in snapshot, none in cache → all task_ids in `first_observation_task_ids`
3. **Pure deletions**: tasks in cache, none in snapshot → all task_ids in `deleted_task_ids` (note: FR-012 aborts before this in the cycle, but the diff function itself is pure and produces correct outputs)
4. **Pure updates**: same task_ids, different field values → divergence per changed field
5. **Mixed scenario**: 3 added, 2 deleted, 1 updated, 5 unchanged → correct partitioning
6. **Privacy filter**: task in private project does NOT produce divergence from `in_both` but DOES appear in `first_observation_task_ids` / `deleted_task_ids` if applicable
7. **Project-layer add/remove/rename/archive/unarchive**: 5 event types verified
8. **Type coercion**: cache key "42" matches snapshot key 42

Integration tests in `tests/sync/test_cycle_*.py` (unchanged interface, modified fixtures) verify end-to-end behavior with the set-diff in place.
