---
title: "F008: Inbox Processing Migration to office2"
doc_type: func-spec
status: draft
feature: F008
---

# F008: Inbox Processing Migration to office2

**Version**: 1.0
**Priority**: HIGH
**Type**: Infrastructure + Migration

---

## Executive Summary

The Obsidian inbox is the primary second brain capture channel — voice notes
via Wispr Flow, typed quick notes, stream-of-consciousness thinking. Three
production-quality skills already process this inbox (inbox-processor,
kent-voice, vault-writer), but they run in a Claude conversation session on
the Mac. When the Mac is asleep, notes pile up unprocessed. This feature
migrates that processing to an always-on OpenClaw agent on office2, running
3× daily, and adds the Vikunja task bridge so actionable items actually
create tasks rather than being flagged in a log.

Current gaps:
- ❌ Inbox processing depends on Mac being awake and a conversation being
  initiated — not always-on
- ❌ Task and action items found in inbox notes are logged but never create
  Vikunja tasks
- ❌ Goal declarations found in inbox notes are not routed to Goals-MOC.md
  or Vikunja via the Felix declaration format
- ❌ No on-demand trigger — Kent cannot say "process my inbox now" via
  WhatsApp and have it run

This spec delivers an always-on inbox processing agent on office2 that runs
the existing skill logic, adds the Vikunja task bridge, and supports
on-demand triggering via WhatsApp.

---

## Problem Statement

**Current State:**
```
Kent (Mac/iPhone)
└── ✅ Wispr Flow + Obsidian inbox capture working
└── ✅ Three skills exist and work in Cowork Mac sessions
│   ├── inbox-processor (orchestrator)
│   ├── kent-voice (authoring style)
│   └── vault-writer (file operations)
└── ❌ Skills only run when Mac is awake + session is initiated
└── ❌ Task items flagged in log only — not in Vikunja
└── ❌ No always-on processing

office2
└── ✅ OpenClaw running (F002)
└── ✅ Vikunja API skill installed (F007)
└── ✅ Obsidian vault synced continuously via obsidian-sync.service
└── ✅ claude user has secondbrain group membership (vault read/write)
└── ❌ No inbox processing agent configured
└── ❌ No scheduled inbox processing
```

