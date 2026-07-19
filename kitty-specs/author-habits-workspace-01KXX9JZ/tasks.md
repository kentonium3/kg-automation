# Tasks: Author felix-admin-habits workspace

**Mission**: author-habits-workspace-01KXX9JZ | **Branch**: `feat/author-habits-workspace`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Single work package (the #584/#585 authoring precedent): the whole refactor is one cohesive,
tightly-coupled content edit to one agent's workspace + a bounded doc-sync. Post-merge
deploy/parity/smoke is operator-owned in [quickstart.md](./quickstart.md) §5–9, not a WP
(a `kitty-specs`-owning WP is rejected by finalize).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----|
| T001 | SOUL.md → voice + one-line privacy stance (remove Purpose, Weekly dup, full Privacy) | WP01 | |
| T002 | USER.md → filtered person-view; remove Date handling; correct false "reporting" claim | WP01 | |
| T003 | TOOLS.md → de-inline volatile IDs (point to vikunja_refs); receive date-handling; keep completion contract | WP01 | |
| T004 | AGENTS.md → narrow truthfulness fix only if it names SOUL as a privacy-enforcement home | WP01 | |
| T005 | service-inventory.md → correct weekly-report rows to match service-inventory.json (FR-012) | WP01 | |
| T006 | Validate (habits-scoped ok:true) + row-by-row conservation + prompt-behavior static diff | WP01 | |

## WP01 — Author habits workspace + weekly-report doc-sync

**Goal**: Re-home habits workspace content to #587 ownership, correct the stale scope claim,
de-inline volatile IDs, fix the repo-wide weekly-report doc drift, and prove the set is
coherent, invariant-green, and behavior-preserving.

**Priority**: MVP (the only WP).

**Independent test**: `python3 -m scripts.openclaw.agents.validate_workspace --json` reports
`felix-admin-habits` `ok: true`; the data-model conservation invariants all hold; the AGENTS
tick/reply workflow is byte-unchanged (except FR-009 if applicable).

**Included subtasks**:
- [ ] T001 SOUL.md → voice + one-line privacy stance (WP01)
- [ ] T002 USER.md → filtered person-view; remove Date handling; correct reporting claim (WP01)
- [ ] T003 TOOLS.md → de-inline IDs; receive date-handling; keep completion contract (WP01)
- [ ] T004 AGENTS.md → narrow truthfulness fix only if warranted (WP01)
- [ ] T005 service-inventory.md → weekly-report rows match the JSON (WP01)
- [ ] T006 Validate + conservation + prompt-behavior static diff (WP01)

**Implementation sketch**: apply the `data-model.md` move-table file by file; run the validator
and the row-by-row conservation checklist from `quickstart.md`; confirm AGENTS workflow byte
diff; leave post-merge deploy/parity/smoke to the operator per quickstart §5–9.

**Dependencies**: none.

**Risks**: Inv-A regression (strip enforceable privacy from all files); dropping weekly-out-of-scope
from both AGENTS and SOUL; treating the helper-output diff as a prompt-behavior gate (it isn't —
pair with static AGENTS diff + smoke); over-editing AGENTS beyond FR-009.

**Estimated prompt size**: ~320 lines (6 subtasks).

**Prompt**: [tasks/WP01-author-habits-workspace.md](./tasks/WP01-author-habits-workspace.md)
