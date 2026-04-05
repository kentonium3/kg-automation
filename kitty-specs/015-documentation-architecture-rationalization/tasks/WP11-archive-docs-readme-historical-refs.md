---
work_package_id: WP11
title: Archive docs-readme.md + Update Historical Spec References
dependencies:
- WP02
- WP07
requirement_refs:
- FR-010
- FR-013
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 015-documentation-architecture-rationalization-WP11-merge-base
base_commit: 09da0c563d8d729876c57567453b2c1422c7e871
created_at: '2026-04-05T04:49:19.074464+00:00'
subtasks:
- T041
- T042
- T043
phase: Phase 3 - Cleanup
assignee: ''
agent: "claude"
shell_pid: "12181"
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/archive/
execution_mode: code_change
owned_files:
- docs/docs-readme.md
- docs/archive/docs-readme.md
- docs/func-spec/F001_vikunja_docker_deploy.md
- docs/func-spec/F002_openclaw_install.md
- docs/func-spec/F005_system_architecture_review.md
---

# Work Package Prompt: WP11 — Archive docs-readme.md + Update Historical Spec References

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or stacked on WP02/WP07.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Archive the stale `docs/docs-readme.md` (replaced by INDEX.md in WP07) and update historical func-spec references that point to files moved in WP02.

**Success criteria**:

- [ ] `docs/docs-readme.md` no longer exists at original path.
- [ ] `docs/archive/docs-readme.md` exists with `status: archived` and `superseded_by: docs/INDEX.md`.
- [ ] `docs/func-spec/F002_openclaw_install.md` references to `office2-backup-and-security.md` use new path (2 occurrences).
- [ ] No active (non-archived) doc references the original `docs/docs-readme.md` path.

## Context & Constraints

After WP07 creates INDEX.md, the old docs-readme.md is redundant and stale (references non-existent diagram files per F015 spec).

**Inbound ref updates needed**:

- F002 has 2 references to `office2-backup-and-security.md` at its OLD path (moved in WP02).
- F001 and F005 reference `personal-ai-system-spec-v03.md` but v03 is deprecated-not-deleted, so those refs still resolve. We do NOT rewrite F001/F005 for v03 → v1.0 (historical artifacts; low value, high churn).

**Constraints**:

- Use `git mv` for the archival move (C-003).
- Historical func-specs are archive-like; do not rewrite extensively. Only fix literally broken refs.

**Reference documents**:

- `kitty-specs/015-documentation-architecture-rationalization/research.md` §6 (reference audit map)

## Subtasks & Detailed Guidance

### Subtask T041 — Archive docs-readme.md

- **Purpose**: Move the old index to `docs/archive/` and mark it as superseded.
- **Steps**:
  1. Verify `docs/archive/` directory exists (if not, `mkdir -p docs/archive/` is acceptable — this is a supported archive home).
  2. Run `git mv docs/docs-readme.md docs/archive/docs-readme.md`.
  3. Edit the new file's frontmatter:

     ```yaml
     ---
     title: Visual Docs Index (archived)
     doc_type: reference
     status: archived
     superseded_by: docs/INDEX.md
     ---
     ```

  4. Leave the body unchanged (historical reference).
  5. Verify: `ls docs/docs-readme.md` fails; `ls docs/archive/docs-readme.md` succeeds.
- **Files**: `docs/docs-readme.md` (origin — removed), `docs/archive/docs-readme.md` (new).
- **Parallel?**: Yes — independent of T042.
- **Notes**: Keep the file's internal links (to non-existent diagrams) as-is — this is frozen history now.

### Subtask T042 — Update F002 references to moved office2-backup doc

- **Purpose**: F002 references the OLD path of office2-backup-and-security.md. Update to new path.
- **Steps**:
  1. Read `docs/func-spec/F002_openclaw_install.md`.
  2. Find references at approx lines 73 and 203:

     - Line ~73: "`docs/runbooks/office2-backup-and-security.md` — credential store location,..."
     - Line ~203: "Follow the procedure documented in `docs/runbooks/office2-backup-and-security.md`"
  3. Replace both with new path: `docs/design/office2-backup-and-security.md`.
  4. Verify with grep: `grep -n "office2-backup-and-security" docs/func-spec/F002_openclaw_install.md` — should show 2 lines, both with new path.
- **Files**: `docs/func-spec/F002_openclaw_install.md`.
- **Parallel?**: Yes — independent of T041.
- **Notes**: F002 is a historical spec; this is a narrow scope update (just broken path refs, not content rewrite).

### Subtask T043 — Verify no active docs reference old docs-readme.md path

- **Purpose**: Confirm archiving is clean.
- **Steps**:
  1. Run `grep -rn "docs/docs-readme\.md\|./docs-readme\.md" docs/ CLAUDE.md ai-agents/ --include="*.md" | grep -v "^docs/archive/" | grep -v "^kitty-specs/"`
  2. Expect zero matches in active (non-archive, non-kitty-specs) paths.
  3. If matches found: those files need updating to reference `docs/INDEX.md` instead. Flag for follow-up.
- **Files**: None modified. Validation only.
- **Parallel?**: No — runs after T041.
- **Notes**: kitty-specs and archive are excluded because they're historical/frozen contexts.

## Test Strategy

N/A — documentation feature, no automated tests.

## Risks & Mitigations

- **Risk**: `git mv` fails if `docs/archive/` doesn't exist. **Mitigation**: mkdir first if needed (acceptable — creating the archive dir is part of this WP).
- **Risk**: F002 has additional stale references not caught. **Mitigation**: grep validation in T043.
- **Risk**: F001, F005 v03 references become a scope-creep trap. **Mitigation**: Explicitly scoped OUT of this WP.

## Integration Verification

- [ ] `docs/docs-readme.md` no longer exists.
- [ ] `docs/archive/docs-readme.md` exists with `status: archived`, `superseded_by: docs/INDEX.md`.
- [ ] F002 spec references to office2-backup-and-security use new path.
- [ ] No active doc (outside archive/ and kitty-specs/) references old `docs-readme.md` path.

## Review Guidance

- **Key checkpoints**: Archive move clean. F002 refs surgical. No broad content rewrites.
- **Before approving**: Run T043's validation grep.

## Definition of Done

- docs-readme.md archived with supersession pointer.
- F002 references updated.
- Validation passes.
- Committed to main.

## Activity Log

- 2026-04-05T04:49:19Z – claude – shell_pid=11028 – Started implementation via workflow command
- 2026-04-05T04:51:41Z – claude – shell_pid=11028 – Ready for review: docs-readme.md archived (status: archived, superseded_by: docs/INDEX.md, 97% similarity preserved via git mv). F002 2 link refs updated to new office2-backup path. F015 spec retains 4 descriptive prose references to docs/docs-readme.md (historical, describing the archive operation) — left in place per WP11 scope; these are inline code backticks, not markdown links.
- 2026-04-05T04:53:44Z – claude – shell_pid=12181 – Started review via workflow command
