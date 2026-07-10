# Issue matrix — f0-exec-hardening-01KX4ZCY

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #675 | Foundation 0: OpenClaw capability-governance / exec-hardening (this mission) | deferred-with-followup | Finding in docs/design/felix-openclaw-boundary.md §8.3 (exec-allowlist infeasible) + §8.4 (close-as-rescoped). Follow-up: #704 (sandbox hard-containment). Finding + full doc reconcile delivered by WP01/WP02. |
| #673 | Bedrock Stabilization epic (Foundation-0 parent) | deferred-with-followup | Foundation-0 Step-3 resolution within Bedrock. Follow-up: #704 (sandbox hard-containment) carries the remaining F0 hard boundary. Epic not closed by this mission. |
| #680 | Email/drive controlled owner (blocker to releasing main's gog) | deferred-with-followup | main documented as the tracked Foundation-0 gog exception in the boundary doc + service-inventory.json. Follow-up: #680 (email/drive owner) itself gates removing gog from main; not fixed here by design. |
| #699 | Felix calendar helper — calendar migrated off gog (closed) | verified-already-fixed | WP02 reconciles docs/design/architecture/data/service-inventory.json to #699's already-shipped reality (calendar skills=[], inline route_calendar_event --create path, gog-free); no code change. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
