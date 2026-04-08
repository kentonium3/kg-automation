---
title: "F019: Escalation Engine"
doc_type: func-spec
status: draft
feature: F019
---

# F019: Escalation Engine

**Version**: 1.0
**Priority**: HIGH
**Type**: Infrastructure
**Depends on**: F013 (Vikunja Task Intelligence Agent — structured tasks with due dates)

---

## Executive Summary

Tasks are now structured with due dates, priorities, and project placement (F013).
The system has no mechanism to act on that structure — overdue tasks and approaching
deadlines go unnoticed until Kent happens to check Vikunja. The constitution is
explicit: "Insistence is a feature." This feature makes that directive operational.

Current gaps:
- ❌ No detection of overdue or at-risk tasks
- ❌ No proactive escalation — Felix never pushes back on slipping commitments
- ❌ No escalation level model — all tasks are treated identically regardless of urgency
- ❌ No escalation state — an escalated task has no record of having been escalated
- ❌ No response path — Kent has no way to acknowledge, snooze, or dismiss an alert

This spec delivers a dedicated escalation agent (`felix-admin-escalation`) that runs
daily, detects tasks meeting escalation criteria, delivers level-appropriate alerts via
WhatsApp, tracks escalation state in Vikunja, and handles Kent's responses. It is the
foundation on which the Commitment Manager (F020) and calendar-aware escalation
heartbeat (F024) will build.

---

## Problem Statement

**Current State:**

```
Vikunja (post-F013)
├── ✅ Tasks have due dates, priorities, and project placement
├── ✅ Overdue filter shows what's late
├── ❌ No agent reads the overdue filter and acts on it
└── ❌ Overdue tasks sit silently — Kent discovers them manually or not at all

Felix
├── ✅ felix-admin-tasker structures incoming tasks
├── ✅ felix-admin-habits tracks habit completion
├── ✅ felix-core-digest surfaces agent activity
└── ❌ No agent monitors commitment status and escalates proactively
```

**Target State:**

```
felix-admin-escalation (F019) — new specialist agent
├── ✅ Daily run: queries Vikunja for overdue and at-risk tasks
├── ✅ Applies escalation level model (Level 1 nudge / Level 2 insistence)
├── ✅ Delivers level-appropriate WhatsApp alert with task context
├── ✅ Records escalation state as structured Vikunja comment
├── ✅ Handles Kent's response: snooze, dismiss, update due date, or mark done
└── ✅ Escalation state prevents repeated alerts on same task without response

Vikunja
└── ✅ Escalated tasks carry escalation comments readable by future agents
    (Commitment Manager, escalation heartbeat)
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **Vikunja task structure post-F013**
   - `docs/runbooks/vikunja-ops.md` — saved filters, project structure, labels
   - `scripts/openclaw/skills/vikunja-api/SKILL.md` — full API skill; note the
     saved Overdue filter and its query expression; note how task comments work
   - The Overdue filter (`due_date < now/d && done = false`) is the primary
     input to escalation. The Today filter is secondary.
   - Study how the habits agent writes structured comments — the escalation
     agent follows the same comment-as-state pattern

2. **Constitution — Insistence and Autonomy**
   - `docs/constitution/FELIX-CONSTITUTION.md` — Directive 2 (Earned Autonomy),
     the surfacing behavior table, and the safety parameters
   - This agent starts at Assisted (Level 1) — all escalation messages are
     sent but Kent retains final authority on every response
   - "Insistence is a feature" (Design Principle 2 in roadmap) is the mandate;
     this feature implements it within constitutional constraints

3. **felix-admin-habits as the pattern reference**
   - `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` — study the cron
     agent pattern: how it queries Vikunja, formats WhatsApp messages, and
     records state as structured task comments
   - `docs/runbooks/habits-ops.md` — study the runbook structure for the
     ops runbook this spec must produce

4. **Commitment Manager concept stub**
   - `docs/func-spec/FUTURE_commitment_manager_agent.md` — understand what
     the Commitment Manager (F020) will build on top of this feature
   - The escalation comment format defined here must be readable by the
     Commitment Manager — design it with that consumer in mind

5. **F013 task-intelligence skill**
   - `scripts/openclaw/skills/task-intelligence/SKILL.md` — understand the
     task structure conventions the escalation agent reasons against
   - Priority model, project placement, and goal relationships are inputs
     to escalation severity assessment

---

## Escalation Level Model

The escalation engine applies a two-level model. Level determines message
tone and urgency. Escalation level is a function of overdue duration and
prior escalation history.

| Level | Name | Trigger | Tone | Action |
|-------|------|---------|------|--------|
| 1 | Nudge | Task due today OR overdue 1–3 days with no prior escalation | Informational — "this needs attention" | Send Level 1 alert; record escalation comment |
| 2 | Insistence | Task overdue >3 days OR at Level 1 for 2+ days with no response | Direct — "this is slipping" | Send Level 2 alert; record escalation comment |

**Priority filter:** Only tasks with priority Medium or above are escalated.
Low-priority tasks that are overdue are not escalated — they accumulate in the
Overdue filter for manual triage. This prevents alert fatigue on non-critical work.

**Project filter:** All projects are in scope for escalation except the Habits
project (managed by felix-admin-habits) and the Goals project (goals are anchors,
not tasks to complete).

**Escalation state is determined from Vikunja comment history**, using the
structured comment format defined in FR-4. The agent reads these comments before
deciding whether to escalate and at what level.

---

## Functional Requirements

### FR-1: Daily Overdue and At-Risk Task Detection

**What it must do:**
- On each scheduled run, query Vikunja for tasks meeting escalation criteria
- Apply the priority and project filters defined in the escalation level model
- For each qualifying task, determine the appropriate escalation level based
  on overdue duration and existing escalation comment history
- Tasks due today (not yet overdue) qualify for a pre-emptive Level 1 alert
  only if they are high priority

**Business rules:**
- A task that is already done is never escalated — always check `done = false`
- A task that Kent has snoozed (per FR-5) is not escalated until the snooze
  window expires
- A task that Kent has dismissed (per FR-5) is never escalated again unless its
  due date is updated to a future date, at which point the escalation history resets
- If no qualifying tasks are found, the agent runs silently — no message sent

**Success criteria:**
- [ ] Overdue tasks (all projects except Habits and Goals) detected correctly
- [ ] Priority filter applied — Low priority tasks excluded
- [ ] Escalation level determined from overdue duration and comment history
- [ ] Snoozed and dismissed tasks correctly skipped
- [ ] Silent run when no tasks qualify

---

### FR-2: Level 1 Alert Delivery (Nudge)

**What it must do:**
- Deliver a concise WhatsApp message listing tasks at Level 1 escalation
- Each task listed with: name, project, days overdue (or "due today"),
  and the identity label
- Message must be concise — one line per task, scannable at a glance
- Include a prompt for response at the end of the message

**Example message format:**

```
⚠️ Tasks needing attention:

