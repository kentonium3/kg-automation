---
title: Habit Check-in Operations Runbook
doc_type: runbook
audience: agents
status: draft
---

# Habit check-in operations

## Overview

The felix-admin-habits agent manages Kent's daily habit check-ins and
accountability tracking. It runs on office2 via OpenClaw, delivering a
morning check-in via WhatsApp and recording completion state in Vikunja.
A weekly pattern report runs Sunday evenings. The agent also sets
`due_date = today` on each scheduled habit so they appear in the
Vikunja Today filter.

## Agent management

- **Agent name**: `felix-admin-habits`
- **Workspace on office2**: `/data/services/openclaw/habits-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-habits/`
- **Model**: `anthropic/claude-sonnet-4-6`

### Workspace files

| File | Purpose |
|------|---------|
| SOUL.md | Kent-voice authoring identity |
| USER.md | Kent's context |
| IDENTITY.md | Agent identity metadata |
| TOOLS.md | Vikunja API reference, habit task IDs |
| AGENTS.md | Standing orders: check-in, completion, reporting, management |

### Update workspace files

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/habits-agent/$f" \
    < scripts/openclaw/agents/felix-admin-habits/$f
done
```

### Verify agent

```bash
ssh office2-claude "openclaw agents list"
```

Expected: `felix-admin-habits` with workspace `/data/services/openclaw/habits-agent`.

## Schedule

Two cron jobs run the agent in isolated sessions, delivering output to
Kent's WhatsApp:

| Job | Schedule (UTC) | Local time (EDT) | Purpose |
|-----|---------------|-----------------|---------|
| habits-morning-checkin | `5 11 * * *` | 7:05 AM ET | Daily check-in |
| habits-weekly-report | `0 22 * * 0` | Sunday 6:00 PM ET | Weekly pattern report |

Both jobs use `--to +16179300916` for WhatsApp delivery and 120s timeout.
They do NOT use `--no-deliver`.

### View jobs

```bash
ssh office2-claude "openclaw cron list"
```

### Manual trigger

```bash
ssh office2-claude "openclaw cron run <job-uuid>"
```

Get the UUID from `openclaw cron list`.

### View run history

```bash
ssh office2-claude "openclaw cron runs --id <job-uuid>"
```

### Direct agent invocation

```bash
ssh office2-claude "openclaw agent --agent felix-admin-habits \
  --message 'Generate today'\''s habit check-in.' --json --timeout 120"
```

## Vikunja habits project

- **Project name**: Habits (id=13)
- **Web UI**: `https://office2.tail0f5f56.ts.net/projects/13`

### View habits

All habits are tasks in the Habits project. Each has a title, frequency
in the description field, and a personal identity label. The agent sets
`due_date` to today on each scheduled habit during the morning check-in
(F018). This is a visibility mechanism for the Vikunja Today filter —
the comment model remains the authoritative source of completion state.

### Current habits

| # | Task ID | Title | Frequency |
|---|---------|-------|-----------|
| 1 | 14 | Wake at 5:00 AM | Mon-Sat |
| 2 | 15 | Meditate 45 min | Daily |
| 3 | 16 | Morning shoulder PT | Daily |
| 4 | 17 | Functional strength training 45 min | Mon/Wed/Fri |
| 5 | 18 | 10K steps (monthly average) | Daily |
| 6 | 19 | Read 30 min minimum | Daily (evening) |
| 7 | 20 | Evening shoulder PT | Daily |

### Check completion history

Completion records are stored as comments on each habit task:

```bash
# Via Vikunja API
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  "https://office2.tail0f5f56.ts.net/api/v1/tasks/15/comments" | python3 -m json.tool
```

Comment format: `[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | optional note`

### Add/remove habits directly in Vikunja

Habits can be managed via the Vikunja web UI or API. To add a habit,
create a task in the Habits project with the frequency in the description
field and the personal label.

To pause a habit, add `(PAUSED)` to the description. To archive, mark
the task as done (history is preserved).

## WhatsApp interaction

### Check-in delivery

The morning cron delivers a numbered list of today's habits. Reply with
completions using natural language:

- "1 and 2 done" — marks habits #1 and #2 as complete
- "meditation done" — fuzzy matches to Meditate 45 min
- "all done" — marks all remaining habits as complete
- "skipping training" — marks as will-not-do
- "moving PT to this afternoon" — marks as rescheduled

### On-demand queries

Send any of these via WhatsApp (routed through the main agent):

- "how am I doing on my habits?"
- "show my track record"
- "habit status"

### Habit management via WhatsApp

- "add daily journaling" — adds a new habit (with confirmation)
- "pause steps habit" — pauses without deleting history
- "resume evening PT" — resumes a paused habit
- "remove reading habit" — archives (marks done, preserves history)

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| No check-in delivered | `ssh office2-claude "openclaw cron list"` | Verify cron exists, is enabled, and has `--to` set |
| Completion not recorded | Check Vikunja task comments via API | Verify vikunja_api skill: `ssh office2-claude "openclaw skills info vikunja_api"` |
| Agent not responding | `ssh office2-claude "openclaw agents list"` | Restart gateway: `ssh office2-claude "systemctl --user restart openclaw-gateway"` |
| Delivery error | `ssh office2-claude "openclaw cron runs --id <uuid>"` | Check `--to` flag is set on the cron job |
| Session cache stale | Agent uses old AGENTS.md | Restart gateway or wait for isolated session |
| Main agent not delegating | Send habit message, check response | Verify habits delegation in `/data/services/openclaw/data/AGENTS.md` |
| Habits not in Today filter | Verify morning cron ran: `ssh office2-claude "openclaw cron runs --id <uuid>"` | If cron succeeded, check task due_dates via API. If cron failed, investigate cron error. |

## Privacy boundary

**Absolute rule**: `02-Growth/_private/` is never read, processed, routed to,
referenced, or logged. Habits originating from private context appear only as
habit names. This is enforced in SOUL.md, AGENTS.md, and TOOLS.md. There are
no exceptions.
