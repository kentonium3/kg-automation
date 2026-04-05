---
work_package_id: WP02
title: Move Misclassified Runbook Content
dependencies: []
requirement_refs:
- C-003
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: 'Current branch at workflow start: main. Planning/base branch for this feature: main. Completed changes must merge into main.'
subtasks:
- T005
- T006
- T007
phase: Phase 0 - Foundation
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
- docs/runbooks/visual-docs-style.md
- docs/runbooks/office2-backup-and-security.md
- docs/design/standards/visual-docs-style.md
- docs/design/office2-backup-and-security.md
---

# Work Package Prompt: WP02 — Move Misclassified Runbook Content

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main for this WP.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Move two files out of `docs/runbooks/` that are not prescriptive how-to content:

1. `visual-docs-style.md` → belongs in `docs/design/standards/` (cross-cutting style standard).
2. `office2-backup-and-security.md` → belongs in `docs/design/` (strategic rationale + security policy narrative).

**Success criteria**:

- [ ] Both files exist at new paths with corrected frontmatter.
- [ ] Both files no longer exist at old paths.
- [ ] Git history preserved (verified via `git log --follow <new-path>`).
- [ ] Both files have `doc_type` corrected: `visual-docs-style.md` → `standard`, `office2-backup-and-security.md` → `explanation`.

## Context & Constraints

This WP does the moves only. Inbound link updates happen in subsequent WPs:

- `docs/runbooks/deployment.md` has 3 links to office2-backup-and-security — WP03 updates these.
- `docs/design/research/005-*/local-audit.md` has 2 links to office2-backup-and-security — WP04 updates these.
- `docs/func-spec/F002_openclaw_install.md` has 2 links to office2-backup-and-security — WP11 updates these.
- `docs/docs-readme.md` has 1 link each to both files — that file is being archived (WP11), so its stale link is frozen history.

**Constraints**:

- C-003: Use `git mv`, never delete-then-recreate. History preservation is mandatory.
- Keep file bodies unchanged; only update frontmatter `doc_type` field.

**Reference documents**:

- `kitty-specs/015-documentation-architecture-rationalization/research.md` §2 (misclassification table)
- `kitty-specs/015-documentation-architecture-rationalization/data-model.md` §1 (doc_type definitions)

## Subtasks & Detailed Guidance

### Subtask T005 — Move visual-docs-style.md to standards [P]

- **Purpose**: `visual-docs-style.md` is a cross-cutting style guide (Mermaid diagrams, visual conventions) — belongs in `docs/design/standards/` alongside other authoring standards.
- **Steps**:
  1. Run `git mv docs/runbooks/visual-docs-style.md docs/design/standards/visual-docs-style.md`.
  2. Edit the frontmatter of the new file: change `doc_type: handbook` → `doc_type: standard`. Add `last_validated: 2026-04-05` if not present.
  3. Do NOT modify the body of the document.
  4. Verify: `ls docs/design/standards/visual-docs-style.md` succeeds; `ls docs/runbooks/visual-docs-style.md` fails.
- **Files**: `docs/runbooks/visual-docs-style.md` (removed), `docs/design/standards/visual-docs-style.md` (new location).
- **Parallel?**: Yes — independent of T006.
- **Notes**: Do not rename the file during the move; keep `visual-docs-style.md` as the filename.

### Subtask T006 — Move office2-backup-and-security.md to design [P]

- **Purpose**: `office2-backup-and-security.md` is strategic rationale describing the backup + security posture design (not prescriptive how-to steps). Belongs in `docs/design/` top-level alongside other rationale docs like `adversarial-analysis.md`.
- **Steps**:
  1. Run `git mv docs/runbooks/office2-backup-and-security.md docs/design/office2-backup-and-security.md`.
  2. Edit the frontmatter of the new file: change `doc_type: handbook` → `doc_type: explanation`. Add `last_validated: 2026-04-05` if not present.
  3. Do NOT modify the body of the document.
  4. Verify: `ls docs/design/office2-backup-and-security.md` succeeds; `ls docs/runbooks/office2-backup-and-security.md` fails.
- **Files**: `docs/runbooks/office2-backup-and-security.md` (removed), `docs/design/office2-backup-and-security.md` (new location).
- **Parallel?**: Yes — independent of T005.
- **Notes**: The `office2-` prefix stays (machine-readable identifier for the server). Don't rename.

### Subtask T007 — Verify history preservation

- **Purpose**: Confirm that git recognizes the moves as renames (not delete+add) so history is retrievable via `--follow`.
- **Steps**:
  1. Run `git status --short` — expect to see R (renamed) status for both files, not D+A.
  2. Run `git log --follow docs/design/standards/visual-docs-style.md` — expect to see commit history from when the file lived in docs/runbooks/.
  3. Run `git log --follow docs/design/office2-backup-and-security.md` — expect same.
  4. If history is not preserved, STOP and investigate (possibly the move was via `rm` + `cp` instead of `git mv`).
- **Files**: None modified. Verification only.
- **Parallel?**: No — runs after T005 and T006.
- **Notes**: `git mv` is equivalent to `git rm` + `git add` but marks as rename. If the file was moved with `mv` (shell), `git add` will detect as rename if the file is similar enough.

## Test Strategy

N/A — documentation move, no automated tests.

**Manual validation**:

- `git status` shows R (rename) entries.
- `git log --follow <new-path>` shows commits prior to the move.
- Files are readable at new locations with expected body content.
- Frontmatter updated correctly.

## Risks & Mitigations

- **Risk**: `git mv` fails silently if target directory doesn't exist. **Mitigation**: Both target dirs (`docs/design/standards/`, `docs/design/`) already exist.
- **Risk**: History not preserved if content changes too drastically during move. **Mitigation**: Move body unchanged; frontmatter edit only.
- **Risk**: Broken inbound refs until WP03, WP04, WP11 run. **Mitigation**: Those WPs are dependencies of this one in the task DAG.

## Integration Verification

- [ ] `docs/runbooks/visual-docs-style.md` no longer exists.
- [ ] `docs/runbooks/office2-backup-and-security.md` no longer exists.
- [ ] `docs/design/standards/visual-docs-style.md` exists with `doc_type: standard`.
- [ ] `docs/design/office2-backup-and-security.md` exists with `doc_type: explanation`.
- [ ] `git log --follow` works for both new paths.
- [ ] File bodies are byte-identical to originals (diff shows only frontmatter change).

## Review Guidance

- **Key checkpoints**: `git status` shows renames (R), not delete+add (D+A). Frontmatter updated to correct Divio values. Body unchanged.
- **Before approving**: Run `git log --follow <new-path> | head -5` for both files — history should show prior commits.

## Definition of Done

- Both moves committed to main.
- Frontmatter `doc_type` corrected per Divio standard.
- Git history preserved via `git mv`.
