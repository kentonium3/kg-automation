---
work_package_id: WP05
title: Acceptance Testing
lane: "doing"
dependencies: [WP01, WP02, WP03, WP04]
requirement_refs:
- FR-001
- FR-003
- NFR-001
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 002-openclaw-install-config-WP05-merge-base
base_commit: bc740360d47ed9a0c5fc7f1a54f34d60173909d9
created_at: '2026-03-27T02:23:49.689884+00:00'
subtasks:
- T025
- T026
- T027
- T028
- T029
- T030
- T031
phase: Phase 3 - Verification
assignee: ''
agent: "claude"
shell_pid: "28862"
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

# Work Package Prompt: WP05 – Acceptance Testing

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`

**Implementation command**: `spec-kitty implement WP05 --base WP04`

---

## Objectives & Success Criteria

Execute all acceptance scenarios from the spec. Document pass/fail results.

**Success**: All scenarios pass. Service active, credentials secure, API direct, Vikunja connected.

## Subtasks & Detailed Guidance

### Subtask T025 – Verify Service Active

**Purpose**: Confirm OpenClaw is running.

**Steps**:
1. `ssh office2-claude`
2. `systemctl status openclaw` (or `systemctl --user status openclaw`)
3. Expected: active (running)
4. Check `systemctl is-enabled openclaw` — should show "enabled"
5. Record: PASS or FAIL

**Parallel?**: Yes.

### Subtask T026 – Verify Service Restart Recovery

**Purpose**: Confirm service recovers after restart.

**Steps**:
1. Present to Kent: `sudo systemctl restart openclaw`
2. Wait 10 seconds
3. `systemctl status openclaw` — should show active
4. Record time to recovery (should be within 30 seconds per NFR-001)
5. Record: PASS or FAIL

**Parallel?**: No — modifies state.

### Subtask T027 – Verify No Proxy in Logs

**Purpose**: Confirm API calls go direct to Anthropic.

**Steps**:
1. `journalctl -u openclaw --since "1 hour ago" | grep -i "litellm\|proxy\|openai-compat\|openai.com"`
2. Expected: no matches
3. Also check config: `cat /home/claude/.openclaw/openclaw.json | grep -i proxy`
4. Expected: no proxy configuration
5. Record: PASS or FAIL

**Parallel?**: Yes.

### Subtask T028 – Verify Credential Permissions

**Purpose**: Confirm credential store security.

**Steps**:
1. `stat /data/services/openclaw/secrets/` — should show `drwx------` (700), owner claude
2. `stat /data/services/openclaw/secrets/anthropic` — should show `-rw-------` (600), owner claude
3. `stat /data/services/openclaw/secrets/vikunja-api` — should show `-rw-------` (600), owner claude
4. `git status` in repo — no secrets files tracked
5. Record: PASS or FAIL

**Parallel?**: Yes.

### Subtask T029 – Verify Vikunja Connectivity

**Purpose**: Confirm OpenClaw can reach Vikunja.

**Steps**:
1. From office2:
   ```bash
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     http://100.92.197.90:3456/api/v1/info
   ```
2. Expected: HTTP 200 with version info
3. Record: PASS or FAIL

**Parallel?**: Yes.

### Subtask T030 – Verify API Key Not in Process Environment

**Purpose**: Confirm SecretRef file source works — key is not in process environment.

**Steps**:
1. Find OpenClaw's PID:
   ```bash
   systemctl show openclaw --property=MainPID
   # or: pgrep -f openclaw
   ```
2. Check process environment:
   ```bash
   cat /proc/<PID>/environ | tr '\0' '\n' | grep -i anthropic
   ```
3. Expected: no match (key is read from file, not set as env var)
4. If key IS in the environment, the SecretRef file source didn't work — record as FAIL and note the fallback used
5. Record: PASS or FAIL

**Parallel?**: Yes.
**Notes**: This is the critical security verification. If the API key appears in the process environment, the SecretRef approach failed and the implementation used an env var fallback.

### Subtask T031 – Document Acceptance Results

**Purpose**: Create the acceptance results document.

**Steps**:
1. Create `docs/handbooks/f002-acceptance-results.md` with:
   - Frontmatter (title, doc_type: reference, status: approved)
   - Test results table (T025-T030 with PASS/FAIL and notes)
   - Success criteria table (SC-001 through SC-008 with YES/NO)
   - Any deferred items with justification
2. Run `python tooling/scripts/validate_docs.py` to verify

**Files**: `docs/handbooks/f002-acceptance-results.md` (new).
**Parallel?**: No — runs last.

## Risks & Mitigations

- **Process env check requires correct PID**: Use systemctl show or pgrep
- **Restart test requires sudo**: Present to Kent

## Review Guidance

- All 7 subtasks have documented PASS/FAIL
- T030 (process environment) is the most critical security check
- Any FAIL must have a clear description and remediation path

## Activity Log

- 2026-03-26T22:28:20Z – system – lane=planned – Prompt created.
- 2026-03-27T02:23:50Z – claude – shell_pid=28862 – lane=doing – Assigned agent via workflow command
