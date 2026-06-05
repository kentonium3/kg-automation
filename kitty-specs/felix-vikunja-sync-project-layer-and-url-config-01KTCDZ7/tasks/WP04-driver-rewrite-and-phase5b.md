---
work_package_id: WP04
title: Driver Rewrite (state.py + cycle.py) and Phase 5b Deletion-Cleanup
dependencies:
- WP02
- WP03
requirement_refs:
- FR-001
- FR-003
- FR-004
- FR-005
- FR-009
- FR-012
- NFR-001
- NFR-002
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
- T016
- T017
history: []
authoritative_surface: scripts/sync/cycle.py
execution_mode: code_change
owned_files:
- scripts/sync/state.py
- scripts/sync/cycle.py
- tests/sync/test_state.py
- tests/sync/test_cycle*.py
tags: []
agent: "claude:sonnet:implementer:implementer"
shell_pid: "83870"
---

# WP04 — Driver Rewrite + Phase 5b Deletion-Cleanup

## Objective

Rewrite the reconciliation driver's state schema and cycle orchestration to deliver the full-poll + 3-way set diff model end-to-end. Wires together WP02's cleanup helpers and WP03's fetch_full_poll + compute_divergences. Adds Phase 5b deletion-cleanup orchestration. Replaces `LayerPointerSnapshot` (incremental-poll artifact) with `LayerSummary` (full-poll per-layer aggregate).

This is the largest WP in the mission. Reviewer fatigue is a known risk; the prompt is structured to make the per-phase changes auditable.

## Context

#518 shipped a working 6-phase cycle (`preamble → fetch → diff → classify → emit → update → complete`). #520 changes:

- **Phase 1 (fetch)**: replace `fetch_delta(...)` with `fetch_full_poll(...)` from WP03
- **Phase 2 (diff)**: replace existing `compute_divergences` call with WP03's new 5-tuple signature
- **Phase 5 (update)**: replace `_apply_cache_updates` (delta-apply) with set-diff-based update; replace `_apply_project_updates` (merge-only) with canonical-snapshot replacement
- **Phase 5b (NEW)**: deletion-cleanup orchestration using WP02's `prune_schedule_yaml` + `append_task_deleted_event`
- **Phase 6 (complete)**: write `PerTickHealthRecord` with `LayerSummary` instead of `layer_pointers`

`scripts/sync/state.py` evolves: `PerLayerSummary` + `LayerSummary` dataclasses added, `LayerPointerSnapshot` removed, `PerTickHealthRecord` field swapped.

Phases 3 (classify) and 4 (emit) are unchanged — they consume the same `DivergenceCandidate` shape, which WP03 preserves.

## Implementation guidance

### Subtask T011: state.py — add LayerSummary types; remove LayerPointerSnapshot; update PerTickHealthRecord

**Purpose**: schema evolution in the state module.

**Steps**:

1. **Add `PerLayerSummary` and `LayerSummary` dataclasses** to `scripts/sync/state.py`:

   ```python
   @dataclass(frozen=True)
   class PerLayerSummary:
       """Per-layer summary of a single cycle's outcomes."""
       polled_at_utc: str
       added: int = 0
       removed: int = 0
       updated: int = 0
       errors: tuple[str, ...] = ()


   @dataclass(frozen=True)
   class LayerSummary:
       """Aggregate of both layers' summaries for one cycle."""
       task_layer: PerLayerSummary
       project_layer: PerLayerSummary
   ```

2. **Remove `LayerPointerSnapshot`** dataclass (currently `state.py:122`).

3. **Update `PerTickHealthRecord`** to swap `layer_pointers` field for `layer_summary`:

   ```python
   @dataclass(frozen=True)
   class PerTickHealthRecord:
       tick_id: str
       started_at_utc: str
       completed_at_utc: str
       duration_ms: int
       cadence_seconds: int
       layer_summary: LayerSummary           # REPLACED — was layer_pointers
       events_emitted: dict[str, int]
       cycle_error: str | None
       vikunja_version_seen: str | None
   ```

4. **Update `write_per_tick_health`** to serialize `layer_summary` (nested dict) instead of `layer_pointers`. Bump the on-disk schema version to 2 if the existing writer uses schema_version. Verify the on-disk JSON shape:

   ```json
   {
     "schema_version": 2,
     "layer_summary": {
       "task_layer": {"polled_at_utc": "...", "added": 0, "removed": 0, "updated": 0, "errors": []},
       "project_layer": {"polled_at_utc": "...", "added": 0, "removed": 0, "updated": 0, "errors": []}
     },
     ...
   }
   ```

