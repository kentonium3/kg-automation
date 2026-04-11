---
work_package_id: WP06
title: Cross-Repo Privacy Boundary and Mission Close-Out
dependencies:
- WP05
requirement_refs:
- FR-006
- C-001
- C-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T034
- T035
- T036
- T037
history:
- date: '2026-04-11T01:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: kitty-specs/026-vault-path-registry-and-folder-renumber/research/
execution_mode: planning_artifact
owned_files:
- kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp06-mission-closeout.md
tags: []
---

# WP06: Cross-Repo Privacy Boundary and Mission Close-Out

## Objective

Complete the cross-repository privacy boundary reinforcement by adding `_private/` to `~/second-brain/.gitignore`, running the idempotent `git rm --cached -r _private/` as future-proofing insurance, committing, and pushing in the second-brain repo. Then perform final mission verification against all 10 Success Criteria from `spec.md` and close GitHub issue #152 with the merge commit reference.

**This is an operator-only WP.** No agent touches the second-brain repository. Every step is manual. The WP description is a crystal-clear operator runbook.

## Context

- WP05 is complete: the vault is renumbered, the deploy is done, `felix-admin-capture` and `felix-admin-tasker` are confirmed running on the new paths, and the operator has explicitly authorized WP06 entry
- `_private/` is currently empty (per operator confirmation during discovery) — the `git rm --cached` command is idempotent insurance, not a functional operation
- Kent has explicitly authorized cross-repository operations (operator comment during planning Q1)
- The path `_private/` is a constitutional hard limit (C-001); no agent or script reads its contents. The gitignore edit references the path by name but does NOT read anything inside it
- After this WP, the mission is ready for `/spec-kitty.review` and `/spec-kitty.merge`

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP06 --agent <name>` (but the agent primarily records and verifies — the operator performs the cross-repo work)
- Execution: single lane worktree, dependency on WP05

## Contracts

- [../contracts/verification-contract.md](../contracts/verification-contract.md) — WP06 acceptance tests

---

## Subtask T034: Execute cross-repo operation in `~/second-brain/`

**Purpose:** Add `_private/` to the second-brain repo's `.gitignore` and run the idempotent cached-removal command. This operation is executed entirely by the operator.

### Operator Runbook

This entire subtask is executed by the operator on the Mac. No agent involvement.

**Step 1: Switch to the second-brain repo**
```bash
cd ~/second-brain
pwd
# Expected: /Users/kentgale/second-brain
```

**Step 2: Confirm the repo is in a clean state before editing**
```bash
git status
# Expected: "nothing to commit, working tree clean"
# If not clean: investigate. Do NOT edit .gitignore until the repo is clean.
# There may be legitimate in-progress work in the second-brain repo that shouldn't be mixed with this edit.
```

**Step 3: View the current .gitignore**
```bash
cat .gitignore
# Note what's already there. Do NOT remove existing entries.
```

**Step 4: Append the _private/ entry**
```bash
echo '' >> .gitignore
echo '# Privacy boundary — constitutional hard limit (kg-automation mission 026)' >> .gitignore
echo '_private/' >> .gitignore
```

**Step 5: Verify the entry was added correctly**
```bash
tail -5 .gitignore
# Expected: shows the three lines just appended
```

**Step 6: Verify the ignore rule matches (test with a hypothetical path)**
```bash
git check-ignore -v _private/test-file.md
# Expected output:
# .gitignore:<line-number>:_private/  _private/test-file.md
# (The line number depends on where _private/ ended up in .gitignore)
#
# If NO output: the rule is not matching. Check the pattern.
```

**Step 7: Run the idempotent cached-removal command**
```bash
git rm --cached -r _private/ 2>&1 || true
# Expected today: "fatal: pathspec '_private/' did not match any files"
# because _private/ is empty. That's OK — the `|| true` swallows the exit code.
#
# If output says "rm 'path/to/file'": something was cached. That's fine;
# the cached-removal handled it.
#
# If output is an unexpected error: investigate before proceeding.
```

**Step 8: Check git status**
```bash
git status
# Expected: .gitignore is modified, no other changes
```

**Step 9: Stage and commit**
```bash
git add .gitignore
git commit -m "$(cat <<'EOF'
chore: gitignore _private/ privacy boundary

Add _private/ to .gitignore so future content placed under this
constitutional privacy-boundary path does not enter git history
by default. Run git rm --cached -r _private/ as idempotent
future-proofing (currently a no-op — _private/ is empty).

