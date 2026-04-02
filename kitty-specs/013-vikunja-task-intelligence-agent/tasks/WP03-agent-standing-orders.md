---
work_package_id: WP03
title: Agent Standing Orders
dependencies: [WP01, WP02]
requirement_refs:
- C-003
- C-005
- C-006
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-009
- FR-010
- FR-011
- FR-012
- FR-013
- FR-014
- FR-015
- FR-016
- FR-026
- FR-027
- NFR-001
- NFR-002
- NFR-003
- NFR-004
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T011, T012, T013, T014, T015, T016, T017]
history:
- date: '2026-04-02T12:53:14Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-tasker/
execution_mode: code_change
owned_files: [scripts/openclaw/agents/felix-admin-tasker/AGENTS.md]
---

# WP03: Agent Standing Orders

## Objective

Create the full AGENTS.md standing orders document for felix-admin-tasker at `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`. This is the core behavioral document — it defines how the agent handles all three action types: `enrich_task`, `retroactive_enrichment`, and `detect_incomplete`. It also defines the primary interaction channel abstraction, confirmation conversation patterns, enrichment state tracking, and action logging.

## Context

- **Feature**: 013-vikunja-task-intelligence-agent
- **Spec**: `kitty-specs/013-vikunja-task-intelligence-agent/spec.md` — FR-001 through FR-016, FR-026, FR-027
- **Data model**: `kitty-specs/013-vikunja-task-intelligence-agent/data-model.md` — entities, state transitions, enrichment flow
- **Agent delegation contract**: `kitty-specs/013-vikunja-task-intelligence-agent/contracts/agent-delegation-contract.md`
- **Vikunja API contract**: `kitty-specs/013-vikunja-task-intelligence-agent/contracts/vikunja-task-enrichment-contract.md`
- **Reference agents**: Read `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (~379 lines) and `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (~334 lines) for established format, tone, and section structure.

### Implementation command

```bash
spec-kitty implement WP03 --base WP02
```

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: WP01 (skill), WP02 (identity files)
- **Actual base branch**: WP02's branch (stacked) — follow `spec-kitty implement` output

---

## Subtask T011: Create AGENTS.md Framework

**Purpose**: Establish the AGENTS.md header, scope declaration, authority boundaries, operating mode, and privacy rules. This is the skeleton that all action sections build upon.

**Steps**:
1. Create `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`
2. Add header section following capture/habits agent format:
   ```markdown
   # felix-admin-tasker — Standing Orders

   **Autonomy Level**: Assisted (Level 1) — registered 2026-04-02 (F013)
   **Constitution**: Operates under Felix Constitution v1.0
   **Authority**: Task structuring and enrichment via Vikunja API
   ```

3. Add **Scope** section (Directive 1 — Narrow Scope):
   - **You handle**: Receiving raw task descriptions, reasoning through attributes, proposing structured tasks via interaction channel, creating confirmed tasks in Vikunja, retroactive enrichment of flat tasks, detection of incomplete directly-created tasks
   - **You do NOT handle**: Inbox processing (felix-admin-capture), habit tracking (felix-admin-habits), daily briefings, calendar management, email triage, goal declaration creation

4. Add **Operating Mode** section:
   - Current level: Assisted (Level 1)
   - At Assisted: Every task creation requires Kent's explicit confirmation
   - At Observed: Create tasks autonomously, surface all actions in daily digest
   - At Autonomous: Create tasks autonomously, surface only exceptions
   - Mode changes are recorded in AGENT-REGISTRY.md

5. Add **Privacy Rules**:
   - NEVER read, process, route to, reference, or log content from `~/second-brain/notes/02-Growth/_private/`
   - No exceptions. Not even in error logs.

6. Add **Skills Reference**:
   - `task-intelligence` skill: `~/.openclaw/skills/task-intelligence/SKILL.md` — read this for all structuring rules
   - `vikunja-api` skill: `~/.openclaw/skills/vikunja-api/SKILL.md` — read this for API patterns

**Validation**:
- [ ] Header with autonomy level and constitution reference
- [ ] Scope with positive and negative declarations
- [ ] Operating mode section with all three levels
- [ ] Privacy rules stated
- [ ] Skills referenced

---

## Subtask T012: Implement enrich_task Action Flow

**Purpose**: Define the core action flow for receiving a raw task and producing a structured, confirmed Vikunja task. This is the primary path triggered by delegation from felix-admin-capture.

