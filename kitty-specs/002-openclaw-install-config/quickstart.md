# Quickstart: OpenClaw Install and Configuration

**Feature**: 002-openclaw-install-config
**Date**: 2026-03-26

## Prerequisites

- office2 running Ubuntu 24.04 LTS
- Node.js 22.22.1+ installed (`node --version`)
- npm available (`npm --version`)
- Tailscale active (IP: `100.92.197.90`)
- SSH access via `ssh office2-claude`
- Vikunja running (F001 complete) at `http://100.92.197.90:3456`
- Kent available for: onboarding wizard, sudo commands, credential placement

## Deployment Steps

### 1. Install OpenClaw

```bash
ssh office2-claude
npm install -g openclaw@v2026.3.24
openclaw --version  # verify
```

### 2. Create Directory Structure

```bash
mkdir -p /data/services/openclaw/secrets
mkdir -p /data/services/openclaw/data
chmod 700 /data/services/openclaw/secrets
```

### 3. Kent: Place Credentials

Kent places the Anthropic API key:
```bash
# As claude user on office2:
# Kent provides the API key value
echo "<API_KEY>" > /data/services/openclaw/secrets/anthropic
chmod 600 /data/services/openclaw/secrets/anthropic
```

Kent generates Vikunja API token (in Vikunja UI: Settings → API Tokens, name: `openclaw-agent`):
```bash
echo "<TOKEN>" > /data/services/openclaw/secrets/vikunja-api
chmod 600 /data/services/openclaw/secrets/vikunja-api
```

### 4. Kent: Run Onboarding

```bash
openclaw onboard --install-daemon
# Follow the interactive wizard
# This creates ~/.openclaw/openclaw.json and installs a systemd service
```

### 5. Capture and Adjust systemd Unit

```bash
# Find the generated unit:
systemctl cat openclaw  # or check ~/.config/systemd/user/

# Copy to repo, adjust User/paths/restart policy
# Final version committed to scripts/openclaw/openclaw.service
```

### 6. Customize Config

Edit `/home/claude/.openclaw/openclaw.json` to add:
- SecretRef file source for Anthropic API key
- Workspace path at `/data/services/openclaw/data`
- Gateway loopback binding

### 7. Verify

- [ ] `systemctl status openclaw` shows active
- [ ] `journalctl -u openclaw` shows no proxy/litellm references
- [ ] `curl -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" http://100.92.197.90:3456/api/v1/info` returns HTTP 200
- [ ] Credential store permissions: `stat /data/services/openclaw/secrets/` shows mode 700
- [ ] No secrets in `git status`

## Files Created

| File | Location | Purpose |
|------|----------|---------|
| `install.sh` | `scripts/openclaw/` | npm install + directory setup |
| `openclaw.service` | `scripts/openclaw/` | Captured and adjusted systemd unit |
| `openclaw-ops.md` | `docs/handbooks/` | Operations runbook |
