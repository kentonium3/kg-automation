---
title: "F015: Documentation Architecture Rationalization"
doc_type: spec
status: draft
feature: 015-documentation-architecture-rationalization
mission: documentation
---

# Feature Specification: Documentation Architecture Rationalization

## Overview

The kg-automation repository has accumulated documentation across multiple directories that grew organically without a unifying structure. Many documents are unreferenced from CLAUDE.md or the Felix constitution, making them undiscoverable by agents and difficult to maintain. The machine-readable artifact home is split and underdocumented. The distinction between runbooks (prescriptive, action-oriented) and reference/explanation docs is not enforced, making it unclear what an agent should execute versus read for context.

This feature classifies every active document against the Divio 4-type framework, establishes a master `docs/INDEX.md` as the chain-of-reference anchor, enforces the runbook-vs-reference distinction, documents the canonical home for machine-readable operational artifacts, and resolves the path dependencies that currently block F016.

Physical directory restructuring (renaming `handbooks/` to `runbooks/`, moving `research/` under `docs/design/`, creating `runbooks/governance/` and `postmortems/`, archiving orphaned directories) has already been completed as an out-of-cycle prerequisite task. This spec assumes that structure is in place.

## User Scenarios & Testing

### Primary Scenario: Agent Receives a New Task

**Actor**: A Claude Code agent (or any AI agent) invoked to work on a kg-automation task.

**Flow**:
1. Agent reads `CLAUDE.md` at repo root as its starting context.
2. Agent follows a reference in `CLAUDE.md` to `docs/INDEX.md` (the master documentation map).
3. From `INDEX.md`, agent navigates to the appropriate directory based on task type: runbook for a prescriptive operation, architecture reference for system context, constitution for governance boundaries, postmortem for prior-incident context.
4. Every active document the agent needs is reachable via this chain — no orphaned docs.
5. Each document's `doc_type` frontmatter matches its actual content (how-to, reference, explanation), so the agent knows whether to execute steps or absorb as context.

**Success**: Agent can reach any active document from `CLAUDE.md` in ≤3 link hops, and the document's type is unambiguous from its frontmatter.

### Secondary Scenario: Human Operator Adds a New Document

**Actor**: Kent, adding a new runbook, reference doc, or postmortem.

**Flow**:
1. Operator identifies the document's Divio type (how-to, reference, explanation).
2. Operator places it in the correct canonical home per `INDEX.md` (one home per artifact type).
3. Operator updates `INDEX.md` to list the new document — enforced by the change-control protocol.
4. The chain-of-reference remains complete; no orphaned docs created.

**Success**: No document lands outside its canonical home, and `INDEX.md` is updated in the same change.

### Tertiary Scenario: F016 Unblocked

**Actor**: Whoever initiates `/spec-kitty.specify` for F016 after F015 acceptance.

**Flow**:
1. F016 spec has resolved paths (no TBD notations) for governance files, postmortems, and change risk taxonomy.
2. F016 can proceed straight into planning without a path-decision gate.

**Success**: F016 spec document has all paths resolved; no TBD markers remain.

### Edge Cases

