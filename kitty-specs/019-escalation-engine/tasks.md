# Tasks: F019 Escalation Engine

**Feature**: 019-escalation-engine
**Mission**: software-dev
**Date**: 2026-04-06
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|-----|----------|
| T001 | Create escalation skill (SKILL.md) with full model definition | WP01 | — | [D] |
| T002 | Create IDENTITY.md for felix-admin-escalation | WP02 | — | [D] |
| T003 | Create SOUL.md (copy from habits agent, adapt identity) | WP02 | [P] with T002 | [D] |
| T004 | Create USER.md (copy from habits agent) | WP02 | [P] with T002 | [D] |
| T005 | Create TOOLS.md with Vikunja API references for escalation | WP02 | [P] with T002 | [D] |
| T006 | Create AGENTS.md — detection, level determination, alerting | WP02 | after T001 | [D] |
| T007 | Create AGENTS.md — response handling section | WP02 | after T006 | [D] |
| T008 | Register agent in OpenClaw on office2 | WP03 | — | [D] |
| T009 | Deploy skill to office2 | WP03 | [P] with T008 |
| T010 | Deploy agent workspace files to office2 | WP03 | after T008 |
| T011 | Create escalation cron job (daily, 8:00 AM ET) | WP03 | after T010 |
| T012 | Register agent in AGENT-REGISTRY.md at Assisted (Level 1) | WP03 | [P] |
| T013 | Update service-inventory.json with agent and cron entries | WP03 | [P] |
| T014 | Update service-inventory.md narrative | WP03 | after T013 |
| T015 | Create escalation-ops.md runbook | WP04 | — |
| T016 | Verify — trigger cron and confirm alert delivery | WP04 | after WP03 |
| T017 | Verify — test response handling (done, snooze) | WP04 | after T016 |
| T018 | Verify — confirm silent run when no tasks qualify | WP04 | after T016 |
| T019 | Verify — check escalation comments written correctly | WP04 | after T016 |

---

## Work Packages

### WP01: Escalation Skill

**Prompt**: [WP01-escalation-skill.md](tasks/WP01-escalation-skill.md)
**Priority**: P0 — foundational; AGENTS.md references this skill
**Dependencies**: none
**Subtasks**: T001
**Estimated prompt size**: ~350 lines

**Goal**: Create the self-contained escalation skill that encodes the
full escalation model: detection criteria, level determination, comment
format, response handling, message format, and error handling.

**Included subtasks**:
- [ ] T001 — Create SKILL.md at `scripts/openclaw/skills/escalation/`

**Why separate WP**: The skill is the authoritative model definition.
AGENTS.md in WP02 references it. Getting the model right in isolation
before writing the agent instructions reduces rework risk.

---

### WP02: Agent Workspace Files

**Prompt**: [WP02-agent-workspace.md](tasks/WP02-agent-workspace.md)
**Priority**: P0 — core agent definition
**Dependencies**: WP01
**Subtasks**: T002, T003, T004, T005, T006, T007
**Estimated prompt size**: ~550 lines

**Goal**: Create the felix-admin-escalation agent workspace with all
supporting files (IDENTITY, SOUL, USER, TOOLS) and the AGENTS.md
standing orders covering detection, alerting, and response handling.

**Included subtasks**:
- [ ] T002 — Create IDENTITY.md
- [ ] T003 — Create SOUL.md (adapt from habits agent)
- [ ] T004 — Create USER.md (copy from habits agent)
- [ ] T005 — Create TOOLS.md with escalation-specific API references
- [ ] T006 — Create AGENTS.md: detection and alerting sections
- [ ] T007 — Create AGENTS.md: response handling section

**Parallel opportunities**: T002-T005 are independent files. T006-T007
are sequential (AGENTS.md sections build on each other).

---

### WP03: Deployment, Cron, and Architecture

**Prompt**: [WP03-deployment-cron-architecture.md](tasks/WP03-deployment-cron-architecture.md)
**Priority**: P1 — operational setup
**Dependencies**: WP02
**Subtasks**: T008, T009, T010, T011, T012, T013, T014
**Estimated prompt size**: ~450 lines

**Goal**: Register the agent in OpenClaw, deploy all files to office2,
create the daily cron job, register in AGENT-REGISTRY.md, and update
architecture documentation.

**Included subtasks**:
- [ ] T008 — Register agent in OpenClaw
- [ ] T009 — Deploy skill to office2
- [ ] T010 — Deploy agent workspace files to office2
- [ ] T011 — Create escalation cron job (daily, 8:00 AM ET / 12:00 UTC)
- [ ] T012 — Register in AGENT-REGISTRY.md
- [ ] T013 — Update service-inventory.json
- [ ] T014 — Update service-inventory.md

**Parallel opportunities**: T008+T009 can run in parallel. T012-T014
are documentation tasks independent of deployment.

---

### WP04: Runbook and Verification

**Prompt**: [WP04-runbook-and-verification.md](tasks/WP04-runbook-and-verification.md)
**Priority**: P2 — validation and documentation
**Dependencies**: WP03
**Subtasks**: T015, T016, T017, T018, T019
**Estimated prompt size**: ~400 lines

**Goal**: Create the operations runbook and verify the full system
end-to-end: alert delivery, response handling, silent run, and
comment format.

**Included subtasks**:
- [ ] T015 — Create escalation-ops.md runbook
- [ ] T016 — Verify: trigger cron and confirm alert delivery
- [ ] T017 — Verify: test response handling (done, snooze)
- [ ] T018 — Verify: confirm silent run when no tasks qualify
- [ ] T019 — Verify: check escalation comments written correctly

**Parallel opportunities**: T015 (runbook) can be written in parallel
with verification tasks T016-T019.

---

**END OF TASKS**
