---
work_package_id: WP03
title: 'Reconciler touchpoint migrations: TP-02, TP-10, TP-12'
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
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
agent: "claude:sonnet:implementer:implementer"
shell_pid: "28322"
history:
- at: '2026-06-04T22:24:02Z'
  by: spec-kitty.tasks
  note: Created WP03 from plan.md + contracts/migration-pattern.md for 3 reconciler TPs
authoritative_surface: scripts/
execution_mode: code_change
owned_files:
- scripts/habits/reconcile_completions.py
- scripts/escalation/reconcile_completions.py
- scripts/enrichment/reconcile_completions.py
- tests/habits/test_reconcile_completions.py
- tests/escalation/test_reconcile_completions.py
- tests/enrichment/test_reconcile_completions.py
tags: []
---

# WP03 — Reconciler touchpoint migrations: TP-02, TP-10, TP-12

## Objective

Migrate the 3 reconciler touchpoints from direct Vikunja HTTP reads to the helper. Each reconciler uses **both** `read_cached_tasks` / `read_cached_task_by_id` (for cache state) AND `read_completion_timestamps` (for state-log lookups). The state-log half is the differentiator from WP02 — reconcilers verify that JSONL completion events match cache `done` flags, which requires reading both data sources.

After this WP, the 3 reconcilers (one per domain: habits, escalation, enrichment) operate end-to-end against the local cache + their domain's state log. Zero Vikunja HTTP calls during normal invocation.

## Context

Per [research.md § Scope Correction](../research.md), the 3 reconcilers are the second half of the 6-touchpoint migration set:

- **TP-02** `scripts/habits/reconcile_completions.py` — habits reconciler
- **TP-10** `scripts/escalation/reconcile_completions.py` — escalation reconciler
- **TP-12** `scripts/enrichment/reconcile_completions.py` — enrichment reconciler

All 3 land on `SLA_NORMAL` (15 min). Each reconciler reads its domain's JSONL log via `read_completion_timestamps(domain="<X>", ...)`. The helper's `CompletionTimestamps` dataclass returns both `most_recent_complete_at_utc` (UTC) and `most_recent_complete_date_et` (ET date) so reconcilers don't re-do the UTC→ET conversion.

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch = `main`. Lane worktree per WP; commits inside the worktree.

## Implementation command

```bash
spec-kitty agent action implement WP03 --agent <name>
```

Depends on WP01.

---

## Subtask T011 — TP-02 migrate `scripts/habits/reconcile_completions.py`

**Purpose**: Habits reconciler. Compares cache `done` state against `habits-history.jsonl` to detect operator-side completions Vikunja knows about but Felix's JSONL doesn't yet record. Migrates both halves.

**Steps**:

1. Open `scripts/habits/reconcile_completions.py`. Identify the existing GET phase (the `_http_request("GET", ...)` for tasks) AND the JSONL-read phase (probably already uses `scripts.common.state_log` or inline JSONL parsing).

2. Add canonical imports:
   ```python
   from scripts.common.sync_cache import (
       read_cached_tasks,
       read_cached_task_by_id,
       read_completion_timestamps,
       SLA_NORMAL,
       SLATier,
       CompletionTimestamps,
   )
   ```

3. Add module-level constants:
   ```python
   TOUCHPOINT_SLA: SLATier = SLA_NORMAL
   TOUCHPOINT_NAME = "habits.reconcile_completions"
   STATE_LOG_DIR = Path("/data/services/openclaw/state")  # or import from existing constants
   ```

4. Replace the Vikunja GET phase with helper invocation. Common pattern:
   ```python
   cached_tasks = read_cached_tasks(
       sla=TOUCHPOINT_SLA,
       touchpoint_name=TOUCHPOINT_NAME,
   )
   for task_id, view in cached_tasks.items():
       if view.is_private:
           continue
       if view.fields.get("project_id") != HABITS_PROJECT_ID:
           continue
       # existing reconciler logic now uses view.fields and view.vikunja_updated_at
   ```

5. Replace any direct `done_at` derivation (likely a `task["done_at"]` access in the old GET response) with `read_completion_timestamps`:
   ```python
   ts: CompletionTimestamps = read_completion_timestamps(
       domain="habits",
       task_id=task_id,
       state_log_dir=STATE_LOG_DIR,
   )
   if view.fields.get("done") is True and ts.most_recent_complete_at_utc is None:
       # Cache says done but no completion event in state log → operator-side completion
       # ... existing reconciler logic for "missing JSONL entry"
   elif view.fields.get("done") is True and ts.most_recent_complete_at_utc is not None:
       # Both agree
       continue
   # ... handle other cases per existing reconciler logic
   ```

6. Let `OSError` from the helpers propagate to non-zero exit (same pattern as WP02).

7. Delete the old direct-Vikunja-read code: the `_http_request` GET calls, any `done_at` derivation that depended on the GET response, any Vikunja URL constants used only by the deleted GETs.

