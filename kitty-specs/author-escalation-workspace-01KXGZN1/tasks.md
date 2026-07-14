# Tasks: Author felix-admin-escalation workspace

**Mission**: author-escalation-workspace-01KXGZN1 | **Branch**: `feat/author-escalation-workspace`

One coherent single-agent authoring refactor (like the #584 capture pilot): re-home escalation's workspace content to #587 owners, absorb #724 fully, and fold the post-plan Codex coherence fixes. All edits are tightly coupled (overlapping files, one review set, no parallelization benefit) → **one work package**.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | SOUL.md → voice/stance only (trim Purpose→stance, privacy→stance, ADD-justification) | WP01 | |
| T002 | USER.md → remove Date handling (keep person-view + Context) | WP01 | |
| T003 | TOOLS.md → receive Date handling; remove Goals(11) from filter+table; fix Z→ET-offset | WP01 | |
| T004 | AGENTS.md → narrow: Z→ET-offset example + enforcement-sentence fix | WP01 | |
| T005 | SKILL.md + escalation-ops.md → remove Goals(11) refs | WP01 | |
| T006 | setup_vikunja.py → remove dormant "Goals" saved-filter block | WP01 | |
| T007 | test_enumerate_candidates.py → de-Goals(11) the generic exclusion test | WP01 | |
| T008 | Validate (escalation-scoped) + row-by-row conservation checklist + suite green | WP01 | |

## Work Packages

### WP01 — Author felix-admin-escalation workspace to #587 + full #724

**Goal**: Re-home escalation's workspace content to #587-canonical owners, fully eliminate Goals(11), fix the date-format + AGENTS-truthfulness coherence issues surfaced by the post-plan Codex review — with zero runtime-behavior change, both #587 invariants preserved.

**Priority**: P1 (the mission's only WP; MVP).

**Independent test**: escalation-scoped `validate_workspace.py` reports `ok: true`; the row-by-row conservation checklist (quickstart §3) all-passes; `pytest scripts/openclaw/agents/tests tests/openclaw tests/escalation` green.

**Included subtasks**:

- [ ] T001 SOUL.md → voice/stance only (WP01)
- [ ] T002 USER.md → remove Date handling (WP01)
- [ ] T003 TOOLS.md → receive Date handling; remove Goals(11); fix Z→ET-offset (WP01)
- [ ] T004 AGENTS.md → narrow Z→ET-offset + enforcement-sentence fix (WP01)
- [ ] T005 SKILL.md + escalation-ops.md → remove Goals(11) (WP01)
- [ ] T006 setup_vikunja.py → remove dormant Goals saved-filter block (WP01)
- [ ] T007 test_enumerate_candidates.py → de-Goals(11) exclusion test (WP01)
- [ ] T008 Validate + conservation checklist + suite green (WP01)

**Implementation sketch**: work the data-model move-table row by row (T001–T004 = the escalation workspace files; T005–T007 = the remaining Goals(11) surfaces); then T008 runs the escalation-scoped validator + conservation checklist + test suite. Reference `data-model.md` (move-table + invariants), `quickstart.md` §1–§3 (exact edits + checks), and `contracts/post-plan-review-resolutions.md` (why each fix).

**Parallel opportunities**: none (single cohesive concern; overlapping files).

**Dependencies**: none.

**Risks**: (1) reducing SOUL privacy must NOT remove the enforceable rule from AGENTS/TOOLS (Invariant A); (2) the Z→ET-offset fix is behavior-adjacent — keep it a faithful offset form; (3) keep the exclusion test's mechanism assertion meaningful after switching off id 11; (4) AGENTS edits limited to the two named narrow changes.

**Estimated prompt size**: ~430 lines (8 subtasks).
