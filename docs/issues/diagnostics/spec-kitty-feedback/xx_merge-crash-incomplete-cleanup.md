---
title: "Bug Report: spec-kitty merge is non-idempotent and leaves incomplete cleanup after interruption"
doc_type: diagnostic
status: active
---
# Bug Report: spec-kitty merge is non-idempotent and leaves incomplete cleanup after interruption

**Date**: 2026-04-05 (trimmed for filing; original observations 2026-03-29 through 2026-04-02)
**Spec-Kitty Version**: 3.0.3 (originally observed on 2.1.2; pattern unchanged through 3.0.3)
**Reporter**: Kent Gale (via Claude Code)
**Priority**: HIGH — merge operation is non-idempotent; any interruption requires manual recovery
**Status**: READY TO FILE — related to #415 (implement-phase recovery) and #410 (umbrella)

## Summary

`spec-kitty merge` performs a multi-step sequence (merge branches → push → remove worktrees → delete branches → commit status files) but is **non-idempotent**: if interrupted between steps (e.g., by a VS Code crash during rapid worktree removal), the command cannot be re-run to completion. Its pre-flight check requires worktrees to exist, even when the actual merge work is done and only cleanup remains. Additionally, status file updates are written by step 1 but committed LAST, so any interruption loses them.

Eight documented incidents across F006–F012 show the same pattern: merges complete, worktrees get removed, then VS Code crashes from FSEvents overflow, leaving stale branches, uncommitted status files, and no automated recovery path.

## Reproduction

### Prerequisites

- A feature with multiple WPs all in `approved` lane
- VS Code integrated terminal as the execution environment
- macOS (FSEvents is the Darwin-specific file system event API)

### Steps

```bash
cd <repo-root>
spec-kitty merge --target main --feature <slug>
```

### Expected Behavior

Either:
- **(a)** All cleanup steps complete atomically, OR
- **(b)** If interrupted, `spec-kitty merge` can be re-run and resumes from wherever it stopped (detecting already-merged branches, already-removed worktrees, etc.)

### Actual Behavior

**During execution**: VS Code may crash during worktree removal. System logs show FSEvents client dropping events, followed ~700ms later by SIGTERM on all VS Code child processes (exit code 15).

**After crash**: repository is left in a partially-cleaned state. Re-running `spec-kitty merge` fails:

```text
Error: No WP worktrees found for feature '<slug>'.
Check the feature slug or create workspaces first.
```

The pre-flight check requires worktrees to exist, even though they were correctly removed before the crash. Manual recovery is required to finish the cleanup.

### Root Cause (two mechanisms, mechanism 2 is the primary ongoing issue)

**Mechanism 1 — macOS code signing enforcement** (incident 5, 2026-04-01, F010):
Background VS Code updates replaced binaries mid-session. When worktree removal spawned new Code Helper subprocesses, macOS detected `errSecCSStaticCodeChanged` (error -67062) and SIGTERM'd the VS Code process tree.

**Mitigation applied**: `"update.mode": "manual"` in VS Code settings. This addresses mechanism 1 completely.

**Mechanism 2 — FSEvents queue overflow** (incident 6, 2026-04-01, F011):
Even with updates disabled and no binary replacement, the crash recurred. Log trail:

```text
16:12:04.327  First file watcher shutdown (worktree HEAD deleted)
16:12:04.939  7th file watcher shutdown
16:12:05.052  FSEvents DROPPED EVENTS: "Events were dropped by the FSEvents
              client. File system must be re-scanned."
16:12:05.655  Git ENOENT: .git/worktrees/<WP>/HEAD (×2)
16:12:05.772  shared-process crashed with code 15 'killed'
16:12:05.775  ptyHost terminated unexpectedly with code 15
16:12:05.783  fileWatcher crashed with code 15 'killed'
16:12:05.858  extensionHost crashed with code 15 'killed'
16:12:05.862  renderer process gone (reason: killed, code: 15)
```

Rapid worktree deletion saturates the macOS FSEvents event queue. When events drop, VS Code's file watcher enters an unrecoverable state and all child processes receive SIGTERM ~700ms later.

**Confirmed mitigation** (incident 7, F012, N=1): inserting a 5-second pause between each `git worktree remove` call prevents the FSEvents overflow and the crash.

## Workaround Applied (F006, F009, F010, F011)

After each crash:

```bash
# Commit uncommitted post-merge status files
git add kitty-specs/<feature>/status.events.jsonl \
       kitty-specs/<feature>/status.json \
       kitty-specs/<feature>/tasks.md \
       kitty-specs/<feature>/tasks/*.md
git commit -m "chore: commit F### post-merge status updates after VS Code crash"

# Delete stale merge-base branches that spec-kitty didn't clean up
git branch -d <feature>-WP##-merge-base

# Push to origin
git push
```

A helper script exists at `scripts/merge-crash-recovery.sh` for kg-automation's own recovery workflow.

## Suggested Fix

**Option A: Add an inter-worktree-removal delay on macOS** (addresses root cause 2).
In `specify_cli/merge/executor.py`, between worktree removals:

```python
import platform, time
if platform.system() == "Darwin":
    time.sleep(5)  # Prevent FSEvents overflow
```

Or make it a flag: `--worktree-removal-delay=<seconds>` with a 5s default on macOS, 0s elsewhere. N=1 test in incident 7 showed 5s pauses eliminate the crash, but more test data would be valuable.

