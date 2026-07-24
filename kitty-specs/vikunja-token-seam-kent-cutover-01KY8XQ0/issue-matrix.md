# Issue matrix — vikunja-token-seam-kent-cutover-01KY8XQ0

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #860 | Retire Vikunja felix-bot: consolidate Felix→Vikunja on the kent token | in-mission | This mission (Phase 2). Terminal at merge + attended cutover (IC-07). |
| #531 | Epic: Shared Vikunja Client and Configuration Boundary | deferred-with-followup | Parent epic; this mission is one child (the token seam + cutover). Epic remains open for further boundary work. |
| #748 | Vikunja reference seam: declared registry + drift validator | in-mission | WP05 (T013) converges `validate_refs.py` on the single-source runtime token (FR-005). |
| #715 | Vikunja label taxonomy + two-token (kent/felix-bot) model | in-mission | This mission collapses the two-token model to a single kent runtime credential (WP01/WP06). |
| #750 | felix-bot 403 attaching kent label (route_someday fail-soft) | in-mission | WP05 (T012) removes the felix-bot 403 fail-soft branch; resolved once kent is the sole runtime token. |
| #831 | vikunja-api SKILL.md stale (v0.24.6 → v2.4.0 + health-check) | in-mission | WP07 (T017) updates token guidance + v2.4.0 header + health-check example. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
