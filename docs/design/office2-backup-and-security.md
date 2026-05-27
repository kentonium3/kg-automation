---
id: office2-backup-and-security
title: "office2 — Backup Strategy, Configuration & Security Model"
doc_type: explanation
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2026-04-05
last_updated: "2026-03-25"
revision: v1.0
audience: agents_and_humans
---

# office2 — Backup Strategy, Configuration & Security Model

This document describes the backup infrastructure and security monitoring running on office2 (Dell XPS 8700, Ubuntu 24.04 LTS), the Linux server used as a hub for AI automation development.

## Hardware Context

| Component | Details |
|---|---|
| CPU | Intel i7-4790 (4c/8t, 3.6–4.0 GHz) |
| RAM | 32 GB |
| OS disk | 238 GB SSD (100 GB LVM partition) |
| Data drive | 2.7 TB HDD mounted at `/data` |
| Backup drive | 1 TB WD USB external, ext4, mounted at `/mnt/backups` |
| GPU | AMD Radeon R7 370 (no CUDA/ROCm — CPU-only AI workloads) |

## User & Permission Model

| User | Role | Privileges |
|---|---|---|
| `kgale` | Personal admin account | Full sudo |
| `claude` | AI agent service account | Member of `docker` and `secondbrain` groups. Scoped sudo for backup script only |
| `root` | System | Not used directly for cron jobs or services |

The `claude` user owns all service directories under `/data/services/` and runs scheduled cron jobs. A narrow sudoers entry (`/etc/sudoers.d/backup-claude`) grants passwordless root execution of the backup script only, so it can read all home directories without broadening group membership.

```
# /etc/sudoers.d/backup-claude
claude ALL=(root) NOPASSWD: /data/services/backup/scripts/backup.sh
```

## Backup Strategy

The system uses a two-tier approach: **Timeshift** for OS-level snapshots and **restic** for data backups, both following Grandfather-Father-Son (GFS) rotation.

### Why GFS Rotation

If a compromise enters through a poisoned dependency (e.g., the litellm PyPI supply chain attack of March 2026), it may not be detected immediately. GFS ensures rollback points exist across a range of time horizons — not just the last few days but weeks and months back — so a clean system state is recoverable even if the breach predates discovery.

### Tier 1: OS Snapshots — Timeshift

Timeshift captures the system partition using rsync-based snapshots stored on the data drive (`/data/timeshift/`).

| Retention | Count |
|---|---|
| Daily | 7 |
| Weekly | 4 |
| Monthly | 3 |

**Config:** `/etc/timeshift/timeshift.json`
**Excludes:** `/home/kgale/**`, `/root/**` (these are covered by restic)

### Tier 2: Data Backups — restic

Restic backs up user data and service configurations to the encrypted repository on the USB backup drive.

**What is backed up:**

- `/data/services` — all service configs, scripts, Docker compose files, security baselines
- `/data/transcripts` — transcription service output
- `/home/claude` — agent service account home
- `/home/kgale` — personal home directory

**What is excluded:**

- `/data/services/transcribe/models` — large Whisper model files (re-downloadable)
- `*.tmp`, `__pycache__`, `.cache`

**Retention (GFS):**

| Tier | Kept |
|---|---|
| Daily | 7 |
| Weekly | 4 |
| Monthly | 6 |
| Yearly | 1 |

**Repository:** `/mnt/backups/restic-repo` (encrypted, deduplicated)
**Password file:** `/home/claude/.config/restic/password` (mode 600)
**Backup password:** Stored offline in password manager. Required to access or restore from the repository. Loss of this password means the backup data is irrecoverable.

**Schedule:** Daily at 4:00 AM via claude user's crontab, run with `sudo`.
**Integrity check:** Automatic every Sunday (`restic check`).
**Logs:** `/data/services/backup/logs/`

### Backup Drive

The 1 TB WD USB external drive is formatted ext4 with label `backups` and auto-mounts via fstab with `nofail` (system boots normally if drive is disconnected):

```
# /etc/fstab entry
LABEL=backups /mnt/backups ext4 defaults,nofail 0 2
```

### Restore Procedures

**Restore a file from restic:**

```bash
export RESTIC_REPOSITORY="/mnt/backups/restic-repo"
export RESTIC_PASSWORD_FILE="/home/claude/.config/restic/password"

# List snapshots
restic snapshots

# Browse a snapshot
restic ls <snapshot-id> /data/services/

# Restore specific path
restic restore <snapshot-id> --target /tmp/restore --include /data/services/transcribe/
```

**Restore OS from Timeshift:**

```bash
sudo timeshift --list
sudo timeshift --restore --snapshot '2026-03-25_03-00-01'
```

## Security Monitoring

A daily audit script scans for indicators of compromise and configuration drift. It runs at 3:00 AM (one hour before backups) so any alerts are visible before backup runs capture potentially compromised state.

**Location:** `/data/services/security-monitor/`
**Script:** `scripts/audit.sh`
**Baselines:** `baselines/` (created on first run, diffed on subsequent runs)
**Logs:** `logs/audit-YYYY-MM-DD.log` and `logs/alerts-YYYY-MM-DD.log`

### What Is Scanned

| Check | What it detects |
|---|---|
| `.pth` file scan | Python startup hijack (the litellm attack vector) |
| Pip package diff | Unexpected packages added to system Python |
| Docker image diff | Unauthorized or modified container images |
| Known IOCs | `/tmp/pglog`, `sysmon.service`, `node-setup-*` containers |
| Listening ports | New network services |
| Systemd services | Newly enabled services |
| SSH authorized_keys | Unauthorized key additions |
| `/etc/hosts` hash | Tampered DNS overrides |
| Crontab diff | Unauthorized scheduled tasks |

### Baselines

Baselines are established on first run and stored as plain text files. Any subsequent change triggers an alert. After intentional system changes (e.g., adding a new service), the baselines need to be regenerated. See the canonical [Security Baseline Operations](<../runbooks/security-baseline-ops.md>) runbook for the procedure and verification steps.

### Blocked Domains

The following C2 domains from the litellm supply chain attack are sinkholed in `/etc/hosts`:

```
0.0.0.0 checkmarx.zone
0.0.0.0 models.litellm.cloud
```

## Cron Schedule Summary

| Time | Job | User | Sudo |
|---|---|---|---|
| 3:00 AM | Security audit | claude | No (uses `sg docker`) |
| 4:00 AM | restic backup + GFS prune | claude | Yes (scoped sudoers) |
| Auto | Timeshift OS snapshots | root | Managed by Timeshift |

## Future Considerations

- **GPU upgrade:** Adding an NVIDIA GPU (e.g., GTX 1060) would dramatically accelerate the transcription service and enable GPU-accelerated AI workloads. The backup and security infrastructure requires no changes.
- **Off-site backup:** The USB drive protects against software failures and compromises but not physical events (fire, theft). Consider periodic `restic copy` to cloud storage (S3, Backblaze B2) or pulling snapshots to the Mac.
- **Mac backups:** Time Machine is the standard macOS backup tool and should be configured with an external drive. This is a separate effort.
- **Alerting:** Currently alerts are written to log files. A future enhancement could push alerts to email, Slack, or a monitoring dashboard.
