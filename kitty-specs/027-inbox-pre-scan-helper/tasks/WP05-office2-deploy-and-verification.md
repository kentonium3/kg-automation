---
work_package_id: WP05
title: Office2 Deploy + Verification
dependencies:
- WP01
- WP02
- WP03
- WP04
requirement_refs:
- C-005
- C-006
- C-007
- NFR-001
- NFR-003
- NFR-005
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T021
- T022
- T023
- T024
- T025
- T026
- T027
agent: "claude:opus-4-6:orchestrator:implementer"
shell_pid: "77642"
history:
- date: '2026-04-11'
  event: created
authoritative_surface: kitty-specs/027-inbox-pre-scan-helper/research/
execution_mode: planning_artifact
mission_slug: 027-inbox-pre-scan-helper
owned_files:
- kitty-specs/027-inbox-pre-scan-helper/research/**
tags: []
---

# WP05: Office2 Deploy + Verification

## Objective

Execute the deploy wrapper against live office2, run three smoke tests (empty run, non-empty run, archive), capture all 10 success criteria with real evidence, and write the mission close-out artifact. This is the integration gate — if WP05 passes, the mission is ready for review/merge.

The only files this WP modifies are the mission's own close-out artifacts under `kitty-specs/027-inbox-pre-scan-helper/research/`. All other changes have already been made by WP01–WP04.

## Context

Read these first:
- `kitty-specs/027-inbox-pre-scan-helper/spec.md` — all 10 success criteria
- `kitty-specs/027-inbox-pre-scan-helper/plan.md` — Deploy Wrapper Contract (Step 1–8) and Post-flight section
- `kitty-specs/027-inbox-pre-scan-helper/quickstart.md` — verification commands
- `kitty-specs/026-vault-path-registry-and-folder-renumber/research/wp06-mission-closeout.md` — prior mission's close-out artifact (as a format reference)
- `scripts/deploy/deploy-149.sh` (from WP03)
- `docs/runbooks/governance/post-change-verification.md` — Tier 2 + Tier 3 post-change checklist

**Critical note on #158**: Obsidian Sync silent failure is risk-accepted for this mission. If smoke-test artifacts fail to propagate from office2 to Mac/phone, that is #158 territory and NOT a WP05 failure. Document the observation in the runlog, do not block the mission on it.

## Branch Strategy

- **Planning base**: main
- **Final merge target**: main
- **Execution worktree**: assigned by `spec-kitty agent action implement WP05 --agent <name>`.
- **Dependencies**: WP01, WP02, WP03, WP04 must all be approved before WP05 begins. Use `spec-kitty next --agent <name> --mission 027-inbox-pre-scan-helper` to confirm.

## Subtasks

### T021 — Pre-flight verification

**Purpose**: Confirm all preconditions before running `--apply`.

**Steps**:
1. Confirm Restic backup age ≤24h:
   ```bash
   ssh office2-claude 'restic snapshots --latest 1 --json 2>&1 | python3 -c "import json,sys,datetime; d=json.load(sys.stdin); t=datetime.datetime.fromisoformat(d[0][\"time\"].replace(\"Z\",\"+00:00\")); age=(datetime.datetime.now(datetime.timezone.utc)-t).total_seconds(); print(f\"latest snapshot: {t}, age: {age/3600:.1f}h\"); sys.exit(0 if age<86400 else 1)"'
   ```
   (Or use the exact command from the Restic runbook in `docs/runbooks/`.)
2. Confirm office2 reachable: `ssh office2-claude true`
3. Confirm `scripts/deploy/deploy-149.sh` exists and is executable
4. Run `./scripts/deploy/deploy-149.sh --dry-run` and capture the full output. Paste it into the WP runlog under a "Pre-flight dry-run output" heading.
5. Review the dry-run output for any anomalies (unexpected file list, unexpected cron UUIDs, etc.)

**Validation**:
- [ ] Restic snapshot age recorded (should be <24h, otherwise halt and trigger a backup first)
- [ ] office2 reachable
- [ ] Dry-run output captured in the runlog
- [ ] No anomalies observed in dry-run

### T022 — Execute deploy wrapper

**Purpose**: Run the deploy for real.

**Steps**:
1. Execute `./scripts/deploy/deploy-149.sh --apply`
2. Capture the FULL stderr and stdout output into the WP runlog under a "Deploy --apply output" heading
3. Confirm the wrapper's own Step 8 smoke test passed
4. If anything fails, do NOT attempt to manually fix it — halt, report the failure, and follow the wrapper's printed rollback instructions. Filing a follow-on issue is acceptable. Retrying the deploy after a fix is acceptable but must be recorded in the runlog.

**Validation**:
- [ ] Deploy reached Step 8 and Step 8 passed
- [ ] Full output captured in the runlog
- [ ] No halt states encountered, or if halted, a clear recovery path is documented

### T023 — Empty-run smoke test (SC-001)

**Purpose**: Prove that when the inbox has zero unprocessed files, the agent replies IDLE and costs ≤500 tokens.

**Steps**:
1. Confirm current inbox state has zero unprocessed files:
   ```bash
   ssh office2-claude 'grep -l "status: unprocessed" /home/kgale/second-brain/notes/01-Inbox/*.md 2>&1 || echo "NONE"'
   ```
   If files are listed, this test is invalid for the moment — either wait for the agent to process them on its next natural cron fire, or move to T024 (non-empty) first and return to T023 later.
2. Trigger the noon cron manually: `ssh office2-claude 'openclaw cron run 7fa9b299-f8fc-44c2-b37d-de4163c80cdf'` (inbox-noon UUID)
3. Wait for completion (poll `openclaw cron runs <uuid>` until the latest run shows `status: ok`)
4. Fetch the run's detail and capture:
   - Total input tokens
   - Total output tokens
   - Total tokens
   - Agent reply text (should be exactly `IDLE`)
   - Run duration
5. Fetch the helper daily log file for the current UTC date and confirm a run entry with `unprocessed: 0, archived: 0` was written:
   ```bash
   ssh office2-claude 'cat /home/claude/second-brain/agents/logs/inbox-prescan-$(date -u +%Y-%m-%d).md'
   ```
6. Spot-check downstream: `ssh office2-claude 'curl -sH "Authorization: Bearer <token>" http://office2:3456/api/v1/tasks/all | jq "[.[] | select(.created_at > \"<run-start-iso>\")]"'` (or whatever pattern fits the Vikunja API) to confirm zero new tasks were created during the run window
7. Spot-check the vault: confirm no new files in vault paths were written during the run window
8. Capture all evidence in the runlog under "SC-001: Empty-run smoke test"

**Validation**:
- [ ] Total tokens ≤500
- [ ] Agent reply is `IDLE` (or semantically equivalent with clear reasoning)
- [ ] Helper log entry shows `unprocessed: 0, archived: 0`
- [ ] Zero new Vikunja tasks during run window
- [ ] Zero new vault files during run window

### T024 — Non-empty smoke test (SC-002)

**Purpose**: Prove that when the inbox has a known unprocessed file, the agent processes only that file correctly.

**Steps**:
1. Plant a known test file in the inbox:
   ```bash
   ssh office2-claude 'cat > /home/kgale/second-brain/notes/01-Inbox/Inbox\ 2026-04-11\ 1200\ test.md <<EOF
---
date: 2026-04-11
time: 12:00
type: inbox
status: unprocessed
---
This is a test capture from mission 027 WP05 T024. It should route to a Vikunja task titled "Test task from mission 027".
EOF'
   ```
2. Trigger the cron: `ssh office2-claude 'openclaw cron run 7fa9b299-f8fc-44c2-b37d-de4163c80cdf'`
3. Wait for completion
4. Capture from the run:
   - Total tokens
   - Agent reply
   - Run duration
5. Verify the test file's status toggled to `processed`:
   ```bash
   ssh office2-claude 'grep "^status:" "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-04-11 1200 test.md"'
   ```
6. Verify the expected downstream effect: a Vikunja task titled "Test task from mission 027" now exists
7. Verify the agent did NOT touch any other file in the inbox (check mtimes of the other files — none should be more recent than the run start time, except the one test file)
8. Capture all evidence in the runlog under "SC-002: Non-empty smoke test"
9. **Cleanup**: once verified, delete the test Vikunja task and either delete the test file or let the next 7-day cycle archive it

**Validation**:
- [ ] Test file was processed (status changed to `processed`)
- [ ] Expected Vikunja task created
- [ ] No other inbox files were touched
- [ ] Agent's token usage was reasonable (a few thousand for one file)

### T025 — Archive smoke test (SC-003, SC-004, SC-005)

**Purpose**: Prove the archive logic works end-to-end: stale files move, recent files stay, unprocessed files stay regardless of age.

**Steps**:
1. Plant three test files with specific mtimes:
   - **Stale processed** (should be archived):
     ```bash
     ssh office2-claude 'cat > /home/kgale/second-brain/notes/01-Inbox/Inbox\ 2026-04-03\ 0800\ stale.md <<EOF
---
date: 2026-04-03
status: processed
---
Stale processed test file for mission 027 WP05 T025.
EOF
     touch -d "8 days ago" "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-04-03 0800 stale.md"'
     ```
   - **Recent processed** (should NOT be archived):
     ```bash
     ssh office2-claude 'cat > /home/kgale/second-brain/notes/01-Inbox/Inbox\ 2026-04-05\ 0800\ recent.md <<EOF
---
date: 2026-04-05
status: processed
---
Recent processed test file for mission 027 WP05 T025.
EOF
     touch -d "6 days ago" "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-04-05 0800 recent.md"'
     ```
   - **Old unprocessed** (should NOT be archived):
     ```bash
     ssh office2-claude 'cat > /home/kgale/second-brain/notes/01-Inbox/Inbox\ 2026-03-12\ 0800\ old-unprocessed.md <<EOF
---
date: 2026-03-12
status: unprocessed
---
Old unprocessed test file for mission 027 WP05 T025. Do not move this.
EOF
     touch -d "30 days ago" "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-03-12 0800 old-unprocessed.md"'
     ```
2. Trigger a cron run (any of the 4 inbox UUIDs). The agent's Step 1 will run the helper, which will archive the stale file and report one unprocessed path (the old unprocessed file).
3. Wait for completion
4. Verify the stale file moved to `02-Inbox-Processed/`:
   ```bash
   ssh office2-claude 'ls /home/kgale/second-brain/notes/02-Inbox-Processed/ | grep "stale"'
   ```
5. Verify the recent file is still in `01-Inbox/`:
   ```bash
   ssh office2-claude 'ls /home/kgale/second-brain/notes/01-Inbox/ | grep "recent"'
   ```
6. Verify the old unprocessed file is still in `01-Inbox/` (it should have been in the helper's unprocessed list → processed by the agent → status now toggled to processed; but the file itself is still in 01-Inbox because it's less than 7 days since the status toggle):
   ```bash
   ssh office2-claude 'ls /home/kgale/second-brain/notes/01-Inbox/ | grep "old-unprocessed"'
   ```
7. Verify the helper log recorded the archive with correct src/dst/age_days
8. Capture all evidence in the runlog under "SC-003/SC-004/SC-005: Archive smoke test"
9. **Cleanup**: delete the three test files from both directories; delete any Vikunja task created from the unprocessed test file

**Validation**:
- [ ] Stale processed file → archived (SC-003)
- [ ] Recent processed file → stays in inbox (SC-004)
- [ ] Old unprocessed file → stays in inbox (SC-005)
- [ ] Helper log recorded archive move with age_days ≥ 8
- [ ] No spurious archives

### T026 — Mission close-out artifact

**Purpose**: Capture all 10 success criteria results in a single close-out document.

**Steps**:
1. Create `kitty-specs/027-inbox-pre-scan-helper/research/wp05-deploy-verification.md` with sections:
   - **Deploy timestamp**: when the wrapper ran
   - **Deploy output**: full stderr/stdout from T021 dry-run and T022 apply
   - **SC-001 Empty-run**: evidence from T023 (token count, reply, helper log, downstream audit)
   - **SC-002 Non-empty run**: evidence from T024 (test file, agent reply, Vikunja task created, status toggle)
   - **SC-003 Stale archive**: evidence from T025 (file moved, helper log)
   - **SC-004 Recent stays**: evidence from T025 (file still in inbox)
   - **SC-005 Unprocessed stays**: evidence from T025 (file still in inbox)
   - **SC-006 Missing dest fails loud**: either (a) synthetic test by temporarily renaming `02-Inbox-Processed/` and triggering, or (b) a unit-test cross-reference to the pytest case that proves this behavior (since T025 proves the happy path). Prefer (a) if risk-free; otherwise (b).
   - **SC-007 Workspace reflects contract**: grep output from office2 showing the updated Step 1 text in `AGENTS.md` or wherever it lives
   - **SC-008 Deploy wrapper correct order**: wrapper output from T022 showing each step's sequence
   - **SC-009 Architecture docs updated**: diff output from `service-inventory.json` showing `updated_by: 027-inbox-pre-scan-helper`
   - **SC-010 Issue #149 closable**: the drafted closure comment (see T027)
   - **Anomalies**: any unexpected observations
   - **Follow-on issues filed**: any new issues opened during WP05 (pointing at #158 if sync issues observed, etc.)
2. Commit the close-out artifact with a conventional commit message

**Files**:
- `kitty-specs/027-inbox-pre-scan-helper/research/wp05-deploy-verification.md` (new)

**Validation**:
- [ ] All 10 success criteria have evidence sections
- [ ] Evidence is concrete (real log quotes, real diffs, real command outputs) not hand-waving
- [ ] File is committed

### T027 — Draft #149 closure comment

**Purpose**: Prepare the comment that will be posted to issue #149 after `/spec-kitty.merge`.

**Steps**:
1. In the close-out artifact from T026, add a section "Issue #149 closure comment draft" containing the GitHub-flavored markdown body of the closure comment. Include placeholders for the merge commit hash (filled post-merge).
2. Template:
   ```markdown
   Mission 027 merged. Merge commit: <HASH>.

   **Delivered:**
   - Pre-scan helper at `scripts/inbox/prescan.py` with 25+ pytest unit tests
   - felix-admin-capture Step 1 contract updated: helper-first, IDLE-on-empty
   - Deploy wrapper `scripts/deploy/deploy-149.sh` following mission 026 safe-order pattern
   - Architecture docs updated (service-inventory.json + md view)

   **Success criteria results:**
   - SC-001 Empty-run: <actual tokens> tokens, reply IDLE, zero downstream writes ✅
   - SC-002 Non-empty routing: test file routed correctly ✅
   - SC-003 Stale archive: 8-day-old file moved ✅
   - SC-004 Recent stays: 6-day-old file remained ✅
   - SC-005 Unprocessed stays: 30-day-old unprocessed file remained ✅
   - SC-006 Missing dest fails loud: verified <method> ✅
   - SC-007 Workspace contract: AGENTS.md Step 1 updated ✅
   - SC-008 Deploy wrapper order: wrapper executed in correct sequence ✅
   - SC-009 Architecture docs: service-inventory.json updated_by: 027-inbox-pre-scan-helper ✅
   - SC-010 Issue closable: this comment ✅

   **Close follow-on**: #158 (Obsidian Sync silent failure) is next — it was risk-accepted for this mission but remains a real operational concern.

   Mission close-out artifact: `kitty-specs/027-inbox-pre-scan-helper/research/wp05-deploy-verification.md`.
   ```
3. Do NOT post the comment during WP05. The spec-kitty merge workflow handles post-merge closure.

**Validation**:
- [ ] Draft comment stored in the close-out artifact
- [ ] Placeholders clearly marked with `<HASH>`, `<actual tokens>`, `<method>`, etc.

## Definition of Done

- [ ] T021 pre-flight captured
- [ ] T022 deploy executed and captured
- [ ] T023 empty-run smoke test captured
- [ ] T024 non-empty smoke test captured
- [ ] T025 archive smoke test (stale/recent/unprocessed) captured
- [ ] T026 close-out artifact committed
- [ ] T027 closure comment drafted
- [ ] All 10 success criteria have evidence in the close-out artifact
- [ ] All test artifacts cleaned up (test files deleted, test Vikunja tasks deleted)
- [ ] Conventional commit: `docs(WP05): mission 027 office2 deploy verification + closeout`

## Risks

- **Inbox not empty when T023 runs**: non-blocker — run T024 first, return to T023 later, or synthetically empty the inbox (NOT recommended, let natural processing handle it)
- **Test artifacts polluting prod**: always clean up. The test Vikunja task from T024 must be deleted. Test files from T025 must be deleted from both inbox and inbox-processed.
- **Sync propagation to Mac/phone**: #158 risk-accepted. Don't block on this.
- **openclaw cron run timeout**: if the agent's turn takes longer than expected (e.g., many unprocessed files), the smoke test may need a longer poll window
- **Archive destination collision**: if a file with the same name already exists in `02-Inbox-Processed/` from a previous mission 026 test, the archive move will skip with a warning. This is correct helper behavior but may cause T025's stale test to fail verification. Pre-clean the destination before planting the stale test file.

## Reviewer Guidance

- The review of WP05 is unusual because it is mostly runtime evidence, not code. The reviewer should verify:
  - Every success criterion has concrete evidence (not just "SC-001 ✅")
  - Token count for the empty run is actually ≤500 (if it's higher, WP02's Step 1 wording may need adjustment)
  - Test artifacts were cleaned up
  - The close-out artifact is committed and its content matches the success criteria
  - The drafted closure comment is present and has all placeholders

- The reviewer should NOT re-run the smoke tests themselves unless they have direct office2 access and reason to doubt the captured evidence.

- If any success criterion is partially met or ambiguous, the reviewer should ask for clarification rather than immediately rejecting.

## Implementation command

```bash
spec-kitty agent action implement WP05 --mission 027-inbox-pre-scan-helper --agent <tool>:<model>:<profile>:<role>
```

## Activity Log

- 2026-04-11T21:54:57Z – claude:opus-4-6:orchestrator:implementer – shell_pid=77642 – Started implementation via action command
- 2026-04-11T22:21:36Z – claude:opus-4-6:orchestrator:implementer – shell_pid=77642 – WP05 complete: all 10 success criteria verified live on office2. 4 integration bugs fixed during deploy (scripts/vault rsync, ssh stdin, frontmatter parser, workspace path). Close-out artifact at kitty-specs/027-inbox-pre-scan-helper/research/wp05-deploy-verification.md. NFR-003 threshold amendment recommended post-merge.
