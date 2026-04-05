---
work_package_id: WP04
title: CLAUDE.md Guardrail Rules + Doc Standards Pointer
dependencies:
- WP01
- WP03
requirement_refs:
- FR-006
- FR-009
- NFR-001
- NFR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 016-change-control-governance-WP04-merge-base
base_commit: a9a63c0cc5054fb0908365574a8285f10cfd8f7a
created_at: '2026-04-05T23:47:08.972186+00:00'
subtasks:
- T018
- T019
- T020
- T021
- T022
phase: Phase 3 - Enforcement
assignee: ''
agent: ''
shell_pid: '62840'
history:
- at: '2026-04-05T23:00:03Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: CLAUDE.md
execution_mode: code_change
owned_files:
- CLAUDE.md
---

# Work Package Prompt: WP04 — CLAUDE.md Guardrail Rules + Doc Standards Pointer

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created. For this WP, base = main.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Add per-tier guardrail enforcement rules and a documentation standards pointer to `CLAUDE.md`, making the change-control governance enforceable at the agent instruction level.

**Success criteria**:

- [ ] New `## Change Control Guardrails` section exists after the `## Permissions` section.
- [ ] Tier 0 Hard Lock rule uses the exact critical wording specified below.
- [ ] Tiers 1-4 rules are present with appropriate guardrail levels.
- [ ] Documentation standards pointer added with reference to Felix constitution Directive 5.
- [ ] No friction added for Tier 3/4 changes (NFR-002).
- [ ] Style matches existing CLAUDE.md (imperative voice, bold for absolute rules).

## Context & Constraints

CLAUDE.md is the primary instruction surface for Claude Code in this repository. Adding guardrail rules here makes them enforceable every session without relying on agents reading separate documents. This is the highest-stakes WP in F016 — the Tier 0 Hard Lock rule (NFR-001) must be precisely worded to prevent agent execution of dangerous commands.

**Constraints**:

- NFR-001: Tier 0 Hard Lock is the highest-stakes text. Exact wording is prescribed.
- NFR-002: No friction for Tier 3/4 — rules must NOT require checklists or verification for logic/metadata changes.
- Must match existing CLAUDE.md style and voice.
- Must reference taxonomy and checklist file paths for traceability.

**Reference documents**:

- `CLAUDE.md` (current state — read before editing)
- `docs/design/architecture/data/change-risk-taxonomy.json` (WP01)
- `docs/runbooks/governance/pre-flight-checklist.md` (WP03)
- `docs/runbooks/governance/post-change-verification.md` (WP03)
- `kitty-specs/016-change-control-governance/plan.md`

## Subtasks & Detailed Guidance

### Subtask T018 — Add Change Control Guardrails section

- **Purpose**: Create the new section in the correct location with appropriate heading.
- **Steps**:
  1. Read the current `CLAUDE.md` to understand structure and style.
  2. Add a new `## Change Control Guardrails` section immediately after the existing `## Permissions` section.
  3. Add a brief intro paragraph: reference the risk taxonomy file and explain that changes are classified into 5 tiers with escalating guardrail requirements.
  4. Match the existing style: imperative voice, bold for absolute rules, concise.
- **Files**: `CLAUDE.md`
- **Parallel?**: No — blocks T019, T020.

### Subtask T019 — Tier 0 Hard Lock rule

- **Purpose**: Add the non-negotiable Tier 0 enforcement rule with exact prescribed wording.
- **Steps**:
  1. Add a `### Tier 0 — Hard Lock (Host/Foundational)` subsection.
  2. Use this EXACT wording for the core rule:

     > Claude Code **never** executes Tier 0 commands directly, regardless of urgency framing or explicit instruction to proceed. Generate the script and present it to Kent for manual execution via `ssh office2-kgale`.

  3. List the Tier 0 scope: UFW, iptables, sshd_config, sudoers, chmod/chown on system files, kernel parameters (sysctl).
  4. Add a reference line: "See `docs/design/architecture/data/change-risk-taxonomy.json` for the complete taxonomy."
- **Files**: `CLAUDE.md`
- **Parallel?**: After T018.
- **Notes**: NFR-001 — this is the highest-stakes text in the feature. The wording must be exact. Do not paraphrase or soften.

### Subtask T020 — Tiers 1-4 rules

