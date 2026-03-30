# Issue Report: VS Code Crash During Merge Leaves Incomplete Cleanup

**Date:** 2026-03-30
**Version:** spec-kitty-cli 2.1.2
**Severity:** Medium - Recurring crash with no automated recovery path
**Reporter:** Claude Opus (via Kent Gale)
**Status:** DIAGNOSED - VS Code file watcher + Git extension crash on rapid worktree removal

## Summary

VS Code crashes during or immediately after the `spec-kitty merge` finalization
step, leaving post-merge cleanup incomplete. This has occurred three times in a
row across three separate implementation cycles at the same point in the merge
workflow. After the crash, `spec-kitty merge` cannot re-run because its
preconditions (worktrees exist) are no longer met, requiring manual recovery.

## Symptoms

After the crash, the following state is observed:

| Post-merge step | State after crash |
| --- | --- |
| Git merge commits | Completed |
| Status lane transitions (WP → done) | Changes written but **not committed** |
| Merge state file (.kittify/merge-state.json) | Removed (cleanup completed) |
| Worktree removal | Completed |
| WP branch deletion | **Incomplete** (stale branches remain) |
| Push to origin | **Not performed** |

## Recovery Failure

Running `spec-kitty merge --feature <slug>` after the crash fails with:

```text
Error: No WP worktrees found for feature '006-goal-and-outcome-structure'.
Check the feature slug or create workspaces first.
```

Running `spec-kitty merge --feature <slug> --dry-run --json` returns an empty
effective branch set (correct — merges are done) but plans a legacy
single-branch merge against a branch that no longer exists.

The `--resume` flag is also unusable because `.kittify/merge-state.json` was
already removed before the crash.

## Observed Incidents

| # | Date | Feature | Last WP | Notes |
| --- | --- | --- | --- | --- |
| 1 | ~2026-03 | Unknown | Unknown | First observed occurrence |
| 2 | ~2026-03 | Unknown | Unknown | Same pattern, recovered with /spec-kitty.merge |
| 3 | 2026-03-30 | F006 (006-goal-and-outcome-structure) | WP03 | Detailed state captured |

Note: Incidents 1 and 2 were not fully documented. The pattern was recognized
on incident 3.

## Root Cause (Diagnosed)

**VS Code crashes when spec-kitty removes multiple git worktrees in rapid
succession.** The crash is caused by the combined effect of file watcher
shutdowns and Git extension ENOENT errors.

### Crash sequence (from VS Code logs, incident 3)

```
11:07:23.620  [File Watcher] Watcher shutdown because watched path got deleted
11:07:23.620  [File Watcher] Watcher shutdown because watched path got deleted
11:07:23.654  [File Watcher] Watcher shutdown because watched path got deleted
11:07:23.655  [File Watcher] Watcher shutdown because watched path got deleted
11:07:23.754  [File Watcher] Watcher shutdown because watched path got deleted
11:07:23.755  [File Watcher] Watcher shutdown because watched path got deleted
                              ← 6 watcher shutdowns in 135ms
11:07:24.942  [Git] ENOENT: .git/worktrees/...-WP01/HEAD
11:07:24.945  [Git] ENOENT: .git/worktrees/...-WP02/HEAD
11:07:24.949  [Git] ENOENT: .git/worktrees/...-WP03/HEAD
                              ← 3 ENOENT errors in 7ms, then window dies
```

### Mechanism

1. VS Code's built-in Git extension auto-discovers worktrees and registers
   each as a separate repository (visible in Source Control panel)
2. GitLens also tracks all worktrees for its own features
3. VS Code's file watcher monitors the worktree directories
4. When `spec-kitty merge` removes all worktrees in rapid succession:
   - File watchers shut down en masse (6 shutdowns in 135ms for 3 WPs)
   - Git extension tries to read HEAD files for deleted worktrees → ENOENT
   - GitLens log also cuts off at the same second
   - The VS Code window crashes (all logs end abruptly)

