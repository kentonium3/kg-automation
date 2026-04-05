---
work_package_id: WP06
title: Documentation Standards — Constitution
dependencies: []
requirement_refs:
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 4d10dd57e62b09b2b98f552298fad3816736510f
created_at: '2026-04-05T23:34:47.204502+00:00'
subtasks:
- T029
- T030
- T031
phase: Phase 0 - Foundation
assignee: ''
agent: "claude"
shell_pid: "59092"
history:
- at: '2026-04-05T23:00:03Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/constitution/
execution_mode: code_change
owned_files:
- docs/constitution/FELIX-CONSTITUTION.md
- .kittify/constitution/constitution.md
---

# Work Package Prompt: WP06 — Documentation Standards — Constitution

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main (no dependencies).
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Add a documentation standards principle as Directive 5 to the Felix constitution, establishing the three-layer documentation standard as a governance-level principle.

**Success criteria**:

- [ ] Directive 5: Documentation Standards added to `docs/constitution/FELIX-CONSTITUTION.md` after the Safety Parameters directive.
- [ ] Matching content added to `.kittify/constitution/constitution.md`.
- [ ] `spec-kitty constitution sync` runs without errors.
- [ ] Tone and structure match existing directives (declarative + bulleted sub-rules).

## Context & Constraints

This WP establishes the documentation standards principle at the governance level (constitution), not the operational level (CLAUDE.md). The principle codifies the three-layer documentation standard that F015 rationalized and F016 depends on.

**Key distinction**: The constitution declares the principle. Operational procedures (how to apply it) live in runbooks and CLAUDE.md. Do not include operational detail in the constitution.

**Constraints**:

- Must match the declarative tone of existing directives.
- Sub-rules must be concise and principled, not procedural.
- The `.kittify/constitution/constitution.md` version must match the `FELIX-CONSTITUTION.md` version exactly in wording and structure.

**Reference documents**:

- `docs/constitution/FELIX-CONSTITUTION.md` (existing directives as tone/structure model)
- `.kittify/constitution/constitution.md` (spec-kitty's copy)
- `kitty-specs/016-change-control-governance/plan.md`
- `kitty-specs/016-change-control-governance/spec.md`
- `kitty-specs/016-change-control-governance/data-model.md`

## Subtasks & Detailed Guidance

### Subtask T029 — Add Directive 5 to FELIX-CONSTITUTION.md

- **Purpose**: Establish documentation standards as a governance-level principle in the canonical constitution.
- **Steps**:
  1. Open `docs/constitution/FELIX-CONSTITUTION.md`.
  2. Locate the Safety Parameters directive (the current last directive).
  3. Add `## Directive 5: Documentation Standards` after the Safety Parameters directive.
  4. Write the directive body:

     > All operational documentation follows a three-layer standard: machine-readable files are the authoritative record, narrative documents provide context and rationale, and diagrams are the preferred format for communicating system structure and relationships.

  5. Add sub-rules as a bulleted list:
     - Machine-readable JSON is truth when conflicts arise between JSON and narrative.
     - Config file pointers in inventory are paths only — content is never duplicated.
     - Diagrams must be consistent with machine-readable sources.
     - Proportionality: not every detail needs prose — machine-readable coverage is sufficient for stable, well-understood artifacts.
- **Files**: `docs/constitution/FELIX-CONSTITUTION.md`
- **Parallel?**: No — blocks T030.
- **Notes**: Review existing directives for tone calibration. The directive should be declarative and principled, not procedural.

### Subtask T030 — Add matching content to .kittify/constitution/constitution.md

- **Purpose**: Ensure spec-kitty's constitution copy matches the canonical version.
- **Steps**:
  1. Open `.kittify/constitution/constitution.md`.
  2. Add the identical Directive 5 content (same heading, body text, and sub-rules) in the matching position.
  3. Verify wording and structure are identical to the FELIX-CONSTITUTION.md version.
- **Files**: `.kittify/constitution/constitution.md`
- **Parallel?**: No — depends on T029.
- **Notes**: The two files must be word-for-word identical for the documentation standards section.

### Subtask T031 — Run constitution sync and verify

- **Purpose**: Confirm spec-kitty's constitution sync mechanism handles the new directive without errors.
- **Steps**:
  1. Run `spec-kitty constitution sync`.
  2. Verify the command completes without errors.
  3. Review the diff of any derived artifacts that change as a result of the sync.
  4. If errors occur, stop and report — do not work around manually.
- **Files**: None modified directly. Verification only (derived artifacts may change).
- **Parallel?**: No — runs after T029 and T030.
- **Notes**: If `spec-kitty constitution sync` is not available or fails, report the issue per the workflow system rules.

## Test Strategy

N/A — governance feature, no automated tests. Manual validation per quickstart.md.

**Manual validation**:

- Directive 5 present in both constitution files.
- Wording identical between the two files.
- Constitution sync runs clean.
- Tone matches existing directives.

## Risks & Mitigations

- **Risk**: Directive wording is too operational/procedural. **Mitigation**: Review against existing directives for tone calibration. Keep to principles, not procedures.
- **Risk**: Constitution sync fails on new content. **Mitigation**: Stop and report per workflow rules; do not manually fix.
- **Risk**: Numbering conflicts if other features added directives. **Mitigation**: Check current directive count before adding.

## Integration Verification

- [ ] `docs/constitution/FELIX-CONSTITUTION.md` contains Directive 5: Documentation Standards.
- [ ] `.kittify/constitution/constitution.md` contains identical Directive 5 content.
- [ ] `spec-kitty constitution sync` completes without errors.
- [ ] Directive tone is declarative with bulleted sub-rules (matches existing pattern).
- [ ] No operational/procedural content in the directive.

## Review Guidance

- **Key checkpoints**: The principle is governance-level (constitution), not operational (CLAUDE.md). Tone should match existing directives (declarative + bulleted sub-rules). Both files must be identical.
- **Before approving**: Read Directive 5 alongside Directives 1-4 — it should feel like a natural continuation of the same voice.

## Definition of Done

- Directive 5: Documentation Standards committed to both `docs/constitution/FELIX-CONSTITUTION.md` and `.kittify/constitution/constitution.md`.
- Constitution sync verified clean.

## Activity Log

- 2026-04-05T23:34:47Z – claude – shell_pid=59092 – Started implementation via workflow command
