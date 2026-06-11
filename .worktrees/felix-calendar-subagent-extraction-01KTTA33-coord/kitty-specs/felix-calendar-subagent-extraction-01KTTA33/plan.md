# Plan — Felix Calendar Subagent Extraction

**Mission**: `felix-calendar-subagent-extraction-01KTTA33`
**Mission ID**: `01KTTA33XZ0VG1SXQH3YD854K1`
**Mission type**: `software-dev`
**Spec**: [spec.md](./spec.md) (committed at `kitty/mission-felix-calendar-subagent-extraction-01KTTA33`)
**Origin**: kentonium3/kg-automation#579
**Branch contract**: Current/base/target = `kitty/mission-felix-calendar-subagent-extraction-01KTTA33` (rc41 #1784 behavior; FF main at lifecycle handoffs)

## Technical Context

**Language/Version**: Python 3.11 (helper scripts for deterministic verification); Bash 5.x (deploy wrapper); Markdown (agent prompt files); JSON (openclaw config, architecture data)

**Primary Dependencies**: OpenClaw 3.2.x runtime, systemd user units (`openclaw-gateway.service`), spec-kitty 3.2.0rc41 (workflow), `gog` CLI (calendar substrate, no version change), `agent-prompt-sync.service` 5-min timer (#567, syncs `scripts/openclaw/agents/<slug>/*.md` to office2 workspace)

**Storage**: No new persistent storage. Agent prompt files (filesystem). `~/.openclaw/openclaw.json` on office2 (registry edit only). Existing calendar state file `~/second-brain/agents/state/pending-calendar-clarifications.jsonl` — handler logic moves, state file path and ownership unchanged.

**Testing**: Pytest under `scripts/openclaw/agents/tests/` for char-count and openclaw.json schema-validation helpers (DIRECTIVE_034 test-first deliverable). Operator smoke DM checklist runbook for behavioral verification post-deploy.

**Target Platform**: office2 (Ubuntu 24.04 LTS); authoring on Mac. Tailscale-internal only (DIR-003).

**Project Type**: Operational infrastructure — OpenClaw agent registration + agent prompt files + bash deploy wrapper + Python verification helpers; not a standalone application.

**Performance Goals**: `main/AGENTS.md` < 12,000 chars (NFR-001); `felix-admin-calendar/AGENTS.md` < 12,000 chars (NFR-004); WhatsApp reply-relay latency p95 ≤ 30s (NFR-003).

**Constraints**: Tier 3 change-control (agent prompts + openclaw config). Audited surfaces touched: `openclaw-agent-prompts`, `openclaw-config` → rebaseline required per #557. No system crontab usage; Tailscale-only exposure. openclaw.json edited in-place on office2 via SSH+jq (not committed to repo per F-03).

**Scale/Scope**: Single new OpenClaw subagent, 5 new agent prompt files (AGENTS.md, IDENTITY.md, SOUL.md, TOOLS.md, USER.md), one modified main/AGENTS.md, one openclaw.json entry, one deploy script, two pytest helper modules, one smoke runbook, ~10 documentation surface updates.

**Branch model (rc41 #1784)**: Planning + implementation commits land on coord branch; FF main absorbs them at lifecycle handoffs (after tasks-finalize is the natural inflection).

**Deploy substrate**: `scripts/deploy/deploy-felix-admin-calendar.sh` (Bash wrapper, mission-shorthand naming per existing `deploy-fNNN.sh` / `deploy-NNN.sh` convention) following strict-order-of-operations per DIR-005.

**Auto-sync substrate**: `agent-prompt-sync.service` 5-min timer auto-copies `scripts/openclaw/agents/felix-admin-calendar/*.md` from repo checkout on office2 → `/data/services/openclaw/calendar-agent/*.md` (NEW workspace path). Deploy script triggers a manual sync run to avoid the 5-min wait.

## Summary

Move the calendar event creation handler + calendar clarification reply handler from `main/AGENTS.md` lines 259–440 into a new OpenClaw subagent `felix-admin-calendar` following the established Felix subagent pattern (`felix-admin-capture`, `-habits`, `-tasker`, `-escalation`). Tighten `main/AGENTS.md` below the 12K bootstrap context cap so the runtime stops truncating the habit-tracking delegation section that broke WhatsApp reply relay on 2026-06-09. Declare a broader calendar-substrate charter inside `felix-admin-calendar/AGENTS.md` so future calendar work (gog credential health, RRULE integration, attendee tracking) has a clear home without expanding scope today. Deploy via a strict-order-of-operations bash wrapper that auto-triggers `agent-prompt-sync.service`, edits the office2 `openclaw.json` via SSH+jq with backup, restarts `openclaw-gateway.service`, and verifies absence of truncation warnings. Operator runs a smoke DM checklist across all subagents to validate SC-001 through SC-005, then runs the canonical rebaseline command per #557.

## Charter Check

Charter loaded for plan action (compact mode). Relevant directives:

| Directive | Application to this mission |
|---|---|
| DIRECTIVE_001 (Architectural Integrity) | New `felix-admin-calendar` cleanly separates the calendar-substrate domain from main's relay role. Boundary already established by existing felix-admin-* pattern. |
| DIRECTIVE_003 (Decision Documentation) | Discovery Q1=A, Q2=A+C, Q3=A and Planning Q1=B captured in spec/plan/research; this plan IS that documentation surface. |
| DIRECTIVE_010 (Specification Fidelity) | Calendar handler content moves 1:1 from main lines 259–440 with no semantic change; charter declaration is additive. Plan stays faithful to spec's "tight 1:1 move + broader charter" decision. |
| DIRECTIVE_024 (Locality of Change) | Mission scope is bounded to the calendar extraction. Inbox-processing delegation (also at the cliff edge) deferred to follow-on per spec Q3. |
| DIRECTIVE_031 (Context-Aware Design) | `felix-admin-calendar` owns the calendar-substrate context. Its only inbound boundary is the main agent's delegation dispatch (existing pattern). Self-dispatch loop within the calendar clarification reply handler stays internal to felix-admin-calendar after the move. |
| DIRECTIVE_033 (Targeted Staging) | Each WP stages only its declared deliverables; no blanket `git add .`. |
| DIRECTIVE_034 (Test-First) | Helper-script unit tests for deterministic verification authored before deploy steps. Behavioral smoke is operator-driven runbook (the mission's risk-shape doesn't call for a synthetic-message test substrate — see Engineering Alignment Q1=B). |
| DIR-001 / DIR-002 | Linux-only target, office2. |
| DIR-003 | All Felix services Tailscale-internal. No new exposure. |
| DIR-004 | Deploy script lives at `scripts/deploy/deploy-felix-admin-calendar.sh`. |
| DIR-005 / DIR-006 | Strict order-of-operations (pre-flight → artifacts → verify → config → post-flight); no cron pause/resume. |
| DIR-007 | No system crontab usage — N/A for this mission (no new cron jobs). |
| DIR-008 | Deploy paths read live from `/home/claude/.openclaw/openclaw.json` for `workspace` and `agentDir`. felix-admin-calendar agentDir → `/home/claude/.openclaw/agents/felix-admin-calendar/agent`; workspace → `/data/services/openclaw/calendar-agent/`. |
| DIR-009 | Tier 2-style backup confirmation NOT required (Tier 3 change). Restic age check is a hygiene step in pre-flight regardless. |
| DIR-010 (c4-incremental-detail-modeling) | spec → plan → research → data-model → tasks → implement. Each layer adds concrete detail to the previous. |
| DIR-014 (Doc sync mandatory) | Explicit doc surface list in [§ Documentation Sync](#documentation-sync-dir-014) derived from signal-to-doc-map.json. |
| DIR-015 (Probe real environment in design phase) | Live office2 probes completed during plan (size of deployed `main/AGENTS.md`, openclaw.json schema, existing subagent layout, `agent-prompt-sync` substrate confirmed). Findings consolidated in [research.md](./research.md). |

No directive conflicts identified. No charter exception needed.

## Architecture

### Topology change (before → after)

```
Before:
  main agent (AGENTS.md ~26K, truncated at 12K)
    ├── delegation: capture       (lines ~197–216, at cliff edge)
    ├── delegation: habits        (lines ~217–235, TRUNCATED — root cause)
    ├── ...other sections...
    └── calendar handlers         (lines 259–440, TRUNCATED, but inline — never reached as delegation)

After:
  main agent (AGENTS.md <12K)
    ├── delegation: capture
    ├── delegation: habits        (preserved in context)
    ├── delegation: tasker
    ├── delegation: escalation
    └── delegation: calendar  →  felix-admin-calendar (NEW subagent)
                                    ├── AGENTS.md (charter + handlers)
                                    ├── IDENTITY.md, SOUL.md
                                    └── TOOLS.md, USER.md (optional)
```

### Component layout

| Path (repo) | Status | Lifecycle |
|---|---|---|
| `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` | NEW | Charter declaration + handler logic moved from `main/AGENTS.md` lines 259–440 |
| `scripts/openclaw/agents/felix-admin-calendar/IDENTITY.md` | NEW | Per `docs/runbooks/openclaw-agent-setup.md` pattern (see felix-admin-habits as canonical reference) |
| `scripts/openclaw/agents/felix-admin-calendar/SOUL.md` | NEW | Voice + privacy boundary per pattern |
| `scripts/openclaw/agents/felix-admin-calendar/TOOLS.md` | NEW | `gog` CLI references, Google Calendar API notes |
| `scripts/openclaw/agents/felix-admin-calendar/USER.md` | NEW | Kent's identity (since calendar replies go directly to user) |
| `scripts/openclaw/agents/main/AGENTS.md` | MODIFIED | Calendar lines 259–440 removed; whole-file tightening to `< 12000` chars |
| `~/.openclaw/openclaw.json` (office2) | MODIFIED (in-place via deploy script) | New `felix-admin-calendar` entry under `agents.list[]` |
| `docs/constitution/agent-registry.json` | MODIFIED | New `felix-admin-calendar` entry under `agents` dict |
| `docs/constitution/AGENT-REGISTRY.md` | MODIFIED | Markdown view of registry updated |
| `docs/design/architecture/data/service-inventory.json` | MODIFIED | New service entry for `felix-admin-calendar` per existing felix-admin-* pattern |
| `docs/design/architecture/service-inventory.md` | MODIFIED | Narrative view |
| `docs/design/architecture/service-dependencies.view.md` | MODIFIED | Dependency diagram |
| `docs/runbooks/openclaw-agent-setup.md` | VERIFY | Confirm still accurate (no schema change implied) |
| `docs/runbooks/agent-prompt-sync-ops.md` | VERIFY | Confirm still accurate |
| `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md` | NEW | Operator smoke DM checklist (regression coverage for SC-001/SC-005) |
| `docs/INDEX.md` + `docs/DEVELOPER_PORTAL.md` | MODIFIED | List new runbook |
| `docs/design/felix-capability-roadmap.md` | VERIFY/MODIFIED | Capability status if calendar is tracked there |
| `scripts/openclaw/agents/tests/test_agents_md_size.py` | NEW | Pytest helper: assert `wc -c` < 12000 for `main/AGENTS.md` and `felix-admin-calendar/AGENTS.md` |
| `scripts/openclaw/agents/tests/test_openclaw_config_schema.py` | NEW | Pytest helper: validate openclaw.json shape and presence of felix-admin-calendar entry |
| `scripts/deploy/deploy-felix-admin-calendar.sh` | NEW | Bash wrapper, strict order-of-operations |

### Deploy substrate (DIR-004 / DIR-005 / DIR-008)

**Order of operations (deploy script):**

1. **Pre-flight**
   - Verify Restic backup hygiene (log presence within 24h — Tier 3 hygiene, not gate)
   - SSH reachable to `office2-claude`
   - Local artifact presence: `scripts/openclaw/agents/felix-admin-calendar/{AGENTS,IDENTITY,SOUL,TOOLS,USER}.md`
   - `wc -c scripts/openclaw/agents/main/AGENTS.md` → assert `< 12000` (helper script)
   - `wc -c scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` → assert `< 12000` (helper script)
   - Validate local conception of openclaw.json schema (helper script — reads remote `~/.openclaw/openclaw.json` via SSH, parses)
2. **Agent prompt sync (artifacts)**
   - Trigger `agent-prompt-sync.service` manually (`systemctl --user start agent-prompt-sync.service`) instead of waiting up to 5 min
   - Verify post-sync: `wc -c /data/services/openclaw/calendar-agent/AGENTS.md` matches local; same for main
3. **openclaw.json edit (config)**
   - SSH to office2; back up `~/.openclaw/openclaw.json` to `~/.openclaw/openclaw.json.bak-<ts>`
   - Use `jq` to insert the new `felix-admin-calendar` entry into `agents.list[]`
   - Validate post-edit JSON parses and contains the new entry
4. **Service restart**
   - `systemctl --user restart openclaw-gateway.service`
   - Wait 5s, check `systemctl --user is-active openclaw-gateway.service` is `active`
5. **Post-flight**
   - `journalctl --user -u openclaw-gateway --since "<deploy-start-ts>" | grep "truncating in injected context"` → expect zero hits for `agent:main:*` sessions (NFR-002)
   - Print operator smoke DM checklist link (`docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md`)
6. **Rebaseline (separate step, operator-invoked)**
   - Canonical command from `docs/runbooks/security-baseline-ops.md`:
     `ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'`

**Rollback** (manual, printed by deploy script on any failure):
- Restore `~/.openclaw/openclaw.json` from `~/.openclaw/openclaw.json.bak-<ts>`
- `systemctl --user restart openclaw-gateway.service`
- `git revert` the agent-prompt commits; let `agent-prompt-sync.service` re-converge office2 workspace

## Implementation Concern Map

Per Constitution Directive 6 / `docs/design/helper-script-conventions.md`, deterministic vs stochastic work split:

| IC | Concern | Type | Owner | Substrate |
|---|---|---|---|---|
| IC-01 | Char-count assertion (< 12K) for `main/AGENTS.md` | Deterministic | Helper script | `scripts/openclaw/agents/tests/test_agents_md_size.py` + invoked by deploy script |
| IC-02 | Char-count assertion (< 12K) for `felix-admin-calendar/AGENTS.md` | Deterministic | Helper script | Same pytest file |
| IC-03 | openclaw.json schema validation post-edit | Deterministic | Helper script | `scripts/openclaw/agents/tests/test_openclaw_config_schema.py` + invoked by deploy script |
| IC-04 | Truncation warning absence in journal | Deterministic | Deploy script | `grep` against `journalctl` output, exit code |
| IC-05 | Backup of openclaw.json pre-edit | Deterministic | Deploy script | `cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak-<ts>` |
| IC-06 | jq-based JSON edit of openclaw.json | Deterministic | Deploy script | `jq '.agents.list += [<new-entry>]'` with validation |
| IC-07 | agent-prompt-sync trigger | Deterministic | Deploy script | `systemctl --user start agent-prompt-sync.service` |
| IC-08 | service restart + activity check | Deterministic | Deploy script | systemctl invocations |
| IC-09 | Behavioral smoke test (subagent DMs reach Kent) | Stochastic | Operator | `docs/runbooks/<mission-slug>-smoke.md` markdown checklist |
| IC-10 | `felix-admin-calendar/AGENTS.md` charter prose | Stochastic | Implementer agent | WP authoring |
| IC-11 | `main/AGENTS.md` whole-file tightening (preserve semantics) | Stochastic | Implementer agent | WP authoring |
| IC-12 | IDENTITY/SOUL/USER/TOOLS authoring | Stochastic | Implementer agent | WP authoring (follow felix-admin-habits pattern) |
| IC-13 | Documentation sync edits (architecture JSON + markdown) | Mostly deterministic structure / stochastic prose | Implementer agent | WP authoring (signal-to-doc-map provides authoritative target list) |

## Testing Strategy (DIRECTIVE_034)

Test-first deliverables (authored before production code per DIRECTIVE_034):

1. **`scripts/openclaw/agents/tests/test_agents_md_size.py`** — pytest:
   - `test_main_agents_md_under_12k()` — asserts `Path("scripts/openclaw/agents/main/AGENTS.md").stat().st_size < 12000`
   - `test_felix_admin_calendar_agents_md_under_12k()` — same assertion for the new file
2. **`scripts/openclaw/agents/tests/test_openclaw_config_schema.py`** — pytest:
   - `test_openclaw_json_has_felix_admin_calendar_entry()` — parses an openclaw.json sample (fixture under `tests/fixtures/`), asserts `felix-admin-calendar` present with required keys (`id`, `name`, `workspace`, `agentDir`, `model`)
   - `test_workspace_path_pattern()` — asserts workspace matches `/data/services/openclaw/<role>-agent` pattern
   - `test_agentdir_path_pattern()` — asserts agentDir matches `/home/claude/.openclaw/agents/felix-admin-calendar/agent`

Both test files fail initially (red state) — felix-admin-calendar files do not exist yet, main/AGENTS.md is over 12K. WPs make them green.

Behavioral verification:
- Pre-deploy: pytest green (red→green from the implementation WPs).
- Deploy-time: deploy script runs the same assertions via pytest (`pytest scripts/openclaw/agents/tests/`).
- Post-deploy: journal-watch (deploy script) + operator smoke DM checklist (runbook) cover SC-001 through SC-008.

Per `feedback_live_integration_tests`, NO synthetic-message integration substrate is introduced. The operator runbook is the canonical behavioral verification surface for this mission's DM flow.

## Documentation Sync (DIR-014)

Authoritative doc surface list pulled from `docs/design/architecture/data/signal-to-doc-map.json` for the change classes this mission triggers:

| Signal | Document target | Action |
|---|---|---|
| `mission-agent-prompt-changed` | `docs/design/architecture/data/service-inventory.json` | Add felix-admin-calendar entry (agent service) |
| `mission-agent-prompt-changed` | `docs/design/architecture/service-inventory.md` | Narrative view update |
| `mission-agent-prompt-changed` | `docs/runbooks/openclaw-agent-setup.md` | Verify still accurate |
| `mission-agent-prompt-changed` | `docs/runbooks/agent-prompt-sync-ops.md` | Verify still accurate |
| `mission-agent-prompt-changed` | `docs/design/architecture/data/audited-surfaces.json` | Verify `openclaw-agent-prompts` pattern still matches (no new pattern needed — `scripts/openclaw/agents/*/AGENTS.md` already covers new agent dir) |
| `mission-service-added-or-modified` | `docs/design/architecture/data/service-inventory.json` | (same as above) |
| `mission-service-added-or-modified` | `docs/design/architecture/service-dependencies.view.md` | Add felix-admin-calendar to dependency diagram |
| `mission-service-added-or-modified` | `docs/design/felix-capability-roadmap.md` | Verify capability status; update if calendar tracked |
| `mission-runbook-added` (smoke) | `docs/INDEX.md` | List new smoke runbook |
| `mission-runbook-added` (smoke) | `docs/DEVELOPER_PORTAL.md` | List new smoke runbook |
| (implicit from agent registration) | `docs/constitution/agent-registry.json` | Add felix-admin-calendar entry (autonomy_level, team, scope, registered date, transition_history) |
| (implicit from agent registration) | `docs/constitution/AGENT-REGISTRY.md` | Markdown view update if hand-maintained (verify generation source) |

Doc sync work is a dedicated WP near the end of the mission. Plan phase enumerates; implement phase executes.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `main/AGENTS.md` tightening removes load-bearing semantics | Medium | High (regression in another delegation flow) | Tightening WP includes a structural diff review checklist: which sections must stay, what each remaining delegation needs intact. Smoke DM checklist verifies each subagent post-deploy. |
| `felix-admin-calendar/AGENTS.md` exceeds 12K after charter prose is added | Medium | Medium (NFR-004 violation, but not immediately operationally broken given other subagents are already 12-15K and functional) | NFR-004 enforced by pytest in deploy pre-flight. WP authoring iterates until under cap. |
| `agent-prompt-sync` 5-min timer races with deploy | Low | Low | Deploy script triggers manual sync run via `systemctl --user start agent-prompt-sync.service` rather than waiting. |
| openclaw.json edit corrupts schema | Low | High (gateway service won't start) | Pre-edit backup; jq-based mutation with parse validation; service-active check post-restart with rollback path printed on failure. |
| Calendar self-dispatch loop ("calendar clarification reply handler" → "calendar event creation" via gog) breaks after move | Low | Medium (clarification flow silently fails) | The self-dispatch is conceptual within the agent's logic, not an openclaw round-trip — moving both handlers together preserves the call relationship. Smoke checklist includes a clarification round-trip DM. |
| felix-doc-auditor regression (different substrate — Python driver on systemd timer, NOT OpenClaw) | Very low | Medium | Bug + fix are scoped to OpenClaw bootstrap; doc-auditor's driver doesn't share the truncation path. Verification = `last-tick.json` updates within an hour of deploy. |
| rc41 #1784 FF-to-main timing | Known | Workflow-only | FF main absorbs coord-branch commits at lifecycle handoffs (after tasks-finalize). Operator-confirmable; not blocking. |
| Rebaseline forgotten post-deploy | Medium | Medium (audit alerts fire 24h later as false drift) | Merge commit footer required (`Rebaseline: completed at <ts>` per CLAUDE.md). Deploy script prints the canonical command in its final output. Operator runs explicitly. |

## Phase 0 — Research

See [research.md](./research.md). Highlights:

- Office2 substrate confirmed: workspace pattern `<role>-agent`; felix-admin-calendar workspace → `/data/services/openclaw/calendar-agent`.
- All 4 existing OpenClaw subagent AGENTS.md files exceed 12K (12K–15K). Truncation occurs for all but is operationally fatal only for `main` because main's delegation instructions live past the cap.
- `agent-prompt-sync.service` (#567) auto-syncs `scripts/openclaw/agents/<slug>/*.md` → `/data/services/openclaw/<workspace>/` every 5 min.
- `openclaw.json` is NOT checked into repo — lives only on office2. Deploy script edits in-place via SSH+jq.
- felix-doc-auditor is NOT an OpenClaw agent — it's a Python driver on a systemd timer. Different regression verification path.

## Phase 1 — Design

See:
- [data-model.md](./data-model.md) — the openclaw.json entry shape, the agent-registry.json entry shape, the message-payload contracts between main and felix-admin-calendar (re-asserted, not redesigned)
- [contracts/](./contracts/) — the calendar-create payload (preserved from current main handler), the openclaw.json entry contract, the runbook smoke-checklist contract
- [quickstart.md](./quickstart.md) — minimal operator walkthrough: deploy → smoke → rebaseline

## Branch Contract (restate before tasks)

- **Current branch**: `kitty/mission-felix-calendar-subagent-extraction-01KTTA33`
- **Planning/base branch**: same (coord branch carries planning artifacts per rc41 #1784)
- **Final merge target**: `main` (via FF after mission completes)
- `branch_matches_target=true` per spec-kitty's view (coord branch matches its own commit target)

## Next step

`/spec-kitty.tasks` translates this plan's deliverables into executable work packages. Plan command stops here.
