---
work_package_id: WP02
title: 'Read pipeline: Vikunja fetch + value diff'
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-009
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: lane-per-WP; merge to main at mission end
subtasks:
- T006
- T007
- T008
- T009
history:
- at: '2026-06-04T19:53:57Z'
  by: spec-kitty.tasks
  note: Created WP02 from plan.md + contracts/cycle-pipeline.md § Phase 1/2
authoritative_surface: scripts/sync/
execution_mode: code_change
owned_files:
- scripts/sync/fetch.py
- scripts/sync/diff.py
- tests/sync/test_fetch.py
- tests/sync/test_diff.py
tags: []
---

# WP02 — Read pipeline: Vikunja fetch + value diff

## Objective

Implement the first two phases of the cycle pipeline: pull delta changes from Vikunja and compute the field-level divergences against the driver's cached state. No judgment, no side effects, no I/O beyond Vikunja HTTP GETs — pure data transformations that downstream WPs (classify, emit) consume.

After this WP, downstream WPs can:
- Call `fetch_delta(token, base_url, since_utc, known_project_ids) → FetchedDelta` to retrieve the changed-tasks delta plus any newly-referenced projects.
- Call `compute_divergences(fetched_delta, task_cache, tracked_fields) → list[DivergenceCandidate]` to identify every field that diverged.

## Context

Phase 1 of the 6-phase pipeline (`fetch`) is documented in `contracts/cycle-pipeline.md`. It performs:
1. One `GET /api/v1/tasks/all?updated_since={pointer}` to get all changed tasks since the last successful cycle.
2. Per-task: if the task references a `project_id` not in the local `ProjectCacheRecord`, issue a `GET /api/v1/projects/{id}` to learn its title/archived state.

Phase 2 (`diff`) compares each fetched task's tracked fields against the cached value and emits a `DivergenceCandidate` for each (task, field) pair that differs. First observations (task NOT in cache) do NOT produce candidates — they're flagged for the `update` phase to create cache entries without firing classify/emit.

Research finding from `research.md` Unknown 3: Vikunja v0.24.6 returns `updated_by: null` on tasks, so authorship cannot be inferred from a direct Vikunja field. The diff is the authorship signal — Felix knew what value was supposed to be there; Vikunja says otherwise; therefore someone (operator or Vikunja itself) wrote it.

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch = `main`. Lane worktree allocated by `spec-kitty agent mission finalize-tasks`; implementer commits inside the worktree only.

## Implementation command

```bash
spec-kitty agent action implement WP02 --agent <name>
```

Depends on WP01. The lane this WP runs in inherits WP01's commits via the mission's lane-graph.

---

## Subtask T006 — `scripts/sync/fetch.py`: Vikunja delta poll

**Purpose**: Implement the fetch phase. Takes the freshness pointer and returns a `FetchedDelta` containing the changed tasks and any newly-needed projects.

**Steps**:

1. Define `@dataclass(frozen=True) class FetchedDelta`:

   ```python
   @dataclass(frozen=True)
   class FetchedDelta:
       tasks: tuple[dict, ...]               # Vikunja task JSON payloads
       projects: dict[int, dict]              # project_id → Vikunja project JSON
       vikunja_version: str | None            # from a separate /api/v1/info call (best-effort)
       fetched_at_utc: str                    # ISO-8601 wall clock at fetch start
   ```

2. Implement `fetch_delta(token: str, base_url: str, since_utc: str, known_project_ids: set[int]) → FetchedDelta`:

   - Issue `GET {base_url}tasks/all?updated_since={since_utc}` via `scripts.sync.http.get_json`.
   - For each task: extract its `project_id`. Add to a `referenced_project_ids` set.
   - For each `project_id ∈ referenced_project_ids - known_project_ids`: issue `GET {base_url}projects/{id}` via the same wrapper. Failures here are LOGGED via `sys.stderr.write` but do NOT abort the cycle — the task is included in the delta with `project_id` resolved to a stub dict `{"id": pid, "title": "<unknown>", "is_archived": false}`.
   - Issue `GET {base_url}info` (best-effort) to capture the Vikunja version for the health record. Failure here is silent; `vikunja_version` becomes `None`.

3. Implement `vikunja_now_iso() → str` returning the wall clock at fetch entry, ISO-8601 UTC, used as `fetched_at_utc` and as the candidate next freshness pointer value (advanced only on cycle success).

4. **Error handling**: any HTTPError from the main `/tasks/all` call propagates as a cycle error. Per-project fetch failures degrade gracefully (logged, not aborted) so the cycle can make progress on other tasks even if one project is briefly unreachable.

**Files**:
- `scripts/sync/fetch.py` (~180 lines)

**Reference precedent**: HTTP wrapper at `scripts/sync/http.py` (from WP01). No HTTP precedent for the delta endpoint elsewhere in the codebase — research.md confirmed the endpoint exists.

