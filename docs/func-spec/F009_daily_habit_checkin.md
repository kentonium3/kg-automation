---
title: "F010: Daily Habit Check-in and Commitment Tracking"
doc_type: func-spec
status: draft
feature: F010
---

# F010: Daily Habit Check-in and Commitment Tracking

**Version**: 1.0
**Priority**: HIGH
**Type**: User Feature

---

## Executive Summary

The infrastructure to track commitments now exists — Vikunja holds tasks
and goals, OpenClaw can read and write them, and WhatsApp is the channel.
F010 puts that infrastructure to daily use. A habit check-in arrives via
WhatsApp each morning listing Kent's recurring commitments. He marks each
complete, rescheduled, or "will not do" with a reply. Completion state is
stored in Vikunja. A weekly pattern report shows how he did this week vs.
last week. The accountability loop is closed.

Current gaps:
- ❌ No daily check-in for recurring commitments delivered via WhatsApp
- ❌ No way to mark a recurring commitment complete via WhatsApp
- ❌ No completion state tracked anywhere in the system
- ❌ No weekly pattern report showing trends over time
- ❌ No track record of keeping commitments to self

This spec delivers a daily habit check-in via WhatsApp, WhatsApp-based
completion marking, Vikunja-backed state storage, and a weekly pattern
report — the core of the personal accountability loop.

---

## Problem Statement

**Current State:**
```
Kent
└── ✅ WhatsApp channel to OpenClaw (F004)
└── ✅ Vikunja holds goals and tasks (F006, F007)
└── ✅ Inbox processing routes captures to Vikunja (F008)
└── ✅ Vault syncing to office2 (F009)
└── ❌ No daily habit check-in
└── ❌ No completion tracking for recurring commitments
└── ❌ No weekly pattern report

Vikunja
└── ✅ Goals project, identity labels, saved filters
└── ❌ No habit project or recurring commitment structure
└── ❌ No completion history queryable for reporting
```

