---
work_package_id: WP03
title: Migration and Verification
dependencies:
- WP02
requirement_refs:
- FR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
- T016
agent: "claude"
shell_pid: "15484"
history:
- date: '2026-04-10T13:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
tags: []
---

# WP03: Migration and Verification

## Objective

Migrate the felix-admin-capture AGENTS.md to template-driven form: create the `.tmpl` source file, register it in `targets.json`, run the deploy script to produce the resolved output, SCP to office2, and verify the inbox agent continues to function normally.

This is the proof-of-methodology deliverable. After this WP, the pattern is established and follow-up migrations in #152 can proceed mechanically.

## Context

- WP01 built the registry and resolvers
- WP02 built the deploy script
- This WP exercises the full pipeline on one real file
- Target file: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
- The hardcoded inbox path to migrate is on line 22 only
- Office2 destination: `/data/services/openclaw/inbox-agent/AGENTS.md`

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP03 --agent claude`

---

## Subtask T011: Create AGENTS.md.tmpl from AGENTS.md

**Purpose**: Create the template source file by copying the current AGENTS.md and replacing the inbox path on line 22 with the template marker.

**Steps**:
1. Copy the current file:
   ```bash
   cp scripts/openclaw/agents/felix-admin-capture/AGENTS.md \
      scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
   ```
2. Edit the `.tmpl` file. Find line 22:
   ```
   Read all `.md` files in `/home/kgale/second-brain/notes/00-Inbox/`.
   ```
3. Replace `/home/kgale/second-brain/notes/00-Inbox` (the path without trailing slash) with `{{VAULT_INBOX}}`. The resulting line should be:
   ```
   Read all `.md` files in `{{VAULT_INBOX}}/`.
   ```
   Note: only the path portion is replaced. The `/` after the path stays in place so the resolved output matches the original exactly.
4. Verify that no OTHER occurrences of the inbox path were changed. Lines 67, 350, and 368 reference `00-Inbox` as a relative folder name, not an absolute path — those stay unchanged.
5. Double-check by grepping:
   ```bash
   grep -n 'VAULT_INBOX' scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
   grep -n '00-Inbox' scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
   ```
   Expected:
   - `VAULT_INBOX` appears exactly once (line 22)
   - `00-Inbox` still appears in the relative references (lines 67, 350, 368 or similar)

**Validation**:
- [ ] `.tmpl` file exists
- [ ] Contains `{{VAULT_INBOX}}` exactly once
- [ ] Other `00-Inbox` references are preserved (not accidentally modified)

---

## Subtask T012: Add Target to targets.json

**Purpose**: Register the new migration in `targets.json` so the deploy script knows to process it.

**Steps**:
1. Edit `scripts/vault/targets.json` to add this target:
   ```json
   {
     "version": 1,
     "targets": [
       {
         "template": "scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl",
         "output": "scripts/openclaw/agents/felix-admin-capture/AGENTS.md",
         "office2_path": "/data/services/openclaw/inbox-agent/AGENTS.md"
       }
     ]
   }
   ```

**Validation**:
- [ ] targets.json has exactly one target entry
- [ ] JSON is valid
- [ ] Paths are relative to repo root (template, output) and absolute (office2_path)

---

## Subtask T013: Dry-Run Deploy and Verify Diff

**Purpose**: Run the deploy script in dry-run mode and confirm it reports the expected change.

**Steps**:
1. Run: `python3 scripts/vault/deploy.py`
2. Expected output should include:
   - Mode: DRY-RUN
   - 1 target
   - Target: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
   - Markers: `INBOX`
   - Status: `would-apply` or `unchanged`
3. If status is `unchanged`, that means the resolved content already matches the current `AGENTS.md` — which is expected because the current file already has the hardcoded path and the resolved template produces the same path. This is the intended idempotent behavior.
4. If status is `would-apply`, verify the diff shows no unexpected changes.

**Key insight**: If the current `AGENTS.md` already has the hardcoded path and the template resolves to the same path, the "resolved" content equals the current content. The status should be `unchanged` — the file is already correct.

To actually see the deploy script do work, you can temporarily break the file:
- Change line 22 of the current `AGENTS.md` to something different
- Re-run dry-run — should show `would-apply` with a diff
- Don't commit the broken version; WP03's T014 will restore it via apply mode

Alternatively, just trust the idempotency and proceed to T014.

**Validation**:
- [ ] Dry-run completes without errors
- [ ] Output shows 1 target with marker `INBOX`
- [ ] Exit code 0

---

## Subtask T014: Apply Deploy and Verify Output

**Purpose**: Run the deploy script with `--apply` to write the resolved file, then verify it matches the original functionally.

**Steps**:
1. Run: `python3 scripts/vault/deploy.py --apply --no-office2`
   (using `--no-office2` first to isolate the local-write step from the SCP step)
2. Expected output: status `applied` or `unchanged`
3. Verify the resolved file:
   ```bash
   diff scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl \
        scripts/openclaw/agents/felix-admin-capture/AGENTS.md
   ```
   Expected: the only diff should be line 22 — `.tmpl` has `{{VAULT_INBOX}}` and `.md` has `/home/kgale/second-brain/notes/00-Inbox`.
4. Verify the resolved `.md` line 22 reads:
   ```
   Read all `.md` files in `/home/kgale/second-brain/notes/00-Inbox/`.
   ```
5. Compare resolved file to git HEAD to see if anything changed:
   ```bash
   git diff scripts/openclaw/agents/felix-admin-capture/AGENTS.md
   ```
   Expected: no changes (the resolved output should match what's already in git).

**Validation**:
- [ ] Deploy ran successfully with exit 0
- [ ] Resolved `.md` file exists and is functionally identical to git HEAD
- [ ] `diff .tmpl .md` shows only the expected marker substitution
- [ ] `git diff` shows no changes to AGENTS.md (idempotent result)

---

## Subtask T015: SCP to Office2 and Verify

**Purpose**: Push the resolved file to office2 so the deployed agent file stays in sync with the repo.

**Steps**:
1. Run the deploy with SCP enabled: `python3 scripts/vault/deploy.py --apply`
2. Verify the script output includes `office2: synced` for the target
3. SSH to office2 and verify the file:
   ```bash
   ssh office2-claude "md5sum /data/services/openclaw/inbox-agent/AGENTS.md"
   md5 scripts/openclaw/agents/felix-admin-capture/AGENTS.md  # on Mac
   ```
4. Verify both md5 sums match
5. Alternatively, verify by content:
   ```bash
   ssh office2-claude "sed -n '22p' /data/services/openclaw/inbox-agent/AGENTS.md"
   ```
   Should show the resolved line 22.

**Validation**:
- [ ] Deploy script reports `office2: synced`
- [ ] office2 file matches repo file (md5 or content check)
- [ ] Line 22 contains the resolved path

---

## Subtask T016: Trigger Inbox Agent and Verify No Regression

**Purpose**: Final validation that the agent continues to function normally after the migration.

**Steps**:
1. Trigger the inbox cron:
   ```bash
   ssh office2-claude "openclaw cron run cc9977fa-e451-47e7-9a18-eb6d85775f26"
   ```
2. Wait ~30-60 seconds for the run to complete
3. Check the latest session log:
   ```bash
   ssh office2-claude 'python3 << "PYEOF"
   import os, glob, json
   files = sorted(glob.glob("/home/claude/.openclaw/agents/felix-admin-capture/sessions/*.jsonl"),
                  key=os.path.getmtime, reverse=True)
   if files:
       print("Latest session:", os.path.basename(files[0]))
       with open(files[0]) as f:
           for line in f:
               d = json.loads(line)
               if d.get("type") == "message" and d.get("message", {}).get("role") == "assistant":
                   msg = d["message"]
                   if msg.get("errorMessage"):
                       print("ERROR:", msg["errorMessage"][:200])
                   content = msg.get("content", [])
                   for block in content:
                       if block.get("type") == "text" and block["text"].strip():
                           print("Output preview:", block["text"][:300])
                           break
                   break
   PYEOF'
   ```
4. Verify:
   - Session completed without errors
   - Output contains the agent identity header (`Sent by felix-admin-capture:haiku`)
   - Output is a normal processing summary, not an error

**Validation**:
- [ ] Inbox agent ran successfully post-migration
- [ ] No errors in the session log
- [ ] Agent identity header present in output
- [ ] Processing summary looks normal

---

## Definition of Done

- [ ] `.tmpl` file exists with `{{VAULT_INBOX}}` marker
- [ ] `targets.json` registers the migration
- [ ] Deploy in apply mode writes the resolved file and SCPs to office2
- [ ] Resolved file is functionally identical to the pre-migration version
- [ ] Office2 file matches repo file
- [ ] Inbox agent runs successfully after migration
- [ ] Repo state is clean (no unexpected changes beyond the new `.tmpl` file and updated `targets.json`)

## Risks

- **Resolved file differs from original** (e.g., trailing newline handling, line endings): Mitigation — the template is a direct copy with a single string substitution; line endings and whitespace should be preserved exactly. If diff shows more than one line changed, stop and investigate before proceeding.
- **Office2 SCP fails**: Mitigation — deploy script reports SCP failure with non-zero exit. Can be retried; no partial state on office2 because SCP is either fully successful or fully failed at the file level.
- **Inbox agent errors post-migration**: Mitigation — if session log shows errors, the resolved file is almost certainly identical to the pre-migration version (we verified in T014), so the issue would be unrelated. But stop and investigate before calling the migration successful.

## Reviewer Guidance

- Confirm `.tmpl` has exactly one `{{VAULT_INBOX}}` marker
- Confirm resolved file matches git HEAD (no functional change)
- Confirm office2 file matches repo file
- Confirm inbox agent session log shows normal completion
- Confirm `git diff` shows only the additions (new `.tmpl`, updated `targets.json`) and no unexpected changes to `AGENTS.md`

## Activity Log

- 2026-04-10T15:38:55Z – claude – shell_pid=15484 – Started implementation via action command
- 2026-04-10T15:56:37Z – claude – shell_pid=15484 – Template created, deploy verified idempotent, inbox agent verified
- 2026-04-10T15:56:45Z – claude – shell_pid=15484 – Methodology proven end-to-end; MVP complete
