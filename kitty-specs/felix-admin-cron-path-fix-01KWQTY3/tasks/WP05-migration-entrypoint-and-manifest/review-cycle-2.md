---
affected_files: []
cycle_number: 2
mission_slug: felix-admin-cron-path-fix-01KWQTY3
reproduction_command:
reviewed_at: '2026-07-05T04:08:00Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP05
---

**Issue 1: Existing target state paths are treated as compliant without repairing permissions/ownership.**

`scripts/deploy/migrate-inbox-state-and-logs.py` returns immediately when `/data/services/openclaw/state/` already exists (`_ensure_target_state_dir`, lines 180-184), so a pre-existing directory with the wrong mode/group remains wrong. `_copy_state_files` also skips an identical pre-existing target file without applying `claude:secondbrain` and `0640` (lines 243-255). This violates FR-012 / contract C2c+C5, which require the migration to ensure the state directory is `claude:secondbrain 0750` and migrated files are `claude:secondbrain 0640`, including idempotent reruns after a partial run.

Fix: make the apply path convergent. For existing target directories/files, verify and repair mode and group/owner where possible, and fail loudly if production ownership cannot be made compliant. Add tests that start with an existing target directory and an identical target state file carrying non-compliant modes and assert a rerun corrects them.

**Issue 2: Ownership failures are non-fatal and the manifest does not verify owner/group.**

`_set_permissions` catches `PermissionError`/`OSError` from `shutil.chown` and only emits a warning (lines 165-173). On office2 this can let the migration exit 0 with files that are not `claude:secondbrain`, especially because the manifest post check only asserts mode `0640` (deploys/queued/0007-migrate-inbox-state-and-logs.yaml lines 11-17). The WP and contract require `claude:secondbrain`, not just best-effort chmod.

Fix: make production ownership setting fail the migration when it cannot meet the contract, while preserving a deliberate test/development escape if needed. Update `verification.post` to assert owner, group, and mode for `/data/services/openclaw/state/` and migrated state files.

**Issue 3: The Tier-2 manifest post checks are weaker than the required decommission/parity checks.**

The WP requires `verification.post` to assert state files present and non-empty with `claude:secondbrain 0640`, historical logs present in the vault, the stray path gone or quarantined, and a parity check proving nothing unclassified was dropped. The committed manifest only checks `inbox-routing.jsonl` exists and has mode `0640`, the vault logs directory exists, and `/home/claude/second-brain` does not exist (deploys/queued/0007-migrate-inbox-state-and-logs.yaml lines 10-19). It does not verify owner/group, does not verify actual historical log contents/counts, does not verify a quarantine directory exists when the original path is gone, and has no size/count parity check.

Fix: strengthen `verification.post` so it checks the full C5 postcondition. At minimum, assert owner/group/mode on the state directory and every migrated state file, verify expected vault log files/counts or a migration-produced manifest/parity report, and verify decommission state is an explicit quarantine/removal outcome rather than just absence of the source path.

**Issue 4: WP05 review rejection affects dependent WP06.**

WP06 depends on WP05. Its agent should rebase/re-evaluate after the migration entrypoint and manifest fixes land.

Anti-pattern checklist:

1. Dead code: PASS. The new entrypoint is referenced by the Tier-2 deploy manifest; no unused public production module surface found.
2. Synthetic-fixture test: PASS. The WP tests invoke the production `main()` path rather than asserting over hand-built output.
3. Silent empty return: PASS. No `return ""`, `return None`, `return []`, `return {}`, or bare `pass` found in the new script.
4. FR coverage: FAIL. FR-012 ownership/mode and FR-008 parity/post-verification behavior are not fully asserted.
5. Frozen surface: PASS. No frozen/untouchable file touched by the WP-owned commit was found.
6. Locked decision: FAIL. The implementation/manifest do not satisfy the C5 `MUST` postconditions for owner/group and parity.
7. Shared-file ownership: PASS. WP05-owned files are not shared in `lanes.json`.
8. Production fragility: PASS. No new unreasoned production `raise` found in the WP05 entrypoint.
