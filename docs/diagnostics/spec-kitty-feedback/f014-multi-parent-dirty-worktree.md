# Bug Report: Multi-Parent Merge-Base Creation Fails on Dirty Working Tree

**Date**: 2026-04-04
**Spec-Kitty Version**: 3.0.3
**Reporter**: Kent Gale (via Claude Code)
**Priority**: Medium — blocks parallel WP creation when planning artifacts are uncommitted
**Status**: OPEN

## Summary

When a work package depends on multiple parents (e.g., WP05 depends on WP03
and WP04), `spec-kitty agent workflow implement` attempts to create a temporary
merge-base branch by checking out a temp branch and merging the parents. This
fails if the main repo has uncommitted changes, because `git checkout` refuses
to switch branches with a dirty working tree.

The uncommitted changes are typically spec-kitty's own planning artifacts
(status.events.jsonl, status.json, workspace context files) that spec-kitty
wrote but did not commit.

## Reproduction

### Prerequisites

- Feature with WP05 depending on both WP03 and WP04
- WP03 and WP04 both approved, branches exist
- Main repo has uncommitted spec-kitty status files (normal state after
  moving WPs through lanes)

### Steps

```bash
spec-kitty agent workflow implement WP05 --feature 014-felix-core-digest --agent claude
```

### Expected Behavior

Workspace created for WP05 with merge base combining WP03 and WP04.

### Actual Behavior

```text
Error: Failed to create merge base
Reason: Failed to checkout temp branch: error: Your local changes to the
following files would be overwritten by checkout:
        docs/constitution/agent-registry.json
Please commit your changes or stash them before you switch branches.
Aborting

Recovery options:
1. Pick a dependency as the base, then merge the others in the worktree:
   spec-kitty implement WP05 --base <WPxx>
   cd .worktrees/014-felix-core-digest-WP05
   git merge 014-felix-core-digest-<WPy>
```

### Root Cause

The merge-base creation code runs `git checkout -b <temp-branch>` in the main
repo before merging parent branches. This requires a clean working tree. But
spec-kitty's own lane-transition commands (`move-task`, `mark-status`) write
status files to the main repo without committing them, so the working tree
is almost always dirty at this point in the workflow.

## Workaround Applied (F014)

```bash
git stash
spec-kitty agent workflow implement WP05 --feature 014-felix-core-digest --agent claude --base WP04
cd .worktrees/014-felix-core-digest-WP05
git merge 014-felix-core-digest-WP03 --no-edit
```

Then `git stash pop` in the main repo. This works but bypasses the automatic
merge-base creation.

## Suggested Fix

Option A: The merge-base creation code should stash dirty state before
checking out the temp branch, then pop after the merge base is created.

Option B: Create the merge base using `git merge-base` and `git merge-tree`
without checking out a branch in the main repo (operate in a detached state
or in a temporary worktree).

Option C: Commit spec-kitty's own status files before attempting merge-base
creation, since they're spec-kitty-generated artifacts anyway.

## Impact

- Any multi-parent WP in a feature with 3+ dependency paths is likely to hit
  this because the main repo accumulates uncommitted status files as WPs move
  through lanes
- The suggested recovery path in the error message works but requires manual
  git operations in the worktree

## Environment

- OS: macOS Darwin 25.3.0
- Python: 3.13.12
- spec-kitty-cli: 3.0.3
- Feature: 014-felix-core-digest (6 WPs)

## Discovered

2026-04-04 by Claude Code during F014 WP05 implementation
