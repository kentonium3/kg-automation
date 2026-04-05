---
title: "Feature Request: Crash Recovery for Implementation Phase"
doc_type: diagnostic
status: FILED https://github.com/Priivacy-ai/spec-kitty/issues/415
---
# Feature Request: Crash Recovery for Implementation Phase

**Date**: 2026-04-02
**Spec-Kitty Version**: 3.0.3
**Reporter**: Kent Gale (via Claude Code)
**Priority**: High — blocks resumption of any feature interrupted by a crash
**Status**: OPEN

## Summary

After a VS Code crash during the `spec-kitty implement` phase, there is no
recovery path to resume the workflow. Worktrees are destroyed but branches and
implementation commits survive. The status ledger still shows all WPs as
"planned." Spec-kitty's existing commands cannot reconcile this state — every
path forward is blocked by a precondition that assumes either the worktree
exists or the branch does not.

## Context: Why Crashes Happen

VS Code crashes during spec-kitty workflows are a recurring issue in this
project (8 incidents documented in `merge-crash-incomplete-cleanup.md`). The
confirmed root causes are:

1. **FSEvents queue overflow** — rapid directory creation/deletion during
   worktree operations overwhelms the macOS FSEvents API. The FSEvents client
   drops events, and ~700ms later all VS Code child processes receive SIGTERM
   (exit code 15). This has been observed during both merge (worktree removal)
   and implementation (worktree creation + parallel Git activity).

2. **macOS code signing enforcement** — when VS Code binaries are replaced by
   a background update mid-session, new subprocess spawns triggered by
   worktree operations hit `errSecCSStaticCodeChanged` and macOS sends SIGTERM.
   Mitigated by setting `"update.mode": "manual"` but does not address
   mechanism 1.

These are external to spec-kitty — the crashes are caused by macOS/VS Code
interactions with rapid filesystem changes. However, it would be helpful if spec-kitty
were resilient to this failure mode should the session be interrupted for any reason.

## The Stuck State

After a crash during `spec-kitty implement` with parallel WP development, the
repository is left in this state:

| Component | State |
| --- | --- |
| WP branches (WP01-WP06) | Exist with implementation commits |
| Worktrees | Gone (cleaned up by crash or OS) |
| Status ledger (status.json) | All WPs show "planned" |
| Implementation work | Preserved on branches, verified complete |

### Why Every Recovery Path Is Blocked

**`spec-kitty implement WP07 --base WP06`** fails:

```text
Error: Base workspace WP06 does not exist
Status: WP06 is in 'planned' lane but workspace missing
```

The command requires the base WP's worktree to exist.

**`spec-kitty implement WP07` (no --base, auto-merge)** fails:

```text
Error: Failed to create merge base
Reason: Merge conflict when merging 013-vikunja-task-intelligence-agent-WP06
```

The auto-merge of all dependency branches hits a conflict with no way to
resolve it interactively.

**`spec-kitty implement WP01` (recreate from root)** fails:

```text
fatal: a branch named '013-vikunja-task-intelligence-agent-WP01' already exists
```

The branch already exists with implementation work, so a new worktree can't
be created with the same branch name.

**`spec-kitty implement WP07 --base WP06 --force`** fails:
Same error as without `--force` — the flag does not bypass the workspace
existence check.

**`spec-kitty agent shim accept`** resolves context but does not update lane
status, so the ledger remains stale.

### The Circular Dependency

- To create WP07, spec-kitty needs a base WP worktree
- To create a base WP worktree, spec-kitty needs the branch to not exist
- The branch exists because implementation was completed before the crash
- There is no command to attach an existing branch to a new worktree within
  the spec-kitty workflow

## Desired Behavior

A `spec-kitty recover` command (or equivalent functionality) that can
reconcile the post-crash state:

### Option A: Dedicated Recovery Command

```bash
spec-kitty recover --feature 013-vikunja-task-intelligence-agent
```

Behavior:
1. **Detect orphaned branches** — find WP branches that exist but have no
   corresponding worktree
2. **Reconcile status** — for each orphaned branch, compare its commits
   against main to determine if implementation work exists. Update the
   status ledger to reflect reality (e.g., move from "planned" to
   "for_review" or "in_progress")
