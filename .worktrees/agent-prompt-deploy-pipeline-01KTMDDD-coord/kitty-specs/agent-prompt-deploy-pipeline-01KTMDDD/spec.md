# Specification: Agent Prompt Deploy Pipeline

**Mission**: `agent-prompt-deploy-pipeline-01KTMDDD`
**Mission ID**: `01KTMDDDGGY00S3S3VFGK0Z6P9`
**Target branch**: `main`
**Mission type**: `software-dev`
**Issue**: kentonium3/kg-automation#567 (parent epic #563; sibling sub-issues #566, #568)
**Created**: 2026-06-08

## Purpose (Stakeholder Summary)

Today, when a spec-kitty mission merges a change to a Felix agent's prompt files (e.g., the `inbox-calendar-and-aspiration-routing-01KTHHXS` change to `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`), the change lands in `main` but does NOT reach the running agent on office2. The deployed prompt at `/data/services/openclaw/<deploy-dir>/AGENTS.md` is stale. Today's measurement: 52,942 bytes in the repo vs 40,009 bytes deployed for capture; comparable drift for habits (#561). The running agents have been silently improvising on pre-merge prompts, including missing the load-bearing routing/preserve instructions that mission #563 traced as the root cause of silent inbox content loss.

This mission delivers an automated pull-based pipeline on office2 that, every 5 minutes, refreshes the office2 git clone of kg-automation and copies any drifted agent prompt files into their deployed locations. Outcome: every merge to `main` that touches a Felix agent prompt file lands on the running agent within one cron-tick window, with no operator intervention. The stranded #558 and #561 changes deploy automatically on first successful tick.

## User Scenarios & Testing

### Primary scenario: a merge reaches the running agent

1. A spec-kitty mission merges to `main`. The merge changes
   `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (e.g., adds a new
   routing rule).
2. Within 5 minutes, the user-level systemd timer on office2 fires its next tick.
3. The tick runs `git fetch && git pull --ff-only origin main` inside
   `/home/claude/kg-automation`, advancing the clone to the new commit.
4. The tick invokes the deploy helper, which iterates Felix agents declared
   in `service-inventory.json`, MD5-compares each in-scope source file under
   the agent's `source_in_repo` against the file at the same name under the
   agent's `workspace` (deploy path), and atomically copies any drifted file.
5. The next openclaw session-init for that agent (next cron tick of capture
   at 7am/noon/5pm/10pm ET) reads the new prompt; the agent behaves on the
   new instructions.

### Exception scenario: git pull fails

1. Network blip, branch divergence, or any other reason causes
   `git pull --ff-only` to fail.
2. The helper exits non-zero, logs a `git_pull_failed` entry to the JSONL
   audit log, and does NOT proceed with file copies (stale-but-consistent
   beats partially-updated).
3. The timer remains active; the next tick is a free retry. Once the
   underlying git issue resolves, sync resumes automatically.

### Exception scenario: a single file copy fails

1. Disk full, permissions issue, or other I/O failure during an atomic copy.
2. `os.replace` either succeeds atomically OR leaves the destination
   untouched plus a leftover temp file at `<deploy_path>/<name>.tmp.<pid>`.
3. The helper logs a `copy_failed` entry per affected file, continues with
   remaining files (per-agent and across agents), and exits non-zero overall
   so the systemd unit registers a failure for journalctl visibility.
4. Next tick is a free retry; on success, the temp file is replaced by the
   next successful write (or remains harmlessly until pruned manually).

### Exception scenario: a new agent prompt file is added

1. A future mission adds `scripts/openclaw/agents/felix-admin-tasker/NEW_FILE.md`
   (also matching the in-scope filename set, e.g., a new canonical prompt
   file). The mission also updates `service-inventory.json` if the file set
   convention is centralized there; otherwise the helper picks it up via the
   in-scope filename allowlist.
2. On the next tick, the helper sees the new file in the source path,
   no matching destination, and copies it (mtime/MD5 mismatch by definition
   when destination is absent).
3. New agent dirs added under `services[openclaw].agents.<slug>` in
   `service-inventory.json` are automatically discovered on the next tick.

### Operator scenario: dry-run inspection

1. Operator runs `python3 -m scripts.openclaw.deploy.deploy_agent_prompts --dry-run`
   from `/home/claude/kg-automation`.
2. Helper computes the drift set and prints what WOULD change, without
   touching any deployed file or writing any JSONL entry.
3. Operator can confirm "yes, this is the deploy I expect" before letting
   the timer run.

### Operator scenario: single-agent sync

1. Operator runs `python3 -m scripts.openclaw.deploy.deploy_agent_prompts --agent felix-admin-capture`.
2. Helper syncs ONLY that agent's files; ignores the others.
3. Useful for forcing a sync during incident response without waiting for
   the timer tick.

## Domain Language

| Term | Definition |
|---|---|
| **Agent slug** | The directory name under `scripts/openclaw/agents/` AND the key under `services[openclaw].agents` in `service-inventory.json`. Examples: `felix-admin-capture`, `felix-admin-habits`, `main`. NOT the deploy-dir name. |
| **Deploy dir** | The directory under `/data/services/openclaw/` where the running agent reads its workspace files. Mapped from the agent slug via `service-inventory.json`'s `workspace` field. Examples: `inbox-agent`, `habits-agent`, `data` (= main). |
| **Prompt file** | A file in the in-scope filename set that constitutes the running agent's workspace context. Sync-managed by this pipeline. |
| **In-scope filename set** | The fixed list of filenames the helper considers for sync, scoped to canonical agent-prompt files. Initial set: `AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`. |
| **Excluded filename pattern** | A filename or glob the helper MUST NOT sync regardless of presence in repo: `HEARTBEAT.md` (runtime state), `*.tmpl` (templates), `*.bak*` (backups), `GOVERNANCE.md` (manually managed, no repo source). |
| **Sync tick** | One execution of the systemd-timer-driven helper: `git pull --ff-only` + per-agent diff + per-file atomic copy + audit log append. |
| **Drift** | A repo file and its deployed counterpart with different MD5s, OR a repo file with no deployed counterpart. |
| **Atomic copy** | Write source bytes to `<deploy_path>/<name>.tmp.<pid>`, `os.replace` to `<deploy_path>/<name>`. Preserves prior file mode (octal). Does NOT change ownership. |
| **Audit log** | Append-only JSONL at `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`. One entry per file action (copy, skip, error) plus one entry per tick summary. |

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | Helper iterates Felix agent slugs declared under `services[openclaw].agents.*` in `docs/design/architecture/data/service-inventory.json`. For each agent with both `source_in_repo` AND `workspace` fields populated, the helper considers the agent in-scope for sync. Agents missing either field are skipped with a warning log entry. | Specified |
| FR-002 | For each in-scope agent, the helper enumerates files in the `source_in_repo` directory and selects those matching the In-Scope Filename Set. Files matching any Excluded Filename Pattern are skipped without warning. | Specified |
| FR-003 | For each selected source file, the helper computes the MD5 of the source file bytes and the MD5 of the destination file at `<workspace>/<filename>` (or treats destination as drift if absent). | Specified |
| FR-004 | When MD5s differ, the helper performs an atomic copy: writes source bytes to `<workspace>/<filename>.tmp.<pid>`, fsyncs the file descriptor, calls `os.replace` to move it to `<workspace>/<filename>`. The destination file's mode (per `os.stat().st_mode`) is preserved if a prior destination existed. | Specified |
| FR-005 | When MD5s match, the helper records a `skip` action in the audit log and proceeds to the next file. | Specified |
| FR-006 | Each tick begins by running `git fetch && git pull --ff-only origin main` inside `/home/claude/kg-automation`. If either git command exits non-zero, the helper logs `git_pull_failed` to the audit log with the captured stderr and exits non-zero WITHOUT attempting any file copies. | Specified |
| FR-007 | The helper accepts a `--dry-run` flag. In dry-run mode, the helper computes the drift set and prints one line per drift-candidate file to stdout. No writes occur to any deployed file or to the audit log. Exit 0 on success regardless of drift count. | Specified |
| FR-008 | The helper accepts a `--agent <slug>` flag. When provided, the helper restricts iteration to that single agent only. Behavior is otherwise identical to a full run. | Specified |
| FR-009 | The helper writes one JSONL line per file action (copy / skip / error / git_pull_failed) and one summary line per tick to `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`. Each line includes ISO-8601 UTC timestamp, agent slug, filename, action, MD5 (where applicable), error string (where applicable). | Specified |
| FR-010 | The helper exits 0 when all in-scope copies succeeded (or no drift was present) and the git pull succeeded. Exits 1 when one or more file copies failed but git pull succeeded. Exits 2 when git pull failed. | Specified |
| FR-011 | A user-level systemd timer at `~/.config/systemd/user/agent-prompt-sync.timer` invokes a sibling oneshot service unit at `~/.config/systemd/user/agent-prompt-sync.service` every 300 seconds after the previous tick exits (`OnUnitInactiveSec=300s`), with `OnBootSec=120s` and `Persistent=true`. | Specified |
| FR-012 | The sibling service unit invokes `/usr/bin/python3 -m scripts.openclaw.deploy.deploy_agent_prompts` with `WorkingDirectory=/home/claude/kg-automation` and `Type=oneshot`. StandardOutput and StandardError are routed to journal. | Specified |
| FR-013 | Repo source files for the timer and service unit live at `scripts/openclaw/deploy/agent-prompt-sync.timer` and `scripts/openclaw/deploy/agent-prompt-sync.service`. Operator deploys them once with `cp` to `~/.config/systemd/user/` and `systemctl --user daemon-reload && systemctl --user enable --now agent-prompt-sync.timer`. Subsequent unit file changes require a manual re-copy + reload (the helper does NOT self-deploy its own systemd units). | Specified |
| FR-014 | The mission update to `service-inventory.json` adds `source_in_repo: "scripts/openclaw/agents/main/"` to the `main` agent entry under `services[openclaw].agents.main` to enable the helper to pick it up. The mission ALSO adds a top-level service entry for the new sync helper itself (`type: systemd-timer`, `host: office2`, etc.). | Specified |
| FR-015 | The helper creates `/data/services/openclaw/deploy/` directory (and any missing parent) on first run if absent, using `pathlib.Path.mkdir(parents=True, exist_ok=True)`. Ownership and mode of the created directory follow the systemd user's umask. | Specified |
| FR-016 | The helper NEVER deletes a file in any deploy dir. Files that exist in a deploy dir but NOT in the source dir are left untouched (no warning, no log entry). | Specified |
| FR-017 | The helper NEVER triggers an openclaw restart or any other service action. Synced files reach the running agent via the agent's normal session-init read on its next scheduled tick. | Specified |

## Non-Functional Requirements

| ID | Description | Status |
|---|---|---|
| NFR-001 | A normal (no-drift) tick completes in under 2 seconds wall time, measured from systemd-service-start to exit, on office2 with the current 5-agent inventory. Validated via journal timestamp delta. | Specified |
| NFR-002 | The helper imports only Python 3.10+ standard library modules. No `requests`, `httpx`, `pydantic`, or any non-stdlib dependency. | Specified |
| NFR-003 | Test coverage for the helper module (excluding the systemd unit files) is at least 90% line coverage and at least 85% branch coverage, gated in CI via pytest-cov. | Specified |
| NFR-004 | The audit log at `/data/services/openclaw/deploy/agent-prompt-sync.jsonl` is append-only. The helper never rewrites existing lines. Log size growth is bounded by tick frequency × per-tick entry count; expected steady-state is ~6 summary lines per hour plus drift-day spikes. No log rotation in scope; operator may add one later via standard logrotate if size becomes a concern. | Specified |
| NFR-005 | Helper invocation form is `python3 -m scripts.openclaw.deploy.deploy_agent_prompts` per [[feedback_helper_m_invocation_form]]. The systemd service unit MUST use this form. Documentation and runbooks MUST use this form. | Specified |
| NFR-006 | The helper is idempotent: running it twice in succession with no intervening change produces zero copy actions on the second run. | Specified |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | The helper runs as the `claude` user on office2 (claude has no sudo). It must NOT require any operation that needs sudo or root. Deploy dirs at `/data/services/openclaw/<dir>/` are already writable by claude (verified during discovery). | Specified |
| C-002 | The helper must NOT modify, create, or delete `HEARTBEAT.md` in any deploy dir. HEARTBEAT.md is runtime state owned by a separate process; competing writes would cause data corruption. | Specified |
| C-003 | The helper must NOT touch `GOVERNANCE.md` in `/data/services/openclaw/data/` (the main agent's deploy dir). It is manually maintained outside the repo. | Specified |
| C-004 | The helper must NOT touch `.tmpl` files (templates) or `*.bak*` files (backups) in any source or destination dir. | Specified |
| C-005 | All work in this mission must be `git pull --ff-only`-safe. The helper must NEVER use `git pull` without `--ff-only`, must NEVER use `git merge`, and must NEVER use `git reset` on the office2 clone. If a non-ff state arises, the operator handles it manually. | Specified |
| C-006 | Per CLAUDE.md, this mission must NOT modify any file under `.github/workflows/`. The decision to use a pull (office2-timer) architecture over a push (GitHub Actions) architecture was explicitly made during discovery to honor this constraint. | Specified |
| C-007 | Risk tier 3 (Standard). No state-changing system config beyond user-level systemd units. No service/credential/data-flow topology changes beyond adding the new helper's service-inventory entry. | Specified |

## Success Criteria

1. After mission merge + operator one-time install of the systemd timer, an edit to any file matching the In-Scope Filename Set in `scripts/openclaw/agents/<slug>/` on `main` propagates to the corresponding `/data/services/openclaw/<deploy-dir>/<filename>` on office2 within 5 minutes, measured by MD5 match.
2. On the first successful tick post-deploy, the stranded #558 AGENTS.md content (capture) and #561 AGENTS.md content (habits) appear deployed on office2 (MD5 of repo file == MD5 of deployed file).
3. Over a 7-day soak window post-deploy, `journalctl --user -u agent-prompt-sync.service --since "7 days ago" | grep -c failed` returns 0 (no service failures other than legitimate `git_pull_failed` during ops-known network blips).
4. A controlled edit-and-commit-and-wait test from clean state: edit a trivial line in `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`, commit + push to main, observe deployed MD5 update within 5 minutes 0 seconds of git push completion.
5. A drift-day spike (deploy of an actual #566 + #561 + future mission set) propagates without any per-file copy failure, with audit-log entries showing one `copy` action per drifted file and one summary line per affected agent.

## Key Entities

| Entity | Fields | Source |
|---|---|---|
| **AgentInventoryEntry** | `slug` (str), `source_in_repo` (path), `workspace` (path), `purpose` (str). The minimal projection of `services[openclaw].agents.<slug>` the helper reads. | `docs/design/architecture/data/service-inventory.json` |
| **SyncAction** | `timestamp` (ISO-8601 UTC), `agent_slug` (str), `filename` (str), `action` (enum: copy / skip / error / git_pull_failed / tick_summary), `src_md5` (hex str, optional), `dst_md5` (hex str, optional), `error` (str, optional). One JSONL line per. | Helper emits to `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`. |
| **TickSummary** | `timestamp` (ISO-8601 UTC), `tick_id` (UUID), `agents_processed` (int), `files_copied` (int), `files_skipped` (int), `files_errored` (int), `git_head_after_pull` (sha), `exit_code` (int), `duration_ms` (int). One JSONL line per tick. | Helper emits at tick end. |

## Assumptions

- The systemd-user units for office2 are an established pattern with several precedents (`felix-vikunja-sync.timer`, `felix-doc-auditor.timer`, etc.); this mission follows the existing pattern verbatim.
- `/home/claude/kg-automation` on office2 is a healthy `main`-tracking clone of `kentonium3/kg-automation` and stays that way. Verified at design time (clone at commit `a45d09c6`, matching local Mac; status clean modulo untracked `scripts/habits/state/`).
- Deploy paths under `/data/services/openclaw/<dir>/` are writable by the `claude` user. Verified at design time.
- All openclaw agents read their workspace prompt files at session-init only (no hot-reload); a prompt change does NOT take effect until the agent's next cron tick. This is acceptable — propagation latency is bounded by both sync cadence (≤5 min) AND agent cron cadence (varies by agent), but is operator-tolerable.
- The 5-minute polling cadence is acceptable. If a future mission needs faster propagation, the cadence can be tuned without re-specifying the helper.
- Audit log size growth is acceptable without rotation for the foreseeable future (~6 lines/hour steady-state).
- `os.replace` provides sufficient atomicity guarantees on the office2 filesystem (ext4). `os.fsync` is called on the file descriptor before replace but NOT on the destination directory descriptor — full crash-durability would prevent rare last-tick-window loss but adds overhead; next-tick retry covers this case adequately for prompt files (which are version-controlled in git).

## Out of Scope

- **Agent prompt content changes** (those are missions #566, #561, #558).
- **Defensive prescan inverse check** for archive anomalies (that is sibling #568).
- **Push-side architecture** — GitHub Actions / git post-receive hooks — explicitly ruled out during discovery in favor of office2 pull.
- **Faster-than-5-minute propagation** — current cadence accepted; not in scope to tune unless soak shows it's insufficient.
- **Hot-reload of agent prompts** (no openclaw API exists for this; agents always read at session-init).
- **Sync of non-agent-prompt files** — the helper is scoped to the In-Scope Filename Set only; auxiliary scripts under `scripts/inbox/`, `scripts/habits/`, etc. are out of scope (those reach office2 via the same `git pull` step but are read directly from `/home/claude/kg-automation/scripts/...` by their own consumers; no copy needed).
- **Deletion sync** — files removed from a repo agent dir are NOT deleted from the deploy dir (FR-016). Operators handle retirements explicitly.
- **Log rotation** of the audit JSONL — not in scope; can be added later via logrotate if size becomes a concern.
- **Restart of openclaw or any other service** on prompt change (FR-017).
- **Helper self-deployment of its own systemd units** — manual one-time install + manual re-copy on rare unit changes.
- **felix-doc-auditor prompt deployment** — felix-doc-auditor is a top-level service (`type: systemd-timer`), not an openclaw agent under `services[openclaw].agents.*`. The helper naturally excludes it. If a future mission promotes felix-doc-auditor to a deployed agent prompt model, this helper picks it up by virtue of the service-inventory entry shape — no helper code change needed.

## Architecture Documentation Updates (DIR-005)

Per Felix Constitution Directive 5 and project Directive DIR-005, this mission updates the following architecture surfaces before merge:

| File | Update |
|---|---|
| `docs/design/architecture/data/service-inventory.json` | Add new top-level service entry for `agent-prompt-sync` (type: `systemd-timer`, host: `office2`, schedule, exec_start, source_in_repo for the timer and service unit, health_check pointing at last entry of the audit JSONL). Update `services[openclaw].agents.main` to add `source_in_repo: "scripts/openclaw/agents/main/"`. Set `updated_by` to include this mission slug. |
| `docs/design/architecture/data/signal-to-doc-map.json` | Add or extend a `change_class` entry for `agent-prompt-changed` mapping to the affected docs (service-inventory entries for the affected agent + this helper). |
| `docs/design/architecture/service-inventory.md` | Add a narrative section: "Agent Prompt Deploy Pipeline" describing the pull-based architecture, slug→deploy-dir mapping rule (currently buried in `[[reference_office2_agent_deploy_paths]]` memory), and the manual one-time install procedure. |
| `docs/runbooks/openclaw-agent-setup.md` | Add a section "Deploy pipeline" referencing the new helper and clarifying the manual unit install + verification steps. Note that subsequent prompt edits no longer require a manual file copy after the first install. |
| `docs/runbooks/agent-prompt-sync-ops.md` | New runbook. Operator-facing: install, dry-run, single-agent force-sync, reading the audit log, common failure modes (git_pull_failed, copy_failed), rollback. |

## Reference Index

- Issue: kentonium3/kg-automation#567
- Parent epic: kentonium3/kg-automation#563
- Sibling sub-issues (separate missions): #566 (Directive 6 refactor of capture), #568 (prescan inverse check)
- Memory references:
  - `[[reference_office2_agent_deploy_paths]]` — slug ≠ deploy-dir mapping
  - `[[feedback_helper_m_invocation_form]]` — `-m` invocation form mandatory
  - `[[feedback_architecture_docs_first]]` — JSON arch docs first, SSH only for gaps
  - `[[feedback_scripts_vs_llm]]` — pure deterministic helper, no LLM surface
  - `[[feedback_vikunja_sync_polling_not_webhooks]]` — Felix operational preference for polling
- Architecture: `docs/design/architecture/data/service-inventory.json` § `services[openclaw].agents.*`
- Existing systemd-user-timer precedent: `scripts/sync/systemd/felix-vikunja-sync.{service,timer}`
