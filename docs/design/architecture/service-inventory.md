---
title: Service Inventory
doc_type: reference
status: approved
tags: [656, 588, 579, 572, 520, 519, 518, 137, 189, 80, 202, 149, 190, 374, 100, 253, 185, 254, 371, 309, 343, 306, 308, 310, 362, 391, 400, 105, 115, 562, 490, 408, 567, 563, 558, 561, 540, 542, 306/, 152, 376, 368-, 112]
---

# Service Inventory

Authoritative data: [`data/service-inventory.json`](<./data/service-inventory.json>)

All services run on office2 unless otherwise noted.

## Running Services

| Service | Type | Version/Image | Port | Bind IP | systemd Unit | Data Path |
|---------|------|---------------|------|---------|-------------|-----------|
| Vikunja | Docker (compose) | `vikunja/vikunja:0.24.6` | 3456 | 100.92.197.90 | `vikunja.service` (system, oneshot → `docker compose up -d`) | `/data/services/vikunja/data` |
| Obsidian Sync | Native | `ob` v0.0.10 (upgraded 2026-06-06), `ob sync --continuous` | — | — | `obsidian-sync.service` (system, runs as `kgale`) | `/home/kgale/second-brain/notes` |
| Transcribe API | Docker (GPU) | `transcribe-transcribe` | 8787 | 100.92.197.90 | `transcribe.service` | `/data/services/transcribe` |
| OpenClaw Gateway | npm-global | `2026.6.11` | 18789 | 127.0.0.1 | `openclaw-gateway.service` (user) | `/data/services/openclaw/data` |
| Ollama | Host binary | `ollama` (latest, 0.23.2) | 11434 | 127.0.0.1 (localhost) | `ollama.service` (system, user `ollama`) | `/usr/share/ollama/.ollama` |
| Google Workspace (`gog` CLI) | CLI integration | `gog` (Linuxbrew, `steipete/tap/gogcli`) | — | — | n/a (on-demand CLI) | `/home/claude/.config/gogcli/credentials.json` |

## Scheduled Jobs

