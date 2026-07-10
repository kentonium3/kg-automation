# Issue matrix — felix-calendar-helper-01KX4H3C

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #681 | RFC: Felix-owned Google Workspace APIs vs gog | deferred-with-followup | This mission delivers the Calendar phase of #681; #681 stays open for the Mail (F024) / Drive phases. |
| #679 | Inbox to calendar path broken (agent-to-agent delegation) | fixed | WP03 (commit d2f94254) replaces the agent hop with a single deterministic `route_calendar_event --create` helper call; reviewer-renata confirmed no `openclaw agent`/`sessions_send` on the calendar path. Final live SC-002 confirmation runs at office2 deploy; GitHub issue closed then. |
| #572 | gog 7-day Testing-app refresh-token residual | deferred-with-followup | Explicitly out of scope (spec C-004): gog retains its other surfaces; #572 residual stays open until those migrate. |
| #682 | office2 bare-python exit-127 (python3-only) | verified-already-fixed | Fixed earlier in commit 917ba99c; this spec only references the failure class (C-007) to justify the `python3 -m` invocation form. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
