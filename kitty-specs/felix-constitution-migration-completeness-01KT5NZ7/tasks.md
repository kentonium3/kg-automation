# Tasks: Felix Constitution — Migration Completeness Directive

**Mission**: `felix-constitution-migration-completeness-01KT5NZ7`
**Planning base**: `main` | **Merge target**: `main`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Insert Directive 7 into `docs/constitution/FELIX-CONSTITUTION.md` between Directive 6 and the Privacy section | WP01 | | [D] |
| T002 | Run SC verification greps (existence + positioning + incident citations) | WP01 | | [D] |
| T003 | Audit the rest of the repo for any directive-index that needs an update (none expected per spec C-004) | WP01 | | [D] |

3 subtasks, single WP. Trivial documentation edit.

## Work Package WP01 — Add Directive 7

**Goal**: Land Directive 7 in the Felix Constitution. The directive codifies the principle that a migration is not done until all transitional artifacts are removed, with explicit conditions for deferring cleanup to a follow-on issue.

**Priority**: P1 (sole WP)

**Independent test**: Quickstart greps return expected matches; no other constitution content changed.

**Estimated prompt size**: ~250 lines

### Included subtasks

- [x] T001 Insert Directive 7 into `docs/constitution/FELIX-CONSTITUTION.md` (WP01)
- [x] T002 Run SC verification greps (WP01)
- [x] T003 Repo-wide audit for directive-index references (WP01)

### Dependencies

None.

## Branch strategy

- Planning base: `main`
- Merge target: `main`
- Single execution worktree via `lanes.json`.
