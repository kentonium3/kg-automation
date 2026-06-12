# Issue matrix — pull-based-deploy-pipeline-01KTYQQS

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #136 | Feature: Deployment model for Mac → office2 with tier-aware controls | in-mission | This IS the implementing mission. Spec.md, plan.md, tasks.md, and the 8 WP prompts all directly implement #136's body. Transitions to `fixed` at mission merge. |
| #533 | Epic: Deploy Script Surface Cleanup | in-mission | Parent Epic. This mission delivers the primary child (#136). Epic remains open post-merge until siblings #548 and #154 resolve. Transitions to `fixed` only when ALL children close. |
| #154 | Charter amendment: recognize shared deploy primitives in deployment rule | in-mission | Folded into this mission per the operator-approved plan (2026-06-12). WP07 rewrites `.kittify/charter/charter.md` Deployment Constraints rule to describe the manifest discipline, replacing both the old per-script rule and #154's narrower (a)/(b) amendment. Close as superseded at mission merge. |
| #549 | Runbook: Document canonical deploy-script template | in-mission | Captured by this mission's WP07 (`docs/runbooks/deploy/discipline.md` is the canonical operational runbook). Close as captured at mission merge. |
| #548 | Audit: Classify deploy scripts as active, deprecated, or historical | deferred-with-followup | Out of scope for this mission per plan.md. #548 is the post-#136 cleanup pass that reclassifies the 7 grandfathered scripts (`deploy-{028,149,f013,f014,f026,felix-admin-calendar,restore-whatsapp-dm-reply-delivery}.sh`) once the library + manifest discipline land. Sibling issue; not blocked by this merge. Operator will run it as a separate cycle. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).

## Notes

- All 5 issues auto-detected by `scaffold_issue_matrix` regex (`(?:^|\s|\(|\[)#(\d{2,6})`); spec.md uses bare `#NNN` form so no manual additions needed.
- `#136`, `#533`, `#154`, `#549` carry `in-mission` verdict during per-WP approvals; transition to terminal verdicts (`fixed` / `superseded` / `captured`) at mission merge per the gate-4 contract.
- `#548` carries `deferred-with-followup` from the start — operator-authored decision; no transition needed.
