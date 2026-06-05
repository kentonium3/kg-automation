# Contract: Cycle Pipeline (Full-Poll)

**Spec FRs**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-009, FR-012
**Source module**: `scripts/sync/cycle.py`
**Predecessor contract**: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/cycle-pipeline.md` (replaced by this)

## Pipeline shape

The driver runs a single `run_cycle(config: CycleConfig) → CycleResult` per `felix-vikunja-sync.timer` firing. The cycle progresses through 7 phases (Phase 5 is split into Phase 5 update + Phase 5b deletion-cleanup). Phases run in strict order; partial progress on a failure preserves only Phase 0 reads.

```
Phase 0  preamble        — read token, freshness, task_cache, project_cache, guard_state
Phase 1  fetch           — fetch_full_poll(token, base_url) → FetchedSnapshot
Phase 2  diff            — compute_divergences(snapshot, task_cache, project_cache, ts_observed_utc) → task changes + project events + LayerSummary
Phase 3  classify        — classify_task_changes(divergences) → conflicts list (auto_resolved | unsafe)
Phase 4  emit            — emit_events(conflicts) + emit_project_events(project_events) → JSONL writes + WhatsApp dispatch
Phase 5  update          — compute new_task_cache + new_project_cache (in-memory)
Phase 5b deletion-cleanup — for each task_id in deleted_task_ids: append history event, prune schedule.yaml
Phase 6  complete        — atomic writes: task_cache, project_cache, guard_state, freshness, last-tick (PerTickHealthRecord with LayerSummary)
```

## Phase 1 (fetch) contract

**Input**: `token: str`, `base_url: str`
**Output**: `FetchedSnapshot`
**Errors**:
- `OSError` raised → cycle aborts with phase="fetch", LayerSummary.task_layer.errors or .project_layer.errors records `vikunja_unreachable`
- Empty `[]` returned for `/tasks/all` while `task_cache` is non-empty → cycle aborts with `empty_response_when_cache_nonzero` error token (FR-012)
- Empty `[]` returned for `/projects` while `project_cache` is non-empty → same as above on project_layer
- HTTP 5xx → cycle aborts with `vikunja_5xx` error token
- HTTP 401/403 → cycle aborts with `auth_failure` error token
- JSON parse failure → cycle aborts with `parse_error` error token

Note: `vikunja_version` capture failure is NOT a cycle-abort signal (it's informational only).

## Phase 2 (diff) contract

**Input**: `FetchedSnapshot`, `TaskCacheRecord`, `ProjectCacheRecord`, `ts_observed_utc`, `private_project_ids`
**Output**:
- `divergences: list[DivergenceCandidate]` — task field-level changes (`in_both` with changed fields)
- `first_observation_task_ids: set[int]` — task IDs new in this cycle (`in_vikunja_only` for tasks)
- `deleted_task_ids: set[int]` — task IDs removed in this cycle (`in_cache_only` for tasks)
- `project_events: list[ProjectDiffEvent]` — project-layer changes
- `layer_summary: LayerSummary` — aggregate counts per layer

**Determinism**: pure function; no side effects; same inputs always yield the same outputs.

**Privacy filter**: tasks whose `project_id` ∈ `private_project_ids` produce no `DivergenceCandidate` rows (preserves #518's privacy semantics).

## Phase 3 (classify) contract

**Input**: `divergences: list[DivergenceCandidate]`, `task_lookup: dict[int, dict]`
**Output**: `list[ClassifiedConflict]`

**Unchanged from #518.** Project-layer events do NOT go through classification (per spec C-005).

## Phase 4 (emit) contract

**Input**: classified conflicts + project events + cycle context
**Output**: conflict-events.jsonl entries written; WhatsApp pings dispatched for unsafe; project events written to `last-tick.json.layer_summary` (no separate JSONL).

**Project events do NOT** trigger WhatsApp pings or JSONL writes outside `last-tick.json`. They appear in the cycle's log only.

## Phase 5b (deletion-cleanup) contract

**Input**: `deleted_task_ids: set[int]`, `task_cache: TaskCacheRecord` (the pre-deletion version, for the title lookup)
**Output**: side effects:
- For each task_id, in order:
  1. Append `task_deleted` event to `scripts/habits/state/habits-history.jsonl` (atomic append)
  2. Open `scripts/habits/migrations/phase3-schedule.yaml`, remove entry for task_id if present, write back (round-trip, preserving comments)
  3. (Phase 6 handles cache removal as part of the atomic task-cache write)

**Failure semantics**:
- If step 1 fails for a given task_id → log the error to `last-tick.errors.jsonl`, skip this task_id (the cycle continues for other deletions; this task_id is re-attempted next cycle)
- If step 2 fails for a given task_id → log the error, leave history-log entry in place (next cycle's full poll re-triggers; FR-003 cleanup runs again)

**Idempotency**: re-running the cleanup for the same task_id is benign — history-log append produces a duplicate event (acceptable; the audit trail is append-only), schedule.yaml prune is no-op if the entry is already absent.

## Phase 6 (complete) contract

**Input**: in-memory new_task_cache, new_project_cache, updated_guard_state, layer_summary, all error state
**Output**: atomic writes to disk

**Order**:
1. `write_task_cache(state_dir, new_task_cache)` — atomic write-temp-rename
2. `write_project_cache(state_dir, new_project_cache)` — atomic write-temp-rename
3. `write_guard_state(state_dir, updated_guard_state)`
4. `write_freshness(state_dir, FreshnessPointer(...))` — updates last_polled_utc
5. `write_per_tick_health(state_dir, PerTickHealthRecord(layer_summary=layer_summary, ...))`

**Failure semantics**: failure in any step records `phase="complete"` failure, returns `CycleResult(success=False)`. The atomic write-temp-rename protects against partial files at the FS layer; what's at risk is **between** writes (e.g., task_cache written but project_cache write failed). In that case, the next cycle's Phase 0 reads will see a mixed pair — but Phase 1's fresh full poll + Phase 2 set-diff produces correct outputs from whatever state was committed.

## Atomic-cycle guarantee

The cycle is **atomic at the cache-pair level**: by convention, downstream consumers (`scripts/common/sync_cache.py`) read freshness.json LAST and treat its `last_updated_utc` as the cache cohort marker. If freshness.json's timestamp doesn't match the cache files' modification times, the consumer's `is_cache_healthy()` returns False and reads fail per #519's no-silent-fallback rule.

This guarantee is preserved by writing freshness LAST in Phase 6.

## Migration from #518's pipeline

| #518 phase | #520 phase | Change |
|---|---|---|
| Phase 0 preamble | Phase 0 (unchanged) | identical |
| Phase 1 fetch (delta) | Phase 1 fetch (full-poll) | `fetch_delta` → `fetch_full_poll`; output type changes from `FetchedDelta` to `FetchedSnapshot` |
| Phase 2 diff (delta-apply) | Phase 2 diff (set-diff) | input changes; output adds `deleted_task_ids` and `project_events` |
| Phase 3 classify | Phase 3 classify | unchanged |
| Phase 4 emit | Phase 4 emit | adds project_events handling (write to layer_summary only) |
| Phase 5 update | Phase 5 update | applies set-diff outputs to caches |
| (none) | Phase 5b deletion-cleanup | NEW |
| Phase 6 complete | Phase 6 complete | `layer_pointers` → `layer_summary` in PerTickHealthRecord |
