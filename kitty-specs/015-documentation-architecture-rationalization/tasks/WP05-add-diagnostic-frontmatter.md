---
work_package_id: WP05
title: Add Frontmatter to Diagnostic Files
dependencies: []
requirement_refs:
- FR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 85ded6c60f98c6df84bde1d39182fde4307a2499
created_at: '2026-04-05T04:13:55.985377+00:00'
subtasks:
- T017
- T018
- T019
phase: Phase 0 - Foundation
assignee: ''
agent: "claude"
shell_pid: "2232"
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/issues/diagnostics/
execution_mode: code_change
owned_files:
- docs/issues/diagnostics/f012-merge-breadcrumbs.md
- docs/issues/diagnostics/spec-kitty-feedback/f014-accept-not-in-resolver.md
- docs/issues/diagnostics/spec-kitty-feedback/f014-merge-json-flag-error.md
- docs/issues/diagnostics/spec-kitty-feedback/f014-multi-parent-dirty-worktree.md
- docs/issues/diagnostics/spec-kitty-feedback/implement-crash-recovery-gap.md
- docs/issues/diagnostics/spec-kitty-feedback/merge-crash-incomplete-cleanup.md
---

# Work Package Prompt: WP05 — Add Frontmatter to Diagnostic Files

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Add missing frontmatter to 6 diagnostic files in `docs/issues/diagnostics/` so they conform to the Divio schema.

**Success criteria**:

- [ ] All 6 files have `doc_type: diagnostic` frontmatter.
- [ ] All 6 files have `title` and `status` fields.
- [ ] `docs/issues/diagnostics/spec-kitty-workflow-journal.md` is UNCHANGED (already has frontmatter).

## Context & Constraints

These are historical incident reports and breadcrumbs. Per C-002, `docs/diagnostics/` is exempt from restructuring but individual files' frontmatter can still be updated.

**Status values**:

- `status: resolved` for incidents that have been fixed or escalated (most files).
- `status: active` for ongoing/unresolved issues.

**Reference documents**:

- `kitty-specs/015-documentation-architecture-rationalization/data-model.md` §3 (required fields)
- `docs/design/standards/divio-classification.md` (created in WP01)

## Subtasks & Detailed Guidance

### Subtask T017 — Add frontmatter to f012-merge-breadcrumbs.md

- **Purpose**: F012 merge issue tracking notes.
- **Steps**:
  1. Read `docs/issues/diagnostics/f012-merge-breadcrumbs.md`.
  2. Determine title from H1 (likely "F012 Merge Breadcrumbs" or similar).
  3. Prepend frontmatter:

     ```yaml
     ---
     title: F012 Merge Breadcrumbs
     doc_type: diagnostic
     status: resolved
     ---
     ```

  4. If the file's content indicates the issue is still open, use `status: active` instead.
- **Files**: `docs/issues/diagnostics/f012-merge-breadcrumbs.md`.
- **Parallel?**: Yes — independent of T018.
- **Notes**: F012 was completed per git history; likely `resolved`.

### Subtask T018 — Add frontmatter to 5 spec-kitty-feedback files [P]

- **Purpose**: Individual spec-kitty bug reports intended for upstream reporting.
- **Files** (5):
  - `f014-accept-not-in-resolver.md`
  - `f014-merge-json-flag-error.md`
  - `f014-multi-parent-dirty-worktree.md`
  - `implement-crash-recovery-gap.md`
  - `merge-crash-incomplete-cleanup.md`
- **Steps**:
  1. For each file, read the H1 to determine the title.
  2. Prepend frontmatter:

     ```yaml
     ---
     title: <from H1>
     doc_type: diagnostic
     status: <active | resolved>
     ---
     ```

  3. Set `status: active` for unfiled/open issues; `status: resolved` if the file notes the issue has been addressed upstream.
- **Files**: 5 files listed above.
- **Parallel?**: Yes — 5 independent files.
- **Notes**: If uncertain about status, default to `active`.

### Subtask T019 — Validate all diagnostic files have frontmatter

- **Purpose**: Confirm every file in `docs/issues/diagnostics/**` has valid frontmatter.
- **Steps**:
  1. Run: `grep -rL "doc_type:" docs/issues/diagnostics/` — expect zero output.
  2. Run: `grep -rL "status:" docs/issues/diagnostics/` — expect zero output.
  3. Run: `grep -r "doc_type: diagnostic" docs/issues/diagnostics/ | wc -l` — expect 7 (6 new + existing workflow-journal).
  4. Report any anomalies.
- **Files**: None modified. Validation only.
- **Parallel?**: No — runs last.
- **Notes**: Simple sanity check.

## Test Strategy

N/A — documentation feature, no automated tests.

## Risks & Mitigations

- **Risk**: Wrong status (resolved vs active) for an issue. **Mitigation**: Default to `active` if uncertain; can be updated later.
- **Risk**: Title doesn't match file content. **Mitigation**: Derive from H1.

## Integration Verification

- [ ] All 6 target files have frontmatter with doc_type, status, title.
- [ ] `spec-kitty-workflow-journal.md` is unchanged (NOT re-written).
- [ ] `grep -rL "doc_type:" docs/issues/diagnostics/` returns zero.

## Review Guidance

- **Key checkpoints**: Each file has at least 3 frontmatter fields. Titles match H1s.
- **Before approving**: Verify the workflow-journal file was not modified.

## Definition of Done

- 6 files have frontmatter committed to main.
- Validation grep passes.

## Activity Log

- 2026-04-05T04:13:56Z – claude – shell_pid=2232 – Started implementation via workflow command
- 2026-04-05T04:14:26Z – claude – shell_pid=2232 – Ready for review: Added diagnostic frontmatter to 6 files in docs/issues/diagnostics/. f012 breadcrumbs marked resolved; 5 spec-kitty-feedback files marked active (upstream bugs still pending). All diagnostic files (7 incl. existing workflow-journal) have doc_type: diagnostic.
