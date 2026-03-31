# Feature Specification: Inbox Processing Migration

**Feature Branch**: `008-inbox-processing-migration`
**Created**: 2026-03-31
**Status**: Draft
**Input**: F008 func-spec — migrate inbox processing to always-on OpenClaw agent on office2

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Always-On Inbox Processing (Priority: P1)

Kent captures notes via Wispr Flow and typed quick notes throughout the day.
Currently, these pile up unprocessed when the Mac is asleep. He needs an
always-on agent on office2 that processes the inbox 3× daily, routing content
to the correct vault locations using the existing routing table, goal handling
rules, and authoring standards.

**Why this priority**: This is the core migration — without it, inbox
processing remains Mac-dependent.

**Independent Test**: Drop an unprocessed test note in 00-Inbox/ on office2's
synced vault. Wait for the next scheduled run (or trigger manually). Verify:
the note is classified, content routed to the correct destination, frontmatter
updated to `status: processed`, and a processing log written.

**Acceptance Scenarios**:

1. **Given** an unprocessed inbox note with values content, **When** the agent
   processes it, **Then** the content is integrated into
   `01-Constitution/Values.md` in Kent's voice, the inbox note is marked
   `status: processed`, and the processing log records the action.
2. **Given** an unprocessed inbox note with multi-domain content (e.g., a
   business idea plus a personal reflection), **When** the agent processes it,
   **Then** each content block is routed to the correct domain with wikilinks
   connecting them.
3. **Given** an empty inbox note (frontmatter only), **When** the agent
   processes it, **Then** it is marked `status: processed` and noted as empty
   in the log.
4. **Given** an already-processed inbox note (`status: processed`), **When**
   the agent runs, **Then** the note is skipped entirely.
5. **Given** an inbox note with content mentioning `02-Growth/_private/`,
   **When** the agent processes it, **Then** no content is routed to or
   references `_private/` — the privacy boundary is enforced absolutely.

---

### User Story 2 — Vikunja Task Bridge (Priority: P1)

When the inbox processor identifies a task or action item in an inbox note,
it must create a real Vikunja task using the F007 API skill. This closes
the loop between capture and accountability.

**Why this priority**: This is the most significant functional addition —
for the first time, captured tasks automatically appear in Vikunja.

**Independent Test**: Drop an inbox note containing a clear action item
("Schedule dentist appointment" or "Review the Q2 proposal for Intentional").
After processing, verify a Vikunja task exists in the Inbox project with the
correct title, identity label, and source reference in the description.

**Acceptance Scenarios**:

1. **Given** an inbox note with a clear task item, **When** the agent
   processes it, **Then** a Vikunja task is created in the Inbox project
   with the correct identity label and a description referencing the
   source note.
