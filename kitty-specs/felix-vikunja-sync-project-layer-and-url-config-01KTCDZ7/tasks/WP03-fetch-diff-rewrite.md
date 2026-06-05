---
work_package_id: WP03
title: fetch.py + diff.py Rewrite (Full-Poll + 3-Way Set Diff)
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-012
- NFR-003
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
history: []
authoritative_surface: scripts/sync/fetch.py
execution_mode: code_change
owned_files:
- scripts/sync/fetch.py
- scripts/sync/diff.py
- tests/sync/test_fetch.py
- tests/sync/test_diff.py
tags: []
agent: "claude:sonnet:implementer:implementer"
shell_pid: "78402"
---

# WP03 — fetch.py + diff.py Rewrite

## Objective

Replace `#518`'s incremental fetch (`fetch_delta` returning `FetchedDelta`) with a full-poll fetch (`fetch_full_poll` returning `FetchedSnapshot`). Rewrite `compute_divergences` to consume the snapshot via 3-way set diff, producing four output streams: task content changes (existing `DivergenceCandidate` shape), first-observation task IDs, deleted task IDs, and project diff events. Compute `LayerSummary` aggregate counts within the diff function.

Per spec FR-001, FR-002, FR-004, FR-012, and `contracts/set-diff.md` + `contracts/cycle-pipeline.md` Phase 1 + Phase 2.

## Context

#518's `fetch.py:fetch_delta` does incremental polling (`GET /tasks/all?updated_since=<ts>`) plus just-in-time per-project fetches for new project_ids referenced by changed tasks. Existing projects are never refreshed. Under #520's full-poll model:

- `GET /tasks/all` (no `updated_since`) returns the COMPLETE current task state
- `GET /projects` returns the COMPLETE current project state

Both are observed in one cycle. The just-in-time per-project logic disappears entirely (project layer is its own canonical full poll).

`compute_divergences` in `diff.py` currently consumes a `FetchedDelta` (changed tasks only) and applies them to the cache. Under #520's set-diff model:

- 3 disjoint task sets: `in_vikunja_only` (additions), `in_cache_only` (deletions), `in_both` (potential updates)
- 3 disjoint project sets: same partition for projects, mapped to 5 event types
- `LayerSummary` carries per-layer aggregate counts and `polled_at_utc`

The conflict-event pipeline (Phase 3 classify + Phase 4 emit) consumes the same `DivergenceCandidate` shape it does today — no downstream interface changes for the content-change path.

## Implementation guidance

### Subtask T007: Replace `fetch_delta` with `fetch_full_poll`; add FR-012 abort guards

**Purpose**: rewrite the fetch phase.

**Steps**:

1. **Delete `FetchedDelta`** dataclass; replace with `FetchedSnapshot`:

   ```python
   @dataclass(frozen=True)
   class FetchedSnapshot:
       """Full-state snapshot returned by full-poll fetch.

       Both layers (tasks + projects) are observed in one cycle. Downstream
       consumers treat this as the source of truth for the cycle.
       """
       tasks: tuple[dict, ...]              # full task list from GET /tasks/all
       projects: dict[int, dict]            # full project list from GET /projects, keyed by project_id
       vikunja_version: str | None
       fetched_at_utc: str
   ```

2. **Delete `fetch_delta`**; replace with `fetch_full_poll`:

   ```python
   def fetch_full_poll(
       token: str,
       base_url: str,
       *,
       task_cache_nonempty: bool = False,
       project_cache_nonempty: bool = False,
   ) -> FetchedSnapshot:
       """Pull the complete current Vikunja state via full poll.

       Args:
           token: Vikunja bearer token
           base_url: Fully qualified API base with trailing slash, e.g.,
               "https://office2.tail0f5f56.ts.net/api/v1/"
           task_cache_nonempty: True if the task_cache passed by the caller
               has non-zero entries. Used by FR-012 guard to detect empty
               responses when the cache says we should have tasks.
           project_cache_nonempty: same for the project cache.

       Returns:
           FetchedSnapshot with current task and project state.

       Raises:
           OSError: on HTTP failure, 4xx/5xx, parse failure, or FR-012
               empty-response-when-cache-nonempty. The OSError message starts
               with a structured token from this set:
                 - "vikunja_unreachable: ..."
                 - "auth_failure: ..."
                 - "vikunja_5xx: ..."
                 - "parse_error: ..."
                 - "empty_response_when_cache_nonzero: ..."
       """
   ```

