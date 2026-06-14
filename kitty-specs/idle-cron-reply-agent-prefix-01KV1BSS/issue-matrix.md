# Issue matrix — idle-cron-reply-agent-prefix-01KV1BSS

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md / plan.md / research.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #592 | Prefix IDLE cron messages with agent identifier (e.g., `[felix-admin-capture]: IDLE`) | in-mission | This mission IS the deliverable; WP01 applied the canonical Hard rule #1 byte-format block to 4 AGENTS.md files; WP02 verifies deployed behavior + rebaseline. |
| #591 | OpenClaw 2026.6 auth-store migration + WhatsApp recovery (post-incident capture) | verified-already-fixed | Referenced in spec Overview as the 2026-06-12 trigger event that surfaced the attribution gap; #591 itself was resolved by the OpenClaw 2026.6.5 auth-store fix + #596/#597 follow-ups. Out-of-scope for this mission; cited only as context. |
| #596 | felix-admin-capture cron failures — invalid x-api-key after OpenClaw 2026.6 doctor --fix imports stale per-agent key | verified-already-fixed | Referenced in research R-05 as the same incident class that surfaced the live `inbox-5pm` auth error during plan-phase probe (2026-06-13T20:54Z). Resolved by #597 (auth-verifier mission `openclaw-auth-verifier-01KV0Y9E`). Out-of-scope for this mission. |
| #557 | Rebaseline obligation (audited surfaces) | in-mission | WP02 T010 runs the rebaseline command per `docs/runbooks/security-baseline-ops.md` and records `Rebaseline: completed at <ts>` in the merge commit. scripts/openclaw/agents/*/AGENTS.md is an audited surface per `docs/design/architecture/data/audited-surfaces.json`. |
| #1716 | upstream Priivacy-ai/spec-kitty coord/main split-authority (P0 release-blocker tracked under name-vs-authority remediation mission #133) | not-applicable | Upstream spec-kitty issue referenced in plan/research as one of several rc41/rc42 quirks the mission was designed to surface on rc43. Encountered and worked around during this mission via the fast-forward dance; per CHANGELOG [Unreleased] covered by 3.2.0 stable's mission #133. Local tracker #602 captures the rc43 reproducer. |
| #1764 | upstream Priivacy-ai/spec-kitty analysis-report staleness (re-fires per WP) | not-applicable | Upstream spec-kitty issue referenced in plan as a known rc41/rc42 quirk. Not hit in this mission run; analyze succeeded with verdict `ready` and persisted cleanly. |
| #1784 | upstream Priivacy-ai/spec-kitty rc40 finalize-tasks branch-model catch-22 (planning artifacts on coord vs target) | verified-already-fixed | Upstream spec-kitty issue. Local tracker #569 documented prior reproducers + workaround. The workaround (fast-forward primary↔coord at each lifecycle handoff) was applied successfully twice in this mission (after specify/plan and after finalize-tasks). Upstream fix lands in 3.2.0 stable per CHANGELOG [Unreleased]. |
| #1817 | upstream Priivacy-ai/spec-kitty merge gate ignores `review_artifact_override` annotation | not-applicable | Upstream spec-kitty issue referenced in plan only as known-rc-quirk. Not triggered in this mission run. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`), `not-applicable` (issue referenced as context only; mission has no scope to close or fix it).

## Pre-`done` resolution plan

Two `in-mission` verdicts must reach terminal state before mission `done`:

- **#592** → `fixed` after merge (the new byte format is live on all 4 cron-firing surfaces + tasker source).
- **#557** → `fixed` after WP02 T010 rebaseline command runs and merge commit records `Rebaseline: completed at <ts>`.

All other rows are terminal already.
