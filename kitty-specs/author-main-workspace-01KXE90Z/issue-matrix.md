# Issue matrix — author-main-workspace-01KXE90Z

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

Most referenced issues are context references (the standard, the pilot, preserved
boundaries, the deploy/rebaseline doctrine) rather than defects this mission fixes.
Verdicts reflect that: this mission fixes #583, relies on already-shipped foundations
(`verified-already-fixed`), and advances/defers the ongoing #167 chain.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #583 | Feature: Intentionally author main workspace context | fixed | This mission. WP01 commit `83a156a5`: five `main/*` files authored to #587 + roster note; `main` validator `ok:true`; AGENTS.md 11586B (<12K); full openclaw suite 72 passed. |
| #167 | Epic: Intentionally author every OpenClaw agent workspace | deferred-with-followup | Advanced by this mission (main = 2nd child after pilot #584). Epic remains open. Follow-up: #585 (escalation), #586 (tasker), #582 (habits), #635 (calendar). |
| #587 | Feature: Define OpenClaw workspace authoring standards + validation | verified-already-fixed | Shipped `ad7ee47d`, closed 2026-07-13. This mission is authored against the standard and reuses `validate_workspace.py` + the 12K-cap guard. |
| #165 | Mail / Executive-Assistant epic | deferred-with-followup | Referenced only as the future capability `main` will extend; the AGENTS role statement frames main as EA-orchestrator on current reality (no speculative mail behavior). Follow-up: #165 (needs a vision session). |
| #679 | Calendar event creation routed via felix-admin-calendar | verified-already-fixed | The #679 calendar-delegation boundary is preserved verbatim in the AGENTS routing matrix (calendar events delegated to felix-admin-calendar; never created by main). |
| #635 | Feature: Intentionally author felix-admin-calendar workspace | deferred-with-followup | Later #167 child (RRULE-gated on go-vikunja/vikunja#3071). Not in scope here. Follow-up: #635. |
| #636 | Agent-prompt deploy boundary (agent-prompt-sync vs felix-deployer manifest) | verified-already-fixed | Established doctrine honored: agent prompts deploy via agent-prompt-sync on merge-to-main; C-001 in spec forbids a `deploys/queued/` manifest, and none was authored. |
| #621 | Rebaseline gap: agent prompt files not hashed by audit.sh | deferred-with-followup | Open gap this mission relies on for its `Rebaseline: not required` record (C-004). Not closed here. Follow-up: #621. |
| #584 | Feature: Intentionally author felix-admin-capture workspace | verified-already-fixed | Pilot, merged + closed. This mission mirrors its clean-separation pattern and adapts (not copies) its canonical Output Discipline block. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