**Steps**:
1. Add **Action: enrich_task** section with this flow:

   **Input**: JSON message from delegation:
   ```json
   {
     "action": "enrich_task",
     "raw_text": "...",
     "source_reference": "...",
     "inferred_identity": "...",
     "date_signals": [...],
     "context_signals": [...]
   }
   ```

2. Define **Step 1 — Attribute Reasoning**:
   - Read the task-intelligence skill
   - For each required attribute (title, identity, project, due date, priority):
     - Extract signals from raw_text, date_signals, context_signals, inferred_identity
     - Apply inference rules from skill
     - Assign confidence level (high ≥90% or low <90%)
   - For optional attributes (start date, repeat, goal, relationships):
     - Only evaluate if contextual signals suggest relevance
     - Apply inference rules from skill

3. Define **Step 2 — Goal Check**:
   - Query Goals project for active (non-done) goals
   - Compare task content against goal titles/descriptions
   - If plausible match found: include in proposal
   - If no match: omit silently

4. Define **Step 3 — Clarification (if needed)**:
   - If any required attribute has low confidence: send clarification question(s) via primary interaction channel
   - One focused question per uncertain attribute
   - Wait for Kent's response before proceeding
   - Format: `"New task from inbox: '{raw_text}'\nQuestion: {specific question about uncertain attribute}"`

5. Define **Step 4 — Proposal**:
   - Build enrichment proposal with all attributes
   - Send via primary interaction channel:
     ```
     New task from your inbox — "{title}"
       Proposed structure:
       • Project: {project}
       • Due: {due_date_human_readable}
       • Priority: {priority_name}
       • Label: {identity}
       [• Repeats: {interval} — only if applicable]
       [• Related goal: "{goal_title}" — only if applicable]
     ```
   - Wait for Kent's response

6. Define **Step 5 — Confirmation Handling**:
   - **Confirmed** ("yes", "looks good", "do it", "ok"): proceed to task creation
   - **Modified** ("yes but make it high priority", "change due date to Friday"): update proposal attributes, proceed without re-proposing
   - **Rejected** ("no", "skip", "don't add"): discard, log the rejection
   - **"Just add it"**: apply sensible defaults for any remaining gaps, proceed
   - Pattern: recognize natural language confirmation — do not require exact keywords

7. Define **Step 6 — Task Creation**:
   - Resolve project ID by name: `GET /projects`, find matching title
   - Resolve label ID by name: `GET /labels`, find matching title
   - Check for duplicates: `GET /projects/{id}/tasks?s={title}`
   - Create task: `PUT /projects/{project_id}/tasks` with all attributes
   - Add identity label: `PUT /tasks/{task_id}/labels` with `{label_id}`
   - If goal relationship confirmed: `PUT /tasks/{task_id}/relations` with `{other_task_id, "related"}`
   - Write enrichment state comment: `PUT /tasks/{task_id}/comments` with `[Felix] enrichment | confirmed | {timestamp}`
   - Log action to `~/second-brain/agents/logs/`
   - Confirm to Kent: `"✓ Done — Vikunja task #{id} created in {project}"`

8. Define **Step 7 — Error Handling**:
   - If any API call fails: follow error handling from task-intelligence skill
   - Never fail silently — every error produces channel notification + log entry

**Validation**:
- [ ] All 7 steps documented with clear instructions
- [ ] Delegation input format matches contract
- [ ] Proposal format is concise and structured
- [ ] Confirmation handling covers yes/modified/rejected/just-add-it
- [ ] Task creation follows two-step pattern (create + label)
- [ ] Goal relationship creation included
- [ ] Error handling references skill document

---

## Subtask T013: Define Primary Interaction Channel Abstraction

**Purpose**: Abstract the communication channel so the agent's logic doesn't hardcode WhatsApp, enabling future channel additions.

**Steps**:
1. Add **Primary Interaction Channel** section:
   ```markdown
   ## Primary Interaction Channel

   All Kent-facing communication uses the primary interaction channel.

   **Current channel**: WhatsApp
   **Channel capabilities required**:
   - Send text messages to Kent
   - Receive text replies from Kent
   - Support multi-turn conversation (question → answer → proposal → confirm)

   To change the channel, update this section. No other part of the
   standing orders references a specific channel by name.
   ```

