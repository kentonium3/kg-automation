---
title: Escalation Engine Operations Runbook
doc_type: runbook
audience: agents_and_humans
status: draft
---

# Escalation engine operations

## Overview

The felix-admin-escalation agent detects overdue and at-risk tasks in
Vikunja and delivers level-appropriate WhatsApp alerts to Kent. It runs
daily at 8:00 AM ET via OpenClaw cron, after the morning habit check-in.
Escalation state is tracked as structured comments on each task.

**What it escalates**: Tasks where `done = false`, `due_date < today`
(or due today with high+ priority), and `priority >= 2` (medium, high,
urgent). Habits project (ID 13) and Goals project (ID 11) are excluded.

**What it does NOT escalate**: Low-priority tasks, done tasks, habits,
goals, or tasks that have been snoozed or dismissed.

## Agent management

- **Agent name**: `felix-admin-escalation`
- **Workspace on office2**: `/data/services/openclaw/escalation-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-escalation/`
- **Model**: `anthropic/claude-sonnet-4-6`
- **Autonomy**: Assisted (Level 1) — alerts are sent; task mutations
  only on Kent's explicit reply

### Workspace files

| File | Purpose |
|------|---------|
| SOUL.md | Kent-voice authoring identity with escalation tone guidance |
| USER.md | Kent's context |
| IDENTITY.md | Agent identity metadata |
| TOOLS.md | Vikunja API reference for escalation operations |
| AGENTS.md | Standing orders: detection, alerting, response handling |

### Update workspace files

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/escalation-agent/$f" \
    < scripts/openclaw/agents/felix-admin-escalation/$f
done
```

### Verify agent

```bash
ssh office2-claude "openclaw agents list"
```

Expected: `felix-admin-escalation` with workspace `/data/services/openclaw/escalation-agent`.

## Escalation skill

The escalation model is encoded in a self-contained skill:

- **Skill on office2**: `/home/claude/.openclaw/skills/escalation/SKILL.md`
- **Source in repo**: `scripts/openclaw/skills/escalation/SKILL.md`

### Update skill

```bash
ssh office2-claude "cat > /home/claude/.openclaw/skills/escalation/SKILL.md" \
  < scripts/openclaw/skills/escalation/SKILL.md
```

The skill defines: escalation criteria, level model (Level 1 nudge /
Level 2 insistence), comment format, WhatsApp message format, response
parsing, and error handling.

## Schedule

| Job | Schedule (UTC) | Local time (EDT) | Purpose |
|-----|---------------|-----------------|---------|
| escalation-daily | `0 12 * * *` | 8:00 AM ET | Daily overdue task check |

The escalation runs 55 minutes after the habit check-in (7:05 AM ET)
so habit context is in Kent's awareness before task escalations arrive.

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

## Escalation level model

| Level | Name | Trigger | Tone |
|-------|------|---------|------|
| 1 | Nudge | Overdue 1-3 days (no prior escalation), or due today (high+ priority) | Informational |
| 2 | Insistence | Overdue >3 days, or Level 1 for 2+ days with no response | Direct |

**Priority filter**: Only tasks with priority >= 2 (medium, high, urgent).
Low-priority overdue tasks accumulate in the Vikunja Overdue filter for
manual triage.

**Project filter**: All projects except Goals (ID 11) and Habits (ID 13).

See the escalation skill for the full level determination algorithm.

## Escalation state via Vikunja comments

Escalation state is tracked as structured comments on each task using
the `[Felix-Escalation]` prefix.

### Comment format

Escalation sent:

```text
[Felix-Escalation] 2026-04-06 | level-1 | sent
[Felix-Escalation] 2026-04-06 | level-2 | sent
```

Response recorded:

```text
[Felix-Escalation] 2026-04-06 | snoozed:3d | acknowledged
[Felix-Escalation] 2026-04-06 | dismissed | acknowledged
[Felix-Escalation] 2026-04-06 | done | acknowledged
[Felix-Escalation] 2026-04-06 | rescheduled:2026-04-10 | acknowledged
```

### Check escalation history for a task

```bash
ssh office2-claude 'curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  "https://office2.tail0f5f56.ts.net/api/v1/tasks/<TASK_ID>/comments" | python3 -m json.tool'
```

Filter for comments starting with `[Felix-Escalation]`. The most recent
one determines the current escalation state.

## WhatsApp interaction

### Alert delivery

The daily cron delivers a numbered list of escalated tasks. Level 2
tasks appear first (marked with a red indicator), followed by Level 1
tasks. The list is capped at 7 tasks.

### Response options

Reply to the escalation message with:

- `1 done` — mark task #1 as complete in Vikunja
- `2 snooze 3d` — suppress escalation for task #2 for 3 days
- `1 dismiss` — permanently stop escalating task #1
- `move 2 to friday` — reschedule task #2 to next Friday
- `all snooze 2d` — snooze all listed tasks for 2 days
- `got it` — acknowledge without specific action

## Configuration

### Adjust priority threshold

Edit the escalation skill (`scripts/openclaw/skills/escalation/SKILL.md`),
update the priority filter value, and redeploy to office2.

### Adjust project exclusions

Edit the escalation skill, update the project exclusion list, and
redeploy.

### Adjust cron schedule

```bash
ssh office2-claude "openclaw cron update <uuid> --cron '<new-expression>'"
```

### Temporarily pause escalation

Disable the cron job (e.g., during travel):

```bash
ssh office2-claude "openclaw cron disable <uuid>"
```

Re-enable when ready:

```bash
ssh office2-claude "openclaw cron enable <uuid>"
```

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| No escalation alerts received | Check cron ran: `ssh office2-claude "openclaw cron runs --id <uuid>"` | Verify cron exists, is enabled, has `--to` set |
| Wrong tasks escalated | Check priority and project filters in escalation skill | Update skill, redeploy to office2 |
| Duplicate alerts on same task same day | Check `[Felix-Escalation]` comments for same-day duplicates | Likely deduplication logic bug — check skill |
| Response not processed | Send response, check agent reply | Verify escalation skill deployed; restart gateway if needed |
| Snoozed task re-escalated early | Check snooze comment date and N value | Verify snooze expiry calculation in skill |
| Agent not responding | `ssh office2-claude "openclaw agents list"` | Restart gateway: `ssh office2-claude "systemctl --user restart openclaw-gateway"` |

## Privacy boundary

**Absolute rule**: `02-Growth/_private/` is never read, processed, routed to,
referenced, or logged. Tasks from private context appear as task names only.
This is enforced in SOUL.md, AGENTS.md, and TOOLS.md. There are no exceptions.