Related: kentonium3/kg-automation#152 (mission 026)
EOF
)"
```

**Step 10: Push**
```bash
git push
# Expected: clean push to origin
```

**Step 11: Return to the kg-automation repo**
```bash
cd /Users/kentgale/repos/kg-automation
pwd
# Expected: /Users/kentgale/repos/kg-automation
```

**Step 12: Record the completion in the runlog artifact**
- Open `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp06-mission-closeout.md`
- Add a section recording the cross-repo operation: timestamp, commit hash from second-brain, a note that the `git rm --cached` was a no-op because `_private/` is empty

**Validation:**
- [ ] `~/second-brain/.gitignore` contains the `_private/` entry
- [ ] Commit exists in second-brain repo with the exact message above
- [ ] Commit is pushed to origin
- [ ] `git check-ignore` confirms the rule is active
- [ ] `git status` in second-brain is clean after the push
- [ ] Operator is back in the kg-automation directory
- [ ] Runlog records the operation with timestamp and commit hash

---

## Subtask T035: Verify `_private/` gitignore effectiveness

**Purpose:** Confirm the gitignore rule is actually working by testing with a hypothetical path.

**Steps:**

1. From the kg-automation repo (already there from T034 step 11), verify the rule is effective in the second-brain repo:
   ```bash
   cd ~/second-brain
   git check-ignore -v _private/some-test-file.md
   # Expected output: .gitignore:<N>:_private/  _private/some-test-file.md
   #
   # If empty output: rule is NOT matching. Go back to T034 and fix.
   ```

2. Optionally (if you want to test with a real file — entirely optional, just additional confidence):
   ```bash
   cd ~/second-brain
   mkdir -p _private
   touch _private/.test-gitignore
   git status
   # Expected: clean — .test-gitignore is ignored
   rm _private/.test-gitignore
   rmdir _private  # only if _private/ is still empty
   ```
   If `_private/` was already created somewhere, do NOT remove it with `rmdir`. Leave it as-is.

3. Return to kg-automation:
   ```bash
   cd /Users/kentgale/repos/kg-automation
   ```

4. Record the verification result in the runlog.

**Validation:**
- [ ] `git check-ignore` returns a positive match for a hypothetical file under `_private/`
- [ ] Runlog records the verification
- [ ] Operator is back in kg-automation

---

## Subtask T036: Final mission verification against all 10 Success Criteria

**Purpose:** Walk through every success criterion from `spec.md` § Success Criteria and confirm it's met. This is the mission's final quality gate before merge.

**Steps:**

1. Open `spec.md` and locate the Success Criteria section.

2. For each of the 10 criteria, execute the verification and check the box in the runlog:

   | # | Criterion | How to verify |
   |---|---|---|
   | 1 | Registry completeness | `python3 scripts/vault/resolver.py <each_name>` for all 10 logical names returns a valid path |
   | 2 | Reference hygiene | Repo-wide grep for old folder literals in production files returns zero hits outside the CLAUDE.md `_private/` boundary (which has been updated to `04-Growth/_private/` in WP05) |
   | 3 | Folder renumbering | `ssh office2-claude 'ls /home/kgale/second-brain/notes/'` shows the 10-folder sequence 00-System, 01-Inbox, 02-Inbox-Processed, 03-Constitution, 04-Growth, 05-Health, 06-Business, 07-Finance, 08-Journal, 09-Resources |
   | 4 | Processed-inbox folder | `ssh office2-claude 'ls /home/kgale/second-brain/notes/02-Inbox-Processed/'` exists and contains the `.gitkeep` |
   | 5 | Agent integrity | Both smoke tests from WP05 passed (already verified); spot-check by invoking each agent once more if desired |
   | 6 | Cron continuity | `ssh office2-claude 'crontab -l \| grep felix-admin-capture'` shows the entry UNCOMMENTED; it has fired at least once since re-enable |
   | 7 | Wikilink integrity | Obsidian Unresolved Links panel shows no new entries attributable to this mission (operator spot-check) |
   | 8 | Privacy boundary reinforcement | `cd ~/second-brain && git check-ignore -v _private/test.md` returns a positive match |
   | 9 | Documentation currency | `validate_docs.py` passes; spot-check of 2-3 architecture JSON files shows they reference new folder names |
   | 10 | Mission #149 unblocked | The spec for mission 026 has been satisfied; #149's prerequisites (registry markers + physical folder) are in place |

3. For each criterion, record in `wp06-mission-closeout.md`:
   - Criterion number and title
   - Verification command used
   - Result (PASS / FAIL)
   - Any notes

4. **If any criterion FAILS:** do NOT close the issue or proceed to merge. Investigate, remediate, and re-verify. A failed criterion at this stage indicates an earlier WP missed something and must be fixed.

5. **If all 10 criteria PASS:** proceed to T037.

**Validation:**
- [ ] All 10 success criteria verified
- [ ] Every criterion has PASS result recorded
- [ ] Runlog contains the verification commands and results

---

## Subtask T037: Close GitHub issue #152

**Purpose:** Close the source issue with a reference to the mission merge commit and a summary of what shipped.

**Steps:**

1. Confirm WP06 is otherwise complete (T034, T035, T036 all done and verified).

2. The mission branch has not been merged yet — merge happens via `/spec-kitty.merge` after this WP closes. So the merge commit hash is not yet available. T037 has two sub-steps:

   **Sub-step 2a (before mission merge):** Draft the closure comment. Include a placeholder for the merge commit hash:
   ```
   Mission 026 complete. This issue is being closed by the mission merge.

   **What shipped:**
   - Vault path registry extended to all 10 top-level vault folders
   - Folder renumbering: clean 00-09 ordinal sequence, `00-` collision fixed
   - New `02-Inbox-Processed/` folder created (unblocks #149)
   - All hardcoded vault references migrated to `{{VAULT_*}}` template markers
     (except the `_private/` constitutional boundary)
   - `_private/` gitignored in the second-brain repo
   - Full documentation synchronization including new migration runbook

   **Mission artifacts:** `kitty-specs/026-vault-path-registry-and-folder-renumber/`

   **Follow-ups:**
   - #149 (inbox pre-scan helper) is now unblocked and can enter spec-kitty
   - #154 (charter amendment: shared deploy primitives) is open and independent

   Merge commit: <MERGE_COMMIT_HASH>
   ```

3. **Sub-step 2b (after mission merge — this is a post-merge action that happens during or after `/spec-kitty.merge`):** close the issue with the finalized comment:
   ```bash
   gh issue close 152 --repo kentonium3/kg-automation \
     --comment "<finalized comment with actual merge commit hash>"
   ```

4. Verify the issue is closed:
   ```bash
   gh issue view 152 --repo kentonium3/kg-automation --json state,closedAt
   ```

5. Record the closure in the runlog (T036's artifact or a new closeout section).

**Validation:**
- [ ] Closure comment drafted and ready
- [ ] Issue #152 closed (after merge) with the finalized comment
- [ ] `gh issue view` confirms state: CLOSED
- [ ] Runlog records the closure

**NOTE:** T037 sub-step 2b may be executed during `/spec-kitty.merge` rather than during WP06 depending on your workflow. If so, the WP06 Definition of Done can include "closure comment drafted" without requiring the actual `gh issue close` call to happen within WP06.

---

## Definition of Done

- [ ] Cross-repo operation completed in `~/second-brain/` (.gitignore edit + idempotent cached removal + commit + push)
- [ ] `_private/` gitignore rule verified effective via `git check-ignore`
- [ ] All 10 success criteria from `spec.md` verified as PASS
- [ ] WP06 runlog (`wp06-mission-closeout.md`) created with all results
- [ ] GitHub issue #152 closure comment drafted (closure itself may happen during `/spec-kitty.merge`)

## Risks

- **`_private/` directory doesn't exist in the second-brain repo at all** (never created). Mitigation: the gitignore rule is still valid — it'll match if/when `_private/` is ever created. The `git rm --cached` is a no-op. Document in the runlog and proceed.
- **Operator forgets to return to kg-automation after the second-brain work.** Mitigation: T034 step 11 explicitly says to `cd` back. T037 validates via `pwd` at the start.
- **Success criterion #7 (Obsidian wikilink integrity) cannot be mechanically verified.** Mitigation: operator spot-checks 2–3 notes manually. Obsidian's Unresolved Links panel is the primary signal.
- **Success criterion #10 (mission #149 unblocked) is subjective.** Mitigation: confirm the registry resolves `inbox_processed` AND the physical folder exists on office2. That's the concrete test.
- **Operator closes issue #152 prematurely (before merge).** Mitigation: T037 explicitly splits into draft-before-merge and close-after-merge. If accidentally closed early, re-open and re-close after merge with updated comment.

## Reviewer Guidance

The reviewer should confirm:

- The cross-repo operation left the second-brain repo in a clean state (check with `cd ~/second-brain && git status`)
- The commit message in second-brain matches the conventional format
- `git check-ignore` returns a positive match for a hypothetical `_private/` path
- All 10 success criteria have PASS records in the runlog
- The GitHub issue #152 closure comment (draft or actual) includes the #149 unblocking note and the #154 reference
- No files under `_private/` were read or referenced during the operation
- The runlog artifact is complete and honest — not a sanitized "everything's fine" report
