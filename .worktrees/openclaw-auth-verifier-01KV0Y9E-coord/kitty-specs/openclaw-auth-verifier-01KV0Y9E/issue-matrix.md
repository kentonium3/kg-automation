# Issue matrix — openclaw-auth-verifier-01KV0Y9E

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #596 | Bug: felix-admin-capture cron failures — `invalid x-api-key` after OpenClaw 2026.6 doctor --fix imports stale per-agent key | in-mission | WP01 (detection) + WP02 (--repair) + WP03 (rotation-script verify gate) prevent recurrence; verifier surfaces shadow rows the doctor migration can plant |
| #591 | OpenClaw 2026.6 auth-store migration + anthropic-rotate.sh (post-incident capture) | in-mission | WP03 extends `anthropic-rotate.sh` with the post-rotation verify gate and `--rollback <ts>` mode |
| #557 | Rebaseline obligation (audited surfaces) | in-mission | Merge commit will record `Rebaseline: completed at <ts>` per spec FR-017; scripts/security/ is an audited surface |
| #343 | felix-doc-auditor scripts-first driver | verified-already-fixed | Driver shipped 2026-05; referenced as plaintext-file consumer in spec § Context and credential-manifest.json |
| #490 | felix-heartbeat-gate | verified-already-fixed | Gate shipped 2026-05; referenced as plaintext-file consumer in spec § Context and credential-manifest.json |
| #597 | Hardening: pre-flight verifier for OpenClaw auth | in-mission | This mission IS the issue's deliverable; WP01-WP04 collectively close it |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).

## Pre-`done` resolution plan

The four `in-mission` verdicts above (#596, #591, #557, #597) MUST be resolved to terminal verdicts before the mission moves to `done` per the spec-kitty gate. The expected terminal transitions at merge:

- #596 → `verified-already-fixed` (immediate stopgap already shipped; verifier prevents recurrence)
- #591 → `verified-already-fixed` (rotation script extension landed via WP03)
- #557 → `fixed` (rebaseline status recorded in merge commit)
- #597 → `fixed` (the verifier shipped end-to-end)
