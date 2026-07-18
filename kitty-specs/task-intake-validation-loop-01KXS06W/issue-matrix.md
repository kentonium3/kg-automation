# Issue matrix — task-intake-validation-loop-01KXS06W

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #750 | felix-bot 403 attaching kent-owned labels | fixed | WP04 apply engine writes exclusively via the kent token (`36a9380b`/`d6b72617`); no felix-bot label-attach code path exists (test asserts zero requests). SC-008. |
| #714 | Vikunja configuration / Tier-1 intake standard | verified-already-fixed | Dependency; the intake standard this loop enforces. #714 chain (#715/#716/#717/#718) shipped + closed. |
| #748 | Vikunja reference/resolution seam | verified-already-fixed | Dependency; CLOSED. Seam shipped (main bccf1f02); WP01 declares the taxonomy on it (e9679050). |
| #715 | Vikunja label taxonomy + two-token model | verified-already-fixed | Dependency; CLOSED. Provides the `vikunja-api-kent` token + labels (ids 18-29 reconciled live in WP01 e9679050). |
| #492 | signal-to-doc-map / doc-surface coverage precedent | verified-already-fixed | Referenced as guidance for doc-sync (INDEX/DEVELOPER_PORTAL); signal-to-doc-map.json in place, WP06 follows it. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
