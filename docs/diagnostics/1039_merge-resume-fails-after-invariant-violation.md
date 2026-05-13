---
title: "Bug Report: `spec-kitty merge` cannot resume after post-merge invariant violation strands working tree"
doc_type: diagnostic
status: active
---
# Bug Report: `spec-kitty merge` cannot resume after post-merge invariant violation strands working tree

**Date**: 2026-05-13
**Spec-Kitty Version**: 3.1.8
**Reporter**: Kent Gale (via Claude Code)
**Priority**: Medium — work content reaches `main` cleanly, but mission bookkeeping (mission_number assignment, lane branch deletion, worktree removal, downstream issue auto-close hook) is left stranded and `spec-kitty merge` cannot complete on retry. Manual git intervention is required for cleanup.
**Status**: FILED - https://github.com/Priivacy-ai/spec-kitty/issues/1039

## Summary

When a `code_change` WP includes a `git mv` rename, `spec-kitty merge` successfully creates the squash commit on the target branch but its post-merge "working-tree invariant" check trips because the renamed source path reappears on disk in the primary checkout as an unexpected `A` (added) staged entry. After the operator cleans the stale file from the working tree, retrying `spec-kitty merge` fails with `Squash commit into main failed: Not currently on any branch.` — leaving the mission's bookkeeping commits (mission_number assignment), the mission branch, the lane branch, and the lane worktree all stranded. The work itself is merged correctly; only the post-merge bookkeeping is unrecoverable through the workflow.

## Reproduction

### Prerequisites

