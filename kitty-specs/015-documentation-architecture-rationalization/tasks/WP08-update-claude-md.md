---
work_package_id: WP08
title: Update CLAUDE.md + AI Agent Instructions
dependencies: [WP07]
requirement_refs:
- FR-009
- NFR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: 'Current branch at workflow start: main. Planning/base branch for this feature: main. Completed changes must merge into main.'
subtasks:
- T032
- T033
- T034
- T035
phase: Phase 3 - Entry Point Updates
assignee: ''
agent: ''
shell_pid: ''
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: CLAUDE.md
execution_mode: code_change
owned_files:
- CLAUDE.md
- ai-agents/claude-code-instructions.md
- ai-agents/claude-instructions.md
---

# Work Package Prompt: WP08 — Update CLAUDE.md + AI Agent Instructions

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or stacked on WP07.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Add references from `CLAUDE.md` to `docs/INDEX.md`, Felix constitution, and the machine-readable artifact home. Update all `personal-ai-system-spec-v03.md` references to point to `v1.0.md`.

**Success criteria**:

- [ ] `CLAUDE.md` references `docs/INDEX.md` as the documentation map.
- [ ] `CLAUDE.md` references `docs/constitution/FELIX-CONSTITUTION.md`.
- [ ] `CLAUDE.md` mentions `docs/design/architecture/data/` as the canonical machine-readable home.
- [ ] All `personal-ai-system-spec-v03.md` references in CLAUDE.md updated to `v1.0.md` (2 occurrences).
- [ ] `ai-agents/claude-code-instructions.md` and `ai-agents/claude-instructions.md` updated: v03 → v1.0 references.

## Context & Constraints

CLAUDE.md is the AI agent's primary entry point. Keep additions concise and well-placed — this file is already large.

**Existing CLAUDE.md structure** (to preserve):

- What This System Is
- Platform
- Server Access
- Architecture Documentation (existing section)
- Repository Structure
- Feature Development Workflow
- Git Workflow
- Permissions
- Architecture Documentation (duplicate section)
- Second Brain Boundary

**Additions needed**:

- Reference to `docs/INDEX.md` in Architecture Documentation section.
- Reference to Felix Constitution.
- Mention machine-readable artifact home.

**Constraints**:

- Do not reorganize CLAUDE.md structure — add references in existing sections.
- Keep additions concise (1-3 sentences each).

## Subtasks & Detailed Guidance

### Subtask T032 — Add INDEX.md reference to CLAUDE.md

- **Purpose**: Make INDEX.md the explicit entry point for documentation navigation from agent context.
- **Steps**:
  1. Open CLAUDE.md at repo root.
  2. Find the "Architecture Documentation" section (~line 35).
  3. At the top of that section (before or after the existing path references), add:

     ```markdown
     **Documentation map**: [`docs/INDEX.md`](docs/INDEX.md) — master index of all active documentation,
     grouped by directory with Divio type annotations. Start here to discover docs by topic or type.
     ```

  4. Ensure the reference is near the top of the doc-discovery content so agents see it early.
- **Files**: `CLAUDE.md`.
- **Parallel?**: No — blocks T033.
- **Notes**: Place the reference where it's most visible to a new agent reading CLAUDE.md.

### Subtask T033 — Add constitution + machine-readable home references

- **Purpose**: Agents need explicit pointers to governance (constitution) and operational truth (data/).
- **Steps**:
  1. In CLAUDE.md's "Architecture Documentation" section, add:

     ```markdown
     **Governance**: [`docs/constitution/FELIX-CONSTITUTION.md`](docs/constitution/FELIX-CONSTITUTION.md)
     — top-level governance, autonomy levels, principles.
     See also [`docs/constitution/AGENT-REGISTRY.md`](docs/constitution/AGENT-REGISTRY.md).

     **Machine-readable operational state**: `docs/design/architecture/data/` is the canonical home for
     JSON artifacts (service inventory, topology, credentials, data-flows, schemas). Exempt from moves.
     ```

  2. Place these near the INDEX.md reference or in a logical adjacent location.
