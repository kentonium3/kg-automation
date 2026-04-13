---
work_package_id: WP02
title: Baseline manifests and enforcement config
dependencies:
- WP01
requirement_refs:
- FR-007
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
agent: "claude:opus-4-6:implementer:implementer"
shell_pid: "83505"
history:
- date: '2026-04-13'
  action: created
  agent: claude-opus-4-6
authoritative_surface: scripts/openclaw/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/baseline-manifest.json
- scripts/openclaw/agents/factory-baselines.json
- scripts/openclaw/enforcement/drift-check-config.json
- scripts/openclaw/enforcement/__init__.py
tags: []
---

# WP02: Baseline Manifests and Enforcement Config

## Objective

Generate machine-readable JSON artifacts that record the post-reconciliation state of all agent workspace files and configure the enforcement script.

## Context

After WP01 completes, all 25 workspace files across 5 agents will be tracked in the repo. This WP creates the reference data the enforcement script (WP03/WP04) uses:

1. **baseline-manifest.json** — SHA256 hashes of all files on both sides, the "last known good" state for three-way diff
2. **factory-baselines.json** — hashes of known factory-default templates, used to distinguish "never customized" from "customized"
3. **drift-check-config.json** — agent-to-workspace mapping, notification config, enforcement mode

See data-model.md for full schemas.

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`
- Execution worktree: allocated by spec-kitty lane assignment per `lanes.json`

## Detailed Guidance

### T006: Generate baseline-manifest.json

**Purpose**: Record the SHA256 hash of every tracked workspace file on both repo and office2 after WP01 reconciliation. This becomes the baseline for three-way diff.

**Steps**:
1. Write a Python helper script (`scripts/openclaw/enforcement/generate_manifest.py`) that:
   - Reads agent mapping from `drift-check-config.json` (or hardcode for initial generation)
   - For each agent, computes SHA256 of each file locally (repo) and remotely (office2 via SSH)
   - Outputs `baseline-manifest.json` in the schema from data-model.md

2. The manifest must be generated AFTER WP01 captures are committed and pushed. For files that were just captured (main 3 files, capture AGENTS.md), the repo and office2 hashes should be identical.

3. For files where repo is authoritative but deploy hasn't happened yet (tasker SOUL/TOOLS/USER/IDENTITY), the hashes will differ — that's expected. Record both. WP05 deploy will bring them into alignment, and the manifest should be regenerated post-deploy.

4. Schema (from data-model.md):
   ```json
   {
     "generated_at": "<ISO 8601>",
     "generated_by": "mission-028",
     "agents": {
       "<agent-id>": {
         "workspace_path": "<office2 path>",
         "repo_path": "<relative repo path>",
         "files": {
           "<filename>": {
             "repo_sha256": "<hash>",
             "office2_sha256": "<hash>",
             "lines": <int>,
             "tracked": true,
             "factory_default": false
           }
         }
       }
     }
   }
   ```

5. Output location: `scripts/openclaw/agents/baseline-manifest.json`

**Files**:
- `scripts/openclaw/agents/baseline-manifest.json` (new)
- `scripts/openclaw/enforcement/generate_manifest.py` (new, helper)

**Validation**:
- [ ] Every agent from openclaw.json has an entry
- [ ] Every workspace file (AGENTS.md, SOUL.md, TOOLS.md, USER.md, IDENTITY.md) has an entry
- [ ] Captured files (main 3, capture AGENTS.md) show matching repo/office2 hashes
- [ ] JSON is valid and parseable

### T007: Generate factory-baselines.json

**Purpose**: Record SHA256 hashes of known unmodified OpenClaw factory templates. Used by the enforcement script to detect when a factory-default file gets customized.

**Steps**:
1. From research.md R6, the known factory hashes are:
   - `BOOTSTRAP.md`: `c6545993b6e07b97...` (identical across all agents)
   - `TOOLS.md` (unmodified): `78f3e26b8625ea28...` (matches main and tasker)
   - `IDENTITY.md` template variant 1 (23 lines, blanks): hash from main agent
   - `IDENTITY.md` template variant 2 (6 lines, minimal): hash from tasker/capture/habits/escalation agents

2. Create `scripts/openclaw/agents/factory-baselines.json`:
   ```json
   {
     "openclaw_version": "2026.3.24",
     "baselines": {
       "BOOTSTRAP.md": "<full hash>",
       "TOOLS.md": "<full hash>",
       "IDENTITY.md": {
         "template_full": "<full hash from main>",
         "template_minimal": "<full hash from tasker>"
       }
     }
   }
   ```

3. Compute full hashes from the actual files (don't use truncated hashes from research.md)

**Files**: `scripts/openclaw/agents/factory-baselines.json` (new)

### T008: Create drift-check-config.json

**Purpose**: Configuration for the enforcement script — agent mapping, notification settings, enforcement mode.

**Steps**:
1. Create `scripts/openclaw/enforcement/drift-check-config.json` using the mapping from research.md R7:

   ```json
   {
     "enforcement_mode": "last-author-wins",
     "agents": {
       "main": {
         "workspace_path": "/data/services/openclaw/data",
         "repo_path": "scripts/openclaw/agents/main",
         "tracked_files": ["AGENTS.md", "SOUL.md", "TOOLS.md", "USER.md", "IDENTITY.md"],
         "excluded_files": ["HEARTBEAT.md", "BOOTSTRAP.md"]
       },
       "felix-admin-capture": {
         "workspace_path": "/data/services/openclaw/inbox-agent",
         "repo_path": "scripts/openclaw/agents/felix-admin-capture",
         "tracked_files": ["AGENTS.md", "SOUL.md", "TOOLS.md", "USER.md", "IDENTITY.md"],
         "excluded_files": ["HEARTBEAT.md", "BOOTSTRAP.md"]
       },
       "felix-admin-habits": {
         "workspace_path": "/data/services/openclaw/habits-agent",
         "repo_path": "scripts/openclaw/agents/felix-admin-habits",
         "tracked_files": ["AGENTS.md", "SOUL.md", "TOOLS.md", "USER.md", "IDENTITY.md"],
         "excluded_files": ["HEARTBEAT.md", "BOOTSTRAP.md"]
       },
       "felix-admin-escalation": {
         "workspace_path": "/data/services/openclaw/escalation-agent",
         "repo_path": "scripts/openclaw/agents/felix-admin-escalation",
         "tracked_files": ["AGENTS.md", "SOUL.md", "TOOLS.md", "USER.md", "IDENTITY.md"],
         "excluded_files": ["HEARTBEAT.md", "BOOTSTRAP.md"]
       },
       "felix-admin-tasker": {
         "workspace_path": "/data/services/openclaw/tasker-agent",
         "repo_path": "scripts/openclaw/agents/felix-admin-tasker",
         "tracked_files": ["AGENTS.md", "SOUL.md", "TOOLS.md", "USER.md", "IDENTITY.md"],
         "excluded_files": ["HEARTBEAT.md", "BOOTSTRAP.md"]
       }
     },
     "notification": {
       "channel": "whatsapp",
       "openclaw_agent": "main",
       "recipient": "<kent-e164-number>",
       "issue_repo": "kentonium3/kg-automation",
       "issue_labels": ["drift-alert", "area/felix-core"]
     },
     "factory_baselines_path": "../agents/factory-baselines.json",
     "baseline_manifest_path": "../agents/baseline-manifest.json",
     "repo_root": "/home/claude/kg-automation"
   }
   ```

2. Also create an empty `scripts/openclaw/enforcement/__init__.py` so the enforcement directory is a Python package for import/testing purposes.

3. The `recipient` field should use a placeholder (`<kent-e164-number>`) — Kent will fill in the actual number during deploy.

**Files**:
- `scripts/openclaw/enforcement/drift-check-config.json` (new)
- `scripts/openclaw/enforcement/__init__.py` (new, empty)

## Definition of Done

- [ ] `baseline-manifest.json` contains all 5 agents × 5 files = 25 entries with both repo and office2 hashes
- [ ] `factory-baselines.json` contains at least BOOTSTRAP.md, TOOLS.md, and IDENTITY.md (two variants) factory hashes
- [ ] `drift-check-config.json` contains correct workspace paths for all 5 agents and notification config
- [ ] `generate_manifest.py` can be re-run to refresh the manifest
- [ ] All JSON files are valid and parseable

## Risks

- **Hash accuracy**: Hashes must be computed from the actual reconciled files, not from research.md truncated values. Use `sha256sum` (Linux) and `shasum -a 256` (Mac) — output format differs slightly.
- **Tasker pre-deploy state**: The manifest will show different hashes for tasker files on repo vs office2. This is expected and correct — WP05 deploy will align them and the manifest should be regenerated.

## Reviewer Guidance

- Verify JSON schemas match data-model.md
- Spot-check at least 2 agents' hashes against live office2 state
- Confirm factory baseline hashes match known unmodified templates

## Activity Log

- 2026-04-13T17:54:06Z – claude:opus-4-6:implementer:implementer – shell_pid=80964 – Started implementation via action command
- 2026-04-13T17:58:48Z – claude:opus-4-6:implementer:implementer – shell_pid=80964 – Ready for review: baseline manifest (25 files), factory baselines, enforcement config
- 2026-04-13T18:02:23Z – codex:gpt-4o:reviewer:reviewer – shell_pid=82637 – Started review via action command
- 2026-04-13T18:05:10Z – codex:gpt-4o:reviewer:reviewer – shell_pid=82637 – Moved to planned
- 2026-04-13T18:05:19Z – claude:opus-4-6:implementer:implementer – shell_pid=83505 – Started implementation via action command
- 2026-04-13T18:06:06Z – claude:opus-4-6:implementer:implementer – shell_pid=83505 – Cycle 2: added generate_manifest.py per review feedback
