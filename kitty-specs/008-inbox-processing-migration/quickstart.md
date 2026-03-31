# Quickstart: Inbox Processing Migration

## Prerequisites

- office2 accessible via `ssh office2-claude`
- OpenClaw running (`systemctl --user status openclaw-gateway`)
- Vikunja API skill deployed (F007) — verify: `openclaw skills list | grep vikunja`
- Obsidian Sync running (`systemctl status obsidian-sync`)
- Vault writable by claude user: `touch /home/kgale/second-brain/vault/00-Inbox/.test && rm /home/kgale/second-brain/vault/00-Inbox/.test`

## Create the Agent

```bash
ssh office2-claude "openclaw agents add felix-admin-capture \
  --workspace /data/services/openclaw/inbox-agent \
  --model anthropic/claude-sonnet-4-6"
```

## Deploy Workspace Files

Copy workspace files to the agent's workspace:

```bash
# From Mac (after writing the files in the repo)
scp scripts/openclaw/agents/felix-admin-capture/SOUL.md \
    scripts/openclaw/agents/felix-admin-capture/AGENTS.md \
    scripts/openclaw/agents/felix-admin-capture/USER.md \
    scripts/openclaw/agents/felix-admin-capture/IDENTITY.md \
    scripts/openclaw/agents/felix-admin-capture/TOOLS.md \
    office2-claude:/data/services/openclaw/inbox-agent/
```

## Add Cron Jobs

```bash
ssh office2-claude "openclaw cron add --name inbox-morning --cron '0 11 * * *' --agent felix-admin-capture --session isolated --message 'Process the inbox now.' --no-deliver"
ssh office2-claude "openclaw cron add --name inbox-midday --cron '0 16 * * *' --agent felix-admin-capture --session isolated --message 'Process the inbox now.' --no-deliver"
ssh office2-claude "openclaw cron add --name inbox-evening --cron '0 22 * * *' --agent felix-admin-capture --session isolated --message 'Process the inbox now.' --no-deliver"
```

## Verify

```bash
# Check agent exists
ssh office2-claude "openclaw agents list"

# Check cron jobs
ssh office2-claude "openclaw cron list"

# Manual test run
ssh office2-claude "openclaw cron run inbox-morning"

# Check processing log
ssh office2-claude "ls -la /home/kgale/second-brain/agents/logs/"
```

## Create Research Project in Vikunja

```bash
ssh office2-claude 'curl -s -X PUT \
  -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  -H "Content-Type: application/json" \
  -d "{\"title\": \"Research\"}" \
  https://office2.tail0f5f56.ts.net/api/v1/projects'
```
