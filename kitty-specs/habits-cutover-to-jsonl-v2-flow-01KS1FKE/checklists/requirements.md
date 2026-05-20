# Specification Quality Checklist: Habits cutover to JSONL v2 flow

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-19 (UTC 2026-05-20)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [~] No implementation details (languages, frameworks, APIs) — *known tension; see Notes*
- [x] Focused on user value and business needs (Kent's morning check-in correctness; structural fix for Tuesday workout bug)
- [~] Written for non-technical stakeholders — *known tension; operator-facing cutover for a deployed agent*
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Requirement types are separated (Functional / Non-Functional / Constraints)
- [x] IDs are unique across FR-###, NFR-###, and C-### entries (FR-001..FR-010, NFR-001..NFR-005, C-001..C-007)
- [x] All requirement rows include a non-empty Status value (all "Active")
- [x] Non-functional requirements include measurable thresholds (NFR-001: <120s, NFR-002: <24500 bytes, NFR-003: 314+ tests, NFR-004: <5s, NFR-005: 0 new secrets)
- [x] Success criteria are measurable
- [~] Success criteria are technology-agnostic — *partial: SC-001 cites sha256, SC-003 cites helper names; these come from concrete deliverables of prior phases*
- [x] All acceptance scenarios are defined (6 scenarios covering deploy, post-cutover tick, Tuesday structural fix, UI backfill, soak anomaly, catastrophic rollback)
- [x] Edge cases are identified (UI completion during day, drift detection, format anomaly, catastrophic failure)
- [x] Scope is clearly bounded (Out of scope explicit; Q1-Q3 design decisions locked)
- [x] Dependencies and assumptions identified (6 assumptions)

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria (mapped via Success Criteria)
- [x] User scenarios cover primary flows (Kent + cron + agent)
- [x] Feature meets measurable outcomes defined in Success Criteria
- [~] No implementation details leak into specification — *known tension; see Notes*

## Notes

**Known tension on "no implementation details" items**: this is an operator-driven cutover for a deployed agent. The spec's "implementation details" (helper script names, file paths, cron times, sha256 verification) ARE the contract — they're the concrete deliverables prior phases established. The template's "no implementation details" rule assumes a feature with separate business/engineering stakeholders. For Phase 5, Kent IS both stakeholder and operator, so the technical specificity is the value.

**Fail-forward posture locked**: C-007 makes explicit that non-catastrophic issues are forward-fix, not rollback. This is a deliberate risk posture chosen by Kent (2026-05-19 discovery).

**No NEEDS CLARIFICATION markers**: Q1-Q3 from the issue formalization were resolved in discovery (Q1=2-3 day soak, Q2=cutover-only mission with separate post-soak decommission, Q3=rename `_v2` → canonical in the follow-up mission).

All other validation items pass.
