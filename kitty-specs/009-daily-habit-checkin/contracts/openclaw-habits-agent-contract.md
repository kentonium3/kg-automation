# OpenClaw Agent Contract: felix-admin-habits

## Agent creation

```bash
openclaw agents add felix-admin-habits \
  --workspace /data/services/openclaw/habits-agent \
  --model anthropic/claude-sonnet-4-6
```

## Workspace structure

```
/data/services/openclaw/habits-agent/
├── AGENTS.md       # Standing orders: check-in, completion marking, reporting
├── SOUL.md         # Kent-voice authoring identity (same as felix-admin-capture)
├── USER.md         # Kent's context
├── IDENTITY.md     # Agent identity (felix-admin-habits)
└── TOOLS.md        # Tool notes (Vikunja skill, Habits project reference)
```

## Cron jobs

```bash
# Morning check-in (7:05 AM ET = 11:05 UTC during EDT)
openclaw cron add \
  --name "habits-morning-checkin" \
  --cron "5 11 * * *" \
  --agent felix-admin-habits \
  --session isolated \
  --message "Generate today's habit check-in. Query Vikunja for active habits scheduled for today, exclude any already marked complete, and deliver the check-in message." \
  --timeout-seconds 120

# Weekly pattern report (Sunday 6 PM ET = 22:00 UTC during EDT)
openclaw cron add \
  --name "habits-weekly-report" \
  --cron "0 22 * * 0" \
  --agent felix-admin-habits \
  --session isolated \
  --message "Generate the weekly habit pattern report. Compare this week vs. last week for each habit and overall." \
  --timeout-seconds 120
```

**Note**: These cron jobs do NOT use `--no-deliver` — the agent's output
must be delivered to Kent via WhatsApp.

## Main agent delegation patch

Append to `/data/services/openclaw/data/AGENTS.md`:

```markdown
## Habit tracking delegation

When Kent sends a message about habits — completing a habit ("meditation
done", "did my steps", "skipped training"), asking about habit status
("how am I doing on habits?", "show my track record"), or managing habits
("add daily journaling", "pause steps habit"):

1. Delegate to felix-admin-habits:
   openclaw agent --agent felix-admin-habits \
     --message "<Kent's exact message>" --json --timeout 120
2. Relay the result back to Kent via WhatsApp.

Do NOT handle habit tracking yourself. felix-admin-habits has the standing
orders, Vikunja project access, and completion state logic.
```

## Vikunja structure

### Habits project

```bash
curl -s -X PUT \
  -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  -H "Content-Type: application/json" \
  -d '{"title": "Habits"}' \
  https://office2.tail0f5f56.ts.net/api/v1/projects
```

### Initial habits (7 tasks)

| # | Title | Description | Label |
|---|-------|-------------|-------|
| 1 | Wake at 5:00 AM | Mon–Sat | personal |
| 2 | Meditate 45 min | Daily | personal |
| 3 | Morning shoulder PT | Daily | personal |
| 4 | Functional strength training 45 min | Mon/Wed/Fri | personal |
| 5 | 10K steps (monthly average) | Daily | personal |
| 6 | Read 30 min minimum | Daily (evening) | personal |
| 7 | Evening shoulder PT | Daily | personal |

## Privacy boundary

Same as felix-admin-capture: NEVER access `02-Growth/_private/`.
Habits originating from private context appear only as habit names.
