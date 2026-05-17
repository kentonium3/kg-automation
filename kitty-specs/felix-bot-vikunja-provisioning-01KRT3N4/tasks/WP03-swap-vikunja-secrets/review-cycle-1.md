---
affected_files: []
cycle_number: 1
mission_slug: felix-bot-vikunja-provisioning-01KRT3N4
reproduction_command:
reviewed_at: '2026-05-17T05:32:41Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
---

**Issue 1**: Post-swap verification does not prove Felix/gateway write attribution. `verify_attribution()` only performs `GET /api/v1/tasks/{task_id}` and compares that task object's `created_by.username` to the expected user. A task's `created_by` is the historical creator of that task, not proof that the rotated gateway token caused a new Felix write to be attributed to `felix-bot`. This can falsely pass whenever the configured task was originally created by `felix-bot`, even if the gateway is still writing comments as `kent`. FR-008 and contract C-11 require invoking a sample Felix agent/comment write after the secrets swap, then reading back the written comment and asserting that comment's `created_by.username == 'felix-bot'`. Fix by implementing the actual post-swap write/readback probe, or invoking the gateway/Felix command that writes the sample comment and then verifying the resulting comment attribution. Update tests so a plain pre-existing task `created_by` match is insufficient, and so the happy path proves the newly written comment attribution.

**Issue 2**: `atomic_write_file()` does not preserve the required `claude:claude` ownership invariant. The WP explicitly requires `atomic_write_file(path, content_bytes, mode=0o600, owner='claude', group='claude')` and the file invariants require both the live secret and `.bak` to remain mode `600`, owner/group `claude:claude`. The current implementation only accepts `path`, `content_bytes`, and `mode`; it never resolves or calls `os.chown` on the temp file before rename. If the helper is run as root, the rotated secret and backup become root-owned after rename, which violates the operational invariant and can break later gateway access or rollback. Fix by adding owner/group handling, applying `chown` to the temp file before rename when appropriate, and adding tests that assert the temp-file permission/ownership operations happen before `os.rename`.

WP05 depends on WP03. Downstream agents should rebase after these fixes land.
