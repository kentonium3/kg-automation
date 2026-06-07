# Issue matrix — inbox-calendar-and-aspiration-routing-01KTHHXS

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #324 | Inbox parser: forward calendar items to Felix for automatic Google Calendar creation | deferred-with-followup | WP01 ships the deterministic validator + RRULE conversion + trivia-night fixture; the inbox→capture→main→gog routing closes via WP02 + WP03. |
| #271 | Epic: Felix as mirror — back-chaining intent to priorities, surfacing tangents | deferred-with-followup | Explicitly out of scope per spec.md § Out of Scope; this mission is a scoped slice (#558) of the epic, no back-chaining/mirror surface delivered. |
| #556 | Feature: Inbox parsing and categorization rework — habits check-in accuracy + capture agent classification | deferred-with-followup | WP01 includes historical-misroute fixtures from #556 in tests/inbox/fixtures/classifier_regression.json; the actual routing fix lands in WP02. Habits side already resolved in 363685ea (pre-mission). |
| #558 | Feature: Capture agent — classify calendar events and aspirations separately from todos | deferred-with-followup | Mission #558 is delivered across WP01–WP04; WP01 completes the deterministic helper + tests + fixtures, three WPs remain. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`.
