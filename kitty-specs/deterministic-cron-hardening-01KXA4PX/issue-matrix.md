# Issue matrix — deterministic-cron-hardening-01KXA4PX

One row per GitHub issue referenced in spec.md (+ the #716 handoff target). Per the spec-kitty mission-review gate.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #723 | Two Felix crons erroring every run (escalation-daily + habits-weekly-report) | fixed | Mission delivers the complete fix: WP02 mechanizes escalation enumeration (enumerate_candidates helper) + rewrites the agent prompt; WP03 moves the weekly report off the LLM to a deterministic systemd-timer driver; WP04 adds the service-inventory observability + the transactional deploy (retire old cron, enable timer). All 4 WPs approved; full suite 4957 pass. GitHub issue stays open until the post-merge office2 deploy + live verification, then closed. |
| #722 | Canary openclaw-cron-state probe (surfaced these two failures) | verified-already-fixed | Shipped + deployed + live-verified + closed 2026-07-12 (merge 9c401894). It is the observability that exposed #723; no work here. |
| #714 | Epic: Vikunja configuration reset — projects, labels, filters, dashboard | deferred-with-followup | This mission externalizes the Vikunja scope selectors into scripts/common/vikunja_scope.py (config seam) so #714 is a config swap, not code. #714 updates the selector VALUES for the new taxonomy. Note posted to #714. Follow-up: #714. |
| #716 | Vikunja reset: restructure projects (create topic projects, delete pseudo-view projects) | deferred-with-followup | The label FETCH strategy + label-form habit exclusion are explicitly deferred here (post-plan review H5/H6); #723 ships the seam + project_id form only. Note posted to #716. Follow-up: #716. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by this mission; must reach a terminal verdict before mission `done`).
