# Issue matrix — agent-prompt-deploy-pipeline-01KTMDDD

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md, plan.md, or WP prompt files.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #567 | Infra: deploy pipeline from `scripts/openclaw/agents/*/` to `/data/services/openclaw/<agent-dir>/` is broken or missing | fixed | This mission IS #567. WP01 delivers the helper (commit a2f800c0 lane-a, 56/56 tests, 97.64% cov); WP02 delivers systemd units; WP03 delivers architecture docs. Verdict transitions to `fixed` on mission merge. |
| #563 | Epic: felix-admin-capture silently moves unprocessed inbox notes — AGENTS.md truncation + deploy gap | deferred-with-followup | Parent epic for #567 + #566 + #568. Only #567 ships in this mission. #566 (prompt shrink) and #568 (prescan inverse) ship separately. Epic closure waits on all three. |
| #566 | Refactor: apply Felix Constitution Directive 6 to felix-admin-capture | deferred-with-followup | Explicitly out of scope per spec.md § Out of Scope. Sibling sub-issue of #567 under epic #563. Follow-up mission. |
| #568 | Feature: prescan inverse check — warn when files with status:unprocessed appear in 02-Inbox-Processed/ | deferred-with-followup | Explicitly out of scope per spec.md § Out of Scope. Sibling sub-issue of #567 under epic #563. Follow-up mission. |
| #561 | Habits output discipline (Hard Rules) | verified-already-fixed | Merged 2026-06-08 as part of `vikunja-client-and-habits-weekly-report-01KTKSFT`. This mission's deploy pipeline (#567) is what UNSTICKS the deployment of #561's AGENTS.md changes from main → office2; #561's code is unchanged. |
| #558 | Inbox calendar + aspiration routing | verified-already-fixed | Merged 2026-06-08 as part of `inbox-calendar-and-aspiration-routing-01KTHHXS`. Same situation as #561: this mission's pipeline is what unsticks deployment of the 265-line AGENTS.md expansion (1215 lines in repo vs 950 deployed). |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`.
