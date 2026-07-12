# Issue matrix — vikunja-restructure-projects-01KXBS2P

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #714 | Epic: Vikunja configuration reset | deferred-with-followup | Umbrella epic; this mission delivers the additive project-structure child (#716). Epic stays open for #717/#718. |
| #717 | Vikunja reset: migrate surviving tasks + delete emptied projects | deferred-with-followup | Task migration + all task-bearing-project deletion explicitly out of scope here; handoff comment posted on #717. |
| #715 | Vikunja reset: label taxonomy | verified-already-fixed | #715 DONE+CLOSED; this mission consumes its deliverables (the `vikunja-api-kent` token + the `t:habit` label). |
| #718 | Vikunja reset: saved filters | deferred-with-followup | #716 deletes the legacy filters; creation of the six canonical filters deferred to #718 (spec Out-of-Scope). |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
