# Implementation Plan: F019 Escalation Engine

**Branch**: `main` | **Date**: 2026-04-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/019-escalation-engine/spec.md`
**Mission**: software-dev

---

## Summary

Build `felix-admin-escalation`, a new specialist agent that runs daily,
detects overdue and at-risk tasks in Vikunja (filtered by priority >= 2
and excluding Habits/Goals projects), delivers level-appropriate WhatsApp
alerts (Level 1 nudge / Level 2 insistence), tracks escalation state via
structured `[Felix-Escalation]` Vikunja comments, and handles Kent's
responses (done, snooze, dismiss, reschedule, acknowledge). Includes
escalation skill, ops runbook, agent registration, and architecture updates.

## Technical Context

**Language/Version**: Markdown (agent instruction files) + OpenClaw skill
definition; no application code written
**Primary Dependencies**: OpenClaw agent system, Vikunja REST API (task
queries, comments, task updates), WhatsApp delivery via OpenClaw `--to`
**Storage**: Vikunja comments (escalation state), Vikunja task fields
(done, due_date)
**Testing**: Manual verification — trigger cron, confirm alert delivery,
test response handling
**Target Platform**: office2 (Ubuntu 24.04 LTS) — agent runtime
**Constraints**: 120-second cron timeout; append-only comments; no
autonomous task mutations

## Research Findings

### Vikunja project IDs (confirmed via live API query)

| Project | ID | Escalation scope |
|---------|-----|-----------------|
| Inbox | 1 | In scope |
| Everyday | 2 | In scope |
| Someday | 4 | In scope |
| Personal Growth & Transformation | 5 | In scope |
| Business Acquisition | 6 | In scope |
| CT-90day | 7 | In scope |
| Health & Conditioning | 8 | In scope |
| Intentional LLC | 9 | In scope |
| Metal Casework | 10 | In scope |
| Goals | 11 | **Excluded** |
| Research | 12 | In scope |
| Habits | 13 | **Excluded** |

### Vikunja priority values (confirmed from task schema)

| Value | Meaning | Escalation |
|-------|---------|-----------|
| 0 | Unset | Excluded |
| 1 | Low | Excluded |
| 2 | Medium | **Included** |
| 3 | High | **Included** |
| 4 | Urgent | **Included** |

**Priority filter**: `priority >= 2` (medium and above).

### Pattern reference: felix-admin-habits

The habits agent established the cron-agent pattern this feature copies:
- Workspace files: SOUL.md, USER.md, IDENTITY.md, TOOLS.md, AGENTS.md
- Cron configuration: `openclaw cron create` with `--to +16179300916`
- Comment-as-state: `[Felix] YYYY-MM-DD | state | note`
- Deployment: `cat > /data/services/openclaw/<agent>/<file>` via SSH

The escalation agent follows all of these patterns with the
`[Felix-Escalation]` prefix distinguishing its comments.

## Constitution Check

*Charter file not yet migrated to 3.1.0a format. Governance checked
against `docs/constitution/FELIX-CONSTITUTION.md` directly.*

- **Insistence is a feature** (Design Principle 2): This feature
  implements the directive. Pass.
- **Kent has final say** (Design Principle 3): Agent detects and alerts;
  task mutations only on Kent's explicit response. Pass.
- **Narrow scope** (Directive 1): Agent handles escalation only — no
  habits, goals, briefings, calendar. Pass.
- **Never fail silently** (Directive 4): Vikunja/WhatsApp failures logged.
  Pass.
- **Earned autonomy** (Directive 2): Starts at Assisted (Level 1). Pass.
- **Privacy** (absolute): `02-Growth/_private/` never read. Pass.

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```
kitty-specs/019-escalation-engine/
├── plan.md              # This file
├── spec.md              # Feature specification
├── meta.json            # Feature identity metadata
├── research.md          # Research findings (below)
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks/               # Work package files (created by /spec-kitty.tasks)
```

### Files Created/Modified (repository)

```
scripts/openclaw/agents/felix-admin-escalation/
├── SOUL.md              # Kent-voice authoring identity (copy from habits)
├── USER.md              # Kent's context (copy from habits)
├── IDENTITY.md          # Agent identity metadata
├── TOOLS.md             # Vikunja API reference, escalation-specific
└── AGENTS.md            # Standing orders: detection, alerting, response

scripts/openclaw/skills/escalation/
└── SKILL.md             # Self-contained escalation model

docs/runbooks/
└── escalation-ops.md    # Operations runbook

docs/constitution/
└── AGENT-REGISTRY.md    # Add felix-admin-escalation entry

docs/design/architecture/data/
└── service-inventory.json  # Add agent and cron entries
docs/design/architecture/
└── service-inventory.md    # Narrative update
```

### Deployed Files (office2)

```
/data/services/openclaw/escalation-agent/
├── SOUL.md
├── USER.md
├── IDENTITY.md
├── TOOLS.md
└── AGENTS.md

/home/claude/.openclaw/skills/escalation/
└── SKILL.md
```

## Implementation Approach

### Phase 1: Agent foundation

Create the agent workspace files following the habits agent pattern.
The AGENTS.md is the core — it defines the escalation detection logic,
level determination, message formatting, comment writing, and response
handling. The skill (SKILL.md) encodes the model in a reusable,
self-contained format.

### Phase 2: Cron and deployment

Configure the OpenClaw cron job (run daily, after 7:05 AM ET, with
WhatsApp delivery). Deploy all workspace files and skill to office2.
Register the agent in OpenClaw.

### Phase 3: Documentation and architecture

Create the ops runbook. Register the agent in AGENT-REGISTRY.md.
Update service-inventory.json and service-inventory.md.

### Phase 4: Verification

Trigger the escalation cron manually. Verify alert delivery, comment
writing, and response handling. Test edge cases: silent run (no
qualifying tasks), Level 2 escalation, snooze expiry.

## Escalation State Machine

```
Task overdue (priority >= 2, not Habits/Goals)
    │
    ├── No prior escalation → Level 1 sent
    │   │
    │   ├── Kent responds (done/snooze/dismiss/reschedule) → recorded
    │   │
    │   └── No response for 2+ days → Level 2 sent
    │       │
    │       ├── Kent responds → recorded
    │       │
    │       └── No response → Level 2 repeated (max once/day)
    │
    ├── Snoozed → skip until snooze expires → re-enter at Level 1
    │
    ├── Dismissed → skip permanently
    │   (unless due_date updated to future date → re-enter at Level 1)
    │
    └── Done → skip (task complete)
```

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Alert fatigue on first run (many overdue tasks) | Medium | Medium | 7-task cap, priority filter, snooze/dismiss available |
| Level 2 tone perceived as aggressive | Low | Low | Intentional — "insistence is a feature"; configurable in skill |
| Comment accumulation slows queries | Low | Low | Agent only reads most recent escalation comment |
| Response parsing misidentifies task numbers | Low | Medium | Numbers match message-as-sent; out-of-range prompts clarification |

---

**Branch contract (confirmed)**:
- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: **yes**

---

**END OF PLAN**
