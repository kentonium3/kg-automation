# Issue matrix — harden-inbox-capture-01KWVGZM

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #658 | Agent runtime-env guardrails — `${PYTHONPATH:?}` canonical form corrected (fails under exec sanitization) | fixed | WP01 (checker inverted) + WP02/WP03 (fleet swapped to checkout-cd); fleet `env_assumptions` clean post-merge |
| #662 | Harden inbox capture (Phase 1: FR-001..005 delivered; Phase 2 multi-intent decomposition = separate follow-up) | fixed | WP02 capture reword+sonnet identity, WP03 fleet, WP04 docs; runtime model flip + SC-002/004/005 verified at post-merge office2 deploy (quickstart) |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
