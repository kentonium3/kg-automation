# Phase 0 — Research

**Mission**: `felix-calendar-subagent-extraction-01KTTA33`
**Probed**: 2026-06-11 (during plan phase, per DIR-015)

## Probes executed

| Probe | Substrate | Result |
|---|---|---|
| Live `wc -c` of `/data/services/openclaw/data/AGENTS.md` (main) on office2 | `ssh office2-claude` | 25,982 chars — matches local repo copy (already fully synced; bug is structural not sync-lag) |
| Live `wc -c` of subagent AGENTS.md files on office2 | `ssh office2-claude` | habits 15,043; inbox (capture) 15,288; tasker 14,994; escalation 12,366 — **all four exceed 12K hard cap** |
| Live `cat /home/claude/.openclaw/openclaw.json` on office2 | `ssh office2-claude` | Confirmed schema; `agents.list[]` contains main + 4 subagents; **no felix-admin-calendar** yet; **felix-doc-auditor NOT registered** (different substrate per `reference_felix_doc_auditor_ops`) |
| Live `ls /home/claude/.openclaw/agents/` on office2 | `ssh office2-claude` | 7 dirs: `claude`, `felix-admin-capture`, `felix-admin-escalation`, `felix-admin-habits`, `felix-admin-tasker`, `felix-doc-auditor`, `main` — note doc-auditor has a dir but is not in openclaw.json (driver-shaped) |
| Live `ls /data/services/openclaw/` on office2 | `ssh office2-claude` | Includes `data/` (main workspace), `inbox-agent`, `habits-agent`, `tasker-agent`, `escalation-agent`, `felix-doc-auditor-driver`, plus support dirs (config, secrets, state, deploy, felix-core-digest-signals, felix-heartbeat-gate) |
| Local repo `scripts/openclaw/` listing | filesystem | Modules: `__init__.py`, `agents/`, `deploy/`, `enforcement/`, `heartbeat_gate/`, `helpers/`, `install.sh`, `observation/`, `openclaw-gateway.service`, `skills/` — **no `openclaw.json` in repo** |
| Local repo `scripts/openclaw/agents/` listing | filesystem | 6 agents: capture, escalation, habits, tasker, doc-auditor, main (no calendar yet) |
| `scripts/openclaw/agents/main/AGENTS.md` lines 250–440 | filesystem | Calendar event creation handler + clarification reply handler confirmed present at lines 259–440 |
| `docs/runbooks/openclaw-agent-setup.md` | filesystem | Two-registration model confirmed: (1) `docs/constitution/agent-registry.json`, (2) `~/.openclaw/openclaw.json` |
| `docs/design/architecture/data/audited-surfaces.json` | filesystem | `openclaw-agent-prompts` (patterns include `scripts/openclaw/agents/*/AGENTS.md` etc) and `openclaw-config` (patterns include `scripts/openclaw/openclaw.json` — aspirational, file not in repo) both require rebaseline. Canonical rebaseline command: `ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'` |
| `docs/design/architecture/data/signal-to-doc-map.json` | filesystem | Field is `id` (NOT `signal`). Mission change classes: `mission-agent-prompt-changed` (5 targets), `mission-service-added-or-modified` (4 targets), `mission-runbook-added` (2 targets). Targets enumerated in plan.md § Documentation Sync. |
| `docs/constitution/agent-registry.json` | filesystem | Shape: `{version, updated, updated_by, agents: {<slug>: {team, scope, autonomy_level, model, model_policy, model_rationale, log_verbosity, deployed_feature, registered, transition_history}}}` |

## Findings

### F-01 — All subagents already exceed the 12K cap; only main is fatally affected

Subagent AGENTS.md sizes on office2: habits 15,043; capture 15,288; tasker 14,994; escalation 12,366. All four are over the documented 12K hard cap but only `main`'s truncation produces the visible WhatsApp reply-relay failure. Hypothesis: for subagents the truncated tail isn't load-bearing (subagents are single-domain and front-load their handler logic); for main the delegation routing instructions for habits/calendar/etc. live in the tail.

**Implication for the mission**: NFR-004 (`felix-admin-calendar/AGENTS.md` < 12K) is the right defensive discipline even though it's not strictly required for the new subagent to function. It prevents this mission from creating another future cliff.

**Implication for follow-on work**: inbox-processing delegation in main is at the cliff edge (lines 197–216 of the original main/AGENTS.md). After this mission, if `main/AGENTS.md` tightening leaves comfortable headroom (e.g., <10K), no follow-on needed. If it lands just under 12K, file a follow-on issue to either extract inbox-router into its own subagent or tighten main further.

### F-02 — `agent-prompt-sync.service` (#567) auto-syncs agent prompt files

Discovered via `audited-surfaces.json` and confirmed via repo memory. The deploy_path for `openclaw-agent-prompts` is `scripts/openclaw/deploy/deploy_agent_prompts.py + agent-prompt-sync.service (auto)`. This means:

- We do NOT need to manually copy `AGENTS.md`/`IDENTITY.md`/`SOUL.md` to office2. The 5-min timer handles it.
- Deploy script can trigger an immediate sync via `systemctl --user start agent-prompt-sync.service` to skip the wait.
- The deploy script's "artifact copy" step becomes "trigger sync + verify post-sync file presence."

### F-03 — `openclaw.json` lives only on office2

