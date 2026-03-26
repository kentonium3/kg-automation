---
work_package_id: WP01
title: Install OpenClaw and Credential Store
lane: "doing"
dependencies: []
requirement_refs:
- C-002
- C-003
- C-004
- C-005
- FR-001
- FR-002
- NFR-002
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 68249caa13e1c28a19b00679a2c7440a7df969a1
created_at: '2026-03-26T22:45:57.076201+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1 - Foundation
assignee: ''
agent: "claude"
shell_pid: "99649"
review_status: ''
reviewed_by: ''
review_feedback: ''
history:
- timestamp: '2026-03-26T22:28:20Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP01 – Install OpenClaw and Credential Store

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP01`

---

## Objectives & Success Criteria

Install OpenClaw v2026.3.24 on office2 via npm global install. Create the credential store directory and data directory with correct permissions. Provide Kent with instructions for placing the Anthropic API key.

**Success**: `openclaw --version` returns version info. `/data/services/openclaw/secrets/` exists with mode 700. `install.sh` committed to repo.

## Context & Constraints

- **SSH**: `ssh office2-claude` only. Sudo commands presented to Kent.
- **Research**: `kitty-specs/002-openclaw-install-config/research.md` (R-001, R-002)
- **Data model**: `kitty-specs/002-openclaw-install-config/data-model.md`
- **Key constraint**: No credentials in committed files. Credential files placed by Kent manually.

## Subtasks & Detailed Guidance

### Subtask T001 – Verify Node.js Version

**Purpose**: Confirm Node.js 22.16+ is available before installing OpenClaw.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Check: `node --version` (expect v22.22.1 or higher)
3. Check npm: `npm --version`
4. If Node.js is missing or too old, STOP and report

**Files**: None.
**Parallel?**: No — must pass before T002.

### Subtask T002 – Install OpenClaw via npm

**Purpose**: Install OpenClaw at the pinned version.

**Steps**:
1. Run: `npm install -g openclaw@v2026.3.24`
2. If permission error, check `npm config get prefix` — if it's `/usr/local`, this needs sudo. Present to Kent: `sudo npm install -g openclaw@v2026.3.24`
3. Verify: `openclaw --version`
4. Verify binary location: `which openclaw`

**Files**: None (global npm install).
**Parallel?**: No.
**Notes**: If the exact version tag `v2026.3.24` doesn't work, try `2026.3.24` (without `v` prefix). Check npm for the exact tag format.

### Subtask T003 – Create Directory Structure

**Purpose**: Create the credential store and data directories on office2.

**Steps**:
1. Create directories:
   ```bash
   mkdir -p /data/services/openclaw/secrets
   mkdir -p /data/services/openclaw/data
   ```
2. Verify: `ls -la /data/services/openclaw/`

**Files**: Directories on office2.
**Parallel?**: No — needed by T004.

### Subtask T004 – Set Credential Store Permissions

**Purpose**: Lock down the credential store to claude user only.

**Steps**:
1. Set permissions:
   ```bash
   chmod 700 /data/services/openclaw/secrets
   ```
2. Verify: `stat /data/services/openclaw/secrets/` should show `drwx------` and owner `claude`
3. Verify the claude user owns it: `ls -la /data/services/openclaw/`

**Files**: Permission changes on office2.
**Parallel?**: No.

### Subtask T005 – Create install.sh in Repo

**Purpose**: Capture installation steps as a repeatable script committed to the repo.

**Steps**:
1. Create `scripts/openclaw/install.sh` in the worktree with:
   - Node.js version check
   - npm install command (pinned version)
   - Directory creation
   - Permission setting
   - Credential placement instructions (printed, not executed)
2. Make executable: `chmod +x scripts/openclaw/install.sh`

**Example structure**:
```bash
#!/usr/bin/env bash
set -euo pipefail
OPENCLAW_VERSION="v2026.3.24"

echo "=== OpenClaw Install ==="

# Check Node.js
node_ver=$(node --version 2>/dev/null || echo "none")
echo "[CHECK] Node.js: $node_ver (need 22.16+)"

# Install OpenClaw
echo "Installing openclaw@${OPENCLAW_VERSION}..."
npm install -g "openclaw@${OPENCLAW_VERSION}"
echo "[OK] $(openclaw --version)"

# Create directories
mkdir -p /data/services/openclaw/secrets
mkdir -p /data/services/openclaw/data
chmod 700 /data/services/openclaw/secrets

echo ""
echo "=== MANUAL STEPS ==="
echo "1. Place Anthropic API key:"
echo "   echo '<KEY>' > /data/services/openclaw/secrets/anthropic"
echo "   chmod 600 /data/services/openclaw/secrets/anthropic"
echo ""
echo "2. Run onboarding:"
echo "   openclaw onboard --install-daemon"
```

**Files**: `scripts/openclaw/install.sh` (new file in repo).
**Parallel?**: Yes — can be written alongside T002-T004.

### Subtask T006 – Instructions for Anthropic API Key Placement

**Purpose**: Provide Kent with exact commands to place the API key in the credential store.

**Steps**:
1. Present to Kent:
   ```
   To place your Anthropic API key:

   ssh office2-claude  (or use your existing terminal as claude)

   echo '<YOUR_ANTHROPIC_API_KEY>' > /data/services/openclaw/secrets/anthropic
   chmod 600 /data/services/openclaw/secrets/anthropic

   Verify:
   stat /data/services/openclaw/secrets/anthropic
   (should show -rw------- owned by claude)

   cat /data/services/openclaw/secrets/anthropic | wc -c
   (should show non-zero character count — don't cat the actual key)
   ```
2. Wait for Kent to confirm key is placed
3. Verify permissions: `stat /data/services/openclaw/secrets/anthropic` shows `-rw-------` and owner `claude`

**Files**: None — manual step.
**Parallel?**: No — depends on T003/T004.

## Risks & Mitigations

- **npm global requires sudo**: Check `npm config get prefix` first. If `/usr/local`, present sudo command to Kent.
- **Version tag format**: Try both `v2026.3.24` and `2026.3.24` if one fails.
- **Directory permissions**: Verify with `stat` after setting.

## Review Guidance

- Verify `openclaw --version` returns the pinned version
- Verify credential store is mode 700, owned by claude
- Verify no secrets appear in any committed file
- Verify `install.sh` prints instructions but does not contain actual credentials

## Activity Log

- 2026-03-26T22:28:20Z – system – lane=planned – Prompt created.
- 2026-03-26T22:45:57Z – claude – shell_pid=95461 – lane=doing – Assigned agent via workflow command
- 2026-03-26T23:11:51Z – claude – shell_pid=95461 – lane=for_review – OpenClaw v2026.3.24 installed, credential store created (mode 700), API key placed (mode 600). install.sh committed.
- 2026-03-26T23:12:07Z – claude – shell_pid=99649 – lane=doing – Started review via workflow command
