# Implementation Plan: Daily Habit Check-in

**Branch**: `main` | **Date**: 2026-03-31 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/009-daily-habit-checkin/spec.md`

## Summary

Build a daily habit accountability loop: a new OpenClaw agent
(felix-admin-habits) delivers a morning WhatsApp check-in listing Kent's 7
recurring commitments, processes completion replies via natural language, stores
state as date-stamped comments on Vikunja habit tasks, and delivers a weekly
pattern report. Follows the felix-admin-capture agent pattern from F008.

## Technical context

**Language/Version**: Markdown (OpenClaw workspace files), Python 3.x (helper scripts)
**Primary dependencies**: OpenClaw v2026.3.24, Vikunja v0.24.6, vikunja_api skill (F007)
**Storage**: Vikunja task comments — one task per habit, daily completion as structured comments
**Testing**: Manual E2E via WhatsApp + Vikunja API verification
**Target platform**: office2 (Ubuntu 24.04 LTS)
**Project type**: OpenClaw agent configuration (no application code)
**Constraints**: Check-in must fit one phone screen (<=10 lines), weekly report <=20 lines

## Constitution check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| Privacy absolute | Pass | C-001: habits from `_private/` appear as names only, no origin context |
| Narrow scope | Pass | C-002: agent handles habits only, not tasks/goals/briefings |
| Never fail silently | Pass | C-003: ambiguous replies prompt clarification, failed writes surface errors |
| No credentials in code | Pass | C-004: Vikunja API token from credential store via vikunja_api skill |
| Gate 1 observation | Pass | C-005: agent confirms all state changes before recording |
| TEST_FIRST directive | Pass | Manual E2E testing via WhatsApp before deployment |

No violations. No complexity tracking needed.

## Project structure

### Documentation (this feature)

```
kitty-specs/009-daily-habit-checkin/
├── spec.md
├── plan.md                    # This file
├── research.md                # Phase 0: storage, delivery, routing decisions
├── data-model.md              # Phase 1: Vikunja habit/completion data model
├── contracts/
│   └── openclaw-habits-agent-contract.md   # Agent, cron, delegation contract
├── checklists/
│   └── requirements.md        # Spec quality checklist
└── tasks/                     # Phase 2 (created by /spec-kitty.tasks)
```

### Source code (repository root)

```
scripts/openclaw/agents/felix-admin-habits/
├── SOUL.md         # Kent-voice identity (reuse from felix-admin-capture)
├── USER.md         # Kent context (reuse from felix-admin-capture)
├── IDENTITY.md     # Agent identity metadata
├── TOOLS.md        # Vikunja Habits project, skill references
└── AGENTS.md       # Standing orders: check-in, completion, reporting

scripts/openclaw/agents/main-patches/
└── habits-delegation.md   # Main agent delegation instruction

docs/handbooks/
└── habits-ops.md          # Operations runbook

docs/design/architecture/
├── data/service-inventory.json   # Updated with agent + crons
└── service-inventory.md          # Updated narrative
```

## Key design decisions

### D1: Completion state storage — comments on parent tasks

Each habit is a Vikunja task in the Habits project. Daily completion is
recorded as a comment with format:
```
[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | optional note
```

Idempotent: search comments for today's date before writing. Update if
found, create if not. See [research.md](research.md) R1 and
[data-model.md](data-model.md) for full rationale.

### D2: Proactive delivery via cron (no --no-deliver)

F008's inbox cron used `--no-deliver` because output goes to a log file.
F009's check-in IS the WhatsApp message — cron output is delivered to Kent.
See [research.md](research.md) R2.

### D3: Reply routing via main agent delegation

All WhatsApp messages go to the main agent. A delegation patch teaches
it to recognize habit-related messages and forward to felix-admin-habits.
Same pattern as F008 inbox delegation. See [research.md](research.md) R3.

### D4: Check-in timing

Morning check-in at 7:05 AM ET (11:05 UTC during EDT), immediately after
the inbox-morning cron at 7:00 AM. Weekly report at Sunday 6:00 PM ET
(22:00 UTC).

### D5: Frequency encoding

Frequency is stored in the habit task description field as plain text
(e.g., "Daily", "Mon–Sat", "Mon/Wed/Fri"). The agent parses this to
determine which habits are scheduled for today. No Vikunja metadata field
for frequency.

## Implementation sequence

### WP01: Agent workspace foundation

Create the felix-admin-habits agent workspace files, register the agent
on office2, deploy the workspace, and verify operational. Reuse SOUL.md
and USER.md from felix-admin-capture.

**Deliverables**: SOUL.md, USER.md, IDENTITY.md, TOOLS.md in
`scripts/openclaw/agents/felix-admin-habits/`

**Dependencies**: None

### WP02: Vikunja habits project and initial habits

Create the Habits project in Vikunja, create 7 habit tasks with identity
labels and frequency descriptions.

**Deliverables**: Habits project + 7 tasks in Vikunja, verification script

**Dependencies**: WP01 (agent must exist to verify)

### WP03: Standing orders — check-in and completion

Write AGENTS.md with the core workflow: morning check-in generation (query
habits, filter by day, exclude completed, format message), completion
marking (natural language parsing, Vikunja comment CRUD, confirmation),
and the comment format specification. Deploy to office2.

**Deliverables**: AGENTS.md in `scripts/openclaw/agents/felix-admin-habits/`

**Dependencies**: WP01, WP02 (agent + habits must exist)

### WP04: Standing orders — reporting and habit management

Add weekly pattern report generation, on-demand track record query, and
habit add/pause/remove functionality to AGENTS.md. Deploy updated file.

**Deliverables**: Updated AGENTS.md

**Dependencies**: WP03 (core workflow must exist first)

### WP05: Scheduling and WhatsApp integration

Add cron jobs for morning check-in and weekly report. Patch main agent
AGENTS.md with habits delegation instruction. Test proactive delivery
and reply processing via WhatsApp. Verify the full loop: cron fires →
check-in delivered → Kent replies → completion recorded → confirmed.

**Deliverables**: 2 cron jobs, main agent delegation patch, E2E test results

**Dependencies**: WP03, WP04 (standing orders must be complete)

### WP06: Documentation and architecture updates

Create `docs/handbooks/habits-ops.md` operations runbook. Update
`service-inventory.json` and `service-inventory.md` with the habits agent
and cron jobs.

**Deliverables**: habits-ops.md, updated architecture docs

**Dependencies**: WP05 (deployed system to document)

## Risk mitigations

| Risk | Mitigation |
|------|-----------|
| Vikunja comment search doesn't support date filtering | Tested in research — ILIKE search on comment text confirmed. Verify during WP02. |
| Cron delivery to WhatsApp needs `--announce` flag | Test during WP05. Fall back to having the agent explicitly send via exec if needed. |
| Main agent fails to classify habit messages correctly | Test with varied natural language in WP05. Iterate on delegation prompt. |
| Check-in too verbose for 7 habits | Design for one line per habit. At 7 lines plus header, fits within 10-line budget. |

## Post-design constitution re-check

| Gate | Status | Notes |
|------|--------|-------|
| Privacy absolute | Pass | Habit names only in messages, no origin context |
| Narrow scope | Pass | Agent scope limited to habits |
| Never fail silently | Pass | Errors surfaced, ambiguity prompts clarification |
| No credentials in code | Pass | Token from credential store |
| Gate 1 observation | Pass | All state changes confirmed before recording |
| Comment format stable | Pass | Structured format enables reliable parsing |

All gates pass. Ready for task generation.
