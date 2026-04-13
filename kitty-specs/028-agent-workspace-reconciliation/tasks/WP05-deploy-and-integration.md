---
work_package_id: WP05
title: Deploy and integration verification
dependencies:
- WP01
- WP04
requirement_refs:
- FR-004
- FR-011
planning_base_branch: main
merge_target_branch: main
branch_strategy: 'Worktree allocated by spec-kitty lane assignment. Planning base and merge target: main.'
subtasks:
- T019
- T020
- T021
- T022
- T023
history:
- date: '2026-04-13'
  action: created
  agent: claude-opus-4-6
authoritative_surface: scripts/deploy/
execution_mode: code_change
owned_files:
- scripts/deploy/deploy-028.sh
tags: []
---

# WP05: Deploy and Integration Verification

## Objective

Deploy reconciled tasker files to office2, install the enforcement cron job, and verify the entire system end-to-end with a controlled drift test.

## Context

This is the integration gate WP required by the charter. It exercises the real environment:

1. **Tasker deploy**: 4 files where repo is authoritative (SOUL.md, TOOLS.md, USER.md, IDENTITY.md) need to be pushed to `/data/services/openclaw/tasker-agent/` on office2
2. **Enforcement install**: `drift_check.py` + config + manifests deployed to office2, cron job registered
3. **Zero-drift verification**: After deploy, hash comparison across all 25 files should show zero drift
4. **Controlled drift test**: Introduce a deliberate change, verify the enforcement script detects and remediates it

**Tier 2 protocol applies**: Restic backup must be confirmed before deploying to office2.

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`
- Execution worktree: allocated by spec-kitty lane assignment per `lanes.json`

## Detailed Guidance

### T019: Create deploy-028.sh following safe-deploy pattern

**Purpose**: Deploy wrapper following the established safe-deploy pattern from the charter.

**Steps**:
1. Create `scripts/deploy/deploy-028.sh` following the pattern from existing deploy scripts (e.g., `deploy-f026.sh`):

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail

   # deploy-028.sh — Agent workspace reconciliation deploy
   # Usage: ./deploy-028.sh [--apply] [--backup-confirmed]
   #
   # Phases:
   #   1. Pre-flight: Restic age, SSH reachability, source file presence
   #   2. Copy: SCP tasker files + enforcement script to office2
   #   3. Verify: Hash comparison of deployed files
   #   4. Post-flight: Run drift-check.py --dry-run as smoke test
   ```

2. Pre-flight checks:
   - `--backup-confirmed` flag required (Tier 2 gate). Without it, print the backup log check command and exit.
   - SSH reachability: `ssh office2-claude 'echo ok'`
   - Source files exist: verify all 4 tasker files and enforcement script are present in repo

3. Dry-run by default. `--apply` flag to actually execute.

4. Copy phase:
   - Tasker files: `scripts/openclaw/agents/felix-admin-tasker/{SOUL,TOOLS,USER,IDENTITY}.md` → `/data/services/openclaw/tasker-agent/`
   - Enforcement: `scripts/openclaw/enforcement/` → `/home/claude/kg-automation/scripts/openclaw/enforcement/` (repo clone on office2)
   - Manifests: `scripts/openclaw/agents/{baseline-manifest,factory-baselines}.json` → same relative path on office2 repo clone

5. Verify phase: hash comparison of deployed files

6. Post-flight: `ssh office2-claude 'cd /home/claude/kg-automation && python3 scripts/openclaw/enforcement/drift_check.py check --dry-run --json'`

**Files**: `scripts/deploy/deploy-028.sh` (new, ~120 lines)

### T020: Deploy reconciled tasker files repo→office2

**Purpose**: The 4 tasker workspace files where repo is authoritative need to be deployed to office2.

**Steps**:
1. This is executed as part of `deploy-028.sh --apply --backup-confirmed`
2. Files to deploy:
   - `scripts/openclaw/agents/felix-admin-tasker/SOUL.md` → `/data/services/openclaw/tasker-agent/SOUL.md`
   - `scripts/openclaw/agents/felix-admin-tasker/TOOLS.md` → `/data/services/openclaw/tasker-agent/TOOLS.md`
   - `scripts/openclaw/agents/felix-admin-tasker/USER.md` → `/data/services/openclaw/tasker-agent/USER.md`
   - `scripts/openclaw/agents/felix-admin-tasker/IDENTITY.md` → `/data/services/openclaw/tasker-agent/IDENTITY.md`
