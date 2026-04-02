# Work Packages: Vikunja Task Intelligence Agent

**Feature**: 013-vikunja-task-intelligence-agent
**Date**: 2026-04-02
**Branch**: `main`

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create SKILL.md structure with required/optional attribute tables | WP01 | - |
| T002 | Define confidence threshold model and attribute inference rules | WP01 | - |
| T003 | Define project placement mapping and identity label inference | WP01 | - |
| T004 | Define goal relationship check procedure | WP01 | - |
| T005 | Define repeat interval conversion table and API patterns | WP01 | - |
| T006 | Define error handling and Vikunja unavailability procedures | WP01 | - |
| T007 | Create SOUL.md agent identity | WP02 | [P] |
| T008 | Create USER.md Kent context | WP02 | [P] |
| T009 | Create IDENTITY.md agent card | WP02 | [P] |
| T010 | Create TOOLS.md available tools and skills | WP02 | [P] |
| T011 | Create AGENTS.md framework — scope, authority, operating mode, privacy | WP03 | - |
| T012 | Implement enrich_task action flow with confidence-based proposals | WP03 | - |
| T013 | Define primary interaction channel abstraction and confirmation pattern | WP03 | - |
| T014 | Implement retroactive_enrichment action with batch handling | WP03 | - |
| T015 | Define enrichment state comment format and skip/defer handling | WP03 | - |
| T016 | Implement detect_incomplete action with polling and dedup | WP03 | - |
| T017 | Define action logging format per Felix Constitution Directive 3 | WP03 | - |
| T018 | Add delegation section to felix-admin-capture AGENTS.md | WP04 | - |
| T019 | Define delegation message payload format and response contract | WP04 | - |
| T020 | Implement fallback to flat task creation on delegation failure | WP04 | - |
| T021 | Update task bridge documentation in capture AGENTS.md | WP04 | - |
| T022 | Define no-gap deployment procedure for handoff transition | WP04 | - |
| T023 | Create task-intelligence-ops.md structure and overview | WP05 | [P] |
| T024 | Document agent operation and manual invocation procedures | WP05 | [P] |
| T025 | Document retroactive enrichment triggers and status checking | WP05 | [P] |
| T026 | Document skip/defer procedures and enrichment state queries | WP05 | [P] |
| T027 | Document troubleshooting: no enrichment, duplicates, timeouts | WP05 | [P] |
| T028 | Register felix-admin-tasker in AGENT-REGISTRY.md | WP06 | [P] |
| T029 | Update service-inventory.md with agent and cron entries | WP06 | [P] |
| T030 | Update service-inventory.json with agent and cron entries | WP06 | [P] |
| T031 | Define cron job specifications for incomplete task detection | WP06 | [P] |
| T032 | Deploy task-intelligence skill to office2 | WP07 | - |
| T033 | Deploy agent workspace to office2 | WP07 | - |
| T034 | Set up cron jobs on office2 | WP07 | - |
| T035 | Manual validation with test task enrichment | WP07 | - |
| T036 | End-to-end verification: handoff, enrichment, detection | WP07 | - |

## Dependency Graph

```
WP01 (Skill) ──────────┐
                        ├──→ WP03 (Standing Orders) ──→ WP04 (Handoff Update)
WP02 (Identity Files) ─┘         │                  ──→ WP05 (Runbook)
                                  │                  ──→ WP06 (Architecture)
                                  │
                                  └──→ WP07 (Deploy) ←── WP04, WP05, WP06
```

**Parallelization**: WP01 and WP02 can run in parallel. After WP03 completes, WP04/WP05/WP06 can run in parallel. WP07 is final.

---

## WP01: Task Intelligence Skill

**Prompt**: `tasks/WP01-task-intelligence-skill.md`
**Priority**: P0 — Foundation
**Subtasks**: T001, T002, T003, T004, T005, T006
**Dependencies**: None
**Estimated prompt size**: ~450 lines

**Goal**: Create the self-contained task-intelligence SKILL.md that encodes all structuring logic, inference rules, confidence thresholds, and Vikunja API patterns. This is the knowledge base that felix-admin-tasker reads to know how to structure tasks.

**Included subtasks**:
- [ ] T001: Create SKILL.md structure with required/optional attribute tables
- [ ] T002: Define confidence threshold model and attribute inference rules
- [ ] T003: Define project placement mapping and identity label inference
- [ ] T004: Define goal relationship check procedure
- [ ] T005: Define repeat interval conversion table and API patterns
- [ ] T006: Define error handling and Vikunja unavailability procedures

**Success criteria**: An agent reading SKILL.md can structure any task end-to-end without additional guidance.

**Risks**: Confidence threshold too aggressive (too few questions) or too conservative (too many). Start conservative per spec.

---

## WP02: Agent Identity & Configuration

**Prompt**: `tasks/WP02-agent-identity-config.md`
**Priority**: P0 — Foundation
**Subtasks**: T007, T008, T009, T010
**Dependencies**: None (parallel with WP01)
**Estimated prompt size**: ~250 lines

**Goal**: Create the supporting workspace files (SOUL.md, USER.md, IDENTITY.md, TOOLS.md) that define the agent's personality, user context, identity card, and tool access. These files are read by OpenClaw when the agent is loaded.

**Included subtasks**:
- [ ] T007: Create SOUL.md agent identity
- [ ] T008: Create USER.md Kent context
- [ ] T009: Create IDENTITY.md agent card
- [ ] T010: Create TOOLS.md available tools and skills

