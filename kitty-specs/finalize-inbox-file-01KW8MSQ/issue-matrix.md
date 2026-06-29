# Issue matrix — finalize-inbox-file-01KW8MSQ

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #325 | Atomic in-place inbox finalize (mark_processed hardening; this mission) | fixed | WP01 c100acaa (helper: exit-2/JSON/inbox-root) + WP02 851ba566 (Step 5c handling) + WP03 2963026a (architecture docs) — all approved |
| #621 | Rebaseline directives gap — agent-prompt surface unmonitored | deferred-with-followup | Context for rebaseline-not-required (agent-prompt surface not hashed by audit.sh); gap stays open. Follow-up: #621 (WP03 records the reasoning) |
| #557 | Rebaseline obligation (audited surfaces) | verified-already-fixed | Obligation framework (auto via #618) already in place; this mission's determination = "not required" (agent-prompt surface not hashed by audit.sh), recorded at merge |
| #327 | RFC: universal error/alerting primitives | deferred-with-followup | Out of scope (spec.md "Out of Scope" names it). Follow-up: #327 (the RFC tracks the broader observability work) |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
