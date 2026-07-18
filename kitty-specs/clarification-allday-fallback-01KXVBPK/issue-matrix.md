# Issue matrix — clarification-allday-fallback-01KXVBPK

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #786 | All-day event support in the calendar helper (#780 item 1) | verified-already-fixed | Shipped 2026-07-18 (merge `acb6058f`); `calendar_helper._all_day_field`/`_build_event_body(all_day=)` present and depended on by WP02. |
| #739 | inbox→calendar: deterministic relative-date resolver + no-time→clarification policy | verified-already-fixed | CLOSED; the "no-time → ask, never guess" policy is the baseline this mission builds on (see spec Lineage). |
| #746 | Note-level atomic `route_and_finalize` transaction | verified-already-fixed | Shipped 2026-07-17 (merge `5f6c0c5e`); `route_and_finalize._run_finalize` reused by WP03 for the atomic create→log→mark. |
| #780 | inbox→calendar: all-day-event fallback when a start-time clarification goes unanswered (items 2+3) | in-mission | This mission (WP01–WP06). Reaches terminal `fixed` at mission merge; close #780 on merge. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
