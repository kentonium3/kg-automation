# Quickstart: Vikunja Docker Deploy

**Feature**: 001-vikunja-docker-deploy
**Date**: 2026-03-26

## Prerequisites

- office2 running Ubuntu 24.04 LTS with Docker installed
- Tailscale active on office2 (IP: `100.92.197.90`)
- SSH access via `ssh office2-claude`
- Python 3.11+ with `requests` library available on office2
- Kent available for any sudo commands

## Deployment Steps

### 1. Deploy Vikunja Container

```bash
# From Mac:
ssh office2-claude

# On office2 — create data directory:
mkdir -p /data/services/vikunja/data

# Deploy (agent runs deploy.sh or equivalent):
# - Pulls pinned Vikunja image
# - Starts container bound to 100.92.197.90:3456
# - Installs systemd unit
# Note: systemd unit installation requires sudo — present to Kent
```

### 2. Initial Admin Setup

```bash
# Access Vikunja web UI from Mac browser:
# http://office2:3456
# Create admin account interactively (first-run setup)
```

### 3. Run Setup Script

```bash
# From office2 (as claude user):
cd /path/to/kg-automation
python scripts/vikunja/setup_vikunja.py

# Script will prompt for Vikunja username/password
# Creates: projects, labels, saved filters
# Safe to re-run (idempotent)
```

### 4. Verify

- [ ] Web UI loads from Mac: `http://office2:3456`
- [ ] Web UI loads from iPhone via Tailscale
- [ ] All projects visible in sidebar
- [ ] Both labels selectable on a task
- [ ] All three saved filters in sidebar
- [ ] `ss -tlnp | grep 3456` shows binding to `100.92.197.90` only
- [ ] `systemctl status vikunja` shows active
- [ ] SQLite file exists at `/data/services/vikunja/data/`

### 5. Post-Deploy

- Reset security baselines at `/data/services/security-monitor/baselines/`
- Verify Vikunja data appears in next Restic backup: `restic snapshots`

## Files Created

| File | Location | Purpose |
|------|----------|---------|
| `deploy.sh` | `scripts/vikunja/` | Docker pull + run + systemd install |
| `vikunja.service` | `scripts/vikunja/` | systemd unit file |
| `setup_vikunja.py` | `scripts/vikunja/` | Idempotent project/label/filter setup |
| `vikunja-ops.md` | `docs/handbooks/` | Operations runbook |
