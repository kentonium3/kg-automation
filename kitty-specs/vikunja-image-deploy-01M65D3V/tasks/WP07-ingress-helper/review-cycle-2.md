---
affected_files: []
cycle_number: 2
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T04:44:24Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP07
---

# WP07 review cycle 2 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES

Cycle-1 findings:

1. **RESOLVED.** Apply creates the missing parent using `umask 077 && mkdir`, verifies directory/type/owner/mode, and retains create-only creation of the release folder. Dry run reports the planned parent action.
2. **NOT RESOLVED.** Recognized noclobber refusals now preserve the competing file, with regression controls. However, cleanup still lacks proof that this transfer created the file.
3. **RESOLVED.** The named refusal tests now have same-fixture success controls; the obsolete missing-parent refusal was replaced by creation and safety coverage.

Stated deviations:

1. **Acceptable:** `parent_code=EXISTS|CREATE` complies with the shared output allowlist; an in-memory emit probe confirmed it.
2. **Acceptable:** fixed owner name `claude` matches the prescribed SSH account and host contract.
3. **Unacceptable:** mode 0700 excludes other users, but does not exclude concurrent writers running as `claude`. Directory creation alone does not establish file ownership.

Additional finding:

- **HIGH — Timeout cleanup bypasses noclobber detection**, [stage_release_archive.py:266](/home/kgale/repos/kg-automation-vikunja-deploy/.worktrees/vikunja-image-deploy-01M65D3V-lane-g/scripts/vikunja/stage_release_archive.py:266). The timeout handler removes the file even when `TimeoutExpired.stderr` contains the recognized noclobber message. An in-memory fake-runner probe confirmed deletion of the competing file. Thus the gap also occurs **with** a noclobber diagnostic. Establish remote file-creation ownership before cleanup; add timeout/collision coverage.

Validation used static inspection and in-memory probes with a success control. No files were edited; no network, SSH, or Docker calls were made. Full pytest was not run because its fixtures write files.

**REQUEST CHANGES**

## Orchestrator disposition
Prove ownership by name. Stream into <dest>/.<name>.<nonce>.part (a 128-bit nonce from secrets.token_hex(16), created with noclobber, so only this run can have created it). Verify the remote sha on the .part file. Publish it with 'ln <part> <final> && rm <part>'; ln fails if <final> exists, giving INGRESS_DEST_FILE_EXISTS and keeping both files. Cleanup on any failure, including a timeout, removes ONLY this run's .part path, never <final>.
