# Issue matrix — observation-digest-repoint-01KWS2E2

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #656 | felix-admin cron path fix (inbox state/log relocation) | verified-already-fixed | Prerequisite; merged c0ffcbb8 + deployed. This mission is its authorized fast-follow (spec Summary; DM-01KWS4F986PVHTJRSHZPQACDM7). Not modified here. |
| #490 | observation signal extraction (tick.py) | verified-already-fixed | Shipped feature; explicitly out of scope (C-003). tick.py + felix-core-digest-signals state untouched by this mission. |
| #557 | rebaseline obligation for audited surfaces | verified-already-fixed | Standing policy; mission complies via deploy-pipeline audited-surface auto-rebaseline (C-007, plan Charter Check). Recorded at deploy time. |
| #658 | fleet-wide runtime-environment-assumption audit | deferred-with-followup | Broader open audit tracked by #658; this mission resolves the concrete observation-digest instance of the same HOME/~ unsynced-path class (spec Relationship). |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
