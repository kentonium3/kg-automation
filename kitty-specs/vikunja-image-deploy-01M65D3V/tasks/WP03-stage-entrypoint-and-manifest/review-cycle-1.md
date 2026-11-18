---
affected_files: []
cycle_number: 1
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T04:41:30Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP03
---

# WP03 review cycle 1 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (2 medium)

- **P2 — Post-load inspection errors bypass the required failure contract.** [deploy-vikunja-release-stage.py:207](scripts/deploy/deploy-vikunja-release-stage.py:207): if `core.image_facts()` raises, execution skips `STAGE_VERIFY_FAILED` and the `STAGE_LOADED_UNTAGGED` detail. An in-memory fake confirmed `DOCKER_INSPECT_FAILED` instead. Catch inspection failures, preserve private diagnostics, and report the required code and loaded ID. Add failure/recovery coverage.

- **P2 — Several refusal tests lack required positive controls.** [test_deploy_vikunja_release_stage.py:398](tests/deploy/test_deploy_vikunja_release_stage.py:398), also lines 424, 438, 445 and 511: unparseable output, load failure, timeout, tag failure and late marker arrival never repair the same fixture and demonstrate success. Add those controls.

Otherwise, static inspection supports read-only dry runs, load → verify → tag ordering, R-23 hold preservation, sequential retry idempotency, exact release/rollback manifest checks, tier 2, baseline declaration, mode handling and executable permission. No INV-1 violation identified in the prescribed sequential flow.

No files changed; no network, SSH or Docker used. Full pytest was not run because it writes fixtures.

**REQUEST CHANGES**
