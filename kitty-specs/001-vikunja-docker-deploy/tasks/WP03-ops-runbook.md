---
work_package_id: WP03
title: Ops Runbook and Security Baseline
lane: planned
dependencies: [WP01]
requirement_refs:
- C-002
- FR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T015
- T016
- T017
- T018
- T019
- T020
phase: Phase 2 - Documentation
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

# Work Package Prompt: WP03 – Ops Runbook and Security Baseline

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created. For stacked WPs it may point at another WP branch.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

**Implementation command**: `spec-kitty implement WP03 --base WP01`

---

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status`. If it says `has_feedback`, read `review_feedback` first.
- **You must address all feedback** before your work is complete.

---

## Objectives & Success Criteria

Create `docs/handbooks/vikunja-ops.md` — a comprehensive operations runbook covering all Vikunja maintenance procedures, including the security baseline reset.

**Success**:
- Runbook exists at `docs/handbooks/vikunja-ops.md`
- Passes `validate_docs.py` (valid frontmatter)
- Covers all five operational topics plus security baseline reset
- A new Claude Code session can follow the runbook to perform operations

## Context & Constraints

- **Plan**: `kitty-specs/001-vikunja-docker-deploy/plan.md`
- **Research**: `kitty-specs/001-vikunja-docker-deploy/research.md` (see R-007)
- **Constitution**: `.kittify/constitution/constitution.md`
- **Frontmatter requirements**: Must include `title`, `doc_type`, `status` per `docs/design/standards/allowed-values.json`
- **Doc type**: `handbook`
- Write the runbook AFTER WP01 deployment so actual paths and service names are confirmed

## Subtasks & Detailed Guidance

### Subtask T015 – Create vikunja-ops.md with Frontmatter

**Purpose**: Establish the runbook file with valid YAML frontmatter.

**Steps**:
1. Create `docs/handbooks/vikunja-ops.md`
2. Add frontmatter:
   ```yaml
   ---
   title: Vikunja Operations Runbook
   doc_type: handbook
   status: draft
   ---
   ```
3. Add top-level heading and overview paragraph explaining what this runbook covers

**Files**: `docs/handbooks/vikunja-ops.md` (new file).
**Parallel?**: Yes — must be created first but the sections below can be written in any order.

### Subtask T016 – Document Start/Stop/Restart Procedures

**Purpose**: Enable any operator to manage the Vikunja service lifecycle.

**Steps**:
1. Add a "Service Management" section covering:
   - Start: `sudo systemctl start vikunja`
   - Stop: `sudo systemctl stop vikunja`
   - Restart: `sudo systemctl restart vikunja`
   - Status: `systemctl status vikunja` (no sudo needed for status)
   - Logs: `journalctl -u vikunja -f` (follow) or `journalctl -u vikunja --since "1 hour ago"`
   - Docker-level: `docker ps | grep vikunja`, `docker logs vikunja`
2. Note that start/stop/restart require sudo (kgale user or Kent's intervention)
3. Note that the claude user can check status and read logs

**Files**: `docs/handbooks/vikunja-ops.md` (add section).
**Parallel?**: Yes.

### Subtask T017 – Document Database Location and Backup Verification

**Purpose**: Document where data lives and how to verify backups.

**Steps**:
1. Add a "Data and Backups" section covering:
   - SQLite database path: `/data/services/vikunja/data/vikunja.db` (confirm actual path from WP01)
   - Data directory: `/data/services/vikunja/data/`
   - Backup mechanism: Restic runs at 4AM via cron, backing up `/data/services/` (includes Vikunja data automatically)
   - Backup script: `/data/services/backup/scripts/backup.sh`
   - Verify backup: `restic snapshots` to list recent snapshots
   - Verify Vikunja data in backup: `restic ls latest /data/services/vikunja/` to confirm files are included
   - Manual backup trigger: document the command to run a backup manually if needed

**Files**: `docs/handbooks/vikunja-ops.md` (add section).
**Parallel?**: Yes.

### Subtask T018 – Document Version Update Procedure

**Purpose**: Provide a safe, repeatable process for upgrading Vikunja.

**Steps**:
1. Add a "Version Updates" section covering:
   - Current version: document where the pinned version is recorded (in `scripts/vikunja/deploy.sh` and/or `vikunja.service`)
   - Before updating:
     - Check Vikunja release notes for breaking changes
     - Verify a recent Restic backup exists
   - Update process:
     1. Edit the version tag in `deploy.sh` / `vikunja.service`
     2. Pull the new image: `docker pull vikunja/vikunja:<new-version>`
     3. Stop the service: `sudo systemctl stop vikunja`
     4. Start with new image: `sudo systemctl start vikunja`
     5. Verify the UI loads and data is intact
   - Rollback process:
     1. Revert the version tag
     2. Pull the old image
     3. Restart the service
   - Commit the version change via PR

**Files**: `docs/handbooks/vikunja-ops.md` (add section).
**Parallel?**: Yes.

### Subtask T019 – Document Tailscale Access and Troubleshooting

**Purpose**: Document how to access Vikunja and troubleshoot connectivity issues.

**Steps**:
1. Add an "Access and Connectivity" section covering:
   - Web UI URL: `http://office2:3456` (from any Tailscale-connected device)
   - Alternative URL: `http://100.92.197.90:3456` (using Tailscale IP directly)
   - Requirements: Tailscale must be active on the accessing device
   - Troubleshooting:
     - Verify Tailscale is connected: `tailscale status` on both devices
     - Verify Vikunja is running: `systemctl status vikunja` on office2
     - Verify port binding: `ss -tlnp | grep 3456` should show `100.92.197.90`
     - If port shows `0.0.0.0`, the service is misconfigured — stop and rebind
   - iPhone access: Tailscale app must be connected; open Safari to `http://100.92.197.90:3456`

