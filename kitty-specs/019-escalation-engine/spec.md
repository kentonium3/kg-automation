# Escalation Engine

**Feature**: 019-escalation-engine
**Mission**: software-dev
**Status**: draft
**Priority**: HIGH
**Depends on**: F013 (Vikunja Task Intelligence Agent)

---

## Summary

Tasks in Vikunja now have due dates, priorities, and project placement (F013),
but no agent monitors them for slippage. Overdue tasks go unnoticed until Kent
checks manually. The Felix Constitution states "Insistence is a feature" — this
feature makes that directive operational.

A new specialist agent (`felix-admin-escalation`) runs daily, detects overdue
and at-risk tasks, delivers level-appropriate WhatsApp alerts (Level 1 nudge /
Level 2 insistence), tracks escalation state via structured Vikunja comments,
and handles Kent's responses. It is designed as a service layer that future
agents (Commitment Manager, escalation heartbeat) can build on.

---

## Actors

- **felix-admin-escalation agent**: Detects overdue tasks, delivers alerts,
  records escalation state, processes responses
- **Kent (system owner)**: Receives alerts, responds with actions (done, snooze,
  dismiss, reschedule, acknowledge)
- **Vikunja**: Source of truth for task state, due dates, and escalation comments
- **Future agents** (Commitment Manager, escalation heartbeat): Consumers of
  the `[Felix-Escalation]` comment format — not actors in F019, but the format
  must be designed for their consumption

---

## User Scenarios and Testing

### Scenario 1: Daily escalation run with overdue tasks

**Actor**: Kent
**Precondition**: Three tasks are overdue — one for 1 day, one for 4 days,
one low priority
**Flow**:
1. Escalation cron runs after morning habit check-in
2. Agent queries Vikunja for overdue tasks (done = false, due_date < today)
3. Agent filters: excludes Habits and Goals projects, excludes low priority
4. Two tasks qualify — 1-day overdue (Level 1), 4-day overdue (Level 2)
5. Agent delivers combined WhatsApp message with Level 2 task first
6. Agent writes `[Felix-Escalation]` comments to both tasks

**Acceptance**: WhatsApp message received with numbered list, visual
distinction between levels, response prompt included. Both tasks have
escalation comments in Vikunja.

### Scenario 2: Kent responds to escalation

**Actor**: Kent
**Precondition**: Escalation message received with 3 tasks listed
**Flow**:
1. Kent replies "1 done, 2 snooze 3d"
2. Agent marks task #1 as complete in Vikunja (sets done = true)
3. Agent writes `[Felix-Escalation] | done | acknowledged` comment on task #1
4. Agent writes `[Felix-Escalation] | snoozed:3d | acknowledged` comment on task #2
5. Agent confirms: "Marked #1 done. Snoozed #2 for 3 days."
6. Next day's run skips task #2 (snooze active)

**Acceptance**: Task #1 marked done in Vikunja. Task #2 has snooze comment.
Task #2 does not appear in next day's escalation until snooze expires.

### Scenario 3: Silent run — no tasks qualify

**Actor**: felix-admin-escalation agent
**Precondition**: No overdue tasks at medium+ priority outside Habits/Goals
**Flow**:
1. Escalation cron runs
2. Agent queries Vikunja — no qualifying tasks found
3. Agent completes silently — no WhatsApp message sent

**Acceptance**: No message delivered. Cron run shows status `ok`.

### Scenario 4: Level 1 escalates to Level 2

**Actor**: felix-admin-escalation agent
**Precondition**: Task was escalated at Level 1 two days ago, Kent did not respond
**Flow**:
1. Agent reads task's `[Felix-Escalation]` comments — finds Level 1 sent 2 days ago
2. No acknowledgment or response comment found after the Level 1 comment
3. Agent determines Level 2 is warranted (Level 1 for 2+ days with no response)
4. Agent delivers Level 2 alert and records Level 2 comment

**Acceptance**: Task appears as Level 2 (not Level 1) in today's message.
Level 2 comment added without modifying the earlier Level 1 comment.

### Scenario 5: Dismissed task with updated due date

**Actor**: Kent
**Precondition**: Kent previously dismissed a task's escalation
**Flow**:
1. Agent reads dismiss comment — skips the task
2. Later, Kent updates the task's due date to a future date in Vikunja
3. On the next run after the new due date passes, the agent detects the
   task as overdue again
4. The escalation history effectively resets — the task is treated as
   newly overdue

**Acceptance**: Dismissed task is not re-escalated until its due date changes
and it becomes overdue again under the new date.

### Scenario 6: Ambiguous response handling

**Actor**: Kent
**Precondition**: Escalation message sent with 2 tasks
**Flow**:
1. Kent replies "handle it"
2. Agent cannot determine specific action or task number
3. Agent asks one clarifying question: "Which task? And would you like to
   mark it done, snooze, or reschedule?"
