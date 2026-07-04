# Issue matrix — author-capture-workspace-01KWPXBB

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #584 | Intentionally author felix-admin-capture workspace context (this mission) | fixed | WP01 5881f823 — SOUL/USER/TOOLS authored + AGENTS label receiver; capture PASSES both #587 invariants (validator run against lane files) and all conservation greps hold |
| #167 | Epic: Intentionally author every OpenClaw agent workspace | deferred-with-followup | Parent epic; continues via sibling authoring children. This mission delivers the capture child. Follow-up: #167 |
| #587 | Define OpenClaw workspace authoring standards and validation | verified-already-fixed | Landed on main 2026-07-04 (merge ad7ee47d); this mission is authored against that standard + validator. |
| #651 | Capture as clarifying router + capability-gap log | deferred-with-followup | Explicitly out of scope (spec Out of Scope + C-006); routing-intelligence follows this pure refactor. Follow-up: #651 |
| #636 | Deploy-path boundary (pull-based agent-prompt-sync vs felix-deployer) | deferred-with-followup | Context for the corrected deploy path (research.md Decision 4; spec FR-009/C-003 amended). Boundary issue stays open. Follow-up: #636 |
| #557 | Rebaseline obligation (audited surfaces) | verified-already-fixed | Obligation framework already in place; this mission's determination = "not required" (agent-prompt surface not hashed by audit.sh), recorded at merge. |
| #621 | Rebaseline directives gap — agent-prompt surface unmonitored | deferred-with-followup | Basis for the rebaseline-not-required determination (audit.sh hashes only openclaw.json, not per-agent prompt files). Gap stays open. Follow-up: #621 |
| #582 | Intentionally author felix-admin-habits workspace context | deferred-with-followup | Sibling authoring child; separate mission (Out of Scope here). Follow-up: #582 |
| #585 | Intentionally author felix-admin-escalation workspace context | deferred-with-followup | Sibling authoring child; separate mission (Out of Scope here). Follow-up: #585 |
| #586 | Intentionally author felix-admin-tasker workspace context | deferred-with-followup | Sibling authoring child; separate mission (Out of Scope here). Follow-up: #586 |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
