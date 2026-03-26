---
work_package_id: WP04
title: Verification and Acceptance
lane: planned
dependencies: [WP01, WP02, WP03]
requirement_refs:
- C-001
- C-007
- FR-002
- NFR-002
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: 'Current branch at workflow start: main. Planning/base branch for this feature: main. Completed changes must merge into main.'
subtasks:
- T021
- T022
- T023
- T024
- T025
- T026
- T027
phase: Phase 3 - Verification
assignee: ''
agent: ''
shell_pid: ''
review_status: ''
reviewed_by: ''
review_feedback: ''
history:
- timestamp: '2026-03-26T06:31:38Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP04 – Verification and Acceptance

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created. For stacked WPs it may point at another WP branch.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

**Implementation command**: `spec-kitty implement WP04 --base WP03`

---

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status`. If it says `has_feedback`, read `review_feedback` first.
- **You must address all feedback** before your work is complete.

---

## Objectives & Success Criteria

Execute all acceptance scenarios from the spec to confirm the deployment is complete and correct. Document pass/fail results for each criterion.

**Success**: All acceptance scenarios pass. Port binding is secure. Data persists across container replacement. Backups include Vikunja data. Setup script is idempotent.

## Context & Constraints

- **Spec**: `kitty-specs/001-vikunja-docker-deploy/spec.md` (acceptance scenarios)
- **Quickstart**: `kitty-specs/001-vikunja-docker-deploy/quickstart.md` (verification checklist)
- **SSH access**: `ssh office2-claude` only
- **iPhone verification**: Requires Kent to confirm manually
- **Backup verification**: May need to wait for 4AM run or trigger manual backup

## Subtasks & Detailed Guidance

### Subtask T021 – Verify Mac Web UI Access

**Purpose**: Confirm Vikunja is accessible from Mac via Tailscale.

**Steps**:
1. From Mac, open browser to `http://office2:3456`
2. Verify the Vikunja login page loads
3. Log in with the admin account
4. Verify the UI is functional (can navigate, create a test task)
5. Record: PASS or FAIL with details

**Files**: None — verification only.
**Parallel?**: Yes — independent check.
**Notes**: If `office2` hostname doesn't resolve, try `http://100.92.197.90:3456`. Both should work.

### Subtask T022 – Verify iPhone Web UI Access

**Purpose**: Confirm Vikunja is accessible from iPhone via Tailscale.

**Steps**:
1. Ask Kent to open `http://100.92.197.90:3456` in Safari on iPhone
2. Verify the login page loads
3. Verify the UI is usable on mobile (responsive layout)
4. Record: PASS or FAIL with details

**Files**: None — verification only.
**Parallel?**: Yes — independent check.
**Notes**: Kent must confirm this manually. Tailscale app must be connected on iPhone.

### Subtask T023 – Verify Port Binding Security

**Purpose**: Confirm port 3456 is bound to the Tailscale IP only, not to `0.0.0.0` or any public interface.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Run: `ss -tlnp | grep 3456`
3. Expected output should show `100.92.197.90:3456` — NOT `0.0.0.0:3456` or `*:3456`
4. Additionally verify: `docker inspect vikunja | grep -A5 HostConfig` to check port bindings
5. Record: PASS or FAIL with exact output

**Files**: None — verification only.
**Parallel?**: Yes — independent check.
**Notes**: If bound to `0.0.0.0`, this is a SECURITY ISSUE. Stop and fix the Docker run command in deploy.sh / vikunja.service immediately.

### Subtask T024 – Verify systemd Restart Recovery

**Purpose**: Confirm the service restarts automatically after failure and boots with the system.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Check current status: `systemctl status vikunja`
3. Present to Kent: `sudo systemctl restart vikunja`
4. Wait 10 seconds, then check: `systemctl status vikunja` (should show active)
5. Check that the container is running: `docker ps | grep vikunja`
6. Verify the web UI responds: `curl -s -o /dev/null -w "%{http_code}" http://100.92.197.90:3456`
7. Verify enabled for boot: `systemctl is-enabled vikunja` (should show "enabled")
8. Record: PASS or FAIL with timing (should recover within 30 seconds per NFR-001)

**Files**: None — verification only.
**Parallel?**: No — modifies system state.

### Subtask T025 – Verify Data Persistence

**Purpose**: Confirm task data survives container replacement.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Create a test task via the Vikunja UI (note the task title)
3. Stop the container: present `sudo systemctl stop vikunja` to Kent
4. Verify the SQLite file exists on host: `ls -la /data/services/vikunja/data/`
5. Start the container: present `sudo systemctl start vikunja` to Kent
6. Verify the test task is still present in the UI
7. Record: PASS or FAIL

**Files**: None — verification only.
**Parallel?**: No — modifies system state.
**Notes**: The key verification is that the SQLite file is on the HOST filesystem at `/data/services/vikunja/data/`, NOT inside the container.

### Subtask T026 – Verify Backup Inclusion

**Purpose**: Confirm Vikunja data is included in Restic backups.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Check the latest Restic snapshot: `restic snapshots --latest 1`
3. List Vikunja data in the latest snapshot: `restic ls latest /data/services/vikunja/`
4. If Vikunja data is present, record PASS
5. If no recent snapshot exists or data is missing:
   - Check that `/data/services/vikunja/data/` is within the backup scope
   - Review `/data/services/backup/scripts/backup.sh` to confirm source paths
   - If the 4AM backup hasn't run yet, either wait or ask Kent to trigger a manual backup
6. Record: PASS or FAIL with details

**Files**: None — verification only.
**Parallel?**: No — depends on backup schedule.
**Notes**: The data directory at `/data/services/vikunja/data/` should be automatically included because `/data/services/` is in the backup scope. If it's NOT included, check the backup script for exclusions.

### Subtask T027 – Verify Setup Script Idempotency

**Purpose**: Confirm the setup script can be run multiple times without creating duplicates.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Count existing projects, labels, and filters in Vikunja (via UI or API)
3. Run the setup script: `python scripts/vikunja/setup_vikunja.py`
4. Verify the script completes without errors
5. Count projects, labels, and filters again — counts should be unchanged
6. Verify in the UI that no duplicates exist
7. Record: PASS or FAIL

**Files**: None — verification only.
**Parallel?**: No — depends on WP02 completion.

## Risks & Mitigations

- **iPhone not on Tailscale**: Kent must verify manually. If Tailscale isn't connected, the test is blocked.
- **Backup hasn't run yet**: May need to wait for 4AM or trigger manual backup. Document the backup trigger command.
- **Container restart timing**: NFR-001 requires recovery within 30 seconds. Time the restart carefully.

## Review Guidance

- All 7 subtasks should have a documented PASS/FAIL result
- Any FAIL must have a clear description of what went wrong
- Security check (T023) is the most critical — any binding to `0.0.0.0` is a blocker
- Data persistence (T025) verifies the host volume mount works correctly
- Idempotency (T027) must show zero duplicates after second run

## Activity Log

- 2026-03-26T06:31:38Z – system – lane=planned – Prompt created.