The audited-surfaces.json `openclaw-config` entry's patterns (`scripts/openclaw/openclaw.json`, `scripts/openclaw/openclaw.*.json`) are aspirational — neither file exists in the repo. Live probe confirmed openclaw.json exists at `/home/claude/.openclaw/openclaw.json` on office2 and contains the gateway auth token in cleartext (`gateway.auth.token`), which is a reason it's not committed.

**Implication for the deploy script**: the openclaw.json mutation step must run via SSH on office2, not as a local commit. The flow is:
1. `ssh office2-claude 'cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak-<ts>'`
2. `ssh office2-claude 'jq ".agents.list += [<new-entry>]" ~/.openclaw/openclaw.json.bak-<ts> > ~/.openclaw/openclaw.json'`
3. `ssh office2-claude 'jq . ~/.openclaw/openclaw.json'` (validate parse + presence)

**Implication for repo audit**: the `openclaw-config` audited-surface pattern is dead until/unless we commit openclaw.json — separate decision out of scope for this mission. The new agent registration still triggers `openclaw-config-drift` from the audit side, which is what the rebaseline step addresses.

### F-04 — Office2 workspace path convention

Live probe of `/data/services/openclaw/` confirmed the pattern `<role>-agent` for subagent workspaces:

| Agent | Workspace path |
|---|---|
| `main` | `/data/services/openclaw/data/` (default workspace, no override) |
| `felix-admin-capture` | `/data/services/openclaw/inbox-agent/` |
| `felix-admin-habits` | `/data/services/openclaw/habits-agent/` |
| `felix-admin-tasker` | `/data/services/openclaw/tasker-agent/` |
| `felix-admin-escalation` | `/data/services/openclaw/escalation-agent/` |
| `felix-doc-auditor` | `/data/services/openclaw/felix-doc-auditor-driver/` (driver-shaped, not openclaw-managed) |
| **`felix-admin-calendar` (NEW)** | **`/data/services/openclaw/calendar-agent/`** |

`agentDir` (the openclaw config dir, not workspace) follows pattern `/home/claude/.openclaw/agents/<slug>/agent`. felix-admin-calendar → `/home/claude/.openclaw/agents/felix-admin-calendar/agent`.

### F-05 — felix-doc-auditor regression verification is NOT a DM round-trip

Per `reference_felix_doc_auditor_ops` and confirmed by openclaw.json probe (doc-auditor not listed): doc-auditor is a Python driver run on an hourly systemd user timer. Its health signal is `last-tick.json` freshness. The spec's regression set named it alongside the OpenClaw subagents, but its verification path is:

```bash
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq .'
```

Within ~1h post-deploy, `last-tick.json` should show a fresh tick. If it doesn't, that's a separate failure not caused by this mission's changes (no shared substrate). The smoke runbook makes this distinction explicit.

### F-06 — Model assignment convention

Subagents use `anthropic/claude-haiku-4-5` (capture, habits, tasker) except `felix-admin-escalation` uses `anthropic/claude-sonnet-4-6`. main also uses Sonnet 4.6.

**Decision**: felix-admin-calendar uses `anthropic/claude-haiku-4-5`. Rationale: the workflows (gog command synthesis from a structured payload, validator-driven clarification matching) are routine — pattern-matching with a deterministic validator, no complex judgment. Same shape as capture / habits / tasker. If empirical accuracy is poor in production, the `model_policy: optimizable` field in agent-registry.json signals it's eligible for re-evaluation.

### F-07 — Branch model under rc41 #1784

Live probe of `setup-plan --json` confirmed: `current_branch`, `target_branch`, `base_branch`, `planning_base_branch`, `merge_target_branch` all = `kitty/mission-felix-calendar-subagent-extraction-01KTTA33` (the coord branch). This is the rc41 #1784 behavior: spec-kitty sees the coord branch as its own merge target during planning. Real merge to main happens via FF at lifecycle handoffs (apply sparingly per `feedback_speckitty_1784_workaround_sparingly` — at tasks-finalize handoff is the natural inflection).

## Decisions log

| Decision | Choice | Rationale | Alternatives rejected |
|---|---|---|---|
| Architectural shape | New felix-admin-calendar subagent | Spec discovery Q1 = Option A | Compress in place (B); lazy-load (C, upstream); raise cap (D, brittle) |
| Scope boundary | Tight 1:1 move + broader charter | Spec discovery Q2 = A+C | Strict move with no charter; broad immediate scope |
| Budget target | < 12K hard cap | Spec discovery Q3 = A | < 14-15K effective budget; extract inbox too |
| Smoke approach | Hybrid (config checks + journal watch + operator DM checklist) | Plan Q1 = B; matches feedback_live_integration_tests | Operator-only (A); fully scripted (C) |
| Model for felix-admin-calendar | `anthropic/claude-haiku-4-5` | F-06: routine deterministic-helper-driven workflow; matches capture / habits / tasker | Sonnet 4.6 (overkill for the workload) |
| openclaw.json edit substrate | SSH+jq in-place on office2 | F-03: file not in repo; secrets in file | Commit openclaw.json (secret exposure); manual operator edit (less reliable) |
| Inbox-router extraction | Out of scope; close follow-on if needed | Spec discovery Q3 (Option A); F-01 (margin determines need) | Bundle into this mission (scope creep) |
| felix-doc-auditor verification | last-tick.json check, NOT DM round-trip | F-05 | Treat as OpenClaw subagent (wrong substrate) |
