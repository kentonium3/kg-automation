---
work_package_id: WP05
title: Folder Rename and Post-Rename Deploy
dependencies:
- WP04
requirement_refs:
- FR-003
- FR-004
- FR-005
- NFR-002
- NFR-003
- NFR-004
- NFR-005
- C-005
- C-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T027
- T028
- T029
- T030
- T031
- T032
- T033
history:
- date: '2026-04-11T01:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: kitty-specs/026-vault-path-registry-and-folder-renumber/research/
execution_mode: planning_artifact
owned_files:
- kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp05-risky-window-runlog.md
tags: []
---

# WP05: Folder Rename and Post-Rename Deploy

## Objective

**This is the risky window.** The only WP in this mission that changes runtime state in an operator-visible way. Pause the `felix-admin-capture` cron, create `02-Inbox-Processed/`, rename 8 vault folders via the Obsidian UI one-at-a-time with inter-rename wikilink verification, update `scripts/vault/paths.json` and `CLAUDE.md`'s `_private/` boundary line to reflect the new folder names, run `deploy-f026.sh --apply --mode post-rename` (which internally performs the deploy, greps for residue, smoke-tests both agents, verifies wikilink integrity, re-enables the cron, and verifies the cron fires correctly), and finally hand off to WP06 for mission close-out.

**Total duration budget: 90 minutes** (NFR-004). If exceeded, the operator pauses to reassess rather than continuing blindly.

**This WP has operator review gates at entry AND at exit.** Do not start without explicit operator authorization from WP04. Do not proceed to WP06 without explicit operator authorization from WP05 completion.

## Context