5. **`read_last_tick`** (if exists) handles both schema_version 1 and 2 during the transition — but production cycles after #520 always write v2. If `read_last_tick` doesn't exist (no reader from this module), skip this step.

**Files**: `scripts/sync/state.py` (substantial change to the type system)

**Validation**:
- [ ] `PerLayerSummary` + `LayerSummary` are defined
- [ ] `LayerPointerSnapshot` is removed (grep returns zero hits in state.py)
- [ ] `PerTickHealthRecord` uses `layer_summary: LayerSummary` field
- [ ] `write_per_tick_health` serializes the new field shape

### Subtask T012: cycle.py Phase 1 — call `fetch_full_poll`

**Purpose**: wire up the new fetcher.

**Steps**:

1. Update import at top of `cycle.py`:

   ```python
   from scripts.sync.fetch import fetch_full_poll, FetchedSnapshot
   # delete the import for fetch_delta / FetchedDelta
   ```

2. **Remove `since_utc` computation** (cycle.py lines 134-136):

   ```python
   # DELETE these lines:
   pointer_before = freshness_before.layers.get(LAYER_STATUS_AND_TASK)
   since_utc = pointer_before.last_polled_utc if pointer_before else EPOCH_ZERO
   layer_pointers_before = {LAYER_STATUS_AND_TASK: since_utc}
   ```

3. **Replace the fetch call** (lines 138-156):

   ```python
   try:
       snapshot = fetch_full_poll(
           token=token,
           base_url=config.api_base_url,
           task_cache_nonempty=bool(task_cache.tasks),
           project_cache_nonempty=bool(project_cache.projects),
       )
   except OSError as e:
       # Parse the structured error token to identify which layer failed
       error_message = str(e)
       return _record_failure(
           config=config,
           tick_id=tick_id,
           started_at_utc=started_at_utc,
           phase="fetch",
           cycle_error=f"step 1 (Vikunja fetch) failed: {error_message}",
           exit_code=1,
           duration_ms=_ms_since(start_perf),
       )
   ```

4. **Remove the `layer_pointers_before` plumbing** — no longer needed under full-poll. Adjust any subsequent references.

5. **Update `CycleResult`** field if it carries `layer_pointers_before` or `layer_pointers_after` — replace with `layer_summary` or remove.

**Files**: `scripts/sync/cycle.py` (Phase 1 section, ~30 line change)

**Validation**:
- [ ] No reference to `since_utc`, `EPOCH_ZERO`, `LAYER_STATUS_AND_TASK` (if used only for the pointer) remains
- [ ] `fetch_full_poll` is called with both cache-non-empty flags
- [ ] Error handling uses the structured token from WP03

### Subtask T013: cycle.py Phase 5 — set-diff based update

**Purpose**: replace delta-apply with set-diff.

**Steps**:

1. **Phase 2 — wire new compute_divergences signature**:

   ```python
   (
       divergences,
       first_observation_task_ids,
       deleted_task_ids,
       project_events,
       layer_summary,
   ) = compute_divergences(
       snapshot=snapshot,
       task_cache=task_cache,
       project_cache=project_cache,
       ts_observed_utc=started_at_utc,
       private_project_ids=PRIVATE_PROJECT_IDS,
   )
   ```