8. Update the module docstring: from "Compares Vikunja's `done` state against habits-history.jsonl" to "Compares the sync cache's `done` state (via scripts/common/sync_cache.py) against habits-history.jsonl completion events."

**Files**: `scripts/habits/reconcile_completions.py` (modified).

**Validation**:
- [ ] `grep -E 'urlopen|_http_request.*GET' scripts/habits/reconcile_completions.py` returns zero hits
- [ ] `import urllib.request` either absent or used only by retained code
- [ ] `done_at` references are replaced by `CompletionTimestamps` field accesses
- [ ] Docstring updated

---

## Subtask T012 — TP-02 update `tests/habits/test_reconcile_completions.py` [P]

**Purpose**: Both fixtures (`mock_sync_cache_fixture` + `mock_state_log_fixture`) parameterize the reconciler's two data sources. Test the matrix of agreement/disagreement between cache and state log.

**Steps**:

1. Remove `mock_urlopen` from GET-phase tests.

2. Add `mock_sync_cache_fixture` + `mock_state_log_fixture` to each test function.

3. Test the agreement matrix:

   - **Cache done + state log has complete event** → reconciler agrees, no action
   - **Cache done + state log has NO complete event** → reconciler detects operator-side completion → existing reconciler logic fires (backfill JSONL? log warning?). Assert the existing behavior.
   - **Cache NOT done + state log has stale complete event** → reconciler detects operator-side incompletion. Per spec C-002, cache wins; reconciler reflects the cache.
   - **Cache NOT done + state log has no complete event** → both agree, no action.

4. Cache + state log failure modes:
   - Cache missing → reconciler exits 3 with stderr "freshness pointer missing"
   - Cache stale → reconciler exits 3 with stderr "stale beyond SLA_NORMAL"
   - State log missing → reconciler exits 3 (or surfaces appropriately based on existing behavior)
   - Private task: skip (bulk enumeration)

5. End-to-end test: synthesize 3 tasks (1 agreeing, 1 disagreeing-cache-done, 1 disagreeing-cache-not-done). Run the reconciler. Assert the right actions fired.

**Files**: `tests/habits/test_reconcile_completions.py` (modified).

**Validation**:
- [ ] `python3 -m pytest tests/habits/test_reconcile_completions.py -q` passes
- [ ] Both fixtures combined in tests
- [ ] Agreement matrix tested

---

## Subtask T013 — TP-10 migrate `scripts/escalation/reconcile_completions.py`

**Purpose**: Same shape as T011 but for the escalation domain.

**Steps**:

1. Open `scripts/escalation/reconcile_completions.py`. Note: the existing structure may differ from TP-02's (RQ-2 cites them at different line ranges). Read carefully.