### Why it doesn't crash in a clean test repo

The crash could not be reproduced in `spec-kitty-crash-test` (a secondary
VS Code window). In that test, the same ENOENT warnings appeared in the Git
extension log, but VS Code survived. Possible factors:

- **kg-automation has more extensions active** (GitLens, GitHub PR, Copilot,
  Ruff, Python, EditorConfig, etc.) — more concurrent reactions to the
  filesystem event storm
- **The primary window may have more state** (open editors, SCM views,
  file watchers) than a fresh secondary window
- **Timing sensitivity** — the crash may depend on how many extensions are
  mid-operation when the worktrees disappear

### Log sources

All logs from: `~/Library/Application Support/Code/logs/20260329T000641/window1/`

| Log file | Key evidence |
| --- | --- |
| `fileWatcher.log` | 6 watcher shutdowns at 11:07:23 |
| `exthost/vscode.git/Git.log` | 3 ENOENT errors at 11:07:24 (last entries) |
| `exthost/eamodio.gitlens/GitLens.log` | Abrupt end at 11:07:24 |

## Impact

- Manual recovery required after every merge (commit status files, delete
  stale branches, push)
- Risk of state inconsistency if recovery steps are missed
- `spec-kitty merge` has no idempotent recovery path for this failure mode
- Workflow trust is eroded — users learn to expect crashes at merge time

## Mitigations

### Immediate (workaround)

1. **Run merges from an external terminal** (not VS Code integrated terminal)
   to avoid the file watcher/git extension interaction
2. **Close Source Control panel** before merging to reduce git extension
   activity during worktree removal
3. **Disable GitLens temporarily** before merge operations (`Ctrl+Shift+P` →
   "Extensions: Disable" → GitLens) to reduce concurrent worktree tracking

### Recommended (spec-kitty improvement)

1. **Add delays between worktree removals** — even 1-2 seconds between each
   `git worktree remove` would spread the file watcher events and may prevent
   the cascading failure
2. **Make merge idempotent** — detect already-integrated branches and skip to
   cleanup, so the command can be re-run after a crash
3. **Commit status files before worktree removal** — the post-merge status
   transitions are the most important cleanup step; committing them before
   the risky worktree removal step would reduce the recovery burden

### VS Code bug report candidate

This may be worth reporting to VS Code. The Git extension should handle
ENOENT on worktree HEAD files gracefully (close the repository, emit a
warning) rather than crashing the window.

## Step-by-Step Reproduction Protocol

When the next multi-WP feature is ready to merge in kg-automation, execute the
merge manually step by step instead of running `spec-kitty merge`. This isolates
which operation triggers the VS Code crash.

**Important:** Run this from the VS Code integrated terminal (where the crash
occurs), not from an external terminal.

### Prerequisites

- Feature must have all WPs in `approved` lane
- You must be in the main repository directory (not a worktree)

### Step 0: Capture the planned operations

```bash
spec-kitty merge --feature <slug> --dry-run --json | python3 -m json.tool
```

Save this output. It lists the exact branches, worktree paths, and operations.

### Step 1: Checkout and update main

```bash
git checkout main
git pull --ff-only
```

Pause — observe VS Code. Stable? Continue.

### Step 2: Merge each WP branch (one at a time)

```bash
git merge --no-ff <feature>-WP01 -m 'Merge WP01 from <feature>'
# PAUSE — observe VS Code for 5-10 seconds
git merge --no-ff <feature>-WP02 -m 'Merge WP02 from <feature>'
# PAUSE — observe VS Code for 5-10 seconds
git merge --no-ff <feature>-WP03 -m 'Merge WP03 from <feature>'
# PAUSE — observe VS Code for 5-10 seconds
```

If VS Code crashes here, record which merge triggered it.

### Step 3: Remove worktrees (one at a time) — PRIME SUSPECT

