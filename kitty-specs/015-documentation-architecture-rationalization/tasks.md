---
description: Work packages for F015 Documentation Architecture Rationalization
---

# Work Packages: Documentation Architecture Rationalization

**Inputs**: Design documents from `/kitty-specs/015-documentation-architecture-rationalization/`
**Prerequisites**: plan.md (required), spec.md (user scenarios), research.md (Divio audit), data-model.md (doc_type schema), quickstart.md (authoring flow)

**Tests**: Not applicable — this is a documentation-curation feature (C-006: no automated validators introduced).

**Organization**: 43 fine-grained subtasks (`T001`–`T043`) roll up into 11 work packages (`WP01`–`WP11`). Each WP has disjoint `owned_files` so WPs cannot overlap in their writes.

**Prompt Files**: Each WP references a matching prompt file in `tasks/` with full implementation guidance.

## Subtask Format: `[Txxx] [P?] Description`

- **[P]** indicates the subtask can proceed in parallel (independent files within the same WP).
- File paths are repo-relative from `/Users/kentgale/repos/kg-automation/`.

## Path Conventions

All changes occur under `docs/`, `CLAUDE.md` (repo root), and `ai-agents/`. No `src/`, no `tests/`.

---

## Work Package WP01: Create Divio Standards Reference Doc (Priority: P0)

**Goal**: Author the permanent Divio classification standard that future docs will cite.
**Independent Test**: `docs/design/standards/divio-classification.md` exists, covers all 7 canonical `doc_type` values, maps each to its canonical home, and describes the legacy-value migration table.
**Prompt**: `tasks/WP01-create-divio-standards-doc.md`
**Requirement Refs**: FR-001, FR-003

### Included Subtasks

- [x] T001 Create `docs/design/standards/divio-classification.md` with frontmatter + intro
- [x] T002 [P] Document the 7 canonical `doc_type` values with Divio-parent mapping
- [x] T003 [P] Document canonical home rules and legacy-value migration table
- [x] T004 [P] Document audience declaration rules and supersession pattern

### Implementation Notes

Content is derived from `data-model.md` sections 1–6. This is the permanent/published version of that schema.

### Parallel Opportunities

T002, T003, T004 can be drafted independently once T001 is in place.

### Dependencies

None — this is the foundational WP that everything else cites.

### Risks & Mitigations

- Doc becomes stale if Divio schema evolves. Mitigated by `status: approved` frontmatter + version field.

---

## Work Package WP02: Move Misclassified Runbook Content (Priority: P0)

**Goal**: Move two files out of `docs/runbooks/` that are not prescriptive how-to guides: `visual-docs-style.md` (a cross-cutting standard) and `office2-backup-and-security.md` (strategic rationale).
**Independent Test**: Both files exist at new paths with corrected frontmatter, old paths no longer exist, git history preserved (verified via `git log --follow`).
**Prompt**: `tasks/WP02-move-misclassified-runbook-content.md`
**Requirement Refs**: FR-003, C-003

### Included Subtasks

- [x] T005 `git mv docs/runbooks/visual-docs-style.md docs/design/standards/visual-docs-style.md` + update `doc_type: handbook` → `standard`
- [x] T006 `git mv docs/runbooks/office2-backup-and-security.md docs/design/office2-backup-and-security.md` + update `doc_type: handbook` → `explanation`
- [x] T007 Verify new paths exist, old paths don't, history preserved via `git log --follow`

### Implementation Notes

Uses `git mv` per C-003. New files inherit original history. Inbound reference updates happen in subsequent WPs (WP03 updates `deployment.md`, WP04 updates `local-audit.md`, WP11 updates F002 spec references).

### Parallel Opportunities

T005 and T006 are independent — parallel-safe.

### Dependencies

None — destination dirs `docs/design/standards/` and `docs/design/` already exist.

### Risks & Mitigations

