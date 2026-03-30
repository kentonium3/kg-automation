---
title: "F006: Goal and Outcome Structure"
doc_type: func-spec
status: draft
feature: F006
---

# F006: Goal and Outcome Structure

**Version**: 1.0
**Priority**: HIGH
**Type**: Configuration + Skill

---

## Executive Summary

The Felix system has a task store (Vikunja), an orchestration engine
(OpenClaw), a WhatsApp channel, and voice transcription — but no concept
of goals. Without declared goals, task management is just a list with no
anchor. This feature creates the goal and outcome structure that all
subsequent features reason against.

Current gaps:
- ❌ No place in the system to declare outcomes with dates and evidence
- ❌ No goal declaration format understood by the system
- ❌ No ability to capture a goal declaration via WhatsApp voice note
- ❌ No view showing all active goals with their target dates

This spec establishes the goal declaration format, extends Vikunja to
hold goal declarations, creates an Obsidian constitution entry for goals,
and wires WhatsApp voice capture to structured goal storage.

---

## Problem Statement

**Current State:**
```
Kent
└── ✅ WhatsApp channel to OpenClaw (F004)
└── ✅ Voice transcription available (F003)
└── ❌ No way to declare a goal the system understands
└── ❌ No structure for goals in Vikunja

Vikunja
└── ✅ Projects: Everyday, Personal Growth, Health, Intentional, Metal Casework
└── ✅ Labels: personal, intentional
└── ✅ Filters: Today, Upcoming, Overdue
└── ❌ No goal project or structure
└── ❌ No goal view

Obsidian (01-Constitution/)
└── ✅ Goals-MOC.md — reset to clean slate (2026-03-29)
│   Legacy pre-Felix content backed up to Goals-MOC-pre-Felix-backup-2026-03-29.md
└── ❌ No declared goals in standard format
└── ❌ No goal declaration template
```

**Target State:**
```
Kent
└── ✅ Can declare a goal by speaking into WhatsApp
└── ✅ Goal is transcribed, structured, and stored automatically
└── ✅ Can see all active goals with target dates in one Vikunja view

Vikunja
└── ✅ Goals project with one task per declared goal
└── ✅ Each goal task carries: outcome statement, target date, evidence criteria
└── ✅ Saved filter: Goals — active declarations sorted by target date

Obsidian (01-Constitution/)
└── ✅ Goals-MOC.md contains all active goal declarations in standard format
└── ✅ Goal declaration template defined and documented
```

---

## Goal Declaration Format

Every goal declaration must follow this exact structure:

```
On [specific date], I have [present-tense outcome statement]
as evidenced by [observable, concrete proof].
```

**Example:**
> On June 30th, 2026, I have established an income of $5,000/month
> through Intentional consulting as evidenced by deposits totaling
> $5,000 or more in my Intentional LLC business checking account.

**Rules for a valid declaration:**
- **Date is specific** — a concrete calendar date, not a range or quarter
- **Outcome is present-tense** — written as if already achieved ("I have"),
  not "I will" or "I want to"
- **Evidence is observable** — something that can be verified without
  interpretation (bank deposits, a completed document, a signed contract,
  a measurable metric)
- **One outcome per declaration** — compound goals must be split

This format is intentional. Present-tense outcome declarations create a
fundamentally different cognitive relationship with goals than future-tense
intentions. The system stores and surfaces them in this format consistently.

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **What Vikunja currently has — F001 artifacts**
   - `docs/handbooks/vikunja-ops.md` — current project structure, labels, and
     saved filters established in F001
   - `docs/design/architecture/data/service-inventory.json` — current Vikunja
     version and access details
   - Study the existing project hierarchy and label taxonomy before adding
     to it — don't duplicate or conflict with what F001 established

2. **What the second brain looks like today**
   - Understand the current state of `01-Constitution/Goals-MOC.md` in the
     Obsidian vault on office2
   - Understand the vault's folder structure (00–07) established by the
     second brain design
   - Note: the vault syncs between Mac, iPhone, and office2 via Obsidian Sync

