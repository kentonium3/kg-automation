# Issue matrix — vikunja-reference-seam-01KXK68Z

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #748 | Audit + stabilize Felix's Vikunja project/label references (declared resolution seam) | in-mission | Primary deliverable; registry+accessor (WP01, `5aac3b5c`/`3cdc3a17`), validator (WP02), migration (WP03/04), routing (WP05). Terminal `fixed` at mission done. |
| #745 | Capture routing: align felix-admin-capture to the post-reset Vikunja model | in-mission | Delivered by WP05 (route_someday→q:schedule+no-due-date, Inbox fallback, AGENTS.md). Terminal at done. |
| #747 | Epic: Felix ↔ Vikunja integration | deferred-with-followup | Parent epic; this mission is one child (#748+#745). Epic stays open for #746/#749 and further children. |
| #714 | Vikunja post-reset configuration | verified-already-fixed | The reset is complete; this mission consumes the locked post-reset names (C-004) and does not modify Vikunja config (C-001). Registry seeded from live post-reset ids (WP01). |
| #743 | Inbox capture silent-loss (by-title lookup of deleted project) | in-mission | Structural guard for the silent-loss class: fail-loud accessor (WP01) + drift/unreachable validator (WP02) + routing retarget (WP05). SC-002 regression guard. Terminal at done. |
| #746 | Routing atomicity (atomic finalize) | deferred-with-followup | Explicitly out of scope; tracked as Follow-up: #746 (separate sequenced fast-follow, spec Scope). |
| #749 | Task-intake validation loop | deferred-with-followup | Out of scope; tracked as Follow-up: #749 (also owns the deferred `f:/q:/t:/loe:` taxonomy-label registry, FR-006). |
| #715 | Per-user (two-token) Vikunja labels | verified-already-fixed | The two-token model is already in place; this mission consumes it for per-token label resolution (FR-006, WP04). Not modified here. |
| #717 | Migrate Habits identity project-id 13 → t:habit label | deferred-with-followup | Future migration tracked as Follow-up: #717; this mission preserves the `{kind,value}` selector shape (FR-008, WP01/WP03) so it lands as a registry value edit. Not performed here. |
| #725 | Native is-null date filtering | deferred-with-followup | Not depended on (C-003); the `q:schedule`+no-due-date convention is independent of the #725 saved filter. Blocked upstream. |
| #723 | Shared vikunja_scope selector seam | verified-already-fixed | The seam #723 established is consumed and folded onto the registry here (WP03 read-through); its behavior is preserved, not changed. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
