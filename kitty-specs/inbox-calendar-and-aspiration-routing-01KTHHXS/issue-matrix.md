# Issue matrix — inbox-calendar-and-aspiration-routing-01KTHHXS

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #324 | Inbox parser: forward calendar items to Felix for automatic Google Calendar creation | deferred-with-followup | Follow-up: #558 (this mission). WP01 ships the deterministic validator + RRULE conversion + trivia-night fixture; the inbox→capture→main→gog routing closes via WP02 + WP03 within #558. |
| #271 | Epic: Felix as mirror — back-chaining intent to priorities, surfacing tangents | deferred-with-followup | Follow-up: #558 (scoped slice of #271). Mirror/back-chaining work is explicitly out of scope per spec.md § Out of Scope. |
| #556 | Feature: Inbox parsing and categorization rework — habits check-in accuracy + capture agent classification | deferred-with-followup | Follow-up: #558. WP01 includes historical-misroute fixtures from #556 in tests/inbox/fixtures/classifier_regression.json; the actual routing fix lands in WP02 within #558. Habits side already resolved in 363685ea (pre-mission). |
| #558 | Feature: Capture agent — classify calendar events and aspirations separately from todos | deferred-with-followup | Follow-up: #558 itself — mission in progress, three WPs (WP02/WP03/WP04) remain after WP01 approval. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`.