- **Borderline classification**: A document that is 60% how-to and 40% reference — dominant type wins, ambiguity noted in frontmatter.
- **Stale/orphaned doc not in `INDEX.md`**: Treated as not-active — either classified and indexed, or archived.
- **`docs/issues/diagnostics/` exemption**: Actively used at runtime; exempt from any archival or restructuring.
- **Broken reference discovered during audit**: All inbound references (CLAUDE.md, func-spec/, ai-agents/) updated as part of this feature, not deferred.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Classify every active document in `docs/` against Divio 4-type framework (how-to, reference, explanation; tutorials absent by design). | Draft |
| FR-002 | Produce a gap analysis that identifies missing coverage by type, misclassified documents, and duplicate coverage. | Draft |
| FR-003 | Within `docs/runbooks/`, enforce the distinction between runbook content (prescriptive, step-by-step, executable) and reference/explanation/standard content. Move misclassified content to its canonical home per Divio type: `docs/design/architecture/` (architecture reference), `docs/design/` top-level (design rationale / explanation), `docs/design/standards/` (cross-cutting standards), or `docs/constitution/` (governance) as appropriate. | Draft |
| FR-004 | Correct the `doc_type` frontmatter on every file in `docs/runbooks/`: replace the legacy `handbook` value with a canonical Divio-aligned value — one of `runbook`, `reference`, `explanation`, or a named sub-type (`spec`, `standard`, `postmortem`, `diagnostic`, `readme`) — per classification. Sub-types are Divio extensions for specific artifact categories and do NOT expand the Divio parent taxonomy. | Draft |
| FR-005 | Add an `audience` frontmatter field to each runbook declaring `human-only`, `agent-executable`, or `both`; flag agent-executable runbooks for future skill conversion. | Draft |
| FR-006 | Document `docs/design/architecture/data/` as the canonical home for all current-state operational machine-readable artifacts (service inventory, network topology, credentials, etc.). | Draft |
| FR-007 | Co-locate schema files alongside the JSON data they describe within `docs/design/architecture/data/`, or clearly link them if located elsewhere. | Draft |
| FR-008 | Create `docs/INDEX.md` as the master documentation map covering every active directory, its purpose, the Divio types it contains, and its key documents (both markdown and machine-readable). | Draft |
| FR-009 | Update `CLAUDE.md` to explicitly reference `docs/INDEX.md` and `docs/constitution/FELIX-CONSTITUTION.md`. | Draft |
| FR-010 | Archive `docs/docs-readme.md` (moved to `docs/archive/`) after `docs/INDEX.md` supersedes it. | Draft |
| FR-011 | Update `docs/design/architecture/change-control.md` to require `INDEX.md` updates whenever a document or directory is added, moved, or removed. | Draft |
| FR-012 | Update the F016 spec (`docs/func-spec/F016_change_control_governance.md`) with resolved paths for governance files (`docs/runbooks/governance/`), postmortems (`docs/issues/postmortems/`), and change risk taxonomy (`docs/design/architecture/data/`); remove all TBD notations. | Draft |
| FR-013 | Audit all inbound references to moved or renamed paths (CLAUDE.md, `docs/func-spec/*`, `ai-agents/*`, any script or workflow) and update them in the same feature branch — no broken references remain. | Draft |

### Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-001 | After acceptance, every active document is reachable from `CLAUDE.md` or `docs/constitution/FELIX-CONSTITUTION.md` via ≤3 link hops. | Draft |
| NFR-002 | After acceptance, 100% of files in `docs/runbooks/` have a non-empty `doc_type` frontmatter value drawn from the set `{runbook, reference, explanation}`. | Draft |
| NFR-003 | After acceptance, the feature branch contains zero broken internal links (link-check over `docs/`, `CLAUDE.md`, `ai-agents/`, `.claude/`, `kitty-specs/` returns 0 errors for moved paths). | Draft |
| NFR-004 | `docs/INDEX.md` references every active directory under `docs/` and names at least one key document per directory. | Draft |

### Constraints

| ID | Requirement | Status |
|---|---|---|
| C-001 | No files in `docs/design/architecture/data/` are moved, renamed, or deleted — this feature is policy documentation only for that path. | Draft |
| C-002 | `docs/issues/diagnostics/` is not restructured, archived, or reclassified — it is actively used at runtime. | Draft |
| C-003 | Content is moved, never deleted; `git mv` used for all moves so history is preserved. | Draft |
| C-004 | No changes to `.github/workflows/` CI configuration without explicit instruction. | Draft |
| C-005 | No writes to `~/second-brain/` paths; this feature operates entirely within the kg-automation repo. | Draft |
| C-006 | No new tooling, CI link-checker, or automated validator introduced — those are explicitly out of scope. | Draft |
| C-007 | Divio classification uses the internal-audience mapping: how-to = runbook (+ diagnostic sub-type), reference = architecture/CLAUDE.md/spec sub-type, explanation = constitution/ADR/postmortem/standard; tutorials absent by design. The canonical doc_type enum and sub-type definitions are authoritative in `docs/design/standards/divio-classification.md` (produced by WP01). | Draft |

## Success Criteria

- **Classification complete**: Every active document in `docs/` has a correct `doc_type` frontmatter value; a gap-analysis artifact enumerates missing, misclassified, and duplicate coverage.
- **Master index in place**: `docs/INDEX.md` exists, covers every active directory, and is explicitly referenced from `CLAUDE.md`.
- **Chain of reference complete**: Every active document is reachable in ≤3 hops from `CLAUDE.md` or the Felix constitution.
- **Runbook discipline enforced**: All files in `docs/runbooks/` are either executable step-by-step procedures with audience declared, or have been moved to a non-runbook home.
- **Machine-readable home documented**: `docs/design/architecture/data/` is documented as the canonical home in the architecture README, `CLAUDE.md`, and `docs/INDEX.md`.
- **F016 unblocked**: F016 spec contains resolved paths with no TBD notations.
- **Zero broken references**: No inbound reference to a moved or renamed path is left broken on the feature branch.
- **Change-control protocol updated**: `INDEX.md` maintenance is an explicit requirement in `docs/design/architecture/change-control.md`.

