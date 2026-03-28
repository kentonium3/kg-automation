# Quickstart: Whisper Transcription Skill

**Feature**: 003-whisper-transcription-skill
**Date**: 2026-03-28

## Prerequisites

- office2 running with Docker and existing transcribe-api container
- OpenClaw running (F002 complete)
- Tailscale active (IP: `100.92.197.90`)
- SSH access via `ssh office2-claude`
- Kent available for sudo commands (systemd installation)

## Steps

### 1. Capture and Update Docker Compose

```bash
# Copy existing compose file, update port binding
# Change "8787:8787" to "100.92.197.90:8787:8787"
# Commit to scripts/transcribe/docker-compose.yml
```

### 2. Create systemd Unit

```bash
# Create transcribe.service that wraps docker compose up/down
# Install via sudo (Kent runs)
```

### 3. Rebind Service

```bash
# Stop existing container
# Start via systemd (docker compose up with new binding)
# Verify: ss -tlnp | grep 8787 shows 100.92.197.90
```

### 4. Create OpenClaw Skill

```bash
# Write SKILL.md with API contract and usage instructions
# Place in ~/.openclaw/skills/whisper/
# Commit source to scripts/openclaw/skills/whisper/
```

### 5. Verify

- [ ] `ss -tlnp | grep 8787` shows `100.92.197.90` only
- [ ] `curl http://100.92.197.90:8787/health` returns OK
- [ ] Sample audio transcription produces readable text
- [ ] `ss -tlnp | grep 0.0.0.0` returns no managed services
- [ ] Runbook passes `validate_docs.py`
