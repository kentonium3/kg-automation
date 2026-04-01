# Issue Report: VS Code Crash During Merge Leaves Incomplete Cleanup

**Date:** 2026-03-30
**Version:** spec-kitty-cli 2.1.2
**Severity:** Medium - Recurring crash with no automated recovery path
**Reporter:** Claude Opus (via Kent Gale)
**Status:** OPEN - Recurred without GitLens; volume-dependent or built-in Git extension issue

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
| 4 | 2026-04-01 | F009 (009-daily-habit-checkin) | WP06 | GitLens NOT installed; 6 WPs |

Note: Incidents 1 and 2 were not fully documented. The pattern was recognized
on incident 3. Incident 4 disproved the GitLens-only hypothesis.

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

## Variable Changes Before Next Test Cycle

**2026-03-30**: GitLens (`eamodio.gitlens`) uninstalled from VS Code. This removes one of the two suspected crash contributors. The next spec-kitty merge should use the step-by-step protocol in this document to determine whether the built-in Git extension alone is sufficient to trigger the crash, or whether the crash is resolved.

Expected outcomes:
- **Crash resolved**: GitLens was the primary contributor. File a bug report against GitLens.
- **Crash persists**: Built-in Git extension is the culprit. Add `log stream --process "Code Helper"` instrumentation and test disabling the built-in Git extension (`"git.enabled": false` in VS Code settings).

## Prior Resolution Attempt (2026-03-30) — Disproved

**GitLens was removed, crash appeared resolved, but recurred on 2026-04-01.**

### Test: F007 merge (4 WPs, step-by-step from VS Code integrated terminal)

Executed the full merge protocol from the VS Code integrated terminal while
monitoring from an external terminal:

**Monitoring setup** (external terminal):
```bash
tail -f "<VS Code logs>/exthost/vscode.git/Git.log" &
log stream --predicate 'process == "Code Helper" OR process == "Electron"' --level error
```

**Merge steps executed** (VS Code integrated terminal):
1. `git checkout main && git pull --ff-only` — stable
2. `git merge --no-ff 007-vikunja-api-skill-WP04` — stable (single effective tip)
3. `git worktree remove .worktrees/007-vikunja-api-skill-WP01` — stable
4. `git worktree remove .worktrees/007-vikunja-api-skill-WP02` — stable
5. `git worktree remove .worktrees/007-vikunja-api-skill-WP03` — stable
6. `git worktree remove .worktrees/007-vikunja-api-skill-WP04` — stable
7. `git branch -d` (all 4 branches) — stable
8. Status transitions and push — stable

**Result**: All 4 worktree removals completed without a VS Code crash. The
built-in Git extension logged ENOENT warnings for the deleted worktree HEAD
files (as expected) but handled them gracefully — no window crash.

**Conclusion at the time**: GitLens was the primary contributor. This was
**disproved** by incident 4 (below).

---

## Incident 4: F009 Merge Crash (2026-04-01) — GitLens NOT Installed

### Timeline (from git reflog)

| Time | Event |
| --- | --- |
| 00:07:49 | `checkout: moving from main to main` (merge prep) |
| 00:07:50 | `merge 009-daily-habit-checkin-WP06: Merge made by 'ort' strategy` |
| 00:08–00:12 | **VS Code crash** — window dies, Claude Code session lost |
| 00:13:12 | Manual recovery: `commit F009 post-merge status updates after VS Code crash` |

### State after crash

Same pattern as all previous incidents:

| Post-merge step | State |
| --- | --- |
| Git merge commits | Completed (WP06 merge at 00:07:50) |
| Status file updates (JSONL, snapshot, frontmatter) | Written but **uncommitted** |
| Worktree removal | Completed (none remaining) |
| WP branch deletion | Completed (none remaining) |
| Push to origin | **Not performed** |

### Key differences from prior incidents

- **GitLens was NOT installed** — uninstalled 2026-03-30
- **6 WPs** — largest merge to date (F006 had 3, F007 had 4)
- Merge was run via `spec-kitty merge` (not step-by-step protocol)
- Pre-crash VS Code window logs were **not preserved** — log rotation
  removed the session before it could be captured

### Forensic analysis: spec-kitty merge execution order

