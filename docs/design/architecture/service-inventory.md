---
title: Service Inventory
doc_type: reference
status: approved
---

# Service Inventory

Authoritative data: [`data/service-inventory.json`](data/service-inventory.json)

All services run on office2 unless otherwise noted.

## Running Services

| Service | Type | Version/Image | Port | Bind IP | systemd Unit | Data Path |
|---------|------|---------------|------|---------|-------------|-----------|
| Vikunja | Docker | `vikunja/vikunja:0.24.6` | 3456 | 100.92.197.90 | `vikunja.service` | `/data/services/vikunja/data` |
| Obsidian Sync | Native | `ob sync --continuous` | — | — | `obsidian-sync.service` | `/home/kgale/second-brain/vault` |
| Transcribe API | Docker | `transcribe_transcribe` | 8787 | 100.92.197.90 | `transcribe.service` | `/data/services/transcribe` |
| OpenClaw Gateway | npm-global | `v2026.3.24` | 18789 | 127.0.0.1 | `openclaw-gateway.service` (user) | `/data/services/openclaw/data` |

## Scheduled Jobs

| Job | Schedule | Script | User | Purpose |
|-----|----------|--------|------|---------|
| Restic Backup | 4AM daily | `/data/services/backup/scripts/backup.sh` | claude | GFS backup to `/mnt/backups/restic-repo` |
| Security Audit | 3AM daily | `/data/services/security-monitor/scripts/audit.sh` | claude | Baseline drift detection |

## Deployment Details

### Vikunja (F001)
- **Deployed by**: F001
- **Config in repo**: `scripts/vikunja/deploy.sh`, `scripts/vikunja/vikunja.service`
- **Setup script**: `scripts/vikunja/setup_vikunja.py` (projects, labels, filters)
- **Data owner**: uid 1000:gid 0 (matches container runtime user)
- **Backup**: Automatically included (under `/data/services/`)
- **Runbook**: `docs/handbooks/vikunja-ops.md`

### Obsidian Sync (pre-F001)
- **Deployed by**: Manual setup
- **Runs as**: kgale user
- **Purpose**: Keeps the Obsidian vault on office2 in sync with Mac/iPhone

### Transcribe API (F003)
- **Deployed by**: F003
- **Compose file**: `/data/services/transcribe/docker-compose.yml`
- **Image**: `transcribe_transcribe` (locally built)
- **Model**: `medium.en` (faster-whisper), 4 workers, 4GB memory limit
- **systemd unit**: `transcribe.service`
- **Port binding**: `100.92.197.90:8787` (Tailscale IP only)
- **Data**: transcripts at `/data/transcripts/`, models at `/data/services/transcribe/models/`
- **Backup**: Included, excluding `/data/services/transcribe/models` (re-downloadable)
- **Runbook**: `docs/handbooks/transcribe-ops.md`

### OpenClaw Gateway (F002)
- **Deployed by**: F002
- **Installation**: `npm install -g openclaw@v2026.3.24` (global, requires sudo)
- **Binary**: `/usr/bin/openclaw`
- **Config**: `/home/claude/.openclaw/openclaw.json`
- **Service level**: User-level systemd with lingering (not system-level)
- **Config in repo**: `scripts/openclaw/openclaw-gateway.service`, `scripts/openclaw/install.sh`
- **Credential store**: `/data/services/openclaw/secrets/` (mode 700)
- **Backup**: Data at `/data/services/openclaw/data/` and config at `/home/claude/.openclaw/` — both in Restic scope
- **Runbook**: `docs/handbooks/openclaw-ops.md`
