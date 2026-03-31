# F009 Research: Daily Habit Check-in

## R1: Vikunja completion state storage

**Decision**: Parent task per habit + date-stamped comments for daily records.

**Rationale**: Vikunja's native recurring tasks (Option A) mutate the task
in place when marked done — `done_at` is overwritten, no history is preserved.
This eliminates native recurrence for habit tracking. Task comments support
text search via ILIKE (`GET /tasks/{id}/comments?s=YYYY-MM-DD`), pagination,
and ordering — providing the query capability needed for 90-day trend
reporting. One task per habit keeps the Vikunja UI clean (vs. Option C's
subtask proliferation of 7 habits x 365 days = 2,555 tasks/year).

**Alternatives considered**:
- Native recurring tasks: eliminated — no history preservation
- Parent + child subtasks per day: eliminated — task proliferation, complex
  API interaction (5+ calls per operation), degraded UI
- Label-based state: not standalone — labels are metadata on tasks, not a
  storage mechanism

**Comment format**:
```
[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | optional note
```

**Idempotency**: Search comments for today's date before writing. If found,
update existing comment. If not, create new.

## R2: Proactive WhatsApp delivery from cron

**Decision**: Cron jobs omit `--no-deliver` so agent output is delivered to
Kent via WhatsApp.

**Rationale**: F008's inbox cron used `--no-deliver` because output is a log
file, not a conversation. F009's check-in IS the conversation — the agent's
output must reach Kent. OpenClaw delivers cron output to the paired WhatsApp
channel when `--no-deliver` is omitted.

**Open item**: Verify whether omitting `--no-deliver` is sufficient or if an
explicit `--announce` flag is needed on OpenClaw v2026.3.24. Test during
implementation.

## R3: Reply processing and agent delegation

**Decision**: Main agent delegates habit-related messages to
felix-admin-habits via `openclaw agent --agent felix-admin-habits`.

**Rationale**: All WhatsApp messages route to the main agent — there is no
per-agent WhatsApp binding. The main agent classifies intent and delegates.
Same pattern as F008 inbox delegation. `openclaw cron run` does not work
from within agent turns (documented in F008).

**Routing rules for main agent**:
- "process my inbox" variants → felix-admin-capture
- Habit-related messages → felix-admin-habits
- Everything else → main agent handles directly

## R4: Check-in delivery timing

**Decision**: 7:05 AM ET (11:05 UTC) — immediately after the inbox-morning
cron at 7:00 AM ET (11:00 UTC).

**Rationale**: Kent confirmed this timing. Bundled morning push — inbox
first, then habits. Configurable via cron schedule.

## R5: Weekly report timing

**Decision**: Sunday 6:00 PM ET (22:00 UTC).

**Rationale**: Evening delivery allows reflection on the completed week.
Same time slot as the inbox-evening cron, establishing a pattern of evening
summaries.
