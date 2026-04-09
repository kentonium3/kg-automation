---
work_package_id: WP01
title: Pre-flight and Baseline
dependencies: []
requirement_refs:
- FR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T001, T002, T003]
history:
- date: '2026-04-09T17:18:21Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: kitty-specs/021-openclaw-agent-model-tiering/artifacts/
execution_mode: planning_artifact
owned_files:
- kitty-specs/021-openclaw-agent-model-tiering/artifacts/baseline.md
---

# WP01: Pre-flight and Baseline

## Objective

Ensure Tier 2 change control compliance before any OpenClaw configuration changes. Verify a recent Restic backup exists, snapshot the current config, and document the baseline model assignments for comparison after deployment.

## Context

- OpenClaw config is at `/home/claude/.openclaw/openclaw.json` on office2
- Access via `ssh office2-claude` (never ssh as kgale)
- This is Tier 2 (application config) per the change risk taxonomy
- Tier 2 requires a confirmed recent Restic backup before modifying
- The claude user does NOT have sudo access — if backup commands need sudo, present the command to Kent

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP01`

---

## Subtask T001: Verify Restic Backup Recency

**Purpose**: Confirm a recent Restic backup exists on office2 before any config changes. This is a Tier 2 gate.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Check the most recent Restic snapshot:
   - Look for backup scripts in `/data/services/backup/scripts/`
   - Check backup logs in `/data/services/backup/logs/`
   - Run restic commands to list recent snapshots (if accessible to claude user)
3. If the most recent backup is older than 24 hours, STOP and report to Kent
4. If claude user cannot access restic directly, report what you found and let Kent verify

**Validation**:
- [ ] Most recent Restic backup confirmed within 24 hours
- [ ] If backup is stale or inaccessible, Kent has been notified before proceeding

---

## Subtask T002: Snapshot Current openclaw.json

**Purpose**: Create a recoverable copy of the current config before any modifications.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Copy the current config to a timestamped backup:
   ```
   cp /home/claude/.openclaw/openclaw.json /home/claude/.openclaw/openclaw.json.backup.2026-04-09
   ```
3. Verify the backup was created and has the same content:
   ```
   diff /home/claude/.openclaw/openclaw.json /home/claude/.openclaw/openclaw.json.backup.2026-04-09
   ```
4. Record the backup path for rollback reference

**Validation**:
- [ ] Backup file created at known path
- [ ] Backup content matches current config (diff shows no differences)

---

## Subtask T003: Document Current Model Assignments

**Purpose**: Record the baseline state so we can measure the impact of tiering and have a rollback reference.

**Steps**:
1. Read the current `openclaw.json` (already discovered in planning — confirm it hasn't changed)
2. Create a baseline document in the mission directory recording:
   - Global default: `agents.defaults.model.primary` value
   - Each agent's current `model` value
   - The date and time of the baseline
3. This baseline will be referenced during deployment (WP04) and cost calculation (WP05)

**Output**: A baseline record (can be a simple markdown table in the mission notes or a JSON snippet) capturing:

| Agent ID | Current Model |
|---|---|
| (global default) | anthropic/claude-sonnet-4-6 |
| main | (inherits default) |
| felix-admin-capture | anthropic/claude-sonnet-4-6 |
| felix-admin-habits | anthropic/claude-sonnet-4-6 |
| felix-admin-escalation | anthropic/claude-sonnet-4-6 |
| felix-admin-tasker | anthropic/claude-sonnet-4-6 |

**Validation**:
- [ ] Baseline document created with all agent model assignments
- [ ] Baseline matches current live config

---

## Definition of Done

- [ ] Restic backup confirmed recent (within 24 hours)
- [ ] openclaw.json snapshot saved to backup path
- [ ] Baseline model assignments documented
- [ ] No config changes made (read-only WP)

## Risks

- **claude user may not have restic access**: Report to Kent for manual verification
- **Config may have changed since planning discovery**: Re-read and update baseline if different

## Reviewer Guidance

- Verify the backup file exists and is a complete copy
- Confirm baseline matches the config read during planning (5 agents + main, all on Sonnet)
- Ensure no config modifications were made in this WP
