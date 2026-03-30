# Issue Report: VS Code Crash During Merge Leaves Incomplete Cleanup

**Date:** 2026-03-30
**Version:** spec-kitty-cli 2.1.2
**Severity:** Medium - Recurring crash with no automated recovery path
**Reporter:** Claude Opus (via Kent Gale)
**Status:** OPEN - Stub (symptoms only, root cause unknown)

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

## Possible Causes (Not Yet Diagnosed)

The root cause is unknown. Candidates include:

- **spec-kitty merge** — rapid file writes during finalization may trigger
  a condition that crashes VS Code
- **VS Code** — file watcher or git extension reacting to rapid repo state
  changes (worktree removal, branch deletion, many file writes)
- **VS Code git extension** — the built-in git extension or GitLens may
  not handle worktree removal gracefully
- **Other VS Code extensions** — extensions reacting to file system events
  during the merge window
- **System resources** — memory or I/O pressure during the merge step
- **GitHub integration** — VS Code GitHub extensions reacting to branch state

## Impact

- Manual recovery required after every merge (commit status files, delete
  stale branches, push)
- Risk of state inconsistency if recovery steps are missed
- `spec-kitty merge` has no idempotent recovery path for this failure mode
- Workflow trust is eroded — users learn to expect crashes at merge time

## Suggested Investigation

1. Run `spec-kitty merge` from a terminal outside VS Code to test whether
   the crash is VS Code-specific
2. Disable VS Code git extensions temporarily and retry
3. Add verbose logging to the merge finalization to identify the exact
   operation that triggers the crash
4. Check VS Code crash logs (`~/Library/Logs/DiagReports/` or
   `~/Library/Application Support/Code/logs/`)

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