- Git sparse checkout on `main` (the same configuration that surfaced #588).
- Spec-kitty 3.1.8 (likely also reproduces in 3.1.x at and around this version).
- A mission with a `code_change` WP that includes a `git mv` rename of a tracked file as one of its subtasks.
- The implement-review skill or manual dispatch through the standard lifecycle.

### Steps

```bash
# From the primary checkout on main
spec-kitty agent mission create "example" --json
# ... write spec/plan/tasks where ONE subtask uses `git mv` to relocate a tracked file ...

# Implement WP01 in lane worktree (agent runs `git mv path/to/file new/path/to/file`)
spec-kitty agent action implement WP01 --mission example-mission --agent <agent>
# Agent commits + moves to for_review

# Review and approve
spec-kitty agent action review WP01 --mission example-mission --agent <agent>
spec-kitty agent tasks move-task WP01 --to approved --mission example-mission

# Merge the mission
cd /path/to/primary/checkout  # primary checkout, not a worktree
spec-kitty merge --mission example-mission
```

### Expected Behavior

`spec-kitty merge` completes end-to-end:

1. Squash commit lands on the target branch.
2. mission_number is assigned and applied to `meta.json` on the target branch.
3. Lane branch + mission branch are deleted.
4. Lane worktree is removed.
5. Stale-assertion check runs cleanly.
6. Downstream consumers (issue auto-close hooks, doc-audit trigger) observe a clean merged state.

### Actual Behavior

Step 1 succeeds. The squash commit lands on `main`. Then the post-merge invariant check fails because the renamed source path reappears in the primary checkout's working tree, auto-staged as `A` (added):

```text
$ spec-kitty merge --mission google-workspace-foundation-01KRH4PE
Lane-based merge for google-workspace-foundation-01KRH4PE
  Mission branch: kitty/mission-google-workspace-foundation-01KRH4PE
  Lanes: lane-a
  ✓ Gate evidence: All 1 WPs have review approval
  ✓ Gate risk: Risk score 0.00 within threshold
  ✓ Gate dependency: All dependencies complete
  Checking and merging lane-a...
  ✓ lane-a → kitty/mission-google-workspace-foundation-01KRH4PE
Assigned mission_number=36 to mission google-workspace-foundation-01KRH4PE
  Merging mission branch into main...

✓ kitty/mission-google-workspace-foundation-01KRH4PE → main
  Commit: fd46ef2
  Recording merged work packages as done...
Error: Post-merge working-tree invariant violated. The following paths diverge
from HEAD unexpectedly:
  A  scripts/google/authorize-calendar.py

Unexpected working-tree state after merge. Run `git status` to investigate
before retrying.
```

`git status` confirms the stranded staged addition:

```text
$ git status
On branch main
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
        new file:   scripts/google/authorize-calendar.py
```

The mission used `git mv scripts/google/authorize-calendar.py docs/archive/scripts/authorize-calendar.py`. `HEAD` contains the rename correctly (the file is at the new path, the old path is gone). The primary checkout's working tree, however, still has the file on disk at the OLD path, and the index has it staged as a new addition — apparently because the sparse-checkout refresh did not catch the rename's source-side deletion.

After the operator manually cleans the stale file:

```bash
git restore --staged scripts/google/authorize-calendar.py
rm scripts/google/authorize-calendar.py
# git status → working tree clean
```

The retry then fails with a different error:

```text
$ spec-kitty merge --mission google-workspace-foundation-01KRH4PE
Resuming merge for google-workspace-foundation-01KRH4PE (1/1 WPs already done)
Lane-based merge for google-workspace-foundation-01KRH4PE
  Mission branch: kitty/mission-google-workspace-foundation-01KRH4PE
  Lanes: lane-a
  ✓ Gate evidence: All 1 WPs have review approval
  ✓ Gate risk: Risk score 0.00 within threshold
  ✓ Gate dependency: All dependencies complete
  Skipping lane-a (all WPs already done)
  Merging mission branch into main...
Error: Squash commit into main failed: Not currently on any branch.
nothing to commit, working tree clean
```

The primary checkout's branch state at this point is healthy — `git branch --show-current` reports `main`, `git status` is clean, `git log --oneline -1` shows `fd46ef2`. The `Not currently on any branch` error appears to come from a branch-check inside spec-kitty's resume path, possibly against a worktree-private HEAD that detached during the prior invariant failure.

Inspecting the post-merge state:

```text
$ git log --oneline --all --graph -8
* fd46ef2 feat(kitty/mission-google-workspace-foundation-01KRH4PE): squash merge of mission
* 87b6de0 chore: Move WP01 to approved on spec google [codex:gpt-5:reviewer:reviewer]
* …
| * 171cb18 chore(google-workspace-foundation-01KRH4PE): assign mission_number=36
```

Commit `171cb18` (the mission_number=36 assignment to `meta.json`) was created on the mission branch but never propagated to `main`. Lane and mission branches remain, lane worktree remains, no auto-close hook fires on downstream issues.

### Root Cause

Suspected two-part cause, both rooted in the sparse-checkout interaction surfaced by #588:

1. **Rename source-side staleness**: when a WP's content includes a `git mv` rename of a tracked file, the source path's deletion isn't propagated to the primary checkout's working tree after the squash-merge into the target branch. The post-merge invariant check correctly flags this — the bug is upstream (the working-tree refresh after merge), not in the check itself. This is the same class of issue as #588 (sparse-checkout staleness after mission merge), now manifesting through `git mv` rather than simple modify.

2. **Resume path doesn't restore branch state**: when the invariant check aborts the merge mid-flow, spec-kitty's resume logic does not re-establish the branch context it had before aborting. The "Not currently on any branch" error suggests an internal `git rev-parse --abbrev-ref HEAD` (or similar) returns `HEAD` (detached) when run against a worktree or internal state that wasn't restored on resume. Since the merge commit IS already on `main`, the resume should be a no-op for the squash step and proceed directly to the bookkeeping cleanup steps.

## Workaround Applied (this session — 2026-05-13, work content was the Google Workspace foundation runbook + arch docs)

The work content (`fd46ef2`) was on `main` correctly. To complete the bookkeeping, the operator would need to apply the mission_number=36 assignment and clean up the lane worktree + branches manually. Manual recovery was paused on author's instruction pending this bug report.

If executed manually (NOT yet performed), the recovery would be:

```bash
# 1. Cherry-pick the mission_number assignment onto main
git cherry-pick 171cb18

# 2. Remove the lane worktree
git worktree remove .worktrees/google-workspace-foundation-01KRH4PE-lane-a

# 3. Delete the leftover branches
git branch -D kitty/mission-google-workspace-foundation-01KRH4PE-lane-a
git branch -D kitty/mission-google-workspace-foundation-01KRH4PE

# 4. Manually close the source GitHub issues (no auto-close hook fired)
gh issue close 100 --comment "Merged in fd46ef2; mission #36 (number assigned manually). See xx_merge-resume-fails-after-invariant-violation.md for the spec-kitty resume bug that prevented automated close."
gh issue close 120 --comment "Closes alongside #100 via the same merge."
```

This violates the "no workflow workarounds" rule (CLAUDE.md user-level). The author elected to file the bug report first and defer manual recovery to a follow-up decision.

## Suggested Fix

**Option A — Fix the working-tree refresh after merge so the invariant doesn't trip in the first place.**

Address the root sparse-checkout-staleness issue at the source: after a squash-merge that includes a rename, the primary checkout's working tree must be refreshed (likely a `git read-tree -m` or `git checkout-index --force` against the new HEAD, or a fresh `git checkout --force HEAD` on the affected paths). If this fix lands, the invariant check will pass on the first attempt and the entire post-merge bookkeeping sequence completes without interruption. Same fix class as #588.

**Option B — Make the resume path tolerant of the post-invariant state.**

When the resume path detects that the merge commit is already on `main` (e.g., by comparing the mission-branch's tip to `main`'s tip), skip the squash step entirely and proceed directly to the bookkeeping cleanup. The "Not currently on any branch" error suggests the resume is trying to re-run the squash step against a stale internal worktree state that no longer applies. A more defensive resume would: (a) check whether the squash commit is already present on `main`, (b) if yes, skip the merge step and jump to bookkeeping, (c) if no, restore the branch context before retrying the merge.

**Option C — Provide a `--skip-merge --continue-bookkeeping` flag for operator recovery.**

If neither (A) nor (B) is feasible in the short term, expose an escape hatch so the operator can drive the bookkeeping steps without re-running the squash logic. Failure modes covered: `--skip-merge` skips squash-and-commit; bookkeeping (mission_number assignment, branch deletion, worktree removal, downstream hooks) runs against the current state of `main`.

## Impact

- **Frequency**: Hits any mission whose WP content includes a `git mv` rename of a tracked file. Renames are not rare in docs-restructuring missions or legacy-archive missions (this session's case: archiving `scripts/google/authorize-calendar.py` to `docs/archive/scripts/`).
- **Data loss**: None for the work content — the squash commit lands on `main` correctly. The bug strands bookkeeping artifacts, not user content.
- **Downstream consequences**:
  - `mission_number` assignment commit doesn't reach `main` (mission stays unnumbered from the perspective of any consumer that reads `meta.json` on `main`).
  - Lane worktree + lane branch + mission branch remain on disk and in `git branch` listings until manually cleaned. Future `git worktree list` and `git branch` output is noisier.
  - The doc-audit-trigger / issue-auto-close hook (if wired to the post-merge step) doesn't fire — operator must manually close source issues.
  - Operator must perform the manual recovery sequence (4 commands plus issue closes), which violates the project's "no workflow workarounds" governance rule and creates audit-trail noise.

## Environment

- OS: Darwin 25.5.0 x86_64 (primary checkout on macOS)
- Python: 3.13.13
- spec-kitty-cli: 3.1.8
- Feature: `google-workspace-foundation-01KRH4PE` (issue #100 Phase 2)
- Git config: sparse-checkout enabled on `main` (legacy from spec-kitty 0.11.0–2.x era; same condition that surfaced #588)

## Open Questions

1. **Does the invariant-violation case reproduce without sparse-checkout?**
   The earlier #588 report (3.1.1 / 3.1.2) was sparse-checkout-specific and was claimed fixed in 3.1.2. The current bug is on 3.1.8 with a different working-tree symptom (staged `A` rather than staged `D`). Worth verifying whether a non-sparse repo reproduces — if not, the fix lineage of #588 needs to extend to the rename case.

2. **Is the resume's "Not currently on any branch" error always recoverable by externally restoring branch state, or is it caused by an internal worktree that the operator can't see/fix?**
   `git branch --show-current` reports `main` and `git status` is clean from the operator's perspective. If spec-kitty maintains an internal worktree under `.kittify/` or similar, that's where the detach may live — and the operator has no way to recover it short of manual cleanup.

3. **Should the post-merge invariant check be downgraded to a warning when the merge commit is already on the target?**
   The first-attempt error message ("Run `git status` to investigate before retrying") implies retry is the supported recovery. If retry can't actually recover, the message is misleading. Either the retry needs to actually work, or the message needs to reflect the manual-recovery requirement.

## Next Steps

- File upstream at `Priivacy-ai/spec-kitty` with this report as the body.
- Pending fix availability, the project's `CLAUDE.md` should add a note under "spec-kitty merge behavior" describing the `git mv` rename hazard and the manual recovery sequence so future agents and operators have it as durable institutional knowledge.
- After filing, rename this report to `{issue-number}_merge-resume-fails-after-invariant-violation.md`.

## Discovered

2026-05-13 by Kent Gale (via Claude Code Opus 4.7) during the spec-kitty mission `google-workspace-foundation-01KRH4PE` (#100 Phase 2), specifically while WP01 archived `scripts/google/authorize-calendar.py` via `git mv` as part of the foundation cleanup.
