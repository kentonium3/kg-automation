---
title: "F013: Vikunja Task Intelligence Agent"
doc_type: func-spec
status: draft
feature: F013
---

# F013: Vikunja Task Intelligence Agent

**Version**: 1.0
**Priority**: HIGH
**Type**: User Feature + Infrastructure

---

## Executive Summary

Tasks are flowing into Vikunja from the inbox processor but they arrive
flat — a title, an identity label, and a source reference. No due dates,
no priority, no project placement beyond Inbox, no relationships to goals
or other tasks, no repeating intervals. This makes Vikunja a task dump
rather than a task management system, and makes the escalation engine
(F014) impossible to implement meaningfully — it has nothing structured
to escalate.

This feature introduces a dedicated task intelligence agent that turns
raw task descriptions into properly structured Vikunja entries. It also
retroactively enriches the flat tasks already in Vikunja, and picks up
any new task created directly without proper attributes.

Current gaps:
- ❌ All inbox-derived tasks land flat in the Inbox project with no dates
  or relationships
- ❌ Existing flat tasks in Vikunja have no due dates, priority, or
  project placement — escalation engine has nothing to work with
- ❌ No structured reasoning about task scope, hierarchy, timing, or
  relationships before a task is created
- ❌ Directly-created tasks without full attributes have no enrichment path

This spec delivers a specialist agent that receives raw task descriptions,
reasons through the full set of required attributes, resolves ambiguity via
WhatsApp conversation, and produces properly structured Vikunja tasks.

---

## Problem Statement

**Current State:**
```
felix-admin-capture (F008)
└── Classifies inbox content as task → creates flat Vikunja task
    ├── Title ✅
    ├── Identity label ✅
    ├── Source reference in description ✅
    ├── Due date ❌
    ├── Priority ❌
    ├── Project placement ❌ (lands in Inbox)
    ├── Goal relationship ❌
    ├── Task relationships ❌
    └── Repeating interval ❌

Vikunja Inbox project
└── Growing pile of flat, undated tasks
└── Escalation engine (F014) cannot function — no dates to escalate on
└── Commitment Manager (future) cannot assess — no structure to reason against
```

