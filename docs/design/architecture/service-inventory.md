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
| Vikunja | Docker (compose) | `vikunja/vikunja:0.24.6` | 3456 | 100.92.197.90 | `vikunja.service` (system, oneshot → `docker compose up -d`) | `/data/services/vikunja/data` |
| Obsidian Sync | Native | `ob` v0.0.8, `ob sync --continuous` | — | — | `obsidian-sync.service` (system, runs as `kgale`) | `/home/kgale/second-brain/notes` |
| Transcribe API | Docker (GPU) | `transcribe-transcribe` | 8787 | 100.92.197.90 | `transcribe.service` | `/data/services/transcribe` |
| OpenClaw Gateway | npm-global | `v2026.3.24` | 18789 | 127.0.0.1 | `openclaw-gateway.service` (user) | `/data/services/openclaw/data` |
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
| Habit Report (weekly) | Sunday 6PM ET | OpenClaw cron → felix-admin-habits | claude | Weekly habit pattern report via WhatsApp |
| Incomplete Task Detection | Every 4 hours (`0 */4 * * *`) | OpenClaw cron → felix-admin-tasker | claude | Poll Inbox for flat tasks |
| Escalation Check (daily) | 8:00 AM ET daily | OpenClaw cron → felix-admin-escalation | claude | Overdue task escalation via WhatsApp |
| Doc Audit Poll | Every 60 minutes (top of hour UTC) | `felix-doc-auditor.timer` (systemd) → `/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py` (#343 scripts-first driver) | claude | Process Doc Audit / Weekly Doc Audit issues |
| Second Brain Sync | Every 15 min | `second-brain-sync.timer` (systemd) | kgale | Bidirectional git sync for non-vault content |
| Felix Core Digest | Every 15 min | `felix-core-digest.timer` (systemd) | claude | Agent activity log summarization → Obsidian digests |

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
- **APIs covered**: Gmail, Calendar, Drive, Contacts (People API), Sheets, Docs — all six validated end-to-end on 2026-05-13.
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
- **Model**: `anthropic/claude-haiku-4-5` (optimizable) — validated 2026-04-09
- **Purpose**: Autonomous Obsidian inbox processing — classifies content, routes to vault locations, creates Vikunja tasks, writes processing logs
- **Schedule**: 4x daily via OpenClaw cron (7 AM, 12 PM, 5 PM, 10 PM ET)
- **Processing logs**: `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
- **Vikunja projects used**: Inbox (tasks), Research (research requests), Goals (goal declarations)
- **Privacy boundary**: `04-Growth/_private/` is never accessed
- **Runbook**: `docs/runbooks/inbox-ops.md`
- **Updated by**: `#256-scope-discipline-guardrails` (2026-05-13) — adds explicit "no unsanctioned reads/edits" prose to AGENTS.md Step 5a + Step 6 after T011 SC-003 verification of #253 surfaced haiku making unsanctioned `edit` attempts on parse_failure notes. `#253-step-5a-6-consolidation` (2026-05-13) — collapses AGENTS.md Step 5a and Step 6 into single-call orchestrator helpers (`handle_marker_cleanup.py`, `handle_parse_failures.py`); applies the deterministic-work-into-scripts principle. `#254-atomic-write-perm-preservation` (2026-05-13) — fixes `_atomic_write` in both marker scripts to preserve target mode (and default new files to `0o664`) so cross-user access by ob (Obsidian Sync daemon, runs as kgale) is not broken by claude-orphaned `0o600` files. `#185-inbox-capture-dedup` (2026-05-12) — adds routing-log dedup + parse-failure halt-and-surface. Previously: `027-inbox-pre-scan-helper` (2026-04-11).

#### State files

- **Routing log** (`~/second-brain/agents/state/inbox-routing.jsonl`, introduced by #185) — Append-only JSONL. Each line records one successful route: `{filename, issue_number, vikunja_task_id, routed_at, note_excerpt}`. The classifier in prescan.py consults this log on every cron tick and filters already-routed filenames out of `unprocessed_paths` invisibly to the agent. This is the load-bearing dedup substrate; it decouples dedup from frontmatter parseability (which was the failure mode in the original #185 bug where a malformed note got filed nine times). NOT git-tracked; backed up by the nightly Restic job.

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
  4. Consults the routing log (`scripts/inbox/routing_log.py` → `~/second-brain/agents/state/inbox-routing.jsonl`) and filters already-routed filenames out of `unprocessed_paths`; surfaces those in `dedup_skipped`
  5. Flags any cleanly-parseable note that still carries a stale `> [!error] felix-capture:` marker in `marker_cleanup_needed`
  6. Archives stale (>7 day) processed files to `{{VAULT_INBOX_PROCESSED}}`
  7. Returns a JSON result with unprocessed paths, parse_failures, dedup_skipped, marker_cleanup_needed, archived entries, and warnings

  When the helper reports zero unprocessed files, zero parse failures, and zero markers to clean up, the agent replies with the single token `IDLE` and takes no further action.

  - **Language**: Python
  - **Dependencies**: `scripts/vault/paths.json`, `scripts/inbox/routing_log.py`
  - **Invoked by**: `felix-admin-capture` step 1
  - **Helper log**: `/home/claude/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md` (daily rotation, append-only)

- **routing-log module** (`scripts/inbox/routing_log.py`, introduced by #185) — Stdlib-only Python module exposing `RoutingLogReader` and `RoutingLogWriter`. Read path is used by prescan.py; write path is wrapped by `append_routing_entry.py`. Atomic appends; reader caches per-tick.

- **handle_parse_failures.py** (script, #253) — End-to-end orchestrator for parse-failure handling. Invoked by AGENTS.md §Step 6 as a single CLI call when `parse_failures` is non-empty. Reads prescan JSON (`@<path>` argument); files-or-dedups the inbox-quality GitHub issue via direct function import of `file_inbox_quality_issue.{find_existing_open_issue,file_new_issue}`; then injects parse-error markers per entry via direct function import of `inject_parse_error_marker.inject_marker`. Subprocess-out to `log_action.py` for structured action-log entries (`inbox_quality_issue_filed`/`_deduped`, `parse_error_marker_injected`, `parse_failure_handling_error`). Exits non-zero on any per-entry failure (continues processing the rest). Replaces the prior multi-step bash recipe to collapse the prompt-execution surface.

- **handle_marker_cleanup.py** (script, #253) — End-to-end orchestrator for marker-cleanup. Invoked by AGENTS.md §Step 5a as a single CLI call when `marker_cleanup_needed` is non-empty. Reads prescan JSON; strips markers via direct function import of `strip_parse_error_marker.strip_marker`. Logs `marker_stripped` per success and `marker_cleanup_error` per failure via `log_action.py` subprocess.

- **inject_parse_error_marker.py** (script, #185 → #253 → #254) — Library + thin-CLI module exposing `inject_marker(path, issue_number, date_str)`. Inserts/refreshes the marker after the frontmatter close fence (or at line 0 for no-frontmatter notes). Idempotent + atomic. As of #253, invoked indirectly via `handle_parse_failures.py`'s direct function import rather than via the AGENTS.md prompt's bash. As of #254, `_atomic_write` preserves the original target file's mode (or applies `0o664` for new files) so cross-user access by ob (kgale-owned daemon, member of `secondbrain` group) is not broken by claude-orphaned `0o600` perms. Emits one stderr `INFO: atomic_write <path> mode=0o<mode> (preserved|new)` log line per successful write.

- **strip_parse_error_marker.py** (script, #185 → #253 → #254) — Library + thin-CLI module exposing `strip_marker(path)`. Removes the marker (and its trailing blank line) when the note now parses cleanly. No-op if no marker present. As of #253, invoked indirectly via `handle_marker_cleanup.py`'s direct function import. As of #254, `_atomic_write` preserves mode identically to `inject_parse_error_marker.py`.

- **append_routing_entry.py** (script, #185) — CLI wrapper around `RoutingLogWriter.append`. Invoked by AGENTS.md §Step 5b exactly once per fully-routed note (after all blocks have been routed, before the atomic `status: processed` write).

- **file_inbox_quality_issue.py** (script, #185 → #253) — Title-prefix-deduped GitHub issue writer. Exposes library functions `find_existing_open_issue()`, `file_new_issue(parse_failures, date_str)`, `build_title()`, `build_body()` alongside its thin `main()` CLI wrapper. As of #253, invoked indirectly via `handle_parse_failures.py`'s direct function imports rather than via the AGENTS.md prompt's bash. Uses `gh issue list --search 'in:title "Inbox quality:"'` + a `startswith()` post-filter to find an existing open issue; if found, returns the existing number without filing. If not, files a new issue against `kentonium3/kg-automation` with title `Inbox quality: <N> notes with parse errors — YYYY-MM-DD`. Body is truncated with an overflow footer if it would exceed the 60K-char safety budget.

### Felix Admin Habits Agent (F009; scripts-first morning + reply flow #371)
- **Deployed by**: F009
- **Refactored by**: `#371` / mission `habits-checkin-reply-scripts-first-01KS86ZQ` (morning + reply ports to scripts-first; mirrors #309 escalation pattern)
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-habits`
- **Workspace**: `/data/services/openclaw/habits-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-habits/`
- **Model**: `anthropic/claude-sonnet-4-6`
- **Purpose**: Daily habit check-in delivery, completion tracking, weekly pattern reports, on-demand track record queries, habit management (add/pause/remove). **Post-#371**: thin orchestrator. The morning tick invokes `scripts/habits/morning_checkin_list.py` (script writes the canonical morning-list artifact + emits the formatted WhatsApp message verbatim); the reply tick invokes `scripts/habits/parse_morning_reply.py` (deterministic mapping of Kent's reply against the persisted morning list) and routes the resulting `(task_id, state)` tuples to the existing `scripts/habits/record_completion.py`. The narrow LLM judgment surface `scripts/habits/judgment/disambiguate_reply.py` is invoked ONLY for ambiguous reply tokens (mirrors the #343 doc-audit judgment pattern).
- **Schedule**: Morning check-in at 7:05 AM ET daily, weekly report Sunday 6 PM ET
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

### Felix Admin Escalation Agent (F019; JSONL state migration #309)
- **Deployed by**: F019
- **Refactored by**: `#309` / mission `migrate-escalation-to-jsonl-state-model-01KS5R4D` (Phase 6 of ADR-0002)
- **Type**: OpenClaw agent (sub-agent of the gateway)
- **Agent name**: `felix-admin-escalation`
- **Workspace**: `/data/services/openclaw/escalation-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-escalation/`
- **Model**: `anthropic/claude-sonnet-4-6`
- **Purpose**: Overdue task escalation — detects tasks past due date, delivers level-appropriate WhatsApp alerts, tracks escalation state. **Post-#309**: per-project JSONL state log at `/data/services/openclaw/state/escalation/<project-slug>-escalation-history.jsonl` is the canonical state source. `[Felix-Escalation]` comments are still written during the soak (C-001) but are no longer parsed by the agent.
- **Skills**: escalation, vikunja-api
- **Autonomy**: Assisted (Level 1)
- **Trigger**: Cron (daily), manual
- **Schedule**: Daily at 8:00 AM ET via OpenClaw cron (`0 12 * * *`)
- **Delivery**: WhatsApp to +16179300916
- **Privacy boundary**: `04-Growth/_private/` is never accessed

#### State files (post-#309)

- **Per-project escalation history** (`/data/services/openclaw/state/escalation/<project-slug>-escalation-history.jsonl`, introduced by #309) — Append-only JSONL. One record per escalation event. Schema: `domain=escalation`, `state ∈ {level_sent, snoozed, dismissed, done, rescheduled}`, `source ∈ {agent, reconcile, backfill, kent_reply, operator_repair}`. Filename-based per-project partition (NFR-003, research D2). Backed up by the nightly Restic job.
- **Pre-backfill snapshot** (`/data/services/openclaw/state/escalation/pre-phase6-snapshot.json`, introduced by #309) — Written exactly once before the historical backfill runs. Captures the full `[Felix-Escalation]` comment surface per task so the operator can verify no Felix-driven Vikunja comments were lost during replay. Rollback substrate per quickstart.md § Rollback.

#### Helpers (post-#309)

Per-helper metadata mirrors `docs/design/architecture/data/service-inventory.json` (the authoritative record) — see the corresponding `config_files[*]` entries there for `runs_on`, `invoked_by`, `writes_to`, `reads_from`, `credentials`, and `updated_by` fields.

- **scripts/escalation/record_completion.py** (script, introduced_by #309, updated_by #309) — Atomic three-write helper per ADR-0002 / research D6. Performs the Vikunja side-effect FIRST (WhatsApp send + `[Felix-Escalation]` comment write during the C-001 soak, `PATCH done=true` for done events, `PATCH due_date` for kent_reply-sourced rescheduled events), then calls `state_log.append("escalation", record)` for the canonical JSONL write LAST. Invoked by the agent at every event; also invoked by `reconcile_completions.py --no-vikunja` for synthetic records. Exposes `record_event()` and `idempotent_record_event()`. FR-002, FR-009.
  - **runs_on**: `office2`
  - **invoked_by**: `felix-admin-escalation` agent; `scripts/escalation/reconcile_completions.py`
  - **writes_to**: Vikunja API (`PUT /tasks/<id>/comments`, `PATCH /tasks/<id>`); `/data/services/openclaw/state/escalation/<project-slug>-escalation-history.jsonl`
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
- **scripts/escalation/backfill_jsonl_from_comments.py** (one-time helper, introduced_by #309, updated_by #309) — Operator-driven historical backfill (FR-006). Reads existing `[Felix-Escalation]` comments from Vikunja escalation-subscribed tasks. Writes the pre-backfill snapshot BEFORE any JSONL writes. Replays parseable comments to `state_log.append` with `source=backfill`, `timestamp=comment.created` (or `comment_date+12:00:00Z` best-effort). Idempotent on re-run via the Phase 2 (task_id, date, state) dedup. Malformed comments are NOT replayed; they surface in the backfill report. Read-only on Vikunja (GET only).
  - **runs_on**: `office2`
  - **invoked_by**: `kent_via_cli`
  - **writes_to**: `/data/services/openclaw/state/escalation/pre-phase6-snapshot.json` (one-shot, before any JSONL writes); JSONL state log (`source=backfill`)
  - **reads_from**: Vikunja API (`GET /projects`, `GET /projects/<id>/tasks`, `GET /tasks/<id>/comments`)
  - **credentials**: `vikunja-api`
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

### Felix Doc Auditor (#105 deployed 2026-05-10; refactored to scripts-first driver in #343, 2026-05-21; Moment 0 drift interpretation added in #362, 2026-05-22)
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
- **Judgment moments (post-#362, four moments; cron-path invocation corrected by #391)**: Moment 0 — **drift_interpretation** (`scripts/doc_audit/judgment/drift_interpretation.py`, introduced by #362) classifies each mapped drift event as PROPOSED_EDIT / JUDGMENT_REQUIRED / NO_CHANGE_NEEDED before any GitHub issue is filed. The cron-path invocation flows through `signals/drift_event.py::DriftEventSignalSource.commit()` → `routing/drift_moment0.py::route_drift_event()` (corrected by #391 — was previously documented as `handle_drift_events.py::process_events()`, which is the library/CLI replay surface, not the cron entry point). Moment 1 — **tier_classification** (Tier-A vs Tier-B vs judgment). Moments 2 and 3 — **debt_body_generation** and **cross_file_implication** (unchanged from #343).
- **Judgment prompts**: checked-in markdown artifacts at `scripts/doc_audit/prompts/*.prompt.md` (drift_interpretation [#362], tier_classification, debt_body_generation, cross_file_implication) — replaces the historical runtime `~/.openclaw/skills/doc-audit/SKILL.md` (no longer loaded at runtime; retained only as historical reference).
- **API path**: driver reads `/data/services/openclaw/secrets/anthropic` (0600, claude:claude) at tick start and calls `api.anthropic.com` directly via the `anthropic` Python SDK; the openclaw-gateway is NOT in the runtime path.
- **Health check**: structured `last-tick.json` at `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json` (expected `status: "success"` within last 2 hours); see `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/tick-signal.contract.md`. The per-tick prose activity log at `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` remains as a human-readable summary.
- **Purpose**: processes Doc Audit and Weekly Doc Audit issues automatically; commits high-confidence edits directly, files docs-debt issues for judgment items, detects missing artifacts
- **Approval mechanism (Level 1)**: WhatsApp summary message + reply parsing (`approve`/`reject`/`skip`); 2-hour timeout = default deny
- **Concurrency lock**: GitHub label `status:in-progress` on the in-flight audit issue (unchanged across #343)
- **Identity**: `kg-felix-bot` (classic PAT via gh CLI auth store) — unchanged across #343
- **Authoritative JSON**: see `felix-doc-auditor` entry in `data/service-inventory.json`
- **Runbook**: `docs/runbooks/doc-auditor-driver-ops.md` (operator quick-reference + troubleshooting; supersedes the prior `doc-auditor-ops.md` for the post-#343 driver implementation; post-#362 includes a "Moment 0 — drift interpretation" section, ledger CLI examples, and rollback procedure)

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

### Credential Health Check (#115, 2026-05-11)
- **Deployed by**: #115
- **Type**: systemd user timer + oneshot service (no LLM — pure deterministic Python script)
- **Schedule**: daily 13:00 UTC via `credential-health-check.timer` (`OnCalendar=*-*-* 13:00:00`, `Persistent=true`)
- **Per-tick invocation**: `credential-health-check.service` runs `/usr/bin/python3 -m credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json`
- **Source in repo**: `scripts/security/credential_health_check/` (package: `__init__.py`, `manifest.py`, `cadence.py`, `signals.py`, `github_writer.py`, `vikunja_writer.py`, `orchestrator.py`, `__main__.py`)
- **Purpose**: closes R-003 — automated credential expiry/cadence tracking. For fixed-cadence credentials, alerts 30 days before the review boundary. For `monitor-activity` credentials (`tailscale-auth`, `whatsapp-session`), alerts on activity-signal drift.
- **Alert path**: paired GitHub issue + Vikunja task. The issue is the audit trail; the task's `due_date = boundary − 7 days` drives the existing escalation engine's WhatsApp pressure window. Activity-staleness alerts are GitHub-only (no Vikunja task — drift is "look at it now," not "rotate by date").
- **Quickstart / runbook**: `kitty-specs/credential-expiry-health-check-01KRCF92/quickstart.md` (mission-local; promote to `docs/runbooks/credential-health-check-ops.md` in a follow-up if operational learnings accumulate).

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
