# Issue matrix — vikunja-client-and-habits-weekly-report-01KTKSFT

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #542 | Shared Vikunja API client (stdlib-only) | fixed | WP01 commit a8bdabe9 (lane-a) — `scripts/common/vikunja_client.py` |
| #561 | Habits output discipline (Hard Rules) | deferred-with-followup | Mission scope — WP03 delivers Hard Rules edits in this slice; verdict transitions to `fixed` on mission merge |
| #556 | Paginate /tasks/all + scope habit query to project 13 | verified-already-fixed | Merged 2026-06-08 as 363685ea (pre-mission); referenced in research.md as the source for the project-13 scoping pattern |
| #408 | Strength training Mon/Wed/Fri habit recurrence pattern | verified-already-fixed | Past mission — reference precedent for the weekday-in-title classification adopted by WP02 (`repeat_after=0` + parsed weekday in title) |
| #563 | Inbox cleanup unprocessed-archive | deferred-with-followup | Out of this mission's scope; tracked separately for a follow-on inbox-pipeline mission |
| #562 | Habits weekly report unimplemented + LLM-improvised data | deferred-with-followup | Mission umbrella issue — WP02 + WP03 deliver the fix in this slice; verdict transitions to `fixed` on mission merge |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`.
