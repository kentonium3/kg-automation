---
affected_files: []
cycle_number: 1
mission_slug: 026-vault-path-registry-and-folder-renumber
reproduction_command:
reviewed_at: '2026-04-11T05:21:23Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP02
---

**Issue**: WP02's original implementation was byte-fidelity-correct against the baseline it saw, but that baseline was CORRUPTED. A pre-existing repo regression — undiscovered until mission 026 WP04 surfaced it — meant the `.tmpl` sources WP02 generated were derived from content that differed from the authoritative office2 production state. WP02 is being re-opened to regenerate its artifacts against the reconciled baseline. This is not a rejection of WP02's original review quality; the review was correct on the evidence it had.

**Discovery**: During mission 026 WP04 execution (pre-rename deploy + refactor-fidelity checkpoint), the file-level fidelity check compared lane-a hashes against office2 hashes for all files in `scripts/vault/targets.json` that have an `office2_path`. Four files had mismatched hashes:

- `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`
- `scripts/openclaw/agents/felix-admin-capture/USER.md`
- `scripts/openclaw/agents/felix-admin-escalation/USER.md`
- `scripts/openclaw/agents/felix-admin-habits/USER.md`

Investigation revealed two separate pre-existing drift sources (see #156 for full root-cause analysis):

1. **`felix-admin-capture/TOOLS.md`** was missing 18 lines — the entire `## GitHub` section with CLI, skill, and label taxonomy references. Mission 022 WP02 (commit `0a1cfb6`) had added this content, but mission 023's specify commit `8c1054c` silently stripped it. The AGENTS.md portion of that regression was later partially reconciled in `16c8c4d`, but the TOOLS.md portion was missed and remained regressed.

2. **`felix-admin-capture/USER.md`, `felix-admin-escalation/USER.md`, `felix-admin-habits/USER.md`** were each missing the same 8-line `## Date handling` section added to office2 during mission 025 work. That content was applied directly to office2 and never committed to the repo.

Lane-a's WP02 `.tmpl` sources were derived from the regressed main state, so they didn't include any of this content. The resolved outputs matched the original files byte-for-byte (NFR-001 satisfied on the corrupted baseline), but they didn't match what was actually running in production.

**Reconciliation applied before this re-run**:

- **Main reconciliation commit** `8c2bd2c` ("fix: reconcile felix-admin-{capture,escalation,habits} workspace files from office2 [doc-audit]"): captured the 4 drifted files from office2 verbatim (SHA256-verified) and committed them to main as Phase 1 of the #156 reconciliation workstream.
- **Lane-a merge commit** `dfd46d9` ("Merge main into lane-a for mission 026 reconciliation"): merged main's reconciliation into lane-a. Clean auto-merge, zero conflicts (expected — WP02's original commit was a pure refactor, so lane-a hadn't diverged from the baseline for these 4 files).

After these commits, lane-a now has the authoritative content for all 4 files. The file hashes match office2 exactly.

**What this WP02 re-run needs to do**:

1. **Regenerate `felix-admin-capture/TOOLS.md.tmpl`** from the newly-reconciled `TOOLS.md`. The existing `{{VAULT_INBOX}}` marker on line 6 stays. The 18 new lines (GitHub section) contain no vault-path literals, so no additional markers are needed there. Net effect: 18 lines added to the `.tmpl` source, one existing marker preserved.

2. **Regenerate `felix-admin-capture/USER.md.tmpl`** as a byte-identical copy of the new `USER.md`. The original WP02 implementation made this a byte-identical copy because the file only contained relative-path references (category-2 residue discussed during the original WP02 review). The new 8 lines (Date handling section) don't reference any vault folder, so the byte-identical-copy approach still applies. No markers needed.

3. **Confirm `felix-admin-escalation/USER.md` and `felix-admin-habits/USER.md` remain OUT of the migration audit.** The original WP02 audit correctly excluded them because they contained no vault-path literals and therefore didn't need `.tmpl` sources. The Date handling additions don't change that conclusion — the new content also contains no vault-path literals. These files stay as regular (non-templated) files with no entry in `targets.json`.

4. **Re-run `deploy.py --apply`** and re-verify byte-fidelity of the 7 target output files against the reconciled baseline.

5. **Re-run the WP02 acceptance grep checks** — zero stale vault-folder literals outside documented exclusions, zero unknown markers in `.tmpl` sources.

6. **Update the WP01 migration-targets audit artifact** (`kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp01-migration-targets.md`) with a note about the reconciliation so the audit record matches what's actually in lane-a.

7. **Amend the WP02 commit (or add a follow-up commit)** that replaces the original `.tmpl` files with the regenerated versions. Commit message should reference #156 and the reconciliation workstream.

**Expected outcome**: WP02 approves again, with `.tmpl` sources matching the reconciled baseline, and all WP02 success criteria re-satisfied. Then WP03 may need a light touch-up review (docs that reference agent content), WP04 can run and actually pass the fidelity check, and mission 026 proceeds as originally planned.

**What this re-run does NOT need to do**:
- Does not need to touch WP01's outputs (`paths.json`, `targets.json`, `deploy-f026.sh`) — those are unaffected by the content drift
- Does not need to re-execute every WP02 subtask from scratch — only the `.tmpl` regeneration for the 2 affected files, the deploy verification, and the acceptance grep
- Does not need to modify any files outside WP02's owned_files list — the reconciliation already placed the correct content in the repo; this re-run just aligns the `.tmpl` sources with it

**References**:
- #156 — parent drift investigation and reconciliation plan
- #157 — main-agent governance gap (Phase 2, deferred)
- `8c2bd2c` — Phase 1 reconciliation commit on main
- `dfd46d9` — lane-a merge commit bringing reconciliation into lane-a
- Original WP02 commit: `71c664c`
