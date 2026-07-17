# Specification Quality Checklist: Atomic Capture Finalize Across Route Kinds

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-07-17
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — kept to WHAT/WHY; helper/module names appear only as bounded context, not design
- [x] Focused on user value and business needs (silent-loss of captures)
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Requirement types are separated (Functional / Non-Functional / Constraints)
- [x] IDs are unique across FR-###, NFR-###, and C-### entries
- [x] All requirement rows include a non-empty Status value
- [x] Non-functional requirements include measurable thresholds
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified (empty note, unclassifiable note, delegated task, calendar clarification)
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria (mapped to SC-001..006)
- [x] User scenarios cover primary flows (happy path + the failure path this closes)
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Design-level decisions locked with Kent (2026-07-17): fold calendar into the unified
  finalize mechanism; cover the tasker-delegated vikunja_task path; no-route/empty
  disposition records a routing-log entry so `processed ⇒ logged` is total.
- **Post-plan Codex review (2026-07-17) reshaped the design** from per-route to a
  **note-level finalize transaction** (12 findings, 6H/6M). Folded: note-level atomicity
  across multi-block notes (FR-001/003), per-block routing-log keys + per-kind idempotency
  (FR-009/010), explicit log/mark state machine (FR-011), agent-hop provenance for
  tasker+github (FR-006/012), empty-body validation (FR-007), prescan needs-review terminal
  (FR-008), health-rail surfaced in the IDLE gate (FR-014), calendar invariant pinned
  (FR-015). Finding 10 (pending-calendar-clarification surfacing) deferred to #740 (C-006).
- Spec fixes the atomicity/coverage/retry-safety contract; the note-level orchestration +
  block-plan shape is carried in plan.md/contracts.
