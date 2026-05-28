---
title: "Bug Report: Sparse-checkout staleness after mission merge silently reverts merged WP content"
doc_type: diagnostic
status: active
---
# Bug Report: Sparse-checkout staleness after mission merge silently reverts merged WP content

**Date**: 2026-04-10
**Spec-Kitty Version**: 3.1.1
**Reporter**: Kent Gale (via Claude Code)
**Priority**: High — silent data loss of merged WP content under common configuration
**Status**: READY TO FILE

## Summary

When `spec-kitty agent mission merge` completes in a repo that is a git sparse checkout, the primary checkout's working tree is not refreshed to match the new `HEAD`. Subsequent `spec-kitty agent tasks status` / `move-task` / similar commands auto-stage the files that now differ from the working tree. Git reports these as "deleted" or "modified" in the staging area, but the deletions are actually the removal of content that was just merged in. If the orchestrator commits any unrelated change (e.g., a `chore:` housekeeping commit) without running `git diff --cached` first, the phantom deletions are committed silently — reverting the WP changes on `main` while still leaving them visible in the git log behind the merge commit. The bug has now reproduced twice during normal mission workflows and caused real data loss once.

## Reproduction

### Prerequisites

- Git sparse checkout on `main` (`git sparse-checkout init`)
- Spec-kitty 3.1.1
- A mission created with at least one `code_change` WP whose lane worktree modifies tracked files (e.g., docs, agent configs, code)
- The implement-review skill or manual dispatch through the standard lifecycle

### Steps

```bash
# From the primary sparse-checkout on main
spec-kitty agent mission create "example" --json
# ... write spec/plan/tasks ...

# Implement WPs in lane worktree
spec-kitty agent action implement WP01 --mission example-mission --agent <agent>
# Agent modifies tracked files in .worktrees/example-mission-lane-a/
# Agent commits + moves to for_review

# Review and approve
spec-kitty agent action review WP01 --mission example-mission --agent <agent>
spec-kitty agent tasks move-task WP01 --to approved --mission example-mission

# Merge the mission
cd /path/to/primary/checkout  # must be in the primary checkout, not a worktree
spec-kitty agent mission merge --mission example-mission

# Observe the trap
git status
```

### Expected Behavior

After `spec-kitty agent mission merge` completes successfully, the primary checkout's working tree should match `HEAD`. The merged WP content should be visible both in `git show HEAD:<file>` and on disk. `git status` should be clean (or only show legitimate untracked files unrelated to the merge).

### Actual Behavior

`git status` reports the merged files as "modified" or "deleted", with the modifications being the removal of the content that was just merged in.

```text
$ git status
On branch main
Your branch is up to date with 'origin/main'.

You are in a sparse checkout with 100% of tracked files present.

Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
	deleted:    docs/runbooks/vikunja-date-handling.md
	modified:   scripts/openclaw/agents/felix-admin-habits/AGENTS.md

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	.kittify/workspaces/025-vikunja-date-timezone-bug-lane-a.json
```

Verifying the merged content is actually in `HEAD`:

```text
$ git show HEAD:docs/runbooks/vikunja-date-handling.md | head -5
---
title: Vikunja Date Handling
doc_type: runbook
status: approved
---

$ git ls-tree HEAD docs/runbooks/vikunja-date-handling.md
100644 blob 0fbaf435d0bcd4a6fe0294cad07af25001847aca	docs/runbooks/vikunja-date-handling.md
```

The file exists in `HEAD`. It's just not in the working tree.

If the next commit in the primary checkout is run without `git diff --cached` inspection, the phantom deletions get committed. The first reproduction (mission 023) resulted in commit `84bf7b6` reverting 243 lines across 4 files — this was a real data loss event that went undetected until the next mission tried to build on those files.

### Root Cause

Two interacting behaviors:

1. **Sparse-checkout working-tree refresh.** When `HEAD` moves (e.g., via merge), git does not automatically refresh the working tree in a sparse checkout the way it does in a full checkout. The working tree on disk retains the pre-merge file contents until an explicit `git checkout HEAD -- <files>` or `git read-tree -u` operation refreshes it.

2. **Spec-kitty commands auto-stage.** Some `spec-kitty agent tasks` and `spec-kitty agent status` commands (observed with `move-task`, possibly others) appear to run the equivalent of `git add` against files they touch. In the primary checkout, they see the working-tree-vs-HEAD discrepancy from (1) and stage it as a phantom deletion.

The combination turns a silent sparse-checkout artifact into committed data loss.

## Workaround Applied (Missions 023 and 025)

### Preventive recovery (after spotting the trap)

Immediately after any `spec-kitty agent mission merge`, run `git status` in the primary checkout. If files appear as "modified" or "deleted" and the current session did not touch them, verify against `HEAD`:

```bash
# For each suspicious file
git show HEAD:<path> | head     # if this shows content, the file is in HEAD
git ls-tree HEAD -- <path>       # confirms tracked state

# Recover the working tree
git reset HEAD <files>                  # unstage phantom deletions
git checkout HEAD -- <files>             # refresh working tree from HEAD

# Verify recovery
ls -la <files>
grep <expected-content> <files>
```

### Retroactive recovery (after a phantom commit already landed)