Worktree removal deletes an entire directory tree that VS Code's file watcher
may be tracking. This is the most likely crash trigger.

```bash
git worktree remove .worktrees/<feature>-WP01
# PAUSE — observe VS Code for 10-15 seconds
git worktree remove .worktrees/<feature>-WP02
# PAUSE — observe VS Code for 10-15 seconds
git worktree remove .worktrees/<feature>-WP03
# PAUSE — observe VS Code for 10-15 seconds
```

If VS Code crashes here, record which worktree removal triggered it. Note
whether the crash happens immediately or after a brief delay (suggesting a
file watcher event queue).

### Step 4: Delete branches (one at a time)

```bash
git branch -d <feature>-WP01
# PAUSE — observe VS Code for 5 seconds
git branch -d <feature>-WP02
# PAUSE — observe VS Code for 5 seconds
git branch -d <feature>-WP03
# PAUSE — observe VS Code for 5 seconds
```

### Step 5: Commit status files and push

```bash
git add kitty-specs/<feature>/status.events.jsonl \
       kitty-specs/<feature>/status.json \
       kitty-specs/<feature>/tasks.md \
       kitty-specs/<feature>/tasks/*.md
git commit -m "chore: post-merge status updates for <feature>"
git push
```

### Recording results

After completing (or encountering a crash), document:

1. **Which step crashed** — step number and exact command
2. **Timing** — did the crash happen during the command or seconds after?
3. **VS Code state** — any error dialogs, frozen UI, or extension host crashes
   vs full window crash?
4. **Partial completion** — if crash occurred, which operations had already
   completed? Check with `git worktree list`, `git branch`, `git status`
5. **VS Code logs** — check `~/Library/Logs/DiagReports/` and
   `~/Library/Application Support/Code/logs/` immediately after restart

### Findings from spec-kitty-crash-test repo (2026-03-30)

Ran the full workflow in a clean test repo (spec-kitty-crash-test) from Claude
Code terminal (outside VS Code):

- **1-WP feature (001-add-changelog):** Merge completed without crash
- **3-WP feature (002-project-docs):** Merge completed without crash
- Both runs confirmed that status files are left **uncommitted** after merge
  (this is by design, not a crash artifact)
- The workflow itself is sound — the crash is likely triggered by VS Code's
  reaction to the rapid filesystem/git state changes, not by spec-kitty logic

This supports the hypothesis that the crash is VS Code-specific (file watcher,
git extension, or GitLens reacting to worktree removal + branch deletion).

## Suggested spec-kitty Improvement

Regardless of root cause, `spec-kitty merge` should handle the case where
merges completed but cleanup didn't:

- Detect that all WP branches are already integrated into the target
- Skip the merge step and proceed directly to cleanup (status commits,
  branch deletion, push)
- Make the merge command idempotent for post-crash recovery

## Manual Recovery Performed (Incident 3)

```bash
# Commit the uncommitted status file updates
git add kitty-specs/006-goal-and-outcome-structure/status.events.jsonl \
       kitty-specs/006-goal-and-outcome-structure/status.json \
       kitty-specs/006-goal-and-outcome-structure/tasks.md \
       kitty-specs/006-goal-and-outcome-structure/tasks/WP03-documentation-updates.md
git commit -m "chore: commit F006 post-merge status updates after VS Code crash"

# Delete stale branch
git branch -d 006-goal-and-outcome-structure-WP03-merge-base

# Push to origin
git push
```

## Environment

- OS: macOS Darwin x64 25.3.0
- Python: 3.13
- spec-kitty-cli: 2.1.2
- VS Code: 1.113.0 (Universal), commit cfbea10c5ffb233ea9177d34726e6056e89913dc
- Electron: 39.8.3
- Chromium: 142.0.7444.265
- Node.js: 22.22.1
- Feature: 006-goal-and-outcome-structure (3 WPs)
