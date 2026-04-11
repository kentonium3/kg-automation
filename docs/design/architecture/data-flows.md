---
title: Data Flows
doc_type: reference
status: approved
---

# Data Flows

Authoritative data: [`data/data-flows.json`](<./data/data-flows.json>)

## Active Flows

### Vikunja Web UI (F001)

```
Kent (Mac/iPhone) → HTTPS via Tailscale Serve → Vikunja :3456 → SQLite
```

Direct task management through the browser. Accessible from any Tailscale-connected device at `https://office2.tail0f5f56.ts.net`.

### Obsidian Vault Sync (updated F011)

**Live sync** (Obsidian Sync — bidirectional):
```
Mac (Obsidian) ↔ Obsidian Sync cloud ↔ office2 (ob sync --continuous) ↔ Obsidian Sync cloud ↔ iPhone (Obsidian)
```

Three-device sync loop: Mac, office2, and iPhone all stay in sync via Obsidian Sync cloud. The `ob` CLI on office2 runs as a continuous daemon (`obsidian-sync.service`, kgale user unit), syncing to `/home/kgale/second-brain/notes`. Changes on any device propagate to the others in near real-time. Obsidian Sync is the live sync mechanism — not git.

**Consumer**: `felix-admin-capture` reads from `/home/kgale/second-brain/notes/01-Inbox/` (3x daily via OpenClaw cron). Processed items are moved to `/home/kgale/second-brain/notes/02-Inbox-Processed/` once the inbox pre-scan helper (#149) ships.

### Second Brain Git Sync (F011)

**Non-vault content** (git — bidirectional, every 15 min):
```
office2 (/home/kgale/second-brain) ↔ git pull --rebase + push ↔ GitHub
```

Bidirectional git sync every 15 minutes via `second-brain-sync.timer` (kgale user unit). Syncs non-vault content (agents/, logs/, config). Vault content (`notes/`) is excluded via `.gitignore` — Obsidian Sync handles that. Replaces the old outbound-only vault-snapshot.

### Nightly Backup

```
office2 (/data/services, /data/transcripts, /home/*) → Restic → /mnt/backups/restic-repo
```

Runs at 4AM daily via claude's crontab. GFS retention policy. Excludes transcribe models, temp files, and caches.

### Security Audit

```
audit.sh → compare running state against baselines → log alerts
```

Runs at 3AM daily. Checks: Docker images, enabled services, listening ports, SSH keys, crontabs, pip packages, hosts file, pth files.

### OpenClaw → Vikunja API (F007)

```
OpenClaw agent → HTTPS via Tailscale Serve → Vikunja REST API :3456 → SQLite
```

OpenClaw agents use the vikunja_api skill to create, read, update, and query tasks
via the Vikunja REST API. Authentication is via Bearer token read from the
credential store at runtime. Used by all downstream features that touch tasks.

### Observation Digest (F014)

```
Felix agent → log_action.py → JSONL → summarize.py (15-min timer) → Markdown → Obsidian Sync → Kent's devices
```

Agent activity logging and digest generation pipeline:
1. Felix agents call `log_action.py` via OpenClaw's exec tool with structured arguments
2. `log_action.py` validates, enforces schema, and appends a JSONL entry to `~/second-brain/agents/logs/{agent}/YYYY-MM-DD.jsonl`
3. `summarize.py` runs every 15 minutes via systemd timer, reads JSONL, generates per-agent Markdown digests at `~/second-brain/notes/Agent-Logs/`
4. Digests reach Kent's Mac and iPhone via the existing Obsidian Sync flow

Raw JSONL logs are gitignored in the second-brain repo. Digest Markdown flows through Obsidian Sync (not git).

## Planned Flows (Not Yet Implemented)

| Flow | Features | Description |
|------|----------|-------------|
| WhatsApp Command Channel | F003–F006 | WhatsApp voice/text → OpenClaw → Whisper → Intent Parser → Vikunja |
| Obsidian Inbox Processing | F007–F010 | 01-Inbox → hourly processor → vault routing + Vikunja API |
| Daily Briefing | F014 | Heartbeat → task summary → WhatsApp to Kent |
| Escalation Heartbeat | F015 | Vikunja label state → escalation logic → WhatsApp alert |

## Storage Locations

| Data | Path | Backed Up |
|------|------|-----------|
| Vikunja tasks (SQLite) | `/data/services/vikunja/data/vikunja.db` | Yes |
| Obsidian vault | `/home/kgale/second-brain/notes` | Yes |
| Transcribe data | `/data/services/transcribe` | Yes (excl. models) |
| Backup repo | `/mnt/backups/restic-repo` | N/A (is the backup) |
| Security baselines | `/data/services/security-monitor/baselines` | Yes |
| Security/audit logs | `/data/services/security-monitor/logs` | Yes |
| Backup logs | `/data/services/backup/logs` | Yes |
| Agent JSONL logs | `/home/claude/second-brain/agents/logs/` | No (gitignored, ephemeral) |
| Agent digest files | `/home/claude/second-brain/notes/Agent-Logs/` | Via Obsidian Sync |
