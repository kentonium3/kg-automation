---
work_package_id: WP04
title: Deploy Updated Agent Files to Office2
lane: "doing"
dependencies: [WP03]
requirement_refs:
- FR-14
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 011-second-brain-vault-cleanup-WP03
base_commit: 7ada443ff046627f7a445a5f71b17f9263a4d166
created_at: '2026-04-01T19:31:53.904132+00:00'
subtasks: [T016, T017, T018]
shell_pid: "27150"
history:
- date: '2026-04-01T18:30:16Z'
  event: created
  actor: claude
---

# WP04: Deploy Updated Agent Files to Office2

## Implementation command

```bash
spec-kitty implement WP04 --base WP03
```

## Objective

Copy the updated agent workspace files (TOOLS.md, AGENTS.md) from the
kg-automation repo to the deployed OpenClaw agent workspaces on office2,
and restart the agents so they pick up the new vault paths.

## Context

- **Source files** (in kg-automation repo, updated in WP03):
  - `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`
  - `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
  - `scripts/openclaw/agents/felix-admin-habits/TOOLS.md`
- **Deploy targets on office2**:
  - `/data/services/openclaw/inbox-agent/TOOLS.md`
  - `/data/services/openclaw/inbox-agent/AGENTS.md`
  - `/data/services/openclaw/habits-agent/TOOLS.md`
- **SSH access**: `ssh office2-claude` (claude user has write access to
  `/data/services/openclaw/` directories)

## Subtask guidance

### T016: Deploy inbox-agent files

**Purpose**: Copy updated TOOLS.md and AGENTS.md to the inbox-agent workspace.

**Steps**:
1. Copy files via scp:
   ```bash
   scp scripts/openclaw/agents/felix-admin-capture/TOOLS.md office2-claude:/data/services/openclaw/inbox-agent/TOOLS.md
   scp scripts/openclaw/agents/felix-admin-capture/AGENTS.md office2-claude:/data/services/openclaw/inbox-agent/AGENTS.md
   ```
2. Verify on office2:
   ```bash
   ssh office2-claude "grep 'notes' /data/services/openclaw/inbox-agent/TOOLS.md"
   ssh office2-claude "grep 'vault' /data/services/openclaw/inbox-agent/TOOLS.md"
   ```

**Validation**:
- [ ] TOOLS.md on office2 references `notes/` path
- [ ] No `vault` references remain in deployed TOOLS.md
- [ ] AGENTS.md on office2 references `notes/` path

### T017: Deploy habits-agent files

**Purpose**: Copy updated TOOLS.md to the habits-agent workspace.

**Steps**:
1. Copy file:
   ```bash
   scp scripts/openclaw/agents/felix-admin-habits/TOOLS.md office2-claude:/data/services/openclaw/habits-agent/TOOLS.md
   ```
2. Verify:
   ```bash
   ssh office2-claude "grep 'notes' /data/services/openclaw/habits-agent/TOOLS.md"
   ssh office2-claude "grep 'vault' /data/services/openclaw/habits-agent/TOOLS.md"
   ```

**Validation**:
- [ ] TOOLS.md on office2 references `notes/` path
- [ ] No `vault` references remain

### T018: Restart OpenClaw agents

**Purpose**: Restart the Felix agents so they pick up the new workspace files.

**Steps**:
1. Check current agent status:
   ```bash
   ssh office2-claude "systemctl --user status openclaw-inbox.timer 2>&1 | head -5"
   ssh office2-claude "systemctl --user status openclaw-habits.timer 2>&1 | head -5"
   ```
2. If timers exist, restart:
   ```bash
   ssh office2-claude "systemctl --user restart openclaw-inbox.timer"
   ssh office2-claude "systemctl --user restart openclaw-habits.timer"
   ```
3. If no systemd timers (agents run via cron or manual triggers): note this
   and confirm with Kent how agents are restarted.

**Note**: OpenClaw agents read their workspace files at each invocation, so
they may not need an explicit restart — the next scheduled run will pick up
the new files. But restarting the timer ensures a clean state.

**Validation**:
- [ ] Agent timers/services show active status
- [ ] No stale vault path references in any deployed agent file on office2

## Post-completion verification

Run a comprehensive check on office2:
```bash
ssh office2-claude "grep -r 'second-brain/vault' /data/services/openclaw/ 2>/dev/null"
```
Expected: no output.

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`

## Definition of Done

- All 3 agent workspace files deployed to office2
- Zero `second-brain/vault` references in deployed files
- Agents restarted or confirmed to pick up changes on next run

## Risks

- **File permissions**: The claude user should have write access to
  `/data/services/openclaw/` — verify before copying
- **Agent state**: If an agent is mid-execution during file copy, it will
  use the old file for that run. This is harmless — the next run picks up
  the new file.
