---
title: "Bug Report: review-lock.json triggers spec-kitty's own uncommitted-changes guard, blocking approve transition"
doc_type: diagnostic
status: active
---
# Bug Report: review-lock.json triggers spec-kitty's own uncommitted-changes guard, blocking approve transition

**Date**: 2026-04-10
**Spec-Kitty Version**: 3.1.1
**Reporter**: Kent Gale (via Claude Code)
**Priority**: Medium — blocks approve transition on every lane-worktree review; well-understood workaround (`--force`) is safe and deterministic
**Status**: READY TO FILE

## Summary

When a reviewer claims a WP review in a lane worktree via `spec-kitty agent action review WP## --mission <slug> --agent <name>`, spec-kitty creates `.spec-kitty/review-lock.json` inside the worktree to mark the review as in progress. The `.spec-kitty/` directory is not in `.gitignore`, so git sees it as untracked. When the reviewer then runs `spec-kitty agent tasks move-task WP## --to approved`, spec-kitty's own uncommitted-changes guard detects the untracked `.spec-kitty/` path and blocks the transition, demanding either a commit or `--force`. The bug reproduces on every lane-worktree review and requires `--force` to bypass. The `--force` workaround is safe in practice because the only "untracked" content is spec-kitty's own lock file.

## Reproduction

### Prerequisites

- Spec-kitty 3.1.1
- A mission with at least one WP in `code_change` execution mode (creates a lane worktree)
- Previous WPs implemented and in the `for_review` lane

### Steps

```bash
# 1. Implement and commit a WP in its lane worktree
cd /path/to/.worktrees/<mission>-lane-a
# ... agent does work, commits, runs move-task to for_review ...

# 2. Claim the review (from anywhere — primary checkout or worktree)
spec-kitty agent action review WP## --mission <slug> --agent <tool>:<model>:<profile>:reviewer

# This creates .spec-kitty/review-lock.json in the worktree

# 3. Complete the review (manual inspection, grep, API queries, etc.)

# 4. Attempt to approve
spec-kitty agent tasks move-task WP## --to approved --mission <slug> --note "Review passed: <summary>"
```

### Expected Behavior

The `move-task --to approved` command should succeed. Spec-kitty owns the review lifecycle — it created the lock file, it should not treat its own lock file as a blocker for the transition that closes out the review.

### Actual Behavior

The move-task command fails with an uncommitted-changes error that treats `.spec-kitty/` as implementation drift:

```text
$ spec-kitty agent tasks move-task WP02 --to approved --mission 025-vikunja-date-timezone-bug --note "Review passed"

Uncommitted implementation changes in worktree!

Modified files:
  ?? .spec-kitty/

Commit your work first:
  cd /path/to/.worktrees/<mission>-lane-a
  git add <deliverable-path-1> <deliverable-path-2> ...
  git commit -m "feat(WP##): <describe implementation>"

Then retry: spec-kitty agent tasks move-task WP## --to for_review

Or use --force to override (not recommended)
```

Two things stand out in this error:

1. **The error is generic and doesn't match the situation.** The reviewer is trying to move to `approved`, not `for_review`. The "retry" instruction at the bottom is for a different state transition. The guard fires the same error regardless of what the requested transition is.

2. **The "Modified files" list only shows `.spec-kitty/`** — the `??` prefix is git's marker for untracked files, and spec-kitty is reporting its own lock file as the sole untracked item. The guard sees untracked content and treats it as "implementation drift", when in fact it's spec-kitty's own in-progress review state.

Looking at the lock file itself:

```bash
$ ls -la .spec-kitty/
total 8
drwxr-xr-x@  3 kentgale  staff   96 Apr 10 13:53 .
drwxr-xr-x@ 26 kentgale  staff  832 Apr 10 13:53 ..
-rw-r--r--@  1 kentgale  staff  243 Apr 10 13:53 review-lock.json

$ cat .spec-kitty/review-lock.json
{
  "wp_id": "WP02",
  "agent": "claude:opus-4.6:reviewer:reviewer",
  "started_at": "2026-04-10T17:53:38Z",
  "pid": 37015
}
```

