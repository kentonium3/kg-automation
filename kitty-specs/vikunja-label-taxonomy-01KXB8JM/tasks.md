# Tasks: Vikunja Label Taxonomy

**Mission**: vikunja-label-taxonomy-01KXB8JM
**Branch**: `feat/vikunja-label-taxonomy` → merges into `feat/vikunja-label-taxonomy`

One cohesive work package: a single-module reconcile helper plus its test suite
and the design-doc color addition. The live run is a post-merge operational step
(see `quickstart.md`), not a WP.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Declare taxonomy (12 labels: title/color/dimension) + legacy (3 titles) constants | WP01 | |
| T002 | Paginated label listing + duplicate-title detection | WP01 | |
| T003 | Create pass: create-missing / already-present / color-mismatch fail-loud | WP01 | |
| T004 | Delete pass: `--delete-legacy` + mandatory `--backup-confirmed` gate, delete-all-matches, 404 re-list | WP01 | |
| T005 | CLI + reporting: argparse flags, `--dry-run`, `--json`, overrides, outcome table, title→id map, exit codes | WP01 | |
| T006 | Add color column to `docs/design/vikunja-configuration-design.md` label tables | WP01 | [P] |
| T007 | Tests: create / skip / color-mismatch / duplicate-title / idempotent + design-doc fidelity | WP01 | |
| T008 | Tests: delete gate + delete-all + 404 re-list + failure modes + `--dry-run` no-mutation | WP01 | |

## Work Packages

### WP01 — Taxonomy reconcile helper + tests + design-doc colors

- **Goal**: Ship `scripts/vikunja/create_taxonomy_labels.py` — a deterministic, idempotent helper that reconciles the live Vikunja label set toward the 12-label taxonomy and (behind an explicit, backup-gated flag) deletes the 3 legacy labels — with a full mocked-client test suite, and add the color column to the design doc so it stays the taxonomy authority.
- **Priority**: MVP (the whole mission).
- **Independent test**: `make test` (the new `tests/vikunja/test_create_taxonomy_labels.py` passes, no live calls); a `--dry-run` against a fake client prints the expected plan.
- **Dependencies**: none.
- **Estimated prompt size**: ~500 lines (8 subtasks).
- **Included subtasks**:
  - [x] T001 Declare taxonomy + legacy constants (WP01)
  - [x] T002 Paginated listing + duplicate-title detection (WP01)
  - [x] T003 Create pass (create / already-present / color-mismatch) (WP01)
  - [x] T004 Delete pass (backup-gated, delete-all, 404 re-list) (WP01)
  - [x] T005 CLI + reporting + exit codes (WP01)
  - [x] T006 Design-doc color column (WP01)
  - [x] T007 Tests: create/idempotency/fidelity (WP01)
  - [x] T008 Tests: delete/failure-modes/dry-run (WP01)
- **Implementation sketch**: constants → list+dedup → create pass → delete pass → CLI/report → doc edit → tests. See `contracts/create_taxonomy_labels.md` and `data-model.md` for the authoritative behavior.
- **Risks**: id-vs-title (identify by title, mutate by id); `per_page` ≤ 50; create = `PUT /labels`; destructive delete must be gated; mock must mirror the real `VikunjaClient` surface.
- **Prompt**: `tasks/WP01-taxonomy-reconcile-helper.md`
