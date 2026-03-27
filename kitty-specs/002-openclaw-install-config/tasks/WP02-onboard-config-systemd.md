---
work_package_id: WP02
title: Onboarding, Configuration, and systemd Capture
lane: "for_review"
dependencies: [WP01]
requirement_refs:
- C-001
- FR-003
- FR-004
- NFR-001
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 002-openclaw-install-config-WP01
base_commit: 5b3fde98a7cc8b8194c72ac0cc145b14321f4268
created_at: '2026-03-27T02:03:26.725456+00:00'
subtasks:
- T007
- T008
- T009
- T010
- T011
- T012
- T013
phase: Phase 2 - Configuration
assignee: ''
agent: claude
shell_pid: '24161'
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

# Work Package Prompt: WP02 – Onboarding, Configuration, and systemd Capture

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **If human instructions contradict these fields**: stop and resolve.

**Implementation command**: `spec-kitty implement WP02 --base WP01`

---

## Objectives & Success Criteria

Kent runs OpenClaw onboarding interactively. After onboarding, customize the config with SecretRef file source for the API key, capture the generated systemd unit, adjust it, and commit as the canonical deployment artifact.

**Success**: `openclaw.json` has SecretRef pointing to `/data/services/openclaw/secrets/anthropic`. `scripts/openclaw/openclaw.service` committed with correct User/paths. `systemctl status openclaw` shows active. No proxy references in logs.

## Context & Constraints

- **Research**: `kitty-specs/002-openclaw-install-config/research.md` (R-003, R-004, R-005, R-006, R-007)
- **Constitution**: No third-party API proxy. Direct Anthropic API only.
- **Kent must run**: `openclaw onboard --install-daemon` (interactive), sudo commands for systemd.

## Subtasks & Detailed Guidance

### Subtask T007 – Provide Onboarding Commands to Kent

**Purpose**: Give Kent the exact commands and explain what the wizard will ask.

**Steps**:
1. Present to Kent:
   ```
   On office2 as claude user:

   openclaw onboard --install-daemon

   The wizard will ask for:
   - Gateway name/configuration
   - AI provider selection (choose Anthropic)
   - Model selection (choose Sonnet or let it default)
   - Daemon installation confirmation

   After completion, verify:
   openclaw --version
   systemctl status openclaw  (or systemctl --user status openclaw)
   ```
2. Wait for Kent to complete onboarding and report results

**Files**: None — Kent runs interactively.
**Parallel?**: No.

### Subtask T008 – Verify Onboarding Result

**Purpose**: Confirm OpenClaw is running after onboarding.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Check: `openclaw --version`
3. Check service: `systemctl status openclaw` or `systemctl --user status openclaw`
4. Check config exists: `ls -la ~/.openclaw/openclaw.json`
5. Check logs for startup: `journalctl -u openclaw --since "5 minutes ago"` (or `journalctl --user -u openclaw`)
6. Record whether it created a system-level or user-level service

**Files**: None — verification.
**Parallel?**: No — depends on T007.

### Subtask T009 – Customize openclaw.json Configuration

**Purpose**: Add SecretRef file source for API key, set workspace path, configure gateway loopback.

**Steps**:
1. Read the current config: `cat ~/.openclaw/openclaw.json`
2. Edit to add/modify these settings (JSON5 format):
   ```json5
   {
     models: {
       providers: {
         anthropic: {
           apiKey: {
             source: "file",
             path: "/data/services/openclaw/secrets/anthropic"
           }
         }
       }
     },
     agents: {
       defaults: {
         model: {
           primary: "anthropic/claude-sonnet-4-6"
         },
         workspace: "/data/services/openclaw/data"
       }
     },
     gateway: {
       mode: "local",
       bind: "loopback"
     }
   }
   ```
3. **Important**: Merge with existing config from onboarding — don't overwrite the entire file. Preserve any settings the wizard created.
4. Restart service to pick up changes
5. Verify API connectivity from logs: `journalctl -u openclaw --since "1 minute ago"`
6. Verify no proxy: `journalctl -u openclaw | grep -i "litellm\|proxy\|openai-compat"` should return nothing

