# OpenClaw Agent Contract: felix-admin-capture

## Agent Creation

```bash
openclaw agents add felix-admin-capture \
  --workspace /data/services/openclaw/inbox-agent \
  --model anthropic/claude-sonnet-4-6
```

## Workspace Structure

```
/data/services/openclaw/inbox-agent/
├── AGENTS.md       # Standing orders: routing table, task bridge, goal handling
├── SOUL.md         # Kent-voice authoring identity
├── USER.md         # Kent's context
├── IDENTITY.md     # Agent identity (felix-admin-capture)
└── TOOLS.md        # Tool notes (vault path, vikunja skill reference)
```

## Cron Jobs

```bash
# Morning run (7 AM ET = 11:00 UTC during EDT)
openclaw cron add \
  --name "inbox-morning" \
  --cron "0 11 * * *" \
  --agent felix-admin-capture \
  --session isolated \
  --message "Process the inbox now." \
  --no-deliver

# Midday run (12 PM ET = 16:00 UTC during EDT)
openclaw cron add \
  --name "inbox-midday" \
  --cron "0 16 * * *" \
  --agent felix-admin-capture \
  --session isolated \
  --message "Process the inbox now." \
  --no-deliver

# Evening run (6 PM ET = 22:00 UTC during EDT)
openclaw cron add \
  --name "inbox-evening" \
  --cron "0 22 * * *" \
  --agent felix-admin-capture \
  --session isolated \
  --message "Process the inbox now." \
  --no-deliver
```

## WhatsApp Trigger (via main agent)

The main agent recognizes "process my inbox" intent and triggers:

```bash
openclaw cron run inbox-morning
```

Or directly:

```bash
openclaw agent --agent felix-admin-capture --message "Process the inbox now." --json
```

## Vault Paths

| Path | Purpose |
| --- | --- |
| `/home/kgale/second-brain/vault/00-Inbox/` | Source: unprocessed inbox notes |
| `/home/kgale/second-brain/vault/01-Constitution/` | Destination: values, goals, vision, identity |
| `/home/kgale/second-brain/vault/02-Growth/` | Destination: growth reflections |
| `/home/kgale/second-brain/vault/03-Health/` | Destination: health/fitness |
| `/home/kgale/second-brain/vault/04-Business/` | Destination: business content |
| `/home/kgale/second-brain/vault/05-Finance/` | Destination: financial content |
| `/home/kgale/second-brain/vault/06-Journal/` | Destination: journal entries |
| `/home/kgale/second-brain/vault/07-Resources/` | Destination: reference material |
| `/home/kgale/second-brain/agents/logs/` | Processing logs |

## Vikunja Projects Used

| Project | Purpose | Resolve by name |
| --- | --- | --- |
| Inbox | Action items / tasks | Yes |
| Research | Research requests | Yes (create if missing) |
| Goals | Goal declarations | Yes |

## Privacy Boundary

**ABSOLUTE**: `/home/kgale/second-brain/vault/02-Growth/_private/` is never
read, processed, routed to, referenced, or logged. This applies to the agent's
standing orders, SOUL.md, and all processing logic.