**Target State:**
```
Kent (each morning via WhatsApp)
└── ✅ Receives daily check-in listing recurring commitments
└── ✅ Marks each complete / rescheduled / will-not-do by reply
└── ✅ Receives weekly pattern report Sunday evening

Vikunja
└── ✅ Habits project with one task per recurring commitment
└── ✅ Daily completion records stored as task comments or labels
└── ✅ Completion history queryable for weekly reporting

OpenClaw
└── ✅ felix-admin-habits agent — daily check-in delivery + completion recording
└── ✅ Weekly pattern report cron (Sunday evening)
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **What exists in Vikunja — post-F007 state**
   - `docs/runbooks/vikunja-ops.md` — current project structure, labels,
     filters. Understand what's already there before adding new structure.
   - `docs/design/architecture/data/service-inventory.json` — Vikunja URL,
     API token location
   - Study Vikunja's API capabilities for recurring tasks, comments, and
     label-based state management — the planning phase must determine the
     correct mechanism for storing daily completion state

2. **How F008 established the agent pattern**
   - `scripts/openclaw/agents/felix-admin-capture/` — the felix-admin-capture
     agent is the closest existing pattern. Study how it was configured
     (SOUL.md, AGENTS.md, TOOLS.md) before designing the habits agent.
   - `docs/runbooks/inbox-ops.md` — how cron jobs were configured for the
     capture agent; the habits agent follows the same pattern

3. **WhatsApp channel current state**
   - `docs/design/architecture/data/service-inventory.json` — dmPolicy is
     now `"disabled"`. Kent's own paired number still receives and sends
     messages normally. Unknown contacts are silently ignored.
   - `docs/runbooks/openclaw-ops.md` — how the WhatsApp channel delivers
     messages and processes replies

4. **User stories and research**
   - `docs/research/005-system-architecture-development/user-story-catalog.md`
     — B-H01 through B-H06, B-08, B-09 define the requirements this spec
     implements
   - `docs/research/005-system-architecture-development/data-architecture.md`
     — data model for habit state storage

---

## Habit Definition

A **habit** in this system is a recurring commitment — something Kent has
decided to do on a regular schedule that supports his goals and wellbeing.

**Examples from known context:**
- Morning meditation
- Exercise (3× weekly at Fitness Together Burlington)
- Physical therapy exercises
- Evening reading
- Learning blocks (deliberate skill development time)

**Properties of a habit:**
- Has a name and a frequency (daily, weekdays, specific days)
- Has an identity label (personal, intentional, metalcasework)
- Has a completion state for each occurrence: complete / rescheduled /
  will-not-do
- Completion state is recorded with a date for historical querying
- Does not have a single due date — it recurs

**Initial habit list**: The planning phase must ask Kent to provide his
current list of habits before configuring the Vikunja structure. Do not
invent or assume habits.

---

## Functional Requirements

### FR-1: Habit Structure in Vikunja

**What it must do:**
- Establish a dedicated Habits project in Vikunja to hold recurring
  commitments, separate from the Goals project and the general task Inbox
- Each habit is a task in the Habits project with: name, frequency, identity
  label, and notes field describing what counts as completion
- Completion state for each day is recorded in a way that supports weekly
  querying (planning phase determines the correct Vikunja mechanism —
  options include task comments, label-based state, or daily sub-tasks)

**Business rules:**
- Habits are not one-time tasks — they recur. The Vikunja structure must
  not treat each occurrence as a separate top-level task
- Every habit must carry an identity label (personal, intentional, or
  metalcasework)
- Completion recording must support at least 90 days of history for
  trend reporting

**Pattern reference:** Study the Goals project structure from F006 and
F007 — apply the same project-plus-label pattern consistently

**Success criteria:**
- [ ] Habits project exists in Vikunja, distinct from Goals and Inbox
- [ ] Each of Kent's recurring commitments is represented as a habit
- [ ] Each habit carries an identity label
- [ ] Daily completion state can be recorded and queried via Vikunja API

---

### FR-2: Daily Check-in Delivery

**What it must do:**
- Deliver a daily check-in message to Kent via WhatsApp listing all habits
  scheduled for that day
- Each habit in the message must be clearly labeled with a response option:
  complete, rescheduled, or "will not do"
- The check-in must include only habits scheduled for today — not habits on
  different days
- Delivery time is configurable — planning phase should determine the
  appropriate time given the existing 7 AM inbox processing cron

**Business rules:**
- The check-in must be concise — a wall of text will not be engaged with.
  One line per habit, clear response instructions.
- If a habit was already marked complete for today (via a previous
  interaction), it must not appear in the check-in again
- The check-in must be delivered even on days Kent hasn't opened the app —
  it is a push notification, not a pull

**Success criteria:**
- [ ] Check-in delivered via WhatsApp at configured time
- [ ] Only today's habits listed
- [ ] Already-completed habits excluded from the check-in
- [ ] Message format is concise and actionable

---

### FR-3: WhatsApp Completion Marking

**What it must do:**
- Kent must be able to reply to the check-in (or send a standalone message)
  to mark a habit as complete, rescheduled, or "will not do" for today
- The agent must recognize natural language responses — not require exact
  command strings
- After marking, the agent must confirm what was recorded via WhatsApp
- Completion state must be written to Vikunja via the F007 API skill

**Business rules:**
- **Complete**: The habit was done today. Record with today's date.
- **Rescheduled**: The habit will be done at a different time today or
  tomorrow. Record with a note. Does not count as a failure in tracking.
- **Will not do**: A conscious decision not to do the habit today. Record
  with today's date as a skipped occurrence. Counts in the pattern report.
- The agent must not accept ambiguous responses silently — if unclear,
  ask one clarifying question
- Marking must be idempotent — marking the same habit twice in one day
  updates rather than duplicates

**Success criteria:**
- [ ] Natural language marking recognized ("done", "skipped", "not today",
  "moved it to this afternoon", etc.)
- [ ] Confirmation sent to Kent after each marking
- [ ] State written to Vikunja correctly
- [ ] Ambiguous responses prompt a clarifying question
- [ ] Double-marking updates rather than duplicates

---

### FR-4: Weekly Pattern Report

**What it must do:**
- Deliver a weekly pattern report to Kent via WhatsApp on Sunday evening
- The report must show, for each habit: completion rate this week vs. the
  prior week
- The report must also show an overall completion rate across all habits
- The report must be concise — a trend indicator per habit, not a full log

**Business rules:**
- "This week" is Monday–Sunday of the current week
- "Last week" is the prior Monday–Sunday
- Completion rate = (complete + rescheduled) / (complete + rescheduled +
  will-not-do + no response) for scheduled days
- Rescheduled counts as a positive outcome (intent preserved)
- "Will not do" and no-response both count as non-completion
- Report delivered Sunday evening, time configurable

**Success criteria:**
- [ ] Weekly report delivered Sunday evening via WhatsApp
- [ ] Each habit shows this-week vs. last-week completion rate
- [ ] Overall completion rate included
- [ ] Report is concise — fits comfortably in a WhatsApp message

---

### FR-5: Track Record Visibility

**What it must do:**
- Kent must be able to ask "how am I doing on my habits?" or "show me my
  track record" via WhatsApp and receive a summary at any time
- The summary must cover at minimum the last 4 weeks for each habit

**Business rules:**
- This is an on-demand query, not a scheduled delivery
- The agent recognizes natural language queries about track record
- The response format should be the same as the weekly report for
  consistency

**Success criteria:**
- [ ] On-demand track record query recognized via WhatsApp
- [ ] Response covers at least 4 weeks of history
- [ ] Format consistent with weekly report

---

### FR-6: Adding and Removing Habits

**What it must do:**
- Kent must be able to add a new habit by describing it via WhatsApp
- Kent must be able to remove or pause a habit via WhatsApp
- Adding a habit creates a new entry in the Vikunja Habits project
- Removing a habit archives it (not deleted — history preserved)

**Business rules:**
- A new habit must specify at minimum: name and frequency
- Identity label defaults to personal if not specified
- Paused habits do not appear in check-ins but their history is preserved
- The agent confirms new habit details before creating — "I'll add daily
  meditation as a personal habit. Is that right?"

**Success criteria:**
- [ ] New habit added via WhatsApp appears in next day's check-in
- [ ] Habit removal/pause removes from check-in without deleting history
- [ ] Confirmation step before creating a new habit

---

### FR-7: Operations Runbook

**What it must do:**
- Create `docs/runbooks/habits-ops.md` covering:
  - How to view and manage habits in Vikunja
  - How to manually trigger a check-in or weekly report
  - How to add/remove habits outside of WhatsApp (direct Vikunja)
  - How to check completion history
  - Troubleshooting common issues

**Success criteria:**
- [ ] Runbook exists at `docs/runbooks/habits-ops.md`
- [ ] Passes doc validation (frontmatter compliant)

---

## Architecture Documentation Updates

F010 adds a new agent and cron jobs. No new services or credentials.

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Add felix-admin-habits agent entry; add habit check-in and weekly report cron jobs |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Add habits agent and crons under OpenClaw section |

### No Changes Required

- `network-topology.json` — no new ports
- `credential-manifest.json` — vikunja-api token already exists
- `hardware-inventory.json` — no hardware changes

**Success criteria:**
- [ ] `service-inventory.json` updated with `updated_by: "F010"`

---

## Out of Scope

- ❌ Calendar time-blocking for habit completion — F016
- ❌ Escalation for missed habits — F012
- ❌ Daily briefing that includes habit summary — F014
- ❌ Goal-habit linkage — future enhancement
- ❌ Habit streak tracking — deferred
- ❌ Oversubscription detection (B-H06) — deferred to F012 escalation design

---

## Success Criteria

**Complete when:**

### Habit Structure
- [ ] Habits project in Vikunja with Kent's recurring commitments
- [ ] Each habit has correct identity label and frequency

### Daily Check-in
- [ ] Check-in delivered at configured time each day via WhatsApp
- [ ] Only today's habits listed
- [ ] Marking via WhatsApp works for all three states

### Reporting
- [ ] Weekly pattern report delivered Sunday evening
- [ ] On-demand track record query works

### Habit Management
- [ ] New habits can be added via WhatsApp
- [ ] Habits can be paused/removed without losing history

### Documentation
- [ ] `docs/runbooks/habits-ops.md` complete and CI-passing
- [ ] Architecture docs updated

---

## Architecture Principles

### Habits Are Not Tasks

Tasks have a due date and are done once. Habits recur indefinitely. The
Vikunja structure must reflect this distinction. The planning phase must
determine whether Vikunja's native recurring task capability or a custom
pattern (e.g., a parent habit task with daily state stored in comments)
is the better fit. Do not shoehorn habits into the single-task model.

### Completion State Is the Data

The value of this feature is in the pattern over time, not any single
check-in. Completion state must be stored in a way that supports querying
across weeks. If Vikunja's native querying cannot support 4-week trend
analysis, the planning phase must determine an alternative storage
approach within the existing data architecture.

### Conciseness Is a Feature

The daily check-in and weekly report will only be used if they are easy
to engage with. A long, formatted message will be skipped. A two-line
check-in and a five-line report will be read. Design for the smallest
effective message, not the most complete one.

---

## Constitutional Compliance

✅ **Privacy is absolute**: Habits that arise from private transformation
work (`02-Growth/_private/`) appear as calendar/habit entries only —
never with references to their origin context (B-P01).

✅ **Narrow scope**: felix-admin-habits handles habit check-ins and
reporting only.

✅ **Never fail silently**: Ambiguous completion responses prompt a
clarifying question. Failed Vikunja writes surface an error.

✅ **No credentials in code**: Vikunja API token from credential store
via F007 skill.

✅ **Agents start at Gate 1**: All completion state changes confirmed
back to Kent before being recorded.

---

## Risk Considerations

**Risk: Vikunja's recurring task model doesn't fit habits well**
- Mitigation: Planning phase evaluates Vikunja's recurring task API
  before choosing an implementation approach.

**Risk: Check-in fatigue**
- Mitigation: Keep message concise (one line per habit). Delivery time
  is configurable.

**Risk: WhatsApp message ordering**
- Mitigation: Each completion marking processed independently.
  Idempotency requirement in FR-3 handles duplicates.

---

## Notes for Implementation

**Pattern discovery:**
- Study felix-admin-capture as the pattern for felix-admin-habits
- Research Vikunja's recurring task API
- Determine OpenClaw mechanism for proactive send AND reply processing

**Habit list:**
- Planning phase must ask Kent for his current list of habits before
  creating any Vikunja structure.

**Observation Mode:**
- Per F011 governance pattern, this agent starts in Observation Mode.
  A daily summary of what the habits agent did must be surfaced to Kent
  until he explicitly turns it off.

---

**END OF SPECIFICATION**
