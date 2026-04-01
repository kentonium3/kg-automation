---
title: OpenClaw Operations Runbook
doc_type: handbook
status: draft
---

# OpenClaw Operations Runbook

This runbook covers operations for the OpenClaw gateway service on office2.

## Installed Version

- **Version**: OpenClaw 2026.3.24
- **Installation**: `npm install -g openclaw@v2026.3.24` (global, requires sudo)
- **Binary**: `/usr/bin/openclaw`
- **Config**: `/home/claude/.openclaw/openclaw.json`

## Service Management

OpenClaw runs as a **user-level systemd service** for the claude user with lingering enabled.

**Service name**: `openclaw-gateway`

### Check status

```bash
# As claude user (no sudo required):
systemctl --user status openclaw-gateway
```

### Start / Stop / Restart

```bash
# As claude user (no sudo required for user-level service):
systemctl --user start openclaw-gateway
systemctl --user stop openclaw-gateway
systemctl --user restart openclaw-gateway
```

### View logs

```bash
journalctl --user -u openclaw-gateway -f              # follow live
journalctl --user -u openclaw-gateway --since "1 hour ago"
journalctl --user -u openclaw-gateway --since today
```

### Lingering

Lingering is enabled for the claude user, which means the service continues running after logout:

```bash
# Check lingering status:
ls /var/lib/systemd/linger/ | grep claude

# If lingering is lost (requires sudo — Kent runs):
sudo loginctl enable-linger claude
```

## Credentials

### API Key (Anthropic)

- **Storage**: OpenClaw native auth at `/home/claude/.openclaw/agents/main/agent/auth-profiles.json` (mode 600)
- **Backup copy**: `/data/services/openclaw/secrets/anthropic` (mode 600)
- **Rotation procedure**:
  1. Get new API key from https://console.anthropic.com/settings/keys
  2. Update the auth-profiles.json file (edit the `key` field)
  3. Update the backup copy in `/data/services/openclaw/secrets/anthropic`
  4. Restart: `systemctl --user restart openclaw-gateway`
  5. Verify logs show successful API connection

### Vikunja API Token

- **Storage**: `/data/services/openclaw/secrets/vikunja-api` (mode 600)
- **Token name in Vikunja**: `openclaw-agent`
- **Rotation procedure**:
  1. Generate new token in Vikunja UI (Settings → API Tokens)
  2. Revoke old token in Vikunja UI
  3. Update: `echo '<NEW_TOKEN>' > /data/services/openclaw/secrets/vikunja-api`
  4. Verify: `curl -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" http://100.92.197.90:3456/api/v1/info`

### Credential Store

```
/data/services/openclaw/secrets/    (mode 700, claude-owned)
├── anthropic                       (mode 600, backup of API key)
└── vikunja-api                     (mode 600, persistent Vikunja token)
```

## Version Updates

1. **Check release notes** for breaking changes
2. **Verify a recent backup exists**: `restic snapshots --latest 1` (with correct env vars)
3. **Install new version** (Kent runs): `sudo npm install -g openclaw@<new-version>`
4. **Update the captured unit file** in `scripts/openclaw/openclaw-gateway.service` (version in Description)
5. **Restart**: `systemctl --user restart openclaw-gateway`
6. **Verify**: `openclaw --version` and check logs
7. **Commit** the version change to the repo

### Rollback

1. `sudo npm install -g openclaw@v2026.3.24` (previous version)
2. `systemctl --user restart openclaw-gateway`
3. Verify service is healthy

## API Connectivity Check

```bash
# Verify no proxy in logs:
journalctl --user -u openclaw-gateway --since "1 hour ago" | grep -i "litellm\|proxy\|openai-compat"
# Expected: no output

# Verify gateway is responding:
curl -s http://127.0.0.1:18789/
```

## Skill Directory

Skills are managed by OpenClaw at `/home/claude/.openclaw/skills/`.
Skills committed to the kg-automation repo live at `scripts/openclaw/skills/`.

```bash
# List installed skills:
openclaw skills list

# Install a skill from the workspace:
openclaw skills install <skill-slug>

# Search ClawHub (public registry) for community skills:
openclaw skills search "<query>"
```

### ClawHub — Public Skill Registry

ClawHub (`clawhub.ai`) is the public registry for OpenClaw skills. It supports
discovery, versioning, and publishing. The kg-automation skills can be published
to ClawHub for backup and versioning using the `clawhub` CLI.

**Constitution policy**: Community skills from ClawHub must be read and reviewed
before installation. Never run `openclaw skills install <community-skill>` without
first reading the skill's SKILL.md and any supporting files. This is a hard
boundary — no exceptions.

**Publishing own skills** (backup/versioning — permitted):
```bash
# Install clawhub CLI (if needed):
npm i -g clawhub

# Publish a skill:
clawhub skill publish ./scripts/openclaw/skills/whisper \
  --slug kg-whisper --name "Whisper Transcription" --version 1.0.0 --tags latest

# Sync all skills:
clawhub sync --all
```

## Data and Backups

- **Workspace**: `/data/services/openclaw/data/` (in Restic backup scope)
- **Config**: `/home/claude/.openclaw/` (in Restic backup scope via `/home/claude/`)
- **Sessions**: `/home/claude/.openclaw/agents/main/sessions/`

## Security Baseline Reset

After deploying or upgrading OpenClaw, reset the security audit baselines:

```bash
# Check current baselines:
ls /data/services/security-monitor/baselines/

# Run the audit to see if alerts fire:
sg docker -c /data/services/security-monitor/scripts/audit.sh

# If baseline reset is needed (may require sudo):
cd /data/services/security-monitor && ./scripts/generate-baselines.sh
```

## Gateway Access

- **Local URL**: `http://127.0.0.1:18789/`
- **Binding**: Loopback only (not exposed to network)
- **Gateway port**: 18789
- **Dashboard**: `openclaw dashboard --no-open` (prints URL with auth token)

## Governance

Felix agents operate under a formal governance framework established in F012.
All agents are registered, assigned an autonomy level, and bound by the
Felix Constitution.

### Key Documents

| Document | Path | Purpose |
|----------|------|---------|
| Felix Constitution | `docs/constitution/FELIX-CONSTITUTION.md` | Top-level governance — autonomy levels, principles, boundaries |
| Agent Registry (human-readable) | `docs/constitution/AGENT-REGISTRY.md` | Quick-reference agent list with current autonomy levels |
| Agent Registry (machine-readable) | `docs/constitution/agent-registry.json` | Authoritative agent state, transition history |
| Governance Runbook | `docs/handbooks/felix-governance.md` | Operational procedures for promotions, demotions, registration |

### Quick Reference

- All agents start at **Assisted (Level 1)** and require explicit promotion
- Each agent's `AGENTS.md` includes a governance preamble referencing the constitution
- The constitution is the tiebreaker when standing orders are ambiguous
- See the [Felix Governance Runbook](felix-governance.md) for all procedures