• [Intentional] Prepare Codie Sanchez call agenda — 2 days overdue
• [Personal] Book physio follow-up — due today (high priority)

Reply with the task number to snooze (e.g. "1 snooze 2d"),
mark done ("1 done"), or update the date ("1 move to friday").
```

**Business rules:**
- Level 1 and Level 2 tasks may be combined in one message, with Level 2
  tasks listed first and clearly marked (e.g. 🔴 vs ⚠️)
- If the combined list exceeds 7 tasks, cap at 7 and note how many more exist
- Numbered list format is required — response handling (FR-5) keys on numbers

**Success criteria:**
- [ ] Alert delivered via WhatsApp when Level 1 tasks exist
- [ ] Each task shown with name, project, overdue duration, identity label
- [ ] Response prompt included
- [ ] Combined Level 1 + Level 2 message formatted with clear visual distinction
- [ ] List capped at 7 with overflow count

---

### FR-3: Level 2 Alert Delivery (Insistence)

**What it must do:**
- Include Level 2 tasks at the top of the combined escalation message,
  visually distinct from Level 1 tasks
- Level 2 message copy must be direct and specific about the duration
  of slippage — not just "overdue" but "overdue 5 days"
- If the only tasks are Level 2 (no Level 1 tasks), the message opener
  must reflect the seriousness: not a casual nudge

**Example Level 2 task line:**

```
🔴 [Intentional] Send consulting proposal to Acme — 5 days overdue
```

**Business rules:**
- A task cannot skip from no-escalation to Level 2 in a single run —
  Level 2 requires either >3 days overdue OR prior Level 1 with no response
- The agent does not repeat a Level 2 alert on the same task within the
  same calendar day — once per day maximum

**Success criteria:**
- [ ] Level 2 tasks appear above Level 1 tasks with distinct visual marker
- [ ] Level 2 copy includes specific overdue duration
- [ ] No same-day duplicate Level 2 alerts for the same task

---

### FR-4: Escalation State via Vikunja Comments

**What it must do:**
- After sending an escalation alert, write a structured comment to each
  escalated task in Vikunja recording the escalation event
- The comment format must be machine-readable for future agents
  (Commitment Manager, escalation heartbeat)
- On response (FR-5), write a follow-up comment recording the outcome

**Required comment format:**

Escalation sent:

```
[Felix-Escalation] YYYY-MM-DD | level-1 | sent
[Felix-Escalation] YYYY-MM-DD | level-2 | sent
```

Response recorded:

```
[Felix-Escalation] YYYY-MM-DD | snoozed:Nd | acknowledged
[Felix-Escalation] YYYY-MM-DD | dismissed | acknowledged
[Felix-Escalation] YYYY-MM-DD | done | acknowledged
[Felix-Escalation] YYYY-MM-DD | rescheduled:YYYY-MM-DD | acknowledged
```

**Business rules:**
- Comments are append-only — never modify or delete existing escalation comments
- The agent reads the most recent `[Felix-Escalation]` comment to determine
  current escalation state before deciding whether to send a new alert
- Comment format must be consistent — the planning phase must not deviate
  from this format without updating this spec

**Success criteria:**
- [ ] Escalation comment written to each escalated task after alert is sent
- [ ] Response comment written when Kent responds
- [ ] Comments are append-only — no modification of existing comments
- [ ] Comment format matches specification exactly

---

### FR-5: Response Handling

**What it must do:**
- Recognize Kent's reply to an escalation alert and record the appropriate
  outcome in Vikunja
- Support the following response types:
  - **Done**: Mark the task complete in Vikunja
  - **Snooze**: Suppress escalation for N days; leave task open; record snooze comment
  - **Dismiss**: Permanently suppress escalation for this task; leave task open; record dismiss comment
  - **Reschedule**: Update the task's due date in Vikunja; reset escalation history
  - **Acknowledge only**: Record that the alert was seen; Level 2 demotes to Level 1

**Natural language response examples:**

```
"1 done" → mark task #1 as complete
"2 snooze 3d" → snooze task #2 for 3 days
"1 and 3 done" → mark tasks #1 and #3 complete
"move 2 to next monday" → reschedule task #2 to next Monday
"1 dismiss" → stop escalating task #1
"got it" → acknowledge without specific action (records acknowledgment)
"all snooze 2d" → snooze all listed tasks for 2 days
```

**Business rules:**
- Response is keyed to the numbered list in the escalation message — numbers
  must match positions in the message as sent
- "Done" via this channel calls the Vikunja API to mark the task complete —
  it is not just a comment, it is an action
- Snooze duration defaults to 1 day if not specified
- "Got it" or any vague acknowledgment without a specific action records an
  acknowledgment comment but takes no other action
- If the response is ambiguous, the agent asks one clarifying question before
  acting — it does not guess

**Success criteria:**
- [ ] "Done" marks the task complete in Vikunja
- [ ] "Snooze N days" writes a snooze comment and suppresses re-escalation until expiry
- [ ] "Dismiss" writes a dismiss comment and permanently suppresses escalation
- [ ] "Reschedule" updates due_date in Vikunja and resets escalation history
- [ ] Acknowledgment without action writes an acknowledgment comment
- [ ] Ambiguous responses prompt one clarifying question
- [ ] "All snooze Nd" applies to every task in the message

---

### FR-6: Escalation Run Schedule

**What it must do:**
- Run on a daily schedule as an OpenClaw cron job
- Run time should be after the morning habit check-in (which runs at 7:05 AM ET)
  so habit context is already in Kent's awareness when task escalations arrive
- The escalation run must be a separate cron job from the habits agent — they
  are independent agents with independent scopes

**Business rules:**
- Planning phase determines the exact run time — 8:00 AM ET is a reasonable
  starting point, but the implementation may adjust based on other cron timing
- The agent does not run multiple times per day by default — a single daily
  run is appropriate for this level of maturity
- A manual trigger must be available for testing and on-demand escalation checks

**Success criteria:**
- [ ] Escalation cron job configured and running daily
- [ ] Run occurs after habit check-in
- [ ] Manual trigger available via `openclaw cron run <uuid>`
- [ ] Silent run (no alert sent) when no tasks qualify

---

### FR-7: Escalation Skill

**What it must do:**
- Create a `escalation` skill at `scripts/openclaw/skills/escalation/SKILL.md`
  that encodes the escalation level model, detection criteria, comment format,
  response handling patterns, and the WhatsApp message format
- This skill is what `felix-admin-escalation` reads to apply consistent
  escalation behavior

**What the skill encodes:**
- Escalation criteria: overdue duration thresholds, priority filter, project filter
- Level 1 vs Level 2 determination logic
- The `[Felix-Escalation]` comment format (exact syntax, all valid states)
- WhatsApp message format and the numbered list pattern
- Response parsing rules
- Snooze expiry calculation
- What to do when Vikunja is unavailable

**Success criteria:**
- [ ] Skill written and deployed to office2
- [ ] Skill is self-contained — `felix-admin-escalation` can apply the
  full escalation model by reading this skill alone
- [ ] Comment format documented precisely enough that future agents
  can parse it without ambiguity

---

### FR-8: Operations Runbook

**What it must do:**
- Create `docs/runbooks/escalation-ops.md` covering:
  - How `felix-admin-escalation` operates and what it escalates
  - How to manually trigger an escalation check
  - How to view escalation history for a task (via Vikunja comments)
  - How to adjust the priority threshold or project exclusions
  - How to pause escalation temporarily (e.g., during travel)
  - Troubleshooting: no alerts received, duplicate alerts, wrong tasks escalated

**Success criteria:**
- [ ] Runbook exists and covers all topics
- [ ] Agent registered in `docs/constitution/AGENT-REGISTRY.md` at Assisted (Level 1)

---

## Architecture Documentation Updates

F019 adds a new agent and cron job. No new services, ports, or credentials.

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Add `felix-admin-escalation` agent entry under `openclaw-gateway.agents`; add escalation cron job entry; set `updated_by: "F019"` |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Add `felix-admin-escalation` under OpenClaw agents section |
| `docs/constitution/AGENT-REGISTRY.md` | Add `felix-admin-escalation` at Assisted (Level 1) |

### No Changes Required

- `network-topology.json` — no new ports
- `credential-manifest.json` — Vikunja API token already exists
- `hardware-inventory.json` — no hardware changes
- `data-flows.json` — escalation reads Vikunja and writes WhatsApp/comments,
  consistent with existing OpenClaw data flow patterns

**Success criteria:**
- [ ] `service-inventory.json` updated with `updated_by: "F019"`
- [ ] Markdown views match JSON sources

---

## Out of Scope

- ❌ Calendar-aware escalation (time-blocking awareness, meeting conflicts) — F024,
  which depends on both this feature and the Calendar skill (F021)
- ❌ Goal-level commitment assessment — F020 (Commitment Manager); that agent
  reasons across goals and outcomes; this agent focuses narrowly on task due dates
- ❌ Escalation of habit misses — habits have their own completion model in
  felix-admin-habits; the escalation engine does not touch the Habits project
- ❌ Automated task rescheduling without Kent's input — the agent proposes
  and records, Kent decides
- ❌ Escalation of goal tasks — Goals project excluded; goals are anchors,
  not tasks with completion deadlines
- ❌ Push notification via any channel other than WhatsApp — primary channel
  only for this feature; multi-channel is future scope

---

## Success Criteria

**Complete when:**

### Detection
- [ ] Overdue tasks detected daily, filtered by priority and project
- [ ] Escalation level correctly determined from overdue duration and comment history
- [ ] Snoozed, dismissed, and done tasks correctly excluded

### Alert Delivery
- [ ] Level 1 and Level 2 alerts delivered via WhatsApp in combined message
- [ ] Message format concise, numbered, visually distinct by level
- [ ] Silent run when no tasks qualify

### State Tracking
- [ ] `[Felix-Escalation]` comments written to Vikunja after each alert
- [ ] All valid response outcomes recorded as comments
- [ ] Comments are append-only

### Response Handling
- [ ] Done, snooze, dismiss, reschedule, and acknowledge all handled correctly
- [ ] "All snooze Nd" applies to full task list
- [ ] Ambiguous responses prompt one clarifying question

### Infrastructure
- [ ] Escalation cron job running daily after habit check-in
- [ ] Manual trigger works
- [ ] Escalation skill deployed to office2
- [ ] Ops runbook complete
- [ ] Agent registered in AGENT-REGISTRY.md at Assisted (Level 1)
- [ ] Architecture docs updated

---

## Architecture Principles

### Insistence Is a Feature

The constitution names this explicitly. The escalation engine is not a nice-to-have
reminder system — it is the mechanism by which Felix holds Kent accountable to
declared commitments. The design must err toward being present and direct rather
than passive and polite. A task that has been overdue for five days and has not
been addressed warrants a Level 2 message that says so plainly.

### Narrow Scope: Due Dates, Not Commitments

`felix-admin-escalation` escalates tasks based on due date and priority. It does
not assess whether those tasks serve declared goals, whether Kent's portfolio of
tasks is overloaded, or whether priorities need to be renegotiated. That reasoning
belongs to the Commitment Manager (F020). This agent's scope is narrow by design —
it is the detection and delivery layer, not the judgment layer.

### Comment-as-State Is the Pattern

The habit agent's comment model (`[Felix] YYYY-MM-DD | state | note`) established
the pattern: structured comments on Vikunja tasks are the machine-readable state
store. The escalation engine follows this pattern with the `[Felix-Escalation]`
prefix. Future agents read these comments; they do not need a separate database or
external state store. This keeps the architecture simple and Vikunja as the single
source of truth for task state.

### Silence Is the Right Default

When no tasks qualify for escalation, the agent runs silently — no message, no
"nothing to report" confirmation. Routine silence trains Kent to notice when a
message does arrive, making alerts meaningful rather than background noise.

---

## Constitutional Compliance

✅ **Insistence is a feature** (Design Principle 2): This feature exists to
implement this principle operationally. The escalation engine is the mechanism.

✅ **Kent has final say — always** (Design Principle 3): The agent detects and
alerts; it does not autonomously reschedule, reprioritize, or delete tasks.
Every action requires Kent's explicit response.

✅ **Narrow scope** (Directive 1): `felix-admin-escalation` escalates overdue
and at-risk tasks. It does not touch habits, goals, briefings, or calendar.

✅ **Never fail silently** (Directive 4): If Vikunja is unavailable, if a
comment write fails, or if WhatsApp delivery fails — the failure is logged.
The agent does not proceed as if delivery succeeded.

✅ **Earned autonomy** (Directive 2): Starts at Assisted (Level 1). All alert
sends are actions, but they are informational pushes — not mutations to task state.
Task mutations (mark done, reschedule) only happen in response to Kent's explicit
reply. Promotion to Observed requires demonstrated reliable behavior.

✅ **Privacy is absolute**: `02-Growth/_private/` is never read or referenced.
Private-context tasks appear as task names only if they surface in Vikunja — the
escalation agent treats them identically to any other task.

---

## Risk Considerations

**Risk: Alert fatigue from too many escalations**
- If the priority filter is too permissive or Kent has accumulated many overdue
  tasks, the first few runs could generate long lists.
- Mitigation: The 7-task cap (FR-2) limits message length. The priority filter
  (Medium and above) reduces volume. After the first run, snoozed and dismissed
  tasks reduce the active escalation set naturally.

**Risk: Level 2 tone perceived as aggressive on first deployment**
- Kent may not have experienced Felix "insisting" before. The first Level 2
  message may feel jarring.
- Mitigation: The spec is explicit that insistence is a feature — this is
  intentional behavior, not a bug. The ops runbook should note that the
  escalation threshold and message tone are configurable in the skill.

**Risk: Comment-as-state accumulates over time, slowing comment queries**
- Tasks with long escalation histories will have many comments.
- Mitigation: The agent only needs to read the most recent `[Felix-Escalation]`
  comment to determine current state. Query cost is bounded. This is a known
  acceptable trade-off of the pattern.

**Risk: Response handling misidentifies task numbers after message truncation**
- If the 7-task cap truncates the list, task numbers in the response may
  not match what Kent expects if they reference a task beyond the cap.
- Mitigation: The agent uses the message-as-sent to parse responses —
  if the list was capped at 7, only numbers 1-7 are valid responses.
  Out-of-range numbers prompt a clarifying question.

---

## Notes for Implementation

**Pattern Discovery (Planning Phase):**
- Study `felix-admin-habits` AGENTS.md — this is the closest existing pattern
  for a cron agent that queries Vikunja and writes structured comments
- Study the habits agent's comment format — the `[Felix-Escalation]` format
  follows the same conventions
- Study the vikunja-api skill's comment write and task update endpoints —
  both are needed for FR-4 and FR-5

**Key Patterns to Copy:**
- Habits agent comment-write pattern → escalation comment-write (FR-4)
- Habits agent WhatsApp delivery pattern → escalation alert delivery (FR-2, FR-3)
- Habits agent cron configuration → escalation cron configuration (FR-6)

**Focus Areas:**
- The escalation level determination logic (reading comment history → deciding
  level) is the most important correctness requirement — get this right before
  worrying about message formatting
- The response parsing (FR-5) must be robust to natural language variation —
  study how the habits agent handles fuzzy responses via WhatsApp

---

**END OF SPECIFICATION**