3. **Implement structured error tokens**: wrap calls to `get_json` (from `http.py`) with try/except; re-raise as OSError with the token-prefixed message. Use the following dispatch:
   - 401, 403 → `auth_failure`
   - 5xx → `vikunja_5xx`
   - JSONDecodeError or non-list response → `parse_error`
   - empty list when `task_cache_nonempty` → `empty_response_when_cache_nonzero`
   - any other OSError → `vikunja_unreachable`

4. **Remove the just-in-time per-project fetch**. Replace with a single `GET /projects` call. Discard the existing `_project_stub` helper (no longer needed; if a project layer fetch fails, the cycle aborts per FR-012).

5. **Keep `vikunja_now_iso()` helper** and the `/info` version capture (best-effort; failure is silent).

6. **Two HTTP calls per fetch** (tasks + projects). Sequence them strictly; abort on first failure (don't make the second call if the first failed). Record `fetched_at_utc` at fetch entry (BEFORE the HTTP calls).

**Files**: `scripts/sync/fetch.py` (rewrite, ~110 lines)

**Validation**:
- [ ] `FetchedSnapshot` replaces `FetchedDelta` (no parallel coexistence)
- [ ] `fetch_full_poll` accepts only `token`, `base_url`, and the cache-non-empty flags
- [ ] No reference to `updated_since`, `since_utc`, or `known_project_ids` remains
- [ ] All 5 structured error tokens are produced for the documented failure modes

### Subtask T008: Rewrite `compute_divergences` in `diff.py`

**Purpose**: 3-way set diff producing all 5 output streams.

**Steps**:

1. **New signature**:

   ```python
   from scripts.sync.fetch import FetchedSnapshot
   from scripts.sync.state import (
       TaskCacheRecord, ProjectCacheRecord,
       LayerSummary, PerLayerSummary,
   )

   @dataclass(frozen=True)
   class ProjectDiffEvent:
       type: str                     # "project_added" | "project_removed" | "project_renamed" | "project_archived" | "project_unarchived"
       project_id: int
       title: str | None
       is_archived: bool | None
       detected_at_utc: str


   def compute_divergences(
       snapshot: FetchedSnapshot,
       task_cache: TaskCacheRecord,
       project_cache: ProjectCacheRecord,
       ts_observed_utc: str,
       private_project_ids: frozenset[int] = PRIVATE_PROJECT_IDS,
   ) -> tuple[
       list[DivergenceCandidate],       # task content changes
       set[int],                         # first_observation_task_ids
       set[int],                         # deleted_task_ids
       list[ProjectDiffEvent],           # project layer events
       LayerSummary,                     # per-layer aggregate counts
   ]:
       """Compute the full set-diff for one cycle. Pure function."""
   ```

2. **Task layer set diff**:
   - `snapshot_task_ids = {t["id"] for t in snapshot.tasks if isinstance(t.get("id"), int)}`
   - `cache_task_ids = set(task_cache.tasks.keys())`
   - `in_vikunja_only = snapshot_task_ids - cache_task_ids` → these are the `first_observation_task_ids`
   - `in_cache_only = cache_task_ids - snapshot_task_ids` → these are the `deleted_task_ids`
   - `in_both = snapshot_task_ids & cache_task_ids` → compare TRACKED_TASK_FIELDS

3. **Privacy filter applies to `in_both` content events only**, NOT to `first_observation_task_ids` or `deleted_task_ids`. Structural operations bypass the privacy filter (the cache still adds/removes private task records; it just doesn't emit conflict events for them).

4. **Field-level diff for `in_both`**: use the existing TRACKED_TASK_FIELDS list (`scripts/sync/diff.py:33` from #518). Compare normalized values (existing `_canonicalize` helper). Emit `DivergenceCandidate` per task with any field difference.

5. **Project layer set diff**:
   - `snapshot_project_ids = set(snapshot.projects.keys())`
   - `cache_project_ids = {int(pid) for pid in project_cache.projects.keys()}` (string-to-int coercion)
   - `in_vikunja_only` → emit `project_added` event per id
   - `in_cache_only` → emit `project_removed` event per id (use last-known title from cache)
   - `in_both` → check title difference → `project_renamed`; check `is_archived` difference → `project_archived` or `project_unarchived`

6. **LayerSummary computation**:

   ```python
   task_layer_summary = PerLayerSummary(
       polled_at_utc=snapshot.fetched_at_utc,
       added=len(first_observation_task_ids),
       removed=len(deleted_task_ids),
       updated=len(divergences),
       errors=(),
   )
   project_layer_summary = PerLayerSummary(
       polled_at_utc=snapshot.fetched_at_utc,
       added=sum(1 for e in project_events if e.type == "project_added"),
       removed=sum(1 for e in project_events if e.type == "project_removed"),
       updated=sum(1 for e in project_events if e.type in {"project_renamed", "project_archived", "project_unarchived"}),
       errors=(),
   )
   layer_summary = LayerSummary(
       task_layer=task_layer_summary,
       project_layer=project_layer_summary,
   )
   ```

7. **Output ordering**: `divergences` sorted by `vikunja_entity_id` ascending; `project_events` sorted by `(project_id, type)`. Deterministic outputs for test stability.

**Files**: `scripts/sync/diff.py` (substantial rewrite, ~180 lines)

**Validation**:
- [ ] `compute_divergences` returns a 5-tuple
- [ ] All 3-way partitions are computed
- [ ] Privacy filter applies to content events only, not structural ops
- [ ] LayerSummary counts match the produced output lists
- [ ] Outputs are deterministically ordered

### Subtask T009: Rewrite `tests/sync/test_fetch.py`

**Purpose**: assert full-poll semantics + FR-012 abort cases.

**Steps**:

Use the existing test scaffolding from #518's `test_fetch.py` (`urlopen` mocking pattern). Rewrite scenarios:

1. **Happy path**: mock `urlopen` to return a task list + project list; assert `fetch_full_poll` returns a `FetchedSnapshot` with both tuples populated; assert exactly two HTTP calls were made (tasks + projects); assert `vikunja_version` captured.

2. **No `updated_since` in URL**: assert the tasks URL is `f"{base_url}tasks/all"` with no query string.

3. **No just-in-time per-project fetch**: even if a task references an unknown project_id, no per-project GET is made (the snapshot's projects dict is the source of truth).

4. **FR-012 — auth_failure**: mock `urlopen` to raise HTTPError 401; expect OSError with message starting `"auth_failure:"`.

5. **FR-012 — vikunja_5xx**: mock 503; expect OSError with `"vikunja_5xx:"`.

6. **FR-012 — parse_error**: mock response with non-JSON body; expect OSError with `"parse_error:"`.

7. **FR-012 — empty_response_when_cache_nonzero**: mock empty `[]` for tasks; pass `task_cache_nonempty=True`; expect OSError with `"empty_response_when_cache_nonzero:"`.

8. **FR-012 — empty allowed when cache empty**: mock empty `[]` for tasks; pass `task_cache_nonempty=False`; expect SUCCESS (no abort).

9. **vikunja_version capture failure does NOT abort**: mock `/tasks/all` and `/projects` happy; mock `/info` raises; expect FetchedSnapshot returns with `vikunja_version=None`.

10. **Strict call sequence**: if tasks fetch fails, projects fetch is NOT attempted (assert mock call count).

**Files**: `tests/sync/test_fetch.py` (rewrite, ~280 lines)

**Validation**:
- [ ] `pytest tests/sync/test_fetch.py -v` passes all 10 scenarios
- [ ] All 5 structured error tokens are tested
- [ ] No live HTTP (all calls mocked)

### Subtask T010: Rewrite `tests/sync/test_diff.py`

**Purpose**: assert 3-way set diff outputs.

**Steps**:

Rewrite test scenarios using the new `compute_divergences` signature. Fixtures: build a `FetchedSnapshot` directly, a `TaskCacheRecord` with synthetic tasks, a `ProjectCacheRecord` with synthetic projects.

Scenarios:

1. **Empty inputs**: empty snapshot + empty cache → empty divergences, empty first_observation/deleted sets, empty project_events, zero LayerSummary counts.

2. **Pure task additions**: 3 tasks in snapshot, none in cache → 3 task_ids in `first_observation_task_ids`, 0 deletes, 0 divergences, LayerSummary task_layer added=3 removed=0 updated=0.

3. **Pure task deletions**: 0 tasks in snapshot, 3 in cache → 3 task_ids in `deleted_task_ids`, 0 first_observation, 0 divergences, LayerSummary task_layer added=0 removed=3 updated=0.

4. **Pure task updates**: same task_ids, different `title` field → divergence per changed task; LayerSummary task_layer added=0 removed=0 updated=N.

5. **Mixed task scenario**: 1 added, 1 deleted, 1 updated, 2 unchanged → correct partitioning + LayerSummary added=1 removed=1 updated=1.

6. **Privacy filter on content events**: task with private project_id has changed title; expect NO `DivergenceCandidate` (filtered), but cycle additions/deletions of private tasks STILL appear in `first_observation_task_ids` / `deleted_task_ids`.

7. **Project added**: project_id 99 in snapshot, not in cache → `project_added` event; LayerSummary project_layer added=1.

8. **Project removed**: project_id 7 in cache, not in snapshot → `project_removed` event with last-known title; LayerSummary project_layer removed=1.

9. **Project renamed**: project_id 1 with different title in snapshot vs cache → `project_renamed` event; LayerSummary project_layer updated=1.

10. **Project archived**: project_id 2 has `is_archived: false` in cache, `is_archived: true` in snapshot → `project_archived` event.

11. **Project unarchived**: reverse of 10 → `project_unarchived` event.

12. **Type coercion**: cache project_id stored as `"5"`, snapshot stores as `5` → no spurious add/remove events.

13. **Deterministic ordering**: divergences sorted by vikunja_entity_id ascending; project_events sorted by `(project_id, type)`.

14. **TRACKED_TASK_FIELDS coverage**: assert each field in TRACKED_TASK_FIELDS produces a divergence when changed in isolation.

**Files**: `tests/sync/test_diff.py` (rewrite, ~320 lines)

**Validation**:
- [ ] `pytest tests/sync/test_diff.py -v` passes all 14 scenarios
- [ ] Privacy filter test verifies content vs structural distinction
- [ ] LayerSummary counts assertion in every relevant scenario

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per computed lane from `lanes.json` (no dependencies; can run in parallel with WP01 and WP02).

## Test Strategy

Unit tests for both files; comprehensive coverage of all phase contracts. Integration tests are owned by WP04 (`test_cycle_*.py`).

## Definition of Done

- [ ] `scripts/sync/fetch.py` provides `fetch_full_poll` + `FetchedSnapshot`; old `fetch_delta` + `FetchedDelta` removed
- [ ] `scripts/sync/diff.py` provides the new `compute_divergences` signature + `ProjectDiffEvent`
- [ ] `tests/sync/test_fetch.py` covers all 10 scenarios
- [ ] `tests/sync/test_diff.py` covers all 14 scenarios
- [ ] `pytest tests/sync/test_fetch.py tests/sync/test_diff.py -v` passes
- [ ] No changes to files outside `owned_files`
- [ ] No live HTTP; all calls mocked

## Risks

- **`compute_divergences` interface is consumed by `cycle.py` (WP04)**: the 5-tuple shape is documented in `contracts/cycle-pipeline.md` Phase 2 — keep this contract precise. If you adjust during implementation, update the contract and flag to WP04's prompt.
- **Privacy filter interpretation**: per `contracts/set-diff.md`, private tasks STILL produce structural events. If you read this differently during implementation, flag for the operator before proceeding.
- **TRACKED_TASK_FIELDS** must remain the same set as #518 (per spec FR-008 — no silent widening). Verify the same tuple is preserved.
- **State imports**: this WP imports `LayerSummary` + `PerLayerSummary` from `scripts/sync/state.py`. These types need to exist; per the dependency graph, WP04 adds them. But WP03 is "no deps"... ⚠️ **Sequencing note**: in practice, this WP needs to coordinate type definitions with WP04. The cleanest path: define `PerLayerSummary` + `LayerSummary` types in WP03's diff.py initially, and WP04 moves them to state.py (where they belong long-term). Or: WP03 declares the types where it uses them and WP04 unifies. Flag this to the operator during implementation if it causes friction.

## Reviewer Guidance

The reviewer should validate:

1. **`fetch_full_poll` makes exactly two HTTP calls** to `/tasks/all` and `/projects` (verified by mock call count).
2. **No reference to `updated_since` or `since_utc` remains** anywhere in fetch.py.
3. **All 5 FR-012 error tokens** appear in the OSError messages for the documented failure cases.
4. **`compute_divergences` returns the 5-tuple** in the documented order.
5. **Privacy filter applies to content events only** — structural ops include private tasks.
6. **TRACKED_TASK_FIELDS** is preserved (no widening).
7. **Tests cover all 14 + 10 scenarios**; no hidden integration tests in this WP.

## Implementation command

```bash
spec-kitty agent action implement WP03 --mission felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7 --agent <tool>:<model>:<profile>:<role>
```

## Next steps after WP03 approval

- WP04 can begin (it depends on WP02 + WP03; both must be approved).
- WP01 is unblocked (no dep on WP03); can be in flight in parallel.

## Activity Log

- 2026-06-05T19:12:56Z – claude:sonnet:implementer:implementer – shell_pid=78402 – Started implementation via action command
- 2026-06-05T19:24:47Z – claude:sonnet:implementer:implementer – shell_pid=78402 – Ready for review: 35 unit tests pass (18 test_fetch + 17 test_diff); full-poll + 3-way set diff implemented per contracts; FR-012 all 5 error tokens covered; TRACKED_TASK_FIELDS preserved; PerLayerSummary + LayerSummary defined in diff.py pending WP04 migration to state.py
