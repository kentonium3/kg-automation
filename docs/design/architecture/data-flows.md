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

### Doc-Auditor Direct Anthropic API (#343)

```
felix-doc-auditor.timer → felix-doc-auditor.service → scripts/doc_audit/run.py
  → Anthropic API (HTTPS, anthropic-python SDK)
  → gh CLI (subprocess; kg-felix-bot PAT)
  → /home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md (file append)
```

Post-#343 doc-audit tick flow. The systemd user timer (`felix-doc-auditor.timer`, `OnCalendar=hourly`, `Persistent=true`) launches the oneshot service which execs the Python driver. The driver:

1. Loads the Anthropic API key from `/data/services/openclaw/secrets/anthropic` (0600 file read) — see **Doc-Auditor Credential Read** below.
2. Calls Anthropic directly at three judgment moments — tier classification, debt-body generation, and cross-file implication. Prompt caching is enabled via the SDK to amortize the cached boilerplate across calls within a tick.
3. Mutates GitHub state exclusively via `gh` subprocess (issue list/edit/create/close, label add/remove, comment create) under the `kg-felix-bot` PAT.
4. Appends a per-tick prose entry to the operator-readable activity log under `/home/kgale/second-brain/agents/logs/`.

This replaces the pre-#343 path that routed through openclaw-gateway and an LLM-interpreted `SKILL.md` procedure. **No openclaw-gateway proxy is in the path** — the driver talks to Anthropic, GitHub, and the filesystem directly.

**Signal sources consumed (read-only)**:
- `/data/services/security-monitor/logs/drift-events.jsonl` — drift adapter signal source
- `/home/claude/kg-automation/docs/design/architecture/data/doc-domain-map.json` — changed-file → owning-doc scope contract
- `/home/claude/kg-automation/docs/design/architecture/data/signal-to-doc-map.json` — signal-class → candidate-doc map

### Doc-Auditor Tick Signal Write (#343)

```
scripts/doc_audit/run.py → /data/services/openclaw/felix-doc-auditor-driver/last-tick.json (file write, atomic rename)
```

At the end of each tick, the driver writes a structured JSON tick signal capturing `status`, `exit_code`, `timestamp_utc`, `signals_processed`, judgment-call counts, token usage, and any errors. This is the canonical health-check and tick-observation surface (replaces the pre-#343 reliance on parsing the prose activity log). The file is overwritten each tick — latest-wins. See `contracts/tick-signal.contract.md` for the full schema.

### Doc-Auditor Credential Read (#343)

```
scripts/doc_audit/run.py → /data/services/openclaw/secrets/anthropic (file read, mode 0600)
```

Sensitive credential read path. The scripts-first driver loads the Anthropic API key directly from disk at tick start. Replaces pre-#343 indirect access through openclaw-gateway's auth-profiles indirection. The credential itself is unchanged (same key, same storage); the driver process is now the second consumer of the same secret. Sibling consumer is `openclaw-gateway` (unchanged), which holds it via its native `auth-profiles.json` mechanism.

**Sensitivity discipline**: the key is loaded once per tick into process memory only. It is never logged, never emitted in the tick signal, and never echoed to the activity log.

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
| Doc-auditor tick signal | `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json` | No (overwritten each tick) |
| Doc-auditor activity log | `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` | Via Obsidian Sync |
| Anthropic API key (sensitive) | `/data/services/openclaw/secrets/anthropic` | Yes (mode 0600) |
