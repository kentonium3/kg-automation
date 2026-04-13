---
title: Backup and Recovery
doc_type: reference
status: approved
---

# Backup and Recovery

## Restic Backup

| Attribute | Value |
|-----------|-------|
| Schedule | 4AM daily (claude's crontab, runs via `sudo`) |
| Script | `/data/services/backup/scripts/backup.sh` |
| Repository | `/mnt/backups/restic-repo` (916 GB drive) |
| Password | `/home/claude/.config/restic/password` |
| Retention | GFS (grandfathered) |
| Effective user | `root` (cron runs `sudo backup.sh`, so snapshots are `root:root`) |
| Log | `/data/services/backup/logs/backup-YYYY-MM-DD.log` |

### Backup Sources

| Path | Contents |
|------|----------|
| `/data/services` | All service data (Vikunja, transcribe, security monitor, backup logs) |
| `/data/transcripts` | Transcription outputs |
| `/home/claude` | Claude user home (configs, scripts) |
| `/home/kgale` | Kgale user home (second-brain notes, configs) |

### Exclusions

- `/data/services/transcribe/models` (large ML models, re-downloadable)
- `*.tmp`, `__pycache__`, `.cache`

### What's Covered

| Service | Data Path | Backed Up? |
|---------|-----------|------------|
| Vikunja | `/data/services/vikunja/data` | Yes (under `/data/services`) |
| Obsidian Vault | `/home/kgale/second-brain/notes` | Yes (under `/home/kgale`) |
| Transcribe | `/data/services/transcribe` | Yes (excluding models) |
| Security Baselines | `/data/services/security-monitor/baselines` | Yes |

### Verification

**Agent-accessible verification (claude user):**

The `claude` user cannot run `restic snapshots` directly because snapshot files
are owned by `root:root` with mode `400` (the backup script runs via `sudo`).
Use the backup log or directory listing instead:

```bash
# Method 1 (preferred): Check today's backup log
cat /data/services/backup/logs/backup-$(date +%Y-%m-%d).log | tail -5
# Look for: "=== Backup complete ===" and snapshot count

# Method 2: Check snapshot directory mtime
ls -laht /mnt/backups/restic-repo/snapshots/ | head -5
# Most recent file's mtime confirms when the last backup ran
```

Deploy scripts use the `--backup-confirmed` operator-attestation flag for
Tier 2 pre-flight. The operator verifies via one of the above methods and
passes the flag to confirm a backup exists within 24 hours.

**Full verification (requires kgale/root access):**

```bash
# List recent snapshots (must run as root or kgale with sudo):
sudo RESTIC_REPOSITORY="/mnt/backups/restic-repo" \
     RESTIC_PASSWORD_FILE="/home/claude/.config/restic/password" \
     restic snapshots --latest 3

# Check specific path in latest snapshot:
sudo RESTIC_REPOSITORY="/mnt/backups/restic-repo" \
     RESTIC_PASSWORD_FILE="/home/claude/.config/restic/password" \
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
