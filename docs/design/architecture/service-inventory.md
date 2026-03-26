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
| Transcribe API | Docker | `transcribe_transcribe` | 8787 | 0.0.0.0 | — | `/data/services/transcribe` |

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

### Transcribe API (pre-F001)
- **Deployed by**: Manual setup
- **Note**: Bound to `0.0.0.0` — should be rebound to Tailscale IP in a future security hardening pass
- **Backup**: Included, excluding `/data/services/transcribe/models`