3. **OpenClaw capabilities for goal capture**
   - `docs/handbooks/openclaw-ops.md` — how OpenClaw skills work, how WhatsApp
     messages are processed, how the transcribe-api skill is invoked
   - F003 func-spec and implementation artifacts — the whisper skill pattern
     is the model for processing voice input in OpenClaw
   - Understand how an inbound WhatsApp voice note flows through OpenClaw today

4. **Research documents from F005**
   - `docs/research/005-system-architecture-development/data-architecture.md`
     — canonical data model: what lives in Vikunja vs second brain vs OpenClaw
   - `docs/research/005-system-architecture-development/user-story-catalog.md`
     — stories B-G01, B-G02, B-G04 define the requirements this spec implements

---

## Functional Requirements

### FR-1: Goal Declaration Format and Template

**What it must do:**
- Define and document the canonical goal declaration format (as specified in
  this spec: "On [date], I have [outcome] as evidenced by [proof]")
- Create a goal declaration template in Obsidian `01-Constitution/` that Kent
  can use as a reference and starting point
- The template must make it easy to write valid declarations and hard to write
  vague or invalid ones

**Business rules:**
- The format is fixed — not a preference. Every goal in the system uses it.
- The template is the authoritative format reference for both Kent and future agents

**Success criteria:**
- [ ] Goal declaration format documented in Obsidian `01-Constitution/`
- [ ] Template makes the three required elements (date, outcome, evidence) explicit
- [ ] At least one example declaration included to illustrate the format

---

### FR-2: Vikunja Goal Structure

**What it must do:**
- Extend the Vikunja project structure to hold goal declarations as tasks
- Each goal declaration must be a task that carries: the full outcome statement,
  the target date as the task due date, the evidence criteria, and the identity
  label (personal, intentional, or metalcasework)
- A saved filter must show all active (incomplete) goal declarations sorted by
  target date

**Business rules:**
- Goals are not the same as tasks — they are the anchor against which tasks are
  evaluated. The Vikunja structure must make this distinction clear
- A goal declaration is active until its target date is reached or it is
  explicitly closed
- Identity label is required on every goal (personal, intentional, or
  metalcasework) — goals without an identity label are invalid

**Pattern reference:** Study the existing project structure and saved filter
patterns established in F001 (`docs/handbooks/vikunja-ops.md`) — extend
consistently, don't duplicate

**Success criteria:**
- [ ] Vikunja has a dedicated location for goal declarations distinct from
  regular tasks
- [ ] Each goal declaration carries: outcome statement, target date, evidence
  criteria, identity label
- [ ] A saved filter shows all active goal declarations sorted by target date
- [ ] Kent can view active goals on the Vikunja web UI and on mobile

---

### FR-3: Obsidian Goals-MOC Integration

**What it must do:**
- `01-Constitution/Goals-MOC.md` must become the human-readable canonical
  reference for all active goal declarations
- When a new goal is declared, it must appear in Goals-MOC.md in the standard
  format
- Goals-MOC.md must be readable standalone — someone reading it should have
  a complete picture of Kent's active declared outcomes

**Business rules:**
- Goals-MOC.md is the agent context ceiling for goal-related reasoning — future
  agents (from F008 onward) will read this file to understand Kent's priorities
- Goals-MOC.md must never contain vague intentions — only properly formatted
  declarations

**Success criteria:**
- [ ] Goals-MOC.md contains at least one real goal declaration in the standard
  format by feature completion
- [ ] Goals-MOC.md structure is clear and extensible as goals are added
- [ ] Goals-MOC.md is the single source of truth for human-readable goal context

---

### FR-4: WhatsApp Voice Capture to Goal Declaration

**What it must do:**
- Kent must be able to speak a goal declaration into WhatsApp as a voice note
  and have it transcribed, structured into the standard format, and stored in
  both Vikunja and Goals-MOC.md
- The capture flow must handle the case where the spoken declaration is not
  immediately valid — the system must ask Kent a clarifying question to
  complete any missing element (date, evidence) rather than storing an
  incomplete declaration
- After successful capture, the system must confirm what was stored back to
  Kent via WhatsApp so he can verify accuracy

**Business rules:**
- A voice note that cannot be parsed as a goal declaration (wrong intent,
  too vague) must not be silently discarded — Kent must be told what happened
- The system must not invent evidence criteria or dates — if they are absent
  from the spoken input, it must ask