**Validation**:
- [ ] Main `/tasks/all` failure propagates with the URL and status in the error message
- [ ] Per-project fetch failure does NOT abort the cycle
- [ ] `vikunja_version` capture failure does NOT abort
- [ ] FetchedDelta is fully populated even when zero changes are returned (empty tasks tuple, empty projects dict)

---

## Subtask T007 — `scripts/sync/diff.py`: value comparison

**Purpose**: Compare the fetched task payloads against the driver's `TaskCacheRecord` and emit a list of `DivergenceCandidate` tuples for downstream classification.

**Steps**:

1. Define `@dataclass(frozen=True) class DivergenceCandidate`:

   ```python
   @dataclass(frozen=True)
   class DivergenceCandidate:
       vikunja_entity_id: int          # the integer task.id
       field: str                       # the field that differed (must be in TRACKED_TASK_FIELDS)
       vikunja_value: Any               # JSON-serializable value from Vikunja
       felix_cached_value: Any          # what the cache says Felix expected
       vikunja_updated_at: str          # Vikunja's `updated` ISO-8601 timestamp
       ts_observed_utc: str             # cycle's wall-clock observation time
   ```

2. Define `TRACKED_TASK_FIELDS: frozenset[str]` as the canonical curated set. Initial set:

   ```python
   TRACKED_TASK_FIELDS = frozenset({
       "title", "done", "due_date", "project_id",
       "repeat_after", "repeat_mode", "labels",
   })
   ```

3. Implement `compute_divergences(delta: FetchedDelta, task_cache: TaskCacheRecord, ts_observed_utc: str) → tuple[list[DivergenceCandidate], list[int]]`:
   - Returns `(divergences, first_observation_ids)`.
   - For each task in delta:
     - If task.id NOT in cache → add to `first_observation_ids`. No divergences emitted for this task; the `update` phase will create a cache entry.
     - Else, for each field in TRACKED_TASK_FIELDS:
       - Read Vikunja's value (handling field-missing as `None`).
       - Read cache's value (handling field-missing as `None`).
       - Apply canonical normalization (see step 4).
       - If normalized values differ → emit DivergenceCandidate.

4. Canonical normalization helpers:
   - Datetime fields (`due_date`): parse to `datetime`, format back to ISO-8601 UTC string. Handles Vikunja's "0001-01-01T00:00:00Z" zero-value.
   - List fields (`labels`): sort by id before compare.
   - String fields: compared verbatim.
   - Int / bool: compared verbatim.

5. **Privacy boundary**: tasks whose `project_id` matches an entry in a config-driven `PRIVATE_PROJECT_IDS` set produce NO divergences (the cache entry for them has empty `fields`, and the diff phase short-circuits). For this WP, treat `PRIVATE_PROJECT_IDS` as an empty default set; operator populates it post-merge if needed. Document the extension point.

**Files**:
- `scripts/sync/diff.py` (~210 lines)

**Validation**:
- [ ] Empty cache → all tasks are first observations → no divergences
- [ ] Cache matches Vikunja exactly → no divergences
- [ ] One field differs → one divergence
- [ ] Multiple fields differ on one task → multiple divergences with the same task_id, different fields
- [ ] Datetime canonical normalization treats `"2026-06-04T17:00:00.000000Z"` and `"2026-06-04T17:00:00Z"` as equal
- [ ] List normalization is order-insensitive

---

## Subtask T008 — `tests/sync/test_fetch.py`: fetch path tests [P]

**Purpose**: Cover the main delta endpoint, per-project just-in-time fetch, partial failures, and the version-capture best-effort path.

**Steps**:

1. Use the same `_resp` / `_http_error` helpers from `tests/sync/test_http.py` (import or duplicate locally for clarity).

2. Test cases:

   - `test_fetch_returns_empty_on_no_changes`: Vikunja returns `[]` → FetchedDelta with empty tasks tuple and empty projects.
   - `test_fetch_resolves_known_project_id_without_extra_fetch`: 2 tasks, both with project_id 13, known_project_ids = {13} → 1 HTTP call total (the delta).
   - `test_fetch_just_in_time_fetches_unknown_project`: 1 task with project_id 99, known_project_ids = {} → 3 HTTP calls (delta + project 99 + info). projects dict contains {99: ...}.
   - `test_fetch_per_project_failure_gracefully_degrades`: project 99 fetch returns HTTP 503 → cycle continues, projects[99] is the stub dict.
   - `test_fetch_main_delta_failure_propagates`: `/tasks/all` returns HTTP 503 → OSError raised, NOT degraded.
   - `test_fetch_version_capture_failure_silent`: `/info` raises → vikunja_version is None, no exception escapes.
   - `test_fetch_uses_authorization_bearer`: verify the request headers.

3. Mock `urllib.request.urlopen` for all calls. No live network.

