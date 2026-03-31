# Task Breakdown: Vikunja API Skill

**Feature**: 007-vikunja-api-skill
**Date**: 2026-03-30
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Subtask Index

| ID | Description | WP | Parallel |
| --- | --- | --- | --- |
| T001 | Write SKILL.md frontmatter and overview | WP01 | |
| T002 | Write health check instructions | WP01 | |
| T003 | Write project resolution instructions | WP01 | |
| T004 | Write label resolution instructions | WP01 | |
| T005 | Write task creation instructions (with label assignment) | WP02 | |
| T006 | Write task read instructions | WP02 | [P] |
| T007 | Write task update instructions | WP02 | [P] |
| T008 | Write task completion instructions | WP02 | [P] |
| T009 | Write task deletion instructions with warning | WP02 | [P] |
| T010 | Write idempotent creation (duplicate check) | WP02 | |
| T011 | Write filter execution instructions | WP03 | |
| T012 | Write comment operations instructions | WP03 | [P] |
| T013 | Write comprehensive error handling section | WP03 | |
| T014 | Write usage examples section | WP03 | |
| T015 | Deploy skill to office2 | WP04 | |
| T016 | Verify skill in openclaw skills list | WP04 | |
| T017 | Run end-to-end CRUD test against live Vikunja | WP04 | |
| T018 | Verify Goals filter returns goal declarations | WP04 | |
| T019 | Update ops runbook with skill usage | WP04 | |
| T020 | Update architecture docs if needed | WP04 | |

## Work Packages

### WP01: SKILL.md Foundation — Frontmatter and Resolution

**Priority**: P1 (must be first — establishes the file and base instructions)
**Subtasks**: T001, T002, T003, T004
**Estimated prompt size**: ~300 lines
**Dependencies**: None

**Summary**: Create the SKILL.md file with OpenClaw frontmatter, API overview,
authentication pattern, health check, and project/label resolution instructions.
This establishes the skill document that all subsequent WPs extend.

**Independent test**: Deploy the partial SKILL.md and verify the agent can
check Vikunja health and resolve project/label names to IDs.

**Included subtasks**:
- [x] T001: SKILL.md frontmatter (name, description, version, metadata)
- [x] T002: Health check instructions (GET /info, no auth)
- [x] T003: Project resolution (list all, get by name, pseudo-projects)
- [x] T004: Label resolution (list all, get by name)

**Prompt file**: [tasks/WP01-skill-foundation.md](tasks/WP01-skill-foundation.md)

---

### WP02: Task CRUD Operations

**Priority**: P1 (core task operations)
**Subtasks**: T005, T006, T007, T008, T009, T010
**Estimated prompt size**: ~450 lines
**Dependencies**: WP01

**Summary**: Add task create, read, update, complete, and delete instructions
to the SKILL.md. Includes the two-step label assignment pattern and idempotent
creation (duplicate check before creating).

**Independent test**: Agent can create a task with a label, read it back,
update it, mark it complete, and delete it.

**Included subtasks**:
- [x] T005: Task creation with label assignment (two-step: create + add label)
- [x] T006: Task read by ID
- [x] T007: Task update (partial field update)
- [x] T008: Task completion (set done=true)
- [x] T009: Task deletion with permanent-delete warning
- [x] T010: Idempotent creation (check existing by title before creating)

**Prompt file**: [tasks/WP02-task-crud.md](tasks/WP02-task-crud.md)

---

### WP03: Filters, Comments, and Error Handling

**Priority**: P1 (completes the skill's instruction set)
**Subtasks**: T011, T012, T013, T014
**Estimated prompt size**: ~350 lines
**Dependencies**: WP01

**Summary**: Add filter execution (pseudo-projects, ad-hoc queries), comment
operations, comprehensive error handling instructions, and usage examples.

**Independent test**: Agent can execute the Goals filter, add a comment to a
task, and correctly handle error scenarios (bad project name, missing fields).

**Included subtasks**:
- [x] T011: Filter execution (pseudo-projects Today/Upcoming/Overdue, /tasks/all with filters)
- [x] T012: Comment operations (add with [Felix] prefix, read comments)
- [x] T013: Error handling section (all error categories from FR-017 through FR-020)
- [x] T014: Usage examples (common agent scenarios and workflows)

**Parallel opportunity**: WP03 can be implemented in parallel with WP02 (both
depend on WP01 but not on each other).

**Prompt file**: [tasks/WP03-filters-comments-errors.md](tasks/WP03-filters-comments-errors.md)

---

### WP04: Deployment, Verification, and Documentation

**Priority**: P1 (skill is not complete until deployed and verified)
**Subtasks**: T015, T016, T017, T018, T019, T020
**Estimated prompt size**: ~400 lines
**Dependencies**: WP02, WP03

**Summary**: Deploy the completed SKILL.md to office2, verify it loads in
OpenClaw, run end-to-end tests against live Vikunja, and update the ops
runbook and architecture docs.

**Independent test**: `openclaw skills list` shows vikunja-api as ready;
agent can complete a full CRUD round-trip; Goals filter returns declarations.

**Included subtasks**:
- [x] T015: Deploy skill to office2 (~/.openclaw/skills/vikunja-api/)
- [x] T016: Verify skill appears in openclaw skills list
- [x] T017: End-to-end CRUD test (create, read, update, complete, delete)
- [x] T018: Verify Goals filter returns active goal declarations
- [x] T019: Update vikunja-ops.md runbook with skill usage and troubleshooting
- [x] T020: Update architecture docs (data-flows, credential-manifest) if needed

**Prompt file**: [tasks/WP04-deploy-verify-docs.md](tasks/WP04-deploy-verify-docs.md)

---

## Dependency Graph

```
WP01 (foundation)
├── WP02 (task CRUD) ──┐
└── WP03 (filters)  ───┤
                        └── WP04 (deploy + verify)
```

WP02 and WP03 can run in parallel after WP01 completes.

## Canonical Status (Generated)
- WP01: planned
- WP02: planned
- WP03: planned
- WP04: planned
<!-- status-model:end -->

<!-- status-model:start -->
## Canonical Status (Generated)
- WP01: done
- WP02: done
- WP03: approved
- WP04: approved
<!-- status-model:end -->
