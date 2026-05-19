# Tasks: Habits native repeat + JSONL state

**Mission**: `habits-native-repeat-jsonl-state-01KS0M59`
**Mission ID**: `01KS0M59313RF0WVJZTXYDJC6C`
**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Source issue**: [#306](https://github.com/kentonium3/kg-automation/issues/306)
**Branch strategy**: planning_base=`main`, merge_target=`main`, branch_matches_target=`true`

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `scripts/habits/identify_workout_task.py` (Vikunja lookup helper) | WP01 | [P] |
| T002 | Create `tests/habits/__init__.py` + `tests/habits/conftest.py` (shared fixtures: mocked vikunja client, sample tasks, common test helpers) | WP01 | |
| T003 | Create `tests/habits/test_identify_workout_task.py` | WP01 | |
| T004 | Implement `scripts/habits/migrate_schedule.py` — `load_schedule()` + YAML schema validation | WP02 | |
| T005 | Implement `scripts/habits/migrate_schedule.py` — `capture_snapshot()` + `apply_schedule()` (patch / retire / create) | WP02 | |
| T006 | Implement `scripts/habits/migrate_schedule.py` — `rollback()` + `__main__` CLI surface | WP02 | |
| T007 | Create `tests/habits/test_migrate_schedule.py` (covers T004-T006 with mocked Vikunja API) | WP02 | |
| T008 | Create `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml` with the 11 operations (workout task ID as TBD placeholder) | WP02 | [P] |
| T009 | Implement `scripts/habits/record_completion.py` — `record()` three-write atomic helper + `__main__` CLI | WP03 | |
| T010 | Implement `scripts/habits/reconcile_completions.py` — `reconcile()` backfill + drift detection + `__main__` CLI | WP03 | |
| T011 | Create `tests/habits/test_record_completion.py` (idempotency, ordering, exit codes) | WP03 | [P] |
| T012 | Create `tests/habits/test_reconcile_completions.py` (backfill + drift) | WP03 | [P] |
| T013 | Implement `scripts/habits/query_active_habits_v2.py` (Vikunja-native filter) + CLI | WP04 | |
| T014 | Implement `scripts/habits/exclude_completed_v2.py` (state_log read) + CLI | WP04 | |
| T015 | Create `tests/habits/test_query_active_habits_v2.py` | WP04 | [P] |
| T016 | Create `tests/habits/test_exclude_completed_v2.py` | WP04 | [P] |
| T017 | Update `docs/design/architecture/data/data-flows.json` — add new write path (habits agent → state_log) + new read path (exclude_completed_v2 → state_log.read) | WP04 | [P] |
| T018 | Update `docs/design/architecture/data/service-inventory.json` — register the 6 new scripts under `scripts/habits/` | WP04 | [P] |

`[P]` = parallel-safe (different file/concern; no inter-subtask dependency within the WP)

---

## Work Packages

### WP01 — Foundation: workout lookup + tests/habits scaffolding

**Prompt**: [tasks/WP01-foundation-lookup-and-test-scaffold.md](tasks/WP01-foundation-lookup-and-test-scaffold.md)
**Goal**: Establish the `tests/habits/` package with shared fixtures, plus deliver the `identify_workout_task.py` lookup helper. This unblocks WP02-WP04 (which all consume the conftest fixtures) and gives the operator the lookup tool needed for the WP02 migration.
**Priority**: P0 (foundation; blocks all downstream WPs)
**Dependencies**: none
**Estimated prompt size**: ~250 lines

#### Included subtasks

- [ ] T001 Create `scripts/habits/identify_workout_task.py`
- [ ] T002 Create `tests/habits/__init__.py` + `tests/habits/conftest.py`
- [ ] T003 Create `tests/habits/test_identify_workout_task.py`

#### Implementation sketch

1. Build the lookup helper (T001) — small self-contained urllib call to `GET /api/v1/tasks` filtered by candidate IDs, returns one match for `r"workout"` case-insensitive title.
2. Create the shared test scaffolding (T002): `conftest.py` with mocked-urllib fixtures (canned Vikunja responses for habit tasks), a `sample_habit_records` fixture matching the Phase 2 state_log shape, and a `mock_state_log_dir` fixture that monkey-patches `STATE_DIR` to a temp path.
3. Test the lookup helper (T003) against the conftest fixtures.

#### Parallel opportunities

T001 is independent of T002/T003 — could be implemented first or in parallel.

#### Risks

- **Lookup may match multiple tasks** if Kent has historical "workout" entries (archived or otherwise). Helper handles by returning the first match among the candidate IDs and surfacing the ambiguity via exit code 1.
- **fcntl-based state_log in conftest**: the `mock_state_log_dir` fixture monkey-patches `STATE_DIR` — verify this propagates correctly to subprocess-based tests in later WPs.

#### Success criteria

Verified by code structure + WP01 tests:
- NFR-006 (zero new third-party deps)
- C-006 (dual module/CLI surface — establishes the pattern)

---

### WP02 — Migration helper: load, validate, snapshot, apply, rollback

**Prompt**: [tasks/WP02-migrate-schedule-helper.md](tasks/WP02-migrate-schedule-helper.md)
**Goal**: Build the config-driven migration helper that PATCHes the 7 daily habit tasks, retires the workout task, creates the 3 new MWF strength-training tasks, persists a rollback snapshot, and supports `--rollback` to reverse. Plus the `habits-schedule.yaml` itself.
**Priority**: P0 (the Tier-2 production-state mutation tool)
**Dependencies**: **WP01** (test fixtures + lookup output)
**Estimated prompt size**: ~480 lines

#### Included subtasks

- [ ] T004 Implement `scripts/habits/migrate_schedule.py` — `load_schedule()` + YAML schema validation
- [ ] T005 Implement `scripts/habits/migrate_schedule.py` — `capture_snapshot()` + `apply_schedule()`
- [ ] T006 Implement `scripts/habits/migrate_schedule.py` — `rollback()` + `__main__` CLI
- [ ] T007 Create `tests/habits/test_migrate_schedule.py`
- [ ] T008 Create `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml`

#### Implementation sketch

1. Build the YAML loader + validator (T004). Schema strictly enforced per `contracts/config.md`; refuse to run on schema error.
2. Build snapshot capture (T005a) — GET each touched task, persist BEFORE state to `/data/services/openclaw/state/habits-pre-phase3-snapshot.json`.
3. Build the apply loop (T005b) — iterate operations, dispatch to `_patch_op`, `_retire_op`, `_create_op` handlers, persist `applied_changes` incrementally so partial failure is recoverable.
4. Build rollback (T006a) — reverse-iterate `applied_changes`, replay inverse ops.
5. Build CLI wrapper (T006b) — argparse with `--schedule`, `--snapshot-out`, `--dry-run`, `--rollback`, `--snapshot-file`, `--token-file`.
6. Write exhaustive tests (T007): schema validation paths, dry-run no-HTTP, happy-path apply with mocked Vikunja, mid-batch failure with partial snapshot, rollback from partial snapshot.
7. Author the mission's `habits-schedule.yaml` (T008) with 7 daily PATCHes (IDs 14, 15, 16, 18, 19, 20, 65), 1 retire (TBD placeholder for workout ID), 3 creates.

#### Parallel opportunities

T008 (the YAML file) is independent of T004-T007 — can be authored anytime during the WP. T011/T012 (downstream WP03's test files) and T015/T016 (downstream WP04's test files) can run in parallel with this WP as long as they don't import from migrate_schedule (they don't).

