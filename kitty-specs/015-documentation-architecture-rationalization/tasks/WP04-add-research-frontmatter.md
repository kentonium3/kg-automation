---
work_package_id: WP04
title: Add Frontmatter to Research Docs + Link Updates
dependencies: []
requirement_refs:
- FR-004
- FR-013
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
phase: Phase 1 - Frontmatter Corrections
assignee: ''
agent: ''
shell_pid: ''
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/research/005-system-architecture-development/
execution_mode: code_change
owned_files:
- docs/design/research/005-system-architecture-development/agent-team-architecture.md
- docs/design/research/005-system-architecture-development/data-architecture.md
- docs/design/research/005-system-architecture-development/data-privacy-identity.md
- docs/design/research/005-system-architecture-development/integration-map.md
- docs/design/research/005-system-architecture-development/integration-needs.md
- docs/design/research/005-system-architecture-development/local-audit.md
- docs/design/research/005-system-architecture-development/openclaw-capabilities.md
- docs/design/research/005-system-architecture-development/roadmap.md
- docs/design/research/005-system-architecture-development/user-story-catalog.md
---

# Work Package Prompt: WP04 — Add Frontmatter to Research Docs + Link Updates

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or stacked on WP02.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Add missing `doc_type`, `status`, and `title` frontmatter to 9 research files in `docs/design/research/005-system-architecture-development/`, and update link references in `local-audit.md` that point to the file moved in WP02.

**Success criteria**:

- [ ] All 9 files in the research directory have valid frontmatter with `doc_type`, `status`, `title`.
- [ ] `doc_type` values match Divio classification per research.md §1.
- [ ] `local-audit.md` links to `office2-backup-and-security.md` now point to `docs/design/office2-backup-and-security.md` (2 occurrences).

## Context & Constraints

These are F005 architecture research outputs authored circa 2025/2026. All 9 files currently lack frontmatter.

**Classifications per research.md §1**:

- `explanation` (design rationale): agent-team-architecture, data-architecture, data-privacy-identity, integration-needs, openclaw-capabilities
- `reference` (inventories/catalogs): integration-map, local-audit, roadmap, user-story-catalog

**Constraints**:

- Body content unchanged; only frontmatter added + local-audit.md's 2 link lines.
- These are historical research artifacts — `status: approved` (they represent past completed research).

**Reference documents**:

- `kitty-specs/015-documentation-architecture-rationalization/research.md` §1 (classifications)
- `kitty-specs/015-documentation-architecture-rationalization/data-model.md` §3 (required fields)
- `docs/design/standards/divio-classification.md` (created in WP01)

## Subtasks & Detailed Guidance

### Subtask T014 — Add frontmatter to explanation-type research files

- **Purpose**: 5 files documenting research RATIONALE (why-oriented design research).
- **Files** (5):
  - `agent-team-architecture.md`
  - `data-architecture.md`
  - `data-privacy-identity.md`
  - `integration-needs.md`
  - `openclaw-capabilities.md`
- **Steps**:
  1. For each file, read the existing H1 to determine the title.
  2. Prepend a frontmatter block to each file:

     ```yaml
     ---
     title: <from H1>
     doc_type: explanation
     status: approved
     owners: [kgale]
     ---
     ```

  3. If `data-privacy-identity.md` is near-duplicate of `data-architecture.md` (per research.md observation), add `divio_ambiguity: "overlap with data-architecture.md; consider consolidating"` to its frontmatter.
- **Files**: 5 files listed above.
- **Parallel?**: Yes — 5 independent files.
- **Notes**: Each file gets 5-6 lines of frontmatter prepended. Body stays unchanged.

### Subtask T015 — Add frontmatter to reference-type research files [P]

- **Purpose**: 4 files documenting system INVENTORIES (what-oriented research output).
- **Files** (4):
  - `integration-map.md`
  - `local-audit.md`
  - `roadmap.md`
  - `user-story-catalog.md`
- **Steps**:
  1. For each file, read the existing H1 to determine the title.
  2. Prepend a frontmatter block:

     ```yaml
     ---
     title: <from H1>
     doc_type: reference
     status: approved
     owners: [kgale]
     ---
     ```
- **Files**: 4 files listed above.
- **Parallel?**: Yes — 4 independent files.
- **Notes**: `local-audit.md` needs link updates in T016 — do frontmatter here, link updates separately.

### Subtask T016 — Update local-audit.md link references

- **Purpose**: `local-audit.md` contains 2 references to `office2-backup-and-security.md` at its OLD path.
- **Steps**:
  1. Read `docs/design/research/005-system-architecture-development/local-audit.md`.
  2. Replace 2 occurrences of `docs/runbooks/office2-backup-and-security.md` with `docs/design/office2-backup-and-security.md`.
  3. Original lines (approximate):

     - Line ~223: "- Documented in docs/runbooks/office2-backup-and-security.md"
     - Line ~233: "- Documented in docs/runbooks/office2-backup-and-security.md"
  4. Verify with grep.
- **Files**: `docs/design/research/005-system-architecture-development/local-audit.md`.
- **Parallel?**: No — runs after T015.
- **Notes**: These are inline markdown references in narrative text.

## Test Strategy

N/A — documentation feature, no automated tests.

## Risks & Mitigations

- **Risk**: Frontmatter inserted incorrectly (missing YAML delimiter or malformed). **Mitigation**: Standard template for all files.
- **Risk**: Wrong classification (some research files blend types). **Mitigation**: Follow research.md §1 classifications; use `divio_ambiguity` field for edge cases.

## Integration Verification

- [ ] All 9 files have valid frontmatter with required fields.
- [ ] `grep -l "doc_type: explanation" docs/design/research/005-system-architecture-development/` shows 5 files.
- [ ] `grep -l "doc_type: reference" docs/design/research/005-system-architecture-development/` shows 4 files.
- [ ] `grep -n "docs/runbooks/office2-backup-and-security" docs/design/research/005-system-architecture-development/local-audit.md` shows zero matches (all updated).

## Review Guidance

- **Key checkpoints**: Frontmatter is valid YAML. Classifications match research.md. local-audit.md links updated.
- **Before approving**: Spot-check 2 files to verify frontmatter is well-formed and title matches H1.

## Definition of Done

- 9 files have frontmatter committed to main.
- local-audit.md 2 links updated.
