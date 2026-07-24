# Issue matrix — retire-vikunja-felix-bot-01KY829X

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #860 | Retire Vikunja felix-bot: consolidate all Felix→Vikunja access on the kent token | deferred-with-followup | Phase 1 (this mission) is the behavior-preserving consolidation onto `VikunjaClient`, still felix-bot; the token flip + felix-bot retirement that CLOSE #860 are the Phase-2 kitty-light follow-on (spec.md "Out of Scope → Phase 2"). |
| #531 | Epic: Shared Vikunja Client and Configuration Boundary | deferred-with-followup | Phase 1 establishes the #531 boundary (all runtime Vikunja access on the shared client); the epic stays open tracking Phase 2 + sibling children (spec.md Purpose). |
| #750 | felix-admin-capture: someday captures untagged — felix-bot 403 attaching kent q:schedule label | verified-already-fixed | Issue already CLOSED upstream of this mission; not reopened. Phase-1 is behavior-preserving (still felix-bot) and does not touch the fail-soft path (its removal is Phase-2, spec.md Out of Scope). |
| #831 | Refresh stale project-id table in deployed vikunja-api SKILL.md (post-#714 reorg) | deferred-with-followup | Phase 1 is code-only and changes no docs/SKILL.md; the SKILL/TOOLS/token-reference reconciliation that resolves #831 is Phase-2 (spec.md Out of Scope). |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