**Option B: Make merge idempotent** (addresses recovery, regardless of crash cause).
Detect the post-crash state and allow re-running:

- If all WP branches are already integrated into the target, skip the merge step
- If worktrees are already gone, skip worktree removal
- If branches are already deleted, skip branch deletion
- Proceed directly to any remaining cleanup (status commits, push)

The existing pre-flight "worktrees must exist" gate is stricter than the actual merge logic needs and blocks recovery.

**Option C: Commit status files BEFORE worktree removal** (reduces data-loss risk).
Source analysis of `specify_cli/merge/executor.py` (lines 585–694) shows the order:

1. Merge WP branches (after each: `_mark_wp_merged_done()` writes status files but **does not commit**)
2. Push to remote (if `--push`)
3. Remove worktrees — **crash-prone step**
4. Delete branches
5. Exit — status files remain uncommitted by design

Committing the status file updates between step 1 and step 3 would ensure that the most important post-merge state (lane transitions) survives any crash during worktree removal.

## Impact

- Manual recovery required after every crashed merge (commit status files, delete stale branches, push)
- Recovery steps are easy to miss — leaves state inconsistency
- No idempotent recovery path — users must know the manual fix pattern
- **Affects kg-automation specifically**: 8 crash incidents across F006–F011; bake-tracker (different repo, same developer) has merged many more WPs without crashing. Project-specific factors (markdown-heavy filesystem, markdownlint+formatter, long session durations) appear to elevate kg-automation above the FSEvents overflow threshold.

## Environment

- OS: macOS Darwin x64 25.3.0
- Python: 3.13
- spec-kitty-cli: observed on 2.1.2 and 3.0.3
- VS Code: 1.113.0 (Universal)
- Electron: 39.8.3
- kg-automation repo size: ~400+ tracked markdown files

## Open Questions

1. **Is the 5-second worktree-removal delay sufficient in all cases?** Incident 7 was N=1 with 5 WPs and a short session. Need more test data to confirm the delay works under typical kg-automation session load (11+ hour sessions, 6+ WPs, markdownlint enabled).

2. **Is the linter auto-fix loop a significant FSEvents amplifier?** kg-automation disabled markdownlint auto-fix on save (2026-04-02) to reduce filesystem-event amplification, but testing pending. If it's a major amplifier, spec-kitty's guidance might include a VS Code settings recommendation for markdown-heavy repos.

3. **Why is the crash project-specific?** kg-automation hits it; bake-tracker does not. Suspected factors include markdown file count, linter/formatter load, workspace settings, and VS Code session duration. Understanding this would help characterize which users will hit the FSEvents issue and which won't.

## Next Steps

- Next multi-WP merge in kg-automation: test with updated VS Code settings (markdownlint auto-fix disabled) to isolate the linter's contribution
- If crash persists, test `time.sleep(5)` patch locally and confirm fix behavior
- Coordinate with #415 and umbrella #410 since crash-recovery across phases is a shared concern

## Related Issues

- **#415** (implement-crash-recovery-gap) — recovery FEATURE REQUEST for the `implement` phase. References this report's incident catalog as crash-frequency evidence.
- **#410** (umbrella) — broader tracking issue for workflow resilience
- **#406** (finalize-tasks-strips-dependencies) — filed; different phase, different concern

## Discovered

First observed 2026-03-29 by Kent Gale during F006 merge. Documented across 8 incidents F006–F012. Trimmed for filing on 2026-04-05 from a longer internal incident log. Full incident detail and forensic evidence (including all 8 incidents, disproved hypotheses, and detailed log analyses) retained in earlier revisions in the kg-automation repo git history.

## Appendix A: Incident Catalog

| # | Date | Feature | WPs | GitLens | Update Mode | Crash? | Mechanism Identified |
|---|---|---|---|---|---|---|---|
| 1 | ~2026-03 | Unknown | ? | yes | default | Yes | Not analyzed |
| 2 | ~2026-03 | Unknown | ? | yes | default | Yes | Not analyzed |
| 3 | 2026-03-30 | F006 | 3 | yes | default | Yes | First detailed analysis |
| 4 | 2026-04-01 | F009 | 6 | **no** | default | Yes | Disproved GitLens-only theory |
| 5 | 2026-04-01 | F010 | 4 | no | default | Yes | Code signing confirmed (mechanism 1) |
| 6 | 2026-04-01 | F011 | 7 | no | **manual** | Yes | FSEvents overflow confirmed (mechanism 2) |
| 7 | 2026-04-01 | F012 | 5 | no | manual | **No** | 5s pauses between worktree removes |
| 8 | 2026-04-05 | F015 | 11 | no | manual | **No** | 11 worktrees removed, no delay, session <3h |

Incident 8 (F015) did not crash despite having 11 worktrees — suggesting the FSEvents threshold depends on session state accumulation over time, not just worktree count. Both N=1 successful runs (7 and 8) had shorter-than-typical sessions.

## Appendix B: Post-Crash Repository State

Consistent pattern observed across incidents 3–6:

| Component | State after crash |
|---|---|
| Git merge commits | Completed |
| Status lane transitions (JSONL + JSON) | Written but **not committed** |
| Merge state file (`.kittify/merge-state.json`) | Already removed |
| Worktree removal | Completed |
| WP branch deletion | **Incomplete** (merge-base branches typically remain) |
| Push to origin | **Not performed** |
