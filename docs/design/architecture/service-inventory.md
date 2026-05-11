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
| Obsidian Sync | Native | `ob` v0.0.8, `ob sync --continuous` | — | — | `obsidian-sync.service` (system, runs as `kgale`) | `/home/kgale/second-brain/notes` |
| Transcribe API | Docker (GPU) | `transcribe-transcribe` | 8787 | 100.92.197.90 | `transcribe.service` | `/data/services/transcribe` |
| OpenClaw Gateway | npm-global | `v2026.3.24` | 18789 | 127.0.0.1 | `openclaw-gateway.service` (user) | `/data/services/openclaw/data` |
| Ollama | Host binary | `ollama` (latest, 0.23.2) | 11434 | 127.0.0.1 (localhost) | `ollama.service` (system, user `ollama`) | `/usr/share/ollama/.ollama` |

## Scheduled Jobs

| Job | Schedule | Script/Agent | User | Purpose |
|-----|----------|-------------|------|---------|
| Restic Backup | 4AM daily | `/data/services/backup/scripts/backup.sh` | claude | GFS backup to `/mnt/backups/restic-repo` |
| Security Audit | 3AM daily | `/data/services/security-monitor/scripts/audit.sh` | claude | Baseline drift detection |
| Obsidian Sync Heartbeat | Every 30 min (`*/30 * * * *`) | `scripts/obsidian/sync-heartbeat.py` (#158) | claude | Probe vault sync propagation; WhatsApp alert on N consecutive failures |
| Inbox Processing (morning) | 7 AM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (midday) | 12 PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (afternoon) | 5 PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (evening) | 10 PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Habit Check-in (morning) | 7:05 AM ET daily | OpenClaw cron → felix-admin-habits | claude | Daily habit check-in via WhatsApp |
| Habit Report (weekly) | Sunday 6PM ET | OpenClaw cron → felix-admin-habits | claude | Weekly habit pattern report via WhatsApp |
| Incomplete Task Detection | Every 4 hours (`0 */4 * * *`) | OpenClaw cron → felix-admin-tasker | claude | Poll Inbox for flat tasks |
| Escalation Check (daily) | 8:00 AM ET daily | OpenClaw cron → felix-admin-escalation | claude | Overdue task escalation via WhatsApp |
| Doc Audit Poll | Every 60 minutes (top of hour UTC) | `felix-doc-auditor.timer` (systemd) → openclaw agent felix-doc-auditor | claude | Process Doc Audit / Weekly Doc Audit issues |
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

### Obsidian Sync (pre-F001, updated F011, system-level confirmed #202)
- **Deployed by**: Manual setup, updated by F011
- **Binary**: `/usr/bin/ob` (v0.0.8)
- **Command**: `ob sync --path /home/kgale/second-brain/notes --continuous`
- **Runs as**: `kgale` user (via `User=kgale` in the unit file)
- **systemd unit**: `obsidian-sync.service` — **system-level** at `/etc/systemd/system/obsidian-sync.service` (not a user unit; verify with `systemctl status obsidian-sync.service`, not `systemctl --user …`)
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

### Transcribe API (F003, GPU-accelerated 2026-05-08 via issue #80, source under git 2026-05-09 via issue #190)
- **Deployed by**: F003
- **Source in repo**: `services/transcribe/` (Dockerfile, app/, requirements.txt, docker-compose.yml, transcribe.service)
- **Compose file on office2**: `/home/claude/kg-automation/services/transcribe/docker-compose.yml` (cloned from this repo; was `/data/services/transcribe/docker-compose.yml` before #190)
- **Deploy flow**: edit in repo → push → `git pull` on office2 → `docker compose up -d --build` (or `sudo systemctl restart transcribe`)
- **Image**: `transcribe-transcribe` (locally built; renamed from `transcribe_transcribe` when migrating to compose v2 on 2026-05-08)
- **Model**: `medium.en` (faster-whisper), 4 workers, 4GB memory limit
- **systemd unit**: `transcribe.service`
- **Port binding**: `100.92.197.90:8787` (Tailscale IP only)
- **Data**: transcripts at `/data/transcripts/`, models at `/data/services/transcribe/models/` (bind mount, unchanged by #190)
- **Backup**: Included, excluding `/data/services/transcribe/models` (re-downloadable)
- **Runbook**: `docs/runbooks/transcribe-ops.md`
- **GPU acceleration** (issue #80, 2026-05-08): runs on GTX 1060 6GB via `nvidia-container-toolkit`. Compute type `int8` (Pascal-appropriate; float16 not supported on this generation). Model VRAM ~830 MiB. Real-time factor ~7x for medium.en (15.8 min audio → 2.3 min processing).
- **GPU runtime requirements**: Compose file declares `deploy.resources.reservations.devices` requesting NVIDIA driver. Container needs `LD_LIBRARY_PATH` set to pip-installed nvidia lib paths so ctranslate2 can find `libcublas.so.12` (cuDNN auto-discovers, cuBLAS does not).

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

### Ollama (issue #80, 2026-05-08)
- **Deployed by**: issue-80-gpu-install
- **Binary**: `/usr/local/bin/ollama` (installed via official `ollama.com/install.sh`)
- **systemd unit**: `ollama.service` (system-level, runs as `ollama` user)
- **Port binding**: `127.0.0.1:11434` — **localhost only**, not exposed via Tailscale. If remote access is needed later, use SSH port-forward or add a Tailscale serve rule explicitly.
- **GPU**: auto-detected NVIDIA driver, runs inference on GTX 1060 (verified with `llama3.2:3b`).
- **Data**: models at `/usr/share/ollama/.ollama/models/` (re-pullable from ollama.com — backup excluded by design)
- **Purpose**: Local LLM inference runtime for future agent / RAG workflows. No active workload yet — installed as part of the GPU compute capability rollout.
- **Verification**: `curl -s http://127.0.0.1:11434/api/version` from office2 should return JSON with the version field.

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
- **Updated by**: `027-inbox-pre-scan-helper` (2026-04-11)

#### Components

- **inbox-prescan-helper** (Python script, `scripts/inbox/prescan.py`) — Introduced by mission `027-inbox-pre-scan-helper` (issue #149). Deployed to `/home/claude/kg-automation/scripts/inbox/prescan.py` on office2. The agent's Step 1 runs this helper before any cognitive work, implementing a pre-scan-then-act pattern. The helper:
  1. Resolves `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}` via the vault path registry (`scripts/vault/paths.json`)
  2. Lists files in the inbox with `status: unprocessed`
  3. Archives stale (>7 day) processed files to `{{VAULT_INBOX_PROCESSED}}`
  4. Returns a JSON result with unprocessed paths, archived entries, and warnings

  When the helper reports zero unprocessed files, the agent replies with the single token `IDLE` and takes no further action. This bounds empty-run cost to ≤500 tokens and eliminates agent-side inbox scanning.

  - **Language**: Python
  - **Dependencies**: `scripts/vault/paths.json`
  - **Invoked by**: `felix-admin-capture` step 1
  - **Helper log**: `/home/claude/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md` (daily rotation, append-only)

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

### Felix Doc Auditor (#105, 2026-05-10)
- **Deployed by**: #105 / mission `felix-doc-auditor-agent-01KR7JK9`
- **Type**: OpenClaw agent triggered by systemd user timer (registered in #223)
- **Agent name**: `felix-doc-auditor`
- **Workspace**: `/data/services/openclaw/felix-doc-auditor/` (deployed from `scripts/openclaw/agents/felix-doc-auditor/`)
- **Skill**: `~/.openclaw/skills/doc-audit/` (deployed from `scripts/openclaw/skills/doc-audit/`)
- **Model**: `anthropic/claude-sonnet-4-6` (pinned — judgment-heavy work)
- **Autonomy level**: Assisted (Level 1) — planned promotion to Supervised (Level 2) after ~1 week clean operation
- **Schedule**: hourly via `felix-doc-auditor.timer` (systemd user timer at `~/.config/systemd/user/`, `OnCalendar=hourly`, `Persistent=true`)
- **Per-tick invocation**: `felix-doc-auditor.service` (systemd user oneshot) runs `openclaw agent --agent felix-doc-auditor --message 'Cron tick…' --timeout 1500`
- **Purpose**: processes Doc Audit and Weekly Doc Audit issues automatically; commits high-confidence edits directly, files docs-debt issues for judgment items, detects missing artifacts
- **Approval mechanism (Level 1)**: WhatsApp summary message + reply parsing (`approve`/`reject`/`skip`); 2-hour timeout = default deny
- **Concurrency lock**: GitHub label `status:in-progress` on the in-flight audit issue
- **Runbook**: `docs/runbooks/doc-auditor-ops.md`

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
