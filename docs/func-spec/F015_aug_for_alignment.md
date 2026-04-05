---
title: "F015 Augmentation — Spec/Plan/Tasks Alignment Edits"
doc_type: reference
status: draft
---

# F015 Augmentation: Spec/Plan/Tasks Alignment Edits

**Purpose**: Input document for `/spec-kitty.specify` refinement of F015. Resolves three issues identified during `/spec-kitty.analyze`:

- **I1 (CRITICAL)**: Spec path references (`docs/diagnostics/`, `docs/postmortems/`) are stale; filesystem now uses `docs/issues/diagnostics/` and `docs/issues/postmortems/`.
- **C1 (HIGH)**: Spec authorizes 3 `doc_type` values (`runbook`, `reference`, `explanation`) but plan/data-model/tasks introduce 4 additional named sub-types (`spec`, `standard`, `postmortem`, `diagnostic`, `readme`) that are not in the spec's enum.
- **I3 (HIGH)**: FR-003 authorizes moves only to `docs/design/architecture/` or `docs/constitution/`, but WP02 moves to `docs/design/` top-level and `docs/design/standards/` — not in the authorized list.

These edits update the spec to match what the plan and tasks already build. After applying, re-run `/spec-kitty.plan` → `/spec-kitty.tasks` → `/spec-kitty.analyze` to verify convergence.

**Scope**: Apply 9 edits to `kitty-specs/015-documentation-architecture-rationalization/spec.md`. No other files are modified by this refinement.

---

## I1 — Path Inconsistency (CRITICAL) — 5 edits

### Edit I1.1 — Constraint C-002 path

**FROM**:

> `docs/diagnostics/` is not restructured, archived, or reclassified — it is actively used at runtime.

**TO**:

> `docs/issues/diagnostics/` is not restructured, archived, or reclassified — it is actively used at runtime.

### Edit I1.2 — Edge case exemption

**FROM**:

> **`docs/diagnostics/` exemption**: Actively used at runtime; exempt from any archival or restructuring.

**TO**:

> **`docs/issues/diagnostics/` exemption**: Actively used at runtime; exempt from any archival or restructuring.

### Edit I1.3 — FR-012 path

**FROM**:

> Update the F016 spec (`docs/func-spec/F016_change_control_governance.md`) with resolved paths for governance files (`docs/runbooks/governance/`), postmortems (`docs/postmortems/`), and change risk taxonomy (`docs/design/architecture/data/`); remove all TBD notations.

**TO**:

> Update the F016 spec (`docs/func-spec/F016_change_control_governance.md`) with resolved paths for governance files (`docs/runbooks/governance/`), postmortems (`docs/issues/postmortems/`), and change risk taxonomy (`docs/design/architecture/data/`); remove all TBD notations.

### Edit I1.4 — Key Entities "Canonical Home"

**FROM**:

> **Canonical Home**: The single directory that owns a given artifact type — e.g., all runbooks in `docs/runbooks/`, all operational JSON in `docs/design/architecture/data/`, all postmortems in `docs/postmortems/`.

**TO**:

> **Canonical Home**: The single directory that owns a given artifact type — e.g., all runbooks in `docs/runbooks/`, all operational JSON in `docs/design/architecture/data/`, all postmortems in `docs/issues/postmortems/`, all diagnostics in `docs/issues/diagnostics/`.

### Edit I1.5 — Assumption 1 (prerequisite restructuring)

**FROM**:

> **Prerequisite restructuring is complete**: `handbooks/` has already been renamed to `runbooks/`, `research/` is under `docs/design/`, `runbooks/governance/` and `postmortems/` exist, orphaned directories are archived, and `workflows/` content is migrated. This was done as a Claude Code out-of-cycle task prior to this spec.

**TO**:

> **Prerequisite restructuring is complete**: `handbooks/` has already been renamed to `runbooks/`, `research/` is under `docs/design/`, `docs/runbooks/governance/` exists, `docs/issues/` consolidates `docs/issues/diagnostics/` and `docs/issues/postmortems/` under a single parent, orphaned directories are archived, and `workflows/` content is migrated. This was done as Claude Code out-of-cycle tasks prior to this spec.