- Broken inbound references immediately after the move. Mitigated by sequencing downstream work packages that update inbound refs as dependents of this package.

---

## Work Package WP03: Fix docs/runbooks/ Frontmatter + Audience + Link Updates (Priority: P0)

**Goal**: Replace legacy `handbook` frontmatter with canonical Divio values across all 24 remaining runbook files, add `audience` declarations to runbooks, and update any inbound links to the files moved in WP02.
**Independent Test**: Every file in `docs/runbooks/**` has `doc_type ∈ {runbook, reference, standard}` and every `doc_type: runbook` file has an `audience` value.
**Prompt**: `tasks/WP03-fix-runbooks-frontmatter.md`
**Requirement Refs**: FR-003, FR-004, FR-005, NFR-002

### Included Subtasks

- [x] T008 Fix handbook → runbook + add audience on 10 service-ops runbooks (vikunja-ops, goals-ops, habits-ops, inbox-ops, observation-ops, openclaw-ops, transcribe-ops, whatsapp-ops, obsidian-sync-ops, task-intelligence-ops)
- [x] T009 Fix handbook → runbook + add audience on 4 setup/deployment runbooks (deployment, obsidian-setup, obsidian, spec-kitty-init-in-existing-repo)
- [x] T010 Fix handbook → runbook + add audience on 6 process/governance runbooks (felix-governance, ci-handbook, agent-handbook, agent-execution-roles, claude-code, maintenance)
- [x] T011 Fix misclassifications: templater-commands handbook → reference; repo-governance policy → standard
- [x] T012 Update `docs/runbooks/deployment.md` link references: `docs/runbooks/office2-backup-and-security.md` → `docs/design/office2-backup-and-security.md` (3 occurrences)
- [x] T013 Validate all runbooks/* files have correct frontmatter values

### Implementation Notes

Audience assignments per research.md §7 (8 files = agent-executable, rest = human-only or both). See prompt file for full mapping.

### Parallel Opportunities

T008, T009, T010, T011 are parallel-safe (different file subsets).

### Dependencies

- WP01 (cite Divio standard)
- WP02 (new path for office2-backup-and-security.md must exist)

### Risks & Mitigations

- Misclassification of agent-executable vs human-only. Mitigated by research.md agent-executable candidate list.

---

## Work Package WP04: Add Frontmatter to Research Docs + Link Updates (Priority: P1)

**Goal**: Add missing `doc_type` and `status` frontmatter to 9 research files in `docs/design/research/005-system-architecture-development/`, and update `local-audit.md`'s link references to the file moved in WP02.
**Independent Test**: All 9 files in the research directory have valid frontmatter; `local-audit.md`'s references to `office2-backup-and-security.md` point to the new path.
**Prompt**: `tasks/WP04-add-research-frontmatter.md`
**Requirement Refs**: FR-004, FR-013, NFR-003

### Included Subtasks

- [x] T014 Add frontmatter to 5 explanation-type research files (agent-team-architecture, data-architecture, data-privacy-identity, integration-needs, openclaw-capabilities)
- [x] T015 [P] Add frontmatter to 4 reference-type research files (integration-map, local-audit, roadmap, user-story-catalog)
- [x] T016 Update `local-audit.md` link references: `docs/runbooks/office2-backup-and-security.md` → `docs/design/office2-backup-and-security.md` (2 occurrences)

### Implementation Notes

Divio type assignments per research.md §1. All 9 files need `doc_type`, `status`, `title`.

### Parallel Opportunities

T014 and T015 can be done in parallel.

### Dependencies

- WP02 (new path for office2-backup-and-security.md)

### Risks & Mitigations

- One file (`data-privacy-identity.md`) may be a near-duplicate of `data-architecture.md`. Note in `divio_ambiguity` field if applicable.

---

## Work Package WP05: Add Frontmatter to Diagnostic Files (Priority: P2)

**Goal**: Add missing frontmatter to 6 diagnostic files so they conform to the Divio schema.
**Independent Test**: All files in `docs/issues/diagnostics/**` except `spec-kitty-workflow-journal.md` (already done) have `doc_type: diagnostic` frontmatter.
**Prompt**: `tasks/WP05-add-diagnostic-frontmatter.md`
**Requirement Refs**: FR-004

### Included Subtasks

- [x] T017 Add frontmatter to `docs/issues/diagnostics/f012-merge-breadcrumbs.md`
- [x] T018 [P] Add frontmatter to 5 files in `docs/issues/diagnostics/spec-kitty-feedback/`
- [x] T019 Validate all files have `doc_type: diagnostic` and a `status` value

### Implementation Notes

Determine title from each file's existing H1. `status: active` or `status: resolved` per file content.

### Parallel Opportunities

T017, T018 parallel-safe.

### Dependencies

None.

### Risks & Mitigations

- None. These are historical incident notes; low risk.

---

## Work Package WP06: Fix docs/design/ Top-Level + Standards Frontmatter (Priority: P1)

**Goal**: Correct `doc_type` misclassifications in 13 docs under `docs/design/` top-level and `docs/design/standards/`, deprecate superseded system spec.
**Independent Test**: All 13 files have canonical `doc_type` values from the enum; `personal-ai-system-spec-v03.md` has `status: deprecated` and `superseded_by: docs/design/personal-ai-system-spec-v1.0.md`.
**Prompt**: `tasks/WP06-fix-design-frontmatter.md`
**Requirement Refs**: FR-004

### Included Subtasks

- [x] T020 Fix top-level explanation docs (Vikunja.md note → explanation; adversarial-analysis strategy → explanation; strategic-acceleration-charter charter → explanation)
- [x] T021 Fix top-level reference docs (felix-capability-roadmap strategy → reference; personal-ai-system-spec-v1.0 strategy → reference + add `supersedes`)
- [x] T022 Deprecate `personal-ai-system-spec-v03.md`: status → deprecated, add `superseded_by` + set `doc_type: reference`
- [x] T023 Fix standards frontmatter (doc-standards policy → standard; obsidian-linter-alignment reference → standard)
- [x] T024 Validate no files retain legacy values (strategy, charter, note, policy) in doc_type

### Implementation Notes

Per research.md §2 misclassification table. Files project-charter.md, decision-log.md, risk-register.md, vision-framework.md, standards-readme.md are already correct — no changes needed.

### Parallel Opportunities

T020, T021, T023 parallel-safe.

### Dependencies

- WP01 (cite Divio standard)

### Risks & Mitigations

- `strategic-acceleration-charter.md` is an edge case — "charter" is strategic intent. Classifying as `explanation` is defensible but could alternatively retain `charter` as a sub-type. Deciding to reclassify as `explanation` to align with the canonical enum.

---

## Work Package WP07: Create docs/INDEX.md Master Map (Priority: P0)

**Goal**: Author `docs/INDEX.md` as the master documentation map covering every active directory, its purpose, the Divio types it contains, and its key documents.
**Independent Test**: `docs/INDEX.md` exists, lists every active directory under `docs/`, names at least one key document per directory, and is the single reachable entry point for all active docs.
**Prompt**: `tasks/WP07-create-index-md.md`
**Requirement Refs**: FR-008, NFR-001, NFR-004

### Included Subtasks

- [x] T025 Create `docs/INDEX.md` with frontmatter, overview, and usage guidance
- [x] T026 Add Constitution + Governance section (docs/constitution/, CLAUDE.md refs)
- [x] T027 Add System Architecture section (docs/design/architecture/ + data/, schemas, machine-readable home)
- [x] T028 Add Operational Runbooks section (docs/runbooks/, grouped by agent-executable vs human-only)
- [x] T029 Add Design + Standards section (docs/design/ top-level, docs/design/standards/, docs/design/research/)
- [x] T030 Add Feature Specifications + Diagnostics/Postmortems sections (docs/func-spec/, docs/issues/, docs/postmortems/)
- [x] T031 Verify every active doc is reachable in ≤3 hops from CLAUDE.md via INDEX.md

### Implementation Notes

Grouping by directory context (not pure Divio type) per data-model.md §8. Each entry shows: `[title](path) — doc_type (audience if runbook)`.

### Parallel Opportunities

T026–T030 can be drafted in parallel after T025.

### Dependencies

- WP01, WP02, WP03, WP04, WP05, WP06 (all frontmatter/moves must be complete so INDEX is accurate)

### Risks & Mitigations

- INDEX.md becomes stale quickly. Mitigated by WP09 (change-control protocol update makes INDEX.md maintenance mandatory).

---

## Work Package WP08: Update CLAUDE.md + AI Agent Instructions (Priority: P0)

**Goal**: Add references from CLAUDE.md to INDEX.md, Felix constitution, and the machine-readable artifact home. Update all `personal-ai-system-spec-v03.md` references to point to `v1.0.md`.
**Independent Test**: CLAUDE.md references `docs/INDEX.md`, `docs/constitution/FELIX-CONSTITUTION.md`, and `docs/design/architecture/data/`. All v03 references in CLAUDE.md and ai-agents/* point to v1.0.
**Prompt**: `tasks/WP08-update-claude-md.md`
**Requirement Refs**: FR-009, NFR-001

### Included Subtasks

- [x] T032 Add CLAUDE.md section referencing `docs/INDEX.md` as the documentation map
- [x] T033 Add CLAUDE.md reference to `docs/constitution/FELIX-CONSTITUTION.md` and `docs/design/architecture/data/` as canonical machine-readable home
- [x] T034 Update CLAUDE.md: `personal-ai-system-spec-v03.md` → `personal-ai-system-spec-v1.0.md` (2 occurrences)
- [x] T035 Update `ai-agents/claude-code-instructions.md` and `ai-agents/claude-instructions.md`: v03 → v1.0 references

### Implementation Notes

CLAUDE.md is the AI agent's primary entry point. Keep new sections concise; don't bloat.

### Parallel Opportunities

T032, T033 can be combined. T034 and T035 can be done in parallel.

### Dependencies

- WP07 (INDEX.md must exist to be referenced)

### Risks & Mitigations

- CLAUDE.md is already large; new sections must be concise and well-placed.

---

## Work Package WP09: Update Architecture README + Change-Control Protocol (Priority: P1)

**Goal**: Document `docs/design/architecture/data/` as the canonical home for machine-readable artifacts in the architecture README, and add `docs/INDEX.md` maintenance to the change-control protocol.
**Independent Test**: Architecture README states `docs/design/architecture/data/` as canonical data home; change-control.md requires INDEX.md updates on every feature.
**Prompt**: `tasks/WP09-update-architecture-readme-change-control.md`
**Requirement Refs**: FR-006, FR-007, FR-011

### Included Subtasks

- [x] T036 Update `docs/design/architecture/README.md` with canonical machine-readable artifact home statement
- [x] T037 Update `docs/design/architecture/change-control.md` to require `docs/INDEX.md` updates on every feature
- [x] T038 Document schema co-location convention (schemas live with or link to the data they describe)

### Implementation Notes

Preserve existing README and change-control structure; additions only.

### Parallel Opportunities

T036, T037, T038 parallel-safe.

### Dependencies

- WP07 (INDEX.md must exist to reference in change-control protocol)

### Risks & Mitigations

- change-control.md is an authoritative doc. Changes must be additive, not destructive.

---

## Work Package WP10: Resolve F016 Path Dependencies (Priority: P1)

**Goal**: Update the F016 feature spec with resolved paths for governance files, postmortems, and change risk taxonomy, removing all TBD notations.
**Independent Test**: `docs/func-spec/F016_change_control_governance.md` contains no TBD markers; all path references resolve to existing directories.
**Prompt**: `tasks/WP10-resolve-f016-paths.md`
**Requirement Refs**: FR-012

### Included Subtasks

- [ ] T039 Replace F016 TBD paths with resolved values: governance → `docs/runbooks/governance/`, postmortems → `docs/postmortems/`, change risk taxonomy → `docs/design/architecture/data/`
- [ ] T040 Verify F016 spec is ready for spec-kitty (no TBD markers remain)

### Implementation Notes

F016 is a future feature spec; we update it but don't implement it. This unblocks F016 from entering spec-kitty.

### Dependencies

None — paths are known from directory structure.

### Risks & Mitigations

- F016 might have additional path assumptions we don't catch. Mitigated by grep for "TBD" after edit.

---

## Work Package WP11: Archive docs-readme.md + Update Historical Spec References (Priority: P2)

**Goal**: Archive the stale `docs/docs-readme.md` (replaced by INDEX.md) and update historical spec references that point to moved/deprecated files.
**Independent Test**: `docs/docs-readme.md` no longer exists at original path; archived copy at `docs/archive/docs-readme.md` has `status: archived`. F002 spec references to `office2-backup-and-security.md` use new path.
**Prompt**: `tasks/WP11-archive-docs-readme-historical-refs.md`
**Requirement Refs**: FR-010, FR-013, NFR-003

### Included Subtasks

- [ ] T041 `git mv docs/docs-readme.md docs/archive/docs-readme.md` and update frontmatter (status: archived, superseded_by: docs/INDEX.md)
- [ ] T042 Update `docs/func-spec/F002_openclaw_install.md` references to `office2-backup-and-security.md` → new path (2 occurrences)
- [ ] T043 Verify no active (non-archived) doc references the original `docs/docs-readme.md` path

### Implementation Notes

Historical func-specs for F001, F002, F005 reference `personal-ai-system-spec-v03.md`. These are historical artifacts; we do NOT rewrite them except where a path is literally broken (F002's office2-backup ref after the move). v03 refs remain valid because v03 is deprecated-not-deleted.

### Dependencies

- WP07 (INDEX.md must exist to be the supersession target)
- WP02 (new path for office2-backup-and-security.md)

### Risks & Mitigations

- Over-eager rewriting of historical specs creates churn with no value. Mitigated by narrowly scoping to broken refs only.

---

## Work Package Execution Order

**Parallel starters (Phase 0)**: WP01, WP02, WP05, WP10

**After Phase 0 (Phase 1)**:
- WP03 (depends on WP01 + WP02)
- WP04 (depends on WP02)
- WP06 (depends on WP01)

**After Phase 1 (Phase 2)**:
- WP07 (depends on WP01–WP06)

**After Phase 2 (Phase 3)**:
- WP08 (depends on WP07)
- WP09 (depends on WP07)
- WP11 (depends on WP07 + WP02)

## MVP Scope Recommendation

**Minimum viable F015**: WP01 + WP07 + WP08 delivers the chain-of-reference (INDEX.md + CLAUDE.md refs + Divio standards doc). Everything else is quality improvements. However, ALL WPs are in scope per the spec.

## Size Validation

All 11 WPs estimated at 100–385 lines, all within the 200–500 ideal range or slightly below. None exceed 700 lines. ✓

| WP | Subtasks | Est. Lines |
|---|---|---|
| WP01 | 4 | ~240 |
| WP02 | 3 | ~150 |
| WP03 | 6 | ~350 |
| WP04 | 3 | ~180 |
| WP05 | 3 | ~135 |
| WP06 | 5 | ~275 |
| WP07 | 7 | ~385 |
| WP08 | 4 | ~240 |
| WP09 | 3 | ~165 |
| WP10 | 2 | ~110 |
| WP11 | 3 | ~165 |

Total: 43 subtasks across 11 WPs.