3. Verify each file's hash matches after SCP

**Files**: No new files (uses deploy-028.sh)

### T021: Install drift-check.py + cron job on office2

**Purpose**: The enforcement script needs to run daily on office2 as a cron job.

**Steps**:
1. The enforcement script runs from the repo clone on office2 at `/home/claude/kg-automation/`
2. Ensure the repo on office2 is up to date: `ssh office2-claude 'cd /home/claude/kg-automation && git pull'`
3. Install cron job. The charter says "System crontab is never used for openclaw-managed cron jobs" — but this is not an openclaw-managed cron; it's a Felix infrastructure job. Use the claude user's crontab:
   ```bash
   ssh office2-claude 'crontab -l > /tmp/crontab.bak && echo "0 6 * * * cd /home/claude/kg-automation && python3 scripts/openclaw/enforcement/drift_check.py check --config scripts/openclaw/enforcement/drift-check-config.json >> /tmp/drift-check.log 2>&1" >> /tmp/crontab.bak && crontab /tmp/crontab.bak'
   ```
4. Verify: `ssh office2-claude 'crontab -l | grep drift-check'`
5. The cron runs at 6:00 AM UTC daily (2:00 AM ET)

**Files**: No new files (crontab on office2)

**Edge cases**:
- If the crontab already has a drift-check entry, don't duplicate it
- The log file at `/tmp/drift-check.log` should be rotated or moved to a better location (e.g., `/data/services/logs/drift-check/`)

### T022: Post-reconciliation zero-drift verification

**Purpose**: After deploying tasker files, verify zero drift across all 25 tracked files.

**Steps**:
1. Run the enforcement script manually:
   ```bash
   ssh office2-claude 'cd /home/claude/kg-automation && python3 scripts/openclaw/enforcement/drift_check.py check --json'
   ```
2. The output should show `NO_CHANGE` for all 25 files
3. If any files show drift, investigate and resolve before proceeding
4. Regenerate baseline-manifest.json to capture the fully reconciled state (all repo and office2 hashes should now match)
5. Commit the updated manifest

**Files**: `scripts/openclaw/agents/baseline-manifest.json` (updated)

### T023: Controlled drift test

**Purpose**: Verify the enforcement script detects and remediates drift correctly in the real environment.

**Steps**:
1. **Test repo-changed detection**: Add a comment line to a tasker file in the local repo, commit, push to office2 repo clone. Run drift-check. Verify it detects `REPO_CHANGED` and deploys the file to the tasker workspace.
2. **Test office2-changed detection**: Append a comment line to a file on office2 directly: `ssh office2-claude 'echo "# test drift" >> /data/services/openclaw/tasker-agent/SOUL.md'`. Run drift-check. Verify it detects `OFFICE2_CHANGED` and captures the file to the repo.
3. **Clean up**: Revert the test changes (remove comment lines, re-run drift-check to reach zero-drift state again).
4. **Verify notifications**: If testing conflict state, introduce changes on both sides. Verify WhatsApp message is sent and GitHub issue is created. Close the test issue after verifying.

**Files**: No new files (verification only)

**Important**: Revert all test changes before completing. The final state must be zero-drift.

## Definition of Done

- [ ] `deploy-028.sh` follows safe-deploy pattern with Tier 2 pre-flight
- [ ] All 4 tasker files deployed to office2 with hash verification
- [ ] Enforcement cron job installed and verified on office2
- [ ] Zero-drift verification passes (all 25 files matching)
- [ ] Controlled drift test demonstrates detection + remediation for at least `REPO_CHANGED` and `OFFICE2_CHANGED` states
- [ ] Baseline manifest regenerated with final reconciled hashes
- [ ] All test artifacts cleaned up

## Risks

- **Tier 2**: Deploy modifies production agent workspaces. Mitigation: `--backup-confirmed` gate, hash verification after each SCP.
- **Cron conflict**: Existing cron jobs may conflict with the enforcement schedule. Mitigation: review `crontab -l` before adding.
- **Controlled test side effects**: The test deliberately introduces drift. Mitigation: explicit cleanup steps with verification.

## Reviewer Guidance

- Verify deploy-028.sh has the `--backup-confirmed` gate (not bypassable)
- Check that zero-drift verification covers all 25 files, not just the 4 tasker files
- Confirm controlled drift test includes cleanup verification
- Verify cron job timing doesn't conflict with existing jobs (backup at 0400 UTC, audit at 0300 UTC, observation at 2300 UTC)
