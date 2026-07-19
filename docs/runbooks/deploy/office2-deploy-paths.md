---
title: office2 Deploy Paths — Surface Partition (reference)
doc_type: reference
audience: agents_and_humans
status: approved
last_updated: '2026-07-19'
---

# office2 Deploy Paths — Surface Partition

## Purpose

office2 has **more than one mechanism that gets a repo change onto the box**, and
they look competing but actually **partition the surface** — each owns a distinct
class of change. This reference states, for any given change, **which mechanism
delivers it**, so a planner does not assume (as the abandoned #325 planning attempt
did) that everything needs a `deploys/queued/*.yaml` manifest. This is the
reconciliation the #636 keystone asked for; the felix-deployer mechanics live in
[`discipline.md`](./discipline.md) and [`../deployment.md`](../deployment.md), and
the pull-path operator steps in [`../agent-prompt-sync-ops.md`](../agent-prompt-sync-ops.md).

The machine-readable source of truth for both mechanisms (units, paths, the
slug→deploy-dir map) is
[`service-inventory.json`](../../design/architecture/data/service-inventory.json);
the audited-surface/rebaseline map is
[`audited-surfaces.json`](../../design/architecture/data/audited-surfaces.json).
When this doc and those JSON files disagree, the JSON wins.

## The mechanisms

### 1. `felix-deployer` — the governed manifest pipeline

