---
work_package_id: WP07
title: End-to-End Verification
lane: "doing"
dependencies: [WP04, WP05, WP06]
requirement_refs:
- FR-21
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 011-second-brain-vault-cleanup-WP07-merge-base
base_commit: 317d9e7fe413d12649521666dcbae4867b45b56c
created_at: '2026-04-01T20:10:31.684002+00:00'
subtasks: [T034, T035, T036, T037, T038]
shell_pid: "35282"
agent: "claude-code"
history:
- date: '2026-04-01T18:30:16Z'
  event: created
  actor: claude
---

# WP07: End-to-End Verification

## Implementation command

```bash
spec-kitty implement WP07 --base WP06
```

## Objective

Verify that all systems work correctly with the new paths and new services:
Obsidian Sync, inbox processing, bidirectional git sync, and that no stale
vault path references remain anywhere.

## Context

- **All prior WPs must be complete** before this WP runs
- **Obsidian Sync**: Should be running on office2 pointing to `notes/`
- **Bidirectional sync timer**: Should be running every 15 minutes
- **Agent workspace files**: Should reference `notes/` paths
- **Architecture docs**: Should be updated with F011 changes
- This WP produces no new files — it is purely verification

## Subtask guidance

### T034: Run grep audit for stale path references

**Purpose**: Comprehensive search for any remaining `second-brain/vault`
references that should have been updated.

**Steps**:

1. **In the kg-automation repo** (local):
   ```bash
   grep -r 'second-brain/vault' \
     scripts/ ai-agents/ CLAUDE.md \
     docs/design/architecture/ docs/handbooks/ \
     --include='*.md' --include='*.json' --include='*.sh' --include='*.service'
   ```
   Expected: no output.

2. **On office2 deployed files**:
   ```bash
   ssh office2-claude "grep -r 'second-brain/vault' /data/services/openclaw/ /home/kgale/second-brain/.gitignore /home/kgale/.config/systemd/user/ 2>/dev/null"
   ```
   Expected: no output.

3. **Known exceptions** (historical docs — these should have `vault` references
   and that is correct):
   - `docs/func-spec/F005_*`, `F008_*`, `F010_*`, `F011_*`
   - `docs/archive/`
   - `docs/reports/`
   - `docs/design/personal-ai-system-spec-*`
   - Completed `kitty-specs/` (005–010)

**Validation**:
- [ ] Zero matches in actionable files
- [ ] Only historical/archived docs contain old path references

### T035: Verify Obsidian Sync — Mac to office2

**Purpose**: Confirm notes sync from Mac to office2 via Obsidian Sync.

**Steps**:
1. Ask Kent to create a test note in Obsidian on Mac:
   - Location: `00-Inbox/`
   - Name: `F011-sync-test.md`
   - Content: "F011 end-to-end sync verification"
2. Wait up to 5 minutes
3. Check on office2:
   ```bash
   ssh office2-claude "cat /home/kgale/second-brain/notes/00-Inbox/F011-sync-test.md 2>/dev/null"
   ```
4. If found: pass. If not: check obsidian-sync logs.

**Validation**:
- [ ] Test note appears on office2 within 5 minutes
- [ ] Content matches what was created on Mac

### T036: Verify inbox processing

**Purpose**: Confirm felix-admin-capture can process notes from the new path.

**Steps**:
1. Trigger a manual inbox processing run on office2:
   ```bash
   ssh office2-claude "cd /data/services/openclaw/inbox-agent && [run command]"
   ```
   (The exact command depends on how OpenClaw agents are invoked — check
   the inbox-agent workspace for the run command)
2. Check for errors in the output
3. Verify a new log entry in `agents/logs/`:
   ```bash
   ssh office2-claude "ls -lt /home/kgale/second-brain/agents/logs/ | head -5"
   ```

**Validation**:
- [ ] Inbox processing run completes without path-related errors
- [ ] New log file created in `agents/logs/`
- [ ] No errors referencing `vault` in the output

### T037: Verify git sync — Mac to office2

**Purpose**: Confirm non-vault content pushed from Mac reaches office2.

**Steps**:
1. On Mac, create a test file in `~/second-brain/`:
   ```bash
   echo "F011 git sync test $(date)" > ~/second-brain/agents/logs/f011-sync-test.md
   cd ~/second-brain && git add -A && git commit -m "test: F011 git sync verification" && git push
   ```
2. Wait up to 15 minutes (or trigger manual sync on office2):
   ```bash
   ssh office2-claude "systemctl --user start second-brain-sync.service"
   ```
3. Check on office2:
   ```bash
   ssh office2-claude "cat /home/kgale/second-brain/agents/logs/f011-sync-test.md"
   ```

**Validation**:
- [ ] Test file appears on office2 after sync
- [ ] `git log --oneline -3` on office2 shows the test commit

### T038: Verify git sync — office2 to origin

**Purpose**: Confirm agent-created files on office2 are pushed to origin.

**Steps**:
1. Create a test file on office2:
   ```bash
   ssh office2-claude "echo 'F011 reverse sync test' > /home/kgale/second-brain/agents/logs/f011-reverse-sync-test.md"
   ```
   Note: This file will be owned by `claude:claude` — same as real agent logs.
2. Trigger sync:
   ```bash
   # The sync script runs as kgale. Present to Kent:
   ssh office2-kgale "systemctl --user start second-brain-sync.service"
   ```
3. Wait for completion, then check on Mac:
   ```bash
   cd ~/second-brain && git pull
   cat agents/logs/f011-reverse-sync-test.md
   ```

**Validation**:
- [ ] Test file appears in Mac repo after pull
- [ ] `git log --oneline -3` on Mac shows the auto-sync commit

## Post-verification cleanup

After all tests pass, clean up test artifacts:
```bash
# On Mac
cd ~/second-brain
rm agents/logs/f011-sync-test.md agents/logs/f011-reverse-sync-test.md
git add -A && git commit -m "chore: remove F011 sync test files" && git push

# On Mac (Obsidian) — delete F011-sync-test.md from 00-Inbox
# Kent does this manually in Obsidian
```

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`

## Definition of Done

- Zero stale vault path references in actionable files
- Obsidian Sync verified: Mac → office2 within 5 minutes
- Inbox processing verified: runs cleanly with new paths
- Git sync verified: Mac → office2 within 15 minutes
- Git sync verified: office2 → origin within 15 minutes
- Test artifacts cleaned up

## Risks

- **Obsidian Sync delay**: 5-minute window may be tight depending on sync
  queue. If test fails, check service logs before declaring failure.
- **Git sync timing**: The 15-minute timer may not fire immediately. Use
  manual trigger for the test, then verify the timer is running for ongoing.
- **Agent invocation**: The exact command to trigger a manual inbox run
  depends on the OpenClaw configuration. Check the workspace README or
  agent config for the correct invocation.

## Activity Log

- 2026-04-01T20:10:32Z – claude-code – shell_pid=35282 – lane=doing – Assigned agent via workflow command
