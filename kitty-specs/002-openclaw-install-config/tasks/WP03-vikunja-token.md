---
work_package_id: WP03
title: Vikunja Token and Connectivity
lane: planned
dependencies: [WP02]
requirement_refs:
- FR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: 'Current branch at workflow start: main. Planning/base branch for this feature: main. Completed changes must merge into main.'
subtasks:
- T014
- T015
- T016
- T017
- T018
phase: Phase 2 - Integration
assignee: ''
agent: ''
shell_pid: ''
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

# Work Package Prompt: WP03 – Vikunja Token and Connectivity

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`

**Implementation command**: `spec-kitty implement WP03 --base WP02`

---

## Objectives & Success Criteria

Generate a persistent Vikunja API token, store it in the credential store, and verify OpenClaw can reach Vikunja.

**Success**: `curl` with stored token returns HTTP 200 from Vikunja. Token survives Vikunja restart. Credential file has mode 600.

## Context & Constraints

- **Research**: `kitty-specs/002-openclaw-install-config/research.md` (R-008)
- **Vikunja URL**: `http://100.92.197.90:3456` (Tailscale IP, established in F001)
- **Token generation**: Kent does this manually in Vikunja UI
- **Token name**: `openclaw-agent` (for traceability)

## Subtasks & Detailed Guidance

### Subtask T014 – Instructions for Vikunja Token Generation

**Purpose**: Guide Kent through creating a persistent API token in Vikunja.

**Steps**:
1. Present to Kent:
   ```
   Generate a Vikunja API token:

   1. Open http://office2:3456 in your browser
   2. Log in with your admin account
   3. Go to Settings → API Tokens
   4. Create a new token:
      - Name: openclaw-agent
      - Permissions: full access (or read/write tasks)
   5. Copy the token value — it will only be shown once

   Keep the token value ready for the next step.
   ```
2. Wait for Kent to confirm token is generated

**Files**: None.
**Parallel?**: No.

### Subtask T015 – Instructions for Token Placement

**Purpose**: Guide Kent to place the token in the credential store.

**Steps**:
1. Present to Kent:
   ```
   Place the Vikunja API token:

   ssh office2-claude  (or use existing terminal as claude)

   echo '<YOUR_VIKUNJA_TOKEN>' > /data/services/openclaw/secrets/vikunja-api
   chmod 600 /data/services/openclaw/secrets/vikunja-api

   Verify:
   stat /data/services/openclaw/secrets/vikunja-api
   (should show -rw------- owned by claude)
   ```
2. Wait for Kent to confirm

**Files**: None — manual step.
**Parallel?**: No — depends on T014.

### Subtask T016 – Verify Token Permissions

**Purpose**: Confirm the token file has correct ownership and permissions.

**Steps**:
1. `stat /data/services/openclaw/secrets/vikunja-api`
2. Expected: `-rw-------` (mode 600), owner `claude`
3. If wrong, fix: `chmod 600 /data/services/openclaw/secrets/vikunja-api`

**Files**: None — verification.
**Parallel?**: No.

### Subtask T017 – Verify Vikunja Connectivity

**Purpose**: Confirm the stored token authenticates to Vikunja.

**Steps**:
1. Run from office2:
   ```bash
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     http://100.92.197.90:3456/api/v1/info | python3 -m json.tool
   ```
2. Expected: HTTP 200 with JSON containing `"version": "v0.24.6"`
3. Also test a task endpoint:
   ```bash
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     http://100.92.197.90:3456/api/v1/projects
   ```
4. Expected: JSON array of projects (the ones created in F001)

**Files**: None — verification.
**Parallel?**: No — depends on T016.

### Subtask T018 – Verify Token Persists Across Restart

**Purpose**: Confirm the token is persistent, not a session JWT.

**Steps**:
1. Present to Kent: `sudo systemctl restart vikunja`
2. Wait 10 seconds for Vikunja to come back up
3. Re-run the connectivity test from T017
4. Expected: Same token still works after restart

**Files**: None — verification.
**Parallel?**: No.

## Risks & Mitigations

- **Vikunja doesn't support persistent API tokens**: Check Settings → API Tokens in UI. If not available, may need to use `POST /api/v1/tokens` endpoint or use a different auth approach.
- **Token scope too narrow**: Ensure the token has sufficient permissions for task CRUD.

## Review Guidance

- Verify token file exists with mode 600, owned by claude
- Verify curl returns HTTP 200 from Vikunja
- Verify token survives Vikunja restart
- Verify no token value appears in any committed file

## Activity Log

- 2026-03-26T22:28:20Z – system – lane=planned – Prompt created.
