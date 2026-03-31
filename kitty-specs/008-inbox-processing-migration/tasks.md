# Task Breakdown: Inbox Processing Migration

**Feature**: 008-inbox-processing-migration
**Date**: 2026-03-31
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Subtask Index

| ID | Description | WP | Parallel |
| --- | --- | --- | --- |
| T001 | Write SOUL.md with kent-voice identity | WP01 | |
| T002 | Write USER.md, IDENTITY.md, TOOLS.md | WP01 | [P] |
| T003 | Create felix-admin-capture agent on office2 | WP01 | |
| T004 | Deploy workspace files to office2 | WP01 | |
| T005 | Verify agent appears in openclaw agents list | WP01 | |
| T006 | Write AGENTS.md — routing table section | WP02 | |
| T007 | Write AGENTS.md — vault-writer standards section | WP02 | |
| T008 | Write AGENTS.md — privacy boundary section | WP02 | |
| T009 | Write AGENTS.md — edge case handling section | WP02 | |
| T010 | Write AGENTS.md — processing log format section | WP02 | |
| T011 | Create Research project in Vikunja | WP03 | |
| T012 | Write AGENTS.md — task bridge section (Inbox project) | WP03 | |
| T013 | Write AGENTS.md — identity label inference rules | WP03 | |
| T014 | Write AGENTS.md — duplicate task detection | WP03 | |
| T015 | Write AGENTS.md — research request routing (Research project) | WP03 | |
| T016 | Write AGENTS.md — task error handling | WP03 | |
| T017 | Write AGENTS.md — Felix declaration validation rules | WP04 | |
| T018 | Write AGENTS.md — valid declaration routing (Goals-MOC + Vikunja) | WP04 | |
| T019 | Write AGENTS.md — potential-goal flagging | WP04 | |
| T020 | Add 3 cron jobs (morning, midday, evening) | WP04 | |
| T021 | Test manual cron run against real inbox notes | WP04 | |
| T022 | Verify idempotency (run twice, same result) | WP04 | |
| T023 | Add inbox-trigger instruction to main agent | WP05 | |
| T024 | Test WhatsApp trigger end-to-end | WP05 | |
| T025 | Test full processing cycle with all content types | WP05 | |
| T026 | Create docs/handbooks/inbox-ops.md | WP06 | |
| T027 | Update service-inventory.json and service-inventory.md | WP06 | |
| T028 | Verify Cowork skills unchanged | WP06 | |

## Work Packages

### WP01: Agent Workspace Foundation

**Priority**: P1 (must be first — creates the agent)
**Subtasks**: T001, T002, T003, T004, T005
**Estimated prompt size**: ~400 lines
**Dependencies**: None

**Summary**: Write the workspace files (SOUL.md with kent-voice, support files),
create the felix-admin-capture agent on office2, deploy the workspace, and verify.

**Independent test**: `openclaw agents list` shows felix-admin-capture with its
workspace at `/data/services/openclaw/inbox-agent/`.

**Included subtasks**:
- [x] T001: Write SOUL.md with kent-voice authoring identity
- [x] T002: Write USER.md, IDENTITY.md, TOOLS.md
- [x] T003: Create felix-admin-capture agent on office2
- [x] T004: Deploy workspace files to office2
- [x] T005: Verify agent appears in openclaw agents list

**Prompt file**: [tasks/WP01-agent-foundation.md](tasks/WP01-agent-foundation.md)

---

### WP02: Standing Orders — Routing and Vault Operations

**Priority**: P1 (defines core processing behavior)
**Subtasks**: T006, T007, T008, T009, T010
**Estimated prompt size**: ~500 lines
**Dependencies**: WP01

**Summary**: Write the AGENTS.md standing orders that define the inbox processing
workflow: content classification routing table, vault-writer file operation
standards, privacy boundary, edge case handling, and processing log format.

**Independent test**: Read AGENTS.md on office2 and verify all routing table
entries match the existing inbox-processor SKILL.md. Verify privacy boundary
is stated. Verify processing log format is defined.

**Included subtasks**:
- [x] T006: Routing table section (all content types → destinations)
- [x] T007: Vault-writer standards (frontmatter, naming, wikilinks, voice)
- [x] T008: Privacy boundary (02-Growth/_private/ absolute rule)
- [x] T009: Edge case handling (empty files, multi-domain, shared content)
- [x] T010: Processing log format and location

**Prompt file**: [tasks/WP02-routing-and-vault.md](tasks/WP02-routing-and-vault.md)

---

### WP03: Standing Orders — Vikunja Task Bridge

**Priority**: P1 (connects inbox to Vikunja)
**Subtasks**: T011, T012, T013, T014, T015, T016
**Estimated prompt size**: ~450 lines
**Dependencies**: WP02