## Key Entities

- **Active Document**: A markdown or JSON file under `docs/` (excluding `archive/`) that an agent or human consults during current operations. Classified by Divio type via `doc_type` frontmatter.
- **Divio Type**: Three parent types — `runbook` (how-to), `reference`, `explanation` — plus four named sub-types that extend them for specific artifact categories: `spec` (reference sub-type), `standard` (explanation sub-type), `postmortem` (explanation sub-type), `diagnostic` (how-to sub-type), and `readme` (reference sub-type). `tutorial` is absent by design for a solo-operator system.
- **Canonical Home**: The single directory that owns a given artifact type — e.g., all runbooks in `docs/runbooks/`, all operational JSON in `docs/design/architecture/data/`, all postmortems in `docs/issues/postmortems/`, all diagnostics in `docs/issues/diagnostics/`.
- **Chain of Reference**: The sequence of links from `CLAUDE.md` → `INDEX.md` → specific document that makes every active doc discoverable by an agent.
- **Gap Analysis**: A produced artifact listing missing coverage by Divio type, misclassified documents, and duplicate coverage across directories.

## Assumptions

1. **Prerequisite restructuring is complete**: `handbooks/` has already been renamed to `runbooks/`, `research/` is under `docs/design/`, `docs/runbooks/governance/` exists, `docs/issues/` consolidates `docs/issues/diagnostics/` and `docs/issues/postmortems/` under a single parent, orphaned directories are archived, and `workflows/` content is migrated. This was done as Claude Code out-of-cycle tasks prior to this spec.
2. **`docs/docs-readme.md` is the basis for `INDEX.md`**: Its intent is captured in the new INDEX.md; the old file is archived, not deleted.
3. **Divio framework fits internal-audience needs**: The 4-type framework (minus tutorials) is sufficient to classify all active docs; no fifth type is needed.
4. **All content moves are reference-safe**: The planning phase will audit all inbound references before content is moved, so no feature work results in broken links.
5. **F016 spec is editable**: Updating F016 paths in this feature does not require a separate spec-kitty flow for F016 itself.
6. **Manual validation is sufficient**: No automated link-checker or CI gate is introduced — correctness is verified by manual review of the gap analysis and by reading `INDEX.md` end-to-end.
7. **`docs/diagnostics/` content classification is deferred**: It is exempt from archival but its individual files' frontmatter may still be reviewed if needed — the exemption is about structure, not content discipline.

## Out of Scope

- Writing new documentation to fill gaps identified by the gap analysis — that is future work.
- Converting runbooks to agent skills — only flagging for future conversion.
- F016 implementation — this feature resolves F016's path dependencies; F016 runs after F015 acceptance.
- Automated doc validation, CI link-checking, frontmatter schema enforcement — a separate feature.
- Any changes to `docs/design/architecture/data/` contents (JSON files, schemas) — policy documentation only.
- Any work inside `docs/diagnostics/` beyond incidental frontmatter review.
- Changes outside `docs/`, `CLAUDE.md`, `ai-agents/`, and `docs/func-spec/F016_*` (F016 spec path updates).

## Dependencies

- **Prerequisite (completed)**: Physical restructuring of `docs/` subdirectories — Claude Code out-of-cycle task.
- **Downstream (unblocked by this feature)**: F016 — Change Control Governance, which needs resolved paths for governance files, postmortems, and change risk taxonomy.

## Notes

- Planning phase should audit all `docs/handbooks/` and `docs/runbooks/` references in `CLAUDE.md`, `docs/func-spec/`, `ai-agents/`, `.claude/`, `kitty-specs/` before authorizing any content moves.
- Study `docs/design/architecture/change-control.md` before modifying it (FR-011).
- Study the Felix constitution tone and structure before adding any documentation-standards content to it (if the classification work surfaces the need).
- `INDEX.md` quality is the primary deliverable — it determines whether chain-of-reference is solved.
- FR-012 (F016 path resolution) is a hard dependency for the next feature in sequence.
