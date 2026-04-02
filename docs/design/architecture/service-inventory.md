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
| Vikunja | Docker | `vikunja/vikunja:0.24.6` | 3456 | 0.0.0.0 | `vikunja.service` (system) | `/data/services/vikunja/data` |
| Obsidian Sync | Native | `ob` v0.0.8, `ob sync --continuous` | — | — | `obsidian-sync.service` (user) | `/home/kgale/second-brain/notes` |
| Transcribe API | Docker | `transcribe_transcribe` | 8787 | 100.92.197.90 | `transcribe.service` | `/data/services/transcribe` |
| OpenClaw Gateway | npm-global | `v2026.3.24` | 18789 | 127.0.0.1 | `openclaw-gateway.service` (user) | `/data/services/openclaw/data` |

## Scheduled Jobs

| Job | Schedule | Script/Agent | User | Purpose |
|-----|----------|-------------|------|---------|
| Restic Backup | 4AM daily | `/data/services/backup/scripts/backup.sh` | claude | GFS backup to `/mnt/backups/restic-repo` |
| Security Audit | 3AM daily | `/data/services/security-monitor/scripts/audit.sh` | claude | Baseline drift detection |
| Inbox Processing (morning) | 7AM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (midday) | 12PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (evening) | 6PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Habit Check-in (morning) | 7:05 AM ET daily | OpenClaw cron → felix-admin-habits | claude | Daily habit check-in via WhatsApp |
| Habit Report (weekly) | Sunday 6PM ET | OpenClaw cron → felix-admin-habits | claude | Weekly habit pattern report via WhatsApp |
| Incomplete Task Detection | Every 4 hours (`0 */4 * * *`) | OpenClaw cron → felix-admin-tasker | claude | Poll Inbox for flat tasks |
| Second Brain Sync | Every 15 min | `second-brain-sync.timer` (systemd) | kgale | Bidirectional git sync for non-vault content |

## Deployment Details