This is unambiguously spec-kitty state, not user work.

### Secondary Anomaly (observed but unconfirmed root cause)

When `move-task --to approved --force` succeeds, the output reports a transition from `in_progress` rather than `for_review`:

```text
$ spec-kitty agent tasks move-task WP02 --to approved --force --mission 025-vikunja-date-timezone-bug --note "Review passed: --force used per review-lock issue"
Branch: main (target for this mission)
Note: Using planning repo's kitty-specs/ on main (worktree copy ignored)
→ Committed status change to main branch
✓ Moved WP02 from in_progress to approved
```

But the reviewer had successfully transitioned the WP to `for_review` earlier (via a separate `move-task` command that worked). This suggests the review-claim action may not actually move the lane forward to `in_review` or similar — it just grabs the lock and leaves the lane in `in_progress`. If that's the case, the `for_review` lane in the kanban may be a display-only state that doesn't correspond to internal state tracking during lane-worktree flows. Worth investigating alongside the primary bug.

### Root Cause

Two interacting behaviors:

1. **`.spec-kitty/` is not gitignored.** When `spec-kitty agent action review` creates the lock file in the worktree, git sees the new directory as untracked. There is no `.gitignore` rule (either worktree-local or repo-wide) that excludes `.spec-kitty/`.

2. **The uncommitted-changes guard uses a broad check.** The guard (used by `move-task` and related commands) appears to run the equivalent of `git status --porcelain` and treat any non-empty output as implementation drift. It does not filter out spec-kitty's own state directories (`.spec-kitty/`, and presumably `.kittify/` or similar if they existed in the worktree).

The combination is self-blocking: spec-kitty owns the lock and the guard, and the guard refuses to let spec-kitty clean up its own state.

## Workaround Applied (Mission 025)

Used `--force` on the approve transition after verifying the only untracked content was `.spec-kitty/review-lock.json`.

```bash
spec-kitty agent tasks move-task WP02 --to approved --force \
  --mission 025-vikunja-date-timezone-bug \
  --note "Review passed: <criteria summary>. --force used to bypass review-lock guard (see upstream bug)"
```

**Safety considerations for this workaround:**

- Before using `--force`, verify with `git status` that the ONLY untracked content is `.spec-kitty/`. If any real user files are also untracked, `--force` would bypass the guard on those too and skip their legitimate review.
- The lock file is cleaned up automatically after the successful approve transition (`.spec-kitty/` is empty afterward).
- The same workaround is needed for every lane-worktree review. We've hit it twice in the same mission (mission 025 WP02 and WP03) and the pattern is deterministic.

## Suggested Fix

**Option A: Exclude `.spec-kitty/` from the uncommitted-changes guard (recommended).**
The guard should filter its working-tree scan to exclude spec-kitty's own state directories. Something like:

```python
ignored_paths = {'.spec-kitty', '.kittify', 'kitty-specs'}
drift_files = [
    p for p in git_status_porcelain()
    if not any(p.startswith(prefix) for prefix in ignored_paths)
]
```

This is the cleanest fix: the guard continues to catch genuine drift but stops flagging spec-kitty's own artifacts.

**Option B: Auto-gitignore `.spec-kitty/` in every worktree spec-kitty creates.**
When `spec-kitty agent action implement` or `spec-kitty agent action review` create/enter a worktree, write `.spec-kitty/` to the worktree's `.git/info/exclude` (which is per-worktree and doesn't require committing a `.gitignore` change). Then `git status` stops reporting the directory as untracked and the guard stops seeing it.

This fixes the symptom but leaves the underlying "guard treats spec-kitty state as drift" issue latent.

**Option C: Clean up the lock file before the guard check runs.**
The `move-task --to approved` command knows it's closing out a review. It could remove the lock file before running the uncommitted-changes guard. This is the narrowest fix but creates a specific ordering constraint inside the command.