2. **Given** a task item with business context (e.g., "Follow up with
   consulting prospect"), **When** the agent classifies it, **Then** the
   identity label is set to `intentional`.
3. **Given** a task that already exists in the Inbox project (same title),
   **When** the agent encounters a duplicate, **Then** no new task is
   created and the duplicate is logged.
4. **Given** a task creation failure (Vikunja unreachable), **When** the
   agent attempts to create the task, **Then** the failure is recorded in
   the processing log — the task is not silently dropped.

---

### User Story 3 — Research Request Task Bridge (Priority: P2)

When the inbox processor identifies a research request, it must create a
Vikunja task in a dedicated Research project so future research agents can
track status and completion.

**Why this priority**: Lower than task bridge — research requests are less
frequent but benefit from the same accountability loop.

**Independent Test**: Drop an inbox note containing a research request
("Research the best CRM options for small consulting firms"). After processing,
verify a Vikunja task exists in the Research project.

**Acceptance Scenarios**:

1. **Given** an inbox note with a research request, **When** the agent
   processes it, **Then** a Vikunja task is created in a Research project
   with the source reference and identity label.
2. **Given** no Research project exists in Vikunja, **When** the feature
   is deployed, **Then** the Research project is created as a prerequisite.

---

### User Story 4 — Goal Declaration Routing (Priority: P1)

When the inbox processor identifies a valid Felix goal declaration, it must
add it to Goals-MOC.md and create a corresponding Vikunja task in the Goals
project. Partial or aspirational items must be flagged, not promoted.

**Why this priority**: Goal declarations are the link between the constitution
and the task system. Incorrect routing undermines both.

**Independent Test**: Drop an inbox note containing a valid declaration:
"On September 30, 2026, I have $5K/month consulting income as evidenced by
deposits in my Intentional LLC account." Verify it appears in Goals-MOC.md
and as a Vikunja task in the Goals project with the correct due date.

**Acceptance Scenarios**:

1. **Given** a valid goal declaration with date, outcome, and evidence,
   **When** the agent processes it, **Then** it is added to Goals-MOC.md
   Active Declarations and a Vikunja task is created in the Goals project
   with the target date as due date.
2. **Given** an aspirational statement without a date ("I want to run a 5K"),
   **When** the agent processes it, **Then** it is flagged as
   `type: potential-goal` in the processing log with a note that the date
   is missing. It is NOT added to Goals-MOC.md.
3. **Given** a goal mention that matches an existing declaration, **When**
   the agent processes it, **Then** the existing declaration is updated
   rather than duplicated.

---

### User Story 5 — Scheduled Execution (Priority: P1)

The agent must run 3× daily on office2 via OpenClaw's scheduling system,
independent of Mac availability.

**Why this priority**: Without scheduling, the migration doesn't achieve
its core purpose — always-on processing.

**Independent Test**: Verify cron/schedule entries exist. Check processing
logs across 24 hours to confirm 3 runs occurred.

**Acceptance Scenarios**:

1. **Given** the agent is configured, **When** 24 hours pass, **Then**
   3 processing logs are written at the scheduled times.
2. **Given** a scheduled run fails (e.g., vault unavailable), **When**
   the next scheduled run occurs, **Then** it attempts processing normally
   — the failure does not block subsequent runs.
3. **Given** the Mac is asleep, **When** a scheduled run occurs on office2,
   **Then** processing completes normally using the synced vault.

---

### User Story 6 — WhatsApp On-Demand Trigger (Priority: P2)

Kent must be able to say "process my inbox now" via WhatsApp and have the
agent run immediately, responding with the processing summary.

**Why this priority**: Convenience feature — the scheduled runs handle the
core need. On-demand is valuable but not blocking.

**Independent Test**: Send "process my inbox" via WhatsApp. Verify the agent
runs and responds with a processing summary.

**Acceptance Scenarios**:

1. **Given** Kent sends "process my inbox now" via WhatsApp, **When**
   OpenClaw receives the message, **Then** the inbox processing agent
   runs and responds with the processing summary.
2. **Given** natural variations ("check my inbox", "run inbox processing"),
   **When** sent via WhatsApp, **Then** the agent recognizes the intent.

**Note**: This user story is contingent on planning-phase research into
OpenClaw's intent routing capabilities. If OpenClaw cannot route specific
intents to specific agents, this may need to be deferred or implemented
differently.

---

### User Story 7 — Cowork Fallback and Documentation (Priority: P2)

The original Cowork skills must remain intact as a fallback, and an ops
runbook must document both execution paths.

**Why this priority**: Safety net during transition.

**Independent Test**: Verify the three skills still exist at
`~/second-brain/.claude/skills/`. Verify the runbook documents both paths.

**Acceptance Scenarios**:

1. **Given** the office2 agent is deployed, **When** someone checks the
   Cowork skills, **Then** they are unchanged and functional.
2. **Given** the ops runbook, **When** a user reads it, **Then** they
   understand how to use the office2 agent, how to trigger a manual run,
   and how to fall back to Cowork if needed.

---

## Functional Requirements

| ID | Requirement | Status |
| --- | --- | --- |
| FR-001 | Configure felix-admin-capture agent in OpenClaw replicating the full inbox-processor routing table | Proposed |
| FR-002 | Agent reads vault from office2 synced copy at the path in service-inventory.json | Proposed |
| FR-003 | Agent preserves kent-voice authoring standards in all vault content | Proposed |
| FR-004 | Agent preserves vault-writer file operation standards (frontmatter, naming, wikilinks) | Proposed |
| FR-005 | Agent enforces privacy boundary — 02-Growth/_private/ never read, processed, routed to, or logged | Proposed |
| FR-006 | Agent marks processed inbox files with `status: processed` frontmatter | Proposed |
| FR-007 | Agent sets `status: needs-review` for unclassifiable content | Proposed |
| FR-008 | Agent writes processing log after each run to ~/second-brain/agents/logs/ | Proposed |
| FR-009 | Task items create Vikunja tasks in the Inbox project via F007 skill | Proposed |
| FR-010 | Each task carries title, identity label (inferred from context), and source reference | Proposed |
| FR-011 | Duplicate task detection — same title in same project prevents creation | Proposed |
| FR-012 | Task creation failures surface in processing log, never silently dropped | Proposed |
| FR-013 | Research requests create Vikunja tasks in a dedicated Research project | Proposed |
| FR-014 | Research project created in Vikunja as a prerequisite if it does not exist | Proposed |
| FR-015 | Valid goal declarations added to Goals-MOC.md Active Declarations in Felix format | Proposed |
| FR-016 | Valid goal declarations create Vikunja tasks in Goals project with target date as due date | Proposed |
| FR-017 | Partial/aspirational goals flagged as `type: potential-goal` in processing log — not added to Goals-MOC.md | Proposed |
| FR-018 | Agent never invents dates or evidence criteria for goals | Proposed |
| FR-019 | Schedule agent for 3x daily execution on office2 via OpenClaw scheduling | Proposed |
| FR-020 | Processing is idempotent — running twice on same files produces same result | Proposed |
| FR-021 | Failed scheduled runs logged without blocking subsequent runs | Proposed |
| FR-022 | On-demand WhatsApp trigger recognized from natural language ("process my inbox") | Proposed |
| FR-023 | WhatsApp response includes processing summary (files processed, actions taken, items flagged) | Proposed |
| FR-024 | Original Cowork skills preserved unchanged at ~/second-brain/.claude/skills/ | Proposed |
| FR-025 | No double-processing risk — `status: processed` frontmatter flag prevents re-processing | Proposed |
| FR-026 | Ops runbook created at docs/handbooks/inbox-ops.md | Proposed |
| FR-027 | Architecture docs updated (service-inventory.json, service-inventory.md) | Proposed |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
| --- | --- | --- | --- |
| NFR-001 | Processing quality equivalent to Cowork skills | Routing accuracy matches existing skill behavior for the same input | Proposed |
| NFR-002 | kent-voice fidelity in generated vault content | Content reads as Kent's voice, not generic AI — matches kent-voice skill examples | Proposed |
| NFR-003 | Processing completes within reasonable time per run | 10 inbox notes processed in under 5 minutes | Proposed |
| NFR-004 | Agent skills follow OpenClaw SKILL.md format | Matches Whisper and Vikunja API skill structure | Proposed |

## Constraints

| ID | Constraint | Status |
| --- | --- | --- |
| C-001 | Privacy: 02-Growth/_private/ is never read, processed, routed to, referenced, or logged | Active |
| C-002 | Vikunja task creation must use F007 API skill — no direct API calls | Active |
| C-003 | Agent must use claude user on office2 — never kgale | Active |
| C-004 | No credentials in code — Vikunja token via F007 skill credential store pattern | Active |
| C-005 | kent-voice is encoded in agent SOUL.md, not as a separate skill invocation | Active |
| C-006 | Cowork skills must not be modified or deleted | Active |
| C-007 | WhatsApp trigger contingent on OpenClaw intent routing research | Active |

## Success Criteria

1. felix-admin-capture agent runs 3x daily on office2 independently of Mac state
2. Full routing table behavior replicated — content classified and routed correctly for all content types
3. Kent's voice preserved in all generated vault content
4. Privacy boundary enforced — zero references to 02-Growth/_private/
5. Task items from inbox create Vikunja tasks in the Inbox project with correct identity labels
6. Research requests create Vikunja tasks in the Research project
7. Valid goal declarations reach both Goals-MOC.md and Vikunja Goals project
8. Processing log written after every run with full audit trail
9. Ops runbook complete and architecture docs updated

## Key Entities

| Entity | Description |
| --- | --- |
| Inbox Note | Markdown file in 00-Inbox/ with `status: unprocessed` frontmatter |
| Content Block | Extracted topic from an inbox note — classified by content type |
| Routing Table | Maps content types to vault destinations (from inbox-processor skill) |
| Processing Log | Audit trail at ~/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md |
| Felix Declaration | Goal format: "On [date], I have [outcome] as evidenced by [proof]" |
| Vikunja Task | Task created in Inbox, Research, or Goals project via F007 skill |
| SOUL.md | OpenClaw agent identity file — encodes kent-voice authoring standards |

## Assumptions

- Obsidian Sync on office2 keeps the vault reasonably current (planning phase should verify sync reliability)
- The claude user on office2 has write access to the vault via secondbrain group membership (planning phase should verify)
- OpenClaw supports scheduled agent execution (cron or equivalent — planning phase confirms mechanism)
- OpenClaw intent routing for WhatsApp-to-agent is feasible (research item — may result in deferral of FR-022/FR-023)
- The inbox-processor routing table and goal handling rules in the existing SKILL.md are the authoritative behavior spec

## Dependencies

- F001: Vikunja deployed and running
- F002: OpenClaw installed with credential store
- F004: WhatsApp channel operational (for on-demand trigger)
- F006: Goals project, identity labels, Goals-MOC.md Felix format
- F007: Vikunja API skill deployed and verified

## Scope Boundaries

**In scope**: Agent configuration, skill migration, Vikunja task bridge (tasks + research requests + goals), scheduled execution, WhatsApp trigger (pending research), ops runbook, architecture docs

**Out of scope**: Daily habit tracking (F009), escalation on inbox-derived tasks (F011), daily briefing (F013), inbox-to-goal routing from WhatsApp (separate capture path), modifying Cowork skill behavior, migration of kent-voice as a standalone OpenClaw skill

## Risk Considerations

- **Vault write conflicts**: Both office2 agent and Mac Cowork could process the same files. Mitigation: `status: processed` frontmatter flag is the mutex.
- **Processing quality regression**: OpenClaw agent context is more constrained than full Claude conversation. Mitigation: Processing logs enable quality comparison; Cowork fallback available.
- **Task noise**: Agent could create too many low-quality tasks from stream-of-consciousness content. Mitigation: Use existing `type: task` classification as threshold — err on inclusion, dial back later.
- **Vault permissions**: claude user write access may vary by subdirectory. Mitigation: Planning phase verifies write access before implementing.
- **Obsidian Sync reliability**: If sync is delayed or broken, agent processes stale data. Mitigation: Planning phase verifies sync status; ops runbook documents sync troubleshooting.
- **WhatsApp routing**: OpenClaw may not support routing specific intents to specific agents. Mitigation: Research during planning; defer FR-022/FR-023 if not feasible.
