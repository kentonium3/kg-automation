---
work_package_id: WP07
title: Deployment & Validation
dependencies: [WP01, WP02, WP03, WP04, WP05, WP06]
requirement_refs:
- FR-020
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T032, T033, T034, T035, T036]
history:
- date: '2026-04-02T12:53:14Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/deploy/
execution_mode: code_change
owned_files: [scripts/deploy/deploy-f013.sh]
---

# WP07: Deployment & Validation

## Objective

Deploy all F013 artifacts to office2 and validate end-to-end operation. This WP creates a deployment script and a validation checklist that ensures felix-admin-tasker is operational, handles all action types, and integrates correctly with felix-admin-capture.

## Context

- **Feature**: 013-vikunja-task-intelligence-agent
- **Plan deployment sequence**: See `kitty-specs/013-vikunja-task-intelligence-agent/plan.md` → Deployment Sequence section
- **Quickstart**: `kitty-specs/013-vikunja-task-intelligence-agent/quickstart.md`
- **All artifacts from WP01-WP06 must be complete before deployment**
- **Key constraint**: Agent must use `ssh office2-claude` — never `ssh office2-kgale`

### Implementation command

```bash
spec-kitty implement WP07 --base WP06
```

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: All prior WPs (WP01-WP06)
- **Actual base branch**: WP06's branch (stacked) — follow `spec-kitty implement` output

---

## Subtask T032: Deploy Task Intelligence Skill to office2

**Purpose**: Copy the task-intelligence skill to office2 where OpenClaw can find it.

