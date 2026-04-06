# Tasks: F018 Habit Today Filter Visibility

**Feature**: 018-habit-today-filter-visibility
**Mission**: software-dev
**Date**: 2026-04-06
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|-----|----------|
| T001 | Read current AGENTS.md and identify insertion point for due_date step | WP01 | — |
| T002 | Add due_date step to AGENTS.md (repo copy) | WP01 | after T001 |
| T003 | Update habits-ops.md runbook with due_date documentation and troubleshooting | WP01 | [P] with T002 |
| T004 | Deploy updated AGENTS.md to office2 | WP01 | after T002 |
| T005 | Verify — trigger check-in and confirm Today filter visibility | WP01 | after T004 |

---

## Work Packages

### WP01: Agent Update and Deployment

**Prompt**: [WP01-agent-update-and-deployment.md](tasks/WP01-agent-update-and-deployment.md)
**Priority**: P0 (only WP)
**Dependencies**: none
**Subtasks**: T001, T002, T003, T004, T005
**Estimated prompt size**: ~350 lines

**Goal**: Add the due_date step to the felix-admin-habits morning check-in
workflow, update the runbook, deploy to office2, and verify habits appear
in the Vikunja Today filter.

**Included subtasks**:
- [x] T001 — Read current AGENTS.md and identify insertion point
- [x] T002 — Add due_date step to AGENTS.md (repo copy)
- [x] T003 — Update habits-ops.md runbook
- [x] T004 — Deploy updated AGENTS.md to office2
- [ ] T005 — Verify Today filter visibility

**Parallel opportunities**: T002 and T003 edit different files and can
be done simultaneously. T004 and T005 must be sequential (deploy then verify).

**Implementation sequence**:
1. T001: Read existing AGENTS.md, understand workflow steps
2. T002 + T003: Edit AGENTS.md and habits-ops.md (parallel-safe)
3. T004: Deploy to office2
4. T005: Trigger check-in and verify

**Success criteria**: Scheduled habits appear in Vikunja Today filter
after morning check-in runs. Deployed AGENTS.md matches repo copy.
Runbook documents the new behavior.

**Risks**:
- Agent misinterprets new step — mitigated by clear, specific instructions
- API call fails during verification — F017 confirmed the call works

---

**END OF TASKS**