#### Risks

- **Vikunja API quirks** (G3, G4 from #317 Verified gotchas): the `create` op uses `PUT /api/v1/projects/<id>/tasks` (per Vikunja convention — verify in canary); the verify-readback (if added) must consult `created_by.username` not `author.username` for TASK objects (G3 inversion).
- **Snapshot atomicity**: writing the snapshot incrementally means an OS crash mid-apply could leave a `applied_changes` entry recorded but not flushed. Use `os.fsync()` after each append, or write a single final snapshot at the end. The contract pulls toward incremental for recoverability — use fsync.
- **Pre-flight verification that `repeat_after=0`** before retire-op: refuse to retire if the BEFORE state has `repeat_after > 0` (else Vikunja auto-advance would un-retire).
- **Tier 2 protocol enforcement**: the helper itself can't verify the Restic snapshot. The CLI should ABORT with a clear message if invoked without `--dry-run` AND without an env-var override `FELIX_TIER2_PREFLIGHT_OK=yes` (operator confirmation). This forces the operator to acknowledge Tier 2 pre-flight.

#### Success criteria (from spec.md)

Mapped to:
- FR-001, FR-002, FR-003, FR-004, FR-005, FR-012, FR-014
- NFR-001 (capture <30s), NFR-004 (rollback <5min)
- C-002, C-003, C-004, C-007

---

### WP03 — Completion + reconcile helpers

**Prompt**: [tasks/WP03-record-completion-and-reconcile.md](tasks/WP03-record-completion-and-reconcile.md)
**Goal**: Build the two Phase 5-consumed helpers — `record_completion.py` (three-write atomic completion) and `reconcile_completions.py` (Vikunja-UI backfill + drift detection). Both are testable standalone but won't be invoked by the cron until Phase 5 cutover.
**Priority**: P0 (foundation for Phase 5 callers)
**Dependencies**: **WP01** (test fixtures)
**Estimated prompt size**: ~350 lines

#### Included subtasks

- [ ] T009 Implement `scripts/habits/record_completion.py` — `record()` three-write atomic helper + `__main__` CLI
- [ ] T010 Implement `scripts/habits/reconcile_completions.py` — `reconcile()` backfill + drift detection + `__main__` CLI
- [ ] T011 Create `tests/habits/test_record_completion.py`
- [ ] T012 Create `tests/habits/test_reconcile_completions.py`

#### Implementation sketch

1. Build record_completion (T009) per ADR Q3-D — three-write atomicity: idempotency check via `state_log.read` first, then Vikunja POST `done=true`, then Vikunja PUT comment, then state_log.append. Loud failure with stderr naming the failing step.
2. Build reconcile_completions (T010) — enumerate active habit tasks, detect missing JSONL entries (backfill from `done_at`), detect drift (JSONL says complete, Vikunja says done=false), exit 0 even with drift (informational).
3. Test exhaustively (T011, T012): idempotency on duplicate, each-write-failure path, drift detection, backfill correctness.

#### Parallel opportunities

T009 and T010 are independent modules; could be implemented serially or in parallel. T011/T012 are file-level parallel after their source counterparts.

#### Risks

- **Three-write ordering invariant** (research D4): Vikunja done=true first, then comment, then state_log. If document violates the ADR Q3-D ordering, the failure modes change. Implementer must follow research D4 precisely.
- **Idempotency pre-flight** must use `state_log.read("habits", task_id, date)` and check for any record with the same state — not just existence. Two completions with different state values (e.g., "incomplete" then "complete") are NOT duplicates.
- **Vikunja G4** (comment endpoint is PUT not POST) — explicit in the implementation.
- **Vikunja G3** (comment attribution on `author.username` not `created_by`) — if the canary verifies readback, consult `author.username`.

#### Success criteria (from spec.md)

Mapped to:
- FR-006, FR-007, FR-008, FR-009
- NFR-002 (<5s p95), NFR-003 (<60s reconcile)
- C-005 (state log canonical)

---

### WP04 — v2 query/exclude variants + architecture documentation

**Prompt**: [tasks/WP04-v2-variants-and-arch-docs.md](tasks/WP04-v2-variants-and-arch-docs.md)
**Goal**: Build the two parallel `_v2.py` variants (query_active_habits_v2, exclude_completed_v2) that Phase 5 cutover will swap to. Plus update `data-flows.json` and `service-inventory.json` to register the new write/read paths and scripts. This WP closes the Phase 3 functional surface.
**Priority**: P0 (completes Phase 3 deliverables)
**Dependencies**: **WP01** (test fixtures). Phase 2's state_log library provides everything exclude_completed_v2 needs.
**Estimated prompt size**: ~400 lines

#### Included subtasks

- [ ] T013 Implement `scripts/habits/query_active_habits_v2.py` — `query_active_today()` + `__main__` CLI
- [ ] T014 Implement `scripts/habits/exclude_completed_v2.py` — `exclude_completed_for_today()` + `__main__` CLI
- [ ] T015 Create `tests/habits/test_query_active_habits_v2.py`
- [ ] T016 Create `tests/habits/test_exclude_completed_v2.py`
- [ ] T017 Update `docs/design/architecture/data/data-flows.json` — add new write/read paths
- [ ] T018 Update `docs/design/architecture/data/service-inventory.json` — register the 6 new `scripts/habits/` files

#### Implementation sketch

1. Build query_active_habits_v2 (T013) — GET `/api/v1/projects/<id>/tasks` with the native filter `due_date <= now/d AND done = false`. Pretty-print JSONL on stdout.
2. Build exclude_completed_v2 (T014) — read stdin as JSONL (active habits), for each call `state_log.read("habits", task_id, date=today, state="complete")`, return tasks with empty result.
3. Tests (T015, T016) verify standalone correctness.
4. Update data-flows.json (T017) — add two entries: habits-agent → state_log (write), exclude_completed_v2 → state_log (read). Don't remove the existing comment-based flows; they remain live until Phase 5.
5. Update service-inventory.json (T018) — register the 6 new scripts as files under their host (office2) with brief purpose annotations.

#### Parallel opportunities

T017 and T018 (doc updates) are independent of T013-T016 (code). All four code+test pairs are file-level independent.

#### Risks

- **Native filter expression format**: Vikunja's filter syntax is `due_date <= now/d AND done = false`. Verify via canary that this syntax is accepted by v0.24.6. Document any deviation in the Verified API gotchas appendix.
- **Stdin parsing in exclude_completed_v2**: must handle empty input, malformed JSON lines, and the case where state_log.read raises (e.g., on perm error). Exit 1 only on hard failure.
- **Doc JSON validity**: data-flows.json and service-inventory.json are validated by the CI doc validator. Run `python3 tooling/scripts/validate_docs.py` after edits.

#### Success criteria (from spec.md)

Mapped to:
- FR-010, FR-011, FR-013
- NFR-005 (coverage ≥85% across the full habits/* test suite)
- C-001 (old path unchanged — the `_v2.py` variants are siblings, not replacements)

---

## Dependency graph

```
WP01 (foundation: lookup + test scaffold, no deps)
  ├── WP02 (migration helper, depends on WP01)
  ├── WP03 (record + reconcile, depends on WP01)
  └── WP04 (v2 variants + arch docs, depends on WP01)
```

After WP01 lands, WP02/WP03/WP04 can run **in parallel** — they touch different source files, different test files, and don't share any code path beyond the conftest fixtures.

## MVP scope

WP01 + WP02 deliver the Tier-2 production-state migration capability. That alone fixes the morning check-in MWF bug (#306's evidence comment) once the operator runs the migration. WP03 + WP04 round out the new code paths but don't change live behavior until Phase 5 cutover. **MVP = WP01 + WP02** (Phase 3's bare-minimum value).

Full mission requires all 4 WPs because the spec's success criteria span all of them.

## Parallelization summary

**Across WPs** (after WP01 lands):
- WP02, WP03, WP04 can all start in parallel — each is mutually independent at the file level.

**Within each WP**:
- WP01: T001 is parallel-safe with T002+T003 (different files).
- WP02: T008 (the YAML file) is parallel-safe with T004-T007 (source/test code).
- WP03: T011/T012 (test files) are parallel-safe with each other after their sources land.
- WP04: T017/T018 (doc updates) parallel with T013-T016 (code/tests).

## Notes for implementers

- All Vikunja API calls in Phase 3 helpers MUST authenticate as `felix-bot` (read the token from `/data/services/openclaw/secrets/vikunja-api`). The token file is mode 0600 claude:claude (per Phase 1 setup); helpers must NOT log token contents.
- The `scripts.common.state_log` library from Phase 2 (#305, commit 231e880) is the canonical JSONL substrate. Phase 3 helpers import from it, never re-implement.
- Verified Vikunja API gotchas (per `docs/design/research/vikunja-task-model-research.md` § Verified API gotchas): G3 (comment attribution on `author.username` not `created_by`) and G4 (comment-create endpoint is PUT not POST) apply to `record_completion.py` writes. The other gotchas (G1, G2) apply only to project-sharing operations which Phase 3 does not perform.
- No modifications to `AGENTS.md` anywhere in Phase 3 (C-002). The cron continues invoking the old scripts until Phase 5 cutover (#308) updates the agent's standing orders.
- Tier 2 pre-flight (C-007): the migration helper must enforce a confirmation gate (env var `FELIX_TIER2_PREFLIGHT_OK=yes` OR `--dry-run`) before any destructive HTTP call. The Restic snapshot itself is operator-confirmed, not script-checked.
