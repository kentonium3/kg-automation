# Issue matrix — unified-alert-bus-01KX5TYT

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #516 | Epic: Foundation 1 — Felix-wide health & observability ("single alert stream") | deferred-with-followup | This mission (#701) is a child of #516 delivering the single-alert-stream substrate (WP01 bus + WP02–WP04 emitter migrations). Follow-up: #516 remains open (F1 epic); further observability children (incl. #702 Slack sink) continue it. |
| #327 | RFC: universal error & alerting primitives | deferred-with-followup | This mission implements #327's delivery + message-construction layer (the `felix-alert` bus, WP01–WP06). Follow-up: #327 remains open for the canary registry and LLM-agent-emit, which are out of scope here (spec C-006). |
| #673 | Epic: Bedrock Stabilization (F1 observability line) | deferred-with-followup | This mission is the F1 alert-bus contribution to the Bedrock program. Follow-up: #673 remains open (Bedrock epic); this mission does not close it. |
| #557 | Rebaseline obligation (audited surfaces) | verified-already-fixed | The rebaseline-automation mechanism is already live (#618/#685). This mission complies with the obligation via WP05 (`expected_baselines` + rebaseline on the audited-surface deploy); no change to #557 itself. |
| #637 | agent-prompt-sync has no failure alerting | deferred-with-followup | This mission migrates agent-prompt-sync's EXISTING health-notifier path onto the bus (WP02), but does not add the NEW failure alerting #637 requests (spec C-006 defers it). Follow-up: #637 remains open (add agent-prompt-sync failure alerting via the bus). |
| #699 | Felix calendar helper — deploy that exposed the alert-opacity symptom (closed) | verified-already-fixed | #699 is already closed; it is referenced only as the missing-executable-bit opacity example. The alert-opacity CLASS it exposed is fixed by WP02 (real stderr threaded into failure alerts, SC-002 + #699 regression test). |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
