---
title: "Bug Report: spec-kitty merge does not clean up auto-created merge-base branches"
doc_type: diagnostic
status: active
---
# Bug Report: spec-kitty merge does not clean up auto-created merge-base branches

**Date**: 2026-04-05
**Spec-Kitty Version**: 3.0.3
**Reporter**: Kent Gale (via Claude Code)
**Priority**: LOW — cruft accumulation, not destructive; high confidence
**Status**: READY TO FILE

## Summary

When a work package has multiple parent dependencies, `spec-kitty agent
workflow implement` auto-creates a temporary merge-base branch named
`<feature>-<WP>-merge-base` combining all parents. After `spec-kitty
merge` completes the feature merge into the target branch, it cleans up
all the WP branches and worktrees correctly — but leaves the
`*-merge-base` branches behind. These branches accumulate as cruft over
features.

## Reproduction

### Prerequisites

- A feature with at least one multi-parent-dependency WP (e.g., WP depends
  on both WP01 and WP02)
- All WPs approved, ready for merge

### Steps

```bash
# Implement a multi-parent WP (this creates a merge-base branch):
spec-kitty agent workflow implement WP03 --agent claude --feature <slug>
# Observe: branch 015-slug-WP03-merge-base is created

# After completing the feature:
spec-kitty merge --target main --feature <slug>

# Check remaining branches:
git branch -l "015-slug-*"
```

### Expected Behavior

After `merge` completes, all feature-related branches are deleted. The
cleanup should include the auto-created merge-base branches, since their
commits are now in the target branch's history.

### Actual Behavior

```text
$ git branch -l "015-documentation-architecture-rationalization-*"
  015-documentation-architecture-rationalization-WP03-merge-base
  015-documentation-architecture-rationalization-WP07-merge-base
  015-documentation-architecture-rationalization-WP11-merge-base
```

The 11 WP branches were correctly deleted, and all 11 worktrees were
removed. But the 3 merge-base branches (for WP03, WP07, WP11 — the
multi-parent WPs in F015) remain.

### Root Cause

Spec-kitty's merge code enumerates feature branches via the WP naming
convention (`<feature>-WP##`) but does not track or clean up the
merge-base branches it auto-generated (`<feature>-WP##-merge-base`).
After merge, these branches become orphaned.

## Workaround Applied (F015)

```bash
git branch -D 015-documentation-architecture-rationalization-WP03-merge-base
git branch -D 015-documentation-architecture-rationalization-WP07-merge-base
git branch -D 015-documentation-architecture-rationalization-WP11-merge-base
```

Safe because the commits these branches reference are all present in
`main`'s history post-merge (verified via `git log`). Used `-D` rather
than `-d` because the merge-base branches may not be ancestors of the
current HEAD by `git branch -d`'s merged-ness check, even though their
commits are included via the no-ff merge commits.

## Suggested Fix

Option A: **Extend cleanup scan.** Update the merge command to also
enumerate and delete branches matching the
`<feature>-<WP>-merge-base` pattern when it enumerates WP branches.

Option B: **Track merge-base branches explicitly.** Record the names
of auto-created merge-base branches in the feature's workspace context
(`.kittify/workspaces/<feature>-WP##.json`) at creation time, and
consult that record during cleanup.

Option C: **Use a dedicated namespace.** Place auto-created merge-base
branches under a distinct prefix (e.g., `kitty-internal/<feature>-...`)
so cleanup can blanket-delete them via prefix match.

## Impact

- Low severity — branches are orphaned but don't block any workflow
- Over many features, `git branch -l` output accumulates cruft
- Scales with number of multi-parent WPs per feature (F015 had 3)
- Minor annoyance for users who use branch-based tools (branch pickers,
  autocomplete) and have to filter past dead branches

## Environment

- OS: macOS Darwin 25.3.0
- Python: 3.13.12
- spec-kitty-cli: 3.0.3
- Feature: 015-documentation-architecture-rationalization (11 WPs, 3
  multi-parent dependencies)

## Open Questions

1. **Are there other auto-created branch patterns?** Besides
   `*-merge-base`, are there other branches spec-kitty creates under
   the hood that aren't tracked for cleanup?

2. **Does this also leave dangling worktrees in edge cases?** For F015,
   the 11 worktrees cleaned up cleanly, but each merge-base branch was
   presumably used in a temporary checkout. Confirm no dangling state.

## Next Steps

- Inspect spec-kitty-cli merge implementation to verify the cleanup
  enumeration logic
- File upstream with this report

## Discovered

2026-04-05 by Claude Code during F015 post-merge inspection. Running
journal entry: `../spec-kitty-workflow-journal.md` (2026-04-05 entry:
"spec-kitty merge cleanup misses auto-created merge-base branches").