2. Add **Confirmation Conversation Pattern**:
   - Proposals are sent as a single structured message
   - Kent replies with confirmation, modification, or rejection
   - Agent processes the reply and acts accordingly
   - Maximum 3 back-and-forth exchanges before escalating with "I need more guidance on this task"
   - If Kent doesn't respond within 24 hours: send one reminder, then log as "pending" and move to next task

**Validation**:
- [ ] No references to "WhatsApp" outside the channel configuration section
- [ ] Channel capabilities documented
- [ ] Conversation pattern defined with limits

---

## Subtask T014: Implement retroactive_enrichment Action

**Purpose**: Define the batch enrichment flow for existing flat tasks.

**Steps**:
1. Add **Action: retroactive_enrichment** section:

   **Input**: JSON message:
   ```json
   {"action": "retroactive_enrichment", "batch_size": 5}
   ```

2. Define **Step 1 — Identify Flat Tasks**:
   - Query Inbox project for non-done tasks: `GET /tasks/all?filter=done%20%3D%20false%20%26%26%20project_id%20%3D%201&sort_by=created&order_by=asc&per_page=50`
   - For each task, check:
     - No due_date (null or zero value)
     - OR no identity label (empty labels array)
     - OR still in Inbox after being created
   - Exclude tasks with existing enrichment comments (`[Felix] enrichment |`)
   - Exclude completed/archived tasks

3. Define **Step 2 — Batch Selection**:
   - Take first N tasks (batch_size, default 5, max 5)
   - Sort by creation date (oldest first)

4. Define **Step 3 — Batch Proposal**:
   - For each task in batch:
     - Apply attribute reasoning (same as enrich_task Step 1-2)
     - Build enrichment proposal
   - Present all proposals in a single channel message:
     ```
     Retroactive enrichment batch (3 tasks):

     1. "{title}" — Proposed: Project: {project} | Due: {date} | Priority: {priority}
     2. "{title}" — Proposed: Project: {project} | Due: {date} | Priority: {priority}
     3. "{title}" — Proposed: Project: {project} | Due: {date} | Priority: {priority}

     Reply with numbers to confirm, "skip 2" to skip, or "later" to defer all.
     ```

5. Define **Step 4 — Response Handling**:
   - "1, 3" or "confirm 1 and 3": enrich those tasks, skip others in batch
   - "skip 2": mark task 2 as skipped (add comment), process rest normally
   - "later" or "defer": pause entire batch, do not re-propose until next manual trigger
   - "all" or "yes": confirm all in batch
   - Handle modifications per-task: "1 yes, 2 skip, 3 yes but high priority"

6. Define **Step 5 — Batch Completion**:
   - After processing batch responses, wait at least 15 minutes before next batch (NFR-002)
   - Log batch results to action log
   - If more flat tasks remain, note count in log

**Validation**:
- [ ] Flat task identification query is correct
- [ ] Batch size respects limit (max 5)
- [ ] Batch proposal format is concise
- [ ] Response handling covers confirm/skip/defer/modify
- [ ] 15-minute pause between batches enforced
- [ ] Enrichment state comments written for each processed task

---

## Subtask T015: Define Enrichment State Comment Format

**Purpose**: Standardize how enrichment state is tracked in Vikunja task comments to prevent duplicate proposals and track history.

**Steps**:
1. Add **Enrichment State Tracking** section:
   - Format: `[Felix] enrichment | <status> | <ISO timestamp> | <optional notes>`
   - Statuses:
     - `proposed` — enrichment offered, awaiting Kent's response
     - `confirmed` — enrichment accepted, task updated
     - `skipped` — Kent explicitly skipped this task
     - `declined` — Kent declined enrichment for this task

2. Define **Comment Check Procedure**:
   - Before proposing enrichment for any task: `GET /tasks/{id}/comments`
   - Parse for `[Felix] enrichment |` prefix
   - If `skipped` or `declined` → do NOT re-propose (single-offer policy)
   - If `proposed` and older than 24 hours → may re-propose once
   - If `confirmed` → task already enriched, skip

3. Define **Comment Write Procedure**:
   - On proposal: write `[Felix] enrichment | proposed | {timestamp}`
   - On confirmation: write `[Felix] enrichment | confirmed | {timestamp}`
   - On skip: write `[Felix] enrichment | skipped | {timestamp} | Kent skipped during batch`
   - On decline: write `[Felix] enrichment | declined | {timestamp}`

**Validation**:
- [ ] Format is consistent and parseable
- [ ] Single-offer policy clearly enforced
- [ ] All status transitions documented
- [ ] Check-before-propose procedure explicit

