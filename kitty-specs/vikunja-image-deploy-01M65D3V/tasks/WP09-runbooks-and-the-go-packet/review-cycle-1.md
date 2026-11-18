---
affected_files: []
cycle_number: 1
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T05:58:11Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP09
---

# WP09 review cycle 1 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (3 HIGH, 4 MEDIUM, 1 LOW)

Reviewed locally against `e36d8271`, the specified lane branches, research R-9–R-24, and harness commit `ad7f0c8e3`. No files changed; no network, SSH, or Docker used.

All cutover references below are to `docs/runbooks/vikunja-release-cutover.md`.

- **HIGH — cutover:661:** Rollback retry assumes cleanup succeeded. Lane F’s cleanup is best effort and can leave the container running or `active` tagged. Repeating Kent’s restore could overwrite a live DB before the next guard runs. Require confirmed container absence and absent tag before restoring again, with recovery instructions for failed cleanup.

- **HIGH — cutover:483:** Migration summary counts are offered as an alternative to deriving each legacy task’s expected rule and flag. The approved acceptance checklist requires per-id expectations and comparisons, plus exact backup-table ids. Counts cannot establish correctness. Supply the conversion method and runnable B4 checks.

- **HIGH — cutover:589:** Pre-snapshot ACTIVATE failures have no recovery procedure. Replay refuses, STAGE cannot recreate `active`, and rollback requires a snapshot. The referral at line 575 to retry is circular because retry requires completed rollback. Define a reviewed recovery route before treating this as an executable go packet.

- **MEDIUM — cutover:720:** Retry assumes ACTIVATE remains queued. Section 9 mandates cancellation, while acceptance-triggered rollback follows an already-applied manifest. Archiving the marker starts nothing in either case. Document requeueing and restoration of the test/inventory changes through a Kent-merged commit.

- **MEDIUM — cutover:785:** Ingress retry instructions fail after destination creation. Lane G retains that directory, and subsequent preflight refuses with `INGRESS_DEST_EXISTS`. Removing a `.part` alone is insufficient. Document recovery for an empty or partially published destination.

- **MEDIUM — cutover:236:** Assembly requires a “clean clone,” but fetches only `main` before referencing the unpushed `feat/vikunja-image-deploy`. A fresh clone cannot resolve it. Specify an existing local repository containing the candidate, or provide an explicit local transfer pinned to the candidate SHA.

- **MEDIUM — `docs/runbooks/vikunja-ops.md:159`:** The agent-audience runbook still presents privileged `office2-kgale` commands without a Kent-only label. Explicitly assign these steps to Kent. This block predates WP09.

- **LOW — `docs/runbooks/deploy/discipline.md:552`:** Recorded failure phases are `entrypoint_dry_run` and `entrypoint_apply`, not `dry_run` and `apply`.

The five STAGE exclusions match `CUTOVER_PATHS` exactly. The merge steps remain Kent’s. Fresh-snapshot binding, data privacy, acceptance timing, and probe-write accounting are otherwise correct. No secrets or prohibited mentions were found.

Flagged gaps: **(a)** is blocking for `started`/`stopped` without a snapshot; `snapshotted` has guarded rollback. **(b)** is covered explicitly. **(c)** is accurately documented. **(d)** is stale, but changing the Compose header conflicts with the approved byte-identical two-line constraint. **(e)** causes the assembly issue above.

**REQUEST CHANGES**