**Success criteria**: OpenClaw can load the agent workspace with correct identity and tool configuration.

**Risks**: Low — follows established pattern from felix-admin-capture and felix-admin-habits.

---

## WP03: Agent Standing Orders

**Prompt**: `tasks/WP03-agent-standing-orders.md`
**Priority**: P0 — Core
**Subtasks**: T011, T012, T013, T014, T015, T016, T017
**Dependencies**: WP01, WP02
**Estimated prompt size**: ~650 lines

**Goal**: Create the full AGENTS.md standing orders document with all three action flows (enrich_task, retroactive_enrichment, detect_incomplete), the channel abstraction, confirmation conversation pattern, enrichment state tracking, and action logging.

**Included subtasks**:
- [ ] T011: Create AGENTS.md framework — scope, authority, operating mode, privacy
- [ ] T012: Implement enrich_task action flow with confidence-based proposals
- [ ] T013: Define primary interaction channel abstraction and confirmation pattern
- [ ] T014: Implement retroactive_enrichment action with batch handling
- [ ] T015: Define enrichment state comment format and skip/defer handling
- [ ] T016: Implement detect_incomplete action with polling and dedup
- [ ] T017: Define action logging format per Felix Constitution Directive 3

**Implementation sequence**: T011 → T013 → T012 → T015 → T014 → T016 → T017

**Success criteria**: AGENTS.md is complete, self-consistent, and follows the pattern of existing agents (felix-admin-capture, felix-admin-habits).

**Risks**: Largest WP — 7 subtasks, ~650 lines. Agent must hold entire context. If implementation struggles, T014-T016 (retroactive/detection) could be extracted to a separate WP.

---

## WP04: Inbox Processor Handoff Update

**Prompt**: `tasks/WP04-inbox-processor-handoff.md`
**Priority**: P1 — Integration
**Subtasks**: T018, T019, T020, T021, T022
**Dependencies**: WP03
**Estimated prompt size**: ~350 lines

**Goal**: Update felix-admin-capture's AGENTS.md to delegate raw task descriptions to felix-admin-tasker instead of creating flat tasks directly, with fallback to existing behavior when the tasker is unavailable.

**Included subtasks**:
- [ ] T018: Add delegation section to felix-admin-capture AGENTS.md
- [ ] T019: Define delegation message payload format and response contract
- [ ] T020: Implement fallback to flat task creation on delegation failure
- [ ] T021: Update task bridge documentation in capture AGENTS.md
- [ ] T022: Define no-gap deployment procedure for handoff transition

**Success criteria**: felix-admin-capture delegates to felix-admin-tasker with graceful fallback. No tasks lost during transition.

**Risks**: Modifying a production agent. Must preserve all existing behavior while adding delegation.

---

## WP05: Operations Runbook

**Prompt**: `tasks/WP05-operations-runbook.md`
**Priority**: P1 — Documentation
**Subtasks**: T023, T024, T025, T026, T027
**Dependencies**: WP03
**Estimated prompt size**: ~350 lines

**Goal**: Create the task-intelligence-ops.md operations runbook covering all operational procedures, manual triggers, status checking, and troubleshooting.

**Included subtasks**:
- [ ] T023: Create task-intelligence-ops.md structure and overview
- [ ] T024: Document agent operation and manual invocation procedures
- [ ] T025: Document retroactive enrichment triggers and status checking
- [ ] T026: Document skip/defer procedures and enrichment state queries
- [ ] T027: Document troubleshooting: no enrichment, duplicates, timeouts

**Success criteria**: Kent can operate, monitor, and troubleshoot felix-admin-tasker using this runbook alone.

**Risks**: Low — documentation work following established handbook pattern.

---

## WP06: Architecture & Registry Updates

**Prompt**: `tasks/WP06-architecture-registry.md`
**Priority**: P1 — Documentation
**Subtasks**: T028, T029, T030, T031
**Dependencies**: WP03
**Estimated prompt size**: ~300 lines

**Goal**: Register the new agent and update architecture documentation to reflect the new service, cron jobs, and data flows.

**Included subtasks**:
- [ ] T028: Register felix-admin-tasker in AGENT-REGISTRY.md
- [ ] T029: Update service-inventory.md with agent and cron entries
- [ ] T030: Update service-inventory.json with agent and cron entries
- [ ] T031: Define cron job specifications for incomplete task detection

**Success criteria**: Architecture documentation accurately reflects the deployed state after F013.

**Risks**: Low — follows established documentation patterns from F008/F009/F012.

---

## WP07: Deployment & Validation

**Prompt**: `tasks/WP07-deployment-validation.md`
**Priority**: P2 — Final
**Subtasks**: T032, T033, T034, T035, T036
**Dependencies**: WP01, WP02, WP03, WP04, WP05, WP06
**Estimated prompt size**: ~300 lines

**Goal**: Deploy all artifacts to office2, set up cron jobs, and validate end-to-end operation with test tasks.

**Included subtasks**:
- [ ] T032: Deploy task-intelligence skill to office2
- [ ] T033: Deploy agent workspace to office2
- [ ] T034: Set up cron jobs on office2
- [ ] T035: Manual validation with test task enrichment
- [ ] T036: End-to-end verification: handoff, enrichment, detection

**Success criteria**: felix-admin-tasker is operational on office2, handles all three action types, and architecture docs match deployed state.

**Risks**: office2 connectivity, OpenClaw configuration, cron scheduling. Manual testing in Assisted mode provides safety net.
