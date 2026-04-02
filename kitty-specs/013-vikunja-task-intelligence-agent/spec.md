# Vikunja Task Intelligence Agent

## Overview

Tasks flowing into Vikunja from the inbox processor arrive flat — a title, an identity label, and a source reference. No due dates, no priority, no project placement beyond Inbox, no relationships to goals or other tasks, no repeating intervals. This makes Vikunja a task dump rather than a task management system, and blocks downstream features (escalation engine F014, daily briefing F016, Commitment Manager, calendar integration F017/F018) that depend on structured task data.

This feature introduces `felix-admin-tasker`, a specialist OpenClaw agent that transforms raw task descriptions into fully structured Vikunja entries. The agent reasons through required and optional attributes using a confidence threshold model, clarifies uncertain attributes via a primary interaction channel (WhatsApp initially), and only creates tasks after Kent's explicit confirmation while operating in Assisted mode.

The feature also retroactively enriches existing flat tasks in Vikunja, detects directly-created incomplete tasks, updates the felix-admin-capture handoff to route through the new agent, and delivers a self-contained task-intelligence skill plus operations documentation.

## Actors

- **Kent** — Task owner. Confirms proposed task structures, answers clarification questions, controls enrichment pace and scope.
- **felix-admin-tasker** — New specialist agent. Receives raw task descriptions, reasons through attributes, proposes structured tasks, writes confirmed tasks to Vikunja.
- **felix-admin-capture** — Existing inbox processor. Classifies inbox content as tasks and hands raw task descriptions to felix-admin-tasker (updated handoff).
- **Vikunja** — Task management system. Stores structured tasks with full attributes.
- **Primary interaction channel** — Abstraction for Kent-facing communication (WhatsApp is the initial implementation; architecture supports future channels).

## User Scenarios & Testing

### Scenario 1: New Task from Inbox with High-Confidence Attributes

Kent receives an email about an appointment. felix-admin-capture classifies it as a task and hands the raw description to felix-admin-tasker. The agent infers project (Personal), due date (from explicit date in text), priority (medium), and identity label (personal) with high confidence. It sends a single confirmation message via the primary interaction channel with the proposed structure. Kent replies "yes." The task is created in Vikunja with all attributes populated.

**Acceptance test**: Task appears in Vikunja in the correct project with due date, priority, and identity label matching the proposal Kent confirmed.

### Scenario 2: New Task with Uncertain Attributes

Kent dictates a vague task via Wispr Flow that lands in the inbox. felix-admin-tasker cannot confidently determine the project or due date. It asks Kent two focused clarification questions via the primary interaction channel. Kent answers. The agent proposes the full structure. Kent confirms with a modification ("make it high priority"). The task is created with Kent's modification applied.

**Acceptance test**: Clarification questions are specific to uncertain attributes only. Confirmed task reflects Kent's modification. No re-proposal required for partial modifications.

### Scenario 3: Retroactive Enrichment Batch

On deployment, felix-admin-tasker identifies 12 flat tasks in the Vikunja Inbox. It sends Kent a batch of 3 tasks for enrichment via the primary interaction channel. Kent enriches 2, skips 1. The skipped task gets a Vikunja comment flag. The agent pauses before sending the next batch.

**Acceptance test**: Batch size does not exceed 5. Skipped task is flagged in Vikunja. No duplicate proposal for the skipped task. New incoming tasks continue to be processed during retroactive enrichment.

### Scenario 4: Directly-Created Incomplete Task Detection

Kent creates a task directly in Vikunja with just a title — no due date, no label, no project assignment. After the configured detection interval, felix-admin-tasker offers enrichment via the primary interaction channel. Kent declines. The agent does not offer again for that task.

**Acceptance test**: Detection occurs within the configured polling interval. Single offer per task. No repeat after decline.

### Scenario 5: felix-admin-tasker Unavailable During Handoff

felix-admin-capture classifies an inbox item as a task but felix-admin-tasker is unavailable. felix-admin-capture falls back to creating a flat task in Vikunja Inbox and logs the fallback event.

**Acceptance test**: No tasks lost. Flat task appears in Inbox. Fallback event logged. Task is picked up by felix-admin-tasker's incomplete task detection once the agent is available again.

### Scenario 6: Goal Relationship Detection

A task arrives that clearly aligns with one of Kent's declared goals in the Vikunja Goals project. felix-admin-tasker includes the proposed goal relationship in the confirmation message. Kent confirms. The task is created with a relationship to the goal.

