---
work_package_id: WP02
title: Agent Workspace Files
dependencies: [WP01]
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T002, T003, T004, T005, T006, T007]
history:
- date: '2026-04-06'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-escalation/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-escalation/**
---

# WP02: Agent Workspace Files

## Objective

Create the complete `felix-admin-escalation` agent workspace at
`scripts/openclaw/agents/felix-admin-escalation/` with all supporting
files and the AGENTS.md standing orders covering detection, level
determination, alert delivery, comment writing, and response handling.

## Context

**Pattern reference**: The habits agent at
`scripts/openclaw/agents/felix-admin-habits/` is the closest pattern.
Read its SOUL.md, USER.md, IDENTITY.md, TOOLS.md, and AGENTS.md before
creating the escalation agent's files.

**Skill dependency**: This WP depends on WP01 (escalation skill). The
AGENTS.md instructions tell the agent to read the escalation skill for
the full model. The AGENTS.md should reference the skill but not
duplicate its content — the skill is the authoritative model definition.

**Key constraint**: The agent starts at Assisted (Level 1) — all alert
sends are actions, but task mutations (mark done, reschedule) only
happen in response to Kent's explicit reply.

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP02 --base WP01`

---

## Subtask T002: Create IDENTITY.md

**Purpose**: Agent identity metadata for OpenClaw registration.

**File**: `scripts/openclaw/agents/felix-admin-escalation/IDENTITY.md`

**Content should include**:
- Agent name: `felix-admin-escalation`
- Role: Escalation specialist — detects overdue tasks and delivers
  level-appropriate alerts
- Autonomy level: Assisted (Level 1)
- Scope: Overdue and at-risk task escalation only
- Deployed: F019

Follow the format of the habits agent's IDENTITY.md.

---

## Subtask T003: Create SOUL.md

**Purpose**: Kent-voice authoring identity.

**File**: `scripts/openclaw/agents/felix-admin-escalation/SOUL.md`

Copy from `scripts/openclaw/agents/felix-admin-habits/SOUL.md` and
adapt the identity section. The escalation agent's voice should be:
- Direct and clear — not passive or apologetic
- "Insistence is a feature" — Level 2 messages should feel deliberate,
  not aggressive
- Brief — WhatsApp messages are scannable, not essays

---

## Subtask T004: Create USER.md

**Purpose**: Kent's context for the agent.

**File**: `scripts/openclaw/agents/felix-admin-escalation/USER.md`

Copy from `scripts/openclaw/agents/felix-admin-habits/USER.md`.
No escalation-specific modifications needed — Kent's context is
the same across agents.

---

## Subtask T005: Create TOOLS.md

**Purpose**: Vikunja API reference tailored for escalation operations.

**File**: `scripts/openclaw/agents/felix-admin-escalation/TOOLS.md`

**Must include**:
- How to query overdue tasks: the filter expression and API endpoint
- How to read task comments (for escalation state)
- How to write task comments (for recording escalation)
- How to mark a task as done (`done: true`)
- How to update a task's due_date (for reschedule)
- How to list projects (to resolve project names for alert messages)
- Vikunja API base URL and token location
- Priority value mapping: 0=unset, 1=low, 2=medium, 3=high, 4=urgent
- Project IDs to exclude: 11 (Goals), 13 (Habits)

Study the habits agent's TOOLS.md and the vikunja-api skill for format
and content conventions.

---

## Subtask T006: Create AGENTS.md — Detection and Alerting

**Purpose**: The core standing orders for the daily escalation run.

**File**: `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`

**Structure** (follow the habits agent's AGENTS.md format):

1. **Governance header**: Autonomy Level, Constitution reference, Registry link
2. **Authority and Scope**: What this agent does and doesn't do
3. **Daily escalation run** — the main workflow:
   - Step 1: Read the escalation skill (`cat ~/.openclaw/skills/escalation/SKILL.md`)
   - Step 2: Query Vikunja for overdue tasks (filter: `done = false`,
     `due_date < today`, `priority >= 2`, exclude project IDs 11 and 13)
   - Step 3: Also query for high-priority tasks due today
     (`done = false`, `due_date = today`, `priority >= 3`, same project exclusions)
   - Step 4: For each qualifying task, read its `[Felix-Escalation]` comments
     to determine current escalation state and level
   - Step 5: Apply the level determination algorithm from the skill
   - Step 6: Format the WhatsApp message per the skill's message format
   - Step 7: Deliver the message
   - Step 8: Write `[Felix-Escalation]` comments to each escalated task
   - Step 9: If no tasks qualify, complete silently — no message sent

**Important details to include in the steps**:
- The agent must re-check `done` status before sending (in case a task
  was completed between query and alert)
- Daily deduplication: check for existing Level 2 comment with today's date
- Error handling: if Vikunja is down, log and exit — do NOT send "nothing
  overdue" message; do NOT write comments if delivery failed

---

## Subtask T007: Create AGENTS.md — Response Handling

**Purpose**: Add the response handling section to AGENTS.md.

**File**: Same file as T006 — append after the daily run section.

**Add these sections**:

4. **Response handling**: When Kent replies to an escalation alert
   - Parse the response using patterns from the escalation skill
   - Match task numbers to the numbered list in the most recent alert
   - For each recognized action:
     - **Done**: Call Vikunja API to mark task complete, write comment
     - **Snooze**: Write snooze comment (default 1d if not specified)
     - **Dismiss**: Write dismiss comment
     - **Reschedule**: Confirm the parsed date, update due_date, write comment
     - **Acknowledge**: Write acknowledgment comment, no task mutation
   - Confirm back to Kent what was recorded
   - If ambiguous: ask ONE clarifying question, do not guess

5. **Action logging**: Log every significant action using
   `log_action.py` (same pattern as habits agent)

6. **Error handling**: If Vikunja is unavailable when processing a
   response, tell Kent the action couldn't be completed and to try
   again. Do not silently drop the response.

7. **Privacy boundary**: `02-Growth/_private/` is never read or
   referenced. Tasks from private context appear as task names only.

---

## Definition of Done

- [ ] All 5 workspace files exist in `scripts/openclaw/agents/felix-admin-escalation/`
- [ ] AGENTS.md covers: governance, authority, daily run (9 steps), response handling, error handling, privacy
- [ ] AGENTS.md references the escalation skill without duplicating its content
- [ ] TOOLS.md includes all required API operations with correct endpoints
- [ ] All files follow the habits agent format conventions
- [ ] No implementation details leak beyond what the agent needs to operate

## Risks

| Risk | Mitigation |
|------|------------|
| AGENTS.md too long and agent ignores parts | Structured with numbered steps and clear section breaks |
| Agent confuses escalation skill with vikunja-api skill | AGENTS.md explicitly names which skill to read for what |

## Reviewer Guidance

1. Read AGENTS.md end-to-end — does it provide a complete, unambiguous
   workflow for the daily run?
2. Verify the skill reference is correct (`~/.openclaw/skills/escalation/SKILL.md`)
3. Confirm response handling covers all 5 response types
4. Check TOOLS.md has all API operations needed for both detection and response
5. Verify privacy boundary section is present

---

**END OF WORK PACKAGE**

## Activity Log

- 2026-04-06T20:09:36Z – unknown – Moved to for_review