**Files**:
- `tests/sync/test_fetch.py` (~220 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_fetch.py -q` passes
- [ ] Mock call counts asserted in every test (catches accidental extra requests)

---

## Subtask T009 — `tests/sync/test_diff.py`: diff path tests [P]

**Purpose**: Cover the comparison matrix, first-observation behavior, canonical normalization, and the privacy-boundary path.

**Steps**:

1. Build synthetic `FetchedDelta` and `TaskCacheRecord` objects in fixtures.

2. Test cases:

   - `test_empty_cache_all_first_observations`: cache empty, 3 tasks fetched → first_observation_ids has 3 entries, divergences is empty.
   - `test_matching_state_no_divergences`: cache matches fetched values for every field → divergences is empty.
   - `test_single_field_diverged`: cache has `due_date=A`, Vikunja has `due_date=B` → one DivergenceCandidate with `field=due_date, vikunja_value=B, felix_cached_value=A`.
   - `test_multiple_fields_diverged_on_one_task`: cache has stale `due_date` AND stale `title` → two DivergenceCandidates with same task_id, different fields.
   - `test_datetime_canonical_normalization`: cache has `"2026-06-04T17:00:00.000Z"`, Vikunja has `"2026-06-04T17:00:00Z"` → no divergence (canonical-equal).
   - `test_list_canonical_normalization`: cache labels `[{id:1}, {id:2}]`, Vikunja `[{id:2}, {id:1}]` → no divergence (order-insensitive).
   - `test_field_missing_in_vikunja_treated_as_none`: cache has `repeat_after=86400`, Vikunja response omits the field → one divergence with `vikunja_value=None`.
   - `test_privacy_boundary_skips_diff`: PRIVATE_PROJECT_IDS = {7}; task with project_id=7 has stale title → no divergence emitted (privacy filter).

3. No HTTP mocking needed (diff is pure).

**Files**:
- `tests/sync/test_diff.py` (~240 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_diff.py -q` passes
- [ ] Comparison matrix covers all 7 fields in TRACKED_TASK_FIELDS at least once

---

## Test strategy

Both new test files use mock-based unit tests. Run together via:

```bash
python3 -m pytest tests/sync/test_fetch.py tests/sync/test_diff.py -q
```

Combined target: ≥80% line coverage of `scripts/sync/fetch.py` and `scripts/sync/diff.py`. Branch coverage where reasonable.

---

## Definition of Done

- [ ] All 4 subtasks complete; all listed files committed in the WP02 worktree
- [ ] `python3 -m pytest tests/sync/ -q` passes (including WP01 tests)
- [ ] No edits to files outside the WP's `owned_files` list
- [ ] No edits to WP01-owned files (state.py, http.py, etc.)
- [ ] `TRACKED_TASK_FIELDS` is exported as a module-level constant (downstream WPs import it)
- [ ] Per-project fetch failure is logged to stderr (not swallowed silently) — operator can diagnose

---

## Risks and mitigations

- **Risk: Vikunja's `updated_since` boundary behavior at the exact-second cutoff.** Mitigation: comparison is against the cache (value-based), not against the timestamp (range-based). A task included in two consecutive `updated_since` queries produces no divergence on the second one because the cache was already updated.
- **Risk: large delta on first cycle after a long downtime.** Mitigation: the fetch endpoint streams all changes since the pointer; at Felix's scale (≤20 active tasks) even a week-old pointer produces tens of tasks. If this becomes a real operational issue, the operator can re-bootstrap (delete state files + run `--bootstrap`).
- **Risk: canonical normalization gap on a field type not yet seen.** Mitigation: explicit tests for each field type in TRACKED_TASK_FIELDS. New fields added to the set without canonical normalization handling will fail review.

---

## Reviewer guidance

When reviewing this WP, verify:
1. **`fetch.py` is HTTP-only**: no other I/O. All persistent state is read/written elsewhere (by `cycle.py` in WP05).
2. **`diff.py` is pure**: no I/O at all. Pure function from inputs to a list of DivergenceCandidate. Tests should be able to run without mocking anything beyond pytest's `tmp_path`.
3. **First-observation behavior**: tasks not in cache → recorded for cache creation but NOT classified as divergence. This is the key invariant that prevents the bootstrap from generating a flood of conflict events.
4. **Per-project graceful degradation** is implemented per spec EC-4 — failed project fetch logs to stderr but does NOT abort the cycle.
5. **TRACKED_TASK_FIELDS is a `frozenset`**: not mutable, not a list. Downstream WPs will import this constant.
6. **No edits to scripts/sync/state.py or scripts/sync/http.py** (those are WP01's owned files).

Reject if the diff phase has any I/O, if first-observation behavior is wrong, or if any owned-file boundary is violated.

---

## References

- Mission spec: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md`
- Pipeline contract: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/cycle-pipeline.md` § Phase 1, Phase 2
- Data model: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/data-model.md`
- Research finding (no Vikunja updated_by): `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/research.md` § Unknown 3
- HTTP wrapper (from WP01): `scripts/sync/http.py`
- State types (from WP01): `scripts/sync/state.py`
- Test pattern precedent: `tests/sync/test_state.py` (from WP01), `tests/habits/test_record_completion.py`
