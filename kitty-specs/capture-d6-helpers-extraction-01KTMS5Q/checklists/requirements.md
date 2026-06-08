# Specification Quality Checklist: Capture Directive-6 Helpers Extraction

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-06-08
**Feature**: [spec.md](../spec.md)
**Mission**: `capture-d6-helpers-extraction-01KTMS5Q`

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
  - Note: Python stdlib + the `-m` invocation form ARE constrained as NFRs because they are operational invariants enforced by `[[feedback_helper_m_invocation_form]]` (production failures TWICE). NFRs are the correct surface for these.
- [x] Focused on user value and business needs
  - Purpose paragraph explains the silent inbox content loss problem and the structural-fix value.
- [x] Written for non-technical stakeholders
  - Stakeholder summary uses business language (silent content loss, openclaw budget) before any code surface.
- [x] All mandatory sections completed
  - Purpose, User Scenarios, Domain Language, FR/NFR/C, Success Criteria, Key Entities, Assumptions, Out of Scope, Architecture Documentation Updates, Reference Index.

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
  - Each FR specifies CLI shape + behavior + idempotency contract.
- [x] Requirement types are separated (Functional / Non-Functional / Constraints)
- [x] IDs are unique across FR-###, NFR-###, and C-### entries
  - FR-001..015, NFR-001..006, C-001..006.
- [x] All requirement rows include a non-empty Status value
- [x] Non-functional requirements include measurable thresholds
  - NFR-001: <500 ms per invocation. NFR-003: ≥90% line / ≥85% branch.
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic
  - SC-1/2/3/4 stated in observable terms (file presence, test pass, MD5/diff, exit code).
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
  - mark_processed idempotency (FR-002), sweep on missing state file (FR-015), ambiguous block kind (FR-007), Vikunja partial-replace gotcha (C-006), private-path refusal (C-001).
- [x] Scope is clearly bounded
  - Out of Scope: AGENTS.md rewrite, existing-helper modification, prescan inverse (#568), LLM disambiguation logic.
- [x] Dependencies and assumptions identified
  - Assumptions section covers 7 load-bearing assumptions about existing helpers + paths + permissions.

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
  - Primary cron-tick scenario + calendar happy/sad + Someday + operator dry-run.
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification
  - Implementation invariants (stdlib only, `-m` form) are scoped as NFRs (correct surface).

## Notes

- All checklist items pass on first pass.
- Bulk-edit detection: confirmed NOT a bulk edit. 6 NEW helper files, 6 new test files, 1 service-inventory entry extension. No cross-file identical-string replacement.
- This mission is intentionally narrow per `[[feedback_speckitty_split_code_and_deploy_missions]]`. The AGENTS.md rewrite is split into a follow-on mission so #567's deploy pipeline can land helpers on office2 before the prompt depends on them.
- Substantiveness gate: spec has 15 real FR rows, 6 measurable NFRs, 6 enforced Cs. Passes `SPEC_NOT_SUBSTANTIVE_OR_UNCOMMITTED` plan_guard.