3. **Optionally recreate worktrees** — attach existing branches to new
   worktrees using `git worktree add <path> <existing-branch>` (this is
   a standard Git operation that spec-kitty currently doesn't use)
4. **Report state** — show the user what was recovered and what needs
   attention

### Option B: Make `implement` Resilient

Modify `spec-kitty implement` to handle the case where the branch already
exists:

- If the branch exists and has commits beyond the base, offer to create a
  worktree from the existing branch (using `git worktree add <path>
  <existing-branch>`) instead of failing
- If `--base WP06` is specified and WP06's worktree doesn't exist but WP06's
  branch does, create the worktree from the branch directly

### Option C: Status Reconciliation Command

```bash
spec-kitty materialize --feature 013-vikunja-task-intelligence-agent --reconcile
```

Add a `--reconcile` flag to the existing `materialize` command that:
- Scans for branches that exist but whose WP status doesn't reflect the work
- Updates the status ledger based on branch state
- Does NOT touch branches or worktrees — only fixes the ledger

This would at least unblock the `implement` command's `--base` check by
getting WP statuses out of "planned."

## Workaround

The current manual workaround (which violates the project's workflow rules)
would be:

```bash
# Recreate worktree from existing branch (standard Git, not spec-kitty)
git worktree add .worktrees/013-vikunja-task-intelligence-agent-WP07 \
  013-vikunja-task-intelligence-agent-WP06

# Rename the worktree's branch
cd .worktrees/013-vikunja-task-intelligence-agent-WP07
git checkout -b 013-vikunja-task-intelligence-agent-WP07
```

This is not recommended because it bypasses spec-kitty's state tracking and
leaves the status ledger inconsistent.

## Impact

- Any feature interrupted by a crash during implementation is unrecoverable
  through the spec-kitty workflow
- My local agent operating rules (CLAUDE.md) prohibit manual workarounds, creating
  a complete deadlock
- This has occurred once so far (F013) but the crash pattern is recurring
  (8 incidents across 7 features), so it will likely happen again

## Recovery Attempts (F013, 2026-04-02)

### Attempted: Option 1 — Merge WP01-WP06 to main via spec-kitty, then implement WP07

**Rationale**: If completed WP work lands on main, `spec-kitty implement WP07`
can branch from main without needing a base WP worktree.

**Dry-run succeeded** — `spec-kitty merge --feature 013-... --dry-run --json`
correctly identified 3 effective tip branches (WP04, WP05, WP06), planned to
skip worktree removal, and generated a valid merge plan.

**Execution failed**:

```text
Error: No WP worktrees found for feature '013-vikunja-task-intelligence-agent'.
Check the feature slug or create workspaces first.
```

The merge command's pre-flight check requires worktrees to exist, even though
the dry-run proved the merge plan would skip worktree removal. The pre-flight
gate is stricter than the actual merge logic.

**Additional note**: `spec-kitty merge` does not accept `--force` or any flag
to bypass the worktree existence check.

### Chosen: Option 2 — Manual git merge using spec-kitty's own dry-run plan

Since spec-kitty's dry-run produced the correct merge plan but execution was
blocked by a precondition check, the recovery uses the exact commands from the
dry-run output:

```bash
# Commands from spec-kitty merge --dry-run --json output:
git checkout main
git pull --ff-only
git merge --no-ff 013-vikunja-task-intelligence-agent-WP04 \
  -m 'Merge WP04 from 013-vikunja-task-intelligence-agent'
git merge --no-ff 013-vikunja-task-intelligence-agent-WP05 \
  -m 'Merge WP05 from 013-vikunja-task-intelligence-agent'
git merge --no-ff 013-vikunja-task-intelligence-agent-WP06 \
  -m 'Merge WP06 from 013-vikunja-task-intelligence-agent'
# WP01-WP03 skipped — ancestors of WP04/WP05/WP06
git branch -d 013-vikunja-task-intelligence-agent-WP01
git branch -d 013-vikunja-task-intelligence-agent-WP02
git branch -d 013-vikunja-task-intelligence-agent-WP03
git branch -d 013-vikunja-task-intelligence-agent-WP04
git branch -d 013-vikunja-task-intelligence-agent-WP05
git branch -d 013-vikunja-task-intelligence-agent-WP06
git push
```

After WP01-WP06 land on main, `spec-kitty implement WP07` should work from
main without needing a base WP worktree.

### Result: Option 1 merge succeeded, but WP07 implement still blocked

Merging WP01-WP06 to main succeeded. However, `spec-kitty implement WP07`
still fails because its auto-merge-base logic looks for the dependency
*branches* (WP01-WP06), which no longer exist after the merge:

```text
Error: Failed to create merge base
Reason: Dependency branch 013-vikunja-task-intelligence-agent-WP01 does not
exist (implement WP01 first)
```

Attempting `--base main` also fails — `--base` only accepts WP IDs:

```text
Error: Base work package main does not exist
```

**Conclusion**: spec-kitty cannot create WP07 through any supported path after
a crash recovery. The implement command assumes dependency branches always
exist, with no fallback to checking whether dependencies are already integrated
into the target branch.

### Final recovery: Manual branch creation for WP07

With spec-kitty exhausted, WP07 was created manually:

```bash
git checkout -b 013-vikunja-task-intelligence-agent-WP07 main
# Implement deploy script
# Commit and proceed to review
```

This bypasses spec-kitty's state tracking. The status ledger will remain
stale for all WPs but the implementation work is complete and on the correct
branches.

## Discovered

2026-04-02 by Kent Gale with Claude Code assistance during F013 implementation
