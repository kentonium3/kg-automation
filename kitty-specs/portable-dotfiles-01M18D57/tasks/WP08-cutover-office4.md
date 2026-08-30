---
work_package_id: WP08
title: 'Cutover: office4'
dependencies:
- WP04
- WP06
- WP07
requirement_refs:
- C-001
- C-002
- FR-009
- FR-010
planning_base_branch: feat/portable-dotfiles
merge_target_branch: feat/portable-dotfiles
branch_strategy: Planning artifacts for this mission were generated on feat/portable-dotfiles. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/portable-dotfiles unless the human explicitly redirects the landing branch.
subtasks:
- T042
- T043
- T044
- T045
- T046
- T047
phase: Phase 5 - Cutover
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: dotfiles/docs/
create_intent:
- dotfiles/docs/cutover-office4.md
execution_mode: code_change
model: ''
owned_files:
- dotfiles/docs/cutover-office4.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP08 – Cutover: office4

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

Install from the repo on office4 and retire its five stopgap blocks.

**Requirements**: FR-009, FR-010, C-001, C-002

**Test criteria**: All assertions pass; `git commit` succeeds in kg-automation on office4 (SC-008).

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T042

Capture the `--verbose` baseline **before** any change. This is the comparison target for atomicity.

### Subtask T043

Run the installer with a second session open, so a broken shell cannot lock the machine.

### Subtask T044

Remove the five marked stopgap blocks and reconcile the stale `.bashrc`/`.profile` pair left over from before the shell became zsh.

### Subtask T045

Create `~/.config/secrets` from the template, mode 600 — **before** running verification, or A13 reports a failure whose cause is merely 'not created yet'.

### Subtask T046

Full assertion run including the real SSH probe.

### Subtask T047

**Measure** the dangling-symlink claim rather than assuming it. Planning asserted that a deleted clone degrades gracefully; that was never tested. Move or rename the clone, observe zsh's actual behaviour, restore, and record the result.

## Risks & Mitigations

office4 goes first precisely because it is **not** the machine executing this mission.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