**Acceptance test**: Goal relationship proposed only when plausible. Relationship created only after Kent's confirmation. Unrelated tasks do not trigger false-positive goal proposals.

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | felix-admin-tasker receives raw task descriptions and reasons through required attributes (title, identity label, project, due date, priority) using a confidence threshold model | proposed |
| FR-002 | For attributes inferred with high confidence (≥90%), the agent includes them in a proposed task structure sent to Kent for single-step confirmation | proposed |
| FR-003 | For attributes with low confidence (<90%), the agent asks specific clarification questions via the primary interaction channel before building the proposal | proposed |
| FR-004 | The agent presents the complete proposed task structure to Kent for approval before writing to Vikunja | proposed |
| FR-005 | On approval, the agent creates the fully structured task in Vikunja with all confirmed attributes | proposed |
| FR-006 | On rejection or modification, the agent updates the proposal and re-confirms; partial modifications (e.g., "yes but high priority") are handled without full re-proposal | proposed |
| FR-007 | The agent places tasks in the correct Vikunja project based on content and identity — not defaulting to Inbox when the project is clear | proposed |
| FR-008 | Project placement follows a defined mapping: Intentional LLC work → Intentional LLC project, health/fitness → Health & Conditioning, personal growth → Personal Growth, metal casework → Metal Casework, ambiguous → ask Kent | proposed |
| FR-009 | Before structuring a task, the agent checks active goal declarations in the Vikunja Goals project and proposes linking when a plausible relationship exists | proposed |
| FR-010 | Goal relationships are only created after Kent's confirmation; no false-positive proposals for unrelated tasks | proposed |
| FR-011 | On deployment, the agent identifies existing flat tasks in Vikunja that lack required attributes and offers retroactive enrichment | proposed |
| FR-012 | Retroactive enrichment proposals are delivered in batches of 3-5 tasks with a pause between batches to avoid overwhelming the interaction channel | proposed |
| FR-013 | Kent can defer a batch ("later") or skip individual tasks ("skip"); skipped tasks are flagged with a Vikunja comment and not re-proposed | proposed |
| FR-014 | Completed or archived tasks are excluded from retroactive enrichment | proposed |
| FR-015 | The agent periodically polls the Vikunja Inbox for directly-created tasks that lack required attributes and offers enrichment | proposed |
| FR-016 | After one declined enrichment offer, the agent stops proposing for that task — no repeat pestering | proposed |
| FR-017 | felix-admin-capture is updated to hand raw task descriptions to felix-admin-tasker instead of creating flat tasks directly in Vikunja | proposed |
| FR-018 | The handoff passes: raw task text, source inbox note reference, inferred identity label, and any date/context signals from the inbox note | proposed |
| FR-019 | If felix-admin-tasker is unavailable, felix-admin-capture falls back to creating a flat task in Inbox and logs the fallback | proposed |
| FR-020 | No tasks are lost during the transition — there is no gap in task capture during F013 deployment | proposed |
| FR-021 | A task-intelligence skill is created encoding the structuring model, confidence rules, inference patterns, project mapping, goal check procedure, and conversation flow | proposed |
| FR-022 | The skill is self-contained — an agent reading it can structure any task without additional guidance | proposed |
| FR-023 | An operations runbook is created covering agent operation, manual enrichment triggers, status checks, skip/defer procedures, and troubleshooting | proposed |
| FR-024 | felix-admin-tasker is registered in AGENT-REGISTRY.md at Assisted (Level 1) | proposed |
| FR-025 | Architecture documentation is updated: service-inventory.json, service-inventory.md, and AGENT-REGISTRY.md | proposed |
| FR-026 | The agent processes optional attributes (start date, repeating interval, subtask/parent relationships, blocking/blocked relationships) when contextually relevant | proposed |
| FR-027 | The primary interaction channel is abstracted so the architecture supports future channels beyond WhatsApp without requiring a spec rewrite | proposed |

## Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-001 | The agent must respond to a raw task handoff with a proposal or clarification question within 60 seconds of receiving the input | proposed |
| NFR-002 | Retroactive enrichment batches must pause at least 15 minutes between batches to avoid channel flooding | proposed |
| NFR-003 | The incomplete task detection poll must run at a configurable interval (default defined during planning) | proposed |
| NFR-004 | The agent must handle Vikunja API unavailability gracefully — log the failure, notify Kent, and retry with backoff rather than losing the task context | proposed |
| NFR-005 | All agent actions must be logged with sufficient detail for operational troubleshooting and operating mode oversight | proposed |
| NFR-006 | The confidence threshold (≥90% for auto-inference) must be configurable in the task-intelligence skill without requiring code changes | proposed |
| NFR-007 | The agent must support the standard operating mode progression (Assisted → Observed → Autonomous) with mode changes requiring no code modifications | proposed |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | felix-admin-tasker operates within OpenClaw on office2 — no separate infrastructure required | proposed |
| C-002 | All Vikunja API access uses tokens from the credential store — no credentials in code or skill documents | proposed |
| C-003 | The agent starts in Assisted mode — every task creation requires Kent's explicit confirmation until mode is elevated | proposed |
| C-004 | The agent follows narrow scope per constitution: it structures tasks only — it does not process inbox notes, manage habits, or send briefings | proposed |
| C-005 | Failures are never silent — Vikunja unavailability, proposal timeouts, and enrichment failures must be logged and reported | proposed |
| C-006 | The agent starts in Assisted mode per F012 constitution directive — all new agents begin at Assisted and progress through Observed to Autonomous based on demonstrated predictable behavior | proposed |
| C-007 | WhatsApp is the initial implementation of the primary interaction channel; channel abstraction must not add complexity to the initial delivery | proposed |
| C-008 | Architecture documentation updates (service-inventory, agent-registry) are part of the same delivery — not a separate task | proposed |