**Target State:**
```
Kent (Mac/iPhone)
└── ✅ Captures notes via Wispr Flow / typing as before
└── ✅ Can trigger "process my inbox now" via WhatsApp
└── ✅ Task items from inbox land in Vikunja automatically

office2
└── ✅ felix-admin-capture agent processes inbox 3× daily
└── ✅ Vault written to via claude user (secondbrain group)
└── ✅ Task items → Vikunja Inbox project via API skill (F007)
└── ✅ Valid goal declarations → Goals-MOC.md + Vikunja Goals project
└── ✅ All other content routed per existing skill routing table
└── ✅ Processing log written after each run

Mac (Cowork)
└── ✅ Original skills retained as fallback — not deleted
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **The three existing skills — these are the source of truth for behavior**
   - `~/second-brain/.claude/skills/inbox-processor/SKILL.md` — the
     orchestrating skill. This defines the full processing workflow, routing
     table, goal handling rules, edge cases, and privacy rules. The
     OpenClaw agent must replicate this behavior exactly.
   - `~/second-brain/.claude/skills/kent-voice/SKILL.md` — authoring style
     guide. Voice conventions must be preserved in the migrated agent.
   - `~/second-brain/.claude/skills/vault-writer/SKILL.md` — file operation
     standards, frontmatter requirements, domain routing table, safety rules.

2. **What F007 delivered**
   - `docs/runbooks/vikunja-ops.md` — Vikunja project structure including
     the Inbox project (where task items should land), Goals project (id=11,
     where goal declarations should land), identity labels
   - `scripts/openclaw/skills/whisper/SKILL.md` — the OpenClaw skill format
     pattern. The migrated skills must follow this format.
   - `docs/runbooks/openclaw-ops.md` — how skills are installed, agent
     configuration, cron scheduling

3. **Infrastructure already in place**
   - `docs/design/architecture/data/service-inventory.json` — vault path
     at `/home/kgale/second-brain/vault`, synced by obsidian-sync.service.
     claude user has secondbrain group membership — vault access is confirmed.
   - `docs/design/architecture/data/credential-manifest.json` — vikunja-api
     token already in credential store from F002/F007

4. **Research findings that inform this spec**
   - `docs/research/005-system-architecture-development/data-architecture.md`
     — second brain access zones and agent access rules per domain
   - `docs/research/005-system-architecture-development/user-story-catalog.md`
     — B-01, B-15 define the user-facing requirements

---

## Functional Requirements

### FR-1: Inbox Processing Agent on office2

**What it must do:**
- Configure a felix-admin-capture agent in OpenClaw that replicates the
  full behavior of the existing inbox-processor skill, including:
  - The complete routing table (all content types to all destinations)
  - The goal handling rules (Felix declaration format, potential-goal flagging)
  - The edge case handling (empty files, multi-domain content, shared content)
  - The privacy absolute rule (02-Growth/_private/ is never touched)
  - The processing log output after each run

**Business rules:**
- Behavior must be functionally equivalent to the existing Cowork skill.
  The migration must not degrade the quality of inbox processing.
- The kent-voice authoring standards must be preserved — content written
  to vault files must sound like Kent, not generic AI output
- The vault-writer file operation standards must be preserved — frontmatter,
  naming conventions, wikilinks, domain routing
- The agent must read the vault from the office2 synced copy at the path
  confirmed in service-inventory.json

**Success criteria:**
- [ ] Agent processes unprocessed inbox notes and routes content correctly
- [ ] Constitution files updated with appropriate content in Kent's voice
- [ ] Domain-specific notes created/updated with correct frontmatter
- [ ] Privacy boundary enforced — 02-Growth/_private/ never touched
- [ ] Processing log written after each run

---

### FR-2: Vikunja Task Bridge

**What it must do:**
- When the inbox processor identifies a task or action item (currently
  flagged as `type: task` in the processing log), it must now create a
  real Vikunja task using the F007 API skill
- Every created task must carry:
  - Title: the action item text
  - Project: Vikunja Inbox project
  - Identity label: personal, intentional, or metalcasework (inferred
    from context — if ambiguous, default to personal)
  - Source note: reference to the originating inbox file in the description

**Business rules:**
- Task creation must use the Vikunja API skill (F007) — not direct API
  calls, not a new implementation
- The identity label must be inferred from context: business-related
  items → intentional, personal life items → personal, metal casework
  items → metalcasework
- Tasks created by this agent must be distinguishable from manually
  created tasks — include a source reference in the description
- Duplicate detection: if a task with the same title already exists in
  the Inbox project, do not create a duplicate — log it as already-exists

**Success criteria:**
- [ ] Task items from inbox notes create Vikunja tasks in the Inbox project
- [ ] Each task carries the correct identity label
- [ ] Each task description references the source inbox note
- [ ] Duplicate tasks are not created
- [ ] Task creation failures surface in the processing log, not silently dropped

---

### FR-3: Goal Declaration Routing

**What it must do:**
- When the inbox processor identifies a valid Felix goal declaration (meeting
  the "On [date], I have [outcome] as evidenced by [proof]" format), it must:
  1. Add the declaration to Goals-MOC.md Active Declarations section
  2. Create a corresponding Vikunja task in the Goals project with the
     target date as due date and the evidence criteria in the description
- When inbox content is goal-adjacent but not a valid declaration (missing
  date, missing evidence, aspirational phrasing), it must flag it in the
  processing log as `type: potential-goal` with a note on what is missing
  — the existing goal handling rules in inbox-processor/SKILL.md apply

**Business rules:**
- Never invent dates or evidence criteria — if either is absent, flag as
  potential-goal, do not promote to an active declaration
- The goal handling rules in inbox-processor/SKILL.md are the authoritative
  specification for this behavior — replicate exactly

**Success criteria:**
- [ ] Valid declarations appear in Goals-MOC.md and Vikunja Goals project
- [ ] Partial/aspirational items flagged as potential-goal in processing log
- [ ] No invalid declarations added to Goals-MOC.md

---

### FR-4: Scheduled Execution (3× Daily)

**What it must do:**
- Schedule the inbox processing agent to run 3× daily via OpenClaw's cron
  system on office2 — independent of Mac availability
- Suggested cadence: morning (7 AM), midday (12 PM), evening (6 PM) —
  planning phase should confirm these times are appropriate given
  OpenClaw's cron capabilities and any system load considerations

**Business rules:**
- Processing must be idempotent — running twice on the same inbox files
  must produce the same result as running once (already-processed files
  are skipped, already-existing tasks are not duplicated)
- If a scheduled run fails (vault unavailable, OpenClaw error), the failure
  must be logged and the next scheduled run must attempt normally

**Success criteria:**
- [ ] Cron configured for 3× daily execution
- [ ] Runs execute independently of Mac state
- [ ] Already-processed inbox files are correctly skipped
- [ ] Failed runs logged without blocking subsequent runs

---

### FR-5: On-Demand WhatsApp Trigger

**What it must do:**
- Kent must be able to send "process my inbox now" (or natural variations)
  via WhatsApp and have the inbox processing agent run immediately
- The agent must respond via WhatsApp with the processing summary when
  the run completes

**Business rules:**
- The trigger phrase should be natural — the agent must recognize intent,
  not require an exact command string
- Response must include the same summary content as the processing log:
  files processed, key actions taken, items flagged for review
- The on-demand trigger must not interfere with scheduled runs

**Success criteria:**
- [ ] "Process my inbox now" via WhatsApp triggers an immediate run
- [ ] WhatsApp response confirms completion with processing summary
- [ ] Natural variations of the trigger phrase are recognized

---

### FR-6: Cowork Skills Preserved as Fallback

**What it must do:**
- The three original Cowork skills must remain in place at
  `~/second-brain/.claude/skills/` — not deleted, not modified
- The Cowork skills serve as a fallback during the transition period and
  as a reference implementation
- The ops runbook must document the two execution paths (office2 agent
  vs. Cowork fallback) and when to use each

**Business rules:**
- The Cowork fallback is for situations where the office2 agent is down
  or misconfigured — not for routine use once the migration is confirmed
  working
- Both paths must not run simultaneously on the same inbox files — the
  `status: processed` frontmatter flag prevents double-processing

**Success criteria:**
- [ ] Original Cowork skills unchanged and functional
- [ ] Ops runbook documents both paths
- [ ] No double-processing risk when both paths exist

---

### FR-7: Operations Runbook

**What it must do:**
- Create or update `docs/runbooks/inbox-ops.md` covering:
  - How the inbox processing agent runs (schedule, trigger, agent name)
  - How to check the processing log
  - How to manually trigger a run
  - How to use the Cowork fallback
  - Troubleshooting common issues (vault not accessible, Vikunja API
    failure, unprocessed files stuck)
  - Privacy boundary reminder

**Success criteria:**
- [ ] Runbook exists and covers all topics
- [ ] Passes doc validation (frontmatter compliant)

---

## Architecture Documentation Updates

F008 adds a new agent and scheduled job but no new services, ports, or
credentials.

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Add felix-admin-capture agent entry and inbox-processing cron job |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Add inbox processing agent and cron under OpenClaw section |

### No Changes Required

- `network-topology.json` — no new ports or services
- `credential-manifest.json` — vikunja-api token already exists
- `hardware-inventory.json` — no hardware changes
- `data-flows.json` / `data-flows.md` — data flows documented in F005
  research; update deferred to architecture v1.0 doc

**Success criteria:**
- [ ] `service-inventory.json` updated with `updated_by: "F008"`
- [ ] Markdown views match JSON

---

## Out of Scope

- ❌ Daily habit tracking or recurring reminders — F009
- ❌ Escalation on inbox-derived tasks — F011
- ❌ Daily briefing that summarizes inbox-derived tasks — F013
- ❌ Inbox-to-goal routing from WhatsApp (separate capture path) — deferred
- ❌ Modifying the Cowork skill behavior — the Cowork skills are preserved
  as-is; any improvements to skill logic belong in future iterations
- ❌ Migration of kent-voice as a standalone OpenClaw skill — in OpenClaw,
  kent-voice authoring standards are absorbed into the agent's SOUL.md
  and standing orders, not a separate skill invocation

---

## Success Criteria

**Complete when:**

### Agent and Processing
- [ ] felix-admin-capture agent runs 3× daily on office2
- [ ] Full routing table behavior replicated from existing skills
- [ ] Kent's voice preserved in all generated vault content
- [ ] Privacy boundary enforced

### Task Bridge
- [ ] Task items from inbox create Vikunja tasks
- [ ] Correct identity labels applied
- [ ] No duplicate tasks created

### Goal Routing
- [ ] Valid goal declarations reach Goals-MOC.md and Vikunja
- [ ] Partial declarations flagged as potential-goal

### Triggers
- [ ] Scheduled runs operate independently of Mac
- [ ] WhatsApp on-demand trigger works and responds with summary

### Fallback
- [ ] Cowork skills intact and documented

### Documentation
- [ ] `docs/runbooks/inbox-ops.md` complete and CI-passing
- [ ] Architecture docs updated

---

## Architecture Principles

### Replicate, Don't Reinvent

The three Cowork skills represent considerable accumulated knowledge about
how Kent's inbox content should be classified, routed, and written. The
migration must preserve this behavior exactly. This is not an opportunity
to redesign the processing logic — that belongs in a future iteration after
observing the system in operation.

### kent-voice Is Identity, Not a Skill

In the Cowork context, kent-voice is loaded as a separate skill. In OpenClaw,
this authoring identity belongs in the agent's SOUL.md — it's part of who
the agent is, not a separate tool it calls. The planning phase must determine
the correct OpenClaw mechanism for encoding authoring style at the agent level.

### Task Bridge Closes the Loop

The most significant functional addition in this feature is not the migration
itself — it's the task bridge. For the first time, something Kent captures in
an inbox note will automatically appear in Vikunja as a real task. This closes
the loop between capture and accountability that has been missing.

---

## Constitutional Compliance

✅ **Privacy is absolute**: `02-Growth/_private/` is never read, processed,
routed to, referenced, or logged — replicating the absolute rule already in
the existing skills.

✅ **Narrow scope**: felix-admin-capture does one thing — inbox processing.
It does not handle WhatsApp commands (that's the router), task escalation
(F011), or briefings (F013).

✅ **Agents start at Gate 1**: All vault write operations are logged. The
processing log provides human-reviewable audit of every action taken.

✅ **Never fail silently**: Processing failures, task creation failures, and
unclassifiable content all surface in the processing log and/or WhatsApp
summary.

✅ **No credentials in code**: Vikunja API token read from credential store
via F007 skill. Never in agent source or logs.

---

## Risk Considerations

**Risk: Vault write conflicts between office2 agent and Mac Cowork session**
- If both run simultaneously on the same inbox files, they could both
  attempt to update the same vault files.
- Mitigation: The `status: processed` frontmatter flag is the mutex.
  The first processor to update a file's status prevents the second from
  processing it. Idempotency requirement in FR-4 enforces this.

**Risk: Processing quality regression from Cowork to OpenClaw**
- The Cowork skills run in a full Claude conversation with rich context.
  The OpenClaw agent runs in a more constrained context. Quality of vault
  content may differ.
- Mitigation: Processing log provides observable output for each run.
  Kent can compare quality over the first few weeks and flag regressions.
  Cowork fallback remains available if quality is unacceptable.

**Risk: Vikunja task creation creating noise**
- If the agent creates too many low-quality tasks from stream-of-consciousness
  content, the Vikunja Inbox becomes cluttered.
- Mitigation: The task bridge should apply a quality threshold — only
  create tasks for clearly actionable items, not passing mentions. The
  planning phase should define this threshold explicitly.

**Risk: vault path permissions on office2**
- If the claude user's secondbrain group membership does not give write
  access to specific subdirectories, vault writes will fail silently or
  with errors.
- Mitigation: Planning phase verifies vault write access as first
  discovery step. Confirm `claude` can write to each domain folder before
  implementing the agent.

---

## Notes for Implementation

**Pattern discovery (planning phase):**
- Read all three existing skill files in full before writing any agent
  configuration — they are the specification for behavior, not this spec
- Study how the F003 Whisper skill and F007 Vikunja API skill are structured
  as OpenClaw skills — the inbox processing agent's skills must follow the
  same format
- Determine how OpenClaw encodes authoring identity (kent-voice) at the
  agent level — SOUL.md is the expected mechanism but confirm from OpenClaw docs
- Verify vault write permissions for claude user on office2 before
  implementing any vault write operations

**Task bridge quality threshold:**
- Err on the side of inclusion — it is better to create a task that turns
  out not to be needed than to miss an actionable item. The Vikunja Inbox
  project is the triage point. Use the existing `type: task` classification
  from inbox-processor as the threshold, without adding a higher bar. Task
  volume and quality can be dialed back in a future iteration once patterns
  are understood from real usage.

**Transition period:**
- Focus on getting the office2 agent working correctly. The Cowork skills
  remain available as a documented fallback if needed, but the goal is to
  run the office2 version as the primary path from deployment. The ops
  runbook documents the fallback procedure but parallel running is not
  required.

**Future architecture consideration — two-layer classification:**
- A pattern worth evaluating after F008 is in operation: the agent's
  SOUL.md handles broad intent classification (task vs. calendar item vs.
  goal vs. second brain content), while specialized downstream skills
  handle the precise execution against each target system. F008 already
  approximates this with inbox-processor (classifier) + Vikunja API skill
  (executor). Observing real usage will reveal where finer-grained
  classification or more focused execution skills would add value.
  Captured for consideration in F010 agent design.

---

**END OF SPECIFICATION**