- WP04 has proven refactor fidelity — the code changes are a pure refactor
- The operator has reviewed WP04's fidelity checkpoint and explicitly authorized WP05 entry
- Tier 2 change-risk classification applies (application state + vault folder structure)
- `felix-admin-capture` cron is currently enabled and running on its normal schedule — this WP pauses it
- This WP is operator-driven for most steps. Agents cannot rename Obsidian folders, cannot execute `ssh office2-claude` commands that manipulate the crontab (no sudo on that account, cron edits are unprivileged but require the operator's SSH session), and cannot make the Restic backup decisions
- The deploy wrapper (`scripts/deploy/deploy-f026.sh --apply --mode post-rename`) encapsulates the deploy + verification sequence into a single invocation, reducing operator toil

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP05 --agent <name>`
- Execution: single lane worktree, dependency on WP04

## Contracts

- [../contracts/deploy-wrapper-contract.md](../contracts/deploy-wrapper-contract.md) — `deploy-f026.sh` contract (post-rename mode)
- [../contracts/verification-contract.md](../contracts/verification-contract.md) — WP05 acceptance tests (20+ checks)

---

## Subtask T027: Tier 2 pre-flight — Restic backup verification

**Purpose:** Confirm a recent backup exists before modifying vault state. Per the change-risk taxonomy, this mission is Tier 2 (application state + vault folder structure) and requires a Restic snapshot ≤24 hours old.

**Steps:**

1. SSH to office2 and check the latest Restic snapshot:
   ```bash
   ssh office2-claude 'restic snapshots --last 1'
   ```
   Review the timestamp.

2. **If the most recent snapshot is ≤24 hours old:** record the snapshot ID in the WP05 runlog and proceed.

3. **If the most recent snapshot is >24 hours old:** trigger a new backup. The exact command depends on your backup runbook — consult `docs/runbooks/` for the canonical backup trigger. For example:
   ```bash
   ssh office2-claude '/path/to/restic-backup.sh'
   ```
   Wait for it to complete, then re-check `restic snapshots --last 1` to confirm the new snapshot.

4. **If Restic is unavailable or in a failed state:** STOP. Do not proceed to WP05. Investigate and restore the backup system before attempting the risky window.

5. Record the pre-flight result in the runlog artifact: snapshot ID, timestamp, verification timestamp, and a go/no-go decision.

**Validation:**
- [ ] Most recent Restic snapshot is ≤24 hours old
- [ ] Snapshot ID recorded in the WP05 runlog
- [ ] Backup system is healthy (no errors from `restic snapshots`)
- [ ] Operator has explicit go decision recorded

---

## Subtask T028: Pause `felix-admin-capture` cron on office2

**Purpose:** Stop the inbox agent from firing during the risky window. This is the entry point to the pause period.

**Steps:**

1. SSH to office2 and view the current crontab:
   ```bash
   ssh office2-claude 'crontab -l'
   ```
   Find the `felix-admin-capture` entry. Record its exact text in the runlog so you can restore it verbatim in T032.

2. Edit the crontab to comment out the `felix-admin-capture` entry. The simplest approach:
   ```bash
   ssh office2-claude 'crontab -l | sed "s|^\([^#].*felix-admin-capture.*\)|# WP05-PAUSED: \1|" | crontab -'
   ```
   (Adjust the sed pattern to match your actual cron entry format.)

3. Verify the pause:
   ```bash
   ssh office2-claude 'crontab -l | grep felix-admin-capture'
   ```
   The entry should now be commented out with a `# WP05-PAUSED:` prefix.

4. Record the pause timestamp in the runlog. This starts the 90-minute NFR-004 window.

5. **Safety check:** manually invoke `felix-admin-capture` one more time now that the cron is paused, confirming it still works (the cron pause is about the schedule, not about the agent itself). This is optional — if you'd rather not add another invocation, skip it. The post-rename deploy will smoke-test the agent anyway.

**Validation:**
- [ ] Original cron entry captured in the runlog
- [ ] Cron entry commented out on office2
- [ ] `crontab -l` confirms the pause
- [ ] Pause timestamp recorded
- [ ] 90-minute window begun

---

## Subtask T029: Create `02-Inbox-Processed/` folder

**Purpose:** Create the new sibling folder for the inbox. This folder is created directly at its final target name (it does not participate in the rename sequence).

**Steps:**

1. Create the folder on the Mac (Obsidian Sync will propagate to office2):
   ```bash
   mkdir -p "$HOME/second-brain/notes/02-Inbox-Processed"
   touch "$HOME/second-brain/notes/02-Inbox-Processed/.gitkeep"
   ```
   (Confirm the exact vault path — the registry uses `/home/kgale/second-brain/notes/` on office2 but the Mac path may differ. Use the Mac path for local creation.)

2. Alternatively, create the folder in Obsidian via the UI: right-click the vault root → New folder → `02-Inbox-Processed` → add a placeholder note inside.

3. Wait for Obsidian Sync to propagate the new folder to office2. Verify:
   ```bash
   ssh office2-claude 'ls /home/kgale/second-brain/notes/ | grep Inbox-Processed'
   ```
   Expected: `02-Inbox-Processed` appears in the output. If it doesn't after a reasonable wait (a few minutes), investigate Obsidian Sync status.

4. Verify the folder is non-empty (has the `.gitkeep` or placeholder):
   ```bash
   ssh office2-claude 'ls -la /home/kgale/second-brain/notes/02-Inbox-Processed/'
   ```

**Validation:**
- [ ] `02-Inbox-Processed/` exists on the Mac filesystem
- [ ] Obsidian Sync has propagated it to office2
- [ ] Folder contains at least a placeholder file

---

## Subtask T030: Rename vault folders via Obsidian UI with inter-rename verification

**Purpose:** Execute the renumber. This is the most delicate step in the mission — done in Obsidian's UI to ensure wikilinks auto-update.

**Steps:**

1. Open Obsidian on the Mac. Navigate to the vault file browser.

2. Execute the renames in this exact order, one at a time, with verification between each:

   | # | Rename | Verification |
   |---|---|---|
   | 1 | `00-Inbox` → `01-Inbox` | Open 2-3 notes that reference the inbox via wikilink. Confirm links resolve. |
   | 2 | `01-Constitution` → `03-Constitution` | Open 2-3 notes from the Constitution folder. Confirm wikilinks to sibling folders still work. |
   | 3 | `02-Growth` → `04-Growth` | **CRITICAL:** Check that `_private/` inside `04-Growth/` is intact and not opened by Obsidian. |
   | 4 | `03-Health` → `05-Health` | Open 2-3 notes, verify wikilinks. |
   | 5 | `04-Business` → `06-Business` | Open 2-3 notes, verify wikilinks. |
   | 6 | `05-Finance` → `07-Finance` | Open 2-3 notes, verify wikilinks. |
   | 7 | `06-Journal` → `08-Journal` | Open 2-3 notes, verify wikilinks. |
   | 8 | `07-Resources` → `09-Resources` | Open 2-3 notes, verify wikilinks. |

3. `00-System` stays as-is (no rename).
4. `02-Inbox-Processed` is already in place from T029 (no rename).

5. **Between each rename:**
   - Check Obsidian's "Unresolved links" panel (if available). It should show no new unresolved links.
   - Spot-check 2–3 notes that contain wikilinks to the just-renamed folder. Confirm links resolve.
   - If ANY link fails to resolve after a rename: STOP. Investigate. Do NOT continue to the next rename.

6. After all 8 renames complete:
   - Wait for Obsidian Sync to propagate every rename to office2
   - Verify:
     ```bash
     ssh office2-claude 'ls /home/kgale/second-brain/notes/'
     ```
     Expected output (sorted):
     ```
     00-System
     01-Inbox
     02-Inbox-Processed
     03-Constitution
     04-Growth
     05-Health
     06-Business
     07-Finance
     08-Journal
     09-Resources
     ```

7. **IMPORTANT:** Do NOT read any file under `04-Growth/_private/` during this step or at any other point in the mission. The `_private/` path is a constitutional hard limit (C-001). If you need to confirm the folder exists post-rename, use `ls -d` on the directory itself (not its contents):
   ```bash
   ssh office2-claude 'ls -d /home/kgale/second-brain/notes/04-Growth/_private/ 2>&1'
   # Expect: the directory exists (or doesn't — _private/ is empty anyway)
   ```

8. Record the rename sequence in the runlog: each rename's timestamp, verification result, and any issues encountered.

**Validation:**
- [ ] All 8 renames executed in the correct order
- [ ] Wikilink integrity verified between each rename (no new unresolved links)
- [ ] Final folder listing on office2 matches the expected 10-folder ordinal sequence
- [ ] `04-Growth/_private/` directory is still present (confirmed via `ls -d`, NOT by reading contents)
- [ ] Rename sequence recorded in the runlog

---

## Subtask T031: Update `paths.json` and `CLAUDE.md` `_private/` boundary

**Purpose:** Update the registry and the one hardcoded vault reference to point at the new folder names. This is the "flip the switch" moment — after this, the registry resolves to the new paths.

**Steps:**

1. Edit `scripts/vault/paths.json`. Change every path value to the new folder name:
   ```json
   {
     "version": 1,
     "updated": "2026-04-11",
     "paths": {
       "system":          "/home/kgale/second-brain/notes/00-System",
       "inbox":           "/home/kgale/second-brain/notes/01-Inbox",
       "inbox_processed": "/home/kgale/second-brain/notes/02-Inbox-Processed",
       "constitution":    "/home/kgale/second-brain/notes/03-Constitution",
       "growth":          "/home/kgale/second-brain/notes/04-Growth",
       "health":          "/home/kgale/second-brain/notes/05-Health",
       "business":        "/home/kgale/second-brain/notes/06-Business",
       "finance":         "/home/kgale/second-brain/notes/07-Finance",
       "journal":         "/home/kgale/second-brain/notes/08-Journal",
       "resources":       "/home/kgale/second-brain/notes/09-Resources"
     }
   }
   ```

2. Edit `CLAUDE.md.tmpl`. Find the `_private/` boundary reference:
   ```
   ~/second-brain/notes/02-Growth/_private/
   ```
   Update to:
   ```
   ~/second-brain/notes/04-Growth/_private/
   ```
   **This is the one hardcoded vault-path change in this WP.** Everything else flows through the registry via markers.

3. Verify there are no other hardcoded references to `02-Growth` in `CLAUDE.md.tmpl` — the only occurrence should have been the boundary line.

4. Commit these two file changes to the mission branch with a semantic message:
   ```
   feat(vault-registry): update registry to new folder names

   - paths.json: all 10 logical names now point at renumbered folders
   - CLAUDE.md.tmpl: update _private/ boundary line (the one
     hardcoded vault-path exception per C-001)

   Part of mission 026 (kentonium3/kg-automation#152), WP05.
   Folders were renamed via Obsidian UI earlier in this WP.
   ```

5. Record the paths.json update timestamp in the runlog.

**Files modified:**
- `scripts/vault/paths.json` (owned by WP01 — this is an operator-driven cross-WP modification, explicitly authorized for this operational phase)
- `CLAUDE.md.tmpl` (owned by WP02 — same as above)

**Validation:**
- [ ] `scripts/vault/paths.json` has all new folder names
- [ ] `python3 scripts/vault/resolver.py inbox` returns the new `01-Inbox` path
- [ ] `CLAUDE.md.tmpl` has `04-Growth/_private/` as the boundary reference
- [ ] No other `02-Growth` references remain in `CLAUDE.md.tmpl`
- [ ] Changes committed with semantic message

---

## Subtask T032: Run `deploy-f026.sh --apply --mode post-rename`

**Purpose:** Execute the deploy wrapper in post-rename mode. The wrapper performs the deploy, verification, smoke tests, wikilink integrity check, cron re-enable, and cron verification as a single orchestrated sequence.

**Steps:**

1. Invoke the wrapper:
   ```bash
   bash scripts/deploy/deploy-f026.sh --apply --mode post-rename
   ```

2. Watch the output carefully. The wrapper should sequentially:
   1. Confirm backup pre-flight (or note that T027 already did it)
   2. Confirm cron is paused (from T028)
   3. Run `python3 scripts/vault/deploy.py --apply` — regenerates all resolved files with new paths, syncs to office2
   4. Repo-wide grep for old folder literals — expect zero hits outside documented exclusions
   5. Deployed-file grep on office2 for unreplaced `{{VAULT_*}}` markers — expect zero hits
   6. Smoke-test `felix-admin-capture` end-to-end against the new inbox path
   7. Smoke-test `felix-admin-tasker` end-to-end
   8. Wikilink integrity check (or manual confirmation from T030)
   9. Re-enable the `felix-admin-capture` cron entry (uncomment the line T028 commented)
   10. Verify the cron fires correctly (trigger a one-shot manual run OR wait for the next natural tick and observe)

3. **If any step fails:** the wrapper halts with a `===== FAILURE =====` banner. It does NOT auto-resume the cron on failure. Read the failure message, identify the root cause, and decide:
   - **Recoverable failure (e.g., a flaky SSH connection):** investigate and re-run from the failure point
   - **Non-recoverable failure (e.g., deploy corrupted a file):** execute the rollback procedure from the WP05 rollback section below

4. **If the wrapper exits 0:**
   - Every verification passed
   - Smoke tests passed
   - Cron is re-enabled and verified
   - The system is running on the new paths

5. Record the wrapper's output (or a summary) in the runlog. Include timing data so NFR-004 (90-minute budget) can be evaluated.

**Validation:**
- [ ] Wrapper exits 0
- [ ] All 10 internal steps completed successfully
- [ ] Zero stale literals in the repo (NFR-002)
- [ ] Zero unreplaced markers in deployed files (NFR-003)
- [ ] `felix-admin-capture` smoke test passed
- [ ] `felix-admin-tasker` smoke test passed
- [ ] Wikilink integrity verified (NFR-005)
- [ ] Cron re-enabled and firing correctly
- [ ] Total WP05 duration (T028 start → wrapper exit) is within 90 minutes (NFR-004)

---

## Subtask T033: Record WP05 runlog + operator authorization gate for WP06

**Purpose:** Consolidate the risky-window runlog into a mission artifact and explicitly request operator authorization to proceed to WP06.

**Steps:**

1. Finalize `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp05-risky-window-runlog.md`. Include:
   - Pre-flight result (T027)
   - Cron pause timestamp and captured original entry (T028)
   - Folder creation result (T029)
   - Rename sequence with per-rename timestamps and verification results (T030)
   - Registry update commit hash (T031)
   - Deploy wrapper output summary (T032)
   - Total risky-window duration (cron pause → cron resume)
   - Final verdict: PASS / HALT
   - Outstanding concerns (if any) for the operator to know

2. Add an "Operator Authorization Required" section:
   ```markdown
   ## Operator Authorization Required

   WP05 risky window: **PASS**

   - Tier 2 pre-flight: ✅
   - Cron paused and resumed: ✅
   - 02-Inbox-Processed/ created: ✅
   - All 8 folder renames: ✅
   - Wikilink integrity: ✅
   - Registry updated: ✅
   - Post-rename deploy: ✅
   - Smoke tests (capture + tasker): ✅
   - Cron verified firing: ✅
   - Total duration: XX minutes (NFR-004 budget: 90 min)

   The risky window is CLOSED. System is running on the new folder names.
   All verification checks passed.

   WP06 will complete the mission with:
   - Cross-repo operation in ~/second-brain/ (gitignore _private/)
   - Final mission verification against all 10 Success Criteria
   - GitHub issue #152 closure

   **Operator: please confirm you are ready to proceed to WP06.**
   ```

3. Commit the runlog to the mission branch.

4. The operator reviews and explicitly authorizes WP06 entry.

**Files produced:**
- `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp05-risky-window-runlog.md` (finalized)

**Validation:**
- [ ] Runlog contains all required sections
- [ ] Verdict: PASS
- [ ] Operator authorization section present and not pre-checked
- [ ] Runlog committed
- [ ] Operator has explicitly authorized WP06

---

## Definition of Done

- [ ] Tier 2 pre-flight passed (Restic backup ≤24h)
- [ ] `felix-admin-capture` cron paused and later re-enabled successfully
- [ ] `02-Inbox-Processed/` folder created and synced
- [ ] All 8 vault folders renamed via Obsidian UI with wikilink integrity preserved
- [ ] `paths.json` and `CLAUDE.md.tmpl` `_private/` boundary updated
- [ ] `deploy-f026.sh --apply --mode post-rename` executed successfully
- [ ] All verification checks from `contracts/verification-contract.md` § WP05 passed (20+ checks)
- [ ] Total risky-window duration within NFR-004 budget (90 minutes)
- [ ] WP05 runlog committed to the mission branch
- [ ] Operator has explicitly authorized WP06 entry

## Rollback Procedures

**If failure at T029–T031 (pre-redeploy):**
- Undo any Obsidian UI renames (rename back to original names via Obsidian UI)
- Revert `scripts/vault/paths.json` (git) — or keep the updated values if no renames happened
- Revert `CLAUDE.md.tmpl` if edited (git)
- Re-enable the cron (T028's original entry)
- Record the failure and halt the mission

**If failure at T032 (post-redeploy):**
- Do NOT auto-resume the cron (wrapper handles this)
- Revert `scripts/vault/paths.json` to the OLD folder names (git)
- Re-run `deploy.py --apply` — this regenerates resolved files pointing at OLD paths
- Undo the Obsidian UI renames
- Revert `CLAUDE.md.tmpl`
- Manually re-enable the cron
- Verify the agent runs cleanly against the old paths
- Record the failure and halt the mission

**If failure is catastrophic (vault state corruption beyond manual recovery):**
- Execute Tier 2 fallback: Restic restore of the vault to the pre-migration snapshot (from T027)
- Follow `docs/runbooks/governance/post-change-verification.md`
- Verify the restored state before re-enabling the cron
- Halt the mission

**In all rollback scenarios:**
- Record the full sequence of rollback actions in the runlog
- Do NOT attempt WP05 again without operator deliberation on the root cause
- Treat the rollback itself as a reviewable event

## Risks

- **Obsidian wikilink auto-update fails for a rename (edge case).** Mitigation: inter-rename verification in T030 catches it immediately, before cascading. Rollback per above.
- **Obsidian Sync lags behind the rename, causing office2 to see inconsistent state during the deploy.** Mitigation: T030 explicitly waits for sync propagation before continuing. If sync is unusually slow, the 90-minute budget may be exceeded — reassess per NFR-004.
- **SSH connection to office2 drops mid-deploy.** Mitigation: `deploy-f026.sh` is idempotent — re-run it from the start. The operator must re-verify the cron state manually.
- **Restic backup fails to verify (T027).** Mitigation: STOP. Do not proceed. Fix the backup system first.
- **Total duration exceeds 90 minutes (NFR-004).** Mitigation: pause and reassess. It's OK to halt mid-WP and resume later, but document the halt clearly in the runlog.

## Reviewer Guidance

The reviewer should confirm:

- Every step's timestamp is recorded in the runlog
- The rename sequence executed in the correct order with inter-rename verification
- The `_private/` boundary was updated in `CLAUDE.md.tmpl` but NOT migrated to a marker
- `paths.json` points at the NEW folder names
- All verification contract items for WP05 are checked
- Total duration is within the NFR-004 budget (if not, the deviation is documented)
- No files under `04-Growth/_private/` were read, listed, or referenced at any point
- The runlog is honest about any issues encountered, not sanitized for presentation