4. Kent replies "1 snooze 2d"
5. Agent processes normally

**Acceptance**: Ambiguous input does not trigger any Vikunja action. One
clarifying question asked. After clarification, action processed correctly.

---

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | On each scheduled run, the agent must query Vikunja for tasks where due_date < today and done = false, excluding the Habits project (ID 13) and Goals project | draft |
| FR-002 | Only tasks with priority Medium or above are escalated; low-priority overdue tasks are excluded | draft |
| FR-003 | For each qualifying task, the agent must determine the escalation level: Level 1 (nudge) for tasks overdue 1-3 days with no prior escalation, or due today with high priority; Level 2 (insistence) for tasks overdue >3 days or at Level 1 for 2+ days with no response | draft |
| FR-004 | The agent must deliver a combined WhatsApp message with Level 2 tasks listed first (marked with distinct visual indicator), followed by Level 1 tasks, numbered sequentially, capped at 7 tasks with overflow count | draft |
| FR-005 | After sending an alert, the agent must write a structured `[Felix-Escalation]` comment to each escalated task recording the escalation event with date, level, and state | draft |
| FR-006 | The agent must handle Kent's responses: done (marks task complete in Vikunja), snooze (suppresses re-escalation for N days, default 1), dismiss (permanently suppresses), reschedule (updates due_date, resets escalation history), and acknowledge (records without action) | draft |
| FR-007 | Tasks that Kent has snoozed must not be re-escalated until the snooze window expires; dismissed tasks must not be re-escalated unless their due_date is updated to a future date | draft |
| FR-008 | The agent must not send duplicate Level 2 alerts for the same task on the same calendar day | draft |
| FR-009 | If no qualifying tasks are found, the agent must complete silently — no WhatsApp message sent | draft |
| FR-010 | Ambiguous responses must prompt one clarifying question before taking any action | draft |
| FR-011 | The escalation cron job must run daily, after the morning habit check-in (7:05 AM ET), as an independent agent with independent scope | draft |
| FR-012 | A manual trigger must be available for testing and on-demand escalation checks | draft |
| FR-013 | An escalation skill must be created encoding the full escalation model: criteria, levels, comment format, response patterns, and error handling | draft |
| FR-014 | An operations runbook must be created covering agent operation, manual triggers, escalation history, threshold adjustment, temporary pause, and troubleshooting | draft |
| FR-015 | The agent must be registered in the Agent Registry at Assisted (Level 1) | draft |
| FR-016 | Architecture documentation must be updated: service-inventory.json with agent and cron entries, service-inventory.md with narrative update | draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | The daily escalation run must complete within the OpenClaw cron timeout | <= 120s total | draft |
| NFR-002 | The `[Felix-Escalation]` comment format must be machine-parseable by future agents without ambiguity | Zero parsing failures on well-formed comments | draft |
| NFR-003 | The escalation skill must be self-contained — the agent can apply the full escalation model by reading the skill alone | No external references required | draft |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | Escalation comments are append-only — the agent must never modify or delete existing comments | active |
| C-002 | The agent must not autonomously reschedule, reprioritize, or delete tasks — all mutations require Kent's explicit response | active |
| C-003 | The Habits project (ID 13) and Goals project are excluded from escalation | active |
| C-004 | The agent starts at Assisted (Level 1) autonomy — all alert sends are actions, but task mutations only happen in response to Kent's explicit reply | active |
| C-005 | `02-Growth/_private/` is never read or referenced; private-context tasks appear as task names only | active |
| C-006 | If Vikunja is unavailable or a comment write fails, the failure must be logged — the agent must not proceed as if delivery succeeded | active |

---

## Escalation Level Model

| Level | Name | Trigger | Tone |
|-------|------|---------|------|
| 1 | Nudge | Task due today (high priority only) OR overdue 1-3 days with no prior escalation | Informational — "this needs attention" |
| 2 | Insistence | Task overdue >3 days OR at Level 1 for 2+ days with no response | Direct — "this is slipping" |

**Escalation state determination**: The agent reads the most recent
`[Felix-Escalation]` comment on each task to determine current state
before deciding whether and at what level to escalate.

**Priority filter**: Medium and above only. Low-priority overdue tasks
accumulate in the Vikunja Overdue filter for manual triage.

**Project filter**: All projects except Habits (ID 13) and Goals.

---

## Escalation Comment Format

The `[Felix-Escalation]` comment format is the machine-readable state
record for escalation. It must be parseable by the escalation agent and
by future agents (Commitment Manager, escalation heartbeat).

**Escalation sent**:
```
[Felix-Escalation] YYYY-MM-DD | level-1 | sent
[Felix-Escalation] YYYY-MM-DD | level-2 | sent
```

