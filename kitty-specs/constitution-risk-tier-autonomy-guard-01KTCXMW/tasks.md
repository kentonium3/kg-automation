# Tasks: Constitution Risk-Tier Autonomy Guard

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `quickstart.md`
**Branch**: planning base `main`; merge target `main`
**Generated**: 2026-06-06T00:37:37Z

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Locate the Directive 2 insertion point and preserve existing autonomy semantics. | WP01 |  | [D] |
| T002 | Add concise constitution wording binding autonomy to risk-tier gates. | WP01 |  | [D] |
| T003 | Reference the canonical risk taxonomy JSON from the constitution. | WP01 |  | [D] |
| T004 | Verify the constitution text covers Tier 0 and Tier 1/2 obligations without duplicating the taxonomy table. | WP01 |  | [D] |
| T005 | Inspect `CLAUDE.md` for consistency with the new constitution wording. | WP02 |  |
| T006 | Inspect `.kittify/charter/charter.md` for consistency with the new constitution wording. | WP02 |  |
| T007 | Inspect `docs/design/architecture/change-control.md` for consistency with the new constitution wording. | WP02 |  |
| T008 | Run documentation validation and targeted requirement checks. | WP02 |  |

## Work Packages

### WP01 — Constitution Autonomy/Risk Amendment

**Prompt**: `tasks/WP01-constitution-autonomy-risk-amendment.md`
**Priority**: P1
**Dependencies**: None
**Independent test**: Inspect `docs/constitution/FELIX-CONSTITUTION.md` and confirm FR-001 through FR-005 are satisfied.

**Summary**: Amend Directive 2 in the Felix Constitution so autonomy level cannot be misread as permission to bypass deployed-change risk-tier controls.

**Included subtasks**

- [x] T001 Locate the Directive 2 insertion point and preserve existing autonomy semantics.
- [x] T002 Add concise constitution wording binding autonomy to risk-tier gates.
- [x] T003 Reference the canonical risk taxonomy JSON from the constitution.
- [x] T004 Verify the constitution text covers Tier 0 and Tier 1/2 obligations without duplicating the taxonomy table.

**Implementation sketch**

1. Read Directive 2 in `docs/constitution/FELIX-CONSTITUTION.md`.
2. Add a short paragraph or subsection after the autonomy level definitions and before promotion rules.
3. Keep wording principle-level: autonomy controls activity surfacing and execution posture; risk tiers control deployed-change gates.
4. Link to `docs/design/architecture/data/change-risk-taxonomy.json`.
5. Verify the amendment states Tier 0 is operator-only and Tier 1/Tier 2 gates remain required where applicable.

**Parallel opportunities**: None within this WP; one file should be edited coherently.
**Risks**: Overstating the amendment into a new autonomy model; duplicating the full tier table; weakening existing promotion/demotion rules.

### WP02 — Companion Consistency and Validation

**Prompt**: `tasks/WP02-companion-consistency-validation.md`
**Priority**: P2
**Dependencies**: WP01
**Independent test**: `python tooling/scripts/validate_docs.py` passes and targeted `rg` checks confirm required wording is discoverable.

**Summary**: Check the companion governance documents named in the spec against the amended constitution, make only concrete consistency fixes if needed, and run validation.

**Included subtasks**

- [ ] T005 Inspect `CLAUDE.md` for consistency with the new constitution wording.
- [ ] T006 Inspect `.kittify/charter/charter.md` for consistency with the new constitution wording.
- [ ] T007 Inspect `docs/design/architecture/change-control.md` for consistency with the new constitution wording.
- [ ] T008 Run documentation validation and targeted requirement checks.

**Implementation sketch**

1. Compare the WP01 amendment to the existing risk-tier sections in the companion docs.
2. Leave companion docs unchanged unless there is a concrete inconsistency with the new constitution wording.
3. If a companion doc is changed, keep edits narrow and preserve its existing role.
4. Run `python tooling/scripts/validate_docs.py`.
5. Run a targeted `rg` inspection over the constitution for autonomy, risk-tier, taxonomy, Tier 0, Tier 1, and Tier 2 language.

**Parallel opportunities**: Companion-document inspection can be done independently after WP01 is complete.
**Risks**: Creating churn in already-correct context docs; changing `.kittify/charter/charter.md` without a concrete inconsistency.

## Dependency Notes

- WP02 depends on WP01 because consistency review needs the final constitution wording.
- No work package owns overlapping files.
- No production deployment, office2 mutation, backup, or service pre-flight is required.

## MVP Recommendation

WP01 is the functional MVP. WP02 is required for acceptance because FR-006 and SC-004 require companion-doc consistency evidence.