---

## Subtask T016: Implement detect_incomplete Action

**Purpose**: Define the polling action that finds directly-created incomplete tasks and offers enrichment.

**Steps**:
1. Add **Action: detect_incomplete** section:

   **Input**: JSON message:
   ```json
   {"action": "detect_incomplete"}
   ```

2. Define **Step 1 — Query Incomplete Tasks**:
   - Same query as retroactive_enrichment Step 1
   - Additional filter: exclude tasks created by felix-admin-capture (check description for `[Felix]` prefix — these are handled by the delegation flow)
   - Focus on tasks that appear to be directly created by Kent

3. Define **Step 2 — Deduplication**:
   - Check each task's comments for existing enrichment state
   - Skip tasks with any `[Felix] enrichment |` comment (already proposed, confirmed, skipped, or declined)

4. Define **Step 3 — Single-Task Proposal**:
   - Unlike retroactive_enrichment (batch), detection offers enrichment one task at a time
   - Send via primary interaction channel:
     ```
     I noticed a task without full details: "{title}"
     Would you like me to help structure it? (yes/no)
     ```
   - If "yes": run enrich_task flow on this task
   - If "no": write `[Felix] enrichment | declined | {timestamp}` — never ask again

5. Define **Step 4 — Rate Limiting**:
   - Maximum 3 detection proposals per polling run
   - If more incomplete tasks exist, process remaining in next polling cycle
   - Log count of remaining incomplete tasks

**Validation**:
- [ ] Query excludes agent-created tasks
- [ ] Deduplication checks enrichment comments
- [ ] Single-task proposal (not batch) for detection
- [ ] Single-offer policy enforced (declined = never ask again)
- [ ] Rate limiting prevents flooding

---

## Subtask T017: Define Action Logging Format

**Purpose**: Define the structured logging format per Felix Constitution Directive 3.

**Steps**:
1. Add **Action Logging** section:
   - Log path: `~/second-brain/agents/logs/task-intelligence-YYYY-MM-DD.md`
   - Every action gets a log entry. No log entry = action did not happen.

2. Define **Log Entry Format**:
   ```markdown
   ## {HH:MM} — {action_type}

   - **Agent**: felix-admin-tasker
   - **Autonomy level**: Assisted (Level 1)
   - **Action**: {enrich_task | retroactive_enrichment | detect_incomplete}
   - **Target**: {task title or batch description}
   - **Outcome**: {accepted | confirmed | skipped | declined | error}
   - **Details**: {Vikunja task ID if created, error message if failed}
   ```

3. Define **Log Entry Triggers**:
   - Task proposal sent to Kent
   - Task confirmed and created in Vikunja
   - Task skipped or declined
   - Batch started/completed
   - Error encountered
   - Detection polling run (summary: X incomplete found, Y proposed)

**Validation**:
- [ ] Log path follows established pattern
- [ ] Entry format includes all required fields (agent, level, action, target, outcome)
- [ ] All action types produce log entries
- [ ] Directive 3 compliance: if logging fails, action is unexecuted

---

## Definition of Done

- [ ] `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` is complete
- [ ] All three action types documented: enrich_task, retroactive_enrichment, detect_incomplete
- [ ] Primary interaction channel abstraction in place — no hardcoded channel names in action flows
- [ ] Enrichment state comment format defined and used consistently
- [ ] Action logging follows Felix Constitution Directive 3
- [ ] AGENTS.md follows the structural pattern of felix-admin-capture and felix-admin-habits
- [ ] Privacy rules stated
- [ ] Scope boundaries (positive and negative) clearly declared

## Risks

- **Largest WP** (7 subtasks, ~600 lines). If implementation is struggling, T014-T016 (retroactive/detection) are the candidates for extraction to a follow-up WP.
- **Conversation pattern complexity**: The confirmation handling (T012 Step 5-6) has many branches. Test with varied natural language inputs.

## Reviewer Guidance

- Verify all Vikunja API calls match the contracts in `contracts/vikunja-task-enrichment-contract.md`
- Check that enrichment state comments use the exact format from T015
- Confirm single-offer policy is enforced in both retroactive and detection flows
- Verify no channel-specific references outside the channel abstraction section (T013)
- Compare overall structure against felix-admin-capture/AGENTS.md for format consistency
- Check that the delegation input format matches `contracts/agent-delegation-contract.md`
