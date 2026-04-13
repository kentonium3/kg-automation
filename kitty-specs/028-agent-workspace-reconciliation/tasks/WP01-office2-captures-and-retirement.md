---
work_package_id: WP01
title: Office2 captures and main-patches retirement
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-005
- FR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-028-agent-workspace-reconciliation
base_commit: 03e0ba7165a293b7bb2468f49cd74a19fcacbb22
created_at: '2026-04-13T17:40:17.012621+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: '77023'
history:
- date: '2026-04-13'
  action: created
  agent: claude-opus-4-6
authoritative_surface: scripts/openclaw/agents/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/main/AGENTS.md
- scripts/openclaw/agents/main/TOOLS.md
- scripts/openclaw/agents/main/IDENTITY.md
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/main-patches/**
tags: []
---

# WP01: Office2 Captures and Main-Patches Retirement

## Objective

Capture 4 workspace files from office2 into the kg-automation repo and retire the `main-patches/` overlay pattern. This resolves the repo-missing files (#157) and the remaining capture-direction drift (#156).

## Context

Fresh probe data (2026-04-13, research.md R1) shows:

| Agent | File | Office2 | Repo | Action |
|---|---|---|---|---|
| main | AGENTS.md | 258 lines, `bbd2866d` | MISSING | Capture |
| main | TOOLS.md | 40 lines, `78f3e26b` | MISSING | Capture |
| main | IDENTITY.md | 23 lines, `1379f924` | MISSING | Capture |
| capture | AGENTS.md | 728 lines, `9d68f37a` | 694 lines, `ce7c914f` | Capture (office2 has 34 more lines) |

The main agent's workspace is at `/data/services/openclaw/data/` (implicit default — no explicit `workspace` field in `openclaw.json`).

The capture agent's workspace is at `/data/services/openclaw/inbox-agent/`.

The `scripts/openclaw/agents/main-patches/` directory contains two files (`inbox-delegation.md`, `habits-delegation.md`) that document patches appended to `data/AGENTS.md`. This pattern is being retired in favor of the single-file approach used by all other agents (plan.md D3).

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`
- Execution worktree: allocated by spec-kitty lane assignment per `lanes.json`

## Detailed Guidance

### T001: Capture main/AGENTS.md from office2

**Purpose**: The main agent's standing orders file (258 lines) exists only on office2. Bring it into the repo.

**Steps**:
1. SCP the file from office2:
   ```bash
   scp office2-claude:/data/services/openclaw/data/AGENTS.md scripts/openclaw/agents/main/AGENTS.md
   ```
2. Verify the captured file matches the office2 original:
   ```bash
   ssh office2-claude 'sha256sum /data/services/openclaw/data/AGENTS.md'
   shasum -a 256 scripts/openclaw/agents/main/AGENTS.md
   ```
3. Confirm line count is 258 and hash starts with `bbd2866d`

**Files**: `scripts/openclaw/agents/main/AGENTS.md` (new file)

### T002: Capture main/TOOLS.md from office2

**Purpose**: The main agent's tools file (40 lines) exists only on office2. Note: this is currently an unmodified OpenClaw factory template (hash matches tasker's factory TOOLS.md: `78f3e26b`). Capture it anyway for completeness — having it in the repo establishes the tracking baseline.

**Steps**:
1. SCP: `scp office2-claude:/data/services/openclaw/data/TOOLS.md scripts/openclaw/agents/main/TOOLS.md`
2. Verify hash matches `78f3e26b8625ea28...`

**Files**: `scripts/openclaw/agents/main/TOOLS.md` (new file)

### T003: Capture main/IDENTITY.md from office2

**Purpose**: The main agent's identity file (23 lines) exists only on office2. This is also currently a factory template with unfilled placeholders. Capture for tracking baseline.

**Steps**:
1. SCP: `scp office2-claude:/data/services/openclaw/data/IDENTITY.md scripts/openclaw/agents/main/IDENTITY.md`
2. Verify hash matches `1379f924cf4b4d6d...`

**Files**: `scripts/openclaw/agents/main/IDENTITY.md` (new file)

### T004: Capture capture/AGENTS.md from office2

**Purpose**: The felix-admin-capture agent's AGENTS.md on office2 has 728 lines (34 more than repo's 694). The office2 version is authoritative — it contains content that was added during operation but never committed.

**Steps**:
1. Before overwriting, diff the two versions to understand what's being added:
   ```bash
   scp office2-claude:/data/services/openclaw/inbox-agent/AGENTS.md /tmp/capture-agents-office2.md
   diff scripts/openclaw/agents/felix-admin-capture/AGENTS.md /tmp/capture-agents-office2.md
   ```
2. Review the diff to confirm it's legitimate content (not corruption or test artifacts)
3. Copy the office2 version to the repo:
   ```bash
   cp /tmp/capture-agents-office2.md scripts/openclaw/agents/felix-admin-capture/AGENTS.md
   ```
4. Verify hash matches `9d68f37a91c9cb59...`

**Files**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (updated)

### T005: Archive and remove main-patches/ directory

**Purpose**: The `main-patches/` overlay pattern is retired (plan.md D3). The content of `inbox-delegation.md` and `habits-delegation.md` is already reflected in the merged `data/AGENTS.md` on office2, which was captured in T001.

**Steps**:
1. Verify that the patch content exists in the captured `main/AGENTS.md`:
   ```bash
   # Check that inbox delegation content is present
   grep -l "inbox" scripts/openclaw/agents/main/AGENTS.md
   # Check that habits delegation content is present
   grep -l "habit" scripts/openclaw/agents/main/AGENTS.md
   ```
2. If confirmed, remove the directory:
   ```bash
   git rm -r scripts/openclaw/agents/main-patches/
   ```
3. The commit message should note the retirement reason

**Files**: `scripts/openclaw/agents/main-patches/` (deleted)

## Definition of Done

- [ ] `scripts/openclaw/agents/main/` contains AGENTS.md, SOUL.md, TOOLS.md, USER.md, IDENTITY.md (5 files — SOUL.md and USER.md already existed)
- [ ] `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` matches office2 content (728 lines, hash `9d68f37a`)
- [ ] `scripts/openclaw/agents/main-patches/` is deleted from the repo
- [ ] All captures verified via SHA256 hash comparison
- [ ] Single commit with descriptive message

## Risks

- **SSH connectivity**: If office2 is unreachable, SCP will fail. Verify connectivity first with `ssh office2-claude 'echo ok'`.
- **Content verification**: The capture diff (T004) might reveal unexpected content. If anything looks wrong, stop and report before committing.

## Reviewer Guidance

- Verify each captured file's hash matches the expected value from research.md R1
- Confirm main-patches/ content is present in the captured main/AGENTS.md
- Check that no other files were accidentally modified