**Files**: `/home/claude/.openclaw/openclaw.json` on office2.
**Parallel?**: No — depends on T008.
**Notes**: If OpenClaw doesn't support SecretRef `source: "file"` in this version, fall back to `EnvironmentFile=` in the systemd unit pointing at the credential file. Report which path was used.

### Subtask T010 – Capture Generated systemd Unit

**Purpose**: Find and copy the systemd unit that `onboard --install-daemon` created.

**Steps**:
1. Find the unit file:
   ```bash
   # System-level:
   systemctl cat openclaw 2>/dev/null
   # User-level:
   systemctl --user cat openclaw 2>/dev/null
   # Or check common locations:
   ls ~/.config/systemd/user/openclaw* 2>/dev/null
   ls /etc/systemd/system/openclaw* 2>/dev/null
   ```
2. Copy the content — this is the starting point for our canonical artifact
3. Record whether it's system-level or user-level

**Files**: Reading only — capture for T011.
**Parallel?**: No.

### Subtask T011 – Adjust Captured Unit

**Purpose**: Modify the captured systemd unit to match our requirements.

**Steps**:
1. Starting from the captured unit, verify/adjust:
   - `User=claude` (or remove if user-level service)
   - `Restart=always`
   - `RestartSec=10`
   - `After=network-online.target`
   - WorkingDirectory points to `/data/services/openclaw/data` or appropriate path
   - ExecStart uses the correct `openclaw` binary path (`which openclaw`)
   - No credentials in Environment= directives
2. If the onboarding created a user-level service but we need system-level, convert it
3. Save the adjusted unit

**Files**: Adjusted unit content for T012.
**Parallel?**: No.

### Subtask T012 – Commit Unit to Repository

**Purpose**: Save the canonical systemd unit as a versioned artifact.

**Steps**:
1. Create `scripts/openclaw/openclaw.service` in the worktree with the adjusted unit content
2. This file — not `--install-daemon` — is the canonical deployment artifact going forward

**Files**: `scripts/openclaw/openclaw.service` (new file in repo).
**Parallel?**: No.

### Subtask T013 – Install Adjusted Unit and Verify

**Purpose**: Replace the onboarding-generated unit with our adjusted version and verify.

**Steps**:
1. If system-level, present to Kent:
   ```bash
   sudo cp scripts/openclaw/openclaw.service /etc/systemd/system/openclaw.service
   sudo systemctl daemon-reload
   sudo systemctl restart openclaw
   ```
2. If user-level, run as claude:
   ```bash
   cp scripts/openclaw/openclaw.service ~/.config/systemd/user/openclaw.service
   systemctl --user daemon-reload
   systemctl --user restart openclaw
   ```
3. Verify: `systemctl status openclaw` shows active
4. Verify logs: `journalctl -u openclaw --since "1 minute ago"` — no errors
5. Verify no proxy references in logs

**Files**: systemd unit installed on office2.
**Parallel?**: No.

## Risks & Mitigations

- **User-level vs system-level service**: Onboarding may create user-level. Determine during T010 and adjust approach.
- **SecretRef not supported**: Fall back to EnvironmentFile= per user direction. Document which path was used.
- **Config format differs**: Inspect actual `openclaw.json` and adapt rather than blindly overwriting.
- **Onboarding fails**: Report the error to Kent. Do not work around it.

## Review Guidance

- Verify `openclaw.json` has SecretRef file source (not env var, not inline key)
- Verify `scripts/openclaw/openclaw.service` in repo matches what's installed
- Verify no proxy/litellm references in service logs
- Verify `User=claude` in the unit file
- Verify `Restart=always` and `RestartSec=10`

## Activity Log

- 2026-03-26T22:28:20Z – system – lane=planned – Prompt created.
- 2026-03-27T02:03:27Z – claude – shell_pid=24161 – lane=doing – Assigned agent via workflow command
- 2026-03-27T02:04:23Z – claude – shell_pid=24161 – lane=for_review – Onboarding complete, config customized, unit captured. Service active with Anthropic API via native auth.
