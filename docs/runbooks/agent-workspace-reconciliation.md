---
id: agent-workspace-reconciliation
doc_type: runbook
title: Agent Workspace Reconciliation
status: approved
level: howto
owners: [kent]
audience: agents_and_humans
last_validated: 2026-04-13
version: "1.0"
---

# Agent Workspace Reconciliation

Operational runbook for the automated drift enforcement system that keeps OpenClaw agent workspace files synchronized between the kg-automation repo and office2.

**Source issue**: [#166](https://github.com/kentonium3/kg-automation/issues/166)
**Mission**: 028-agent-workspace-reconciliation

## Overview

OpenClaw agents on office2 have workspace files (`AGENTS.md`, `SOUL.md`, `TOOLS.md`, `USER.md`, `IDENTITY.md`) that define their identity, capabilities, and standing orders. These files can be modified from two directions:

- **Repo side**: missions commit workspace file changes via spec-kitty workflow
- **Office2 side**: agents autonomously evolve their files ("organic evolution"), or operators manually edit them

The enforcement system uses a **three-way diff** against a baseline manifest to detect changes and automatically reconcile them using a **"last author edits wins"** strategy.

**Workspaces are self-contained.** OpenClaw loads each configured agent's prompt
files strictly from that agent's own workspace directory — there is no
`defaults.workspace` inheritance for configured agents (source-verified in
[#553](https://github.com/kentonium3/kg-automation/issues/553)). Reconciliation
therefore treats each agent's files as an independent set; there is no shared/base
layer to reconcile against. How those files are *authored* (which concern lives in
which file, which invariants must be present) is governed by the
[OpenClaw Workspace Authoring Standard](<../design/openclaw-workspace-authoring-standard.md>);
this runbook governs how the authored files stay *in sync* between repo and office2.

## Architecture

```
Repo (scripts/openclaw/agents/)     ←→     Office2 (workspace paths)
         ↕                                          ↕
    baseline-manifest.json (records last known good hashes for both sides)
         ↕
    drift-check.py (cron, daily 06:00 UTC)
         ↕
    WhatsApp + GitHub Issue (on conflict or factory transition)
```

- **Repo** is the single source of truth for tracked files
- **Baseline manifest** stores SHA256 hashes from the last reconciliation
- **Enforcement cron** runs daily, compares current hashes against baseline
- **Notifications** fire only for conflicts (both sides changed) or factory-default transitions

## Agent-to-Workspace Mapping

| Agent ID | Repo path | Office2 workspace path |
|---|---|---|
| `main` | `scripts/openclaw/agents/main/` | `/data/services/openclaw/data/` |
| `felix-admin-capture` | `scripts/openclaw/agents/felix-admin-capture/` | `/data/services/openclaw/inbox-agent/` |
| `felix-admin-habits` | `scripts/openclaw/agents/felix-admin-habits/` | `/data/services/openclaw/habits-agent/` |
| `felix-admin-escalation` | `scripts/openclaw/agents/felix-admin-escalation/` | `/data/services/openclaw/escalation-agent/` |
| `felix-admin-tasker` | `scripts/openclaw/agents/felix-admin-tasker/` | `/data/services/openclaw/tasker-agent/` |

This mapping is stored in `scripts/openclaw/enforcement/drift-check-config.json`.

**Roster reconciliation (as of #587):**

- **`felix-admin-calendar`** (added #579) is a live, deployed agent
  (`scripts/openclaw/agents/felix-admin-calendar/` → `/data/services/openclaw/calendar-agent/`,
  registered in `service-inventory.json`) but is **not yet listed in
  `drift-check-config.json`** — so its workspace deploys via the manifest pipeline
  but is **not currently drift-monitored**. Closing this gap (adding the
  `felix-admin-calendar` entry and regenerating the baseline manifest) is a tracked
  follow-up; it is out of #587's file scope.
- **`felix-doc-auditor`** was refactored to a scripts-first Python driver (#343) and
  is **suspended** as a live agent — no deployed workspace, intentionally absent from
  the drift roster. Its repo directory is retained as history only.

## Last-Author-Wins Enforcement Strategy

The enforcement script compares each file's current hash against its baseline hash on both sides:

| Repo vs Baseline | Office2 vs Baseline | Interpretation | Auto-Action |
|---|---|---|---|
| Unchanged | Unchanged | No drift | None |
| Changed | Unchanged | Repo was last author | Auto-deploy repo→office2 |
| Unchanged | Changed | Office2 was last author | Auto-capture office2→repo + commit |
| Changed | Changed | Both sides edited | File issue + WhatsApp alert |

**After remediation**: the baseline manifest is updated with the new hashes so the next run starts clean.

**Auto-capture commits** use the prefix `chore: drift-reconcile <agent>/<file> (office2→repo)` for auditability. Recovery: `git revert <commit>`.

## Factory-Default Lifecycle Policy

OpenClaw provisions factory-default template files when a workspace is initialized. These files start as boilerplate and may be customized through:

1. **Bootstrap ritual** — one-time guided Q&A that fills in `IDENTITY.md`, `USER.md`, `SOUL.md`
2. **Manual editing** — operator opens files in a text editor
3. **Organic evolution** — agent autonomously updates files based on interactions

### Lifecycle Stages

```
Factory Default (untracked) → Customized (detected) → Tracked in Repo → Monitored
```

**Stage 1: Factory Default** — file hash matches a known baseline in `factory-baselines.json`. Enforcement ignores these files.

**Stage 2: Customized** — file hash no longer matches any factory baseline. Enforcement detects the transition and files a GitHub issue labeled `drift-alert` + sends a WhatsApp notification.

**Stage 3: Tracked** — operator captures the customized file to the repo. Enforcement begins monitoring for drift.

**Stage 4: Monitored** — three-way diff detects changes on either side; last-author-wins auto-remediates.

### Known Factory Baselines

Stored in `scripts/openclaw/agents/factory-baselines.json`:

- `BOOTSTRAP.md` — transient birth-certificate file (deleted after first run)
- `TOOLS.md` — generic local-notes scaffold
- `IDENTITY.md` (template_full) — 23-line template with blank placeholder fields

The 6-line `IDENTITY.md` files on existing agents are NOT factory defaults — they were filled in during bootstrap with agent-specific content.

### Ownership and Generalization

**Detection ownership**: The enforcement cron job owns detection of factory-default transitions. It runs daily and requires no human intervention for detection.

**Capture-to-repo ownership**: The operator (Kent) owns the capture step. When a factory-default transition is detected, the enforcement script files a GitHub issue and sends a WhatsApp notification. The operator then captures the customized file to the repo and regenerates the baseline manifest. Future automation may auto-capture if proven safe.

**Generalization beyond OpenClaw**: The `factory-baselines.json` format supports entries for any app, not just OpenClaw. When a new IA-type app joins the Felix stack with its own workspace files, add its factory template hashes to the baselines file under a new key. The enforcement config (`drift-check-config.json`) can be extended with new agent entries following the same structure.

## Manual Operations

### Run drift check manually

```bash
# Detection only (no remediation), exit code 1 if drift found:
python3 scripts/openclaw/enforcement/drift_check.py report --json

# Full enforcement (detect + remediate + notify):
python3 scripts/openclaw/enforcement/drift_check.py check --json

# Preview enforcement actions without executing:
python3 scripts/openclaw/enforcement/drift_check.py check --dry-run --json
```

On office2, prefix with `cd /home/claude/kg-automation &&`.

- `report` — detection only, no remediation, exit code 1 if drift found
- `check` — detection + remediation + notification, exit code 0 on success
- `check --dry-run` — shows what would happen without executing
- `--json` — machine-readable output (single consolidated JSON document)

### Regenerate the baseline manifest

After manual reconciliation or when hashes need resetting:

```bash
python3 scripts/openclaw/enforcement/generate_manifest.py
```

This probes all agent workspaces on office2 via SSH, computes hashes, and writes `scripts/openclaw/agents/baseline-manifest.json`.

### Force a specific direction

To manually deploy a repo file to office2:
```bash
scp scripts/openclaw/agents/<agent>/<file> office2-claude:<workspace-path>/<file>
```

To manually capture an office2 file to repo:
```bash
scp office2-claude:<workspace-path>/<file> scripts/openclaw/agents/<agent>/<file>
```

After manual intervention, regenerate the baseline manifest.

## Adding a New Agent

When a new OpenClaw agent is registered:

1. Register in `/home/claude/.openclaw/openclaw.json`
2. Create `scripts/openclaw/agents/<agent-id>/` in the repo
3. If workspace files are customized: capture from office2 to repo
4. If workspace files are factory default: leave them (enforcement will detect customization later)
5. Add the agent entry to `scripts/openclaw/enforcement/drift-check-config.json`
6. Regenerate the baseline manifest: `python3 scripts/openclaw/enforcement/generate_manifest.py`

## Troubleshooting

| Symptom | Check |
|---|---|
| Cron not running | `ssh office2-claude 'crontab -l \| grep drift-check'` |
| WhatsApp not delivered | `ssh office2-claude 'openclaw agent --agent main --message "test" --deliver --channel whatsapp --to <number>'` |
| False drift alerts | Regenerate baseline manifest |
| SSH timeout during check | Check office2 connectivity: `ssh office2-claude 'echo ok'` |
| `ModuleNotFoundError` | Ensure repo root is on `sys.path` or run from repo root |

## Cron Schedule

- **When**: Daily at 06:00 UTC (02:00 ET)
- **Where**: office2 (`claude` user crontab)
- **Log**: `/tmp/drift-check.log`
- **Remove**: `ssh office2-claude 'crontab -l | grep -v drift-check | crontab -'`

## Related

- [#166](https://github.com/kentonium3/kg-automation/issues/166) — parent issue
- [#156](https://github.com/kentonium3/kg-automation/issues/156) — drift root cause analysis
- [#157](https://github.com/kentonium3/kg-automation/issues/157) — main agent governance gap
- [#105](https://github.com/kentonium3/kg-automation/issues/105) — doc auditor (potential future enforcement home)
- [#106](https://github.com/kentonium3/kg-automation/issues/106) — state auditor (potential future enforcement home)
