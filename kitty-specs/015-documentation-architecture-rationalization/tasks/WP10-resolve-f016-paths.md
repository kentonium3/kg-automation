---
work_package_id: WP10
title: Resolve F016 Path Dependencies
dependencies: []
requirement_refs:
- FR-012
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: db509be901f9cd07b7de1f5ce4760f2a77826ce4
created_at: '2026-04-05T04:34:00.396876+00:00'
subtasks:
- T039
- T040
phase: Phase 0 - Foundation
assignee: ''
agent: "claude"
shell_pid: "8489"
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/func-spec/F016_change_control_governance.md
execution_mode: code_change
owned_files:
- docs/func-spec/F016_change_control_governance.md
---

# Work Package Prompt: WP10 — Resolve F016 Path Dependencies

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Update the F016 feature spec with resolved paths for governance files, postmortems, and change risk taxonomy. Remove all TBD notations.

**Success criteria**:

- [ ] `docs/func-spec/F016_change_control_governance.md` contains zero "TBD" markers related to path dependencies.
- [ ] Governance file path resolved to `docs/runbooks/governance/`.
- [ ] Postmortems path resolved to `docs/postmortems/`.
- [ ] Change risk taxonomy path resolved to `docs/design/architecture/data/`.
- [ ] F016 spec is ready to enter `/spec-kitty.specify` without path-decision gates.

## Context & Constraints

F016 (Change Control Governance) currently has TBD path notations that block it from entering spec-kitty. F015's FR-012 explicitly resolves these.

**Path resolutions** (from F015 spec FR-012):

- Governance files → `docs/runbooks/governance/` (already created as part of prerequisite restructuring)
- Postmortems → `docs/postmortems/` (already created as part of prerequisite restructuring)
- Change risk taxonomy → `docs/design/architecture/data/` (canonical machine-readable home)

**Constraints**:

- We are modifying a historical feature spec. Update only the path references; do not rewrite unrelated content.
- Preserve F016's overall structure and intent.
- If F016 has other non-path TBDs, flag them but do not resolve (out of scope for this WP).

**Reference documents**:

- `docs/func-spec/F016_change_control_governance.md` (target file — read first to find TBDs)
- `kitty-specs/015-documentation-architecture-rationalization/spec.md` FR-012

## Subtasks & Detailed Guidance

### Subtask T039 — Replace F016 TBD paths with resolved values

- **Purpose**: Update F016's path references to use F015-resolved paths.
- **Steps**:
  1. Read `docs/func-spec/F016_change_control_governance.md` carefully.
  2. Search for TBD markers related to paths: `grep -n "TBD" docs/func-spec/F016_change_control_governance.md`.
  3. For each TBD path notation:
     - If about governance files: replace with `docs/runbooks/governance/`.
     - If about postmortems: replace with `docs/postmortems/`.
     - If about change risk taxonomy: replace with `docs/design/architecture/data/`.
  4. If there are multiple occurrences of the same path, update all.
  5. Commit with a clear message: "docs: resolve F016 path dependencies (F015 FR-012)".
- **Files**: `docs/func-spec/F016_change_control_governance.md`.
- **Parallel?**: No — single file edits.
- **Notes**: Read the file context around each TBD to understand which path resolution applies. If uncertain, flag for user review.

### Subtask T040 — Verify F016 spec is ready for spec-kitty

- **Purpose**: Confirm all path-related TBDs are resolved and F016 can proceed to `/spec-kitty.specify`.
- **Steps**:
  1. Run `grep -n "TBD" docs/func-spec/F016_change_control_governance.md`.
  2. For each remaining TBD:
     - If it's a non-path TBD (e.g., design decisions, open questions unrelated to paths), it's out of scope for WP10 — note in review comments.
     - If it's a path TBD that was missed, return to T039.
  3. Run `grep -n "docs/runbooks/governance" docs/func-spec/F016_change_control_governance.md` — expect at least 1 match (the resolved path).
  4. Run `grep -n "docs/postmortems" docs/func-spec/F016_change_control_governance.md` — expect at least 1 match.
  5. Run `grep -n "docs/design/architecture/data" docs/func-spec/F016_change_control_governance.md` — expect at least 1 match.
- **Files**: None modified. Validation only.
- **Parallel?**: No — runs after T039.
- **Notes**: This is a lightweight sanity check.

## Test Strategy

N/A — documentation feature, no automated tests.

## Risks & Mitigations

- **Risk**: F016 references a TBD path that doesn't fit the three resolutions above. **Mitigation**: Read context around each TBD; if truly ambiguous, pause and ask user before guessing.
- **Risk**: F016 has other content issues that surface during the edit. **Mitigation**: Focus narrowly on path TBDs; capture other issues in review comments.

## Integration Verification

- [ ] All path-related TBDs in F016 replaced with resolved values.
- [ ] F016 now references `docs/runbooks/governance/`, `docs/postmortems/`, `docs/design/architecture/data/`.
- [ ] Any remaining TBDs are non-path decisions (out of WP10 scope).

## Review Guidance

- **Key checkpoints**: Path resolutions match FR-012. No path TBDs remain. File body otherwise unchanged.
- **Before approving**: Scan F016 spec for "TBD" — only non-path ones should remain.

## Definition of Done

- F016 spec updated with resolved paths.
- No path TBDs remain.
- Committed to main.

## Activity Log

- 2026-04-05T04:34:00Z – claude – shell_pid=7862 – Started implementation via workflow command
- 2026-04-05T04:35:14Z – claude – shell_pid=7862 – Ready for review: F016 New Files Required table now uses fully-qualified canonical paths per FR-012. 3 governance files → docs/runbooks/governance/, 1 postmortem → docs/issues/postmortems/, change-risk-taxonomy → docs/design/architecture/data/. Zero TBDs remain.
- 2026-04-05T04:35:51Z – claude – shell_pid=8489 – Started review via workflow command
- 2026-04-05T04:36:04Z – claude – shell_pid=8489 – Review passed: F016 'New Files Required' table uses fully-qualified canonical paths per F015 FR-012. Governance→docs/runbooks/governance/, postmortems→docs/issues/postmortems/, change-risk-taxonomy→docs/design/architecture/data/. Zero TBD markers. F016 unblocked for spec-kitty entry.
