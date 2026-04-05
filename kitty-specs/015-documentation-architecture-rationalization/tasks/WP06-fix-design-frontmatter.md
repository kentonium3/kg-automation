---
work_package_id: WP06
title: Fix docs/design/ Top-Level + Standards Frontmatter
dependencies:
- WP01
requirement_refs:
- FR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T020
- T021
- T022
- T023
- T024
phase: Phase 1 - Frontmatter Corrections
assignee: ''
agent: ''
shell_pid: ''
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/
execution_mode: code_change
owned_files:
- docs/design/Vikunja.md
- docs/design/adversarial-analysis.md
- docs/design/decision-log.md
- docs/design/felix-capability-roadmap.md
- docs/design/personal-ai-system-spec-v03.md
- docs/design/personal-ai-system-spec-v1.0.md
- docs/design/project-charter.md
- docs/design/risk-register.md
- docs/design/strategic-acceleration-charter.md
- docs/design/vision-framework.md
- docs/design/standards/doc-standards.md
- docs/design/standards/obsidian-linter-alignment.md
- docs/design/standards/standards-readme.md
---

# Work Package Prompt: WP06 — Fix docs/design/ Top-Level + Standards Frontmatter

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or stacked on WP01.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Correct `doc_type` misclassifications in 13 docs under `docs/design/` top-level and `docs/design/standards/`, deprecate the superseded system spec, and add supersession pointers.

**Success criteria**:

- [ ] Zero files in `docs/design/` (top-level) retain legacy values (`strategy`, `charter`, `note`, `policy`).
- [ ] `personal-ai-system-spec-v03.md` has `status: deprecated` and `superseded_by: docs/design/personal-ai-system-spec-v1.0.md`.
- [ ] `personal-ai-system-spec-v1.0.md` has `supersedes: docs/design/personal-ai-system-spec-v03.md` (verify; might already).
- [ ] Standards files use `doc_type: standard` (not `policy` or `reference`).

## Context & Constraints

Changes per research.md §2 misclassification table. Some files are already correct and need no changes: `project-charter.md`, `decision-log.md`, `risk-register.md`, `vision-framework.md`, `standards-readme.md`.

**Constraints**:

- Body content unchanged; only frontmatter.
- `strategic-acceleration-charter.md` is an edge case — `charter` isn't in the canonical enum, so reclassify as `explanation` (sub-type of strategic rationale).

**Reference documents**:

- `kitty-specs/015-documentation-architecture-rationalization/research.md` §2
- `docs/design/standards/divio-classification.md` (created in WP01)

## Subtasks & Detailed Guidance

### Subtask T020 — Fix top-level explanation docs [P]

- **Purpose**: Convert docs that describe design rationale to `doc_type: explanation`.
- **Files** (3):
  - `Vikunja.md`: `doc_type: note` → `doc_type: explanation`
  - `adversarial-analysis.md`: `doc_type: strategy` → `doc_type: explanation`
  - `strategic-acceleration-charter.md`: `doc_type: charter` → `doc_type: explanation`
- **Steps**: Change frontmatter `doc_type` value for each file. Keep all other frontmatter fields.
- **Parallel?**: Yes — 3 independent files.
- **Notes**: `strategic-acceleration-charter.md` — "charter" is a strategic direction document, but `charter` is not in the canonical enum. Reclassify as `explanation`. Optionally add `divio_ambiguity: "strategic charter; explanation sub-type"`.

### Subtask T021 — Fix top-level reference docs [P]

- **Purpose**: Convert docs that describe CURRENT STATE to `doc_type: reference`.
- **Files** (2):
  - `felix-capability-roadmap.md`: `doc_type: strategy` → `doc_type: reference`
  - `personal-ai-system-spec-v1.0.md`: `doc_type: strategy` → `doc_type: reference`
- **Steps**:
  1. Update each file's `doc_type` to `reference`.
  2. For `personal-ai-system-spec-v1.0.md`, verify existing `supersedes: docs/design/personal-ai-system-spec-v03.md` (from research.md). If missing, add it.
- **Parallel?**: Yes — 2 independent files.
- **Notes**: Living capability status docs are `reference` (describes what IS, not rationale).

### Subtask T022 — Deprecate personal-ai-system-spec-v03.md

- **Purpose**: Mark the superseded v0.3 spec as deprecated.
- **Steps**:
  1. Update `docs/design/personal-ai-system-spec-v03.md` frontmatter:

     ```yaml
     ---
     title: "Personal AI Command & Accountability System — v0.3"
     doc_type: reference
     status: deprecated
     superseded_by: docs/design/personal-ai-system-spec-v1.0.md
     ---
     ```

  2. Preserve other existing frontmatter fields.
  3. Do NOT delete or move the file — deprecated-not-removed (to preserve CLAUDE.md historical refs).
- **Files**: `docs/design/personal-ai-system-spec-v03.md`.
- **Parallel?**: No — requires v1.0 path to be stable.
- **Notes**: `superseded_by` is the pointer to the replacement. CLAUDE.md updates in WP08 will use v1.0 going forward.

### Subtask T023 — Fix standards frontmatter [P]

- **Purpose**: Use `standard` as the canonical doc_type for cross-cutting standards.
- **Files** (2):
  - `docs/design/standards/doc-standards.md`: `doc_type: policy` → `doc_type: standard`
  - `docs/design/standards/obsidian-linter-alignment.md`: `doc_type: reference` → `doc_type: standard`
- **Steps**: Update frontmatter `doc_type` for each. Preserve other fields.
- **Parallel?**: Yes — 2 independent files.
- **Notes**: `standards-readme.md` can keep `doc_type: readme` OR be changed to `doc_type: reference`. Per data-model.md, `readme` is a legacy value mapping to `reference`. Prefer `reference` for consistency but not mandatory here; leave as-is if it blocks progress.

### Subtask T024 — Validate no legacy values remain

- **Purpose**: Confirm zero legacy values in docs/design/ top-level.
- **Steps**:
  1. Run: `grep -rE "doc_type: (strategy|charter|note|policy)\b" docs/design/` — expect zero matches.
  2. Run: `grep -n "status: deprecated" docs/design/personal-ai-system-spec-v03.md` — expect 1 match.
  3. Run: `grep -n "superseded_by" docs/design/personal-ai-system-spec-v03.md` — expect 1 match.
  4. Report any anomalies.
- **Files**: None modified. Validation only.
- **Parallel?**: No — runs last.
- **Notes**: Use `\b` word boundary to avoid matching in narrative prose within file bodies.

## Test Strategy

N/A — documentation feature, no automated tests.

## Risks & Mitigations

- **Risk**: Breaking existing frontmatter by replacing wrong line. **Mitigation**: Careful sed/edit with surrounding context.
- **Risk**: Removing `supersedes`/`superseded_by` fields if template inconsistencies exist. **Mitigation**: Read file first, then edit.
- **Risk**: `strategic-acceleration-charter.md` reclassification is debatable. **Mitigation**: Decision documented in `divio_ambiguity` field.

## Integration Verification

- [ ] 8 files in `docs/design/` top-level have correct doc_type.
- [ ] 3 files in `docs/design/standards/` have correct doc_type.
- [ ] `personal-ai-system-spec-v03.md` has `status: deprecated` + `superseded_by`.
- [ ] grep validations pass.

## Review Guidance

- **Key checkpoints**: No legacy values remain. Supersession fields present and correct.
- **Before approving**: Spot-check 3 files to verify frontmatter is well-formed.

## Definition of Done

- 13 files have corrected frontmatter committed to main.
- Deprecation pointer in place.
- Validation grep passes.
