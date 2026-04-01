# F009 Tasks: Daily Habit Check-in

**Feature**: 009-daily-habit-checkin
**Branch**: main
**Total work packages**: 6
**Total subtasks**: 28

## Dependency graph

```
WP01 (Agent Foundation)
  └─► WP02 (Vikunja Habits)
       └─► WP03 (Check-in & Completion)
            └─► WP04 (Reporting & Management)
                 └─► WP05 (Scheduling & WhatsApp)
                      └─► WP06 (Docs & Architecture)
```

## Work packages

### WP01: Agent workspace foundation

**Priority**: P0 — foundation
**Dependencies**: none
**Estimated prompt size**: ~300 lines

Create the felix-admin-habits agent workspace files, register the agent on
office2, deploy the workspace, and verify operational. Reuse SOUL.md and
USER.md patterns from felix-admin-capture.

**Included subtasks**:
- [x] T001: Write SOUL.md with kent-voice identity (reuse from felix-admin-capture)
- [x] T002: Write USER.md, IDENTITY.md, TOOLS.md
- [x] T003: Create felix-admin-habits agent on office2
- [x] T004: Deploy workspace files to office2
- [x] T005: Verify agent is operational

**Prompt file**: [tasks/WP01-agent-foundation.md](tasks/WP01-agent-foundation.md)

---

### WP02: Vikunja habits project and initial habits

**Priority**: P0 — foundation
**Dependencies**: WP01
**Estimated prompt size**: ~350 lines

Create the Habits project in Vikunja, create 7 habit tasks with identity
labels and frequency descriptions, verify the comment-based completion
storage approach works.

**Included subtasks**:
- [x] T006: Create Habits project in Vikunja
- [x] T007: Create 7 habit tasks with labels and frequency descriptions
- [x] T008: Verify habit tasks via API query
- [x] T009: Test comment CRUD on a habit task (validate storage approach)

**Prompt file**: [tasks/WP02-vikunja-habits.md](tasks/WP02-vikunja-habits.md)

---

### WP03: Standing orders — check-in and completion

**Priority**: P1 — core functionality
**Dependencies**: WP02
**Estimated prompt size**: ~450 lines

Write the AGENTS.md standing orders covering the morning check-in generation
workflow and completion marking via WhatsApp. This is the core processing
loop — the most critical deliverable.

**Included subtasks**:
- [x] T010: Write AGENTS.md — authority and processing workflow overview
- [x] T011: Check-in generation section (query habits, filter by day/frequency, exclude completed, format message)
- [x] T012: Completion marking section (natural language parsing, Vikunja comment CRUD, confirmation)
- [x] T013: Comment format specification and idempotency rules
- [x] T014: Deploy AGENTS.md to office2 and verify agent reads it

**Prompt file**: [tasks/WP03-checkin-completion.md](tasks/WP03-checkin-completion.md)

---

### WP04: Standing orders — reporting and habit management

**Priority**: P1 — core functionality
**Dependencies**: WP03
**Estimated prompt size**: ~400 lines

Add weekly pattern report generation, on-demand track record query, and
habit add/pause/remove functionality to AGENTS.md.

**Included subtasks**:
- [x] T015: Weekly pattern report section (query history, calculate rates, format concise report)
- [x] T016: On-demand track record query section (4-week summary)
- [x] T017: Habit add/pause/remove section (WhatsApp-based management with confirmation)
- [x] T018: Deploy updated AGENTS.md to office2 and verify

**Prompt file**: [tasks/WP04-reporting-management.md](tasks/WP04-reporting-management.md)

---

### WP05: Scheduling and WhatsApp integration

**Priority**: P1 — integration
**Dependencies**: WP04
**Estimated prompt size**: ~450 lines

Add cron jobs for morning check-in and weekly report. Patch the main agent
with habits delegation. Test the full WhatsApp loop end-to-end.

**Included subtasks**:
- [ ] T019: Add morning check-in cron job (7:05 AM ET, without --no-deliver)
- [ ] T020: Add weekly report cron job (Sunday 6 PM ET, without --no-deliver)
- [ ] T021: Patch main agent AGENTS.md with habits delegation instruction
- [ ] T022: Test proactive check-in delivery via WhatsApp
- [ ] T023: Test completion marking via WhatsApp reply
- [ ] T024: Test weekly report delivery
- [ ] T025: Verify full loop: cron → check-in → reply → completion recorded → confirmed

**Prompt file**: [tasks/WP05-scheduling-whatsapp.md](tasks/WP05-scheduling-whatsapp.md)

---

### WP06: Documentation and architecture updates

**Priority**: P2 — polish
**Dependencies**: WP05
**Estimated prompt size**: ~300 lines

Create the habits operations runbook and update architecture documentation
with the new agent and cron jobs.

**Included subtasks**:
- [ ] T026: Create docs/handbooks/habits-ops.md operations runbook
- [ ] T027: Update service-inventory.json with agent and cron entries
- [ ] T028: Update service-inventory.md narrative

**Prompt file**: [tasks/WP06-docs-architecture.md](tasks/WP06-docs-architecture.md)

---

## Parallelization notes

The dependency chain is linear (WP01→WP02→WP03→WP04→WP05→WP06). Each WP
builds on the previous. No parallel execution opportunities between WPs.

Within WPs, T001/T002 can run in parallel (WP01), and T019/T020/T021 are
independent setup tasks (WP05).

## MVP scope

WP01 through WP05 deliver the complete daily habit loop. WP06 (docs) can
be deferred if needed but is required for feature acceptance.

<!-- status-model:start -->
## Canonical Status (Generated)
- WP01: approved
- WP02: approved
- WP03: approved
- WP04: in_progress
<!-- status-model:end -->
