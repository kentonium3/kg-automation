# Implementation Plan: Vikunja Task Migration & Project Teardown

**Branch**: `feat/vikunja-migrate-tasks` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/vikunja-migrate-tasks-01KXBZ8A/spec.md`

## Summary

Ship a deterministic, idempotent Python helper (`scripts/vikunja/migrate_tasks.py`)
that, driven by a committed routing manifest, moves every surviving Vikunja task
into its correct topic project (read-modify-write to avoid POST field-zeroing),
applies the `t:habit` label to Habits tasks, deletes two test-artifact tasks,
and deletes the six emptied legacy projects (children before parents, only when
confirmed empty). It updates `scripts/common/vikunja_scope.py` to drop the
deleted Goals(11) reference, and updates the design doc. The live migration is
operator-run post-merge on office2 as `kent` (Tier-2 backup-gated). The helper
wraps the canonical `VikunjaClient` and mirrors the shape of the shipped
`reconcile_projects.py` (#716).

## Technical Context

**Language/Version**: Python 3.12 (office2 system python3; stdlib-only client)
**Primary Dependencies**: `scripts.common.vikunja_client.VikunjaClient` (stdlib `urllib`, no `requests`); `PyYAML` for the manifest (already a repo dependency)
**Storage**: Live Vikunja (v0.24.x) via REST API over Tailscale; SQLite `vikunja.db` on office2 (Restic-backed)
**Testing**: `pytest` with `--cov-branch`; mocked `VikunjaClient` (no live calls in tests), mirroring `tests/vikunja/test_reconcile_projects.py`
**Target Platform**: office2 (Ubuntu 24.04) for the live run; helper is host-agnostic
**Project Type**: single (Python helper under `scripts/vikunja/`)
**Performance Goals**: N/A — one-shot migration of <80 tasks; per-page cap 50 (Vikunja)
**Constraints**: idempotent; live preflight (owner==kent + target/doomed titles+parents + unique t:habit + complex-state block); fail-loud on non-empty doomed project or wrong identity; allowlisted read-modify-write + post-move readback on every task move; deletions gated on non-empty `--backup-ref`
**Scale/Scope**: 30 task moves, 11 habit labels, 2 task deletes, 6 project deletes; one config module edit; one design-doc edit

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **DIRECTIVE_001 (Architectural Integrity)** — PASS. Migration logic is isolated in one helper on the existing `VikunjaClient` boundary; manifest data is separate from code; no new HTTP path.
- **DIRECTIVE_003 (Decision Documentation)** — PASS. Human-judgment routing is captured in the committed manifest and #717; the HABIT_SELECTOR-stays-project-id decision (C-004) is recorded.
- **DIRECTIVE_010 (Specification Fidelity)** — PASS. Manifest content is asserted (test) to match the locked routing.
- **DIRECTIVE_024 (Locality of Change)** — PASS. Blast radius limited to `scripts/vikunja/`, `scripts/common/vikunja_scope.py`, and the design doc.
- **DIRECTIVE_031 (Context-Aware Design)** — PASS. Uses the Vikunja ubiquitous language (project/task/label) and the two-token model (#715).
- **Change-Risk Tier** — Tier 2 (application state: live DB mutation). NFR-002 enforces a confirmed Restic backup before any destructive op. Live run is operator-invoked; the mission itself does not mutate live state.
- **Rebaseline obligation** — none expected: `scripts/vikunja/**`, `scripts/common/**`, and `docs/design/**` are not audited surfaces. Confirm against `audited-surfaces.json` at merge.

## Project Structure

### Documentation (this mission)

```
kitty-specs/vikunja-migrate-tasks-01KXBZ8A/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/           # Phase 1 output (helper CLI + manifest schema contracts)
```

### Source Code (repository root)

```
scripts/
├── vikunja/
│   ├── migrate_tasks.py              # NEW — the migration helper
│   └── task_migration_manifest.yaml  # NEW — committed routing manifest (human judgment)
└── common/
    └── vikunja_scope.py              # EDIT — drop deleted Goals(11) from ESCALATION_EXCLUDED_PROJECT_IDS

tests/
└── vikunja/
    └── test_migrate_tasks.py         # NEW — mocked-client unit tests (idempotency, RMW, fail-loud)

docs/design/
└── vikunja-configuration-design.md   # EDIT — mark migration-sequence step 5 done; record final ids
```

## Implementation Concern Map

| IC | Concern | Surfaces | Notes |
|----|---------|----------|-------|
| IC-01 | **Manifest** — committed routing data + loader/validator | `task_migration_manifest.yaml`, `migrate_tasks.py::load_manifest` | Schema: `moves` (id→project key), `label_habit` (ids), `delete_tasks` (ids), `delete_projects` (ordered ids), `target_projects` (key→id). Validate: known keys, int ids, delete order children-first, three id-sets pairwise disjoint (M-8), target ids == #716. FR-008. |
| IC-02 | **Task move (allowlisted RMW + readback)** — move without zeroing/dropping fields | `migrate_tasks.py::move_task`, `::_writable_payload` | GET task → POST `/tasks/{id}` copying the writable-field allowlist + new `project_id` (NFR-001, #524); readback asserts only `project_id` changed. Idempotent: skip if already in target. FR-001/FR-011. |
| IC-03 | **Habit labelling** — attach `t:habit` (kent-owned) | `migrate_tasks.py::apply_habit_label` | Resolve label id by title (`t:habit`); PUT `/tasks/{id}/labels` `{label_id}`; skip if already present. Requires kent token (felix-bot 403). FR-002. |
| IC-04 | **Deletions** — test-artifact tasks + emptied projects, ordered, gated, fail-loud | `migrate_tasks.py::delete_test_tasks`, `::delete_projects`, `::list_all_tasks` | Test-task DELETE runs first (H-5); project empty-check enumerates all tasks incl done via paginated `/tasks/all` filtered by project (NFR-004), re-listed immediately before each delete (C-1), refuse if non-empty; children before parents; all gated on non-empty `--backup-ref`. FR-003/FR-004/FR-006, NFR-002/NFR-004. |
| IC-05 | **Preflight + identity guard** — kent-only + live validation | `migrate_tasks.py::_load_token`, `::preflight`, `main` | Token read only from explicit `--token-file` (kent secret); refuse felix-bot path up front. Live preflight: target+doomed projects match title/parent/`owner==kent`, `t:habit` unique, `label_habit` in Habits(13), moved tasks scanned for complex state (block if present). Abort before any mutation. FR-006/FR-010/FR-011 (H-3/H-4). |
| IC-06 | **Summary + plan/apply** — dry-run plan, applied summary | `migrate_tasks.py::build_plan`, `reconcile`, `main` | `build_plan()` computes the mutation set from live state (pure); `--apply` executes; default is dry-run print. Emits counts (moved/labelled/deleted/skipped). FR-009. |
| IC-07 | **Scope config** — drop dead Goals(11) | `scripts/common/vikunja_scope.py` | Remove `11` from `ESCALATION_EXCLUDED_PROJECT_IDS` (Habits 13 stays); leave `HABIT_SELECTOR` on project_id:13 (C-004). Update tests. FR-007, SC-006. |
| IC-08 | **Docs** — design doc | `docs/design/vikunja-configuration-design.md` | Mark migration-sequence step 5 done; note final project distribution. |

## Phase 0 — Research

See [research.md](./research.md). Key questions resolved: Vikunja move-task API shape
and field-preservation (RMW), label-attach endpoint + kent-token requirement,
project-delete cascade + empty-check ordering, and the `vikunja_scope.py` blast
radius (which consumers read `ESCALATION_EXCLUDED_PROJECT_IDS`).

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md): manifest schema + entity fields used.
- [contracts/migrate_tasks_cli.md](./contracts/migrate_tasks_cli.md): CLI interface contract.
- [contracts/manifest_schema.md](./contracts/manifest_schema.md): manifest file contract.
- [quickstart.md](./quickstart.md): operator run procedure (backup → dry-run → apply → verify).

## Branch contract (repeated per runbook)

- Current branch at plan: `feat/vikunja-migrate-tasks`
- Planning/base branch: `feat/vikunja-migrate-tasks`
- Final merge target: `main` (feat → main after post-merge Codex)
- `branch_matches_target`: true (working on the feature branch)
