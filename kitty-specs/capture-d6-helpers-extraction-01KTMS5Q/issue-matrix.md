# Issue matrix — capture-d6-helpers-extraction-01KTMS5Q

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md, plan.md, or WP prompt files.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #566 | Refactor: apply Felix Constitution Directive 6 to felix-admin-capture | deferred-with-followup | This mission ships **half 1** of #566: six stdlib `scripts/inbox/` helpers extracted from felix-admin-capture's AGENTS.md. The AGENTS.md rewrite that invokes them is deliberately split into a follow-on mission per `[[feedback_speckitty_split_code_and_deploy_missions]]` so the helpers reach office2 (via #567's 5-min deploy tick) BEFORE the prompt depends on them. #566 closure waits on the follow-on. |
| #563 | Epic: felix-admin-capture silently moves unprocessed inbox notes — AGENTS.md truncation + deploy gap | deferred-with-followup | Parent epic for #566 + #567 + #568. This mission progresses #566 (half 1 of helpers). Epic closure waits on the follow-on AGENTS.md rewrite mission and on #568 (prescan inverse). |
| #567 | Infra: deploy pipeline from `scripts/openclaw/agents/*/` to `/data/services/openclaw/<agent-dir>/` is broken or missing | verified-already-fixed | Merged 2026-06-08 as `agent-prompt-deploy-pipeline-01KTMDDD`. This mission's helpers ride the existing 5-min deploy tick to office2; no changes to the pipeline. |
| #568 | Feature: prescan inverse check — warn when files with status:unprocessed appear in 02-Inbox-Processed/ | deferred-with-followup | Explicitly out of scope per spec.md § Out of Scope. Sibling sub-issue of #566 under epic #563. Follow-up mission. |
| #558 | Inbox calendar + aspiration routing | verified-already-fixed | Merged 2026-06-08 as `inbox-calendar-and-aspiration-routing-01KTHHXS`. This mission consumes its design intent (clarification state file path, gog calendar create execution boundary) without modification. |
| #542 | Vikunja client + habits weekly report | verified-already-fixed | Merged 2026-06-08 as `vikunja-client-and-habits-weekly-report-01KTKSFT`. This mission consumes `scripts.common.vikunja_client.VikunjaClient` (used by `route_someday`, WP05) without modification. |
| #562 | Helper -m invocation form (production incident) | verified-already-fixed | Memory `[[feedback_helper_m_invocation_form]]` — all six new helpers use `python3 -m scripts.inbox.<module>` form; tests drive `main(argv)` directly per existing `tests/inbox/` convention. WP04 specifically validated with `python3 -m scripts.inbox.route_calendar_event --help`. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`.
