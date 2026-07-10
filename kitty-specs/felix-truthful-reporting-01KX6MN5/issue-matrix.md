# Issue matrix — felix-truthful-reporting-01KX6MN5

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #683 | Felix fabricated a completion status + created unrequested infrastructure | in-mission | This mission's fix target — WP01 doctrine (FR-001/002/003) + WP02 cron-drift detector + WP03 assertion ledger + WP04 runner/alert; terminal `fixed` at mission merge/close. |
| #701 | Unified alert bus | verified-already-fixed | Shipped + deployed 2026-07-10; reused verbatim as this mission's alert sink (C-002). Not modified here. |
| #706 | Alert-bus durable local ledger | verified-already-fixed | Shipped 2026-07-10; append-only-JSONL + fcntl fail-safe pattern reused by the assertion ledger. Not modified here. |
| #621 | Rebaseline audited-surface gap (audit.sh doesn't hash AGENTS.md) | deferred-with-followup | Known open gap; this mission relies on it (prompts are an unmonitored audited surface → no rebaseline, per spec C-004). Not fixed here; remains tracked. |
| #702 | Slack alert sink | deferred-with-followup | Explicitly out of scope (alert-bus Phase 2). Contextual reference only. |
| #673 | Bedrock stabilization epic | deferred-with-followup | Umbrella epic; this mission is a child contributing to it. Epic stays open. |
| #661 | felix-admin-capture haiku hallucination | verified-already-fixed | Closed (superseded by #662). Cited only as related trust/comprehension lineage. |
| #662 | Harden inbox capture | verified-already-fixed | Closed + deployed. Cited only as related lineage. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