**Option D: Document `--force` as the expected workaround.**
If none of the above is practical, document that `--force` is required on approve/reject transitions when `.spec-kitty/` is present. This is the least-good option because it makes `--force` routine, which erodes its signal value for genuine force conditions.

Option A is the best fix. Option B is a good complement. Option C is acceptable but narrower. Option D is a fallback only if the first three can't be done.

## Impact

- **Who hits this:** Any user running a `code_change` execution mode mission where WPs use lane worktrees and reviews are dispatched via `spec-kitty agent action review`. This is the standard lane-worktree flow — every review in this mode triggers the bug.
- **How often:** Every single review of a lane-worktree WP. Reproduced on both WP02 and WP03 of the same mission in quick succession.
- **What's lost:** Nothing, IF the reviewer knows to check `git status` before using `--force` and IF the only untracked content is `.spec-kitty/`. But:
  - A naive reviewer who blindly follows the error's suggestion to `git add` and commit would commit spec-kitty's lock file to the lane branch, which is wrong and may cause downstream issues.
  - A reviewer who has unrelated untracked files in the worktree (unlikely but possible) and uses `--force` to bypass the guard would skip reviewing those too.
  - Every review needs `--force`, which erodes the user's ability to distinguish "this is routine" from "something is really wrong and I'm bypassing a guard intentionally".
- **Workflow friction:** Every review cycle has an extra friction point. For missions with many WPs, this adds up.
- **Detection difficulty:** Low. The error is immediate and visible. The trap is that the error message suggests the wrong remedy ("commit your work first") and the user has to notice the `??` prefix on `.spec-kitty/` to understand it's spec-kitty's own state.

## Environment

- OS: macOS Darwin 25.3.0
- Python: 3.13.13
- spec-kitty-cli: 3.1.1 (installed via pipx)
- Git: stock macOS
- Primary checkout: `/Users/kentgale/repos/kg-automation` (sparse checkout on main)
- Lane worktree: `.worktrees/025-vikunja-date-timezone-bug-lane-a`
- Mission: 025-vikunja-date-timezone-bug
- Execution mode for affected WPs: `code_change` (lane worktree)

## Open Questions

1. **Is the review-lock intended to be visible in the worktree at all?**
   Could the lock be stored outside the worktree (e.g., in `~/.spec-kitty/locks/` or in the `.kittify/` directory that lives in the main repo)? That would avoid the interaction with the worktree's git state entirely. Moving the lock out of the worktree is a bigger change but would address the root "self-blocking" pattern more fundamentally than filtering the guard.

2. **Does the same bug affect the reject transition (`move-task --to planned --review-feedback-file ...`)?**
   We haven't hit a rejection cycle yet so we haven't tested. If the reject transition also runs through the same uncommitted-changes guard, it would fail with the same error, and the cycle-tracking rejection workflow from the `spec-kitty-implement-review` skill would break on every rejection.

3. **Is the secondary state anomaly (approve reports `from in_progress` instead of `from for_review`) also a symptom of the same bug, or independent?**
   If the review-claim action fails to advance the lane state due to the lock interaction, the secondary anomaly may be part of the same root cause. If the claim advances state normally but the approve transition sees stale state, it's a second bug in the same area.

4. **Does this affect `planning_artifact` missions?**
   In a planning_artifact mission (no lane worktree, work happens in the primary checkout), the review lock would presumably also land in a `.spec-kitty/` directory — but in the primary checkout. We saw WP01 of mission 025 (planning_artifact mode) approved without this error, which suggests the bug may be specific to lane-worktree flows. Worth confirming whether planning_artifact reviews create a lock at all.

## Discovered

2026-04-10 by Kent Gale and Claude Code during mission 025-vikunja-date-timezone-bug (Vikunja date timezone bug fix). Two consecutive reproductions on WP02 and WP03 of the same mission during the implement-review-merge cycle driven by the `spec-kitty-implement-review` skill.