---

## C1 — doc_type Enum Expansion (HIGH) — 3 edits

### Edit C1.1 — FR-004 expanded enum

**FROM**:

> Correct the `doc_type` frontmatter on every file in `docs/runbooks/`: replace the legacy `handbook` value with one of `runbook`, `reference`, or `explanation` per classification.

**TO**:

> Correct the `doc_type` frontmatter on every file in `docs/runbooks/`: replace the legacy `handbook` value with a canonical Divio-aligned value — one of `runbook`, `reference`, `explanation`, or a named sub-type (`spec`, `standard`, `postmortem`, `diagnostic`, `readme`) — per classification. Sub-types are Divio extensions for specific artifact categories and do NOT expand the Divio parent taxonomy.

### Edit C1.2 — Key Entities "Divio Type"

**FROM**:

> **Divio Type**: One of `runbook` (how-to), `reference`, `explanation`; `tutorial` is absent by design for a solo-operator system.

**TO**:

> **Divio Type**: Three parent types — `runbook` (how-to), `reference`, `explanation` — plus four named sub-types that extend them for specific artifact categories: `spec` (reference sub-type), `standard` (explanation sub-type), `postmortem` (explanation sub-type), `diagnostic` (how-to sub-type), and `readme` (reference sub-type). `tutorial` is absent by design for a solo-operator system.

### Edit C1.3 — Constraint C-007 clarification

**FROM**:

> Divio classification uses the internal-audience mapping: how-to = runbook, reference = architecture/CLAUDE.md, explanation = constitution/ADR/postmortem; tutorials absent by design.

**TO**:

> Divio classification uses the internal-audience mapping: how-to = runbook (+ diagnostic sub-type), reference = architecture/CLAUDE.md/spec sub-type, explanation = constitution/ADR/postmortem/standard; tutorials absent by design. The canonical doc_type enum and sub-type definitions are authoritative in `docs/design/standards/divio-classification.md` (produced by WP01).

---

## I3 — Move Destinations (HIGH) — 1 edit

### Edit I3.1 — FR-003 expanded destinations

**FROM**:

> Within `docs/runbooks/`, enforce the distinction between runbook content (prescriptive, step-by-step, executable) and reference/explanation content; move misclassified content to `docs/design/architecture/` or `docs/constitution/` as appropriate.

**TO**:

> Within `docs/runbooks/`, enforce the distinction between runbook content (prescriptive, step-by-step, executable) and reference/explanation/standard content. Move misclassified content to its canonical home per Divio type: `docs/design/architecture/` (architecture reference), `docs/design/` top-level (design rationale / explanation), `docs/design/standards/` (cross-cutting standards), or `docs/constitution/` (governance) as appropriate.

---

## Out-of-Scope for This Refinement

The following were identified in `/spec-kitty.analyze` but are NOT covered by this augmentation:

- **A1 (TEST_FIRST exception)** — user accepted the current N/A handling; no formal Exception Policy record needed.
- **I2 (constitution stale `docs/handbooks/` path)** — constitution changes are explicitly out of scope for F015; handle in a separate constitution sync.
- **C2 (validate_docs.py coverage)** — deferred to user decision.
- **U1, U2, T1, I4, C3, D1, A2, S1** — MEDIUM/LOW severity, not blocking.

---

## How to Apply

Option A — Feed this file as refinement input to `/spec-kitty.specify`:

```text
Refine F015 spec using the 9 alignment edits in docs/func-spec/F015_aug_for_alignment.md.
Apply all edits in I1, C1, and I3 sections. After edits, revise any dependent sections
(Success Criteria, Notes) so they remain consistent with the updated requirements.
```

Option B — Apply manually via Edit tool against `kitty-specs/015-documentation-architecture-rationalization/spec.md` using the find/replace pairs above.

After applying, re-run `/spec-kitty.plan` and `/spec-kitty.tasks` to regenerate planning artifacts aligned with the corrected spec. Then re-run `/spec-kitty.analyze` to verify no HIGH or CRITICAL findings remain.
