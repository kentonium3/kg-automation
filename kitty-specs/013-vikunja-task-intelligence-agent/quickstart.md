# Quickstart: Vikunja Task Intelligence Agent

**Feature**: 013-vikunja-task-intelligence-agent
**Date**: 2026-04-02

## Prerequisites

- office2 accessible via `ssh office2-claude`
- OpenClaw installed and running on office2
- Vikunja v0.24.6 running on office2 (port 3456)
- Vikunja API token at `/data/services/openclaw/secrets/vikunja-api`
- felix-admin-capture agent deployed and operational
- WhatsApp channel operational (Baileys session)

## Development Setup

```bash
# Connect to office2
ssh office2-claude

# Verify OpenClaw is running
openclaw --version

# Verify Vikunja API is accessible
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  https://office2.tail0f5f56.ts.net/api/v1/info | head -1

# Verify existing agents
openclaw agent list
```

## Agent Workspace

The agent workspace follows the standard OpenClaw pattern:

```
/data/services/openclaw/tasker-agent/
├── AGENTS.md      # Standing orders (from scripts/openclaw/agents/felix-admin-tasker/)
├── SOUL.md        # Agent identity
├── USER.md        # User context
├── IDENTITY.md    # Identity card
└── TOOLS.md       # Available tools
```

## Skill Deployment

```bash
# Deploy task-intelligence skill
cp scripts/openclaw/skills/task-intelligence/SKILL.md \
   ~/.openclaw/skills/task-intelligence/SKILL.md
```

## Manual Testing

```bash
# Test delegation handoff
openclaw agent --agent felix-admin-tasker \
  --message '{"action": "enrich_task", "raw_text": "Test task from quickstart", "source_reference": "test", "inferred_identity": "personal"}' \
  --json --timeout 120

# Test incomplete task detection
openclaw agent --agent felix-admin-tasker \
  --message '{"action": "detect_incomplete"}' \
  --json --timeout 300

# Test retroactive enrichment
openclaw agent --agent felix-admin-tasker \
  --message '{"action": "retroactive_enrichment", "batch_size": 3}' \
  --json --timeout 300
```

## Cron Setup

```bash
# Add incomplete task detection (every 4 hours)
openclaw cron add \
  --name "task-detection" \
  --cron "0 */4 * * *" \
  --agent felix-admin-tasker \
  --session isolated \
  --message '{"action": "detect_incomplete"}' \
  --no-deliver
```

## Validation Checklist

- [ ] Agent responds to delegation with `{"status": "accepted"}`
- [ ] Agent proposes task structure via WhatsApp
- [ ] Confirmed task appears in Vikunja with correct attributes
- [ ] Fallback creates flat task when agent is unavailable
- [ ] Incomplete task detection finds flat tasks in Inbox
- [ ] Enrichment state comments appear on processed tasks
- [ ] Action log entries written to `~/second-brain/agents/logs/`