- Confirmation message must include the structured declaration exactly as stored

**Pattern reference:** Study how the F003 Whisper skill receives and processes
voice notes from WhatsApp — the transcription path is already established and
this feature extends it for goal-specific processing

**Success criteria:**
- [ ] Kent can send a voice note via WhatsApp saying a goal declaration and
  have it stored correctly
- [ ] System asks for missing elements if date or evidence criteria are absent
- [ ] Confirmation of stored goal sent to Kent via WhatsApp
- [ ] Stored goal appears in both Vikunja and Goals-MOC.md
- [ ] Invalid or unclear voice notes surface a helpful error, not silence

---

### FR-5: Goal Evaluation Prompt

**What it must do:**
- When Kent types or speaks a new commitment (a task, an appointment, a "yes"
  to something), the system must be able to surface his active goal declarations
  as context so he can evaluate whether the new commitment serves his goals
- This capability is intentionally lightweight in F006 — it is the prompt
  pattern, not a full negotiation engine (that is F010)

**Business rules:**
- The system does not block or prevent new commitments — it surfaces context
- The goal evaluation prompt is a question, not a gate: "Before I add this,
  here are your active goals — does this serve them?"
- This is the seed of B-G03 and B-G06 — the full negotiation capability builds
  on top of this in later features

**Success criteria:**
- [ ] When Kent adds a task via WhatsApp, the system can optionally surface
  active goals as context
- [ ] The prompt is conversational, not bureaucratic

---

## Architecture Documentation Updates

F006 makes no changes to deployed services, ports, or credentials. The
changes are entirely in Vikunja's data structure and Obsidian content.

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Update Vikunja entry to note goals project structure added by F006 |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Note goal structure under Vikunja deployment details |

### No Changes Required

- `network-topology.json` — no new ports or services
- `credential-manifest.json` — no new credentials
- `hardware-inventory.json` — no hardware changes
- `data-flows.json` / `data-flows.md` — data flows expand in later features

**Success criteria:**
- [ ] `service-inventory.json` updated with `updated_by: "F006"`

---

## Out of Scope