| Job | Schedule | Script/Agent | User | Purpose |
|-----|----------|-------------|------|---------|
| Restic Backup | 4AM daily | `/data/services/backup/scripts/backup.sh` | claude | GFS backup to `/mnt/backups/restic-repo` |
| Security Audit | 3AM daily | `/data/services/security-monitor/scripts/audit.sh` | claude | Baseline drift detection |
| Obsidian Sync Heartbeat | Every 30 min (`*/30 * * * *`) | `scripts/obsidian/sync-heartbeat.py` (#158) | claude | Probe vault sync propagation; WhatsApp alert on N consecutive failures |
| Credential Health Check | Daily 13:00 UTC | `credential-health-check.timer` (systemd) → `python3 -m credential_health_check` | claude | Daily credential expiry + activity-signal audit; R-003 |
| Inbox Processing (morning) | 7 AM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (midday) | 12 PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (afternoon) | 5 PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Inbox Processing (evening) | 10 PM ET daily | OpenClaw cron → felix-admin-capture | claude | Obsidian inbox processing |
| Habit Check-in (morning) | 7:05 AM ET daily | OpenClaw cron → felix-admin-habits | claude | Daily habit check-in via WhatsApp |
| Habit Report (weekly) | Monday 6 AM ET (cron `0 6 * * 1` America/New_York) | OpenClaw cron → felix-admin-habits → `scripts/habits/query_active_habits_weekly.py` → `scripts/habits/history.py` → canonical `habits-history.jsonl` (completion history); `scripts/common/vikunja_client.py` → Vikunja API for current-state habit metadata only | claude | Weekly habit pattern report via WhatsApp — deterministic-helper-backed and reads canonical JSONL (NOT Vikunja `done_at` history) post mission `trustworthy-weekly-habit-report-01KV4GZ7` (#605). Cron moved Sunday 22:00 ET → Monday 06:00 ET so the report fires after the week has closed. Helper also emits the pre-rendered WhatsApp body (`rendered_text` / `--output text`), so the agent posts verbatim. Original deterministic-helper introduction: `vikunja-client-and-habits-weekly-report-01KTKSFT` (#542 + #562); this mission corrected the read path. |
| Escalation Check (daily) | 8:00 AM ET daily | OpenClaw cron → felix-admin-escalation | claude | Overdue task escalation via WhatsApp |
| Doc Audit Poll | ⏸ Suspended 2026-05-26 (was: every 60 min top of hour UTC) | `felix-doc-auditor.timer` (systemd, currently **disabled**) → `/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py` (#343 scripts-first driver) | claude | Process Doc Audit / Weekly Doc Audit issues — **paused indefinitely** pending #137 cost-control work |
| Second Brain Sync | Every 15 min | `second-brain-sync.timer` (systemd) | kgale | Bidirectional git sync for non-vault content |
| Felix Core Digest | Every 15 min | `felix-core-digest.timer` (systemd, two chained ExecStart post-#490) | claude | Agent activity log summarization → Obsidian digests + deterministic OpenClaw-log signal extraction → GitHub issues via kg-felix-bot (#490) |
| Felix Heartbeat Gate | Every 30 min (OnUnitActiveSec=30min, OnBootSec=5min) | `felix-heartbeat-gate.timer` (systemd, #490) → `/usr/bin/python3 /home/claude/repos/kg-automation/scripts/openclaw/heartbeat_gate/run.py` | claude | Routes each OpenClaw heartbeat tick via a **deterministic stdlib rule** (no LLM call, post-#676); only escalates to Sonnet 4.6 on novel signal / contract task / fallback. Replaces OpenClaw's internal heartbeat. (#490; determinized by #676) |
| Felix Health Check | Twice daily 11:00 + 23:00 local | `felix-health-check.timer` (systemd, #676) → `python3 -m scripts.office2.felix_health_check.run` | claude | Runs the existing bash health check off the Sonnet `main` agent (zero `main` sessions per run); ntfy alert on failure. Replaces the openclaw crons `health-check-morning` / `health-check-evening`. (#676) |
| Felix Habit Sweeper | 7:30 AM ET daily (`OnCalendar=*-*-* 07:30 America/New_York`) | `felix-habit-sweeper.timer` (systemd, #408) → `/usr/bin/python3 /home/claude/kg-automation/scripts/habits/sweeper.py` | claude | Daily 48hr auto-skip pass for habit check-ins — marks unresolved habits as `auto_skipped` and advances day-specific habit `due_date` to the next designated weekday EOD-ET. Deterministic, zero LLM calls. (#408) |
| Agent Prompt Sync | Every 5 min after last tick (`OnUnitInactiveSec=300s`) | `agent-prompt-sync.timer` (systemd, #567) → `/usr/bin/python3 -m scripts.openclaw.deploy.deploy_agent_prompts` | claude | Pull-based deploy pipeline. Each tick `git pull --ff-only` then MD5-compare + atomic-copy any drifted agent prompt file from repo into `/data/services/openclaw/<deploy-dir>/`. Slug → deploy-dir mapping is NOT 1:1 (see Agent Prompt Deploy Pipeline section below). Deterministic, zero LLM calls. (#567) |
| Felix-Deployer | Every 5 min (`felix-deployer.timer`, systemd-user, #136) | `/usr/bin/python3 scripts/deploy/felix-deployer/deployer.py` (Type=oneshot) | claude | Pull-based deploy applier. Each tick `git pull` then scans `deploys/queued/*.yaml`, applies each via `scripts/deploy/lib/`, dispatches **ntfy.sh push notification on failure** (substrate set by #595, replaces broken openclaw-cron WhatsApp DM path). Reads `FELIX_DEPLOYER_NTFY_TOPIC` from `EnvironmentFile=-/home/claude/.config/felix-deployer/env` (non-fatal if missing). Outbound dep: `ntfy.sh:443/tcp`. Runbook: [`deploy/discipline.md`](../runbooks/deploy/discipline.md). |
| Felix Trust Scan | Every 15 min (`OnBootSec=5min`, `OnUnitActiveSec=15min`, `Persistent=true`) | `felix-trust-scan.timer` (systemd, #683) → `python3 -m scripts.trust.run_trust_scan --json` | claude | Detection half of the Felix Truthful Reporting Guardrails: cron-drift detection (live OpenClaw crons vs the committed approved-cron baseline — agent-independent, load-bearing) + completion-assertion verification (asserted artifact ids checked against their owning system). Alerts via the #701 `felix-alert` bus. Fail-safe: timer mode always exits 0. (#683) |

## Agent Prompt Deploy Pipeline (#567)

**Purpose**: Automate the sync of Felix agent prompt files (`AGENTS.md`,
`IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`) from the
`kg-automation` repo on office2 (`/home/claude/kg-automation`) into the
deployed openclaw workspace directories under `/data/services/openclaw/`.
Closes the deploy gap exposed by #563 (truncated prompts surfacing as silent
content loss) and unsticks stranded changes from #558 + #561.

**Architecture** (pull-based; see [agent-prompt-sync-ops.md](../runbooks/agent-prompt-sync-ops.md)):

1. User-level systemd timer (`agent-prompt-sync.timer`) fires every 5 minutes
   after the previous tick exits (`OnUnitInactiveSec=300s`)
2. The service unit runs `python3 -m scripts.openclaw.deploy.deploy_agent_prompts`
   inside `/home/claude/kg-automation`
3. The helper: (a) `git fetch && git pull --ff-only origin main`,
   (b) reads `service-inventory.json` to discover Felix agents,
   (c) MD5-compares each in-scope file in `<source_in_repo>` against the file
   at `<workspace>/<filename>`, (d) atomically copies any drifted file
   (preserving destination mode), (e) appends structured records to
   `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`

**Slug → deploy-dir mapping** (NOT 1:1; sourced from `service-inventory.json`
`services[openclaw].agents.<slug>.workspace`):

| Agent slug | Deploy directory |
|------------|------------------|
| `felix-admin-capture` | `/data/services/openclaw/inbox-agent/` |
| `felix-admin-habits` | `/data/services/openclaw/habits-agent/` |
| `felix-admin-escalation` | `/data/services/openclaw/escalation-agent/` |
| `felix-admin-tasker` | `/data/services/openclaw/tasker-agent/` |
| `felix-admin-calendar` | `/data/services/openclaw/calendar-agent/` |
| `main` | `/data/services/openclaw/data/` |

**Files synced** (in-scope filename allowlist):

- `AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`

**Files excluded** (would-be candidates the helper deliberately ignores):

- `HEARTBEAT.md` (deployed-side runtime state owned by openclaw's heartbeat process)
- `*.tmpl` (templates — used to seed new agents, not deployed)
- `*.bak*` (backups left by past mission migrations)
- `GOVERNANCE.md` (manually maintained on the `main` agent only; no repo source)

**Operator surface**: see [`docs/runbooks/agent-prompt-sync-ops.md`](../runbooks/agent-prompt-sync-ops.md)
for the install procedure, dry-run, single-agent force-sync, troubleshooting,
and rollback paths.

**Behavior on prompt change**: agents read their workspace files at openclaw
session-init only (no hot-reload). A new prompt deployed at 09:32 reaches a
felix-admin-capture cron tick at 12:00 ET (the next scheduled invocation).
The helper does NOT trigger an openclaw restart — that is intentional per
spec FR-017.

## Deployment Details

### Vikunja (F001; compose pattern via #189)
- **Deployed by**: F001; migrated to docker-compose pattern via #189 (2026-05-12)
- **Public URL**: `https://office2.tail0f5f56.ts.net`
- **TLS**: Tailscale Serve (auto-provisioned Let's Encrypt certs, auto-renewed)
- **systemd unit**: `vikunja.service` (system-level, runs as claude user, `Type=oneshot` + `RemainAfterExit=yes`)
- **ExecStart**: `/usr/bin/docker compose -f /home/claude/kg-automation/services/vikunja/docker-compose.yml up -d`
- **Restart policy**: `restart: unless-stopped` declared in the compose file (Docker handles container restarts, including across daemon restarts — survives the `StartLimitBurst=5` failure mode that bit the legacy pattern during the docker.io→docker-ce migration in #80)
- **Compose source**: `services/vikunja/docker-compose.yml` (in-repo source-of-truth; deployed via `git pull` on office2)
- **Config in repo**: `scripts/vikunja/deploy.sh` (idempotent deploy with legacy-unit backup at `/data/services/vikunja/.deploy-backups/`), `scripts/vikunja/vikunja.service`
- **Setup script**: `scripts/vikunja/setup_vikunja.py` (projects, labels, filters)
- **Bind IP**: `100.92.197.90` (Tailscale IP only — corrected from the stale `0.0.0.0` listing prior to #189; the actual binding has been Tailscale-only since the early port-binding fix)
- **Data owner**: uid 1000:gid 0 (matches container runtime user)
- **Backup**: Automatically included (under `/data/services/`)
- **Runbook**: `docs/runbooks/vikunja-ops.md`
- **F006 additions**: Goals project (top-level, id=11) for structured goal declarations, `metalcasework` label (#ff9800), Goals saved filter. Setup script: `scripts/vikunja/setup_goals.py`. Goals runbook: `docs/runbooks/goals-ops.md`

### Obsidian Sync (pre-F001, updated F011, system-level confirmed #202)
- **Deployed by**: Manual setup, updated by F011
- **Binary**: `/usr/bin/ob` (v0.0.10 as of 2026-06-06; upgraded from v0.0.8 during #540 recovery for upstream JSON-parse fix)
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
- **Known failure mode — process-alive-not-syncing** (occurred 2026-04-07 and 2026-06-06): the systemd unit reports `active (running)` and the process is alive, but no notes actually round-trip. Confirmed twice; 2026-06-06 root cause was a JSON parse bug in `ob` 0.0.8 (server returns non-2xx, client crashes silently into broken state, process keeps running). Detection via heartbeat staleness on other devices + empty `01-Inbox/` despite known captures + prescan reporting `unprocessed=0`. **`active (running)` is not a sufficient health signal for this service** — it satisfies Engineering Principle 1 (Runtime Truth Must Have a Machine-Readable State) only at the process level, not at the sync-round-trip level. Recovery + diagnostic procedure documented at [`docs/runbooks/obsidian-sync-ops.md` § Silent Sync Failure](<../../runbooks/obsidian-sync-ops.md>). Candidate consumer of the lifecycle-state contract being designed under [#516](https://github.com/kentonium3/kg-automation/issues/516) (Felix-wide observability framework / Epic C).

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
- **Installation**: `npm install -g openclaw@2026.6.11` (global, requires sudo)
- **Binary**: `/usr/bin/openclaw`
- **Config**: `/home/claude/.openclaw/openclaw.json`
- **Service level**: User-level systemd with lingering (not system-level)
- **Config in repo**: `scripts/openclaw/openclaw-gateway.service`, `scripts/openclaw/install.sh`
- **PYTHONPATH drop-in** (`scripts/openclaw/openclaw-gateway.service.d/pythonpath.conf`, introduced by #656): Sets `Environment=PYTHONPATH=/home/claude/kg-automation` in a systemd drop-in at `~/.config/systemd/user/openclaw-gateway.service.d/pythonpath.conf`, on the openclaw-gateway **process** environment. **Correction (harden-inbox-capture-01KWVGZM #662, verified #658):** this does *not* let agent helpers run as a bare `python3 -m scripts.…` from any cwd — OpenClaw's `exec` tool **strips PYTHONPATH from the subshells it spawns**, so the inherited gateway PYTHONPATH is invisible to helpers launched via `exec`. Agent prompts must therefore use the self-contained `cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod> …` form (the leading `cd` makes cwd the checkout root so `scripts.*` imports resolve regardless of env); the invariant is deterministic only because of that explicit `cd`, not because of the process-env PYTHONPATH. The drop-in still usefully sets the process env for non-`exec` import paths. Drop-in composes with the base unit; avoids source-line collision with #653's in-flight `ExecStart` relocation. Deployed via `deploys/queued/0006-gateway-pythonpath-dropin.yaml`. **Audited surface** (systemd-user-dropins.txt baseline): merge commit must carry `Rebaseline: completed at <ts>`.
- **Credential store**: `/data/services/openclaw/secrets/` (mode 700)
- **Backup**: Data at `/data/services/openclaw/data/` and config at `/home/claude/.openclaw/` — both in Restic scope
- **Model tiering**: Global default is Haiku; per-agent model override via `agents.list[].model` in `openclaw.json`. See agent registry for per-agent assignments.
- **Exec posture (Foundation-0 finding, #675)**: every agent scope runs `security: full` (`openclaw exec-policy show` confirms `ask=off`, approvals file missing) — **no per-agent exec allowlist or containment is deployed**. This is recorded as a finding, not a claimed restriction. `gog` ownership post-#699: `main` is the **only** current gog consumer (Gmail + Drive; no worker — including `felix-admin-calendar` — uses gog), retained as the tracked exception until email/drive get controlled owners (#680).
- **Session scoping (`v2026.5.28+`)**: Sessions are keyed per channel + peer phone-number using the `agent:<agent_id>:<channel>:<scope>:<peer>` format (e.g., `agent:main:whatsapp:direct:+16179300916`). This per-channel-peer scoping is what makes a DM thread its own session — separate from group-chat sessions and from cron-driven announce-mode invocations. See also the [`whatsapp-dm-reply`](<./data-flows.md>) data flow for the full runtime path.
- **Main agent standing orders**: `/data/services/openclaw/data/AGENTS.md` governs the **main** agent's routing of inbound channel messages to the `felix-admin-*` sub-agents. Per #374 (`main-verbatim-passthrough-01KSATRP`), the main agent must pass downstream messages to sub-agents **verbatim** (no paraphrase, no summary, no editorial). Sessions cache the system prompt for their lifetime — AGENTS.md changes only load on the next-started session. Force-rotating active sessions after a deploy is the 5-step cutover sequence in [openclaw-agent-setup.md](<../../runbooks/openclaw-agent-setup.md>) §"Cutover sequence for main-agent AGENTS.md changes (post-#374)"; step 4 invokes `scripts/openclaw/helpers/rotate_main_session.py`.
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

### Google Workspace via `gog` CLI (#100, 2026-05-13)
- **Deployed by**: #100 / mission `google-workspace-foundation-01KRH4PE` (ADR-0001)
- **Type**: CLI integration — on-demand binary shelled out to by Felix agents; not a long-running service.
- **Binary**: `/home/linuxbrew/.linuxbrew/bin/gog` (Linuxbrew tap `steipete/tap/gogcli`)
- **OAuth model**: `gog auth credentials` + `gog auth add <email> --remote` two-step flow. Refresh tokens stored in gog's encrypted keyring at `/home/claude/.config/gogcli/credentials.json` (file backend, encrypted via `GOG_KEYRING_PASSWORD`).
- **APIs covered**: Gmail, Drive, Contacts (People API), Sheets, Docs. (Originally all six including Calendar, validated end-to-end 2026-05-13; the **Calendar** surface **migrated off gog** to the Felix calendar helper by #699 (RFC #681 phase) — see the *Felix Calendar Helper* section below. gog is not retired.)
- **Active accounts**: `kentgale@gmail.com` (personal). `kent@intentional.biz` planned (separate OAuth client; see `identity-model.md`).
- **Skill**: bundled `gog` skill at `/usr/lib/node_modules/openclaw/skills/gog/SKILL.md` (OpenClaw-discoverable).
- **Secrets**: `/data/services/openclaw/secrets/google-workspace-client.json` (OAuth client_secret, mode 600), `/data/services/openclaw/secrets/gog-keyring-password` (keyring passphrase, mode 600). See `credentials-and-secrets.md`.
- **Risk tier**: 3 (logic/workflow — no long-running service or fabric component).
- **Consumers**: any Felix agent. Centralized integration; agents do not embed OAuth clients of their own.
- **Runbook**: [`docs/runbooks/google-workspace-ops.md`](<../../runbooks/google-workspace-ops.md>) — full setup procedure, pitfalls, common commands, troubleshooting, and second-account expansion.
- **Supersedes**: the legacy direct-OAuth path under `scripts/google/authorize-calendar.py` (now archived at `docs/archive/scripts/authorize-calendar.py`) and the `personal-google` credential entry (now deprecated; superseded by the gog-managed credential set).

### Felix Admin Capture Agent (F008)
- **Deployed by**: F008
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-capture`
- **Workspace**: `/data/services/openclaw/inbox-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-capture/`
- **Model**: `anthropic/claude-haiku-4-5` (evaluating) — held on haiku as the static baseline. #662's reliability fix was ENVIRONMENTAL (OpenClaw's exec tool strips PYTHONPATH; fixed fleet-wide by self-contained `cd /home/claude/kg-automation && python3 -m scripts.…` invocations, corrects #658), NOT a model deficit — haiku's "missing infrastructure" output was a downstream misread of the resulting ModuleNotFoundError. A sonnet upgrade was briefly deployed 2026-07-06 then reverted the same day; whether haiku suffices for the capture reasoning task is under ~1-week evaluation (#671).
- **Skills**: vikunja_api, github
- **Purpose**: Autonomous Obsidian inbox processing — classifies content, routes to vault locations, creates Vikunja tasks, writes processing logs
- **Schedule**: 4x daily via OpenClaw cron (7 AM, 12 PM, 5 PM, 10 PM ET)
- **Processing logs**: `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
- **Vikunja projects used**: Inbox (tasks), Research (research requests), Goals (goal declarations)
- **Privacy boundary**: `04-Growth/_private/` is never accessed
- **Runbook**: `docs/runbooks/inbox-ops.md`
- **Updated by**: `harden-inbox-capture-01KWVGZM` (#662, 2026-07-06) — self-contained helper invocations fleet-wide (corrects the #656/#658 env-assumption failure); capture held on haiku (model choice under evaluation, #671). `#256-scope-discipline-guardrails` (2026-05-13) — adds explicit "no unsanctioned reads/edits" prose to AGENTS.md Step 5a + Step 6 after T011 SC-003 verification of #253 surfaced haiku making unsanctioned `edit` attempts on parse_failure notes. `#253-step-5a-6-consolidation` (2026-05-13) — collapses AGENTS.md Step 5a and Step 6 into single-call orchestrator helpers (`handle_marker_cleanup.py`, `handle_parse_failures.py`); applies the deterministic-work-into-scripts principle. `#254-atomic-write-perm-preservation` (2026-05-13) — fixes `_atomic_write` in both marker scripts to preserve target mode (and default new files to `0o664`) so cross-user access by ob (Obsidian Sync daemon, runs as kgale) is not broken by claude-orphaned `0o600` files. `#185-inbox-capture-dedup` (2026-05-12) — adds routing-log dedup + parse-failure halt-and-surface. Previously: `027-inbox-pre-scan-helper` (2026-04-11).

#### State files

- **Routing log** (`/data/services/openclaw/state/inbox-routing.jsonl`, introduced by #185, relocated from `~/second-brain/agents/state/` by #656) — Append-only JSONL. Each line records one successful route: `{filename, issue_number, vikunja_task_id, routed_at, note_excerpt}`. The classifier in prescan.py consults this log on every cron tick and filters already-routed filenames out of `unprocessed_paths` invisibly to the agent. This is the load-bearing dedup substrate; it decouples dedup from frontmatter parseability (which was the failure mode in the original #185 bug where a malformed note got filed nine times). NOT git-tracked; backed up by the nightly Restic job. Owner `claude:secondbrain`, dir mode 0750, file mode 0640.

#### Parse-failure surface (#185)

Notes with malformed frontmatter (BOM, leading-content-before-fence, missing closing fence, invalid YAML) are now classified as `parse_failure` rather than silently routed as `unprocessed`. The agent's response:

- Halts routing for the affected note (so it is not mis-routed as a generic content issue).
- Files (or dedupes against) a batched GitHub issue with title prefix `Inbox quality:`. Existing open issues are reused; bodies are not rewritten.
- Injects an Obsidian `> [!error] felix-capture:` callout marker at the top of each affected note pointing at the issue. The marker is idempotent — re-runs refresh the existing marker rather than stacking duplicates.
- When the user fixes the malformation, the next cron tick auto-strips the marker as part of normal routing.

Operator workflow: see `docs/runbooks/inbox-ops.md` §"When you see an 'Inbox quality' issue".

#### Components

- **inbox-prescan-helper** (Python script, `scripts/inbox/prescan.py`) — Introduced by mission `027-inbox-pre-scan-helper` (issue #149); extended by #185 to add parse-failure classification and routing-log dedup filtering. Deployed to `/home/claude/kg-automation/scripts/inbox/prescan.py` on office2. The agent's Step 1 runs this helper before any cognitive work, implementing a pre-scan-then-act pattern. The helper:
  1. Resolves `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}` via the vault path registry (`scripts/vault/paths.json`)
  2. Lists files in the inbox with `status: unprocessed`
  3. Detects malformed frontmatter (BOM, leading content, missing close fence, invalid YAML) and emits them as `parse_failures` (NOT in `unprocessed_paths`)
  4. Consults the routing log (`scripts/inbox/routing_log.py` → `/data/services/openclaw/state/inbox-routing.jsonl`) and filters already-routed filenames out of `unprocessed_paths`; surfaces those in `dedup_skipped`
  5. Flags any cleanly-parseable note that still carries a stale `> [!error] felix-capture:` marker in `marker_cleanup_needed`
  6. Archives stale (>7 day) processed files to `{{VAULT_INBOX_PROCESSED}}`
  7. Returns a JSON result with unprocessed paths, parse_failures, dedup_skipped, marker_cleanup_needed, archived entries, and warnings

  When the helper reports zero unprocessed files, zero parse failures, and zero markers to clean up, the agent replies with the byte string `[felix-admin-capture]: IDLE` and takes no further action. (Per kentonium3/kg-automation#592, the same `[<agent-slug>]: IDLE` pattern applies across the four IDLE-emitting Felix sub-agents: `felix-admin-capture`, `felix-admin-habits`, `felix-admin-tasker`, `felix-admin-escalation`.)

  - **Language**: Python
  - **Dependencies**: `scripts/vault/paths.json`, `scripts/inbox/routing_log.py`
  - **Invoked by**: `felix-admin-capture` step 1
  - **Helper log**: `/home/kgale/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md` (daily rotation, append-only; relocated from `/home/claude/second-brain/agents/logs/` by #656)

- **routing-log module** (`scripts/inbox/routing_log.py`, introduced by #185, updated by #656) — Stdlib-only Python module exposing `RoutingLogReader` and `RoutingLogWriter` for the dedup substrate at `/data/services/openclaw/state/inbox-routing.jsonl`. Read path is used by prescan.py; write path is wrapped by `append_routing_entry.py`. Atomic appends; reader caches per-tick. `DEFAULT_ROUTING_LOG_PATH` relocated from `~/second-brain/agents/state/` by #656.

- **handle_parse_failures.py** (script, #253) — End-to-end orchestrator for parse-failure handling. Invoked by AGENTS.md §Step 6 as a single CLI call when `parse_failures` is non-empty. Reads prescan JSON (`@<path>` argument); files-or-dedups the inbox-quality GitHub issue via direct function import of `file_inbox_quality_issue.{find_existing_open_issue,file_new_issue}`; then injects parse-error markers per entry via direct function import of `inject_parse_error_marker.inject_marker`. Subprocess-out to `log_action.py` for structured action-log entries (`inbox_quality_issue_filed`/`_deduped`, `parse_error_marker_injected`, `parse_failure_handling_error`). Exits non-zero on any per-entry failure (continues processing the rest). Replaces the prior multi-step bash recipe to collapse the prompt-execution surface.

- **handle_marker_cleanup.py** (script, #253) — End-to-end orchestrator for marker-cleanup. Invoked by AGENTS.md §Step 5a as a single CLI call when `marker_cleanup_needed` is non-empty. Reads prescan JSON; strips markers via direct function import of `strip_parse_error_marker.strip_marker`. Logs `marker_stripped` per success and `marker_cleanup_error` per failure via `log_action.py` subprocess.

- **inject_parse_error_marker.py** (script, #185 → #253 → #254) — Library + thin-CLI module exposing `inject_marker(path, issue_number, date_str)`. Inserts/refreshes the marker after the frontmatter close fence (or at line 0 for no-frontmatter notes). Idempotent + atomic. As of #253, invoked indirectly via `handle_parse_failures.py`'s direct function import rather than via the AGENTS.md prompt's bash. As of #254, `_atomic_write` preserves the original target file's mode (or applies `0o664` for new files) so cross-user access by ob (kgale-owned daemon, member of `secondbrain` group) is not broken by claude-orphaned `0o600` perms. Emits one stderr `INFO: atomic_write <path> mode=0o<mode> (preserved|new)` log line per successful write.

- **strip_parse_error_marker.py** (script, #185 → #253 → #254) — Library + thin-CLI module exposing `strip_marker(path)`. Removes the marker (and its trailing blank line) when the note now parses cleanly. No-op if no marker present. As of #253, invoked indirectly via `handle_marker_cleanup.py`'s direct function import. As of #254, `_atomic_write` preserves mode identically to `inject_parse_error_marker.py`.

- **append_routing_entry.py** (script, #185) — CLI wrapper around `RoutingLogWriter.append`. Invoked by AGENTS.md §Step 5b exactly once per fully-routed note (after all blocks have been routed, before the atomic `status: processed` write).

- **file_inbox_quality_issue.py** (script, #185 → #253) — Title-prefix-deduped GitHub issue writer. Exposes library functions `find_existing_open_issue()`, `file_new_issue(parse_failures, date_str)`, `build_title()`, `build_body()` alongside its thin `main()` CLI wrapper. As of #253, invoked indirectly via `handle_parse_failures.py`'s direct function imports rather than via the AGENTS.md prompt's bash. Uses `gh issue list --search 'in:title "Inbox quality:"'` + a `startswith()` post-filter to find an existing open issue; if found, returns the existing number without filing. If not, files a new issue against `kentonium3/kg-automation` with title `Inbox quality: <N> notes with parse errors — YYYY-MM-DD`. Body is truncated with an overflow footer if it would exceed the 60K-char safety budget.

- **mark_processed.py** (script, #566 → #325) — Atomic in-place finalize helper. Invoked by AGENTS.md §Step 5c: `python3 -m scripts.inbox.mark_processed --path <path>`. Sets `status: processed` + `processed_at` atomically; note stays at its `01-Inbox/` path (never moved). As of mission `finalize-inbox-file-01KW8MSQ` (#325): exit contract is **0/1/2/3** (0 success/idempotent · 1 validation failure · 2 filesystem error · 3 private-path refusal); on success emits a single-line JSON object on stdout for machine-confirmable finalize; validates `--path` is under the inbox root (from `scripts/vault/paths.json`). Write failures (previously uncaught tracebacks) now surface as exit 2 with the OSError detail on stderr; the original note is guaranteed uncorrupted. Authoritative record: `data/service-inventory.json` → `services[openclaw].agents.felix-admin-capture.components[mark-processed]`.

### Felix Admin Habits Agent (F009; scripts-first morning + reply flow #371; scripts-first weekly report via vikunja-client-and-habits-weekly-report-01KTKSFT #542 + #562)
- **Deployed by**: F009
- **Refactored by**: `#371` / mission `habits-checkin-reply-scripts-first-01KS86ZQ` (morning + reply ports to scripts-first; mirrors #309 escalation pattern); `vikunja-client-and-habits-weekly-report-01KTKSFT` (#542 foundation + #562 umbrella + #561 co-shipped output discipline) — weekly report ported to a deterministic helper backed by a new shared Vikunja client; co-shipped output-discipline Hard Rules mirror felix-admin-capture's standing-orders pattern
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-habits`
- **Workspace**: `/data/services/openclaw/habits-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-habits/`
- **Model**: `anthropic/claude-haiku-4-5`
- **Skills**: vikunja_api
- **Purpose**: Daily habit check-in delivery, completion tracking, weekly pattern reports, on-demand track record queries, habit management (add/pause/remove). **Post-#371**: thin orchestrator for the morning + reply ticks. The morning tick invokes `scripts/habits/morning_checkin_list.py` (script writes the canonical morning-list artifact + emits the formatted WhatsApp message verbatim); the reply tick invokes `scripts/habits/parse_morning_reply.py` (deterministic mapping of Kent's reply against the persisted morning list) and routes the resulting `(task_id, state)` tuples to the existing `scripts/habits/record_completion.py`. The narrow LLM judgment surface `scripts/habits/judgment/disambiguate_reply.py` is invoked ONLY for ambiguous reply tokens (mirrors the #343 doc-audit judgment pattern). **Post mission `trustworthy-weekly-habit-report-01KV4GZ7` (#605)**: the weekly Monday-06:00 tick is a thin orchestrator — the agent invokes `scripts/habits/query_active_habits_weekly.py --output text` which reads completion history from the canonical `habits-history.jsonl` via `scripts/habits/history.py` (built on `scripts/common/state_log.py`) and queries Vikunja project-13 only for current-state habit metadata (titles + `repeat_after` for classification, via `scripts/common/vikunja_client.py`); it emits the pre-rendered WhatsApp message body on stdout, which the agent posts verbatim. Vikunja `done_at` is NOT read for history because `repeat_after` recurrence resets that field on each cycle (collapsing daily-habit history to 0% — the original #605 bug). The earlier deterministic-helper introduction (mission `vikunja-client-and-habits-weekly-report-01KTKSFT` #542 + #562) replaced the pre-existing LLM-improvised path; this mission corrected the read source and moved the cron to Monday so the report fires after the week has closed.
- **Schedule**: Morning check-in at 7:05 AM ET daily; weekly report Monday 6 AM ET (cron `0 6 * * 1` America/New_York, post mission `trustworthy-weekly-habit-report-01KV4GZ7` #605; previously Sunday 22:00 ET per #542 + #562)
- **Vikunja project**: Habits (id=13) with 7 habit tasks (ids 14-20)
- **Canonical completion storage**: JSONL state log at `/data/services/openclaw/state/habits-history.jsonl` (Phase 3 #306, cutover #308). `[Felix]` comments on each habit task are written by `record_completion.py` as a Vikunja UI mirror only.
- **Morning-list artifact (post-#371)**: `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json` — per-Kent-day canonical ordering used by the reply parser (data-model Entity 1)
- **WhatsApp delivery**: Cron jobs use `--to` for direct delivery; completion marking via main agent delegation
- **Privacy boundary**: `04-Growth/_private/` is never accessed
- **Runbook**: `docs/runbooks/habits-ops.md`

#### State files (post-#371)

- **Per-date morning-list artifact** (`/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`, introduced by #371) — One file per Kent-day. Schema per data-model Entity 1: `{schema_version, date, generated_at, habits:[{position, vikunja_task_id, title}]}`. Written by `morning_checkin_list.py` at the morning cron tick; read by `parse_morning_reply.py` at reply time. Authoritative ordering for the reply tick — the parser NEVER re-queries Vikunja, so positions in Kent's reply align with what he actually saw. ~1 KB per file at N=8-12 habits (NFR-005); no rotation (~365 files/year). Backed up by the nightly Restic job.
- **Habits history JSONL** (`/data/services/openclaw/state/habits-history.jsonl`) — Unchanged from #306/#307/#308. Canonical per-domain completion log; the new helpers consume it via the existing Phase 3 `exclude_completed_v2.py` filter.

#### Helpers (post-#371)

Per-helper metadata mirrors `docs/design/architecture/data/service-inventory.json` (the authoritative record) — see the corresponding `config_files[*]` entries on the `habit-checkin` cron for `runs_on`, `invoked_by`, `writes_to`, `reads_from`, `credentials`, and `updated_by` fields.

- **scripts/habits/morning_checkin_list.py** (script, introduced_by #371, updated_by #371) — Sole source of the ordered habit list. Reads active habits from Vikunja (project-scoped via `query_active_habits_v2.py`), excludes habits already addressed today (via `exclude_completed_v2.py` reading the JSONL state log), and writes `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json` atomically (tmp+fsync+rename). Emits the formatted WhatsApp check-in message to stdout — the agent relays this verbatim with NO commentary or re-ordering. Implements FR-001, FR-002, FR-007.
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-habits` agent (cron `habits-morning-checkin`)
  - **writes_to**: `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`
  - **reads_from**: Vikunja API (`GET /projects/<id>/tasks` via `query_active_habits_v2.py`); habits JSONL state log (via `exclude_completed_v2.py`)
  - **credentials**: `vikunja-api`
- **scripts/habits/parse_morning_reply.py** (script, introduced_by #371, updated_by #371) — Deterministic reply parser. Loads the persisted morning-list artifact for the date, tokenizes Kent's reply, and emits canonical `{tuples, judgment_required, errors}` JSON per data-model Entity 2. Supports number references (single + comma-separated), exact title matches (case-insensitive), simple substring matches that uniquely identify one habit, and special `"all done"` family tokens. Ambiguous substring matches emit `judgment_required` records (NOT silently picked). Implements FR-003, FR-004, FR-005, FR-008. Exit code 4 when no morning-list artifact exists for the date — agent files a P2-bug via `felix-file-issue.py` rather than falling back to live Vikunja state (FR-009).
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-habits` agent (reply tick)
  - **writes_to**: (none — caller routes the tuples to `record_completion.py`)
  - **reads_from**: `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`
  - **credentials**: (none — does not call Vikunja)
- **scripts/habits/judgment/disambiguate_reply.py** (script + library, introduced_by #371, updated_by #371) — Narrow LLM judgment surface. Invoked ONLY when the deterministic parser emits `judgment_required` (FR-006). Mirrors the #343 doc-audit judgment pattern: the LLM is never in the path for the bulk of replies, only for ambiguous reply tokens (e.g., `"PT done"` when the morning list has multiple PT habits). Reads `/data/services/openclaw/secrets/anthropic` at invocation, calls `api.anthropic.com` directly via the anthropic-python SDK with `claude-haiku-4-5`, and returns either `{result: chosen, chosen_task_id}` from the candidate set or `{result: clarify, suggested_question}` for the agent to ask Kent. Validates chosen_task_id is within the input's candidate set (out-of-set responses are a hard-fail, exit code 5).
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-habits` agent (reply tick, only when parser emits `judgment_required`)
  - **writes_to**: (none)
  - **reads_from**: `/data/services/openclaw/secrets/anthropic`; `api.anthropic.com` (HTTPS)
  - **credentials**: `anthropic-api`

#### Weekly-report helpers (post mission `vikunja-client-and-habits-weekly-report-01KTKSFT`)

Per-helper metadata mirrors `docs/design/architecture/data/service-inventory.json` (the authoritative record) — see the corresponding `config_files[*]` entries on the `habit-checkin` cron.

- **scripts/habits/query_active_habits_weekly.py** (script, introduced_by `vikunja-client-and-habits-weekly-report-01KTKSFT`, read path corrected by `trustworthy-weekly-habit-report-01KV4GZ7` #605) — Sole source of the weekly Monday-06:00 habit-pattern report. Reads completion history from the canonical `/data/services/openclaw/state/habits-history.jsonl` via `scripts/habits/history.py` (which sits on `scripts/common/state_log.py`); queries Vikunja project 13 (`Habits`) only for current-state habit metadata (titles + `repeat_after`) via the shared `scripts/common/vikunja_client.VikunjaClient`. Rolls up by canonical habit title — daily-cadence habits (`repeat_after == 86400`) and weekday-in-title habits (e.g., `Strength training — Monday`) are classified per the `HabitClassifier` rules and counted against per-kind scheduled-days math (7 for daily, 1 per matched-weekday occurrence for weekday-in-title). Non-habit project-13 tasks (e.g., one-off cardiac-task class with `repeat_after == 0` and no weekday in title) are filtered at the helper layer per FR-006. Emits a `WeeklyHabitReport` JSON on stdout (additive `rendered_text` field per FR-005) or, with `--output text`, just the pre-rendered WhatsApp message body; the agent posts the text verbatim, no in-prompt rendering. Vikunja `done_at` is NOT read for history (the #605 bug class). Standard library only beyond the shared client + state-log primitive. Failure mode: typed `VikunjaError` exceptions propagate; agent emits `Weekly report unavailable: <reason>` rather than fabricating data.
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-habits` agent (cron `habits-weekly-report`, `0 6 * * 1` America/New_York)
  - **writes_to**: (none — stdout JSON only; agent renders to WhatsApp)
  - **reads_from**: Vikunja API via `scripts/common/vikunja_client.py` (`GET /projects/13/tasks?filter=done=true` with `done_at` date-range refinement)
  - **credentials**: `vikunja-api`
- **scripts/common/vikunja_client.py** (shared library, introduced_by mission `vikunja-client-and-habits-weekly-report-01KTKSFT` foundation #542) — Stateless shared client for direct Vikunja API consumers. Centralizes base URL composition (via `scripts/common/vikunja_config.get_vikunja_base_url()` with trailing-slash normalization), token loading from `/data/services/openclaw/secrets/vikunja-api`, `urllib.request`-backed HTTP execution, 30s default per-request timeout, and a typed exception hierarchy (`VikunjaError` -> `VikunjaAuthError`, `VikunjaNotFoundError`, `VikunjaBadRequestError`, `VikunjaServerError`, `VikunjaTimeoutError`, `VikunjaHttpError`). Errors are redaction-safe by default (exception messages include the request path but NOT request body or response body). No global state — instantiating two clients in the same process is isolated. Standard library only. Architectural note: `service-inventory.json` does not model shared libraries as first-class service entries; this module is registered under the `habit-checkin` cron's `config_files[*]` array as the first consuming service. Future migrations (`scripts/sync/`, `scripts/habits/`, `scripts/escalation/`, etc.) will reference this module from their own service entries as they cut over.
  - **runs_on**: `office2`
  - **invoked_by**: `scripts/habits/query_active_habits_weekly.py` (first and only consumer in this mission; future migrations will add consumers across scripts/sync/, scripts/habits/, scripts/escalation/, scripts/enrichment/ per #542's deferred follow-up issue)
  - **writes_to**: Vikunja API (per consumer demand — read-only against Vikunja in this mission's only consumer)
  - **reads_from**: `/data/services/openclaw/secrets/vikunja-api`; Vikunja API
  - **credentials**: `vikunja-api`

### Felix Admin Tasker Agent (F013; JSONL state migration #310)
- **Deployed by**: F013
- **Refactored by**: `#310` / mission `tasker-jsonl-migration-01KSB5XV` (Phase 7 of ADR-0002 — final phase)
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-tasker`
- **Workspace**: `/data/services/openclaw/tasker-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-tasker/`
- **Model**: `anthropic/claude-haiku-4-5`
- **Purpose**: Task intelligence — transforms raw tasks into structured Vikunja entries. **Post-#310**: enrichment state migration complete. AGENTS.md cut from 19,391 to ~13,800 chars; canonical state lives in the JSONL ledger at `/data/services/openclaw/state/enrichment/enrichment-history.jsonl`; `[Felix] enrichment` Vikunja comments are written through during the post-cutover soak (C-002) for rollback safety but are NO LONGER the source of truth — `derive_state` reads ONLY the JSONL. The agent delegates state transitions to `scripts/enrichment/record_completion.py` rather than writing comments directly.
- **Skills**: task_intelligence, vikunja_api
- **Autonomy**: Assisted (Level 1)
- **Trigger**: Delegation (from felix-admin-capture for `enrich_task`), manual (`retroactive_enrichment`, `detect_incomplete`). **Not cron-driven** — the previously-listed `task-detection` cron (every 4h UTC) was unverified drift (no matching `openclaw cron list` entry on office2) — removed by #310. C-006 in the mission spec confirms tasker is delegation-driven only.
- **Privacy boundary**: `04-Growth/_private/` is never accessed (path renumbered from `02-Growth/_private/` in mission 026 / #152)

#### State files (post-#310)

- **Enrichment history JSONL** (`/data/services/openclaw/state/enrichment/enrichment-history.jsonl`, introduced by #310) — Append-only JSONL. One record per enrichment state event. Schema (data-model E1): `EnrichmentCompletion(task_id, state, timestamp_utc, source[, note], schema_version=1)`. `VALID_STATES = {proposed, confirmed, skipped, declined}`. `VALID_SOURCES = {agent, reconcile, backfill, operator_repair}`. Single-file partition (NOT per-project — enrichment is a system-wide vertical). Backed up by the nightly Restic job.
- **Cutover marker** (`~/.config/openclaw/cutover-310.done`, introduced by #310) — Written by `scripts/openclaw/helpers/cutover_tasker.py` on successful one-shot cutover. Sentinel only; not in Restic scope.

#### Helpers (post-#310)

Per-helper metadata mirrors `docs/design/architecture/data/service-inventory.json` (the authoritative record — see the `enrichment-helpers` service entry).

- **scripts/enrichment/record_completion.py** (script + library, introduced_by #310, updated_by #310) — Atomic three-write helper per ADR-0002. Performs the Vikunja side-effect FIRST (`[Felix] enrichment | <state> | <ISO timestamp>` comment write during the C-002 soak), then JSONL append SECOND (fcntl-locked + flush + fsync), then ack log THIRD (best-effort). Soft-fails per FR-013 (Q10) when the JSONL step fails post-Vikunja — exits 0 with a warning so the next cycle re-proposes (annoying but harmless; reconcile can recover the row).
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-tasker` agent; `scripts/enrichment/reconcile_completions.py`
  - **writes_to**: Vikunja API (`PUT /tasks/<id>/comments`); `/data/services/openclaw/state/enrichment/enrichment-history.jsonl`
  - **reads_from**: Vikunja API (idempotency pre-check); `/data/services/openclaw/secrets/vikunja`
  - **credentials**: `vikunja-api`
- **scripts/enrichment/reconcile_completions.py** (one-shot helper, introduced_by #310, updated_by #310) — Operator-driven historical backfill (FR-006..FR-009). Enumerates Vikunja tasks with historic `[Felix] enrichment` comments since the 2026-04-11 window, disambiguates them from habit comments (`[Felix] YYYY-MM-DD` vs literal `enrichment` in the second field), and replays each parseable comment as a synthetic JSONL row via `record_completion.py --no-vikunja --source backfill`. Idempotent — re-runs on the same comment set are no-ops.
  - **runs_on**: `office2`
  - **invoked_by**: Operator via `cutover_tasker.py`; Operator via manual triage
  - **writes_to**: `/data/services/openclaw/state/enrichment/enrichment-history.jsonl` (source=backfill)
  - **reads_from**: Vikunja API (`GET /projects`, `GET /projects/<id>/tasks`, `GET /tasks/<id>/comments`)
  - **credentials**: `vikunja-api`
- **scripts/enrichment/derive_state.py** (library + debug CLI, introduced_by #310, updated_by #310) — Pure function (FR-014). Input: list of JSONL records for one task (newest-first). Output: `EnrichmentState` dataclass with `current_state`, `last_event_recorded_at`. Single-offer policy enforcement lives here (skipped/declined are terminal). Consumed by `record_completion.py` (idempotency pre-check) + the tasker agent (check-before-propose) + `reconcile_completions.py` (dedup).
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-tasker` agent; `scripts/enrichment/record_completion.py`; `scripts/enrichment/reconcile_completions.py`
  - **writes_to**: (none — pure function)
  - **reads_from**: `/data/services/openclaw/state/enrichment/enrichment-history.jsonl`
  - **credentials**: (none)
- **scripts/enrichment/schema.py** (library, introduced_by #310, updated_by #310) — `EnrichmentCompletion` dataclass + validators per data-model E1. Frozen dataclass; `VALID_STATES`/`VALID_SOURCES` frozensets; `DEFAULT_LEDGER_PATH`. Pure validator surface; does not file bugs.
  - **runs_on**: `office2`
  - **invoked_by**: `scripts/enrichment/record_completion.py`; `scripts/enrichment/reconcile_completions.py`; `scripts/enrichment/derive_state.py`
  - **writes_to**: (none — pure validator)
  - **reads_from**: (none — operates on in-memory records)
  - **credentials**: (none)
- **scripts/openclaw/helpers/cutover_tasker.py** (one-shot operator script, introduced_by #310, updated_by #310) — Phase 7 (#310) one-shot operator cutover. Deploys task-intelligence SKILL.md (closes pre-existing skill deployment gap surfaced during spec-readiness) + deploys the cut tasker AGENTS.md to `/data/services/openclaw/tasker-agent/` + invokes `reconcile_completions` to backfill the JSONL ledger + writes idempotency marker at `~/.config/openclaw/cutover-310.done`. Mirrors `scripts/doc_audit/helpers/cutover_362.py` shape. Exit codes: 0 success/no-op / 1 filesystem / 2 reconcile failed / 3 invalid args.
  - **runs_on**: `office2`
  - **invoked_by**: Operator (Kent) via `ssh office2-claude`
  - **writes_to**: `/home/claude/.openclaw/skills/task-intelligence/SKILL.md`; `/data/services/openclaw/tasker-agent/AGENTS.md`; `~/.config/openclaw/cutover-310.done`
  - **reads_from**: `scripts/openclaw/skills/task-intelligence/SKILL.md` (repo); `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` (repo)
  - **credentials**: (none)

### Felix Admin Escalation Agent (F019; JSONL state migration #309)
- **Deployed by**: F019
- **Refactored by**: `#309` / mission `migrate-escalation-to-jsonl-state-model-01KS5R4D` (Phase 6 of ADR-0002)
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-escalation`
- **Workspace**: `/data/services/openclaw/escalation-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-escalation/`
- **Model**: `anthropic/claude-sonnet-4-6`
- **Purpose**: Overdue task escalation — detects tasks past due date, delivers level-appropriate WhatsApp alerts, tracks escalation state. Per-project JSONL state log at `/data/services/openclaw/state/escalation/<project-slug>-escalation-history.jsonl` is the sole canonical state source.
- **Skills**: escalation, vikunja_api
- **Autonomy**: Assisted (Level 1)
- **Trigger**: Cron (daily), manual
- **Schedule**: Daily at 8:00 AM ET via OpenClaw cron (`0 12 * * *`)
- **Delivery**: WhatsApp to +16179300916
- **Privacy boundary**: `04-Growth/_private/` is never accessed

#### State files (post-#309)

- **Per-project escalation history** (`/data/services/openclaw/state/escalation/<project-slug>-escalation-history.jsonl`, introduced by #309) — Append-only JSONL. One record per escalation event. Schema: `domain=escalation`, `state ∈ {level_sent, snoozed, dismissed, done, rescheduled}`, `source ∈ {agent, reconcile, backfill, kent_reply, operator_repair}`. Filename-based per-project partition (NFR-003, research D2). Backed up by the nightly Restic job.
- **Pre-migration snapshot** (`/data/services/openclaw/state/escalation/pre-phase6-snapshot.json`, introduced by #309) — Written once at #309 cutover. Preserved as a historical artifact.

#### Helpers (post-#309)

Per-helper metadata mirrors `docs/design/architecture/data/service-inventory.json` (the authoritative record) — see the corresponding `config_files[*]` entries there for `runs_on`, `invoked_by`, `writes_to`, `reads_from`, `credentials`, and `updated_by` fields.

- **scripts/escalation/record_completion.py** (script, introduced_by #309, updated_by #376) — Per-event side-effect dispatcher per ADR-0002 / research D6. Performs the Vikunja PATCH FIRST when the event needs one (`PATCH done=true` for `done` events, `PATCH due_date` for `rescheduled` events) and the JSONL append LAST. For `level_sent`/`snoozed`/`dismissed` the JSONL append is the sole side-effect. Invoked by the agent at every event; also invoked by `reconcile_completions.py --no-vikunja` for synthetic records. Exposes `record_event()` and `idempotent_record_event()`. FR-002, FR-009.
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-escalation` agent; `scripts/escalation/reconcile_completions.py`
  - **writes_to**: Vikunja API (`PATCH /tasks/<id>` for done/rescheduled events only); `/data/services/openclaw/state/escalation/<project-slug>-escalation-history.jsonl`
  - **reads_from**: Vikunja API (`GET /tasks/<id>`); JSONL state log (idempotent dedup pre-check)
  - **credentials**: `vikunja-api`
- **scripts/escalation/reconcile_completions.py** (script, introduced_by #309, updated_by #309) — Drift detection helper (FR-005). Invoked at tick start. Enumerates escalation-subscribed tasks (those with at least one prior `level_sent` JSONL record AND no terminal record since) per project; GETs current Vikunja state per task; compares against `derive_state()` output. Emits synthetic `done` records when Vikunja shows `done=true` with no JSONL `done`; emits synthetic `rescheduled` records when `due_date` changed without a JSONL `rescheduled` record. Surfaces hard-fails per Q10 (FR-008) by calling `scripts/escalation/hard_fail.py`. Output: `ReconcileReport` dataclass.
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-escalation` agent (tick start)
  - **writes_to**: JSONL state log (synthetic records, via `record_completion.py --no-vikunja`); GitHub Issues (via `hard_fail.py` for Q10 hard-fails)
  - **reads_from**: Vikunja API (`GET /projects/<id>/tasks`, `GET /tasks/<id>`); JSONL state log (via `derive_state.py`)
  - **credentials**: `vikunja-api`
- **scripts/escalation/derive_state.py** (library + debug CLI, introduced_by #309, updated_by #309) — Pure function (FR-001). Input: list of JSONL records for one task (newest-first). Output: `EscalationState` dataclass with `current_state`, `last_event`, `snooze_active_until`, `next_eligible_level`, `last_event_recorded_at`. All escalation policy lives here; consumed by `record_completion` + `reconcile_completions`. Debuggable via `python3 -m scripts.escalation.derive_state --task-id <id> --project-id <id>`. Raises `EscalationStateError` on internally inconsistent record sets (Q10 hard-fail surface — bug filing delegated to `hard_fail.py`).
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-escalation` agent; `record_completion.py`; `reconcile_completions.py`; `kent_via_cli` (debug mode)
  - **writes_to**: (none — pure function)
  - **reads_from**: JSONL state log (via `scripts/common/state_log.py`)
  - **credentials**: (none)
- **scripts/escalation/schema.py** (library, introduced_by #309, updated_by #309) — Event-parameter validator surface (FR-003). Exposes `EVENT_TYPE_PARAMETERS`, `validate_event_params()`, `EscalationSchemaError`. Consumed by `record_completion.py` to enforce required parameter fields per event_type (`level_sent` → `level`; `snoozed` → `snooze_days` + `snooze_until`; `rescheduled` → `reschedule_to`; `dismissed`/`done` → no required params). Does NOT file bug reports — Q10 hard-fail filing is owned by `scripts/escalation/hard_fail.py`.
  - **runs_on**: `office2`
  - **invoked_by**: `scripts/escalation/record_completion.py`
  - **writes_to**: (none — pure validator)
  - **reads_from**: (none — operates on in-memory records)
  - **credentials**: (none)
- **scripts/escalation/hard_fail.py** (library, introduced_by #309 (WP04 — forward-referenced), updated_by #309) — Q10 hard-fail bug-filing + dedup helper (FR-008, FR-009). Pure library: `render_bug_body(...)` returns the Markdown body per data-model Entity 5; `dedup_existing_open(task_id)` queries `gh issue list --state open --search 'in:title "(task #<id>)" "Escalation hard-fail"'` per research D9; `file_hard_fail_bug(...)` invokes `scripts/openclaw/agents/main/felix-file-issue.py` as a subprocess with labels `P2-bug, area/escalation`. Consumed by `reconcile_completions.py` (and by `record_completion.py` during validate). **Module not yet implemented — landed by WP04 in this same mission.**
  - **runs_on**: `office2`
  - **invoked_by**: `scripts/escalation/reconcile_completions.py`; `scripts/escalation/record_completion.py`
  - **writes_to**: GitHub Issues (P2-bug, area/escalation via `felix-file-issue.py` subprocess)
  - **reads_from**: GitHub Issues (`gh issue list --state open --search` dedup query)
  - **credentials**: `github-pat-kg-felix-bot`

### Felix Admin Calendar Agent (#579, mission `felix-calendar-subagent-extraction-01KTTA33`, 2026-06-11)
- **Deployed by**: [#579](https://github.com/kentonium3/kg-automation/issues/579) / mission `felix-calendar-subagent-extraction-01KTTA33`
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-calendar`
- **Workspace**: `/data/services/openclaw/calendar-agent/`
- **agentDir**: `/home/claude/.openclaw/agents/felix-admin-calendar/agent`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-calendar/` (IDENTITY.md, SOUL.md, AGENTS.md, TOOLS.md, USER.md per `docs/runbooks/openclaw-agent-setup.md`)
- **Model**: `anthropic/claude-haiku-4-5` (optimizable) — Routine deterministic-validator-driven workflow; matches capture / habits / tasker shape. Re-evaluate if accuracy is poor in production.
- **Purpose**: Calendar **judgment layer** (reshaped by #699, RFC #681 calendar phase — was: gog-executing substrate). Handles only the work that needs an LLM: the conversational calendar path and clarification round-trips (interpreting Kent's natural-language date/time/intent, at most one clarification round on ambiguity). Its terminal action is a call to the **Felix calendar helper** (`scripts/google/calendar_helper.py`), **not** `gog calendar create`. On inbound WhatsApp clarification reply, reads the pending-calendar-clarifications state file, merges Kent's reply into the deferred event payload, re-validates, and issues the create via the helper. Surfaces a helper exit 3 (auth) / 1 (operational) verbatim and never fakes success (#683); it must not fall back to gog.
- **Skills**: `[]` (none) — `calendar` was never a real OpenClaw skill and the `gog` skill was **removed** by #699; the helper is invoked via `exec`, not a gog skill (that #699 skill removal was the only `openclaw.json` rebaseline-triggering change in the calendar migration)
- **Autonomy**: Assisted (Level 1)
- **Triggers**: Conversational calendar requests (Kent → main → calendar agent); WhatsApp clarification reply relay (for incomplete inbox-capture round-trips). NOTE: complete inbox calendar events no longer delegate here — since #699 they reach the calendar inline via `route_calendar_event --create` (closes #679).
- **Depends on**: Felix calendar helper (`scripts/google/calendar_helper.py`, run under the venv `/data/services/openclaw/felix-calendar/venv`) for Google Calendar access; the `felix-google-personal-calendar` per-account OAuth credential (`~/.config/felix/google/personal/`). No longer depends on `gog` / `GOG_KEYRING_PASSWORD` for the calendar surface.
- **Privacy boundary**: `04-Growth/_private/` is never accessed
- **Why extracted from main**: Per mission spec, calendar work previously lived in `main/AGENTS.md` (lines 259-440 pre-mission). Delegations to `main` were blocking on the deprecated `main` alias surface, suppressing the WhatsApp reply relay. Extracting to a dedicated subagent restores the relay and gives the calendar substrate room to grow.
- **Contract owner after extraction**: `felix-admin-calendar` (was: `main`). The calendar event creation payload and response envelope contracts (per `kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/contracts/capture_to_main_calendar_payload.md`) are moved 1:1 — no behavioral change.
- **Dispatcher (post-#699)**: `felix-admin-capture` reaches the calendar **inline** via `scripts/inbox/route_calendar_event.py --create` (direct Felix calendar helper call — no agent hop, no `gog`). *(Pre-#699 this was openclaw-agent dispatch to `felix-admin-calendar`; #699 retired the hop for complete inbox-captured events.)*
- **Runbook**: `docs/runbooks/openclaw-agent-setup.md` (canonical agent-setup procedure — required reading before deploy/modify/register); mission-specific smoke runbook: `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md`
- **Mission spec**: `kitty-specs/felix-calendar-subagent-extraction-01KTTA33/spec.md` (data model + payload contracts in `data-model.md`)
- **Authoritative JSON**: see `services[openclaw-gateway].agents.felix-admin-calendar` in `data/service-inventory.json`

#### State files

- **Pending calendar clarifications** (`/data/services/openclaw/state/pending-calendar-clarifications.jsonl`, relocated from `~/second-brain/agents/state/` by #656) — Per data-model.md, file path and JSONL record shape are PRESERVED from main's pre-mission handler (path only was updated by #656). Atomic-write protocol (LOCK_EX + .tmp + rename) preserved verbatim. Records aged out after 24h by the sweep. Owner `claude:secondbrain`, dir mode 0750, file mode 0640.

### Felix Calendar Helper (#699, mission `felix-calendar-helper-01KX4H3C`, RFC #681 calendar phase, 2026-07-09)
- **Deployed by**: [#699](https://github.com/kentonium3/kg-automation/issues/699) / mission `felix-calendar-helper-01KX4H3C` (first concrete delivery of accepted RFC #681)
- **Type**: `library` — Python CLI + importable library. **On-demand invocation only** (no long-running service, no systemd unit, no cron).
- **Purpose**: Felix-owned deterministic Google Calendar helper. Performs event create / list / update / delete **directly** against the Google Calendar API via `google-api-python-client`, replacing `gog calendar create` on the calendar surface (closes #679). Multi-account-ready: default account `personal` (`kentgale@gmail.com`); adding `intentional.biz` later is credential-only (no code change).
- **Source in repo**: `scripts/google/calendar_helper.py` (CLI: create/list/update/delete + `--self-check`), `scripts/google/calendar_auth.py` (per-account load/refresh/persist).
- **Runtime**: dedicated uv-provisioned venv at `/data/services/openclaw/felix-calendar/venv` (pinned `google-api-python-client`, `google-auth`, `google-auth-oauthlib`; office2 system `python3` lacks these and has no `pip`). Invoked module-form (C-007/#682): `cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper <subcommand> …`. The google deps live in the venv, **not** in `requirements.txt`, so the pip-packages security baseline is untouched.
- **Credential**: `felix-google-personal-calendar` (OAuth2 authorized-user, `calendar.events` scope) at `~/.config/felix/google/personal/{client_secret,token}.json` (0600 / dir 0700; `FELIX_GOOGLE_DIR` overrides base). See `credentials-and-secrets.md` §8.
- **Invoked by**: `felix-admin-calendar` (judgment layer, via `exec`); `scripts/inbox/route_calendar_event.py --create` (inline from `felix-admin-capture`, no agent hop).
- **Exit-code contract**: `0` success · `1` operational/API error · `2` usage/bad-args · `3` auth failure (fail-safe — no calendar mutation, actionable "re-mint on the Mac" message; #683). Attendee invitations suppressed by default (`sendUpdates=none`); inbox creates carry a stable `felix_source_key` for idempotent retry.
- **Health**: on-demand — no continuous signal. Liveness via `--self-check` (loads creds, refreshes token, bounded `events().list(primary, maxResults=1)`); the deploy manifest runs it as a post-flight gate.
- **Depends on**: external **Google Calendar API** (`calendar.events` scope) — free within quota. Not gog.
- **Deploy**: `deploys/queued/felix-calendar-helper.yaml` (Tier 2+3) — Restic gate → provision venv → verify creds present → `--self-check`. Credential staging is a manual operator step (Mac → office2, 0600); the manifest only verifies presence.
- **Runbook**: [`docs/runbooks/calendar-helper-ops.md`](<../../runbooks/calendar-helper-ops.md>)
- **Authoritative JSON**: see `services[felix-calendar-helper]` in `data/service-inventory.json`

### Felix Time-Log Helper (#703, mission `felix-time-logging-01KX79HT`, 2026-07-11)
- **Deployed by**: [#703](https://github.com/kentonium3/kg-automation/issues/703) / mission `felix-time-logging-01KX79HT`
- **Type**: `library` — Python CLI + importable library. **On-demand invocation only** (no long-running service, no systemd unit, no cron).
- **Purpose**: Felix-owned deterministic Google Sheets helper for the WhatsApp "log time" workflow. `scripts/google/timelog.py` validates structured args extracted by main's recognizer (option A — extraction + dialog, no sub-agent delegation), resolves the client to a workbook tab (tabs-as-truth + aliases in `timelog-clients.json`), maintains pending/correction state, and appends a confirmed row via `scripts/google/sheets_helper.py`. No LLM anywhere in the helper — all judgment lives in `main`.
- **Source in repo**: `scripts/google/timelog.py` (main-facing normalizer: validate/resolve/typed-signal/write), `scripts/google/sheets_helper.py` (CLI: append-row/create-tab/list-tabs/update-last/delete-last + `--self-check`), `scripts/google/sheets_auth.py` (per-account load/refresh/persist, scope-agnostic).
- **Runtime**: shares the **#699 calendar helper's** dedicated uv-provisioned venv at `/data/services/openclaw/felix-calendar/venv` (same `google-api-python-client` / `google-auth` / `google-auth-oauthlib` pins) — no second venv is provisioned. Invoked module-form: `cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.timelog --client ... --hours ... --date ... --description ... --channel whatsapp --conversation <id> --source-msg-id <id> --json`.
- **Credential**: `felix-google-personal-calendar` (OAuth2 authorized-user), re-minted **once** by #703 with the **combined** `calendar.events + spreadsheets` scopes at `~/.config/felix/google/personal/{client_secret,token}.json` (0600 / dir 0700). See `credentials-and-secrets.md` §8.
- **Invoked by**: `main` (via `exec`) — the sole judgment/extraction layer; no delegation to a sub-agent.
- **Exit-code contract**: `timelog.py` uses **F9** (NOT the sheets_helper 0/1/2 convention) — exit `0` for any handled `TimelogResult` status (including `error`/`client_created_entry_failed`), exit `2` only on a usage/arg error. `sheets_helper.py` mirrors `calendar_helper.py`'s `0`/`1`/`2` convention and adds `--self-check --account personal` (auth refresh + a bounded `spreadsheets().get`, no write).
- **Fail-safe guarantee**: an append is reported `logged` only after an API-confirmed read-back (#683 trust defect); any Sheets API error surfaces via the `#701` alert bus rather than a silent no-op or a false success. A new-client two-step onboarding (create-tab then append) that fails mid-sequence reports `client_created_entry_failed`, never `logged`.
- **Health**: on-demand — no continuous signal. Liveness via `sheets_helper --self-check --account personal`; the deploy manifest also runs a no-write `timelog` self-test (guaranteed-unresolvable client) as a combined post-deploy gate before prompt-sync verification (#711 pattern).
- **Depends on**: external **Google Sheets API** (`spreadsheets` scope) — free within quota. Not gog.
- **Deploy**: `deploys/queued/timelog.yaml` (Tier 2+3) — venv/deps gate (shared venv) → verify staged combined-scope creds + workbook-config presence → no-emit dry-run self-test (gated, #711) → prompt-sync trigger + verify main's recognizer. Credential re-consent and the one-time workbook bootstrap are **manual operator steps** (Kent-in-the-loop); the manifest only verifies presence.
- **Runbook**: [`docs/runbooks/timelog.md`](<../../runbooks/timelog.md>)
- **Authoritative JSON**: see `services[felix-timelog-helper]` in `data/service-inventory.json`

### Felix Doc Auditor (#105 deployed 2026-05-10; refactored to scripts-first driver in #343, 2026-05-21; Moment 0 drift interpretation added in #362, 2026-05-22)
- **Operational status**: ⏸ **Suspended indefinitely 2026-05-26**. Implementation complete (post-#343 / #362 / #391 / #400). Two-layer suspension in place: `felix-doc-auditor.timer` `disabled` + `[drift_interpretation].enabled = false` + `[audit_interpretation].enabled = false` in `scripts/doc_audit/config.toml` (commit `d46a9ead`). GH Actions workflows `Doc Audit Trigger` + `Doc Audit Weekly` also `disabled_manually`. Reactivation gated on [#137](https://github.com/kentonium3/kg-automation/issues/137) cost-control epic landing plus explicit operator decision. The entries below describe the design and intended runtime behavior, unchanged by suspension.
- **Deployed by**: #105 / mission `felix-doc-auditor-agent-01KR7JK9`
- **Refactored by**: #343 / mission `refactor-doc-auditor-to-scripts-first-driver-01KS2XNX`
- **Extended by**: #362 / mission `drift-event-auto-resolution-01KS8J32` (v2 since #362 — adds Moment 0 drift interpretation; PROPOSED_EDIT verdicts route through the existing tier_classification surface, preserving SKILL.md §4.3 guardrails)
- **Type**: Python driver process triggered by systemd user timer (no openclaw session in the runtime path post-#343)
- **Service name**: `felix-doc-auditor` (the SERVICE identity is unchanged; only the implementation changed)
- **Driver entry**: `/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py`
- **Source in repo**: `scripts/doc_audit/` (driver + adapters + helpers + judgment prompts)
- **Model**: `anthropic/claude-haiku-4-5` (pinned; downshifted from Sonnet by #343 — judgment calls are now narrow and prompt-scoped)
- **Autonomy level**: Assisted (Level 1) — planned promotion to Supervised (Level 2) after ~1 week clean operation
- **Schedule**: hourly via `felix-doc-auditor.timer` (systemd user timer at `~/.config/systemd/user/`, `OnCalendar=hourly`, `Persistent=true`)
- **Per-tick invocation**: `felix-doc-auditor.service` (systemd user oneshot) invokes the driver entry above directly — no `openclaw agent` shell-out, no SKILL.md procedure loaded at runtime. Each tick is a fresh Python process; state is stateless per tick (carried only via GitHub labels/issues and `last-tick.json`).
- **Judgment moments (post-#400, five moments)**: Moment 0 splits into TWO judgment surfaces — one per signal class. **drift_interpretation** (`scripts/doc_audit/judgment/drift_interpretation.py`, introduced by #362, cron-path corrected by #391) classifies each mapped drift event as PROPOSED_EDIT / JUDGMENT_REQUIRED / NO_CHANGE_NEEDED before any GitHub issue is filed; invocation flows through `signals/drift_event.py::DriftEventSignalSource.commit()` → `routing/drift_moment0.py::route_drift_event()`. **audit_interpretation** (`scripts/doc_audit/judgment/audit_interpretation.py`, introduced by #400) is the structural twin for commit-derived `Doc audit:` issues — invoked by `handle_audit_routing.py` on the no-proposals branch when `[audit_interpretation].enabled = true`, it returns one AuditVerdict PER in-scope doc, with the same three-verdict vocabulary and ≥0.80 confidence threshold. Moment 1 — **tier_classification** (Tier-A vs Tier-B vs judgment; consumes PROPOSED_EDIT verdicts from either Moment 0 surface). Moments 2 and 3 — **debt_body_generation** and **cross_file_implication** (unchanged from #343).
- **Judgment prompts**: checked-in markdown artifacts at `scripts/doc_audit/prompts/*.prompt.md` (drift_interpretation [#362], audit_interpretation [#400], tier_classification, debt_body_generation, cross_file_implication) — replaces the historical runtime `~/.openclaw/skills/doc-audit/SKILL.md` (no longer loaded at runtime; retained only as historical reference).
- **API path**: driver reads `/data/services/openclaw/secrets/anthropic` (0600, claude:claude) at tick start and calls `api.anthropic.com` directly via the `anthropic` Python SDK; the openclaw-gateway is NOT in the runtime path.
- **Health check**: structured `last-tick.json` at `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json` (expected `status: "success"` within last 2 hours); see `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/tick-signal.contract.md`. The per-tick prose activity log at `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` remains as a human-readable summary.
- **Purpose**: processes Doc Audit and Weekly Doc Audit issues automatically; commits high-confidence edits directly, files docs-debt issues for judgment items, detects missing artifacts
- **Approval mechanism (Level 1)**: WhatsApp summary message + reply parsing (`approve`/`reject`/`skip`); 2-hour timeout = default deny
- **Concurrency lock**: GitHub label `status:in-progress` on the in-flight audit issue (unchanged across #343)
- **Identity**: `kg-felix-bot` (classic PAT via gh CLI auth store) — unchanged across #343
- **Authoritative JSON**: see `felix-doc-auditor` entry in `data/service-inventory.json`
- **Runbook**: `docs/runbooks/doc-auditor-driver-ops.md` (operator quick-reference + troubleshooting; supersedes the prior `doc-auditor-ops.md` for the post-#343 driver implementation; post-#362 includes a "Moment 0 — drift interpretation" section with ledger CLI examples and rollback procedure; post-#400 adds a parallel "Moment 0 — commit-derived audit interpretation" section plus a one-time "Cutover replay for stuck audits" procedure)

#### Moment 0 modules and supporting helpers (post-#362)

Per-module metadata mirrors `docs/design/architecture/data/service-inventory.json` (the authoritative record). See the corresponding top-level entries there for full dependencies and `config_files[*]` details.

- **scripts/doc_audit/judgment/drift_interpretation.py** (judgment module, introduced_by #362, updated_by #391) — Moment 0 LLM judgment. Builds a cache-aware prompt + dynamic `DriftInterpretationContext` (drift event metadata + diff + mapping rationale + current contents of each target doc), calls Anthropic via the shared `JudgmentClient` (model `claude-haiku-4-5-20251001`), parses + validates the response against the E1 invariants, and returns a `DriftVerdict` (PROPOSED_EDIT / JUDGMENT_REQUIRED / NO_CHANGE_NEEDED, with explicit confidence ∈ [0.0, 1.0]). Confidence < 0.80 demotes to JUDGMENT_REQUIRED at the helper boundary. Retry policy 30s/60s/120s; on exhaustion raises `DriftInterpretationError` which the caller (signals/drift_event.py on the cron path, or handle_drift_events.py on the replay path) catches and converts to a pre-#362 fallback `[doc-audit]` issue with the diagnostic block.
  - **runs_on**: `office2`
  - **invoked_by**: `signals/drift_event.py::DriftEventSignalSource.commit()` (cron path, corrected by #391) and `helpers/handle_drift_events.py::process_events()` (library/CLI replay path) — both delegate to `routing/drift_moment0.py::route_drift_event()` which calls `interpret()` once per mapped drift event when `[drift_interpretation].enabled = true`
  - **writes_to**: (none — caller writes the ledger)
  - **reads_from**: `/data/services/openclaw/secrets/anthropic` (via shared JudgmentClient); `api.anthropic.com` (HTTPS)
  - **credentials**: `anthropic-api`
- **scripts/doc_audit/output/drift_ledger.py** (storage + read-only query CLI, introduced_by #362, updated_by #362) — Append-only JSONL audit ledger writer at `/data/services/security-monitor/logs/drift-events-ledger.jsonl`. One row per processed drift event capturing `event_id`, `timestamp_utc`, `baseline`, `mapping_id`, `verdict`, `confidence`, `outcome ∈ {auto_committed, pr_filed, issue_filed, auto_closed, retry_exhausted}`, `doc_paths`, `retry_count`, `latency_ms`, `tier_classification_outcome`, `github_issue_number`. Atomic appends (tempfile + rename). Read-only CLI subcommands `summary`, `tail`, `triage-rate` back the NFR-001 operator-triage-rate metric over a configurable trailing window (default 7 days).
  - **runs_on**: `office2`
  - **invoked_by**: `felix-doc-auditor` driver (via `handle_drift_events.py`) on the write side; operator (Kent) for read-only subcommands
  - **writes_to**: `/data/services/security-monitor/logs/drift-events-ledger.jsonl` (append-only; no rotation in v1)
  - **reads_from**: same ledger file for query subcommands
  - **credentials**: (none — file-only)
- **scripts/doc_audit/judgment/audit_interpretation.py** (judgment module, introduced_by #400, updated_by #400) — Moment 0 LLM judgment for commit-derived `Doc audit:` issues. Builds a cache-aware prompt + dynamic `AuditInterpretationContext` (audit issue metadata + commit SHA + diff + in-scope doc paths + per-doc current contents) and invokes the LLM ONCE PER in-scope doc via the shared `JudgmentClient` (model `claude-haiku-4-5-20251001`). Each call returns an `AuditVerdict` (PROPOSED_EDIT / JUDGMENT_REQUIRED / NO_CHANGE_NEEDED, with explicit confidence ∈ [0.0, 1.0]). PROPOSED_EDIT or NO_CHANGE_NEEDED at confidence <0.80 demotes to JUDGMENT_REQUIRED at the helper boundary. PROPOSED_EDIT proposing an edit to a path outside the audit's in-scope list (semantic violation) also demotes. Retry policy 30s/60s/120s per doc; failures on doc N do NOT prevent docs N±1 from being evaluated (per-doc isolation — emits a synthetic JUDGMENT_REQUIRED for the failed doc).
  - **runs_on**: `office2`
  - **invoked_by**: `scripts/doc_audit/helpers/handle_audit_routing.py` on the no-proposals branch when `[audit_interpretation].enabled = true`
  - **writes_to**: (none — caller writes the ledger)
  - **reads_from**: `/data/services/openclaw/secrets/anthropic` (via shared JudgmentClient); `api.anthropic.com` (HTTPS); per-doc disk contents (read by `handle_audit_routing.py`, passed in via context)
  - **credentials**: `anthropic-api`
- **scripts/doc_audit/output/audit_ledger.py** (storage + read-only query CLI, introduced_by #400, updated_by #400) — Append-only JSONL ledger writer for the commit-audit Moment 0 path at `/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl`. One row per (audit_issue, doc_path) capturing `audit_issue` (int — replaces drift's `event_id`/`baseline`/`mapping_id` since the audit issue number is the cursor for the commit-audit path), `doc_path`, `verdict`, `confidence`, `outcome ∈ {auto_committed, pr_filed, judgment_required_posted, auto_closed, retry_exhausted}` (note `judgment_required_posted` replaces drift's `issue_filed` because audit appends a comment to the EXISTING audit issue rather than creating a new one), `retry_count`, `latency_ms`, `tier_classification_outcome`, `timestamp_utc`, `schema_version`. Atomic appends (tempfile + rename). Read-only CLI subcommands `summary`, `tail`, `triage-rate` back the NFR-001 operator-triage-rate metric.
  - **runs_on**: `office2`
  - **invoked_by**: `handle_audit_routing.py` (one append per in-scope doc on the write side); operator (Kent) for read-only subcommands
  - **writes_to**: `/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl` (append-only; no rotation in v1)
  - **reads_from**: same ledger file for query subcommands
  - **credentials**: (none — file-only)
- **scripts/doc_audit/routing/drift_to_proposed_edit.py** (translator, introduced_by #362, updated_by #391) — Pure-function translator. Builds a `ProposedEdit` (`change_type='drift_derived'` — the 8th `change_type` value documented in `data_model.py`; `tier='tier_b'` placeholder; `confidence='high'`; `evidence_source=f"drift-event:{baseline}:{event_id}"`) from a high-confidence (≥0.80) PROPOSED_EDIT `DriftVerdict` + its `DriftInterpretationContext`. Validates the proposed `doc_path` is within the mapping's `doc_targets` list — out-of-set proposals raise `ValueError` (the caller demotes to JUDGMENT_REQUIRED). The resulting `ProposedEdit` feeds the existing `tier_classification` surface; its conservative rules ultimately decide Tier A / Tier B / judgment (defense-in-depth — drift-derived edits the classifier can't confidently tier go to judgment).
  - **runs_on**: `office2`
  - **invoked_by**: `routing/drift_moment0.py::route_drift_event()` on PROPOSED_EDIT verdicts at confidence ≥0.80; reached from both `signals/drift_event.py` (cron) and `helpers/handle_drift_events.py` (replay) post-#391
  - **writes_to**: (none — pure function)
  - **reads_from**: (none — operates on in-memory dataclasses)
  - **credentials**: (none)
- **scripts/doc_audit/routing/drift_moment0.py** (routing helper, introduced_by #391, updated_by #391) — Shared Moment 0 routing helper. Single source of truth for Moment 0 + verdict routing + ledger append: (1) calls `drift_interpretation.interpret()` (with internal retries per #362 D6); (2) routes the verdict (PROPOSED_EDIT → `drift_to_proposed_edit` → `tier_classification`; demoted/JUDGMENT_REQUIRED → `[doc-audit]` issue; NO_CHANGE_NEEDED ≥threshold → auto-close + ledger only); (3) appends one `AuditLedgerEntry` via `drift_ledger.append()` (terminal step, for crash recovery). Exposes `RoutingOutcome` dataclass + `route_drift_event()` function. Callers catch `DriftInterpretationError` externally to drive the RETRY_EXHAUSTED fallback path so the fallback semantics live in one place. Promoted from inline orchestration in `handle_drift_events.py` by #391 so both entry points (cron + replay) execute identical behavior.
  - **runs_on**: `office2`
  - **invoked_by**: `signals/drift_event.py::DriftEventSignalSource.commit()` (cron entry point) and `helpers/handle_drift_events.py::process_events()` (library/CLI replay)
  - **writes_to**: GitHub Issues (via gh CLI subprocess); `/data/services/security-monitor/logs/drift-events-ledger.jsonl` (via `drift_ledger.append`)
  - **reads_from**: (none directly — receives Mapping + DriftEvent from callers)
  - **credentials**: `anthropic-api` (via JudgmentClient); `github-pat-kg-felix-bot` (via gh CLI)
- **scripts/doc_audit/helpers/cutover_362.py** (one-shot script, introduced_by #362, updated_by #362) — Idempotent operator-driven backlog cutover. Bridges from the pre-#362 deterministic-only pipeline into the new Moment 0 pipeline by closing the 13 known pre-#362 `[doc-audit]` P3 issues (#351-#360, #368-#370) with a comment noting the new pipeline will reprocess them, resetting the drift-events cursor at `/data/services/security-monitor/.drift-events.cursor` to 0 so existing piled-up drift events are reprocessed via Moment 0, and writing a sentinel marker at `~/.config/doc-audit/cutover-362.done`. Marker presence short-circuits re-runs unless `--force` is passed. `--dry-run` prints intent without mutations.
  - **runs_on**: `office2`
  - **invoked_by**: operator (Kent) — manual one-shot post-deploy
  - **writes_to**: GitHub Issues (comment + close via gh CLI subprocess, identity kg-felix-bot); `/data/services/security-monitor/.drift-events.cursor`; `~/.config/doc-audit/cutover-362.done`
  - **reads_from**: GitHub Issues via `gh issue list --search`
  - **credentials**: `github-pat-kg-felix-bot`
- **scripts/doc_audit/helpers/cleanup_391.py** (one-shot script, introduced_by #391, updated_by #391) — Idempotent operator-driven cleanup. Closes the 13 broken-pipeline `[doc-audit]` artifact issues (#378-#390) that were filed by the broken pre-#391 pipeline replay on 2026-05-22T22:28 UTC; writes a sentinel marker at `~/.config/doc-audit/cleanup-391.done`. Marker presence short-circuits re-runs unless `--force` is passed. `--dry-run` prints intent without mutations. Structurally identical to `cutover_362.py` except: (a) static issue list (no `gh issue list` query); (b) does NOT reset the drift-events cursor — the fixed pipeline at `signals/drift_event.py` processes subsequent events via Moment 0 naturally.
  - **runs_on**: `office2`
  - **invoked_by**: operator (Kent) — manual one-shot post-deploy
  - **writes_to**: GitHub Issues (comment + close via gh CLI subprocess, identity kg-felix-bot); `~/.config/doc-audit/cleanup-391.done`
  - **reads_from**: (none — issue list is static at code-write time)
  - **credentials**: `github-pat-kg-felix-bot`
- **scripts/openclaw/helpers/rotate_main_session.py** (one-shot script, introduced_by #374, updated_by #374) — Operator-driven forced rotation of the OpenClaw **main** agent's active sessions. Renames each active `<uuid>.jsonl` under `/home/claude/.openclaw/agents/main/sessions/` to `<uuid>.jsonl.reset.<timestamp>` (the existing OpenClaw rotation convention), skipping any file already carrying a `.reset.` suffix. Writes a per-invocation marker at `~/.config/openclaw/main-rotation-<timestamp>.done` listing the rotated sessions for audit. Used as step 4 of the 5-step cutover sequence (see `docs/runbooks/openclaw-agent-setup.md` §"Cutover sequence for main-agent AGENTS.md changes (post-#374)") when changing `/data/services/openclaw/data/AGENTS.md` — forces the new standing orders to load on the next invocation rather than waiting for sessions to expire naturally. Naturally idempotent (each call produces a uniquely-timestamped marker + reset suffix). `--dry-run` prints intent without mutations. `--force` is reserved for future use.
  - **runs_on**: `office2`
  - **invoked_by**: operator (Kent) — manual, post-AGENTS.md-deploy
  - **writes_to**: `/home/claude/.openclaw/agents/main/sessions/` (Path.rename to `*.jsonl.reset.<timestamp>`); `~/.config/openclaw/main-rotation-<timestamp>.done` (marker)
  - **reads_from**: `/home/claude/.openclaw/agents/main/sessions/` (directory listing)
  - **credentials**: (none — pure filesystem operation)
- **scripts/doc_audit/helpers/handle_drift_events.py** (library + operator-replay CLI, introduced_by #343, updated_by #391) — Library + replay CLI for drift-event processing. Exposes atomic primitives (`find_mapping`, `file_doc_audit_issue`, `append_unmapped`, `write_cursor_atomic`) shared with the cron entry point. The `process_events()` function delegates to `routing/drift_moment0.py::route_drift_event()` for Moment 0 + verdict routing + ledger append so behavior matches the cron path bit-for-bit. **Post-#391 NOT invoked by the cron service** — the cron path is `signals/drift_event.py::DriftEventSignalSource.commit()`. Only operator replay (via `python3 -m doc_audit.helpers.handle_drift_events`) and programmatic callers reach this entry point. Reads `/data/services/security-monitor/logs/drift-events.jsonl` from the cursor; per event consults `signal-to-doc-map.json` and assembles a `DriftInterpretationContext`. When `[drift_interpretation].enabled = false`, behaves identically to the pre-#362 deterministic-only pipeline (FR-013).
  - **runs_on**: `office2`
  - **invoked_by**: operator (replay only); programmatic callers needing library primitives. **Not** invoked by the cron service after #391.
  - **writes_to**: GitHub Issues (via gh CLI subprocess); `/data/services/security-monitor/logs/drift-events-ledger.jsonl` (via routing/drift_moment0.py → drift_ledger.append); cursor file
  - **reads_from**: `/data/services/security-monitor/logs/drift-events.jsonl`; `signal-to-doc-map.json`
  - **credentials**: `anthropic-api` (via JudgmentClient); `github-pat-kg-felix-bot` (via gh CLI)

### Felix Core Digest (F014, signal extraction added #490)
- **Deployed by**: F014; signal-extraction pass added by #490 (mission `signal-driven-monitoring-haiku-gate-01KT22PC`)
- **Type**: Scheduled service (systemd user timer; `Type=oneshot` with two chained `ExecStart=` lines post-#490)
- **systemd unit**: `felix-core-digest.timer` + `felix-core-digest.service` (user unit under claude)
- **Schedule**: Every 15 minutes (OnUnitActiveSec=15min, OnBootSec=3min, Persistent=true)
- **Runs as**: claude user
- **ExecStart 1**: `/usr/bin/python3 /home/claude/kg-automation/scripts/openclaw/observation/summarize.py` (existing — agent-log digest)
- **ExecStart 2** (post-#490): `/usr/bin/python3 /home/claude/kg-automation/scripts/openclaw/observation/tick.py` (NEW — deterministic OpenClaw-log signal extraction). Runs **only if** ExecStart 1 exits 0 (systemd `Type=oneshot` semantics).
- **Input (summarize)**: JSONL log files at `/home/kgale/second-brain/agents/logs/{agent}/YYYY-MM-DD.jsonl`
- **Input (tick)**: OpenClaw daily logs at `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
- **Output (summarize)**: Markdown digests at `/home/kgale/second-brain/notes/00-System/agent-activity/Agent-Logs/`
- **Output (tick)**: Per-signal state + `last-tick.json` + `signals-ledger.jsonl` under `/data/services/openclaw/felix-core-digest-signals/`; GitHub issue filings via `scripts/openclaw/agents/main/felix-file-issue.py` (subprocess, kg-felix-bot identity)
- **Retention**: 5 days (digest files deleted by filename date); signal state + `last-tick.json` overwritten each cycle; `signals-ledger.jsonl` append-only
- **Idempotency**: Skips digest writes when no new JSONL content; signal filer deduplicates against open issues within the configured dedup window (FR-002)
- **Source in repo**: `scripts/openclaw/observation/summarize.py`, `scripts/openclaw/observation/tick.py`, `scripts/openclaw/observation/signals/` (signal sources + `config.toml`)
- **Log writer**: `scripts/openclaw/observation/log_action.py` (utility, not a service)
- **Health check (post-#490)**: `/data/services/openclaw/felix-core-digest-signals/last-tick.json` — `exit_status=success` within last 30 minutes, `errors=[]` (see `kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md`)
- **Runbook**: `docs/runbooks/observation-ops.md` (summary digest); `docs/runbooks/signal-driven-monitoring-ops.md` (signal extraction + cutover, #490)

### Felix Heartbeat Gate (#490, signal-driven-monitoring-haiku-gate; determinized #676)
- **Deployed by**: #490 / mission `signal-driven-monitoring-haiku-gate-01KT22PC`; determinized by #676 / mission `deterministic-monitoring-checks-01KX1XNW`
- **Type**: systemd user timer + oneshot service (**deterministic** stdlib routing gate for OpenClaw's heartbeat — no LLM call, post-#676; previously Haiku-tier)
- **systemd unit**: `felix-heartbeat-gate.timer` + `felix-heartbeat-gate.service` (user unit under claude)
- **Schedule**: `OnUnitActiveSec=30min`, `OnBootSec=5min`, `Persistent=true`. The 5-min boot offset (vs `felix-core-digest.timer`'s 3-min) avoids lockstep contention.
- **Runs as**: claude user
- **ExecStart**: `/usr/bin/python3 /home/claude/repos/kg-automation/scripts/openclaw/heartbeat_gate/run.py`
- **Session mode**: stateless per tick — each invocation is a fresh Python process; nothing carried between ticks except via filesystem (`last-gate-decision.json`, `gate-ledger.jsonl`, `HEARTBEAT.md`).
- **Model**: **none** (post-#676) — the tick decision (`decide_deterministic(context)`) is Python-standard-library-only; no `anthropic` SDK import, no API key read in the hot path. Formerly `claude-haiku-4-5` (anthropic SDK, direct, pinned) prior to #676.
- **Inputs**: `/data/services/openclaw/felix-core-digest-signals/last-tick.json` (primary), `/data/services/openclaw/data/HEARTBEAT.md` (contract file, FR-010 of the original mission).
- **Outputs**: `last-gate-decision.json` (canonical health surface, overwritten each tick; token fields always `0` post-#676), `gate-ledger.jsonl` (append-only per-tick ledger backing NFR-001/NFR-003 cost telemetry).
- **Escalation surface**: on `ESCALATE_TO_SONNET` or fallback (fail-safe, FR-007 of #676), invokes `openclaw system event --mode now` exactly once per tick to wake the existing Sonnet 4.6 main-agent path — unchanged from the original mission.
- **Determinism (#676)**: `decide_deterministic(context)` reproduces the former routing prompt's boolean escalation contract exactly (`novelty_markers` non-empty OR `heartbeat_md_state == "has_tasks"` OR `errors` non-empty → `ESCALATE_TO_SONNET`); validated against the full historical `gate-ledger.jsonl` before cutover — 0 missed escalations (INV-006), over-escalation ≤5%. See `scripts/openclaw/heartbeat_gate/validate_ledger.py`.
- **Cutover note (Tier 2, original mission)**: the original #490 cutover step `openclaw system heartbeat disable` was Tier 2 — requires Restic backup currency check. #676 is Tier 3 (logic-only change to an already-running deterministic timer; no new systemd cutover against OpenClaw's internal heartbeat).
- **Source in repo**: `scripts/openclaw/heartbeat_gate/` (run.py, gate.py, context.py, escalator.py, ledger.py, validate_ledger.py). `prompts/routing.prompt.md` is retained in the repo as historical reference for the boolean contract it specified, but is no longer read by the tick path.
- **Health check**: `/data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json` — `outcome ∈ {HEARTBEAT_OK, LOG_AND_SKIP, ESCALATE_TO_SONNET}` within last 35 min, `errors=[]`, `fallback_invoked=false` on the steady state.
- **Runbook**: `docs/runbooks/signal-driven-monitoring-ops.md`
- **Mission context**: `kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/spec.md` (original); `kitty-specs/deterministic-monitoring-checks-01KX1XNW/spec.md` (determinization)

### Felix Habit Sweeper (#408, 2026-06-02)
- **Deployed by**: #408 / mission `habit-day-specific-scheduling-01KT48Y6`
- **Type**: systemd user timer + oneshot service (deterministic Python — no LLM calls per Directive 6)
- **systemd unit**: `felix-habit-sweeper.timer` + `felix-habit-sweeper.service` (user unit under claude)
- **Schedule**: `OnCalendar=*-*-* 07:30 America/New_York`, `Persistent=true`. Fires 25 minutes after the 7:05 AM ET morning check-in cron so today's check-in is delivered before the sweep evaluates yesterday's.
- **Runs as**: claude user
- **ExecStart**: `/usr/bin/python3 /home/claude/kg-automation/scripts/habits/sweeper.py`. Path uses `/home/claude/kg-automation/` per the post-#59 cutover convention (NOT `/repos/`).
- **Session mode**: stateless per tick — each invocation is a fresh Python process; persistent state lives in `/data/services/openclaw/state/habits/` (per-tick artifacts + ledger) and the canonical `/data/services/openclaw/state/habits-history.jsonl`.
- **Determinism**: zero LLM calls. The sweep is a pure data operation against the schedule YAML, morning-checkin artifacts, and habits-history. Vikunja `due_date` advancement re-uses the WP-01 `compute_next_eod_et_for_weekdays` helper (which is unit-tested for the #112 explicit-ET-offset guard).
- **Inputs**: `/data/services/openclaw/state/habits/morning-checkin-<date>.json` (artifacts older than 48hr are eligible) + `/data/services/openclaw/state/habits-history.jsonl` (resolution state) + `/home/claude/kg-automation/scripts/habits/migrations/phase3-schedule.yaml` (day-of-week metadata).
- **Outputs**: `sweeper-tick-<date>.json` (overwrite per-day at `/data/services/openclaw/state/habits/`) + `sweeper-ledger.jsonl` (append-only) + `auto_skipped` events appended to `habits-history.jsonl` + Vikunja `POST /tasks/<id>` for day-specific habits (advances `due_date` to next designated weekday EOD-ET).
- **Idempotency (FR-005)**: re-running the sweeper for the same `(task_id, original_checkin_date_et)` is a no-op. The sweeper scans history for an existing `auto_skipped` event matching the pair before appending.
- **Issue #112 regression-prevention**: any Vikunja `due_date` PUT MUST end with explicit ET offset (`-04:00`/`-05:00`), NOT `Z`. The sweeper re-uses `set_due_dates.ISO_EOD_PATTERN` for validation before any HTTP call.
- **Failure resilience**: per-habit Vikunja failures DO NOT abort the tick. The tick continues with remaining habits, records the failure in `errors[]`, and exits status `partial` (exit code 1). Sweeper-fatal errors (schedule load failure, etc.) produce `exit_status: failure` with exit code 2.
- **Health check**: `/data/services/openclaw/state/habits/sweeper-tick-<today-ET>.json` — `exit_status=success` with `started_at_utc` within the last ~24 hours; `errors=[]`. See `kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md`.
- **Source in repo**: `scripts/habits/sweeper.py` (~700 lines) + `scripts/office2/felix-habit-sweeper.{service,timer}`
- **Runbook**: `docs/runbooks/habits-ops.md`
- **Mission context**: `kitty-specs/habit-day-specific-scheduling-01KT48Y6/spec.md`

### Felix Health Check (#676, 2026-07-08)
- **Deployed by**: #676 / mission `deterministic-monitoring-checks-01KX1XNW`
- **Type**: systemd user timer + oneshot service (no LLM — the existing bash health check's assertions are reused unchanged; only the execution path moves off the Sonnet `main` agent)
- **Schedule**: twice daily via `felix-health-check.timer` (`OnCalendar=*-*-* 11:00:00` + `OnCalendar=*-*-* 23:00:00`, `Persistent=true`) — matches the two removed crons' `0 11 * * *` / `0 23 * * *`, cadence unchanged (FR-010)
- **Per-tick invocation**: `felix-health-check.service` runs `/usr/bin/python3 -m scripts.office2.felix_health_check.run`, which subprocesses (never `exec`s) `/home/claude/helper-scripts/health-check.sh` and classifies the result with failure-wins precedence (`FAILURES_DETECTED` > `ALL_HEALTHY` > `UNKNOWN`/`SCRIPT_MISSING`)
- **Source in repo**: `scripts/office2/felix_health_check/` (package: `__init__.py`, `run.py`, `tests/`)
- **Purpose**: replaces the two openclaw crons `health-check-morning` / `health-check-evening`, which ran the same bash check but **through a full Sonnet `main` session** (mostly cache-write cost, ~$12/mo, NFR-003). The new timer creates zero `main` sessions per run (NFR-002, verified via `openclaw cron runs`).
- **Alert path**: ntfy.sh push on any non-healthy outcome (`FAILURES_DETECTED` / `UNKNOWN` / `SCRIPT_MISSING`), Title `Felix Health Check — office2`, Priority `high`, full (bounded/truncated) output. Healthy runs are silent — only a signal-file stamp, no push. **Delivery-channel change**: WhatsApp → ntfy (research R5 — a non-agent timer avoids re-coupling to the openclaw/WhatsApp messaging capability being removed). An ntfy-send failure is logged (journal + signal file `delivery` field), non-fatal.
- **Health check (self)**: `/data/services/openclaw/felix-health-check/last-run.json` — `status`, `ran_at_utc`, `exit_code`, `delivery`.
- **Cron removal**: `health-check-morning` / `health-check-evening` are removed via `openclaw cron rm <id>` by the deploy manifest's entrypoint (`scripts/deploy/deploy-deterministic-monitoring-checks.py`), strictly after the new timer is installed, smoke-tested, enabled, and verified active — never before (avoids a double-alert or missed-check window around 11:00/23:00).
- **Contract**: `kitty-specs/deterministic-monitoring-checks-01KX1XNW/contracts/health-check-runner.contract.md`

### Felix Trust Scan (#683, 2026-07-10)
- **Deployed by**: #683 / mission `felix-truthful-reporting-01KX6MN5` (WP05)
- **Type**: systemd user timer + oneshot service (deterministic Python — no LLM calls; the scan is fully rule-based)
- **Schedule**: every 15 minutes via `felix-trust-scan.timer` (`OnBootSec=5min`, `OnUnitActiveSec=15min`, `Persistent=true`) — the NFR-002 detection-cycle ceiling
- **Per-tick invocation**: `felix-trust-scan.service` runs `/usr/bin/python3 -m scripts.trust.run_trust_scan --json`, the single entrypoint driving both sub-scans
- **Purpose**: the detection half of the Felix Truthful Reporting Guardrails (the doctrine half is a set of AGENTS.md prompt edits, not a service). Two deterministic scans:
  1. **Cron-drift detection** (`scripts/trust/cron_baseline.py` + `cron_drift_detector.py`) — enumerates live OpenClaw crons (`openclaw cron list --json`) and diffs them against the committed approved-cron baseline at [`approved-crons.json`](<./data/approved-crons.json>), matched on `(name, agent_id)`. This is the **load-bearing, agent-independent** guard against `main` creating unrequested standing infrastructure (FR-003) — it needs no agent cooperation to catch a violation.
  2. **Completion-assertion verification** (`scripts/trust/completion_assertion.py` + `assertion_verifier.py`) — reads completion-assertion records auto-emitted by artifact-creation helpers (starting with the Vikunja task helper) and checks each asserted artifact id against its owning system (a real existence check for `vikunja_task`; an `unverifiable_kind` warning for kinds with no cheap check today).
- **Alert path**: every finding renders to an `Alert` (`scripts/trust/alert_render.py`) and emits via the `#701` unified alert bus (shared `felix-alert` topic — no parallel channel, C-002). Seen-findings state (`scripts/trust/state.py`) alerts on first observation, re-alerts every 24h while a finding persists, and emits one info-level `drift_resolved` alert when it clears; fingerprints are versioned by the baseline's content hash so editing the baseline re-evaluates every finding.
- **Fail-safe / exit-code contract (NFR-001)**: **timer mode** (this unit's `ExecStart`) always exits `0` — an internal fault is caught per sub-scan, recorded in `errors[]`, and surfaced as `ok:false` in the JSON summary, never a non-zero process exit (no systemd failed/restart-loop risk). **Preflight/explicit mode** (`--preflight`/`--once`, used by the deploy self-test) may exit `2` on a hard scan-inability fault. Finding drift itself is never a non-zero exit in either mode.
- **Explicit non-goal**: a pure verbal completion claim that creates no artifact and emits no assertion is not detectable by either scan — that residual is doctrine-only (FR-001) until outbound-message/request logging exists (FR-006 blind spot).
- **Source in repo**: `scripts/trust/` (`cron_baseline.py`, `cron_drift_detector.py`, `completion_assertion.py`, `assertion_verifier.py`, `state.py`, `alert_render.py`, `run_trust_scan.py`) + `scripts/office2/felix-trust-scan.{service,timer}`
- **Deploy**: `deploys/queued/truthful-reporting-detector.yaml` + `scripts/deploy/deploy-truthful-reporting.py` — installs the units, enables the timer, runs a preflight self-test, and verifies the WP01 truthful-reporting doctrine landed in the deployed `main` `AGENTS.md` via a triggered `agent-prompt-sync.service` run.
- **Rebaseline**: not required (gap #621 — `audit.sh` does not hash deployed `AGENTS.md`; the detector code is not a hashed baseline either).
- **Health check (self)**: `/data/services/trust/state/seen-findings.json` (seen-findings state, written atomically each non-dry-run tick) plus the per-tick JSON scan summary (`{ok, drift_findings, assertion_findings, alerts_emitted, errors}`).
- **Runbook**: [Trust Reporting Detector Operations](<../runbooks/trust-reporting-detector.md>)
- **Mission context**: `kitty-specs/felix-truthful-reporting-01KX6MN5/spec.md`

### Credential Health Check (#115, 2026-05-11)
- **Deployed by**: #115
- **Type**: systemd user timer + oneshot service (no LLM — pure deterministic Python script)
- **Schedule**: daily 13:00 UTC via `credential-health-check.timer` (`OnCalendar=*-*-* 13:00:00`, `Persistent=true`)
- **Per-tick invocation**: `credential-health-check.service` runs `/usr/bin/python3 -m credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json`
- **Source in repo**: `scripts/security/credential_health_check/` (package: `__init__.py`, `manifest.py`, `cadence.py`, `signals.py`, `github_writer.py`, `vikunja_writer.py`, `orchestrator.py`, `__main__.py`)
- **Purpose**: closes R-003 — automated credential expiry/cadence tracking. For fixed-cadence credentials, alerts 30 days before the review boundary. For `monitor-activity` credentials (`tailscale-auth`, `whatsapp-session`), alerts on activity-signal drift.
- **Alert path**: paired GitHub issue + Vikunja task. The issue is the audit trail; the task's `due_date = boundary − 7 days` drives the existing escalation engine's WhatsApp pressure window. Activity-staleness alerts are GitHub-only (no Vikunja task — drift is "look at it now," not "rotate by date").
- **Quickstart / runbook**: `kitty-specs/credential-expiry-health-check-01KRCF92/quickstart.md` (mission-local; promote to `docs/runbooks/credential-health-check-ops.md` in a follow-up if operational learnings accumulate).

### Credential Liveness Probe (#572, 2026-06-09)
- **Deployed by**: #572
- **Type**: systemd user timer + oneshot service (no LLM — deterministic Python + `gog` CLI probe)
- **Schedule**: every 6 hours via `credential-liveness-probe.timer` (`OnCalendar=*-*-* 00,06,12,18:00:00`, `Persistent=true`)
- **Source in repo**: `scripts/office2/credential-liveness-probe.{service,timer}`; deploy script: `scripts/office2/deploy/credential-liveness-probe.sh`
- **Purpose**: OAuth credential liveness probe — issues a cheap `gog calendar list` call per monitored credential and files a GitHub issue on `invalid_grant`. Surfaces dead refresh tokens within ≤6h instead of waiting for user-facing failure.
- **Alert path**: GitHub issue only. Title prefix `credential-liveness-routine-7day:` for expected 7-day Testing-app cycle expiry; `credential-liveness-unexpected:` for out-of-cycle revocations. Issue body includes the exact `gog-reauth.sh` recovery command.
- **Depends on**: `openclaw-gateway.service`, `network-online.target`; consumes `gog-credentials-keyring`
- **Runbook**: [Google Workspace Operations](<../../runbooks/google-workspace-ops.md>) §Common issues → "Automatic detection (post-#572)"

## Schema v1.1 Fields

As of F016, `service-inventory.json` includes additional fields on each service entry to support change control governance:

| Field | Type | Purpose |
|-------|------|---------|
| `risk_tier` | integer (0-4) | Risk classification per the five-tier taxonomy in `data/change-risk-taxonomy.json`. Determines which guardrail protocol applies to changes affecting this service. |
| `dependencies` | array of strings | Services this entry depends on. Used by the pre-flight checklist (`docs/runbooks/governance/pre-flight-checklist.md`) to assess blast radius before a change. |
| `health_check` | object | Defines how to verify the service is healthy after a change. Used by post-change verification (`docs/runbooks/governance/post-change-verification.md`). Contains `command` and `expected` fields. |
| `config_files` | array of strings | Filesystem paths to configuration files for this service. Referenced during pre-flight to ensure config backups exist before changes. |

These fields are consumed by the governance runbooks — not by runtime automation. The visual dependency graph is rendered in `docs/design/architecture/service-dependencies.view.md`.

### Felix-Vikunja Sync Driver (#518, full-poll + project layer + URL config via #520)
- **Deployed by**: #518; extended by #519 (touchpoint migration) and #520 (Mission C — full-poll, project layer, URL config)
- **Type**: systemd user timer + oneshot service (deterministic Python — no LLM calls)
- **systemd unit**: `felix-vikunja-sync.timer` + `felix-vikunja-sync.service` (user unit under claude)
- **Schedule**: `OnUnitInactiveSec=300s` (5 minutes after the previous tick exits), `OnBootSec=120s`, `Persistent=true`
- **Runs as**: claude user
- **ExecStart**: `cd /home/claude/kg-automation && python3 -m scripts.sync.driver`
- **Source in repo**: `scripts/sync/`
- **Vikunja base URL**: read from `scripts/common/vikunja_config.py` at every cycle start. Resolution order: `VIKUNJA_BASE_URL` env var first; `/data/services/openclaw/config/vikunja-base-url.txt` second. Raises `VikunjaConfigError` if both are absent. The file is mode 0644 (world-readable; NOT a secret). Must be created at deploy time before enabling the timer.
- **Post-#520 pipeline (7 phases)**:
  1. Phase 0 — preamble: reads token, freshness, task_cache, project_cache, guard_state, and the Vikunja base URL
  2. Phase 1 — fetch: `GET /tasks/all` + `GET /projects` (full poll every tick; no `updated_since` delta)
  3. Phase 2 — diff: 3-way set-diff (in_vikunja_only / in_both / in_cache_only) for both task and project layers → produces `divergences`, `first_observation_task_ids`, `deleted_task_ids`, `project_events`, and `LayerSummary`
  4. Phase 3 — classify: UC-1..UC-4 classification on task divergences (unchanged from #518)
  5. Phase 4 — emit: conflict-events.jsonl writes + WhatsApp dispatch for unsafe task events; project events written to `last-tick.json` layer_summary only (no WhatsApp, no JSONL)
  6. Phase 5 — update: compute new_task_cache + new_project_cache in memory
  7. Phase 5b — deletion-cleanup: for each deleted task_id: append `task_deleted` to habits-history.jsonl, prune phase3-schedule.yaml, cache removal handled in Phase 6
  8. Phase 6 — complete: atomic writes of task_cache, project_cache, guard_state, freshness, last-tick (PerTickHealthRecord with LayerSummary)
- **Project layer**: audit/discovery role — new/changed/deleted projects are stored in `project-cache.json` for downstream consumption (future missions may act on project state). Project events do NOT trigger WhatsApp pings.
- **Read-only against Vikunja**: the driver never writes to Vikunja. All task mutations continue via the existing touchpoints (scripts/habits/, scripts/escalation/, etc.).
- **State directory**: `/data/services/openclaw/state/sync/` — freshness.json, task-cache.json, project-cache.json, guard-state.json, conflict-events.jsonl, last-tick.json, last-tick.errors.jsonl
- **Health check**: `cat /data/services/openclaw/state/sync/last-tick.json | jq '.completed_at_utc, .cycle_error'` — expect timestamp within ~6 minutes and `null` cycle_error
- **Downstream consumers (post-#519 touchpoint migration)**: 6 scripts read task state from task-cache.json via `scripts/common/sync_cache.py` instead of calling Vikunja directly — habits: morning_checkin_list.py (TP-07), query_active_habits_v2.py (TP-03), set_due_dates.py (TP-04), reconcile_completions.py (TP-02); escalation: reconcile_completions.py (TP-10); enrichment: reconcile_completions.py (TP-12). No silent fallback — stale cache beyond SLA_NORMAL (900s) raises OSError.
- **URL config dependency**: the driver and all 6 touchpoints above read the Vikunja base URL from `scripts/common/vikunja_config.py` (introduced by #520 Mission C), which resolves via the `VIKUNJA_BASE_URL` env var or `/data/services/openclaw/config/vikunja-base-url.txt`.
- **Authoritative JSON**: see `felix-vikunja-sync-driver` entry in `data/service-inventory.json`
- **Runbook**: `docs/runbooks/sync-driver-ops.md`

### WhatsApp Channel (F004)
- **Deployed by**: F004
- **Type**: OpenClaw channel (Baileys — unofficial WhatsApp Web protocol)
- **Account**: Kent's personal cell (617) 930-0916 — linked device
- **DM policy**: `allowlist` — `allow_from = ["+16179300916"]`. Inbound DMs from the operator phone number are accepted and routed to the main agent via an `embedded_run` keyed `agent:main:whatsapp:direct:+16179300916`; DMs from any other number are silently ignored. (The previous `disabled` setting matched the v2026.3.24 runtime; per the `restore-whatsapp-dm-reply-delivery-01KTVVHH` (#588) reconciliation, the deployed openclaw.json uses `allowlist` with the operator number.)
- **Group policy**: `allowlist` — no group chats by default
- **Session storage**: `~/.openclaw/credentials/whatsapp/` (managed by OpenClaw)
- **No external credentials**: Baileys session is managed internally, not in the credential store
- **No new ports**: Baileys uses outbound WebSocket only
- **Risk acceptance**: Baileys is unofficial; account ban risk accepted (see `security-posture.md`)
- **DM runtime path**: see the [`whatsapp-dm-reply`](<./data-flows.md>) entry in `data-flows.md` (and the corresponding flow in `data-flows.json`) for the full inbound→reply round-trip semantics.
- **Runbook**: `docs/runbooks/whatsapp-ops.md`