**Steps**:
1. Create deployment script `scripts/deploy/deploy-f013.sh`:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail

   echo "=== F013: Deploying task-intelligence skill ==="
   ssh office2-claude "mkdir -p ~/.openclaw/skills/task-intelligence"
   scp scripts/openclaw/skills/task-intelligence/SKILL.md \
     office2-claude:~/.openclaw/skills/task-intelligence/SKILL.md
   echo "✓ Skill deployed"
   ```

2. The script uses `scp` from the Mac to office2 via the `office2-claude` SSH alias

**Validation**:
- [ ] Skill file exists at `~/.openclaw/skills/task-intelligence/SKILL.md` on office2
- [ ] File content matches repo version

---

## Subtask T033: Deploy Agent Workspace to office2

**Purpose**: Copy the agent workspace files to office2.

**Steps**:
1. Add to deployment script:
   ```bash
   echo "=== F013: Deploying agent workspace ==="
   ssh office2-claude "mkdir -p /data/services/openclaw/tasker-agent"
   for f in AGENTS.md SOUL.md USER.md IDENTITY.md TOOLS.md; do
     scp "scripts/openclaw/agents/felix-admin-tasker/$f" \
       "office2-claude:/data/services/openclaw/tasker-agent/$f"
   done
   echo "✓ Agent workspace deployed"
   ```

2. Add updated felix-admin-capture deployment:
   ```bash
   echo "=== F013: Updating felix-admin-capture ==="
   scp scripts/openclaw/agents/felix-admin-capture/AGENTS.md \
     office2-claude:/data/services/openclaw/inbox-agent/AGENTS.md
   echo "✓ Capture agent updated"
   ```

**Validation**:
- [ ] All 5 workspace files exist at `/data/services/openclaw/tasker-agent/` on office2
- [ ] felix-admin-capture AGENTS.md updated on office2
- [ ] File contents match repo versions

---

## Subtask T034: Set Up Cron Jobs on office2

**Purpose**: Configure the incomplete task detection cron job.

**Steps**:
1. Add to deployment script:
   ```bash
   echo "=== F013: Setting up cron ==="
   ssh office2-claude 'openclaw cron add \
     --name "task-detection" \
     --cron "0 */4 * * *" \
     --agent felix-admin-tasker \
     --session isolated \
     --message '"'"'{"action": "detect_incomplete"}'"'"' \
     --no-deliver'
   echo "✓ Cron job configured"
   ```

2. Add verification:
   ```bash
   echo "=== Verifying cron ==="
   ssh office2-claude "openclaw cron list"
   ```

**Validation**:
- [ ] Cron job appears in `openclaw cron list` output
- [ ] Schedule is `0 */4 * * *`
- [ ] Agent is `felix-admin-tasker`

---

## Subtask T035: Manual Validation with Test Task Enrichment

**Purpose**: Validate the agent works end-to-end with a real test task in Assisted mode.

**Steps**:
1. Add validation section to deployment script:
   ```bash
   echo "=== F013: Running validation ==="
   echo "Step 1: Test direct enrichment..."
   ssh office2-claude 'openclaw agent --agent felix-admin-tasker \
     --message '"'"'{"action": "enrich_task", "raw_text": "F013 validation test task — delete after testing", "source_reference": "test/f013-validation", "inferred_identity": "personal"}'"'"' \
     --json --timeout 120'
   ```

2. Document manual validation steps (as comments in the script):
   ```bash
   # After running the test:
   # 1. Check WhatsApp for proposal message from Felix
   # 2. Reply "yes" to confirm the test task
   # 3. Verify task appears in Vikunja Inbox with attributes
   # 4. Check action log: ssh office2-claude "cat ~/second-brain/agents/logs/task-intelligence-$(date +%Y-%m-%d).md"
   # 5. Delete the test task from Vikunja
   ```

**Validation**:
- [ ] Agent responds to delegation with proposal via WhatsApp
- [ ] Confirmed task appears in Vikunja with correct attributes
- [ ] Action log entry written
- [ ] Test task cleaned up after validation

---

## Subtask T036: End-to-End Verification

**Purpose**: Verify the complete flow from inbox capture delegation through task creation.

**Steps**:
1. Add end-to-end checklist as comments in the deployment script:
   ```bash
   # === End-to-End Verification Checklist ===
   #
   # [ ] Direct enrichment: Agent proposes and creates task (T035)
   # [ ] Detection polling: Run detect_incomplete, verify it finds flat Inbox tasks
   #     ssh office2-claude 'openclaw agent --agent felix-admin-tasker \
   #       --message '"'"'{"action": "detect_incomplete"}'"'"' --json --timeout 300'
   # [ ] Retroactive enrichment: Run batch of 3
   #     ssh office2-claude 'openclaw agent --agent felix-admin-tasker \
   #       --message '"'"'{"action": "retroactive_enrichment", "batch_size": 3}'"'"' --json --timeout 300'
   # [ ] Capture delegation: Wait for next inbox processing run, verify delegation
   #     (check capture agent logs for delegation attempt)
   # [ ] Fallback: Temporarily stop tasker agent, verify capture creates flat task
   # [ ] Action logging: Verify all actions appear in log file
   # [ ] Cron execution: Wait for next 4-hour cycle, verify detection runs
   #
   # NOTE: Some checks require waiting for scheduled events. Mark as verified
   # over the first 24 hours of operation.
   ```

2. Make the deployment script executable:
   ```bash
   chmod +x scripts/deploy/deploy-f013.sh
   ```

**Validation**:
- [ ] Deployment script is complete and executable
- [ ] End-to-end checklist covers all action types
- [ ] All verification can be performed within 24 hours of deployment

---

## Definition of Done

- [ ] `scripts/deploy/deploy-f013.sh` exists and is executable
- [ ] Skill deployed to office2
- [ ] Agent workspace deployed to office2
- [ ] felix-admin-capture updated on office2
- [ ] Cron job configured
- [ ] Direct enrichment test passes (proposal → confirm → task created)
- [ ] Action log entry written for test
- [ ] End-to-end verification checklist documented

## Risks

- **office2 connectivity**: SSH connection must be available. Use `ssh office2-claude`.
- **OpenClaw configuration**: Agent registration may require additional OpenClaw setup not documented. If `openclaw agent` doesn't find the new agent, check OpenClaw's agent discovery configuration.
- **WhatsApp channel**: Must be operational for confirmation flow. If Baileys session is expired, that blocks validation.

## Reviewer Guidance

- Verify deployment script uses `office2-claude` (never `office2-kgale`)
- Check that deployment order matches plan.md: skill first, then workspace, then capture update, then cron
- Ensure no credentials are embedded in the script
- Verify the test task enrichment flow includes cleanup (delete test task)
- Check that the end-to-end checklist is comprehensive