**Response recorded**:
```
[Felix-Escalation] YYYY-MM-DD | snoozed:Nd | acknowledged
[Felix-Escalation] YYYY-MM-DD | dismissed | acknowledged
[Felix-Escalation] YYYY-MM-DD | done | acknowledged
[Felix-Escalation] YYYY-MM-DD | rescheduled:YYYY-MM-DD | acknowledged
```

**Design principles for future extensibility**:
- Prefix `[Felix-Escalation]` distinguishes from `[Felix]` habit comments
- Pipe-delimited fields: date | state | disposition
- States are lowercase, hyphenated tokens — new states can be added without
  breaking existing parsers that match on known tokens
- `acknowledged` is the disposition for all response types — distinguishes
  agent-sent escalations from Kent-responded outcomes

---

## Scope

### In scope

- New `felix-admin-escalation` agent with workspace files (SOUL.md, USER.md,
  IDENTITY.md, TOOLS.md, AGENTS.md)
- Escalation skill encoding the full model
- Daily cron job configuration
- WhatsApp alert delivery with Level 1/Level 2 visual distinction
- Escalation state tracking via Vikunja comments
- Response handling (done, snooze, dismiss, reschedule, acknowledge)
- Operations runbook
- Agent Registry entry
- Architecture documentation updates (service-inventory)

### Out of scope

- Calendar-aware escalation (time-blocking, meeting conflicts) — F024
- Goal-level commitment assessment — F020 (Commitment Manager)
- Escalation of habit misses — managed by felix-admin-habits
- Automated task rescheduling without Kent's input
- Escalation of goal tasks — Goals project excluded
- Push notifications via any channel other than WhatsApp
- Escalation of tasks in the Habits project

---

## Success Criteria

### Detection
- Overdue tasks detected daily, filtered by priority (medium+) and project
  (excluding Habits and Goals)
- Escalation level correctly determined from overdue duration and comment history
- Snoozed, dismissed, and done tasks correctly excluded from escalation
- Silent run when no tasks qualify — no message sent

### Alert delivery
- Level 1 and Level 2 alerts delivered via WhatsApp in a combined message
- Message is concise, numbered, with visual distinction by level
- List capped at 7 tasks with overflow count noted

### State tracking
- `[Felix-Escalation]` comments written to each escalated task after alert
- All response outcomes recorded as comments
- Comments are append-only — no modification of existing comments
- Comment format is consistent and machine-parseable

### Response handling
- Done, snooze, dismiss, reschedule, and acknowledge all processed correctly
- "All snooze Nd" applies to every task in the message
- Ambiguous responses prompt one clarifying question

### Infrastructure
- Escalation cron job running daily after habit check-in
- Manual trigger available
- Escalation skill deployed to office2
- Operations runbook complete and CI-passing
- Agent registered in AGENT-REGISTRY.md at Assisted (Level 1)
- service-inventory.json updated with agent and cron entries

---

## Key Entities

| Entity | Role | Changes in this feature |
|--------|------|------------------------|
| felix-admin-escalation agent | New specialist agent | Created with full workspace files |
| Escalation skill | Encodes the escalation model | Created at scripts/openclaw/skills/escalation/ |
| Vikunja tasks | Source of due dates and priorities | Escalation comments added; done status set on "done" response |
| `[Felix-Escalation]` comments | Machine-readable escalation state | New comment format defined and written |
| Escalation cron job | Daily trigger | New cron job in OpenClaw |
| escalation-ops.md | Operations runbook | New document |
| Agent Registry | Agent governance record | New entry for felix-admin-escalation |
| service-inventory.json | Architecture record | New agent and cron entries |

---

## Assumptions

- The Vikunja Overdue filter expression (`due_date < now/d && done = false`)
  correctly identifies overdue tasks — confirmed by F013 deployment
- Task priority values in Vikunja are numeric (0=unset, 1=low, 2=medium,
  3=high, 4=urgent) — planning phase must confirm the exact mapping
- The Goals project ID is discoverable via the Vikunja API (project listing)
- OpenClaw cron configuration follows the same pattern as habits-morning-checkin
- The vikunja_api skill already supports task comment creation, task completion
  (marking done), and task update (due_date modification)
- WhatsApp delivery via OpenClaw `--to` flag works the same as for the habits agent

---

## Dependencies

- **F013**: Task intelligence agent — provides structured tasks with due dates
  and priorities that the escalation engine reads
- **felix-admin-habits pattern**: Comment-as-state model, cron agent pattern,
  WhatsApp delivery — all established by F009/F018 and copied here
- **vikunja_api skill**: API capabilities for task queries, comment operations,
  and task mutations

---

**END OF SPECIFICATION**