### Vikunja (F001)
- **Deployed by**: F001
- **Public URL**: `https://office2.tail0f5f56.ts.net`
- **TLS**: Tailscale Serve (auto-provisioned Let's Encrypt certs, auto-renewed)
- **systemd unit**: `vikunja.service` (system-level, runs as claude user, `Restart=always`)
- **Config in repo**: `scripts/vikunja/deploy.sh`, `scripts/vikunja/vikunja.service`
- **Setup script**: `scripts/vikunja/setup_vikunja.py` (projects, labels, filters)
- **Data owner**: uid 1000:gid 0 (matches container runtime user)
- **Backup**: Automatically included (under `/data/services/`)
- **Runbook**: `docs/handbooks/vikunja-ops.md`
- **F006 additions**: Goals project (top-level, id=11) for structured goal declarations, `metalcasework` label (#ff9800), Goals saved filter. Setup script: `scripts/vikunja/setup_goals.py`. Goals runbook: `docs/handbooks/goals-ops.md`

### Obsidian Sync (pre-F001, updated F011)
- **Deployed by**: Manual setup, updated by F011
- **Binary**: `/usr/bin/ob` (v0.0.8)
- **Command**: `ob sync --path /home/kgale/second-brain/notes --continuous`
- **Runs as**: kgale user (user-level systemd unit)
- **systemd unit**: `obsidian-sync.service` (user unit under kgale)
- **Vault ID** (ob CLI): `3dca727577026343c5dc34b17e05692e`
- **Auth**: `ob login` (interactive, credentials stored locally by ob)
- **Sync direction**: Bidirectional (Mac, iPhone, and office2 via Obsidian Sync cloud)
- **Conflict strategy**: Merge
- **Excluded folders**: `02-Growth/_private`
- **Purpose**: Continuous live sync of the Obsidian vault across all three devices

### Second Brain Sync (F011)
- **Deployed by**: F011
- **systemd unit**: `second-brain-sync.timer` (user unit under kgale)
- **Schedule**: Every 15 minutes
- **Runs as**: kgale user
- **Data path**: `/home/kgale/second-brain`
- **Direction**: Bidirectional (git pull --rebase, then push)
- **Purpose**: Keeps non-vault content (agents/, logs/, config) in sync between office2 and GitHub. Vault content (`notes/`) is excluded via `.gitignore` — Obsidian Sync handles that.

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

### Felix Admin Capture Agent (F008)
- **Deployed by**: F008
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-capture`
- **Workspace**: `/data/services/openclaw/inbox-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-capture/`
- **Model**: `anthropic/claude-sonnet-4-6`
- **Purpose**: Autonomous Obsidian inbox processing — classifies content, routes to vault locations, creates Vikunja tasks, writes processing logs
- **Schedule**: 3x daily via OpenClaw cron (7 AM, 12 PM, 6 PM ET)
- **Processing logs**: `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
- **Vikunja projects used**: Inbox (tasks), Research (research requests), Goals (goal declarations)
- **Privacy boundary**: `02-Growth/_private/` is never accessed
- **Runbook**: `docs/handbooks/inbox-ops.md`

### Felix Admin Habits Agent (F009)
- **Deployed by**: F009
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-habits`
- **Workspace**: `/data/services/openclaw/habits-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-habits/`
- **Model**: `anthropic/claude-sonnet-4-6`
- **Purpose**: Daily habit check-in delivery, completion tracking via Vikunja comments, weekly pattern reports, on-demand track record queries, habit management (add/pause/remove)
- **Schedule**: Morning check-in at 7:05 AM ET daily, weekly report Sunday 6 PM ET
- **Vikunja project**: Habits (id=13) with 7 habit tasks (ids 14-20)
- **Completion storage**: Comments on habit tasks in format `[Felix] YYYY-MM-DD | {state} | note`
- **WhatsApp delivery**: Cron jobs use `--to` for direct delivery; completion marking via main agent delegation
- **Privacy boundary**: `02-Growth/_private/` is never accessed
- **Runbook**: `docs/handbooks/habits-ops.md`

### Felix Admin Tasker Agent (F013)
- **Deployed by**: F013
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-tasker`
- **Workspace**: `/data/services/openclaw/tasker-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-tasker/`
- **Model**: `anthropic/claude-sonnet-4-6`
- **Purpose**: Task intelligence — transforms raw tasks into structured Vikunja entries
- **Skills**: task-intelligence, vikunja-api
- **Autonomy**: Assisted (Level 1)
- **Trigger**: Delegation from felix-admin-capture, cron (incomplete detection), manual
- **Schedule**: Every 4 hours via OpenClaw cron (`0 */4 * * *`)
- **Privacy boundary**: `02-Growth/_private/` is never accessed

**Cron setup command** (run on office2):
```bash
openclaw cron add \
  --name "task-detection" \
  --cron "0 */4 * * *" \
  --agent felix-admin-tasker \
  --session isolated \
  --message '{"action": "detect_incomplete"}' \
  --no-deliver
```

**Cron timing rationale**:
- Every 4 hours = 6 runs per day
- Balances detection speed vs. polling overhead
- Not too frequent (avoids redundant checks) but catches tasks within half a workday
- Configurable: adjust via `openclaw cron update` if 4 hours is too frequent/infrequent

### WhatsApp Channel (F004)
- **Deployed by**: F004
- **Type**: OpenClaw channel (Baileys — unofficial WhatsApp Web protocol)
- **Account**: Kent's personal cell (617) 930-0916 — linked device
- **DM policy**: `disabled` — unknown contacts silently ignored
- **Group policy**: `allowlist` — no group chats by default
- **Session storage**: `~/.openclaw/credentials/whatsapp/` (managed by OpenClaw)
- **No external credentials**: Baileys session is managed internally, not in the credential store
- **No new ports**: Baileys uses outbound WebSocket only
- **Risk acceptance**: Baileys is unofficial; account ban risk accepted (see `security-posture.md`)
- **Runbook**: `docs/handbooks/whatsapp-ops.md`
