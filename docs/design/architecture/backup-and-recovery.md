---
title: Backup and Recovery
doc_type: reference
status: approved
---

# Backup and Recovery

## Restic Backup

| Attribute | Value |
|-----------|-------|
| Schedule | 4AM daily (claude's crontab) |
| Script | `/data/services/backup/scripts/backup.sh` |
| Repository | `/mnt/backups/restic-repo` (916 GB drive) |
| Password | `/home/claude/.config/restic/password` |
| Retention | GFS (grandfathered) |

### Backup Sources

| Path | Contents |
|------|----------|
| `/data/services` | All service data (Vikunja, transcribe, security monitor, backup logs) |
| `/data/transcripts` | Transcription outputs |
| `/home/claude` | Claude user home (configs, scripts) |
| `/home/kgale` | Kgale user home (second-brain vault, configs) |

### Exclusions

- `/data/services/transcribe/models` (large ML models, re-downloadable)
- `*.tmp`, `__pycache__`, `.cache`

### What's Covered

| Service | Data Path | Backed Up? |
|---------|-----------|------------|
| Vikunja | `/data/services/vikunja/data` | Yes (under `/data/services`) |
| Obsidian Vault | `/home/kgale/second-brain/vault` | Yes (under `/home/kgale`) |
| Transcribe | `/data/services/transcribe` | Yes (excluding models) |
| Security Baselines | `/data/services/security-monitor/baselines` | Yes |

### Verification

```bash
# List recent snapshots:
export RESTIC_REPOSITORY="/mnt/backups/restic-repo"
export RESTIC_PASSWORD_FILE="/home/claude/.config/restic/password"
restic snapshots --latest 3

# Check specific path in latest snapshot:
restic ls latest /data/services/vikunja/data/
```

### Recovery

```bash
# Restore a specific file:
restic restore latest --target /tmp/restore --include /data/services/vikunja/data/vikunja.db

# Restore entire service directory:
restic restore latest --target /tmp/restore --include /data/services/vikunja/
```

## Obsidian Sync (Additional Redundancy)

The Obsidian vault is synced to Mac and iPhone via Obsidian Sync (cloud service). This provides an additional copy beyond Restic, though it is not a formal backup — it's a sync mechanism.
