---
title: "F012 Merge Breadcrumbs — Incident 7 Test"
doc_type: diagnostic
status: resolved
---
# F012 Merge Breadcrumbs — Incident 7 Test

Crash reproduction protocol per merge-crash-incomplete-cleanup.md.
Running from VS Code integrated terminal. 5 worktrees, all branches already merged.

## Pre-merge state
- Feature: 012-constitution-agent-governance-setup
- All 5 WP branches already merged to main (no merge step needed)
- Remaining cleanup: 5 worktree removals, 5 branch deletions, status commit, push

## Step 0: Dry-run (COMPLETE)
- effective_wp_branches: [] (all integrated)
- planned_steps: 5 worktree removals + 5 branch deletions

## Step 1: Checkout and update main
- Status: COMPLETE — stable

## Step 3a: Remove worktree WP01
- Status: COMPLETE — stable

## Step 3b: Remove worktree WP02
- Status: COMPLETE — stable

## Step 3c: Remove worktree WP03
- Status: COMPLETE — stable

## Step 3d: Remove worktree WP04
- Status: COMPLETE — stable

## Step 3e: Remove worktree WP05
- Status: COMPLETE — stable
- NOTE: All 5 worktrees removed without crash. 5s pauses between removals.

## Step 4: Delete branches
- Status: COMPLETE — all 5 deleted, stable

## Step 5: Commit status files and push
- Status: COMPLETE — pushed to origin

## Result: NO CRASH
- All 10 cleanup steps completed without VS Code crash
- 5-second pauses between worktree removals may have prevented FSEvents overflow
- This is consistent with the FSEvents overflow theory: spacing out deletions
  avoids the event queue saturation that triggers SIGTERM