2. **Phase 5 — rewrite `_apply_cache_updates`** to consume the set-diff:

   ```python
   def _apply_cache_updates(
       task_cache: TaskCacheRecord,
       snapshot: FetchedSnapshot,
       first_observation_task_ids: set[int],
       deleted_task_ids: set[int],
       ts_observed_utc: str,
       private_project_ids: frozenset[int],
   ) -> TaskCacheRecord:
       """Apply set-diff outputs to the task cache.

       New tasks (first_observation_task_ids) get TaskCacheEntry records added.
       Deleted tasks (deleted_task_ids) get removed.
       Existing tasks get their tracked fields updated from snapshot.
       """
   ```

   Implementation: iterate snapshot.tasks; for each task_id:
   - If in `first_observation_task_ids`: create a TaskCacheEntry with `first_observation_id=task_id`, `first_observation_utc=ts_observed_utc`
   - Else (in_both): update the existing TaskCacheEntry's tracked fields (preserving observation metadata)
   - Skip task_ids in `deleted_task_ids` (they're not in snapshot anyway)
   - After iteration: exclude any cache_task_ids in `deleted_task_ids` from the new cache

3. **Phase 5 — rewrite `_apply_project_updates`** to canonical replacement:

   ```python
   def _apply_project_updates(
       *,
       snapshot: FetchedSnapshot,
       ts_observed_utc: str,
   ) -> ProjectCacheRecord:
       """Canonical-snapshot replacement of the project cache.

       Per data-model.md, the new project cache is the snapshot's projects
       directly — not a merge of cache and snapshot.
       """
       new_projects = {
           str(pid): ProjectCacheEntry(
               title=str(proj.get("title", "<unknown>")),
               is_archived=bool(proj.get("is_archived", False)),
           )
           for pid, proj in snapshot.projects.items()
       }
       return ProjectCacheRecord(
           last_refreshed_utc=ts_observed_utc,
           projects=new_projects,
       )
   ```

4. Update the Phase 5 try/except block to call both functions with the new signatures.

**Files**: `scripts/sync/cycle.py` (Phase 5 section, ~60 line change)

**Validation**:
- [ ] `_apply_cache_updates` consumes the set-diff outputs
- [ ] `_apply_project_updates` is canonical replacement (no merge)
- [ ] Both functions are pure — no I/O

### Subtask T014: cycle.py Phase 5b — deletion-cleanup orchestration

**Purpose**: implement FR-003's three-action cleanup using WP02 helpers.

**Steps**:

1. **Insert Phase 5b** between Phase 5 (update) and Phase 6 (complete) in `run_cycle`:

   ```python
   # --- Phase 5b: deletion-cleanup ---
   from scripts.sync.cleanup import prune_schedule_yaml, append_task_deleted_event

   habits_history_path = Path("scripts/habits/state/habits-history.jsonl")
   schedule_yaml_path = Path("scripts/habits/migrations/phase3-schedule.yaml")

   for task_id in sorted(deleted_task_ids):
       prior_entry = task_cache.tasks.get(task_id)
       prior_title = prior_entry.title if prior_entry else "<unknown>"
       try:
           append_task_deleted_event(
               task_id=task_id,
               title=prior_title,
               detected_at_utc=started_at_utc,
               path=habits_history_path,
           )
       except OSError as e:
           # Per FR-003: log the error to last-tick.errors.jsonl, skip this task_id, continue
           sys.stderr.write(
               f"[sync cleanup] WARNING: append_task_deleted_event failed for task_id={task_id}: {e}\n"
           )
           # Append to last-tick.errors.jsonl
           append_per_tick_error(
               config.state_dir,
               PerTickErrorRecord(
                   tick_id=tick_id,
                   started_at_utc=started_at_utc,
                   failed_at_utc=vikunja_now_iso(),
                   phase="cleanup_history_log",
                   cycle_error=f"append_task_deleted_event failed for task_id={task_id}: {e}",
                   layer_pointers_unchanged=False,
               ),
           )
           continue   # Skip schedule.yaml prune if history-log failed (atomicity)

       try:
           prune_schedule_yaml(task_id, schedule_yaml_path)
       except (OSError, ValueError) as e:
           sys.stderr.write(
               f"[sync cleanup] WARNING: prune_schedule_yaml failed for task_id={task_id}: {e}\n"
           )
           append_per_tick_error(
               config.state_dir,
               PerTickErrorRecord(
                   tick_id=tick_id,
                   started_at_utc=started_at_utc,
                   failed_at_utc=vikunja_now_iso(),
                   phase="cleanup_schedule_yaml",
                   cycle_error=f"prune_schedule_yaml failed for task_id={task_id}: {e}",
                   layer_pointers_unchanged=False,
               ),
           )
           # Continue — cache removal happens in Phase 6
   ```

2. **Cache removal**: handled by Phase 6's atomic write of the new_task_cache (which excludes deleted task_ids). No separate operation here.

3. **Path constants**: use absolute paths or repo-root-relative paths consistently. Verify the existing code's convention.

**Files**: `scripts/sync/cycle.py` (Phase 5b section, ~50 line add)

**Validation**:
- [ ] Phase 5b runs between Phase 5 and Phase 6
- [ ] Order: history-log first, then schedule.yaml, then cache (via Phase 6)
- [ ] Per-task failure is logged and continues with other task_ids
- [ ] If history-log fails for a given task_id, schedule.yaml is NOT pruned for that task_id (atomicity per data-model.md)

### Subtask T015: cycle.py Phase 6 — write LayerSummary

**Purpose**: serialize LayerSummary instead of layer_pointers.

**Steps**:

1. **Update `write_per_tick_health` call** in Phase 6:

   ```python
   write_per_tick_health(
       config.state_dir,
       PerTickHealthRecord(
           tick_id=tick_id,
           started_at_utc=started_at_utc,
           completed_at_utc=completed_at_utc,
           duration_ms=duration_ms,
           cadence_seconds=config.cadence_seconds,
           layer_summary=layer_summary,        # CHANGED from layer_pointers
           events_emitted=events_count,
           cycle_error=None,
           vikunja_version_seen=snapshot.vikunja_version,
       ),
   )
   ```

2. **Update `CycleResult`** field if it carries `layer_pointers_after` — replace with `layer_summary` or remove.

3. **Update `_record_failure`** to populate `layer_summary` with the errors from the failed layer (e.g., `task_layer.errors = ("vikunja_unreachable",)` on a fetch failure).

**Files**: `scripts/sync/cycle.py` (Phase 6 section, ~20 line change)

**Validation**:
- [ ] `PerTickHealthRecord` constructor uses `layer_summary` field
- [ ] `CycleResult` no longer carries `layer_pointers_after`
- [ ] Failure paths populate `layer_summary.<layer>.errors` correctly

### Subtask T016: tests/sync/test_state.py — add LayerSummary tests

**Purpose**: cover the new schema in unit tests.

**Steps**:

1. Add tests for `PerLayerSummary` + `LayerSummary` dataclass construction (positional + kwarg).

2. Add tests for `PerTickHealthRecord` with the new `layer_summary` field shape.

3. Remove tests that reference `LayerPointerSnapshot` (they're now stale).

4. Update `write_per_tick_health` round-trip tests — write a record, read the JSON file, assert the layer_summary shape matches the dataclass.

**Files**: `tests/sync/test_state.py` (~100 line delta — additions + removals)

**Validation**:
- [ ] `pytest tests/sync/test_state.py -v` passes
- [ ] No reference to `LayerPointerSnapshot` remains

### Subtask T017: tests/sync/test_cycle_*.py — update fixtures

**Purpose**: integration tests act as regression guards; fixture migration is mostly mechanical.

**Steps**:

1. Replace `FetchedDelta` mock fixtures with `FetchedSnapshot` mocks. The `tasks` field stays a tuple of task dicts; the `projects` field stays a dict of project_id → project dict. `vikunja_version` and `fetched_at_utc` are unchanged.

2. Drop `since_utc` argument from mock setup.

3. Adjust expectations for `last-tick.json` — assertions on `layer_pointers` become assertions on `layer_summary`.

4. Assertions on cache contents, JSONL event emission, WhatsApp dispatch are **unchanged** — these are the regression-guard role per the operator's test-strategy decision.

5. Add new integration test cases for:
   - Task deletion happy path (deleted task_id triggers Phase 5b; history.jsonl gets a line; cache shrinks)
   - Project rename event (project layer in `last-tick.json.layer_summary.project_layer.updated`)
   - FR-012 abort (mock fetch failure; verify cycle aborts cleanly without partial cache writes)

**Files**: `tests/sync/test_cycle_*.py` (~150 line delta across multiple test files)

**Validation**:
- [ ] `pytest tests/sync/test_cycle_*.py -v` passes
- [ ] Cache content assertions still match #519's contract (NFR-004 regression guard)
- [ ] New integration tests for Phase 5b + project rename + FR-012 abort

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per computed lane from `lanes.json`. Depends on WP02 + WP03 — the worktree base inherits both.

## Test Strategy

Per the operator's decision (2026-06-05): rewrite affected unit tests in place (`test_state.py`); integration tests in `test_cycle_*.py` act as regression guards. Fixture migration is mechanical (FetchedDelta → FetchedSnapshot); assertions on outcomes stay stable.

The NFR-004 cache-read contract test from #519 (`tests/common/test_sync_cache.py`) MUST continue to pass unchanged.

## Definition of Done

- [ ] `state.py` provides `PerLayerSummary` + `LayerSummary`; `LayerPointerSnapshot` is removed
- [ ] `PerTickHealthRecord` uses `layer_summary` field
- [ ] `cycle.py` Phase 1 calls `fetch_full_poll`
- [ ] `cycle.py` Phase 2 consumes the new 5-tuple `compute_divergences` output
- [ ] `cycle.py` Phase 5 uses set-diff-based update; project cache is canonical replacement
- [ ] `cycle.py` Phase 5b runs deletion-cleanup in the documented order with per-task failure logging
- [ ] `cycle.py` Phase 6 writes `layer_summary` in `PerTickHealthRecord`
- [ ] `tests/sync/test_state.py` covers new types; `LayerPointerSnapshot` tests removed
- [ ] `tests/sync/test_cycle_*.py` integration tests pass; new tests for Phase 5b + project rename + FR-012 abort added
- [ ] `tests/common/test_sync_cache.py` (NFR-004) passes unchanged
- [ ] `pytest tests/sync/ tests/common/ -v` exits 0
- [ ] No changes to files outside `owned_files`

## Risks

- **R-001 (medium)**: rewriting cycle.py Phase 5 has the largest blast radius. Reviewer must validate phase-by-phase against `contracts/cycle-pipeline.md`.
- **Atomic-cycle guarantee**: any failure in Phase 5/5b/6 must NOT leave a partial state on disk. Existing #518 ordering (freshness written LAST in Phase 6) is preserved.
- **Phase 5b failure semantics**: a partial cleanup (history-log written, schedule.yaml prune failed) leaves a recoverable state — next cycle's full poll re-triggers because the task is still in `in_cache_only`. Verify the cache removal happens in Phase 6 only when the schedule.yaml prune succeeded OR was a no-op (i.e., not on partial failure). Actually wait: per current design, the cache removal happens unconditionally in Phase 6 because the new_task_cache from Phase 5 already excludes deleted_task_ids. So if Phase 5b fails partially, the cache is updated but schedule.yaml may still have the entry. This is acceptable — next cycle's prune will be idempotent and clean up.
- **Phase 5b path constants**: ensure they point to the correct files (`scripts/habits/state/habits-history.jsonl` and `scripts/habits/migrations/phase3-schedule.yaml` are repo-relative; consider using `Path(__file__).parent.parent.parent / "habits/state/habits-history.jsonl"` for portability).
- **Integration test fixture migration**: mostly mechanical but watch for test fixtures that hardcoded `FetchedDelta` shape; missed migrations cause test failures.

## Reviewer Guidance

The reviewer should validate:

1. **Each phase's contract from `contracts/cycle-pipeline.md` is met** — phase-by-phase walkthrough.
2. **No reference to `fetch_delta`, `FetchedDelta`, `LayerPointerSnapshot`, `since_utc` remains** in cycle.py or state.py.
3. **Phase 5b ordering**: history-log first, then schedule.yaml, then cache via Phase 6.
4. **Atomicity**: any failure in 5/5b/6 leaves an interpretable state (no corrupted files; cache+freshness atomically consistent).
5. **NFR-004 regression test still passes** — the cache-read contract from #519 holds.
6. **`layer_summary.errors` is populated on failure** — partial cycles record what failed.
7. **Test coverage**: per-phase unit tests in `test_state.py`, end-to-end integration in `test_cycle_*.py`.
8. **Path conventions**: cycle.py uses repo-relative paths via `Path(__file__).parent...` or an injected config field, not hardcoded absolute paths.

## Implementation command

```bash
spec-kitty agent action implement WP04 --mission felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7 --agent <tool>:<model>:<profile>:<role>
```

## Next steps after WP04 approval

- WP06 (architecture docs) can begin — it depends on WP04 (docs reflect actual delivered behavior).
- WP01 + WP05 may already be approved by the time WP04 finishes (parallel paths).

## Activity Log

- 2026-06-05T19:27:55Z – claude:sonnet:implementer:implementer – shell_pid=83870 – Started implementation via action command
- 2026-06-05T19:53:42Z – claude:sonnet:implementer:implementer – shell_pid=83870 – Ready for review: driver rewrite (state.py + cycle.py) + Phase 5b deletion cleanup + LayerSummary. 382 tests pass; NFR-004 regression clean. Note: WP04 also includes a 2-line collateral fix to tests/sync/test_driver.py (CycleResult API change ripple) — implementer flagged this in the report.
