# Tasks: Observation-Digest Log Repoint & Decommission

**Mission**: observation-digest-repoint-01KWS2E2 | **Branch**: `fix/observation-digest-repoint`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Tests are in scope (spec NFR-004/NFR-005/FR-001 require them).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Repoint `config.py` `log_dir` default to absolute vault constant | WP01 | |
| T002 | Update `~/second-brain/agents/logs` docstrings in config/log_action/summarize | WP01 | [P] |
| T003 | Unit test: resolved `log_dir` == vault path under any `HOME`; override honored | WP01 | |
| T004 | `observation_migration.py`: atomic union-merge (temp+fsync+os.replace), glob only `agents/logs/*/*.jsonl` | WP02 | |
| T005 | `observation_migration.py`: vault-writability check + `migrate_logs()` flow (idempotent) | WP02 | |
| T006 | `migrate-observation-logs.py` executable wrapper (shebang/+x/shim; --dry-run default/--apply) | WP02 | |
| T007 | Tests: union-merge union+atomic; dry-run subprocess exits 0 no-mutation; +x/shim; no descendant path in output | WP02 | |
| T008 | `observation_decommission.py`: precondition gate (snapshot+coverage, origin, quiesce+no-proc, inbox-prescan mtime) → abort-on-fail | WP03 | |
| T009 | `observation_decommission.py`: final merge under quiesce + root-only `rm -rf` (no walk/rglob/git-status-ignored); restart timer | WP03 | |
| T010 | `decommission-observation-stray-tree.py` executable wrapper (shebang/+x/shim; flags incl. --attest-backup-coverage) | WP03 | |
| T011 | Tests: each gate-abort path → non-zero + no delete; dry-run subprocess exits 0 no-mutation; no `_private`/descendant path in output/errors | WP03 | |
| T012 | `deploys/queued/0008-migrate-observation-logs.yaml` (tier 2, snapshot pre, migrate apply, writability post) | WP04 | |
| T013 | `deploys/queued/0009-decommission-observation-stray-tree.yaml` (tier 2, snapshot pre, decommission apply, `test ! -e` post) | WP04 | |
| T014 | `service-inventory.json` felix-core-digest: repoint input_path, fix stale output_path + exec_start, remove retention notes, `updated_by:659` | WP05 | |
| T015 | `data-flows.json` observation-digest: repoint log paths, remove retention note, `updated_by:659` | WP05 | [P] |
| T016 | Regenerate md views (service-inventory.md, data-flows.md/.view.md, service-dependencies.view.md); run architecture-data validator | WP05 | |

## Work Packages

### WP01 — Repoint observation log_dir default (Phase 1 code)
- **Goal**: `config.py` `log_dir` default resolves to `/home/kgale/second-brain/agents/logs` independent of `HOME`; docstrings corrected.
- **Priority**: P1 (MVP — the actual defect fix). **Independent test**: unit test asserts resolved path under arbitrary `HOME`.
- **Subtasks**: - [ ] T001 (WP01) · - [ ] T002 (WP01) · - [ ] T003 (WP01)
- **Dependencies**: none. **Requirements**: FR-001, FR-007.
- **Prompt**: [tasks/WP01-repoint-log-dir.md](./tasks/WP01-repoint-log-dir.md) (~180 lines)

### WP02 — Migration logic module + Phase-1 entrypoint (Phase 1)
- **Goal**: importable `observation_migration.py` (atomic union-merge, writability) + `migrate-observation-logs.py` wrapper; non-destructive.
- **Priority**: P1. **Independent test**: dry-run exits 0 no-mutation; union-merge preserves union atomically.
- **Subtasks**: - [ ] T004 (WP02) · - [ ] T005 (WP02) · - [ ] T006 (WP02) · - [ ] T007 (WP02)
- **Dependencies**: none. **Requirements**: FR-002, FR-005.
- **Prompt**: [tasks/WP02-migrate-logs-module.md](./tasks/WP02-migrate-logs-module.md) (~230 lines)

### WP03 — Phase-2 decommission entrypoint (Phase 2)
- **Goal**: `observation_decommission.py` (gated, quiesced, root-only delete, `_private`-safe) + `decommission-observation-stray-tree.py` wrapper.
- **Priority**: P1 (destructive; highest care). **Independent test**: every gate-abort path returns non-zero without deleting.
- **Subtasks**: - [ ] T008 (WP03) · - [ ] T009 (WP03) · - [ ] T010 (WP03) · - [ ] T011 (WP03)
- **Dependencies**: WP02 (imports merge helper). **Requirements**: FR-003, FR-004, FR-005.
- **Prompt**: [tasks/WP03-decommission-entrypoint.md](./tasks/WP03-decommission-entrypoint.md) (~260 lines)

### WP04 — Deploy manifests (two, staged)
- **Goal**: two `deploys/queued` manifests (Phase 1 migrate; Phase 2 decommission), Tier-2, snapshot-gated.
- **Priority**: P2. **Independent test**: manifest-schema validator passes.
- **Subtasks**: - [ ] T012 (WP04) · - [ ] T013 (WP04)
- **Dependencies**: WP02, WP03. **Requirements**: FR-008, FR-009.
- **Prompt**: [tasks/WP04-deploy-manifests.md](./tasks/WP04-deploy-manifests.md) (~150 lines)

### WP05 — Architecture-doc corrections
- **Goal**: correct `service-inventory.json` + `data-flows.json` (+ md views) to reflect the vault paths, remove `#659` retention notes, fix stale output_path/exec_start.
- **Priority**: P2. **Independent test**: architecture-data validator passes; no `#659` retention notes remain.
- **Subtasks**: - [ ] T014 (WP05) · - [ ] T015 (WP05) · - [ ] T016 (WP05)
- **Dependencies**: none. **Requirements**: FR-006.
- **Prompt**: [tasks/WP05-arch-doc-corrections.md](./tasks/WP05-arch-doc-corrections.md) (~150 lines)

## Dependencies

- WP03 depends on WP02 (shared union-merge helper).
- WP04 depends on WP02 + WP03 (manifests invoke the entrypoints).
- WP01, WP05 independent (parallelizable).

## MVP

WP01 + WP02 (Phase 1: repoint + migrate) is the minimal shippable increment; WP03/WP04 add the
gated decommission (Phase 2); WP05 keeps docs truthful.