- ❌ Vikunja API skill — F007 (goals are created manually or via this
  feature's WhatsApp skill; programmatic CRUD wrapper comes next)
- ❌ Daily habit tracking or recurring reminders — F008
- ❌ Escalation or persistent follow-up on goals — F010
- ❌ Daily briefing that includes goals — F012
- ❌ Calendar time-blocking for goal work — F014
- ❌ Goal progress measurement or trend analysis — F017
- ❌ Goal Context Loader (reading constitution for agent context) — F024
- ❌ Any personal transformation content — `02-Growth/_private/` is never
  accessed; the goal format itself is the boundary
- ❌ Inbox-to-goal routing — F015 (when the inbox processor migrates to office2,
  it should recognize goal declarations in inbox notes and route them the same
  way this feature's WhatsApp capture flow does; that is F015 scope, not F006)

---

## Success Criteria

**Complete when:**

### Goal Format
- [ ] Standard declaration format defined and documented in Obsidian
- [ ] Template makes it easy to write valid declarations
- [ ] Format is consistent with the "On [date], I have [outcome] as evidenced
  by [proof]" structure specified in this document

### Vikunja Structure
- [ ] Dedicated goal structure exists in Vikunja, distinct from regular tasks
- [ ] Goals carry: outcome statement, target date, evidence criteria, identity label
- [ ] Active goals filter exists and shows goals sorted by target date
- [ ] Visible on Vikunja web UI and mobile (via Tailscale)

### Obsidian
- [ ] Goals-MOC.md contains at least one real declared goal in standard format
- [ ] Structure is clean, extensible, and readable standalone

### WhatsApp Capture
- [ ] Voice note goal capture works end-to-end
- [ ] Confirmation sent to Kent after successful capture
- [ ] Incomplete declarations handled with clarifying questions, not silence
- [ ] Goal appears in both Vikunja and Goals-MOC.md after capture

### Quality
- [ ] Ops runbook at `docs/handbooks/goals-ops.md` documenting the format,
  how to add goals manually, how to close/retire a goal
- [ ] Architecture docs updated per above

---

## Architecture Principles

### Goals Are Not Tasks

Goals and tasks are distinct entities with different lifecycles. A goal is an
outcome declaration with a target date — it persists until achieved or retired.
Tasks are the actions taken to advance toward goals. The Vikunja structure must
reflect this distinction clearly. Future features will reason against the
distinction (e.g., escalation behaves differently for a task that's overdue vs.
a goal that's approaching its target date).

### The Format Is the Contract

The "On [date], I have [outcome] as evidenced by [proof]" format is not a
preference or a guideline — it is the contract between Kent and the system.
Future agents will parse, quote, and reason against declarations in this exact
format. Vague declarations ("I want to be healthier", "grow my business") are
not goal declarations in this system. The implementation must enforce the format
rather than accept approximations.

### Second Brain Is the Human Layer, Vikunja Is the Machine Layer

Goals-MOC.md is the human-readable, context-rich record that Kent and agents
read for understanding. Vikunja is the structured, queryable record that drives
automation. Both must stay in sync. When in conflict, Vikunja is the source of
truth for state (active/closed/target date). Goals-MOC.md is the source of
truth for narrative context.

---

## Constitutional Compliance

✅ **Privacy is absolute**: Goal declarations are personal and business — but
they are intentionally shared with the system. The privacy boundary is
`02-Growth/_private/`, which this feature does not touch. Goals that arise
from private work may be captured in the standard format without referencing
their origin context.

✅ **Agents start at Human In The Middle**: The WhatsApp capture skill
proposes a structured declaration and confirms with Kent before storing. Kent
approves the stored version. The system does not write to Goals-MOC.md without
Kent's confirmation.

✅ **No credentials in code**: No new credentials introduced in this feature.

✅ **Safety parameters**: If the system cannot parse a voice note as a valid
goal declaration, it surfaces the issue to Kent rather than silently
storing an invalid declaration or discarding the input.

✅ **Narrow scope**: This feature establishes goal structure. It does not
attempt to implement escalation, briefings, habit tracking, or calendar
integration — those are later features that build on this foundation.

---

## Risk Considerations

**Risk: Goal declarations become vague over time**
- If the format is not enforced, Kent may drift toward storing intentions
  ("I want to...") rather than declarations ("On [date], I have..."). The
  system then loses its anchor.
- Mitigation: The WhatsApp capture skill must validate the three required
  elements before storing. Manual entry in Obsidian or Vikunja bypasses
  this check — the ops runbook should make the format rules clear.

**Risk: Goals-MOC.md and Vikunja diverge**
- If a goal is added to one but not the other, the system has inconsistent
  state. Future agents reading Goals-MOC.md would have incomplete context.
- Mitigation: The WhatsApp capture flow must write to both atomically. For
  manually added goals, the ops runbook must document the two-step process.
  A sync check capability is a candidate for a later feature.

**Risk: Too many active declarations become noise**
- If Kent declares many goals without ever retiring them, the goals view
  loses signal.
- Mitigation: The feature should make retiring a completed or abandoned goal
  as easy as declaring one. The ops runbook must cover goal lifecycle.

---

## Notes for Implementation

**Pattern discovery (planning phase):**
- Study the Whisper skill (F003) as the model for voice input processing in
  OpenClaw — the goal capture skill follows the same inbound voice note pattern
  but adds a parsing and validation step before storage
- Study the F001 Vikunja setup script and ops runbook to understand the existing
  project and filter structure before extending it
- Read the current state of `01-Constitution/Goals-MOC.md` in the vault on
  office2 before writing to it — understand what's already there

**Key behaviors to validate during planning:**
- Understand how OpenClaw's WhatsApp channel handles a voice note today
  (audio arrives, transcription is available) — the goal capture skill builds
  on top of this
- Understand how the Vikunja API can be used to create a task with a due date,
  description, and label — this is needed even before F007's full API skill,
  since F006 needs to write at least one structured goal record

**Ops runbook scope:**
- The runbook at `docs/handbooks/goals-ops.md` must cover: the goal declaration
  format, how to add a goal manually (Vikunja + Obsidian), how to close a goal
  when achieved, how to retire an abandoned goal, and what a valid vs invalid
  declaration looks like

---

**END OF SPECIFICATION**
