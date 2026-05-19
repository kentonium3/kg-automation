# Specification Quality Checklist: Backfill habits JSONL from Felix comments

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-19
**Feature**: [spec.md](../spec.md)

## Content Quality

- [~] No implementation details (languages, frameworks, APIs) — *known tension; see Notes*
- [x] Focused on user value and business needs (preserving historical habit completion data before Phase 5 cutover)
- [~] Written for non-technical stakeholders — *known tension; appropriate for one-shot operator-driven helper*
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Requirement types are separated (Functional / Non-Functional / Constraints)
- [x] IDs are unique across FR-###, NFR-###, and C-### entries (FR-001..FR-012, NFR-001..NFR-005, C-001..C-007)
- [x] All requirement rows include a non-empty Status value (all "Active")
- [x] Non-functional requirements include measurable thresholds (NFR-001: <60s, NFR-002: <30s, NFR-003: 0 new deps, NFR-004: ≥85%, NFR-005: no new sensitive-data leakage)
- [x] Success criteria are measurable
- [~] Success criteria are technology-agnostic — *partial: SCs reference state_log.read, Vikunja, JSONL records; acceptable because these are concrete deliverables of prior phases*
- [x] All acceptance scenarios are defined (5 scenarios covering dry-run, live-run, unmapped state, malformed comment, rollback)
- [x] Edge cases are identified (unmapped state, malformed comments, zero comments on new MWF tasks, retired workout history, rollback)
- [x] Scope is clearly bounded (Out of scope explicit; locked HISTORICAL_STATE_MAP)
- [x] Dependencies and assumptions identified (6 assumptions)

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria (mapped via Success Criteria)
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [~] No implementation details leak into specification — *known tension; see Notes*

## Notes

**Known tension on "no implementation details" items**: same as Phase 2 and Phase 3 — this is a foundation/utility helper where the architectural decisions (state_log library, FELIX_COMMENT_PATTERN reuse, HISTORICAL_STATE_MAP shape) come from prior ADR-0002 phases and the 2026-05-19 production data probe. The spec template's "no implementation details" rule assumes a user-facing feature with separate business and engineering stakeholders. For this mission both roles collapse onto Kent + the LLM implementer.

**HISTORICAL_STATE_MAP is locked**: based on the 2026-05-19 probe finding only 2 distinct state values (`complete` × 24, `will-not-do` × 2). If future data discovers new values, the map updates reactively per the unmapped-state-values report.

All other validation items pass.
