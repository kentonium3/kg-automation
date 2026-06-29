# Issue matrix — finalize-inbox-file-01KW8MSQ

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #325 | finalize_inbox_file.py — atomic post-routing cleanup (this mission) | in-mission | WP01 c100acaa (helper hardened); reaches `fixed` when WP02+WP03 complete |
| #621 | Rebaseline directives gap — agent-prompt surface unmonitored | deferred-with-followup | Referenced as context (why rebaseline is not required here); the gap remains open as its own tracked issue — WP03 records the reasoning |
| #557 | Rebaseline obligation (audited surfaces) | verified-already-fixed | Obligation framework (auto via #618) already in place; this mission's determination = "not required" (agent-prompt surface not hashed by audit.sh), recorded at merge |
| #327 | RFC: universal error/alerting primitives | deferred-with-followup | Explicitly out of scope (spec.md "Out of Scope"); the RFC itself is the followup |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
