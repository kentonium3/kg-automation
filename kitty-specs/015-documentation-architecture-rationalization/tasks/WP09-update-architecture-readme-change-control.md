---
work_package_id: WP09
title: Update Architecture README + Change-Control Protocol
dependencies:
- WP07
requirement_refs:
- FR-006
- FR-007
- FR-011
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 015-documentation-architecture-rationalization-WP07
base_commit: 09da0c563d8d729876c57567453b2c1422c7e871
created_at: '2026-04-05T04:29:45.151740+00:00'
subtasks:
- T036
- T037
- T038
phase: Phase 3 - Entry Point Updates
assignee: ''
agent: ''
shell_pid: '6723'
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/architecture/
execution_mode: code_change
owned_files:
- docs/design/architecture/README.md
- docs/design/architecture/change-control.md
---

# Work Package Prompt: WP09 — Update Architecture README + Change-Control

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or stacked on WP07.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Document `docs/design/architecture/data/` as the canonical home for machine-readable artifacts in the architecture README, and add `docs/INDEX.md` maintenance to the change-control protocol so it stays current.

**Success criteria**:

- [ ] `docs/design/architecture/README.md` explicitly states `data/` as the canonical machine-readable artifact home.
- [ ] `docs/design/architecture/change-control.md` requires `docs/INDEX.md` updates when a doc/directory is added, moved, or removed.
- [ ] Schema co-location convention documented (schemas live with or link to the data they describe).

## Context & Constraints

These two files are authoritative architecture docs. Changes must be additive — preserve existing structure and content.

**Constraints**:

- Body content unchanged except for additions.
- Keep existing frontmatter.
- Don't restructure sections.

**Reference documents**:

- `kitty-specs/015-documentation-architecture-rationalization/spec.md` FR-006, FR-007, FR-011
- `docs/design/architecture/README.md` (existing — read first)
- `docs/design/architecture/change-control.md` (existing — read first)

## Subtasks & Detailed Guidance

### Subtask T036 — Update architecture README with canonical data home statement

- **Purpose**: Formalize `docs/design/architecture/data/` as the single canonical home for operational JSON.
- **Steps**:
  1. Read `docs/design/architecture/README.md` to understand existing structure.
  2. Add a new section (or extend an existing one) titled "Machine-Readable Artifacts":

     ```markdown
     ## Machine-Readable Artifacts

     `docs/design/architecture/data/` is the **canonical home** for all current-state operational
     JSON describing the kg-automation system: service inventory, hardware, network topology,
     credentials manifest, data flows, and associated JSON schemas.

     - **Authoritative record**: These JSON files are the source of truth. Narrative `.md`
       companions (e.g., `service-inventory.md`) render the JSON as prose for human readers.
     - **Exempt from moves**: Files in `data/` are not relocated by documentation-rationalization
       work (F015 constraint C-001).
     - **Schema co-location**: Schema files (`*-schema.json`) live alongside the data files they
       describe, or link to a clear schema reference location.

     See [docs/INDEX.md](../../INDEX.md) for the full machine-readable artifact listing.
     ```

  3. Place near the top (after the directory's purpose statement).
- **Files**: `docs/design/architecture/README.md`.
- **Parallel?**: Yes — independent of T037, T038.
- **Notes**: If a similar section already exists, extend rather than duplicate.

### Subtask T037 — Update change-control protocol to require INDEX.md updates

- **Purpose**: Make INDEX.md maintenance mandatory, preventing staleness.
- **Steps**:
  1. Read `docs/design/architecture/change-control.md` to understand existing protocol structure.
  2. Add a new rule to the change-control protocol (in whatever section covers "when a feature changes docs"):

     ```markdown
     ### INDEX.md Maintenance (mandatory)

     When a feature adds, moves, archives, or deletes any document or directory under `docs/`,
     the same feature branch MUST update `docs/INDEX.md` to reflect the change. Failure to
     update INDEX.md is a protocol violation and blocks feature acceptance.

     **Applies to**:

     - Adding a new doc or directory
     - Moving/renaming a doc or directory
     - Archiving a doc (moving to `docs/archive/`)
     - Deprecating a doc (`status: deprecated`)
     - Adding a new machine-readable artifact

     **Does not apply to**:

     - Editing an existing doc's body content without changing its path
     - Updating frontmatter metadata alone (e.g., `last_validated`)
     ```

  3. Also add a bullet to any existing "Standing Requirements" or "When to update" checklist.
- **Files**: `docs/design/architecture/change-control.md`.
- **Parallel?**: Yes — independent of T036.
- **Notes**: Cite FR-011 in the commit message.

### Subtask T038 — Document schema co-location convention

- **Purpose**: Record the rule that schemas live with or link to the data they describe.
- **Steps**:
  1. Can be done as part of T036 (the README update already includes this bullet in the Machine-Readable Artifacts section).
  2. If preferred standalone, add a short subsection under T036's new content listing the current examples:

     ```markdown
     **Current schemas**:

     - `docs/design/architecture/data/capabilities-schema.json` — schema for capability registration
     - `docs/design/architecture/data/catalog-schema.json` — schema for catalog entries
     - `docs/design/standards/frontmatter.schema.json` — schema for doc frontmatter (lives in standards/)
     ```

- **Files**: `docs/design/architecture/README.md` (or change-control.md if the author prefers there).
- **Parallel?**: Yes.
- **Notes**: If the schema-frontmatter file lives outside `data/`, that's documented as the exception (standards directory).

## Test Strategy

N/A — documentation feature, no automated tests.

**Manual validation**:

- README states data/ as canonical home.
- change-control.md has INDEX.md maintenance rule.
- Schema co-location documented.

## Risks & Mitigations

- **Risk**: Duplicating existing content. **Mitigation**: Read each file fully before adding; extend existing sections where applicable.
- **Risk**: change-control.md's existing structure doesn't fit the new rule. **Mitigation**: Add a new section if no existing section fits.

## Integration Verification

- [ ] `docs/design/architecture/README.md` contains "canonical home" language for data/.
- [ ] `docs/design/architecture/change-control.md` has INDEX.md update requirement.
- [ ] Schema co-location rule documented.
- [ ] No existing content deleted or restructured.

## Review Guidance

- **Key checkpoints**: Additions integrate with existing structure. Language is clear and enforceable.
- **Before approving**: Read the updated change-control.md end-to-end — does the new rule fit naturally?

## Definition of Done

- Both files updated and committed to main.
- Canonical home statement + INDEX.md rule + schema co-location in place.
