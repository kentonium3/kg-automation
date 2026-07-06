# Issue matrix — harden-inbox-capture-01KWVGZM

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #658 | Agent runtime-env guardrails — `${PYTHONPATH:?}` canonical form corrected (fails under exec sanitization) | in-mission | WP01 461cc5d5 (checker inverted); fleet swap completes in WP02/WP03 |
| #662 | Harden inbox capture (Phase 1: FR-001..005; Phase 2 deferred to follow-up) | in-mission | WP01 461cc5d5; capture fix WP02, fleet WP03, docs WP04 |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
