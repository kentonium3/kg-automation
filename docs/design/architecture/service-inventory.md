---
title: Service Inventory
doc_type: reference
status: approved
---

# Service Inventory

Authoritative data: [`data/service-inventory.json`](<./data/service-inventory.json>)

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
| Inbox Processing (morning) | 7 AM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (midday) | 12 PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (afternoon) | 5 PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (evening) | 10 PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Habit Check-in (morning) | 7:05 AM ET daily | OpenClaw cron → felix-admin-habits | claude | Daily habit check-in via WhatsApp |
| Habit Report (weekly) | Sunday 6PM ET | OpenClaw cron → felix-admin-habits | claude | Weekly habit pattern report via WhatsApp |
| Incomplete Task Detection | Every 4 hours (`0 */4 * * *`) | OpenClaw cron → felix-admin-tasker | claude | Poll Inbox for flat tasks |
| Escalation Check (daily) | 8:00 AM ET daily | OpenClaw cron → felix-admin-escalation | claude | Overdue task escalation via WhatsApp |
| Second Brain Sync | Every 15 min | `second-brain-sync.timer` (systemd) | kgale | Bidirectional git sync for non-vault content |
| Felix Core Digest | Every 15 min | `felix-core-digest.timer` (systemd) | claude | Agent activity log summarization → Obsidian digests |

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
- **Runbook**: `docs/runbooks/vikunja-ops.md`
- **F006 additions**: Goals project (top-level, id=11) for structured goal declarations, `metalcasework` label (#ff9800), Goals saved filter. Setup script: `scripts/vikunja/setup_goals.py`. Goals runbook: `docs/runbooks/goals-ops.md`

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
- **Excluded folders**: `04-Growth/_private`
- **Consumer folders**: `01-Inbox` (input to `felix-admin-capture`), `02-Inbox-Processed` (destination after processing; consumed by #149)
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
- **Runbook**: `docs/runbooks/transcribe-ops.md`

### OpenClaw Gateway (F002)
- **Deployed by**: F002
- **Installation**: `npm install -g openclaw@v2026.3.24` (global, requires sudo)
- **Binary**: `/usr/bin/openclaw`
- **Config**: `/home/claude/.openclaw/openclaw.json`
- **Service level**: User-level systemd with lingering (not system-level)
- **Config in repo**: `scripts/openclaw/openclaw-gateway.service`, `scripts/openclaw/install.sh`
- **Credential store**: `/data/services/openclaw/secrets/` (mode 700)
- **Backup**: Data at `/data/services/openclaw/data/` and config at `/home/claude/.openclaw/` — both in Restic scope
- **Model tiering**: Global default is Haiku; per-agent model override via `agents.list[].model` in `openclaw.json`. See agent registry for per-agent assignments.
- **Runbook**: `docs/runbooks/openclaw-ops.md`

### Felix Admin Capture Agent (F008)
- **Deployed by**: F008
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-capture`
- **Workspace**: `/data/services/openclaw/inbox-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-capture/`
- **Model**: `anthropic/claude-haiku-4-5` (optimizable) — validated 2026-04-09
- **Purpose**: Autonomous Obsidian inbox processing — classifies content, routes to vault locations, creates Vikunja tasks, writes processing logs
- **Schedule**: 4x daily via OpenClaw cron (7 AM, 12 PM, 5 PM, 10 PM ET)
- **Processing logs**: `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
- **Vikunja projects used**: Inbox (tasks), Research (research requests), Goals (goal declarations)
- **Privacy boundary**: `04-Growth/_private/` is never accessed
- **Runbook**: `docs/runbooks/inbox-ops.md`

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
- **Privacy boundary**: `04-Growth/_private/` is never accessed
- **Runbook**: `docs/runbooks/habits-ops.md`

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
- **Privacy boundary**: `04-Growth/_private/` is never accessed

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

### Felix Admin Escalation Agent (F019)
- **Deployed by**: F019
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-escalation`
- **Workspace**: `/data/services/openclaw/escalation-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-escalation/`
- **Model**: `anthropic/claude-sonnet-4-6`
- **Purpose**: Overdue task escalation — detects tasks past due date, delivers level-appropriate WhatsApp alerts, tracks escalation state via Vikunja comments
- **Skills**: escalation, vikunja-api
- **Autonomy**: Assisted (Level 1)
- **Trigger**: Cron (daily), manual
- **Schedule**: Daily at 8:00 AM ET via OpenClaw cron (`0 12 * * *`)
- **Delivery**: WhatsApp to +16179300916
- **Privacy boundary**: `04-Growth/_private/` is never accessed

### Felix Core Digest (F014)
- **Deployed by**: F014
- **Type**: Scheduled service (systemd user timer)
- **systemd unit**: `felix-core-digest.timer` + `felix-core-digest.service` (user unit under claude)
- **Schedule**: Every 15 minutes (OnUnitActiveSec=15min, OnBootSec=3min, Persistent=true)
- **Runs as**: claude user
- **ExecStart**: `/usr/bin/python3 /home/claude/repos/kg-automation/scripts/openclaw/observation/summarize.py`
- **Input**: JSONL log files at `~/second-brain/agents/logs/{agent}/YYYY-MM-DD.jsonl`
- **Output**: Markdown digests at `~/second-brain/notes/Agent-Logs/`
- **Retention**: 5 days (digest files deleted by filename date)
- **Idempotency**: Skips writes when no new JSONL content since last run
- **Source in repo**: `scripts/openclaw/observation/summarize.py`
- **Log writer**: `scripts/openclaw/observation/log_action.py` (utility, not a service)
- **Runbook**: `docs/runbooks/observation-ops.md`

## Schema v1.1 Fields

As of F016, `service-inventory.json` includes additional fields on each service entry to support change control governance:

| Field | Type | Purpose |
|-------|------|---------|
| `risk_tier` | integer (0-4) | Risk classification per the five-tier taxonomy in `data/change-risk-taxonomy.json`. Determines which guardrail protocol applies to changes affecting this service. |
| `dependencies` | array of strings | Services this entry depends on. Used by the pre-flight checklist (`docs/runbooks/governance/pre-flight-checklist.md`) to assess blast radius before a change. |
| `health_check` | object | Defines how to verify the service is healthy after a change. Used by post-change verification (`docs/runbooks/governance/post-change-verification.md`). Contains `command` and `expected` fields. |
| `config_files` | array of strings | Filesystem paths to configuration files for this service. Referenced during pre-flight to ensure config backups exist before changes. |

These fields are consumed by the governance runbooks — not by runtime automation. The visual dependency graph is rendered in `docs/design/architecture/service-dependencies.view.md`.

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
- **Runbook**: `docs/runbooks/whatsapp-ops.md`
