---
work_package_id: WP01
title: Create Divio Standards Reference Doc
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 60a2baddbbccf5f0031eef0796babfee9e0300f3
created_at: '2026-04-05T03:45:21.449947+00:00'
subtasks:
- T001
- T002
- T003
- T004
phase: Phase 0 - Foundation
assignee: ''
agent: ''
shell_pid: '95612'
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/standards/divio-classification.md
execution_mode: code_change
owned_files:
- docs/design/standards/divio-classification.md
---

# Work Package Prompt: WP01 — Create Divio Standards Reference Doc

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created. For this WP, base = main.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Author `docs/design/standards/divio-classification.md` — the permanent, published Divio classification standard for kg-automation documentation. This is the reference doc that all future docs cite to justify their `doc_type` value.

**Success criteria**:

- [ ] `docs/design/standards/divio-classification.md` exists with correct frontmatter (`doc_type: standard`, `status: approved`).
- [ ] Document defines the 7 canonical `doc_type` values and maps each to its Divio parent (how-to, reference, explanation).
- [ ] Document specifies the canonical home (directory path) for each `doc_type`.
- [ ] Document provides the legacy-value migration table for existing docs.
- [ ] Document specifies audience declaration rules for runbooks.
- [ ] Document is reachable from `docs/INDEX.md` (reference added in WP07).

## Context & Constraints

This is the **foundational WP** for F015. Other WPs cite this document when correcting frontmatter. Content is derived from `kitty-specs/015-documentation-architecture-rationalization/data-model.md` sections 1–6 — that file is the draft that this WP promotes to a published standard.

**Constraints**:

- Must be self-contained — readers shouldn't need to read spec-kitty templates or external Divio docs.
- Keep the tone aligned with existing standards docs (`docs/design/standards/doc-standards.md`, `docs/design/standards/obsidian-linter-alignment.md`).
- No new frontmatter field invention — stick to the schema in data-model.md.
- Cross-reference: link back to `docs/design/standards/doc-standards.md` as the operational authoring standards companion.

**Reference documents**:

- `kitty-specs/015-documentation-architecture-rationalization/data-model.md` (authoritative schema)
- `kitty-specs/015-documentation-architecture-rationalization/research.md` (audit findings with legacy values)
- `docs/design/standards/doc-standards.md` (existing companion standard)

## Subtasks & Detailed Guidance

### Subtask T001 — Create file with frontmatter and intro

- **Purpose**: Establish the document skeleton with proper frontmatter and an introduction framing Divio for kg-automation's internal audience.
- **Steps**:
  1. Create `docs/design/standards/divio-classification.md` with frontmatter:

     ```yaml
     ---
     title: Divio Classification Standard
     doc_type: standard
     status: approved
     owners: [kgale]
     version: "1.0"
     last_validated: 2026-04-05
     ---
     ```

  2. Add H1 and a 2–3 paragraph introduction explaining:
     - What Divio is (brief: the 4-type documentation framework)
     - Why kg-automation uses it (discoverability for AI agents + humans)
     - The internal-audience mapping (how-to = runbook, reference = architecture, explanation = rationale; tutorials absent by design)
- **Files**: `docs/design/standards/divio-classification.md` (new, ~40 lines for this subtask)
- **Parallel?**: No — blocks T002, T003, T004.
- **Notes**: Version 1.0 since this is the first published version. Credit Divio framework upstream (divio.com/blog/documentation).

### Subtask T002 — Document the 7 canonical doc_type values [P]

- **Purpose**: Enumerate the canonical `doc_type` values and their Divio mapping so authors can pick the right one.
- **Steps**:
  1. Add a section titled "Canonical doc_type Values" with a table matching data-model.md §1:

     | `doc_type` | Divio Parent | Purpose | Example Paths |

  2. Cover all 7 values: `runbook`, `reference`, `spec`, `explanation`, `standard`, `postmortem`, `diagnostic`.
  3. For each value, provide 2–3 example paths from the actual repo.
- **Files**: `docs/design/standards/divio-classification.md` (append ~60 lines)
- **Parallel?**: Yes — after T001 creates the file skeleton.
- **Notes**: Examples should be real paths from the current repo (e.g., `docs/runbooks/vikunja-ops.md` for runbook).

### Subtask T003 — Document canonical home rules + legacy migration [P]

- **Purpose**: State which directory each `doc_type` lives in, and how to migrate legacy values.
- **Steps**:
  1. Add a section "Canonical Home Per Type" with a table per data-model.md §2.
  2. Add a section "Legacy Value Migration Table" with the retired-values table from data-model.md §1 (`handbook`, `strategy`, `charter`, `policy`, `note`, `index`, `guide`, `func-spec`).
  3. For each legacy value, note how to pick the migration target (dominant-type rule per spec constraint C-007).
- **Files**: `docs/design/standards/divio-classification.md` (append ~50 lines)
- **Parallel?**: Yes — after T001.
- **Notes**: This is the exact reference that WP03, WP04, WP05, WP06 will cite when applying corrections.

### Subtask T004 — Document audience rules + supersession pattern [P]

- **Purpose**: Specify the `audience` field for runbooks and the supersession pattern for deprecated docs.
- **Steps**:
  1. Add a section "Audience Declaration (for runbooks)" listing the 3 values (`human-only`, `agent-executable`, `both`) with 1–2 sentence definitions each.
  2. Add a section "Supersession" explaining `status: deprecated` + `superseded_by` field for superseded docs.
  3. Add a short "Compliance" section noting: docs that don't conform are orphaned and get flagged on next feature.
- **Files**: `docs/design/standards/divio-classification.md` (append ~40 lines)
- **Parallel?**: Yes — after T001.
- **Notes**: Audience values come from data-model.md §5. Supersession pattern from §6.

## Test Strategy

N/A — documentation feature, no automated tests (per spec constraint C-006).

**Manual validation**:

- File parses as valid markdown (no broken tables).
- All 7 `doc_type` values covered.
- All legacy values have a migration target.
- Audience rules cover all 3 values.

## Risks & Mitigations

- **Risk**: Doc becomes stale if Divio schema evolves. **Mitigation**: `version` + `last_validated` frontmatter fields; change-control protocol update (WP09) will require version bumps.
- **Risk**: Doc conflicts with existing `docs/design/standards/doc-standards.md`. **Mitigation**: Explicitly link the two; treat doc-standards.md as operational authoring guide, divio-classification.md as the taxonomy.

## Integration Verification

- [ ] File exists at `docs/design/standards/divio-classification.md`.
- [ ] Frontmatter valid (parses as YAML, has required fields).
- [ ] All 7 `doc_type` values documented.
- [ ] Legacy migration table complete.
- [ ] No broken markdown (tables render, links resolve).

## Review Guidance

- **Key checkpoints**: All 7 canonical values defined; legacy migration table complete; audience rules present.
- **Before approving**: Spot-check one example path per `doc_type` — does it exist in the repo? Does the classification fit the example?

## Definition of Done

- File committed to main at `docs/design/standards/divio-classification.md`.
- Passes manual validation.
- No broken internal links.
