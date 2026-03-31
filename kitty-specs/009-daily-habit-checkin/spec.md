# F009: Daily Habit Check-in

## Overview

Build a daily habit accountability loop delivered via WhatsApp and backed by
Vikunja. A new OpenClaw agent (felix-admin-habits) delivers a morning check-in
listing Kent's recurring commitments scheduled for that day. Kent marks each
complete, rescheduled, or skipped via WhatsApp reply. Completion state is
stored in Vikunja. A weekly pattern report is delivered Sunday evening. Kent
can query his track record and manage habits via WhatsApp at any time.

## Problem statement

Kent has an accountability system in progress — Vikunja holds tasks and goals,
OpenClaw orchestrates agents, WhatsApp is the channel. What is missing is the
daily feedback loop: a push-based check-in for recurring commitments, a way to
mark them done via WhatsApp, and a weekly view of patterns over time. Without
this, commitments exist as intentions without a track record.

## Actors

- **Kent** — the sole user. Interacts via WhatsApp and Vikunja web UI.
- **felix-admin-habits** — OpenClaw agent. Delivers check-ins, records
  completion state, generates reports.
- **Vikunja** — stores habit definitions and completion history.
- **Main agent** — delegates habit-related WhatsApp messages to
  felix-admin-habits (same pattern as inbox processing delegation in F008).

## Initial habit list

| # | Habit | Frequency | Identity label |
|---|-------|-----------|---------------|
| 1 | Wake at 5:00 AM | Mon–Sat | personal |
| 2 | Meditate 45 min | Daily | personal |
| 3 | Functional strength training 45 min | Mon/Wed/Fri | personal |
| 4 | 10K steps (monthly average) | Daily | personal |
| 5 | Read 30 min minimum | Daily (evening) | personal |

## User scenarios

### S1: Morning check-in

Kent receives a WhatsApp message at a configured morning time listing only
the habits scheduled for today. Each habit is one line with a clear label.
He replies with completions (e.g., "meditation done, skipped training") and
the agent confirms what was recorded.

### S2: Completion marking throughout the day

Kent sends "did my steps" or "training done" at any point during the day.
The agent recognizes which habit is being referenced, records it in Vikunja,
and confirms. If the message is ambiguous, the agent asks one clarifying
question.

### S3: Weekly pattern report

Sunday evening, Kent receives a concise WhatsApp message showing each habit's
completion rate this week vs. last week, plus an overall rate. The message
fits comfortably in one screen.

### S4: On-demand track record

Kent asks "how am I doing on my habits?" via WhatsApp at any time. The agent
responds with a 4-week summary in the same format as the weekly report.

### S5: Adding a habit

