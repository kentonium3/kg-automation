---
affected_files:
- scripts/deploy/migrate-inbox-state-and-logs.py
- tests/deploy/test_migrate_inbox_state.py
cycle_number: 3
mission_slug: felix-admin-cron-path-fix-01KWQTY3
reproduction_command: python3 -m pytest tests/deploy/test_migrate_inbox_state.py -q
reviewed_at: '2026-07-05T04:31:00Z'
reviewer_agent: codex:gpt-5-codex:reviewer-renata
verdict: rejected
wp_id: WP05
---

**Cycle-1 feedback status:** The prior blockers are materially resolved. The apply path now repairs modes on pre-existing target directories/files, production `chown` failures hard-fail unless the explicit test-only `--skip-chown` flag is used, and the deploy manifest post checks now verify owner/group/mode, vault log presence, quarantine, original path absence, and log-count parity.

**Issue 1: A mismatched pre-existing target state file can be treated as migrated, then the source can be quarantined.**

In `scripts/deploy/migrate-inbox-state-and-logs.py`, `_copy_state_files()` handles an existing destination with different content by warning and keeping the destination (`Target exists with different content — keeping target`), then appending the source file to `handled` and continuing. The main flow can then inventory the source as classified and quarantine `/home/claude/second-brain`.

That means a partial prior run, stale target file, or live append to `/home/claude/second-brain/agents/state/inbox-routing.jsonl` after an initial target copy can leave newer source ledger entries out of `/data/services/openclaw/state/inbox-routing.jsonl` while still allowing quarantine. This violates FR-005's requirement to migrate the live ledger with contents preserved, and the spec edge case requiring the migration not to lose ledger entries written between snapshot and cutover. It also weakens H1 because the new path may be stale even though readers are repointed to it.

Fix: make divergent source/destination state files a safe, explicit outcome. Either merge/reconcile append-only JSONL state so all source ledger entries are preserved at the target, or refuse to quarantine and exit non-zero with a clear remediation message when the destination differs. Add a test that pre-creates `target_state_dir/inbox-routing.jsonl` with stale or partial content, leaves a source ledger containing an additional entry, runs `--apply`, and asserts either:

- the target contains the source entry and the source can be quarantined, or
- the command exits non-zero and the source root remains unquarantined.

Do the same for `pending-calendar-clarifications.*` if those files are copied without a merge strategy.

**Dependent WP note:** WP06 depends on WP05. Its agent should rebase/re-evaluate after this fix lands.

Anti-pattern checklist:

1. Dead code: PASS. The new entrypoint is referenced by the Tier-2 deploy manifest.
2. Synthetic-fixture test: PASS. The tests invoke the production `main()` path.
3. Silent empty return: PASS. No undocumented silent empty returns found in the new entrypoint.
4. FR coverage: FAIL. FR-005/H1 ledger-preservation coverage does not cover the divergent pre-existing target case.
5. Frozen surface: PASS. No frozen/untouchable file touched by the WP-owned commits was found.
6. Locked decision: FAIL. The divergent-target behavior contradicts the spec's no-ledger-loss edge case.
7. Shared-file ownership: PASS. WP05-owned files are not shared in lane metadata.
8. Production fragility: PASS. The new `raise RuntimeError` path has a documented fail-loud ownership rationale.
