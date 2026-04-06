---
work_package_id: WP03
title: Deployment, Cron, and Architecture
dependencies: [WP02]
requirement_refs:
- FR-011
- FR-012
- FR-015
- FR-016
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T008, T009, T010, T011, T012, T013, T014]
history:
- date: '2026-04-06'
  action: created
  by: spec-kitty.tasks
authoritative_surface: docs/
execution_mode: code_change
owned_files:
- docs/constitution/AGENT-REGISTRY.md
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
---

# WP03: Deployment, Cron, and Architecture

## Objective

Register the agent in OpenClaw, deploy all files (skill + workspace) to
office2, create the daily escalation cron job, register the agent in the
Agent Registry, and update architecture documentation.

## Context

**Deployment pattern**: Follow the habits agent deployment pattern
documented in `docs/runbooks/habits-ops.md`:
- Workspace files deployed to `/data/services/openclaw/escalation-agent/`
- Skill deployed to `/home/claude/.openclaw/skills/escalation/`
- Agent registered via `openclaw agents create`
- Cron created via `openclaw cron create`

**Cron timing**: 8:00 AM ET = 12:00 UTC. After the habits check-in
(7:05 AM ET / 11:05 UTC) by 55 minutes.

**Access**: `ssh office2-claude` only. The claude user does not have sudo.

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP03 --base WP02`

---

## Subtask T008: Register Agent in OpenClaw

**Purpose**: Create the felix-admin-escalation agent in OpenClaw.

**Steps**:
1. Read how the habits agent was registered — check the habits-ops
   runbook or run `ssh office2-claude "openclaw agents list"` to see
   the current agent configuration
2. Register the escalation agent:
   ```bash
   ssh office2-claude "openclaw agents create felix-admin-escalation \
     --workspace /data/services/openclaw/escalation-agent"
   ```
3. Verify registration:
   ```bash
   ssh office2-claude "openclaw agents list"
   ```
   Expected: `felix-admin-escalation` with workspace path shown.

---

## Subtask T009: Deploy Skill to office2

**Purpose**: Install the escalation skill in OpenClaw's skill system.

**Steps**:
1. Create the skill directory on office2:
   ```bash
   ssh office2-claude "mkdir -p /home/claude/.openclaw/skills/escalation"
   ```
2. Deploy the skill file:
   ```bash
   ssh office2-claude "cat > /home/claude/.openclaw/skills/escalation/SKILL.md" \
     < scripts/openclaw/skills/escalation/SKILL.md
   ```
3. Verify:
   ```bash
   ssh office2-claude "head -5 /home/claude/.openclaw/skills/escalation/SKILL.md"
   ```

---

## Subtask T010: Deploy Agent Workspace Files to office2

**Purpose**: Install all workspace files for the escalation agent.

**Steps**:
1. Create the workspace directory:
   ```bash
   ssh office2-claude "mkdir -p /data/services/openclaw/escalation-agent"
   ```
2. Deploy all workspace files:
   ```bash
   for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
     ssh office2-claude "cat > /data/services/openclaw/escalation-agent/$f" \
       < scripts/openclaw/agents/felix-admin-escalation/$f
   done
   ```
3. Verify all files present:
   ```bash
   ssh office2-claude "ls -la /data/services/openclaw/escalation-agent/"
   ```

---

## Subtask T011: Create Escalation Cron Job

**Purpose**: Configure the daily escalation check.

**Steps**:
1. Create the cron job:
   ```bash
   ssh office2-claude "openclaw cron create escalation-daily \
     --agent felix-admin-escalation \
     --schedule '0 12 * * *' \
     --message 'Run the daily escalation check per your standing orders.' \
     --to +16179300916 \
     --timeout 120 \
     --target isolated"
   ```
   Schedule: `0 12 * * *` = 12:00 UTC = 8:00 AM ET daily.

2. Verify the cron job:
   ```bash
   ssh office2-claude "openclaw cron list"
   ```
   Expected: `escalation-daily` visible with correct schedule.

---

## Subtask T012: Register in AGENT-REGISTRY.md

**Purpose**: Add the agent to the governance registry.

**File**: `docs/constitution/AGENT-REGISTRY.md`

**Add entry** following the existing format:
- Agent name: `felix-admin-escalation`
- Autonomy level: Assisted (Level 1)
- Deployed by: F019
- Scope: Overdue and at-risk task escalation via WhatsApp
- Workspace: `/data/services/openclaw/escalation-agent/`

Read the existing AGENT-REGISTRY.md first to match the format exactly.

---

## Subtask T013: Update service-inventory.json

**Purpose**: Add the agent and cron job to the architecture record.

**File**: `docs/design/architecture/data/service-inventory.json`

**Changes**:
1. Add `felix-admin-escalation` agent entry under the openclaw-gateway
   service's agents section (follow the habits agent entry format)
2. Add `escalation-daily` cron job entry
3. Set `updated_by: "F019"`
4. Update `last_updated` date

Read the existing service-inventory.json to match the format exactly.

---

## Subtask T014: Update service-inventory.md

**Purpose**: Update the narrative architecture documentation.

**File**: `docs/design/architecture/service-inventory.md`

Add `felix-admin-escalation` under the OpenClaw agents section following
the existing format. Include: agent name, purpose, schedule, scope.

Read the existing file to match format.

---

## Definition of Done

- [ ] Agent registered in OpenClaw (`openclaw agents list` shows it)
- [ ] Skill deployed to `/home/claude/.openclaw/skills/escalation/SKILL.md`
- [ ] All 5 workspace files deployed to `/data/services/openclaw/escalation-agent/`
- [ ] Cron job `escalation-daily` created at 12:00 UTC with correct `--to` flag
- [ ] AGENT-REGISTRY.md contains felix-admin-escalation at Assisted (Level 1)
- [ ] service-inventory.json updated with agent and cron entries, `updated_by: "F019"`
- [ ] service-inventory.md narrative matches JSON
- [ ] All documentation passes CI validation

## Risks

| Risk | Mitigation |
|------|------------|
| Agent registration command syntax wrong | Check habits agent registration pattern first |
| Cron schedule UTC/ET conversion error | Verified: 12:00 UTC = 8:00 AM ET (EDT, UTC-4) |
| Workspace path mismatch | Use consistent `/data/services/openclaw/escalation-agent/` everywhere |

## Reviewer Guidance

1. Verify agent appears in `openclaw agents list`
2. Confirm cron schedule is `0 12 * * *` (not `0 8 * * *` — that would be 8 UTC = 4 AM ET)
3. Check `--to +16179300916` is set on the cron job
4. Verify AGENT-REGISTRY.md entry has Assisted (Level 1)
5. Check service-inventory.json has `updated_by: "F019"`

---

**END OF WORK PACKAGE**