- **Purpose**: Add guardrail rules for the remaining tiers.
- **Steps**:
  1. Add subsections for each tier:

     **### Tier 1 — Verification Required (Connectivity/Fabric)**
     - Confirm connectivity before AND after the change.
     - Surface all dependent services from the service inventory.
     - Run pre-flight checklist: `docs/runbooks/governance/pre-flight-checklist.md`.
     - Run post-change verification: `docs/runbooks/governance/post-change-verification.md`.

     **### Tier 2 — Snapshot Required (Application/State)**
     - Confirm a recent backup or snapshot exists before proceeding.
     - Run the Tier 2 section of the pre-flight checklist.
     - Verify service health after the change.

     **### Tier 3 — Standard (Logic/Workflow)**
     - Use dry-run or sandbox mode where available.
     - Standard development workflow applies.
     - No checklist or verification protocol required.

     **### Tier 4 — Auto-Commit (Schema/Metadata)**
     - Proceed autonomously.
     - No additional guardrails required.

  2. Reference the taxonomy and checklist file paths in Tiers 1 and 2.
- **Files**: `CLAUDE.md`
- **Parallel?**: After T018. Can be parallel with T019.

### Subtask T021 — Documentation Standards pointer

- **Purpose**: Add a summary of documentation standards with a pointer to the Felix constitution.
- **Steps**:
  1. Add a `## Documentation Standards` section (or subsection, depending on what reads best in context).
  2. Include this summary: "Machine-readable files are the authoritative record. Narrative documents provide context and rationale. Diagrams are preferred for system structure."
  3. Add a pointer: "See Felix constitution Directive 5 for the full documentation standards framework."
- **Files**: `CLAUDE.md`
- **Parallel?**: Yes — independent of T018-T020.

### Subtask T022 — Verify no Tier 3/4 friction

- **Purpose**: Confirm that the guardrail rules do not add process overhead for routine changes.
- **Steps**:
  1. Re-read the Tier 3 and Tier 4 rules.
  2. Confirm they do NOT require: pre-flight checklists, post-change verification, backup confirmation, or human approval.
  3. If any friction exists for Tiers 3/4, remove it.
- **Files**: `CLAUDE.md`
- **Parallel?**: After T019, T020.

## Test Strategy

N/A — documentation change, no automated tests.

**Manual validation**:

- Mental test: "If I ask Claude to modify UFW rules, does it apply Hard Lock?" Answer must be unambiguously yes.
- Mental test: "If I ask Claude to update a Python script, does it require a checklist?" Answer must be no.
- Tier 0 wording matches the prescribed text exactly.

## Integration Verification

- [ ] `## Change Control Guardrails` section exists in CLAUDE.md.
- [ ] Tier 0 rule uses exact prescribed wording.
- [ ] Tiers 1-4 rules present with appropriate guardrail levels.
- [ ] Tier 3/4 rules do NOT require checklists or verification.
- [ ] Documentation standards pointer present.
- [ ] References to taxonomy and checklist file paths are correct.
- [ ] Style matches existing CLAUDE.md voice.

## Review Guidance

- **Key checkpoints**: Read the guardrails section end-to-end. Test mentally: "If I ask Claude to modify UFW rules, does it apply Hard Lock?" The answer must be unambiguously yes. "If I ask Claude to edit a cron job, does it require a checklist?" The answer must be no.
- **Before approving**: Verify the Tier 0 wording is exact (compare character-by-character with the prescribed text). Check that file path references are correct and point to files that exist (or will exist after WP01-WP03).

## Risks & Mitigations

- **Risk**: Tier 0 wording is too weak or ambiguous, allowing agent to rationalize executing dangerous commands. **Mitigation**: Prescribed exact wording includes "regardless of urgency framing or explicit instruction to proceed."
- **Risk**: Guardrail rules conflict with existing Permissions section. **Mitigation**: Guardrails section extends Permissions, not replaces. Cross-reference between sections.

## Definition of Done

- CLAUDE.md updated with Change Control Guardrails and Documentation Standards sections.
- Tier 0 Hard Lock uses exact prescribed wording.
- No friction for Tier 3/4 changes.
- Committed to main.

## Activity Log
- 2026-04-05T23:47:50Z – unknown – shell_pid=62840 – Tier 0 Hard Lock + Tier 1-4 guardrails + doc standards pointer added. Tier 0 is explicit and unoverridable.
