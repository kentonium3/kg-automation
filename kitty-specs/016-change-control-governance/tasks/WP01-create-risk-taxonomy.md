---
work_package_id: WP01
title: Create Risk Taxonomy
dependencies: []
requirement_refs:
- FR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: ff96a994c610e45471eadaff11e69796243a85e2
created_at: '2026-04-05T23:34:42.622245+00:00'
subtasks:
- T001
- T002
- T003
- T004
phase: Phase 0 - Foundation
assignee: ''
agent: "claude"
shell_pid: "59029"
history:
- at: '2026-04-05T23:00:03Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/architecture/data/change-risk-taxonomy.json
execution_mode: code_change
owned_files:
- docs/design/architecture/data/change-risk-taxonomy.json
---

# Work Package Prompt: WP01 — Create Risk Taxonomy

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created. For this WP, base = main.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Create `docs/design/architecture/data/change-risk-taxonomy.json` containing a five-tier risk taxonomy (Tier 0 Hard Lock through Tier 4 Auto-Commit) that classifies all system changes by scope and required guardrail protocol.

**Success criteria**:

- [ ] `docs/design/architecture/data/change-risk-taxonomy.json` exists and is valid JSON.
- [ ] File contains exactly 5 tier objects (Tier 0 through Tier 4).
- [ ] Each tier has: `tier`, `name`, `scope`, `guardrail_protocol`, `guardrail_description`, `examples`, `overridable`.
- [ ] Tier 0 has `"overridable": false`; all others have `"overridable": true`.
- [ ] Top-level fields include `schema_version`, `last_updated`, `updated_by`.

## Context & Constraints

This is the foundational data artifact for F016. All subsequent WPs reference this taxonomy to assign risk tiers to services and to define guardrail enforcement rules. The taxonomy must be machine-readable JSON — the authoritative record per kg-automation conventions.

**Reference documents**:

- `kitty-specs/016-change-control-governance/plan.md` (tier definitions)
- `kitty-specs/016-change-control-governance/research.md` (origin incident analysis)

## Subtasks & Detailed Guidance

### Subtask T001 — Create file skeleton

- **Purpose**: Establish the JSON file with top-level metadata fields and an empty tiers array.
- **Steps**:
  1. Create `docs/design/architecture/data/change-risk-taxonomy.json`.
  2. Add top-level fields:
     - `"schema_version": "1.0"`
     - `"last_updated": "2026-04-05"`
     - `"updated_by": "F016"`
     - `"tiers": []`
- **Files**: `docs/design/architecture/data/change-risk-taxonomy.json` (new)
- **Parallel?**: No — blocks T002.

### Subtask T002 — Define all 5 tiers

- **Purpose**: Populate the tiers array with the complete five-tier taxonomy.
- **Steps**:
  1. Add 5 tier objects to the `tiers` array. Each object must have these fields:
     - `tier` (integer 0-4)
     - `name` (string)
     - `scope` (string)
     - `guardrail_protocol` (string — one of: `hard_lock`, `verification_required`, `snapshot_required`, `standard`, `auto_commit`)
     - `guardrail_description` (string)
     - `examples` (array of strings)
     - `overridable` (boolean)
  2. Tier definitions:

     **Tier 0 — Host/Foundational**
     - scope: "Host-level and foundational security configuration"
     - guardrail_protocol: `hard_lock`
     - guardrail_description: "Claude Code never executes directly. Generate script and present to human for manual execution."
     - examples: `["SSH configuration (sshd_config)", "Firewall rules (UFW, iptables)", "sudoers configuration", "Kernel parameters (sysctl)", "File permissions on system files (chmod/chown)"]`
     - overridable: `false`

     **Tier 1 — Connectivity/Fabric**
     - scope: "Network connectivity and service fabric"
     - guardrail_protocol: `verification_required`
     - guardrail_description: "Confirm connectivity before AND after change. Surface all dependent services from inventory."
     - examples: `["Tailscale configuration", "Docker network settings", "Reverse proxy configuration", "DNS resolution"]`
     - overridable: `true`

     **Tier 2 — Application/State**
     - scope: "Application data, state, and service configuration"
     - guardrail_protocol: `snapshot_required`
     - guardrail_description: "Confirm recent backup or snapshot exists before proceeding."
     - examples: `["Database schema migrations", "Environment files (.env)", "Docker Compose service definitions", "Vikunja configuration"]`
     - overridable: `true`

     **Tier 3 — Logic/Workflow**
     - scope: "Application logic, automation scripts, and workflow definitions"
     - guardrail_protocol: `standard`
     - guardrail_description: "Use dry-run or sandbox mode where available. Standard development workflow."
     - examples: `["Python scripts", "Agent prompt files", "Cron job definitions", "OpenClaw skill definitions"]`
     - overridable: `true`

     **Tier 4 — Schema/Metadata**
     - scope: "Documentation, metadata, and non-functional configuration"
     - guardrail_protocol: `auto_commit`
     - guardrail_description: "Proceed autonomously. No additional guardrails required."
     - examples: `["CLAUDE.md updates", "README files", "Code comments", "Logging configuration"]`
     - overridable: `true`

- **Files**: `docs/design/architecture/data/change-risk-taxonomy.json`
- **Parallel?**: No — depends on T001.

### Subtask T003 — Verify overridable flags

- **Purpose**: Ensure Tier 0 is non-overridable and all other tiers are overridable.
- **Steps**:
  1. Confirm Tier 0 has `"overridable": false`.
  2. Confirm Tiers 1-4 each have `"overridable": true`.
- **Files**: `docs/design/architecture/data/change-risk-taxonomy.json`
- **Parallel?**: Yes — after T002.

### Subtask T004 — Validate JSON parsability

- **Purpose**: Ensure the file is valid, parsable JSON.
- **Steps**:
  1. Run `python -m json.tool docs/design/architecture/data/change-risk-taxonomy.json` or equivalent to confirm valid JSON.
  2. Fix any syntax errors.
- **Files**: `docs/design/architecture/data/change-risk-taxonomy.json`
- **Parallel?**: Yes — after T002.

## Test Strategy

N/A — data artifact, no automated tests.

**Manual validation**:

- File parses as valid JSON.
- Exactly 5 tiers present.
- All required fields present on each tier.
- Tier 0 overridable = false, all others true.

## Integration Verification

- [ ] File exists at `docs/design/architecture/data/change-risk-taxonomy.json`.
- [ ] 5 tiers present in the `tiers` array.
- [ ] Valid JSON (parsable by `json.tool`).
- [ ] Tier 0 `overridable` is `false`.
- [ ] All tier objects have: `tier`, `name`, `scope`, `guardrail_protocol`, `guardrail_description`, `examples`, `overridable`.

## Review Guidance

- **Key checkpoints**: Verify tier scope boundaries make sense and don't overlap ambiguously. Confirm `guardrail_protocol` names match the spec (`hard_lock`, `verification_required`, `snapshot_required`, `standard`, `auto_commit`).
- **Before approving**: Check that the examples for each tier are correctly classified — e.g., UFW belongs in Tier 0, not Tier 1.

## Definition of Done

- File committed to main at `docs/design/architecture/data/change-risk-taxonomy.json`.
- Valid JSON with 5 tiers.
- Tier 0 non-overridable.

## Activity Log
- 2026-04-05T23:34:43Z – claude – shell_pid=59029 – Started implementation via workflow command
