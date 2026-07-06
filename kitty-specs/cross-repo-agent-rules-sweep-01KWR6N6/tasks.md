# Tasks: Cross-Repo Standing Rules Sweep

**Feature Dir**: `/private/tmp/kg-automation-649-clone/kitty-specs/cross-repo-agent-rules-sweep-01KWR6N6`
**Branch**: `feat/cross-repo-standing-rules-sweep`
**Generated**: 2026-07-05T04:08:47Z

## Subtask Index

| ID | Description | Work Package | Parallel |
| --- | --- | --- | --- |
| T001 | Review canonical standing-rules file and linked spec-kitty bug-reporting runbook for stale or duplicated guidance. | WP01 |  |
| T002 | Sweep repo, runbook, constitution, and agent-rule surfaces for candidate universal rules using focused searches. | WP01 |  |
| T003 | Classify high-signal candidates using the promote/link-only/already-represented/local/agent-specific/unclear model. | WP01 |  |
| T004 | Write a live diagnostic candidate classification note with promoted, rejected, and unclear candidates. | WP01 |  |
| T005 | Update `.agents/rules/cross-repo-standing-rules.md` to remove stale spec-kitty paste-file wording and align to the v1.3 runbook flow. | WP02 |  |
| T006 | Promote any universal short rule identified by WP01, preserving the existing concise style and public-copy protections. | WP02 |  |
| T007 | Keep long procedures as links instead of duplicated prose, and preserve all existing protection sections. | WP02 |  |
| T008 | Run docs validation and targeted standing-rules checks from the quickstart. | WP03 |  |
| T009 | Write a live diagnostic validation report covering line count, stale wording checks, protected headings, and any follow-up judgment items. | WP03 |  |
| T010 | Summarize whether #649 is ready for closeout or needs operator judgment. | WP03 |  |

## Work Packages

### WP01 — Candidate Sweep And Classification

**Prompt**: [tasks/WP01-candidate-sweep-and-classification.md](tasks/WP01-candidate-sweep-and-classification.md)
**Priority**: P1
**Independent test**: Candidate classification note exists and ties each high-signal candidate to source evidence and a classification.
**Dependencies**: none
**Estimated prompt size**: ~250 lines

**Included subtasks**:

- [x] T001 Review canonical standing-rules file and linked spec-kitty bug-reporting runbook for stale or duplicated guidance. (WP01)
- [x] T002 Sweep repo, runbook, constitution, and agent-rule surfaces for candidate universal rules using focused searches. (WP01)
- [x] T003 Classify high-signal candidates using the promote/link-only/already-represented/local/agent-specific/unclear model. (WP01)
- [x] T004 Write a mission-owned candidate classification note with promoted, rejected, and unclear candidates. (WP01)

**Implementation sketch**:

Use the search patterns from `quickstart.md`, then read only the line ranges needed to classify candidates. Write findings to `docs/diagnostics/cross-repo-standing-rules-sweep-candidates.md`.

**Parallel opportunities**: None. WP02 depends on the classification note.
**Risks**: Search output can get noisy; prefer source-backed high-signal candidates over exhaustive transcript dumps.

### WP02 — Canonical Standing-Rules Update

**Prompt**: [tasks/WP02-canonical-standing-rules-update.md](tasks/WP02-canonical-standing-rules-update.md)
**Priority**: P1
**Independent test**: `.agents/rules/cross-repo-standing-rules.md` aligns with the current bug-reporting runbook and keeps existing protection sections.
**Dependencies**: WP01
**Estimated prompt size**: ~240 lines

**Included subtasks**:

- [x] T005 Update `.agents/rules/cross-repo-standing-rules.md` to remove stale spec-kitty paste-file wording and align to the v1.3 runbook flow. (WP02)
- [x] T006 Promote any universal short rule identified by WP01, preserving the existing concise style and public-copy protections. (WP02)
- [x] T007 Keep long procedures as links instead of duplicated prose, and preserve all existing protection sections. (WP02)

**Implementation sketch**:

Use WP01's diagnostic classification note as the source of truth. Edit only `.agents/rules/cross-repo-standing-rules.md`, keeping the file under 80 nonblank lines unless the note records explicit operator approval to expand.

**Parallel opportunities**: None. Depends on WP01 and feeds WP03.
**Risks**: Over-promoting local rules would pollute global context; stale summary wording can be just as harmful as a missing link.

### WP03 — Validation And Closeout Readiness

**Prompt**: [tasks/WP03-validation-and-closeout-readiness.md](tasks/WP03-validation-and-closeout-readiness.md)
**Priority**: P1
**Independent test**: Validation report records docs validator result, targeted checks, protected heading checks, and closeout recommendation.
**Dependencies**: WP02
**Estimated prompt size**: ~230 lines

**Included subtasks**:

- [ ] T008 Run docs validation and targeted standing-rules checks from the quickstart. (WP03)
- [ ] T009 Write a mission-owned validation report covering line count, stale wording checks, protected headings, and any follow-up judgment items. (WP03)
- [ ] T010 Summarize whether #649 is ready for closeout or needs operator judgment. (WP03)

**Implementation sketch**:

Run `python tooling/scripts/validate_docs.py` and the targeted `rg` checks from `quickstart.md`. Write results to `docs/diagnostics/cross-repo-standing-rules-sweep-validation.md`.

**Parallel opportunities**: None. Must run after the canonical file edit.
**Risks**: Do not close or comment on #649 without exact-copy approval because issue comments are public copy.
