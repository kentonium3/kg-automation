---
affected_files: []
cycle_number: 3
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T04:49:25Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP07
---

# WP07 review cycle 3 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (1 HIGH, 2 MEDIUM)

Cycle-2 findings:

1. Parent creation and verification: **RESOLVED**.
2. Cleanup ownership: **RESOLVED** under the approved nonce-name design; cleanup targets only this run’s part.
3. Same-fixture success controls: **RESOLVED**.
4. Timeout cleanup deleting a competing final: **RESOLVED**.

New findings:

- **HIGH — `scripts/vikunja/stage_release_archive.py:311`:** Plain `ln -- <part> <final>` treats an existing directory or symlink to a directory as a container. A concurrent directory creation after precheck therefore yields success, removes the part, and ultimately reports `INGRESS_APPLIED` although the final path is not an archive. Use `ln -T --` and cover both directory collision cases.
- **MEDIUM — `scripts/vikunja/stage_release_archive.py:318`:** A timeout or execution failure during the collision probe escapes without cleaning up the part or reporting `INGRESS_PART_KEPT`.
- **MEDIUM — `scripts/vikunja/stage_release_archive.py:324`:** A timeout or execution failure during part removal bypasses both `INGRESS_PART_KEPT` and `INGRESS_PART_REMOVE_FAILED`. Handle raised failures as well as nonzero return codes.

The separate SSH calls, stderr reporting, new codes, and injectable nonce are reasonable deviations, subject to these fixes.

Validation: static inspection and in-memory failure probes with a success control. No files edited; no network, SSH, Docker, or pytest execution.

**REQUEST CHANGES**
