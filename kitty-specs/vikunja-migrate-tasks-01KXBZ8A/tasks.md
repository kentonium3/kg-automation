# Tasks: Vikunja Task Migration & Project Teardown

**Mission**: vikunja-migrate-tasks-01KXBZ8A | **Branch**: `feat/vikunja-migrate-tasks` → `main`

One cohesive helper on `VikunjaClient` plus a scope-config edit and doc update.
Single work package (matches #715/#716 precedent; minimizes lane friction).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Committed manifest + loader/validator (static invariants) | WP01 | |
| T002 | `list_all_tasks` paginated done-inclusive enumeration + per-project derivation | WP01 | |
| T003 | `preflight` (identity/owner/title/parent, unique t:habit, label_habit-in-13, complex-state block) | WP01 | |
| T004 | `build_plan` (diff live vs manifest → moves/labels/deletes/skipped/blocked) | WP01 | |
| T005 | `move_task` (allowlisted RMW + readback) + `apply_habit_label` | WP01 | |
| T006 | Deletions (test-tasks first, immediate re-list empty-check, children-first, backup-ref gate) + `reconcile` + summary + CLI/`main` + identity guard | WP01 | |
| T007 | `vikunja_scope.py` drop Goals(11) + update scope/escalation tests + goals-as-candidates test | WP01 | |
| T008 | Helper unit tests (idempotency, RMW/readback, fail-loud, paged/done empty-check, fidelity, disjointness, preflight) | WP01 | |
| T009 | Design-doc update (migration-sequence step 5 done + final distribution) | WP01 | |

## Work Packages

### WP01 — Vikunja task-migration helper, manifest, scope config, tests, docs

**Goal**: Ship `scripts/vikunja/migrate_tasks.py` + committed manifest + tests +
the `vikunja_scope.py` edit + design-doc update, implementing FR-001..011 and
NFR-001..004. The live migration is operator-run post-merge (not from this WP).

**Priority**: P1 (MVP — this is the whole mission).

**Independent test**: `pytest tests/vikunja/test_migrate_tasks.py -q` passes
(mocked client), the manifest fidelity test passes, and the updated
escalation/scope tests pass — with no live Vikunja calls.

**Included subtasks**:

- [ ] T001 Committed manifest + loader/validator (WP01)
- [ ] T002 `list_all_tasks` paginated done-inclusive enumeration (WP01)
- [ ] T003 `preflight` identity/target/complex-state validation (WP01)
- [ ] T004 `build_plan` live-vs-manifest diff (WP01)
- [ ] T005 `move_task` allowlisted RMW + readback + `apply_habit_label` (WP01)
- [ ] T006 Deletions + `reconcile` orchestration + summary + CLI (WP01)
- [ ] T007 `vikunja_scope.py` drop Goals(11) + test updates (WP01)
- [ ] T008 Helper unit tests (WP01)
- [ ] T009 Design-doc update (WP01)

**Dependencies**: none.

**Estimated prompt size**: ~550 lines.

**Risks**: silent field loss on move (mitigated by allowlist + readback); empty-check
missing done tasks (mitigated by done-inclusive paginated enumeration); self-block on
test task in doomed project (mitigated by ordering test-deletes first).

**Prompt**: [tasks/WP01-migrate-tasks-helper.md](./tasks/WP01-migrate-tasks-helper.md)

## MVP

WP01 is the entire mission.
