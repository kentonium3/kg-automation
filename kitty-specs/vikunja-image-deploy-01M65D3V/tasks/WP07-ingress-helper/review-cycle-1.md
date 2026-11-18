---
affected_files: []
cycle_number: 1
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T04:38:20Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP07
---

# WP07 review cycle 1 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES

1. **HIGH — Ingress cannot run on the supplied host state.** [scripts/vikunja/stage_release_archive.py:148](scripts/vikunja/stage_release_archive.py#L148) rejects a missing `release-artifacts` parent in both modes, but nothing creates it. Given that office2 lacks this directory, deviation 2 makes the intended transfer unreachable. Create the parent safely as `claude`, while preserving create-only `mkdir` for the release-specific directory, or establish an explicit provisioning prerequisite in the design and operator workflow.

2. **HIGH — Cleanup defeats noclobber protection by deleting an existing file.** [scripts/vikunja/stage_release_archive.py:198](scripts/vikunja/stage_release_archive.py#L198) unconditionally calls `_remove()` after a nonzero stream result. If another writer creates the file before the redirection, noclobber correctly refuses—but cleanup deletes that writer’s file. An in-memory reproduction using the committed fake confirmed this: `INGRESS_TRANSFER_FAILED`, followed by disappearance of the preexisting file. Track creation ownership remotely and only clean up files created by this transfer. Add a collision regression with a successful transfer control.

3. **MEDIUM — Several refusal tests lack the required same-fixture positive controls.** These include [tests/deploy/test_vikunja_stage_release_archive.py:302](tests/deploy/test_vikunja_stage_release_archive.py#L302), [:324](tests/deploy/test_vikunja_stage_release_archive.py#L324), [:340](tests/deploy/test_vikunja_stage_release_archive.py#L340), and [:358](tests/deploy/test_vikunja_stage_release_archive.py#L358). Separate happy-path tests do not satisfy the explicit requirement. Demonstrate success with the same setup before changing only the condition under test.

The remaining reviewed mechanics look sound: remote paths are constrained and shell-quoted; SSH targets only `office2-claude`; production subprocess calls have explicit timeouts, with transfer/hash limits scaled by size; and public output uses the shared allowlist. Bypassing `core.run` for streaming stdin is reasonable: it preserves argv execution without a local shell, captured output, timeouts, and private error handling.

Deviation 4 matches the prompt’s file-only mismatch cleanup: retaining the verified first archive and directory is acceptable, though reruns require operator cleanup.

Validation was read-only: static review and in-memory fake-runner probes. Full pytest was not run because it writes fixtures and pytest was unavailable. No network, SSH, or Docker calls were made.

**REQUEST CHANGES**

## Orchestrator disposition
1: In --apply, create the parent /data/services/vikunja/release-artifacts if it is absent, with 'umask 077 && mkdir' (no -p; its parent /data/services/vikunja exists, claude:claude 775). Then verify that it is a real folder (not a symlink), owned by uid claude, mode 0700. Refuse INGRESS_DEST_PARENT_UNSAFE otherwise. The per-sha folder stays create-only. The dry run reports whether the parent will be created. 2: The stream creates the file with noclobber inside the per-sha folder that this run created (create-only mkdir), so only this run can have created files there. Still, track ownership: only remove a file if this run's mkdir created the folder and this run's stream started the write; never remove after a noclobber refusal (detect it as a distinct exit or stderr, INGRESS_DEST_FILE_EXISTS). Add the collision regression with a success control. 3: Add same-fixture positive controls to the named tests.
