# Quickstart: Vikunja API Skill

## Prerequisites

- office2 accessible via `ssh office2-claude`
- OpenClaw running (`systemctl --user status openclaw-gateway`)
- Vikunja running at `https://office2.tail0f5f56.ts.net`
- API token at `/data/services/openclaw/secrets/vikunja-api`

## Development

The skill is a single SKILL.md file. Edit it at:

```
scripts/openclaw/skills/vikunja-api/SKILL.md
```

Follow the Whisper skill pattern at `scripts/openclaw/skills/whisper/SKILL.md`
for format reference.

## Deploy

```bash
# Copy skill to office2
scp scripts/openclaw/skills/vikunja-api/SKILL.md \
  office2-claude:~/.openclaw/skills/vikunja-api/SKILL.md

# Or via SSH
ssh office2-claude "mkdir -p ~/.openclaw/skills/vikunja-api"
ssh office2-claude "cat > ~/.openclaw/skills/vikunja-api/SKILL.md" \
  < scripts/openclaw/skills/vikunja-api/SKILL.md
```

## Verify

```bash
# Check skill is loaded
ssh office2-claude "openclaw skills list" | grep vikunja

# Test via agent message
ssh office2-claude "openclaw agent --message 'List all Vikunja projects'"
```

## Test API directly

```bash
# Health check (no auth)
ssh office2-claude 'curl -s https://office2.tail0f5f56.ts.net/api/v1/info'

# List projects
ssh office2-claude 'curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" https://office2.tail0f5f56.ts.net/api/v1/projects'

# List labels
ssh office2-claude 'curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" https://office2.tail0f5f56.ts.net/api/v1/labels'
```
