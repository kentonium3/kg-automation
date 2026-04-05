---
work_package_id: WP03
title: Governance Runbooks — Checklists + Verification
dependencies:
- WP01
- WP02
requirement_refs:
- FR-004
- FR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T012
- T013
- T014
- T015
- T016
- T017
phase: Phase 2 - Governance Docs
assignee: ''
agent: ''
shell_pid: ''
history:
- at: '2026-04-05T23:00:03Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/runbooks/governance/
execution_mode: code_change
owned_files:
- docs/runbooks/governance/pre-flight-checklist.md
- docs/runbooks/governance/post-change-verification.md
---

# Work Package Prompt: WP03 — Governance Runbooks — Checklists + Verification

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created. For this WP, base = main.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Create a pre-flight checklist (covering Tier 0/1 full and Tier 2 lighter protocols) and a post-change verification protocol as operational runbooks.

**Success criteria**:

- [ ] `docs/runbooks/governance/pre-flight-checklist.md` exists with correct frontmatter.
- [ ] Pre-flight checklist covers Tier 0/1 (full protocol) and Tier 2 (lighter protocol).
- [ ] `docs/runbooks/governance/post-change-verification.md` exists with correct frontmatter.
- [ ] Post-change verification defines per-tier verification steps.
- [ ] Rollback trigger defined: any dependent service health check failure within 5 minutes.
- [ ] Both documents reference the enriched service inventory for dependency lookups.

## Context & Constraints

These runbooks operationalize the risk taxonomy from WP01 and the enriched inventory from WP02. They are referenced by the CLAUDE.md guardrails (WP04) and validated by the origin incident walkthrough (WP05).

**Constraints**:

- Checklists must reference the enriched inventory for dependency and health-check data.
- Tier 0/1 checklist must be thorough; Tier 2 must be lightweight.
- Tiers 3/4 do not require checklists (NFR-002: no friction for logic/metadata changes).

**Reference documents**:

- `docs/design/architecture/data/change-risk-taxonomy.json` (tier definitions from WP01)
- `docs/design/architecture/data/service-inventory.json` (enriched by WP02)
- `kitty-specs/016-change-control-governance/plan.md`

## Subtasks & Detailed Guidance

### Subtask T012 — Create pre-flight-checklist.md with frontmatter

- **Purpose**: Establish the pre-flight checklist document.
- **Steps**:
  1. Create `docs/runbooks/governance/pre-flight-checklist.md`.
  2. Add frontmatter:
     ```yaml
     ---
     title: Pre-Flight Checklist for System Changes
     doc_type: runbook
     audience: both
     status: approved
     owners: [kgale]
     version: "1.0"
     last_validated: 2026-04-05
     ---
     ```
  3. Add H1, brief introduction explaining purpose and when to use (Tier 0, 1, and 2 changes).
- **Files**: `docs/runbooks/governance/pre-flight-checklist.md` (new)
- **Parallel?**: No — blocks T013, T014.

### Subtask T013 — Tier 0/1 full checklist

- **Purpose**: Define the comprehensive pre-flight checklist for high-risk changes.
- **Steps**:
  1. Add a section for Tier 0 and Tier 1 changes with these checklist items:
     1. **Identify affected ports/interfaces** — list all network ports, interfaces, and firewall rules that will be modified.
     2. **Query service inventory for dependent services** — look up `docs/design/architecture/data/service-inventory.json` for services whose `dependencies` array references the affected ports/interfaces.
     3. **Note health-check endpoints** — for each dependent service, record the `health_check` endpoint and expected result.
     4. **Document rollback procedure** — write down the exact commands to revert the change.
     5. **Confirm operator availability** — ensure a human operator is available for the duration of the change and the 5-minute verification window.
     6. **Define post-change verification plan** — list the health checks to run after the change, referencing the post-change verification runbook.
  2. For Tier 0 specifically, add a reminder: "Tier 0 changes are Hard Lock. Claude Code generates the script; human executes via `ssh office2-kgale`."
- **Files**: `docs/runbooks/governance/pre-flight-checklist.md`
- **Parallel?**: After T012.

### Subtask T014 — Tier 2 lighter checklist

