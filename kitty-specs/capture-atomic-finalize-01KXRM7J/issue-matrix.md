# Issue matrix — capture-atomic-finalize-01KXRM7J

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #737 | inbox: append_routing_entry couldn't record calendar routes (calendar atomic-finalize precedent) | verified-already-fixed | CLOSED. This mission generalizes #737's `route_calendar_event._run_finalize` into the note-level transaction (spec Overview; research D1/D2). |
| #10 | (parser false-match on "Finding #10") | verified-already-fixed | NOT a dependency. "Finding #10" in spec C-006/Dependencies is the Codex review finding number, not GitHub issue #10 (CODEOWNERS, unrelated + already merged). |
| #740 | inbox: pending-calendar-clarification notes re-clarify/re-WhatsApp every tick | deferred-with-followup | OPEN. Kent's scope call (spec C-006): the Codex finding "surface pending-calendar-clarification in prescan" is out of scope for #746, deferred to follow-up #740. |
| #745 | Capture routing: align felix-admin-capture to the post-reset Vikunja model | verified-already-fixed | CLOSED dependency. Ensures finalize routes to stable destinations (spec Assumptions/Dependencies). |
| #744 | infra: reconcile duplicate Vikunja Inbox projects (id 1 vs id 14) | verified-already-fixed | CLOSED dependency. Canonical Inbox is stable (spec Dependencies). |
| #738 | inbox→calendar unreliable: haiku drops --create, misclassifies/mis-dates | deferred-with-followup | OPEN. #746's note-level finalize + removal of hand-sequenced mark_processed closes the structural "processed-without-route" silent-loss facet; the classification-quality / model-reliability facet remains tracked in follow-up #738. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
