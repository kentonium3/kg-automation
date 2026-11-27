---
affected_files: []
cycle_number: 1
mission_slug: delivery-doctrine-followups-01M8FBH0
reproduction_command:
reviewed_at: '2026-11-27T21:14:27Z'
reviewer_agent: claude
wp_id: WP03
---

# WP03 review feedback, round 1

**Reviewer:** Codex gpt-6.1-sol (read-only), 2026-11-27, independent of the implementer (python-pedro, claude-sonnet-5-5). **Lead triage:** claude-opus-5-5.
**Range reviewed:** 32009aa5c..c59f9f7a7. **Verdict:** REQUEST CHANGES.

Fix all three items, adding a test for each that fails before the fix.

1. **MAJOR: a retry can hide a failed reload** (`scripts/deploy/deploy-announce-agent-tool-deny.py` ~L494).
   - **Problem:** after the patch persists, a missing reload acknowledgement fails the first apply, as it should. But a retry returns success just because the deny arrays exist, and the post-check only looks at persisted config. Codex reproduced this in memory: exit 1, then exit 0, with no acknowledgement either time. The deployer retries failed manifests, so this can happen in normal use.
   - **Fix:** record the reload verification separately, for example a `reload_verified` field in the receipt. A retry that finds the deny already persisted but the receipt not marked reload-verified must re-establish runtime confirmation before it succeeds: a fresh acknowledgement after the persisted change, or the effective-tools check showing the denied tools absent. Otherwise it fails.
   - **Tests:** failure→retry for a missing acknowledgement, and for restart-required.
2. **MINOR: `--verify` passes without hash protection** (~L549).
   - **Problem:** with no receipt, verify reports PASS and skips the non-target comparison the manifest relies on.
   - **Fix:** fail verify when the receipt is missing or its baseline hashes are incomplete. Test the refusal, with a passing control.
3. **MINOR: an existing receipt is barely validated** (~L329).
   - **Problem:** the loader does not check the schema, the deny set, hash completeness, or whether the saved originals belong to the current state. A stale receipt could restore obsolete settings, and a malformed `present: true` entry can load and then crash rollback.
   - **Fix:** validate the full receipt, and reconcile it against the current state (original or patched) before any change; refuse otherwise.
   - **Tests:** a stale receipt and a malformed value.

**Kept as-is (passed):** manifest fields, schema validity and rollback notes; config JSON shapes and patch parsing (checked against upstream source); refusal controls; collateral-change and PID-change coverage; no dead code; ownership.
