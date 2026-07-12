# Tasks: Vikunja Project Restructure

**Mission**: vikunja-restructure-projects-01KXBS2P
**Branch**: `feat/vikunja-restructure-projects` → merges into `feat/vikunja-restructure-projects`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Single cohesive deliverable: one idempotent reconciliation helper + its tests +
one design-doc update. One work package.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Token loading (explicit kent token file, no felix-bot fallback) + paginated, owner-scoped project fetch with `null→[]` | WP01 | |
| T002 | Reconcile-plan builder: owner+active+parent match, ambiguity abort, ordered create set, legacy-filter derivation | WP01 | |
| T003 | Create pass: `PUT /projects` (Clients-first parent resolution) + create-response `owner==kent` assertion + verify Inbox | WP01 | |
| T004 | Filter-delete pass: gated on `--delete-legacy` + `--backup-confirmed`, `GET` title readback before `DELETE`, never `-1` | WP01 | |
| T005 | CLI entrypoint: flags, exit codes (0/1/2), `--dry-run`, `--json`, human summary + partial-failure report | WP01 | |
| T006 | Tests: idempotency, ambiguity, owner assertion, pagination page-2, filter readback + non-`1..5` ids, backup gate, mid-run failure, `null→[]` (≥90% cov) | WP01 | |
| T007 | Update `docs/design/vikunja-configuration-design.md` Project Structure to final agreed structure | WP01 | |

## WP01 — Vikunja project + legacy-filter reconciliation helper

**Goal**: Ship `scripts/vikunja/reconcile_projects.py`, an idempotent helper that
creates the canonical topic projects (as kent) and deletes the five legacy saved
filters, with tests and the design-doc reconciled.

**Priority**: P1 (MVP — the whole mission).
**Independent test**: `python3 -m scripts.vikunja.reconcile_projects --dry-run`
prints the correct plan against the live instance; `pytest tests/vikunja/test_reconcile_projects.py` passes ≥90% coverage.

**Included subtasks**:

- [x] T001 Token loading + paginated owner-scoped project fetch with `null→[]` (WP01)
- [x] T002 Reconcile-plan builder with ambiguity abort + legacy-filter derivation (WP01)
- [x] T003 Create pass + create-response owner assertion + verify Inbox (WP01)
- [x] T004 Filter-delete pass (backup-gated, title readback, never `-1`) (WP01)
- [x] T005 CLI entrypoint (flags, exit codes, dry-run, json, partial-failure report) (WP01)
- [x] T006 Tests to ≥90% coverage (WP01)
- [x] T007 Update design doc Project Structure section (WP01)

**Implementation sketch**: build the plan from a paginated, owner-scoped read →
run the additive create pass (parent before children, assert owner) → optionally
run the backup-gated delete pass (readback then delete) → emit summary. CLI wraps
it with the documented flags/exit codes.

**Dependencies**: none.
**Risks**: owner-scoped matching must ignore felix-bot's `Inbox` (id 14); never
emit a project delete; filter ids are environment-specific (readback guards).
**Estimated prompt size**: ~380 lines.

**Prompt**: [tasks/WP01-reconcile-projects-helper.md](./tasks/WP01-reconcile-projects-helper.md)