Kent says "add daily journaling as a habit" via WhatsApp. The agent confirms
details ("I'll add daily journaling as a personal habit, daily frequency.
Correct?") and creates the entry in Vikunja after confirmation.

### S6: Pausing a habit

Kent says "pause the steps habit for now." The agent archives it — no longer
appears in check-ins but history is preserved.

## Functional requirements

| ID | Requirement | Status |
|----|------------|--------|
| FR-001 | A dedicated Habits project exists in Vikunja, separate from Goals and Inbox. Each habit is a task with name, frequency, identity label, and completion notes. | proposed |
| FR-002 | Daily completion state for each habit is recorded in Vikunja in a way that supports querying across at least 90 days for trend reporting. | proposed |
| FR-003 | A daily check-in message is delivered to Kent via WhatsApp at a configured morning time, listing only habits scheduled for today. Already-completed habits are excluded. | proposed |
| FR-004 | The check-in message is concise — one line per habit with clear response instructions. | proposed |
| FR-005 | Kent can mark a habit as complete, rescheduled, or "will not do" for today via WhatsApp reply using natural language. | proposed |
| FR-006 | After marking, the agent confirms what was recorded. Ambiguous responses prompt one clarifying question. | proposed |
| FR-007 | Completion marking is idempotent — marking the same habit twice in one day updates rather than duplicates. | proposed |
| FR-008 | A weekly pattern report is delivered via WhatsApp on Sunday evening showing each habit's completion rate this week vs. last week, plus an overall rate. | proposed |
| FR-009 | Kent can query "how am I doing on my habits?" via WhatsApp at any time and receive a 4-week summary. | proposed |
| FR-010 | Kent can add a new habit via WhatsApp by describing it. The agent confirms details before creating the entry in Vikunja. | proposed |
| FR-011 | Kent can pause or remove a habit via WhatsApp. Paused habits do not appear in check-ins but their history is preserved. | proposed |
| FR-012 | An operations runbook exists at `docs/handbooks/habits-ops.md` covering habit management, manual triggers, troubleshooting, and Vikunja direct access. | proposed |
| FR-013 | Architecture documentation is updated: `service-inventory.json` and `service-inventory.md` include the habits agent and cron jobs with `updated_by: "F009"`. | proposed |

## Non-functional requirements

| ID | Requirement | Threshold | Status |
|----|------------|-----------|--------|
| NFR-001 | Check-in delivery must occur within 5 minutes of the configured time. | <= 5 min drift | proposed |
| NFR-002 | Completion marking response must be confirmed back to Kent within 30 seconds of receiving his reply. | <= 30 sec | proposed |
| NFR-003 | Weekly report generation must complete within 60 seconds. | <= 60 sec | proposed |
| NFR-004 | Completion history must support querying across at least 90 days without performance degradation. | >= 90 days queryable | proposed |
| NFR-005 | The check-in message must fit on one phone screen — no more than 10 lines for a full day's habits. | <= 10 lines | proposed |
| NFR-006 | The weekly report must fit in a single WhatsApp message. | <= 20 lines | proposed |

## Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Privacy is absolute: habits originating from `02-Growth/_private/` appear only as habit names — never with references to their origin context. | active |
| C-002 | The habits agent (felix-admin-habits) handles habit check-ins and reporting only. It does not handle task escalation, goal management, or daily briefings. | active |
| C-003 | The agent must never fail silently. Ambiguous responses prompt clarification. Failed Vikunja writes surface an error to Kent. | active |
| C-004 | No credentials in code. Vikunja API token is read from the credential store via the vikunja_api skill. | active |
| C-005 | Agent starts at Gate 1 (observation mode). All completion state changes are confirmed back to Kent before being recorded. | active |
| C-006 | Habits are not one-time tasks — they recur. The Vikunja structure must not treat each occurrence as a separate top-level task. | active |
| C-007 | Completion rate formula: (complete + rescheduled) / (complete + rescheduled + will-not-do + no-response) for scheduled days. Rescheduled counts as positive. | active |
| C-008 | The agent follows the felix-admin-capture pattern from F008: same OpenClaw workspace structure (SOUL.md, AGENTS.md, TOOLS.md, etc.), same cron pattern, same WhatsApp delivery mechanism. | active |

## Assumptions

- Vikunja's task comment API supports date-stamped entries that can be queried
  for historical reporting. If not, the planning phase will determine an
  alternative storage mechanism within the existing architecture.
- The existing WhatsApp channel (paired to Kent's number) supports both
  proactive message delivery (agent-initiated) and reply processing
  (Kent-initiated) within the same agent session.
- Kent's habit list will evolve over time. The system must support adding and
  removing habits without structural changes.
- The 10K steps habit tracks a monthly average, not a strict daily threshold.
  The check-in asks "did you get your steps today?" and the weekly report
  notes the response pattern, but does not calculate a monthly rolling average.

## Dependencies

| Dependency | Required for | Status |
|-----------|-------------|--------|
| F004 — WhatsApp channel | Check-in delivery and completion marking | complete |
| F006 — Goal and outcome structure | Vikunja project/label patterns | complete |
| F007 — Vikunja API skill | Reading/writing habit data via API | complete |
| F008 — Inbox processing migration | Agent pattern (felix-admin-capture) to replicate | complete |

## Out of scope

- Calendar time-blocking for habit completion (requires F015 calendar integration)
- Escalation for missed habits (F011 task escalation scope)
- Daily briefing that includes habit summary (F013 daily briefing scope)
- Goal-habit linkage (future enhancement once both systems are in daily use)
- Habit streak tracking (consecutive days) — basic completion rate is sufficient to start
- Oversubscription detection (deferred to F011 escalation design)

## Success criteria

1. Habits project exists in Vikunja with Kent's 5 recurring commitments, each
   with correct identity label and frequency.
2. Daily check-in is delivered at the configured time via WhatsApp, listing
   only today's scheduled habits, excluding already-completed ones.
3. Kent can mark habits complete, rescheduled, or skipped via natural language
   WhatsApp replies, with confirmation after each marking.
4. Weekly pattern report is delivered Sunday evening showing per-habit and
   overall completion rates, this week vs. last week.
5. On-demand track record query returns a 4-week summary via WhatsApp.
6. New habits can be added and existing habits paused/removed via WhatsApp
   without losing history.
7. Operations runbook at `docs/handbooks/habits-ops.md` passes CI validation.
8. Architecture docs updated with habits agent and cron entries.

## Key entities

- **Habit** — a recurring commitment with name, frequency, identity label,
  and active/paused status.
- **Completion record** — a date-stamped entry per habit per day recording
  the state: complete, rescheduled, will-not-do, or no-response.
- **Pattern report** — a computed view of completion rates across a date
  range, per habit and overall.

## Risk considerations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Vikunja's recurring task model may not fit habits well | High — wrong storage model makes reporting fragile | Planning phase evaluates Vikunja API before choosing approach. Parent-task-plus-comments pattern may be more reliable than native recurrence. |
| Check-in fatigue — message too long or poorly timed | Medium — Kent stops engaging | One line per habit, configurable delivery time, adjust format before adding features. |
| WhatsApp message ordering with rapid replies | Low — out-of-order processing | Each completion marking is processed independently. Idempotency handles duplicates. |
| Agent needs both proactive delivery and reply processing | Medium — two interaction modes | Planning phase determines correct OpenClaw mechanism for both modes. |

## Architecture documentation updates

| File | Change |
|------|--------|
| `data/service-inventory.json` | Add felix-admin-habits agent under openclaw-gateway; add habit check-in and weekly report cron jobs |
| `service-inventory.md` | Add habits agent narrative section and cron entries in scheduled jobs table |

No changes required to: `network-topology.json`, `credential-manifest.json`,
`hardware-inventory.json`.

## Constitutional compliance

- **Privacy is absolute**: Habits from private context appear only as names,
  never with origin references.
- **Narrow scope**: felix-admin-habits handles habit check-ins and reporting
  only.
- **Never fail silently**: Ambiguous responses prompt clarification; failed
  writes surface errors.
- **No credentials in code**: Vikunja API token from credential store.
- **Agents start at Gate 1**: Observation mode from day one — completion
  state changes confirmed before recording.