- **Files**: `CLAUDE.md`.
- **Parallel?**: No — after T032.
- **Notes**: Keep language terse; CLAUDE.md is a context-efficient document.

### Subtask T034 — Update CLAUDE.md v03 → v1.0 spec references

- **Purpose**: `personal-ai-system-spec-v03.md` is deprecated (per WP06); CLAUDE.md should point to v1.0.
- **Steps**:
  1. In CLAUDE.md, find line ~20: "Read `docs/design/personal-ai-system-spec-v03.md` before making any architectural decisions."
     - Replace with: "Read `docs/design/personal-ai-system-spec-v1.0.md` before making any architectural decisions."
  2. Find line ~62: "`docs/design/personal-ai-system-spec-v03.md` — design intent (what we're building toward):"
     - Replace with: "`docs/design/personal-ai-system-spec-v1.0.md` — design intent (what we're building toward):"
  3. Run `grep -n personal-ai-system-spec-v03 CLAUDE.md` to confirm zero occurrences.
- **Files**: `CLAUDE.md`.
- **Parallel?**: Yes — independent of T032/T033.
- **Notes**: Both updates change `v03` to `v1.0` — simple find/replace (but verify context each time).

### Subtask T035 — Update ai-agents/ v03 → v1.0 references

- **Purpose**: The two AI agent instruction files also reference the deprecated v03 spec.
- **Steps**:
  1. Update `ai-agents/claude-code-instructions.md`:
     - Find line ~21 referencing `personal-ai-system-spec-v03.md`.
     - Replace with reference to `personal-ai-system-spec-v1.0.md`.
  2. Update `ai-agents/claude-instructions.md`:
     - Find line ~21 and line ~62 referencing `personal-ai-system-spec-v03.md`.
     - Replace both with references to `personal-ai-system-spec-v1.0.md`.
  3. Run `grep -rn personal-ai-system-spec-v03 ai-agents/` to confirm zero occurrences.
- **Files**: `ai-agents/claude-code-instructions.md`, `ai-agents/claude-instructions.md`.
- **Parallel?**: Yes — independent of CLAUDE.md updates.
- **Notes**: Same find/replace pattern as T034.

## Test Strategy

N/A — documentation feature, no automated tests.

**Manual validation**:

- CLAUDE.md references resolve to real files (INDEX.md, FELIX-CONSTITUTION.md).
- No v03 references remain in CLAUDE.md or ai-agents/.
- CLAUDE.md structure is preserved (no section reorganization).

## Risks & Mitigations

- **Risk**: CLAUDE.md gets bloated. **Mitigation**: Terse additions (1-3 sentences each); no duplicate content.
- **Risk**: v1.0 file doesn't exist at expected path. **Mitigation**: WP06 confirms v1.0 exists and is the canonical reference.
- **Risk**: Accidentally breaking existing CLAUDE.md structure. **Mitigation**: Read file first; additions only; no restructuring.

## Integration Verification

- [ ] CLAUDE.md references `docs/INDEX.md` with correct relative path.
- [ ] CLAUDE.md references `docs/constitution/FELIX-CONSTITUTION.md`.
- [ ] CLAUDE.md mentions `docs/design/architecture/data/`.
- [ ] `grep -rn "personal-ai-system-spec-v03" CLAUDE.md ai-agents/` returns zero matches.
- [ ] All referenced files exist.

## Review Guidance

- **Key checkpoints**: Additions are concise. Links resolve. v03 → v1.0 updates complete.
- **Before approving**: Read the modified sections of CLAUDE.md — do they flow well? Are references discoverable?

## Definition of Done

- CLAUDE.md references INDEX.md, constitution, and machine-readable home.
- All v03 → v1.0 updates complete in CLAUDE.md + ai-agents/.
- All changes committed to main.
