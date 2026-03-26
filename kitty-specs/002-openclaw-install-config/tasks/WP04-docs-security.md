---
work_package_id: WP04
title: Ops Runbook, Architecture Docs, Security Baseline
lane: planned
dependencies: [WP02]
requirement_refs:
- FR-006
- FR-007
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T019
- T020
- T021
- T022
- T023
- T024
phase: Phase 2 - Documentation
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

# Work Package Prompt: WP04 – Ops Runbook, Architecture Docs, Security Baseline

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`

**Implementation command**: `spec-kitty implement WP04 --base WP02`

---

## Objectives & Success Criteria

Create the OpenClaw ops runbook, update architecture documentation (JSON + markdown) to reflect the new service and credentials, and reset security baselines.

**Success**: Runbook passes `validate_docs.py`. JSON files have `updated_by: "F002"`. Security audit produces no false positives for OpenClaw.

## Context & Constraints

- **Runbook format**: Match `docs/handbooks/vikunja-ops.md` structure
- **Architecture docs**: `docs/design/architecture/data/` (JSON) and `docs/design/architecture/` (markdown)
- **Func-spec section**: `docs/func-spec/F002_openclaw_install.md` "Architecture Documentation Updates"

## Subtasks & Detailed Guidance

### Subtask T019 – Create openclaw-ops.md with Frontmatter

**Purpose**: Establish the runbook file.

**Steps**:
1. Create `docs/handbooks/openclaw-ops.md` with frontmatter:
   ```yaml
   ---
   title: OpenClaw Operations Runbook
   doc_type: handbook
   status: draft
   ---
   ```

**Files**: `docs/handbooks/openclaw-ops.md` (new).
**Parallel?**: Yes.

### Subtask T020 – Document Operational Procedures

**Purpose**: Cover all operational topics listed in FR-007.

**Steps**:
1. Add sections for:
   - **Installed version**: Pinned tag, where it's recorded
   - **Service management**: start/stop/restart commands (note system vs user level)
   - **Logs**: `journalctl -u openclaw` commands
   - **Credential rotation**: How to replace API key or Vikunja token, verify reconnection
   - **Version updates**: Pin new version, `npm install -g openclaw@<version>`, restart service
   - **API connectivity check**: `journalctl` verification, no proxy check
   - **Skill directory**: Location for future skill files (note: no skills installed in F002)
   - **Security baseline reset**: Procedure after updates
2. Reference actual paths, service names, and commands from the deployment

**Files**: `docs/handbooks/openclaw-ops.md`.
**Parallel?**: Yes — sections can be written independently.

### Subtask T021 – Update service-inventory.json

**Purpose**: Add OpenClaw to the machine-readable service inventory.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json`
2. Add entry to the `services` array:
   ```json
   {
     "name": "openclaw",
     "type": "npm-global",
     "version": "v2026.3.24",
     "host": "office2",
     "port": 18789,
     "bind_ip": "127.0.0.1",
     "systemd_unit": "openclaw.service",
     "systemd_user": "claude",
     "config_path": "/home/claude/.openclaw/openclaw.json",
     "data_path": "/data/services/openclaw/data",
     "secrets_path": "/data/services/openclaw/secrets",
     "backup_included": true,
     "deployed_by": "F002",
     "status": "running",
     "purpose": "Orchestration and intelligence layer"
   }
   ```
3. Set `last_updated` and `updated_by: "F002"` at the top level
4. Adjust port/bind based on actual deployment (may differ from research)

**Files**: `docs/design/architecture/data/service-inventory.json`.
**Parallel?**: Yes.

### Subtask T022 – Update credential-manifest.json

**Purpose**: Move anthropic and vikunja-api from planned to active.

**Steps**:
1. Read `docs/design/architecture/data/credential-manifest.json`
2. Move `anthropic` from `planned_credentials` to `credentials`:
   ```json
   {
     "name": "anthropic",
     "type": "api-key",
     "scope": "Claude API for OpenClaw orchestration",
     "storage": "/data/services/openclaw/secrets/anthropic",
     "host": "office2",
     "used_by": ["openclaw"],
     "deployed_by": "F002"
   }
   ```
3. Move `vikunja-api` from `planned_credentials` to `credentials`:
   ```json
   {
     "name": "vikunja-api",
     "type": "api-token",
     "scope": "OpenClaw agent access to Vikunja REST API",
     "storage": "/data/services/openclaw/secrets/vikunja-api",
     "host": "office2",
     "used_by": ["openclaw"],
     "deployed_by": "F002",
     "notes": "Persistent token named openclaw-agent, generated in Vikunja UI"
   }
   ```
4. Remove both from `planned_credentials`
5. Set `last_updated` and `updated_by: "F002"`

**Files**: `docs/design/architecture/data/credential-manifest.json`.
**Parallel?**: Yes.

### Subtask T023 – Update Markdown Architecture Views

**Purpose**: Keep markdown views consistent with JSON.

**Steps**:
1. Update `docs/design/architecture/service-inventory.md`:
   - Add OpenClaw to "Running Services" table
   - Add "OpenClaw (F002)" deployment details section
2. Update `docs/design/architecture/credentials-and-secrets.md`:
   - Move `anthropic` and `vikunja-api` from "Planned" to "Active" table
3. Run `python tooling/scripts/validate_docs.py` to verify

**Files**: Two markdown files.
**Parallel?**: Yes.

### Subtask T024 – Reset Security Baselines

**Purpose**: Update baselines to include the new OpenClaw service.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Check if baseline reset requires sudo:
   ```bash
   ls -la /data/services/security-monitor/scripts/
   ```
3. If sudo required, present to Kent:
   ```bash
   sudo /data/services/security-monitor/scripts/generate-baselines.sh
   ```
   Or if no script exists, present manual steps to regenerate baselines
4. Verify: run audit manually and confirm no alerts:
   ```bash
   /data/services/security-monitor/scripts/audit.sh
   cat /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log
   ```

**Files**: None — office2 operation.
**Parallel?**: Yes — independent of docs work.
**Notes**: The audit script runs via `sg docker -c` in crontab, so running it manually may need the docker group context.

## Risks & Mitigations

- **Security baseline reset requires sudo**: Present to Kent
- **validate_docs.py fails on new runbook**: Check frontmatter fields match allowed values

## Review Guidance

- Runbook covers all 7 topics listed in FR-007
- JSON files have `updated_by: "F002"` and correct entries
- Markdown views match JSON sources
- All docs pass `validate_docs.py`

## Activity Log

- 2026-03-26T22:28:20Z – system – lane=planned – Prompt created.