**Summary**: Create the Research project in Vikunja, then add standing orders
for the task bridge: task items → Inbox project, research requests → Research
project, with identity label inference, duplicate detection, and error handling.

**Independent test**: Run the agent with a test inbox note containing a task
item and a research request. Verify both create Vikunja tasks in the correct
projects with correct labels.

**Included subtasks**:
- [x] T011: Create Research project in Vikunja
- [x] T012: Task bridge section — task items → Inbox project via F007
- [x] T013: Identity label inference rules (context → personal/intentional/metalcasework)
- [x] T014: Duplicate task detection (search before create)
- [x] T015: Research request routing → Research project
- [x] T016: Task creation error handling (log failures, never drop silently)

**Prompt file**: [tasks/WP03-task-bridge.md](tasks/WP03-task-bridge.md)

---

### WP04: Goal Routing and Scheduling

**Priority**: P1 (goals + scheduling complete the core feature)
**Subtasks**: T017, T018, T019, T020, T021, T022
**Estimated prompt size**: ~500 lines
**Dependencies**: WP03

**Summary**: Add goal declaration routing to AGENTS.md (Felix validation,
Goals-MOC.md + Vikunja routing, potential-goal flagging), then add 3 cron
jobs and test the full scheduled processing cycle.

**Independent test**: Run the agent with a test inbox note containing a valid
goal declaration and an aspirational statement. Verify: declaration appears in
Goals-MOC.md and Vikunja Goals project; aspiration is flagged as potential-goal.
Verify cron jobs exist and a manual run completes successfully.

**Included subtasks**:
- [ ] T017: Felix declaration validation rules in AGENTS.md
- [ ] T018: Valid declaration routing (Goals-MOC.md + Vikunja Goals project)
- [ ] T019: Potential-goal flagging for partial/aspirational items
- [ ] T020: Add 3 cron jobs (7 AM, 12 PM, 6 PM ET)
- [ ] T021: Test manual cron run against real inbox notes
- [ ] T022: Verify idempotency (run twice, same result)

**Prompt file**: [tasks/WP04-goals-and-scheduling.md](tasks/WP04-goals-and-scheduling.md)

---

### WP05: WhatsApp Trigger and End-to-End Test

**Priority**: P2 (convenience feature, depends on research)
**Subtasks**: T023, T024, T025
**Estimated prompt size**: ~350 lines
**Dependencies**: WP04

**Summary**: Add an inbox-trigger instruction to the main agent's workspace
so it recognizes "process my inbox" via WhatsApp and delegates to
felix-admin-capture. Run a comprehensive end-to-end test covering all content
types.

**Independent test**: Send "process my inbox" via WhatsApp and verify the agent
runs and responds. Test with inbox notes covering: values, tasks, research
requests, goal declarations, journal entries, and unclassifiable content.

**Note**: WhatsApp trigger is contingent on OpenClaw's ability to invoke
`openclaw cron run` or `openclaw agent --agent` from within an agent turn.
If this doesn't work, document the limitation and defer.

**Included subtasks**:
- [ ] T023: Add inbox-trigger instruction to main agent workspace
- [ ] T024: Test WhatsApp trigger end-to-end
- [ ] T025: Comprehensive end-to-end test with all content types

**Prompt file**: [tasks/WP05-whatsapp-and-e2e.md](tasks/WP05-whatsapp-and-e2e.md)

---

### WP06: Documentation and Fallback Verification

**Priority**: P2 (documentation and safety)
**Subtasks**: T026, T027, T028
**Estimated prompt size**: ~300 lines
**Dependencies**: WP04

**Summary**: Create the inbox-ops.md runbook, update architecture docs with
the new agent and cron jobs, and verify the original Cowork skills are intact.

**Parallel opportunity**: WP06 can be implemented in parallel with WP05
(both depend on WP04 but not on each other).

**Included subtasks**:
- [ ] T026: Create docs/handbooks/inbox-ops.md
- [ ] T027: Update service-inventory.json and service-inventory.md
- [ ] T028: Verify Cowork skills unchanged at ~/second-brain/.claude/skills/

**Prompt file**: [tasks/WP06-docs-and-fallback.md](tasks/WP06-docs-and-fallback.md)

---

## Dependency Graph

```
WP01 (agent foundation)
└── WP02 (routing + vault operations)
    └── WP03 (task bridge)
        └── WP04 (goals + scheduling)
            ├── WP05 (WhatsApp + E2E test)
            └── WP06 (docs + fallback)
```

WP05 and WP06 can run in parallel after WP04 completes.

## Canonical Status (Generated)
- WP01: planned
- WP02: planned
- WP03: planned
- WP04: planned
- WP05: planned
- WP06: planned
<!-- status-model:end -->

<!-- status-model:start -->
## Canonical Status (Generated)
- WP01: approved
- WP02: approved
- WP03: approved
<!-- status-model:end -->
