# Tasks: Doc Audit Infrastructure

**Feature**: 020-doc-audit-infrastructure
**Mission**: software-dev
**Created**: 2026-04-08T19:40:49Z
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Subtask Index

| ID | Description | Work Package | Parallel |
|----|-------------|-------------|----------|
| T001 | Create doc-domain-map.json with all 8 area labels | WP01 | — |
| T002 | Create docs-debt.md issue template | WP01 | [P] |
| T003 | Validate domain map covers all active docs from INDEX.md | WP01 | — |
| T004 | Add `[doc-audit]` commit tag convention to CLAUDE.md | WP02 | [P] |
| T005 | Create doc-audit-trigger.yml (post-merge action) | WP02 | — |
| T006 | Create doc-audit-weekly.yml (weekly cron stub) | WP02 | [P] |
| T007 | Update docs/INDEX.md to reference domain map and template | WP02 | [P] |
| T008 | Update docs/design/architecture/README.md Data Files table | WP02 | [P] |

---

## Phase 1: Foundation (Setup)

### WP01 — Domain Map & Issue Template

**Prompt**: [WP01-domain-map-and-issue-template.md](tasks/WP01-domain-map-and-issue-template.md)
**Priority**: P1 — must exist before WP02 (Actions reference the domain map)
**Dependencies**: none
**Subtasks**: T001, T002, T003
**Estimated prompt size**: ~350 lines

**Goal**: Create the doc-domain-map.json mapping all 8 area labels to their
affected documentation files, and the docs-debt issue template for filing
documentation gaps.

**Included subtasks**:
- [ ] T001: Create doc-domain-map.json at docs/design/architecture/data/
- [ ] T002: Create .github/ISSUE_TEMPLATE/docs-debt.md
- [ ] T003: Validate domain map completeness against INDEX.md

**Implementation sketch**:
1. Build JSON object keyed by area label (8 entries)
2. Map each area to its list of affected doc paths (relative to repo root)
3. Create issue template following existing template pattern (bug.md as reference)
4. Cross-check map entries against docs/INDEX.md to ensure all active docs appear

**Parallel opportunities**: T001 and T002 are independent and can be written in parallel.
T003 depends on T001 completion.

**Risks**: Domain map may miss newly-added docs — T003 mitigates this.

---

## Phase 2: Automation & References

### WP02 — Commit Convention, GitHub Actions & Index Updates

**Prompt**: [WP02-actions-and-references.md](tasks/WP02-actions-and-references.md)
**Priority**: P1
**Dependencies**: WP01 (workflows reference doc-domain-map.json)
**Subtasks**: T004, T005, T006, T007, T008
**Estimated prompt size**: ~450 lines

**Goal**: Add the `[doc-audit]` commit tag convention to CLAUDE.md, create
both GitHub Actions workflows (post-merge trigger and weekly cron stub),
and update INDEX.md and architecture README to reference the new artifacts.

**Included subtasks**:
- [ ] T004: Add `[doc-audit]` tag convention to CLAUDE.md Git Workflow section
- [ ] T005: Create .github/workflows/doc-audit-trigger.yml
- [ ] T006: Create .github/workflows/doc-audit-weekly.yml
- [ ] T007: Update docs/INDEX.md with domain map and template references
- [ ] T008: Update docs/design/architecture/README.md Data Files table

**Implementation sketch**:
1. Add `[doc-audit]` tag paragraph to CLAUDE.md under Git Workflow
2. Create post-merge workflow: triggers on closed PR with merged=true,
   reads area labels from PR, looks up domain map, creates audit issue
3. Create weekly workflow: cron schedule Sunday midnight ET, checks for
   existing open weekly audit issue, creates one if none exists
4. Add domain map line to INDEX.md under architecture data section
5. Add domain map row to architecture README Data Files table

**Parallel opportunities**: T004, T006, T007, T008 are all independent.
T005 is the most complex and can proceed in parallel with T004/T007/T008.

**Risks**: Post-merge action must handle missing domain map gracefully.
Weekly stub must deduplicate correctly.

---

## MVP Scope

WP01 alone delivers the domain map and issue template — the foundational
artifacts the future felix-doc-auditor (#105) needs. WP02 adds automation
but the system is functional (manually) with just WP01.

---

**END OF TASKS**