**Files**: `docs/handbooks/vikunja-ops.md` (add section).
**Parallel?**: Yes.

### Subtask T020 – Document Security Baseline Reset

**Purpose**: Document how to reset security audit baselines after deploying Vikunja.

**Steps**:
1. Add a "Security Baseline Reset" section covering:
   - Why: The security monitoring system on office2 detects unexpected changes. A new Docker container, systemd service, and port 3456 will trigger alerts unless baselines are updated.
   - Baselines location: `/data/services/security-monitor/baselines/`
   - What to reset:
     - Docker container baseline (new `vikunja` container)
     - systemd service baseline (new `vikunja.service`)
     - Port baseline (port 3456 now expected to be open on Tailscale interface)
   - Reset command: document the actual command (may require sudo — note this)
   - When to reset: after initial deployment, and after any version update that changes the container
   - Note: this step may require Kent to run manually if sudo is needed

**Files**: `docs/handbooks/vikunja-ops.md` (add section).
**Parallel?**: Yes.
**Notes**: The exact reset command depends on how the security monitor works on office2. If the command is not discoverable by the claude user, document the baseline location and what needs to be updated, and note that Kent should run the reset.

## Risks & Mitigations

- **Paths not yet confirmed**: Write runbook after WP01 deploys so actual paths are known. Use placeholder notes if writing in parallel.
- **Security baseline reset command unknown**: Document the baseline location and what needs updating; note that Kent should run the actual reset.
- **Frontmatter validation failure**: Use `doc_type: handbook` which is in the allowed values list.

## Review Guidance

- Run `python tooling/scripts/validate_docs.py` to confirm frontmatter passes
- Verify all five operational topics are covered (start/stop, database/backup, version updates, access, security baseline)
- Confirm all paths match the actual deployment from WP01
- Check that sudo-required commands are clearly marked
- Verify a new session could follow the runbook without prior context

## Activity Log

- 2026-03-26T06:31:38Z – system – lane=planned – Prompt created.