**Target State:**
```
felix-admin-capture (F008)
└── Classifies content as task → hands raw task to felix-admin-tasker
    └── Raw task description + source context passed as input

felix-admin-tasker (F013) — new specialist agent
└── Receives raw task description
└── Reasons through required attributes at high-certainty level
└── Initiates WhatsApp conversation for uncertain attributes
└── Produces fully structured Vikunja task:
    ├── Title ✅
    ├── Identity label ✅
    ├── Project (correct project, not just Inbox) ✅
    ├── Due date (inferred or confirmed) ✅
    ├── Start date (if needed) ✅
    ├── Priority ✅
    ├── Goal relationship (if applicable) ✅
    ├── Task relationships (blocking/blocked/subtask) ✅
    └── Repeating interval (if applicable) ✅

Vikunja (retroactive enrichment)
└── Existing flat tasks in Inbox enriched by felix-admin-tasker
└── New tasks without full attributes detected and enriched
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **Vikunja's full capabilities**
   - `docs/handbooks/vikunja-ops.md` — current project structure,
     labels, filters
   - `scripts/openclaw/skills/vikunja-api/SKILL.md` — the full API
     skill including task relationships, all updatable fields, repeat
     intervals, priority model, and the pseudo-project filter IDs
   - Research Vikunja's task relation API specifically — the skill
     covers CRUD but the planning phase must confirm the exact API
     calls for creating subtask/parent/blocking/precedes relationships
   - Research Vikunja's repeat_after field — understand how repeating
     intervals are stored (duration in seconds? enum? string?)

2. **Current inbox processor task bridge**
   - `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` — the
     task bridge section describes exactly what gets passed to Vikunja
     today. F013 needs to either modify this handoff or intercept it.
   - Planning phase must determine: does felix-admin-capture call
     felix-admin-tasker directly (agent-to-agent handoff), or does
     felix-admin-tasker poll for flat tasks and enrich them?

3. **How OpenClaw handles agent-to-agent communication**
   - Research the OpenClaw mechanism for one agent invoking another
     agent as a specialist. This is the "agent handoff" pattern
     referenced in the design discussion. If OpenClaw supports it,
     this is the preferred approach.
   - If agent-to-agent invocation is not supported, the alternative
     is a polling pattern: felix-admin-tasker polls the Inbox project
     for tasks matching an "unenriched" signature and processes them

4. **Context for the intelligence layer**
   - `docs/constitution/FELIX-CONSTITUTION.md` — goal declarations
     and project structure the agent reasons against
   - Active goal declarations in Vikunja Goals project — the agent
     must be aware of these to identify goal relationships
   - Existing Vikunja projects — the agent must know what projects
     exist before placing tasks in them

---

## Primary Interaction Channel

All clarification conversations and confirmation prompts are delivered via
the **primary interaction channel**. WhatsApp is the initial implementation.
The architecture must not hardcode WhatsApp — it must be abstracted so
additional channels (Vikunja comments, Obsidian inbox, email) can be
supported later without a spec rewrite.

The primary interaction channel is configured per agent deployment. Any
reference below to "WhatsApp" means "the configured primary interaction
channel for this agent."

---

## The Task Intelligence Model

A task requires answers to the following questions before it is fully
structured. The agent must answer all of them — either by inference with
high confidence or by asking Kent via WhatsApp.

### Required attributes

| Attribute | Question | Can infer? | Fallback |
|---|---|---|---|
| Title | What is the task? | Yes — from raw description | Clarify if ambiguous |
| Identity label | Which identity? (personal/intentional/metalcasework) | Usually yes | Ask if ambiguous |
| Project | Where does this belong? | Often yes | Ask |
| Due date | When must this be done? | Sometimes (explicit dates in text) | Ask |
| Priority | How important/urgent? | Sometimes (signal words) | Default to medium |

### Optional but valuable attributes

| Attribute | Question | When to ask |
|---|---|---|
| Start date | When should work begin? | Only if task has lead time or dependencies |
| Repeating interval | Does this recur? | Only if task sounds recurring |
| Goal relationship | Does this serve a declared goal? | Check against active goals; ask if unclear |
| Subtask/parent | Is this part of a larger task? | Ask if task sounds like a component |
| Blocking/blocked | Does anything depend on this? | Ask if task has clear dependencies |

### Confidence threshold

The agent applies a confidence threshold to each attribute:

- **High confidence (≥90%)**: infer and proceed — include in proposed
  structure for single-step confirmation
- **Low confidence (<90%)**: initiate a WhatsApp clarification for that
  specific attribute before creating the task

This keeps the WhatsApp conversation focused — Kent is only asked about
attributes that are genuinely uncertain, not every attribute for every task.

---

## Functional Requirements

### FR-1: Task Enrichment via Primary Interaction Channel Conversation

**What it must do:**
- Receive a raw task description (from inbox processor handoff or
  retroactive enrichment) and reason through required attributes
- For high-confidence attributes: include in a proposed task summary
  sent to Kent for a single confirmation step
- For uncertain attributes: ask specific clarifying questions before
  building the proposed structure
- Present the complete proposed task structure to Kent for approval
  before writing to Vikunja
- On approval: create the fully structured task in Vikunja
- On rejection or modification: update the proposal and re-confirm

**Example interaction flow (via primary interaction channel):**
```
Felix: New task from your inbox — "Schedule car for oil change"
  Proposed structure:
  • Project: Personal
  • Due: Next week Friday (Apr 11)
  • Priority: Medium
  • Label: personal
  One question: Is this a repeating task (every 3 months)?

Kent: Yes, every 3 months

Felix: Got it. Creating:
  "Schedule car for oil change"
  Project: Personal | Due: Apr 11 | Repeats: every 3 months
  Priority: medium | Label: personal
  ✓ Done — Vikunja task #247 created