Source analysis of `specify_cli/merge/executor.py` reveals the exact operation
sequence within `merge_workspace_per_wp()`:

1. **Merge WP branches** into target (lines 585–624)
   - After each merge: `_mark_wp_merged_done()` updates status files
   - Status JSONL, snapshot JSON, and frontmatter are written **but not committed**
2. **Push to remote** (lines 627–636) — if `--push` flag set
3. **Remove worktrees** (lines 639–659) — `git worktree remove --force`
4. **Delete branches** (lines 661–684) — `git branch -d`, falls back to `-D`
5. **Render completion message** (lines 686–694)
6. **Exit** — status files remain uncommitted by design

The crash consistently interrupts at step 3 or between steps 3–4. Status file
writes (step 1) have always completed before the crash point.

### Log evidence

Pre-crash VS Code session logs were lost to rotation. The post-restart session
(`20260401T001803`) shows a normal startup with no crash artifacts. The
`cli.log` at `20260401T000822` (00:08, immediately after crash) shows only
`code --list-extensions` — likely the previous Claude session's diagnostics.

No macOS crash reports were generated (`~/Library/Logs/DiagReports/` empty),
suggesting the Electron process exited uncleanly but did not segfault.

### Volume hypothesis

| Feature | WP count | GitLens | Crash? |
| --- | --- | --- | --- |
| F006 | 3 | Yes | Yes (incidents 1–3) |
| F007 | 4 | No | No |
| F009 | 6 | No | **Yes** (incident 4) |

GitLens lowers the crash threshold. Without GitLens, the built-in Git extension
alone may still crash when the worktree count is high enough. The threshold
appears to be somewhere between 4 and 6 worktrees.

**However**: bake-tracker has run spec-kitty merges with many more than 6 WPs
without crashing, also from the VS Code integrated terminal. This rules out
both WP count and terminal type as the sole factor. The crash is
**kg-automation-specific**. Possible differentiators:

- **VS Code window identity**: kg-automation and bake-tracker open in separate
  VS Code windows. The kg-automation window may carry more accumulated state
  (open editors, SCM panel state, longer uptime)
- **File watcher load**: kg-automation has ~400+ tracked files, heavily
  markdown-based; bake-tracker is smaller and Python-focused. More active
  file watchers = more concurrent reactions to worktree deletion
- **Workspace settings**: kg-automation has markdownlint, markdown word-wrap,
  and trimming enabled — extensions that register additional file watchers
  on the doc-heavy tree
- **Repo size/complexity**: kg-automation has more directories, kitty-specs
  artifacts, and nested status files — the Git extension's `status -z -uall`
  scan is heavier

The crash appears to require a threshold of concurrent file watcher + Git
extension activity during worktree removal that kg-automation exceeds but
bake-tracker does not. Next test: `"git.enabled": false` in kg-automation
workspace settings before merging.

## Recovery Script

A recovery script is available at `scripts/merge-crash-recovery.sh`. It detects
and completes the standard post-crash cleanup (commit status files, delete stale
branches, push).

## Next Steps

1. **For the next merge**: Run `log stream --predicate 'process CONTAINS "Code"'
   --level error > /tmp/vscode-merge-monitor.log &` in an external terminal
   BEFORE starting the merge. This captures crash evidence outside VS Code's
   own log system.

2. **Test disabling built-in Git extension**: Set `"git.enabled": false` in
   VS Code settings before the next merge to definitively test whether the
   Git extension is the culprit.

3. **If crash persists with git.enabled=false**: The cause is the file watcher
   subsystem itself, not any extension. Consider running merges from an external
   terminal as the permanent workaround.

---

## Environment

- OS: macOS Darwin x64 25.3.0
- Python: 3.13
- spec-kitty-cli: 2.1.2
- VS Code: 1.113.0 (Universal), commit cfbea10c5ffb233ea9177d34726e6056e89913dc
- Electron: 39.8.3
- Chromium: 142.0.7444.265
- Node.js: 22.22.1
- Feature (crash incidents 1-3): 006-goal-and-outcome-structure (3 WPs)
- Feature (resolution test): 007-vikunja-api-skill (4 WPs)
- Feature (incident 4): 009-daily-habit-checkin (6 WPs)
