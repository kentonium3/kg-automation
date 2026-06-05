# Implementation Plan: Constitution Risk-Tier Autonomy Guard
*Path: kitty-specs/constitution-risk-tier-autonomy-guard-01KTCXMW/plan.md*

**Branch**: `main` | **Date**: 2026-06-05 | **Spec**: `kitty-specs/constitution-risk-tier-autonomy-guard-01KTCXMW/spec.md`
**Input**: Feature specification from `kitty-specs/constitution-risk-tier-autonomy-guard-01KTCXMW/spec.md`

## Summary

Amend `docs/constitution/FELIX-CONSTITUTION.md` so Directive 2 explicitly
states that agent autonomy level controls activity surfacing and routine
execution posture, not permission to bypass deployed-change risk-tier gates.
The constitution will reference the canonical Tier 0-4 taxonomy JSON and name
the Tier 0, Tier 1, and Tier 2 guardrails at principle level without duplicating
the full taxonomy table.

## Technical Context

**Language/Version**: Markdown documentation; JSON taxonomy reference only.  
**Primary Dependencies**: Felix Constitution, change-risk taxonomy, companion governance docs.  
**Storage**: Repository documentation files only.  
**Testing**: `python tooling/scripts/validate_docs.py`; targeted text inspection for required phrases and references.  
**Target Platform**: kg-automation repository governance documentation.  
**Project Type**: Documentation/governance amendment.  
**Performance Goals**: N/A.  
**Constraints**: Tier 4 documentation/governance change; no production deployment, no office2 mutation, no taxonomy change.  
**Scale/Scope**: One constitution amendment plus consistency checks of named companion docs.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Risk tier**: Tier 4, schema/metadata/governance documentation. No pre-flight,
  backup, production deployment, or office2 mutation required.
- **Canonical source rule**: Pass. The implementation will reference
  `docs/design/architecture/data/change-risk-taxonomy.json` instead of copying
  the full tier table into the constitution.
- **Scope discipline**: Pass. Implementation is limited to
  `docs/constitution/FELIX-CONSTITUTION.md` unless concrete inconsistency is
  found in `CLAUDE.md`, `.kittify/charter/charter.md`, or
  `docs/design/architecture/change-control.md`.
- **Validation**: Pass with documentation validator and targeted requirement
  checks.

## Project Structure

### Documentation (this feature)

```
kitty-specs/constitution-risk-tier-autonomy-guard-01KTCXMW/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── README.md
└── tasks/
```

### Source Code (repository root)

```
docs/
├── constitution/
│   └── FELIX-CONSTITUTION.md
└── design/
    └── architecture/
        ├── change-control.md
        └── data/
            └── change-risk-taxonomy.json

CLAUDE.md
.kittify/charter/charter.md
```

**Structure Decision**: Use the existing governance documentation structure.
Primary implementation belongs in the Felix Constitution near Directive 2.
Companion docs are verification targets and should be edited only if the
implementation review finds a concrete inconsistency.

## Phase 0: Research

See `research.md`.

## Phase 1: Design

See `data-model.md`, `contracts/README.md`, and `quickstart.md`.

## Complexity Tracking

No charter violations or additional complexity are planned.