This happened once with commit `84bf7b6` on mission 023. The fix was to restore files from a known-good commit (the mission merge commit itself, `113d734`):

```bash
git checkout 113d734 -- <affected-files>
git commit -m "fix: restore mission 023 agent file changes reverted by 84bf7b6"
git push
```

### In both cases, verify the recovery

```bash
# Content match with deployed state (if applicable)
md5 -q <repo-file>
ssh <host> "md5sum <deployed-file> | awk '{print \$1}'"
# Should match if the file is supposed to be deployed elsewhere
```

## Suggested Fix

**Option A: Refresh primary checkout after merge (recommended).**
`spec-kitty agent mission merge` should run `git checkout HEAD -- <touched-paths>` (or equivalent) in the primary checkout after the merge, so the working tree reflects the merged content. This is especially important for sparse checkouts but is a sound default for all configurations.

**Option B: Suppress auto-staging when the file hasn't been modified in the current session.**
`spec-kitty agent tasks` commands that currently auto-stage should detect that the file delta is "working tree behind HEAD" rather than "working tree ahead of HEAD" and refuse to stage in the former case. This is a narrower fix than Option A but addresses the proximate cause.

**Option C: Warn when committing deletions that restore content from behind HEAD.**
A softer mitigation: the orchestrator could print a warning when a staged deletion would remove content that is present in a reachable commit. This doesn't prevent the bug but would make it visible before the commit lands.

Option A is the cleanest root-cause fix. Option B is a good complement. Option C is a safety net if the first two can't be applied everywhere.

## Impact

- **Who hits this:** Any spec-kitty user whose primary checkout is a git sparse checkout and who runs multiple missions in sequence through the standard implement-review-merge workflow. Sparse checkouts are common in large monorepos and in workflows that use `git sparse-checkout init` to limit the visible tree.
- **How often:** Observed on every mission merge we've run in this configuration. Two distinct missions (023 and 025) have hit it. The `spec-kitty agent tasks status` command in between missions triggers auto-staging, so even missions that don't modify the affected files can inherit the phantom state.
- **What's lost:** The entire delta of any WP whose files differ between `HEAD` and the stale working tree. In mission 023, this was 243 lines across 4 files (identity header + routing logic for 4 agents) — a significant feature's worth of content reverted in a single cleanup commit.
- **Detection difficulty:** The bug is silent. `git log` and `git show HEAD` both look correct because the content IS in the merge commit. The revert is a separate subsequent commit, and its message ("chore: record done transitions for merged WPs") provides no hint that it deletes content. You only notice when something later in the workflow (a subsequent mission that edits the same file, or manual inspection) fails to find content that should be there.
- **Recovery cost:** ~35 minutes of diagnostic + recovery in mission 025 (having recognized the pattern from mission 023). First-time diagnosis in mission 023 took longer and delayed that mission's acceptance.

## Environment

- OS: macOS Darwin 25.3.0
- Python: 3.13.13
- spec-kitty-cli: 3.1.1 (installed via pipx)
- Git: stock macOS + sparse checkout on `main`
- Features affected: 023-agent-identity-whatsapp-header, 025-vikunja-date-timezone-bug
- Primary checkout: `/Users/kentgale/repos/kg-automation`
- Lane worktrees: `.worktrees/*-lane-a`

## Open Questions

1. **Is this specific to sparse checkouts, or does it also affect full checkouts under some conditions?**
   All reproductions have been on sparse checkouts. A non-sparse primary checkout may refresh automatically after merge because git doesn't have to manage a filtered working set. Worth testing both configurations before picking a fix strategy.

2. **Which spec-kitty commands exactly auto-stage?**
   We observed the phantom staging state after `spec-kitty agent mission merge` followed by subsequent `tasks mark-status` / `move-task` / `status` calls. We haven't isolated which specific command does the staging. The fix design depends on whether this is a shared helper or per-command behavior.

3. **Does `spec-kitty agent mission merge` already attempt a working-tree refresh?**
   If it does, is the sparse-checkout case simply falling through a condition that assumes a full checkout? Reading the merge implementation would confirm.

4. **Is the recovery recipe safe if the orchestrator has REAL modifications in progress?**
   Our recovery is `git reset HEAD <files>` + `git checkout HEAD -- <files>`. This discards working-tree state. If the user has intentional edits to those same files that weren't yet committed, this recipe would destroy them. A safer recovery recipe would stash first, but that adds complexity. Documentation should call this out.

## Next Steps

- File upstream in the spec-kitty issue queue with this report content
- Test reproduction in a clean sparse-checkout repo (not our production one) to isolate confounds
- Confirm whether the bug reproduces on a non-sparse full checkout
- After filing, add the upstream issue number to this file's filename (`xx_` → `<issue#>_`)
- After confirmed fix + release, move to `docs/archive/spec-kitty-feedback/`

## Discovered

2026-04-09 by Kent Gale and Claude Code during implementation of mission 023 (agent-identity-whatsapp-header). Reproduced 2026-04-10 during mission 025 (vikunja-date-timezone-bug). First reproduction caused commit `84bf7b6` on `main` to silently revert mission 023's changes; second reproduction was caught immediately and recovered before committing.
