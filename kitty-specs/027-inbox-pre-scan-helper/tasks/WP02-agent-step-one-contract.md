---
work_package_id: WP02
title: Agent Workspace Step 1 Update
dependencies: []
requirement_refs:
- FR-009
- FR-010
- FR-011
- FR-012
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T008
- T009
- T010
agent: "claude:opus-4-6:implementer:implementer"
shell_pid: "55000"
history:
- date: '2026-04-11'
  event: created
authoritative_surface: ai-agents/felix-admin-capture/
execution_mode: code_change
mission_slug: 027-inbox-pre-scan-helper
owned_files:
- ai-agents/felix-admin-capture/**
tags: []
---

# WP02: Agent Workspace Step 1 Update

## Objective

Update the `felix-admin-capture` agent workspace files so that Step 1 of the agent's standing orders becomes "run the pre-scan helper, then either reply IDLE or process the returned paths", replacing the current "scan the inbox" behavior.

This WP is the bridge between the helper (WP01) and the live agent behavior (WP05). It does not require WP01 to be implemented — it only references the helper's deployed path and CLI contract, both of which are already specified in `plan.md`.

## Context

Read these first:
- `kitty-specs/027-inbox-pre-scan-helper/spec.md` — FR-009, FR-010, FR-011, FR-012
- `kitty-specs/027-inbox-pre-scan-helper/plan.md` — "Agent Workspace Changes" and "Helper CLI contract" sections
- `ai-agents/felix-admin-capture/` — the workspace files you will edit
- `scripts/openclaw/agents/felix-admin-capture/` — if present, this is the deploy-source location for the workspace files (the `.tmpl` variants). Mission 026 established a `.tmpl` + substitution + render pattern for these files.
- `scripts/vault/paths.json` — the registry (for reference; this WP does not add new markers)

The helper's deployed path on office2 is `/home/claude/kg-automation/scripts/inbox/prescan.py` (hardcoded as a deploy artifact path, not a vault path).

The helper's CLI contract (from `plan.md` and `data-model.md`):
- Invocation: `python3 /home/claude/kg-automation/scripts/inbox/prescan.py`
- Exit 0 → JSON on stdout with `unprocessed_count`, `unprocessed_paths`, `archived_count`, `archived`, `warnings`
- Exit ≠ 0 → error on stderr, no stdout

The agent's new Step 1 contract:
- Run the helper
- Parse the JSON
- If `unprocessed_count == 0` → reply with the single token `IDLE` and nothing else; turn ends
- If `unprocessed_count > 0` → iterate over `unprocessed_paths` and process each file per the existing routing rules (which are unchanged from Step 2 onward)
- If helper exits non-zero → report the stderr as the turn output and stop; do not process any files

## Branch Strategy

- **Planning base**: main
- **Final merge target**: main
- **Execution worktree**: assigned by `spec-kitty agent action implement WP02 --agent <name>` at implementation time.

Use `spec-kitty next --agent <your-name> --mission 027-inbox-pre-scan-helper` for the exact command.

## Subtasks

### T008 — Identify which file owns "Step 1"

**Purpose**: Before editing anything, confirm exactly which file (or files) contain the current "scan the inbox" instruction.

**Steps**:
1. Read all files in `ai-agents/felix-admin-capture/`:
   - `IDENTITY.md`
   - `SOUL.md`
   - `AGENTS.md`
   - `USER.md`
   - `TOOLS.md`
2. Read all files in `scripts/openclaw/agents/felix-admin-capture/` (if present) including the `.tmpl` variants. Mission 026 established that the `.tmpl` files are the deploy-source-of-truth and the rendered `.md` files are generated artifacts on office2.
3. Search for phrases like "Step 1", "scan the inbox", "read all files", "01-Inbox", "{{VAULT_INBOX}}". Record every location in the WP runlog.
4. Determine the source-of-truth: typically `AGENTS.md.tmpl` or `SOUL.md.tmpl` in `scripts/openclaw/agents/felix-admin-capture/`. If unsure, check the deploy script from mission 026 (`scripts/deploy/deploy-f026.sh` was deleted, but the pattern is captured in `docs/runbooks/` or the mission 026 plan).
5. Confirm your finding: the file you will edit is the source from which the office2 workspace files are rendered/deployed. You are NOT editing the office2 files directly.

**Files**:
- Read-only: all of the above

**Validation**:
- [ ] You can point to exactly one source-of-truth file that owns "Step 1" for felix-admin-capture
- [ ] You have verified via grep that there are no duplicate "Step 1" definitions across multiple files
- [ ] The runlog records which file(s) you found and which you chose as the edit target

### T009 — Update the identified file with the new Step 1 contract

**Purpose**: Replace the old "scan the inbox" instruction with the new helper-driven contract.

**Steps**:
1. Open the identified source-of-truth file (likely `AGENTS.md.tmpl` or `SOUL.md.tmpl`)
2. Locate the Step 1 section
3. Replace it with a new Step 1 that reads like this (adapt the phrasing to match the surrounding idiom):

```markdown
## Step 1 — Run the pre-scan helper

Your first action on every turn is to run the inbox pre-scan helper:

```bash
python3 /home/claude/kg-automation/scripts/inbox/prescan.py
```

The helper returns a JSON object on stdout with this shape:
```json
{
  "unprocessed_count": <int>,
  "unprocessed_paths": [<absolute path>, ...],
  "archived_count": <int>,
  "archived": [{"src": "...", "dst": "...", "age_days": <int>}, ...],
  "warnings": [...]
}
```

Branch on the result:

- **Helper exit code is non-zero** → The helper reports an error on stderr. Report the stderr content as your turn output and stop. Do NOT attempt to process any files. The next cron run retries.

- **Helper exit code is 0 AND `unprocessed_count == 0`** → Reply with the single token `IDLE` and nothing else. Your turn ends. Do NOT write to the vault, do NOT create Vikunja tasks, do NOT send WhatsApp messages. The helper has already handled any stale-file archiving; there is nothing for you to do.

- **Helper exit code is 0 AND `unprocessed_count > 0`** → Process each file in `unprocessed_paths` in order, following the routing rules in Step 2 and beyond. Do NOT scan `{{VAULT_INBOX}}` yourself — the helper's list is authoritative.
```

4. Preserve all other standing orders unchanged. The new Step 1 replaces the old Step 1 only.
5. If the old Step 1 had any rationale or context comments, preserve the ones that still apply (e.g., "always process the oldest file first" is still relevant if it was there).
6. Add a short comment near the Step 1 block noting the dependency: `<!-- Step 1 contract defined by mission 027; helper at /home/claude/kg-automation/scripts/inbox/prescan.py -->`

**Files**:
- `ai-agents/felix-admin-capture/AGENTS.md.tmpl` OR `SOUL.md.tmpl` (or whichever file T008 identified) — edit in place

**Validation**:
- [ ] Step 1 now references `python3 /home/claude/kg-automation/scripts/inbox/prescan.py`
- [ ] Step 1 specifies the three branches (error, empty, non-empty) with unambiguous wording
- [ ] No references to "scan the inbox" remain in the file
- [ ] Step 2 and beyond are unchanged
- [ ] Grep confirms no other `ai-agents/felix-admin-capture/` file still says "scan the inbox"

### T010 — Verify render through vault path registry deploy mechanism

**Purpose**: Confirm the updated `.tmpl` file still produces a clean render via the existing substitution logic (no new markers, no orphaned placeholders).

**Steps**:
1. If the vault path registry has a local render/dry-run CLI (e.g., `python3 scripts/vault/render.py <tmpl-file>` — check `scripts/vault/` and `scripts/deploy/` for tooling), run it against the updated `.tmpl` and compare the output to the previous render.
2. If no CLI exists, do a manual substitution: grep for `{{VAULT_*}}` markers in the updated file, confirm each resolves to a key present in `scripts/vault/paths.json`, and mentally render the file.
3. Confirm:
   - No new `{{VAULT_*}}` markers were introduced (scope constraint C-004)
   - Existing `{{VAULT_INBOX}}` references (if any in Step 2 and beyond) still resolve
   - No orphaned placeholders (e.g., `{{VAULT_UNKNOWN}}` typos)
4. The helper path `/home/claude/kg-automation/scripts/inbox/prescan.py` is NOT a vault path — it is a deploy artifact path. Do NOT wrap it in a `{{VAULT_*}}` marker; leave it as a literal string. Add an inline comment explaining why.

**Files**:
- No file changes — this is verification only. Any issues found in T010 are fixed in a revisit to T009.

**Validation**:
- [ ] No new vault markers introduced
- [ ] No orphaned placeholders
- [ ] The helper path is a literal string, not a marker
- [ ] The rendered file would land cleanly on office2 via the mission 026 deploy mechanism

## Definition of Done

- [ ] T008 runlog identifies the exact source-of-truth file
- [ ] T009 updates that file with the new Step 1 contract
- [ ] T010 verification passes
- [ ] Grep confirms zero "scan the inbox" references remain in `ai-agents/felix-admin-capture/` and `scripts/openclaw/agents/felix-admin-capture/`
- [ ] The file diff is minimal — only the Step 1 section changed, everything else is byte-identical
- [ ] Commit message: `feat(WP02): agent step 1 contract now runs pre-scan helper`

## Risks

- **Duplicate Step 1 definitions**: if Step 1 is redundantly defined in both `SOUL.md.tmpl` and `AGENTS.md.tmpl`, updating one without the other creates a contradiction. T008 must find all of them.
- **Step 1 expressed as narrative**: if the current wording is prose rather than numbered steps, find the semantic equivalent ("the first thing you do is...") and replace it in place. Don't restructure the whole file.
- **Tone mismatch**: the new Step 1 wording should match the tone of the rest of the file. If the file uses second-person imperative ("You scan the inbox..."), write the new Step 1 in the same tone.
- **Helper path is hardcoded**: if the kg-automation repo location on office2 ever changes, this file will break. Mitigate by adding the dependency comment in T009 step 6.
- **Forgetting the agent deploy step**: this WP edits the source-of-truth `.tmpl` only. WP03's deploy wrapper handles pushing the rendered file to office2. Do not try to deploy in this WP.

## Reviewer Guidance

- Verify exactly one source-of-truth file was edited. If multiple files changed, the reviewer should ask why.
- Verify the new Step 1 covers all three branches (error / empty / non-empty) and the wording is unambiguous.
- Verify the helper path is a literal hardcoded string with a comment explaining why it isn't a vault marker.
- Verify no unrelated drift (whitespace, reordered sections, added emoji) crept into the file. The diff should be tight and focused.
- Verify grep for "scan the inbox" returns zero hits across the repo (excluding `kitty-specs/027-inbox-pre-scan-helper/` which contains the spec text describing the old behavior).
- The agent's behavioral change is not testable in this WP — WP05 validates it live on office2.

## Implementation command

```bash
spec-kitty agent action implement WP02 --mission 027-inbox-pre-scan-helper --agent <tool>:<model>:<profile>:<role>
```

## Activity Log

- 2026-04-11T18:59:24Z – claude:opus-4-6:implementer:implementer – shell_pid=55000 – Started implementation via action command
- 2026-04-11T19:02:14Z – claude:opus-4-6:implementer:implementer – shell_pid=55000 – Ready for review: Step 1 now invokes prescan.py, IDLE sentinel on empty, processes unprocessed_paths on non-empty
