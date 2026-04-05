---
title: Inbox Processing Operations Runbook
doc_type: runbook
audience: agent-executable
status: draft
---

# Inbox processing operations

## Overview

The felix-admin-capture agent processes Kent's Obsidian inbox autonomously.
It runs on office2 via OpenClaw, 3 times daily on a cron schedule. It reads
unprocessed notes from `00-Inbox/`, classifies content, routes it to the
correct vault locations, creates Vikunja tasks for action items, and writes
a processing log.

## Agent management

- **Agent name**: `felix-admin-capture`
- **Workspace on office2**: `/data/services/openclaw/inbox-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-capture/`
- **Model**: `anthropic/claude-sonnet-4-6`

### Workspace files

| File | Purpose |
|------|---------|
| SOUL.md | Kent-voice authoring identity |
| USER.md | Kent's context |
| IDENTITY.md | Agent identity metadata |
| TOOLS.md | Vault paths, Vikunja API reference |
| AGENTS.md | Standing orders: full processing workflow |

### Update workspace files

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/inbox-agent/$f" \
    < scripts/openclaw/agents/felix-admin-capture/$f
done
```

### Verify agent

```bash
ssh office2-claude "openclaw agents list"
```

Expected: `felix-admin-capture` with workspace `/data/services/openclaw/inbox-agent`.

## Schedule

Three cron jobs run the agent in isolated sessions:

| Job | Schedule (UTC) | Local time (EDT) |
|-----|---------------|-----------------|
| inbox-morning | `0 11 * * *` | 7:00 AM ET |
| inbox-midday | `0 16 * * *` | 12:00 PM ET |
| inbox-evening | `0 22 * * *` | 6:00 PM ET |

All jobs have a 5-minute (300s) timeout and use `--no-deliver` (no WhatsApp
notification on completion).

### View jobs

```bash
ssh office2-claude "openclaw cron list"
```

### Manual trigger

```bash
ssh office2-claude "openclaw cron run <job-uuid>"
```

Get the UUID from `openclaw cron list`. Cron run by name is not currently
supported.

### Direct agent invocation

```bash
ssh office2-claude "openclaw agent --agent felix-admin-capture \
  --message 'Process the inbox now.' --json --timeout 300"
```

## Processing log

- **Location**: `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
- **Multiple runs per day**: Appended with time-stamped section headers

### Check recent logs

```bash
ssh office2-claude "ls -lt /home/kgale/second-brain/agents/logs/ | head"
```

### What to look for

- **Files processed**: Count and descriptions
- **Tasks created**: Vikunja tasks with project, label, and source
- **Goals routed**: Felix declarations added to Goals-MOC.md
- **Items flagged**: Errors, needs-review items, potential-goals

## WhatsApp trigger

Send "process my inbox" (or natural variations) via WhatsApp. The main agent
delegates to felix-admin-capture and responds with a processing summary.

**Known limitation**: The nested agent call requires sufficient timeout. If
the main agent times out before felix-admin-capture finishes, the processing
still completes but the summary is not relayed back.

## Cowork fallback

When the office2 agent is down or misconfigured, processing can be done
manually using the original Cowork skills on Mac.

### Fallback procedure

1. Open a Claude session on Mac
2. Invoke the inbox-processor skill manually:
   ```
   Use the inbox-processor skill to process my inbox
   ```
3. The skill reads from `~/second-brain/notes/00-Inbox/`
4. Results are written directly to the vault (syncs to office2 via Obsidian Sync)

### Skill locations (Mac)

- `~/second-brain/.claude/skills/inbox-processor/SKILL.md`
- `~/second-brain/.claude/skills/kent-voice/SKILL.md`
- `~/second-brain/.claude/skills/vault-writer/SKILL.md`

**Warning**: Do not run both the office2 agent and Cowork fallback
simultaneously on the same inbox files. This will cause duplicate processing.

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| No processing logs | `ssh office2-claude "openclaw cron list"` | Verify cron jobs exist and are enabled |
| Vault not accessible | `ssh office2-claude "ls /home/kgale/second-brain/notes/00-Inbox/"` | Check Obsidian Sync: `ssh office2-kgale "systemctl status obsidian-sync"` |
| Vikunja tasks not created | Check processing log error section | Verify vikunja_api skill and API token |
| Agent not responding | `ssh office2-claude "openclaw agents list"` | Restart gateway: `ssh office2-claude "systemctl --user restart openclaw-gateway"` |
| Session lock error | Check for stale `.lock` files | `ssh office2-claude "rm -f ~/.openclaw/agents/felix-admin-capture/sessions/*.lock"` |
| Timeout on large inbox | Processing log shows partial results | Increase `--timeout-seconds` on cron jobs or process manually |

## Privacy boundary

**Absolute rule**: `02-Growth/_private/` is never read, processed, routed to,
referenced, or logged. This is enforced in SOUL.md, AGENTS.md, and TOOLS.md.
There are no exceptions.