Consumes `deploys/queued/*.yaml`, applies under a tier-aware safety gate via the
shared library `scripts/deploy/lib/`, then writes a durable per-deploy record
`deploys/applied/<NNNN>-<slug>.yaml` (with `apply_mode`, `applied_at`, and a
deferred `rebaseline` stamp — #688). Units: `felix-deployer.{service,timer}`
(5-min tick). It owns **anything that needs a tier-guarded, recorded,
rebaseline-aware apply**: OpenClaw cron jobs, systemd units/drop-ins, service
config, venvs, Python-helper *installs to office2 paths*, and the deploy library
itself. Full contract: [`discipline.md`](./discipline.md).

### 2. `agent-prompt-sync` — the pull-based prompt copier

A 5-min oneshot (`agent-prompt-sync.{service,timer}`, script
`scripts/openclaw/deploy/deploy_agent_prompts.py`) that advances the office2
checkout to `origin/main` (race-immune fast-forward, #667) and **MD5-copies the
agent workspace prompt files** — `AGENTS.md`, `IDENTITY.md`, `SOUL.md`,
`TOOLS.md`, `USER.md` — from `scripts/openclaw/agents/<slug>/` to
`/data/services/openclaw/<deploy-dir>/` on drift. It owns **agent prompt file
content only**. It does **not** restart OpenClaw (agents read prompts at
session-init, so a running DM lane needs a rotate + gateway restart to pick up a
main-agent prompt change), and it writes **no `deploys/applied/` record** — only an
append-only JSONL audit log (`/data/services/openclaw/deploy/agent-prompt-sync.jsonl`)
and a liveness pointer (`last-tick.json`). See the audit-parity note below.

**Sibling:** `agent-skill-sync` (#775) is the identical pattern for agent
`SKILL.md` files → `/home/claude/.openclaw/skills/<skill>/`.

**Slug ≠ deploy-dir.** The mapping is not a standalone file — it is the
`source_in_repo` + `workspace` fields on each `services[openclaw].agents.<slug>`
object in `service-inventory.json`:

| Agent slug | Repo source | office2 deploy-dir |
|---|---|---|
| `felix-admin-capture` | `scripts/openclaw/agents/felix-admin-capture/` | `/data/services/openclaw/inbox-agent/` |
| `felix-admin-habits` | `scripts/openclaw/agents/felix-admin-habits/` | `/data/services/openclaw/habits-agent/` |
| `felix-admin-tasker` | `scripts/openclaw/agents/felix-admin-tasker/` | `/data/services/openclaw/tasker-agent/` |
| `felix-admin-escalation` | `scripts/openclaw/agents/felix-admin-escalation/` | `/data/services/openclaw/escalation-agent/` |
| `felix-admin-calendar` | `scripts/openclaw/agents/felix-admin-calendar/` | `/data/services/openclaw/calendar-agent/` |
| `main` | `scripts/openclaw/agents/main/` | `/data/services/openclaw/data/` |

### 3. self-pull — helper scripts ride the shared checkout

Python helpers under `scripts/**` (inbox/habits/intake/enrichment/common/…) are
copied by **neither** pipeline. They are read **live from the office2 checkout**
once either 5-min timer's `git pull` advances `origin/main`. There is no copy step,
no manifest, and no per-file record for a helper change — merging to `main` is the
deploy. (This is why many helper-only missions correctly ship with **no**
`deploys/queued/` manifest.)

## Surface-partition table

| Change class | Delivered by | Record written |
|---|---|---|
| Agent prompt files (`AGENTS/IDENTITY/SOUL/TOOLS/USER.md`) | **agent-prompt-sync** (pull + MD5 copy) | JSONL only (no `applied/` record) |
| Agent `SKILL.md` | **agent-skill-sync** (pull + MD5 copy) | JSONL only |
| Helper scripts under `scripts/**` | **self-pull** (live from the checkout) | none — the merge is the deploy |
| OpenClaw cron jobs | **felix-deployer** manifest | `deploys/applied/<NNNN>-*.yaml` |
| Systemd user units / drop-ins | **felix-deployer** manifest | `deploys/applied/<NNNN>-*.yaml` |
| Service config, venvs, office2-path installs | **felix-deployer** manifest (openclaw.json config may be a manual Tier-2 out-of-band change) | `deploys/applied/…` (or the out-of-band exception) |
| The deploy library `scripts/deploy/lib/**` + manifests | **felix-deployer** (self-hosting), via a **controlled bootstrap** when the change *is* the pull path (#667) | `deploys/applied/…` (`apply_mode: bootstrap` for the chicken-and-egg case) |
| First install of the sync/deployer units themselves | **operator one-time / bootstrap** — neither running mechanism | bootstrap record |

**Boundary in one line:** felix-deployer owns anything needing a *tier-guarded,
recorded, rebaseline-aware* apply; agent-prompt-sync (+ agent-skill-sync) owns
agent prompt/skill **content**; helper scripts ride **self-pull**.

## Not a deploy path: drift-check enforcement

`scripts/openclaw/enforcement/drift_check.py` (mission 028,
[agent-workspace-reconciliation.md](../agent-workspace-reconciliation.md)) is a
separate **drift-detection/enforcement** concern — it *compares* deployed agent
workspaces against the repo baseline and alerts on conflicts (daily 06:00 UTC
cron). **agent-prompt-sync (#567) is the authoritative repo→office2 copier**; do
not plan a deploy against drift_check. Note that drift_check's `check` mode still
performs last-author-wins *remediation* (it can copy in either direction to
resolve drift), so it is not purely read-only — but it is enforcement-oriented,
not the primary delivery path. The #766 defect (the cron had used a Mac-only SSH
alias on-host) was **fixed** (commit `fac206f1`, 2026-07-18): drift_check now reads
the office2 workspace files locally when running on-host, so enforcement is
functional. Do not treat drift_check as a deploy path.

## Audit-parity note (open — see #636 recommendation)

The two recorded mechanisms are **asymmetric on audit granularity**:

- **felix-deployer** writes a durable per-deploy `deploys/applied/<NNNN>-*.yaml`
  record and (for audited surfaces) a `rebaseline` stamp.
- **agent-prompt-sync** writes **no per-deploy record** — only the per-file JSONL
  `copy` entries (`{agent_slug, filename, src_md5, dst_md5_before, dst_path}`) and
  a liveness pointer.

This is partly **by design**: agent prompts are an *unmonitored* audited surface —
`audited-surfaces.json` sets `openclaw-agent-prompts.rebaseline_required: false`
with `affected_baselines: []`, because `security-monitor/audit.sh` hashes only
`openclaw.json` and the OpenClaw cron list, **never** the deployed `AGENTS.md`
(the #621 gap). So a prompt-only
deploy has no baseline, no rebaseline, and no `applied/` record — only the JSONL
trail.

**Recommendation (documented, not yet built):** bring the pull path to record
parity — emit a lightweight per-deploy record (or fold prompt deploys into the
`applied/`-style ledger) so "an agent prompt changed on office2" is auditable at
*deploy* granularity, consistent with the bedrock Foundation-2 "extend the guard,
not fork it" intent. This is a code change with a design choice (record shape,
whether to also close the #621 hashing gap), so it is **surfaced for a decision**
rather than implemented here; **[#799](https://github.com/kentonium3/kg-automation/issues/799)**
tracks the implementation.

## Cross-references

- [`discipline.md`](./discipline.md) — the felix-deployer manifest contract (canonical).
- [`../deployment.md`](../deployment.md) — rebaseline mechanics (watermark #685,
  `expected_baselines`, applied-record stamp #688), deploylock, controlled bootstrap.
- [`../agent-prompt-sync-ops.md`](../agent-prompt-sync-ops.md) — operator steps for the pull path.
- [`../agent-workspace-reconciliation.md`](../agent-workspace-reconciliation.md) —
  the drift-*enforcement* layer (mission 028; #766 on-host-read fix landed 2026-07-18).
- [`../../design/felix-bedrock-stabilization.md`](../../design/felix-bedrock-stabilization.md)
  — Foundation 2, the #636 problem statement.