2. Apply the same migration pattern as T011, with two differences:
   - `TOUCHPOINT_NAME = "escalation.reconcile_completions"`
   - `read_completion_timestamps(domain="escalation", ...)` (reads `escalation-history.jsonl` — verify the actual filename; could be `project-9-escalation-history.jsonl` per memory of #518's deployed state). **Verify the actual JSONL file name on office2 before locking the implementation.**
   - The "project-scoped" structure (escalation history is per-project) may require the touchpoint to derive the project_id from the cache before reading the state log. The helper accepts `domain` as a string; the caller can compose `domain=f"escalation-project-{project_id}"` if the JSONL file name is per-project. **The implementer makes this judgment by reading the existing code.**

3. Delete the old direct-read code as in T011.

**Files**: `scripts/escalation/reconcile_completions.py` (modified).

**Validation**:
- [ ] Same grep-based validation as T011
- [ ] State log filename matches the actual on-disk file (verified by `ls /data/services/openclaw/state/escalation/` or similar)

---

## Subtask T014 — TP-10 update `tests/escalation/test_reconcile_completions.py` [P]

**Purpose**: Same as T012 but for the escalation tests. Same agreement matrix; different domain in fixtures.

**Steps**:

1. Same as T012 with `domain="escalation"` (or per-project, per T013's actual choice).

2. If the escalation reconciler is per-project (multiple JSONL files), the test suite parameterizes per-project too.

**Files**: `tests/escalation/test_reconcile_completions.py` (modified).

**Validation**:
- [ ] `python3 -m pytest tests/escalation/test_reconcile_completions.py -q` passes
- [ ] Matches T013's per-project structure

---

## Subtask T015 — TP-12 migrate `scripts/enrichment/reconcile_completions.py`

**Purpose**: Same shape as T011 but for enrichment. **Special check**: per RQ-2 the enrichment reconciler's `read_set` is `id`, `title`, `updated` — it may NOT need `read_completion_timestamps`. Verify before implementing.

**Steps**:

1. Open `scripts/enrichment/reconcile_completions.py`. Read the existing logic carefully:
   - Does it use `done_at` or similar JSONL-derived data? If NO → this becomes a WP02-shape migration (cache-only; drop the `read_completion_timestamps` import).
   - If YES → use the WP03 shape with `domain="enrichment"`.

2. Apply the appropriate pattern. If cache-only: the imports drop to `read_cached_tasks` + `SLA_NORMAL` + `SLATier`. `TOUCHPOINT_NAME = "enrichment.reconcile_completions"`.

3. Delete the old direct-read code.

**Files**: `scripts/enrichment/reconcile_completions.py` (modified).

**Validation**:
- [ ] grep validation
- [ ] If `read_completion_timestamps` is used: state log filename matches
- [ ] If NOT used: import is not present (clean)

---

## Subtask T016 — TP-12 update `tests/enrichment/test_reconcile_completions.py` [P]

**Purpose**: Match T015's shape. Cache-only or cache+state-log per T015's actual decision.

**Steps**:

1. If T015 used both fixtures: same as T012/T014 with `domain="enrichment"`.

2. If T015 used cache-only: same as WP02 T006 shape.

**Files**: `tests/enrichment/test_reconcile_completions.py` (modified).

**Validation**:
- [ ] `python3 -m pytest tests/enrichment/test_reconcile_completions.py -q` passes
- [ ] Matches T015's shape

---

## Test strategy

```bash
python3 -m pytest tests/habits/test_reconcile_completions.py tests/escalation/test_reconcile_completions.py tests/enrichment/test_reconcile_completions.py -q
```

Plus full regression:

```bash
python3 -m pytest tests/sync/ tests/common/ tests/habits/ tests/escalation/ tests/enrichment/ -q
```

---

## Definition of Done

- [ ] All 6 subtasks complete; all listed files committed in the WP03 worktree
- [ ] Full sync + common + habits + escalation + enrichment test suites pass
- [ ] grep validation passes for all 3 reconciler source files
- [ ] All 3 reconcilers have `TOUCHPOINT_SLA = SLA_NORMAL` + `TOUCHPOINT_NAME` constants
- [ ] No edits outside the WP's `owned_files` list
- [ ] No edits to WP01-owned or WP02-owned files
- [ ] Agreement matrix tested in all 3 test suites

---

## Risks and mitigations

- **Domain-specific state-log filenames**: each domain's JSONL file has a slightly different name pattern. The implementer MUST verify the actual filename on office2 (or the deployed precedent) before locking the `domain` argument value. Mitigation: T013 and T015 explicitly mention this verification step.
- **TP-12 may not need state-log lookups**: RQ-2 catalog suggests `read_set = id, title, updated`. If true, T015 becomes a WP02-shape migration. The implementer makes this call by reading the existing code. Mitigation: T015's prompt explicitly handles both cases.
- **Per-project escalation reconcilers**: if the escalation reconciler is multi-project (one JSONL per project), the `domain` argument shape needs per-project composition. Mitigation: T013 acknowledges this and asks the implementer to verify.

---

## Reviewer guidance

When reviewing this WP, verify:
1. **Each reconciler follows the migration-pattern.md 6-step contract**, with the addition of `read_completion_timestamps` where applicable.
2. **State-log filenames match the actual on-disk files**: verify by `ssh office2-claude 'ls /data/services/openclaw/state/'` or by inspecting #518's deployment.
3. **TP-12's shape is correct for its actual needs**: if T015 imports `read_completion_timestamps` and the reconciler doesn't use it, that's a wrong import — flag for cleanup.
4. **Agreement matrix tests cover the disagreement cases**: a reconciler that doesn't trigger on cache-done + state-log-empty is broken.
5. **Privacy boundary respected**: bulk enumeration skips private tasks.

Reject if state-log filenames don't match the actual deployment, if disagreement-matrix tests are missing, or if TP-12 has spurious imports.

---

## References

- Mission spec: `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/spec.md`
- Migration pattern contract: `kitty-specs/migrate-felix-touchpoints-to-sync-cache-01KTAAGX/contracts/migration-pattern.md`
- WP01 helper module: `scripts/common/sync_cache.py` (post-WP01)
- WP01 test fixtures: `tests/common/conftest.py` (post-WP01)
- RQ-2 per-TP citations: `docs/research/felix-vikunja-sync-architecture/findings/rq-2-touchpoints.md` § TP-02, TP-10, TP-12
- State log file locations on office2: `ssh office2-claude 'ls /data/services/openclaw/state/'` (live-probe during implementation)

## Activity Log

- 2026-06-04T23:19:18Z – claude:sonnet:implementer:implementer – shell_pid=28322 – Started implementation via action command
- 2026-06-04T23:43:37Z – claude:sonnet:implementer:implementer – shell_pid=28322 – Ready for review: TP-02 (habits), TP-10 (escalation), TP-12 (enrichment) reconcilers migrated to sync cache; 1261 tests pass (1 pre-existing failure on main unrelated to WP03)