## Success Criteria

1. Raw tasks from the inbox processor receive full attribute enrichment through an interactive confirmation flow — no flat tasks enter Vikunja once the handoff is active
2. Existing flat tasks in Vikunja are identified and offered retroactive enrichment in manageable batches with skip/defer controls
3. Directly-created incomplete tasks are detected and offered a single enrichment opportunity
4. felix-admin-capture hands off to felix-admin-tasker with graceful fallback to flat task creation when the tasker is unavailable
5. Tasks are placed in the correct Vikunja project based on content and identity, not left in Inbox by default
6. Goal relationships are detected and proposed where plausible, created only on Kent's confirmation
7. A self-contained task-intelligence skill enables consistent task structuring
8. Operations runbook enables manual operation, troubleshooting, and status monitoring
9. Agent is registered and architecture documentation is current

## Key Entities

- **Raw Task Description** — Unstructured text from inbox capture or direct creation; input to the enrichment flow
- **Enrichment Proposal** — Structured task summary with all inferred/confirmed attributes; presented to Kent for approval
- **Vikunja Task** — Fully structured entry in Vikunja with title, identity label, project, due date, priority, and optional attributes
- **Task Relationship** — Link between tasks (subtask/parent, blocking/blocked, related) or between a task and a goal
- **Identity Label** — Classification tag (personal, intentional, metalcasework) that drives project placement
- **Confidence Threshold** — Configurable cutoff (default ≥90%) that determines whether an attribute is inferred or clarified
- **Primary Interaction Channel** — Abstraction for Kent-facing communication; WhatsApp is the initial implementation
- **Enrichment Batch** — Group of 3-5 flat tasks proposed for retroactive enrichment in a single interaction
- **Task-Intelligence Skill** — OpenClaw skill document encoding the structuring model, inference rules, and conversation patterns

## Dependencies

- **F008 (felix-admin-capture)** — The inbox processor must be modified to hand off raw tasks instead of creating flat Vikunja entries
- **F012 (Constitution & Agent Setup)** — Provides the operating mode framework (Assisted → Observed → Autonomous) and skill-authoring conventions
- **Vikunja API** — Task CRUD, task relationships, repeat intervals, and project management endpoints must be available and documented
- **OpenClaw agent-to-agent communication** — The handoff mechanism (direct invocation vs. polling) is an architectural question resolved during planning
- **WhatsApp integration** — Existing primary interaction channel infrastructure must support the confirmation and clarification conversation patterns

## Assumptions

- The Vikunja API supports task relationship creation (subtask, related, blocking) — exact endpoints to be confirmed during planning
- The Vikunja `repeat_after` field format will be documented during planning research
- OpenClaw's agent-to-agent invocation capability will be researched during planning; polling is the fallback pattern
- The existing WhatsApp integration supports the conversational patterns required (multi-turn clarification, confirmation, batch proposals)
- The current Vikunja project structure (Intentional LLC, Health & Conditioning, Personal Growth, Metal Casework, Business Acquisition, Inbox) is stable for the project placement mapping

## Out of Scope

- Calendar time-blocking for tasks (F018)
- Escalation of structured tasks (F014)
- Commitment Manager / full cross-goal assessment (future feature)
- Vikunja UI improvements or saved filter changes
- Task completion tracking or reporting (F014/F016)
- Bulk import or migration tools beyond retroactive enrichment

## Risks

- **WhatsApp conversation volume during retroactive enrichment** — Flat tasks have accumulated; retroactive enrichment could generate a burst of messages. Mitigation: batching (3-5 per batch) with configurable pause between batches; Kent can defer entire batches.
- **Agent-to-agent handoff mechanism not supported by OpenClaw** — If direct specialist invocation is unsupported, the handoff needs an alternative. Mitigation: polling pattern (incomplete task detection) is the fallback; resolved during planning research.
- **Confidence threshold miscalibration** — Too low means Kent gets asked about obvious attributes; too high means wrong attributes applied silently. Mitigation: start conservative (ask more), tune based on operational feedback. Threshold is configurable in the skill document.
- **Retroactive enrichment disrupts existing task management habits** — Kent may have mentally organized flat Inbox tasks. Mitigation: retroactive enrichment is opt-in per batch; Kent can decline all retroactive enrichment.