```

**Business rules:**
- The agent NEVER creates a task in Vikunja until Kent has confirmed
  the proposed structure — this is Assisted (Level 1) behavior
- Confirmation is delivered and received via the primary interaction
  channel
- Confirmation can be a simple "yes" / "looks good" / "do it"
- Kent can modify any attribute in the confirmation reply
- The agent must handle partial confirmations ("yes but make it
  high priority") without requiring a full re-proposal
- If Kent says "just add it" or "add it as-is" without detail, the
  agent applies sensible defaults and proceeds

**Success criteria:**
- [ ] Raw task received and attributes reasoned through
- [ ] High-confidence attributes proposed without questions
- [ ] Uncertain attributes clarified via WhatsApp before proposing
- [ ] Proposed structure presented for confirmation
- [ ] Task created in Vikunja only after confirmation
- [ ] Confirmation modifications handled gracefully

---

### FR-2: Project Placement Intelligence

**What it must do:**
- Place tasks in the correct Vikunja project based on content and
  identity, not default everything to Inbox
- Map task content to the appropriate project:
  - Intentional LLC / consulting work → Intentional LLC project
  - Business acquisition / CT course → Business Acquisition project
  - Health, fitness, PT, medical → Health & Conditioning project
  - Personal growth, habits, mindset → Personal Growth project
  - Metal casework research → Metal Casework project
  - Everything else → Inbox for manual triage
- Distinguish between the Vikunja Inbox (default for unassigned tasks)
  and the conceptual "needs triage" state — tasks should not stay in
  Inbox if their project is clear

**Business rules:**
- Project placement follows identity label: intentional tasks go in
  Intentional LLC, personal tasks go in the appropriate personal project
- When a task clearly fits a project: infer and include in proposal
- When project is ambiguous: ask before proposing
- Tasks spanning multiple projects: place in primary project, add a
  comment referencing the secondary

**Success criteria:**
- [ ] Inbox-derived tasks placed in correct project, not left in Inbox
- [ ] Project placement included in proposed structure for confirmation
- [ ] Ambiguous project placement triggers a clarifying question

---

### FR-3: Goal Relationship Detection

**What it must do:**
- Before structuring a task, check active goal declarations in the
  Vikunja Goals project
- If the task plausibly serves a declared goal, propose linking them
  as a subtask or related task relationship
- Surface the proposed goal relationship in the confirmation message
  so Kent can confirm or decline

**Business rules:**
- Do not create goal relationships without Kent's confirmation
- A task can serve a goal without being a formal subtask — the related
  relation type is sufficient for most cases
- If no goal relationship is apparent, do not ask — omit silently
- Goal relationships become data the Commitment Manager (future) and
  escalation engine (F014) use for context

**Success criteria:**
- [ ] Active goals checked before structuring any task
- [ ] Plausible goal relationship surfaces in proposal
- [ ] Goal relationship only created on Kent's confirmation
- [ ] No false-positive goal relationships proposed for unrelated tasks

---

### FR-4: Retroactive Enrichment of Existing Flat Tasks

**What it must do:**
- On F013 deployment, identify all existing flat tasks in Vikunja that
  lack the full attribute set (no due date, no project placement beyond
  Inbox, or missing identity label)
- Process each flat task through the same enrichment flow as new tasks
- Deliver enrichment proposals via the primary interaction channel,
  batched to avoid flooding (no more than 3-5 tasks per batch, with
  a pause between batches)

**Business rules:**
- Retroactive enrichment is opt-in per batch — Kent can defer a batch
  with "later" or skip individual tasks with "skip"
- Skipped tasks are flagged in Vikunja with a comment so they can
  be found later
- Completed or archived tasks are not retroactively enriched
- The inbox processor's flat task bridge remains operational during
  retroactive enrichment — new tasks continue to flow

**Success criteria:**
- [ ] Existing flat Inbox tasks identified on deployment
- [ ] Enrichment proposals delivered in batches of 3-5 via WhatsApp
- [ ] Kent can defer or skip individual tasks
- [ ] Skipped tasks flagged with a Vikunja comment
- [ ] Retroactive enrichment does not block new task processing

---

### FR-5: Detection of Directly-Created Incomplete Tasks

**What it must do:**
- Poll the Vikunja Inbox project (and the native Vikunja default inbox
  for tasks without project assignment) periodically for tasks that
  lack required attributes
- When an incomplete task is found that was not created by the inbox
  processor, offer enrichment via the primary interaction channel

**What "incomplete" means:**
- No due date AND no explicit "no due date" confirmation
- No identity label
- Still in Inbox/default project after reasonable time (planning phase
  defines the threshold — e.g., tasks older than 2 hours with no attributes)

**Business rules:**
- The agent must distinguish between tasks it has already proposed
  enrichment for and genuinely new incomplete tasks — no duplicate proposals
- Tasks Kent created in Vikunja directly and left in Inbox intentionally
  should not be pestered repeatedly — after one declined enrichment
  offer the agent stops proposing for that task

**Success criteria:**
- [ ] Incomplete tasks detected in Vikunja Inbox
- [ ] Single enrichment offer per task — not repeated if declined
- [ ] Detection polling cadence configured (planning phase determines
  appropriate interval)

---

### FR-6: Inbox Processor Handoff Update

**What it must do:**
- Update the felix-admin-capture task bridge to hand raw task
  descriptions to felix-admin-tasker rather than creating flat tasks
  directly in Vikunja
- The handoff must pass: the raw task text, the source inbox note
  reference, the inferred identity label, and any date/context signals
  found in the inbox note

**Business rules:**
- The inbox processor's role ends at classification — "this content is
  a task" — and begins felix-admin-tasker's role
- If felix-admin-tasker is unavailable, felix-admin-capture falls back
  to creating a flat task in Inbox and logs the fallback
- The transition must not lose any tasks that arrive while F013 is
  being deployed — there must be no gap in task capture

**Success criteria:**
- [ ] felix-admin-capture passes raw tasks to felix-admin-tasker
- [ ] Fallback to flat task creation if felix-admin-tasker unavailable
- [ ] No tasks lost during the transition
- [ ] felix-admin-capture AGENTS.md updated with new handoff behavior

---

### FR-7: Vikunja Task Intelligence Skill

**What it must do:**
- Create a `task-intelligence` skill at
  `scripts/openclaw/skills/task-intelligence/SKILL.md` that encodes
  the task structuring model, confidence rules, attribute inference
  patterns, and the conversation flow
- This skill is what felix-admin-tasker reads to know how to structure
  tasks consistently
- The skill must reference the skill-authoring skill conventions (F012)

**What the skill encodes:**
- The required and optional attribute table from this spec
- Confidence threshold rules and when to ask vs. infer
- Project placement mapping (task content → project)
- Identity label inference rules
- Goal relationship check procedure
- The confirmation conversation pattern
- Error handling: what to do if Vikunja is unavailable during enrichment

**Success criteria:**
- [ ] Skill written and deployed to office2
- [ ] Skill is self-contained — an agent reading it can structure any
  task without additional guidance
- [ ] Skill updated in the same PR as any future changes to task
  structuring conventions

---

### FR-8: Operations Runbook

**What it must do:**
- Create `docs/handbooks/task-intelligence-ops.md` covering:
  - How felix-admin-tasker operates
  - How to trigger retroactive enrichment manually
  - How to check enrichment status
  - How to skip or defer enrichment for a task
  - Troubleshooting: task not being enriched, duplicate proposals,
    WhatsApp conversation timing out

**Success criteria:**
- [ ] Runbook exists and covers all topics
- [ ] Agent registered in AGENT-REGISTRY.md at Assisted (Level 1)

---

## Architecture Documentation Updates

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Add felix-admin-tasker agent; add polling cron for incomplete task detection; set updated_by F013 |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Add felix-admin-tasker under OpenClaw agents |
| `docs/constitution/AGENT-REGISTRY.md` | Add felix-admin-tasker at Assisted (Level 1) |

---

## Out of Scope

- ❌ Calendar time-blocking for tasks — F018
- ❌ Escalation of tasks once structured — F014
- ❌ The Commitment Manager (full cross-goal assessment) — future feature,
  see `FUTURE_commitment_manager_agent.md`
- ❌ Vikunja UI improvements or saved filter changes — separate concern
- ❌ Task completion tracking or reporting — F014/F016
- ❌ Bulk import or migration tools beyond retroactive enrichment

---

## Success Criteria

**Complete when:**

### Core Enrichment
- [ ] Raw tasks receive full attribute enrichment via WhatsApp conversation
- [ ] High-confidence attributes proposed; uncertain ones clarified
- [ ] Tasks placed in correct project, not left in Inbox
- [ ] Goal relationships detected and proposed where applicable

### Retroactive
- [ ] Existing flat tasks identified and offered enrichment in batches
- [ ] Declined/skipped tasks flagged, not repeatedly proposed

### Direct Task Detection
- [ ] Incomplete directly-created tasks detected and offered enrichment

### Handoff
- [ ] felix-admin-capture updated to hand off to felix-admin-tasker
- [ ] Fallback to flat task if tasker unavailable

### Skills and Docs
- [ ] task-intelligence skill written and deployed
- [ ] Ops runbook complete
- [ ] Agent registered at Assisted (Level 1)
- [ ] Architecture docs updated

---

## Architecture Principles

### Classifier and Specialist Are Different Roles

The inbox processor's job is to recognize that something is a task. The
task intelligence agent's job is to structure that task properly. These
are genuinely different cognitive tasks requiring different context —
one needs broad knowledge of content types, the other needs deep
knowledge of Vikunja's capabilities and Kent's goal structure.
Separating them keeps both agents narrow in scope, which is a
constitution directive.

### Assisted (Level 1) Is the Right Mode for Task Creation

Every task that enters Vikunja as a result of felix-admin-tasker's
work has been confirmed by Kent before it was written. This is explicit
Assisted (Level 1) behavior. The confirmation step is not overhead — it
is the moment Kent commits to the task. An unconfirmed task is not a
commitment, it is a suggestion.

### Structured Tasks Are the Foundation of Everything Downstream

The escalation engine (F014), the daily briefing (F016), the Commitment
Manager (future), and calendar integration (F017/F018) all depend on
tasks having due dates, priority, and project placement. This feature is
not optional polish — it is load-bearing infrastructure for the rest of
Phase 1.

---

## Operating Mode Progression

felix-admin-tasker follows the standard F012 operating mode progression:

- **Assisted (Level 1)** — Initial mode. Agent does not create tasks
  without Kent's explicit confirmation via the primary interaction channel.
  Kent may run it manually after initial deployment or approve/deny when
  invoked by another agent.
- **Observed (Level 2)** — Agent creates tasks autonomously. Distilled
  reporting is generated so Kent has visibility into what actions were
  taken and when. This is the probationary period.
- **Autonomous (Level 3)** — Agent creates tasks independently. Only
  exceptions (errors, flagged items, security concerns) are surfaced.

Progression is not automatic. It requires demonstrated predictable
behavior and Kent's explicit decision. Mode regression is possible at any
time — for example, after a code change, the agent may be returned to
Assisted until confidence is re-established.

The spec does not prescribe when transitions happen. That is a governance
decision made from operational evidence.

---

## Constitutional Compliance

✅ **Assisted (Level 1)**: No task created in Vikunja until Kent confirms.

✅ **Narrow scope**: felix-admin-tasker structures tasks. It does not
process inbox notes, manage habits, or send briefings.

✅ **Never fail silently**: If Vikunja is unavailable, if a proposal
times out, or if enrichment fails — the failure is logged and reported.

✅ **No credentials in code**: Vikunja API token from credential store.

✅ **Observation Mode**: At Observed (Level 2), all task creation actions
are surfaced via distilled digest per F012 constitution directive.

---

## Risk Considerations

**Risk: WhatsApp conversation volume overwhelms Kent during retroactive enrichment**
- Flat tasks have accumulated — retroactive enrichment could generate
  a burst of WhatsApp conversations.
- Mitigation: FR-4 requires batching (3-5 tasks per batch) with pause
  between batches. Kent can defer entire batches with "later".

**Risk: Agent-to-agent handoff mechanism not supported by OpenClaw**
- If OpenClaw doesn't support invoking a specialist agent from within
  a running agent session, the handoff pattern needs an alternative.
- Mitigation: Planning phase researches OpenClaw agent-to-agent
  invocation as first discovery step. Polling pattern (FR-5) is the
  fallback if direct handoff is unsupported.

**Risk: Confidence threshold miscalibrated — too many or too few questions**
- If the threshold is too low, Kent gets asked about obvious attributes.
  If too high, tasks are created with wrong attributes silently.
- Mitigation: Start conservative (ask more than necessary). Tune based
  on feedback from first two weeks of operation. The confidence model
  is in the skill document (FR-7) — it can be updated without a spec.

**Risk: Retroactive enrichment interrupts existing task management habits**
- Kent may have already mentally organized the flat tasks in Inbox.
  Sudden enrichment proposals could be disorienting.
- Mitigation: FR-4 makes retroactive enrichment opt-in per batch.
  Kent can decline all retroactive enrichment and let the new forward-
  looking enrichment take effect from deployment onward.

---

## Notes for Implementation

**First discovery step — agent handoff mechanism:**
Research whether OpenClaw supports invoking a specialist agent from
within a running cron agent session. This is the critical architectural
question for FR-6. If supported, felix-admin-capture calls
felix-admin-tasker directly. If not, felix-admin-tasker polls.

**Vikunja task relation API:**
The vikunja-api skill covers CRUD but not task relations. The planning
phase must discover the exact API endpoint for creating task relations
(subtask, related, blocking, etc.) and add it to the vikunja-api skill
as part of F013 — or document it in the task-intelligence skill.

**Repeating task field:**
Research how Vikunja's `repeat_after` field works in v0.24.6.
This field is referenced in the API skill as updatable but its format
(duration in seconds? ISO duration string? integer + unit?) needs to
be confirmed before the task-intelligence skill specifies how to set it.

**Two-layer classification forward reference:**
The architecture note in F008 about SOUL.md handling broad intent
classification and skills handling specialist execution is the design
pattern this feature implements. Felix-admin-capture is the classifier;
felix-admin-tasker is the specialist. This pattern will repeat as more
specialist agents are added.

---

**END OF SPECIFICATION**
