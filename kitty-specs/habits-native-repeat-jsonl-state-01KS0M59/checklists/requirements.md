# Specification Quality Checklist: Habits native repeat + JSONL state

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-19
**Feature**: [spec.md](../spec.md)

## Content Quality

- [~] No implementation details (languages, frameworks, APIs) — *known tension; see Notes*
- [x] Focused on user value and business needs (Kent's morning check-in MWF workout failure motivates the migration; consumer agent value tracked via downstream phases)
- [~] Written for non-technical stakeholders — *known tension; appropriate for foundation migration where the stakeholder is also the operator*
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Requirement types are separated (Functional / Non-Functional / Constraints)
- [x] IDs are unique across FR-###, NFR-###, and C-### entries (FR-001..FR-014, NFR-001..NFR-006, C-001..C-007)
- [x] All requirement rows include a non-empty Status value (all "Active")
- [x] Non-functional requirements include measurable thresholds (NFR-001: <30s, NFR-002: <5s p95, NFR-003: <60s, NFR-004: <5min, NFR-005: ≥85%, NFR-006: 0 new deps)
- [x] Success criteria are measurable
- [~] Success criteria are technology-agnostic — *partial: SC-001/SC-002/SC-003 cite Vikunja API fields (`repeat_after`, `done`) that come from ADR-0002 architectural decisions, not arbitrary implementation choices*
- [x] All acceptance scenarios are defined (6 scenarios covering migration, completion, backfill, drift detection, dry-run/smoke, rollback)
- [x] Edge cases are identified (workout task identification deferred to plan, drift detection, partial-write recovery via reconcile)
- [x] Scope is clearly bounded (Out of scope explicit; constraints lock down what does NOT change)
- [x] Dependencies and assumptions identified (6 assumptions)

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria (mapped via Success Criteria)
- [x] User scenarios cover primary flows (operator migration + agent completion + UI backfill + rollback)
- [x] Feature meets measurable outcomes defined in Success Criteria
- [~] No implementation details leak into specification — *known tension; see Notes*

## Notes

**Known tension on "no implementation details" items**:

This is a production-state migration where the architectural decisions (config-driven YAML schema, JSONL state log location, three-write atomicity, retired-via-done-true) come directly from ADR-0002 — they ARE the design, not arbitrary implementation choices. The spec template's "no implementation details" rule assumes a user-facing feature with separate business and engineering stakeholders. For this mission both roles collapse onto Kent + the LLM implementer.

**Open lookup deferred to plan phase**: the exact Vikunja task ID for the current single "Workout" task is unknown to this spec. The plan phase will run a Vikunja query, identify the task, and update `habits-schedule.yaml` with the correct `task_id` for the `retire` op. This is operationally clean — the spec doesn't pre-commit to an ID that might be wrong.

All other validation items pass.
