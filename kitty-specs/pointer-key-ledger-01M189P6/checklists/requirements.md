# Specification Quality Checklist: Backup Pointer Key Ledger

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-30 · **Revalidated**: 2026-08-30 against spec.md v2
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
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
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

**Validation pass 2 (v2), after the post-plan review.** All items pass. Pass 1 also reported all
items passing, which is the useful record here: the checklist is necessary and was not sufficient.
Three independent review lenses then found ~39 issues in the artifact it had just certified,
including a live regression. Recording that so the checklist is not mistaken for a quality gate —
it verifies *form*, and the review verifies *substance*.

Items whose v1 pass was wrong, and why they now genuinely pass:

- **"Requirements are testable and unambiguous"** — v1 passed this while FR-008 specified no
  tolerance value at all ("beyond the tolerated margin"), which is not executable. v2 states 5
  minutes with a derivation, along with every other previously-unstated threshold (9-day integrity
  bound, 50 GiB free-space floor from live measurement, snapshot floor of 2 with first-run
  suppression).
- **"Success criteria are measurable"** — v1's SC-001 asserted a 20-minute detection latency that
  no offline test can observe and whose only live demonstration would require corrupting the single
  backup copy. v2 splits it: the *decision* is the measured criterion, the *latency* is a stated
  derivation from the 15-minute interval.
- **"Scope is clearly bounded"** — v1 passed this while never naming the three keys it declined to
  adopt, so a reader could not learn that three of four catastrophic conditions stayed green. v2
  opens with a *What this mission does not close* table. After the decision to close all four legs,
  that table records only the one that genuinely remains (the unwatched alerter), promoted to a
  named risk R-001 rather than an assumption.
- **"Edge cases are identified"** — v1 missed the two that mattered most: the integrity check
  *silently stopping* (distinct from "not run today"), and an adjudicated key being *absent* versus
  present-and-null.

Two conventions worth stating, since both look like violations of the first checklist section:

- **FR-004 ("derived from a real execution") is deliberately near-implementation.** It is a
  requirement, not a design preference: a hand-maintained key list is the exact defect being
  retired, so a conforming implementation cannot use one.
- **NFR-006 (evaluator totality) names a runtime behaviour.** Also deliberate: a raised exception is
  caught upstream and mapped to `unknown`, and a first-seen `unknown` does not alert — so an
  evaluator that throws converts a detected corruption into silence. Without stating it, the
  mission's own mechanism could reproduce the failure it fixes.

No items require spec updates before `/spec-kitty.tasks`.