- **Purpose**: Define a lightweight pre-flight checklist for application-state changes.
- **Steps**:
  1. Add a section for Tier 2 changes with these checklist items:
     1. **Confirm recent Restic backup** — verify a backup exists from within the last 24 hours.
     2. **Note health-check endpoint** — record the affected service's health-check endpoint and expected result.
     3. **Have rollback plan** — document how to revert (restore from backup, revert config file, etc.).
  2. Note that Tiers 3 and 4 do not require a pre-flight checklist.
- **Files**: `docs/runbooks/governance/pre-flight-checklist.md`
- **Parallel?**: After T012. Can be parallel with T013.

### Subtask T015 — Create post-change-verification.md with frontmatter

- **Purpose**: Establish the post-change verification document.
- **Steps**:
  1. Create `docs/runbooks/governance/post-change-verification.md`.
  2. Add frontmatter:
     ```yaml
     ---
     title: Post-Change Verification Protocol
     doc_type: runbook
     audience: both
     status: approved
     owners: [kgale]
     version: "1.0"
     last_validated: 2026-04-05
     ---
     ```
  3. Add H1, brief introduction explaining this protocol runs immediately after any Tier 0, 1, or 2 change.
- **Files**: `docs/runbooks/governance/post-change-verification.md` (new)
- **Parallel?**: Yes — independent of T012-T014.

### Subtask T016 — Per-tier verification steps

- **Purpose**: Define what verification looks like for each tier level.
- **Steps**:
  1. **Tier 0/1 verification**: Check ALL dependent services' health endpoints. Query the service inventory for services that depend on the changed infrastructure. For each, execute the health check defined in `health_check.endpoint` and compare to `health_check.expected`.
  2. **Tier 2 verification**: Check the affected service's own health endpoint. Verify the service is operational and responding as expected.
  3. Include example commands for HTTP health checks (`curl`), systemd status checks (`systemctl`), and TCP checks (`nc`).
- **Files**: `docs/runbooks/governance/post-change-verification.md`
- **Parallel?**: After T015.

### Subtask T017 — Rollback trigger definition

- **Purpose**: Define the clear, unambiguous trigger for executing a rollback.
- **Steps**:
  1. Add a "Rollback Trigger" section stating: if ANY dependent service health check fails within 5 minutes of the change, execute the rollback procedure documented in the pre-flight checklist.
  2. Define the 5-minute window: verification checks should run immediately after the change and be repeated at 1-minute intervals for 5 minutes.
  3. Note: rollback is mandatory, not discretionary. If a health check fails, rollback first, investigate second.
- **Files**: `docs/runbooks/governance/post-change-verification.md`
- **Parallel?**: After T015. Can be parallel with T016.

## Test Strategy

N/A — documentation feature, no automated tests.

**Manual validation**:

- Both files parse as valid markdown with correct frontmatter.
- Tier 0/1 checklist has all 6 items.
- Tier 2 checklist has all 3 items.
- Rollback trigger is unambiguous.
- Both documents reference the service inventory.

## Integration Verification

- [ ] `docs/runbooks/governance/pre-flight-checklist.md` exists with `doc_type: runbook`, `audience: both`.
- [ ] `docs/runbooks/governance/post-change-verification.md` exists with `doc_type: runbook`, `audience: both`.
- [ ] Pre-flight checklist references `docs/design/architecture/data/service-inventory.json`.
- [ ] Tier 0/1 checklist has 6 items.
- [ ] Tier 2 checklist has 3 items.
- [ ] Rollback trigger defined with 5-minute window.

## Review Guidance

- **Key checkpoints**: Checklists reference the enriched inventory for dependency and health-check lookups. Tier 0/1 is thorough (6 steps). Tier 2 is lightweight (3 steps). Tiers 3/4 are explicitly excluded.
- **Before approving**: Mentally walk through a scenario: "Agent about to restart Docker" — does the Tier 2 checklist catch it? "Agent about to modify UFW rules" — does the Tier 0/1 checklist surface all dependencies?

## Definition of Done

- Both runbooks committed to main.
- Checklists reference enriched inventory.
- Rollback trigger clearly defined.
- No checklist friction for Tiers 3/4.

## Activity Log
