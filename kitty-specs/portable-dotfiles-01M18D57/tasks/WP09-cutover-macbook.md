---
work_package_id: WP09
title: 'Cutover: MacBook Pro'
dependencies:
- WP08
requirement_refs:
- FR-005
- FR-009
- FR-010
planning_base_branch: feat/portable-dotfiles
merge_target_branch: feat/portable-dotfiles
branch_strategy: Planning artifacts for this mission were generated on feat/portable-dotfiles. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/portable-dotfiles unless the human explicitly redirects the landing branch.
subtasks:
- T048
- T049
- T050
- T051
phase: Phase 5 - Cutover
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: dotfiles/docs/
create_intent:
- dotfiles/docs/cutover-macbook.md
execution_mode: code_change
model: ''
owned_files:
- dotfiles/docs/cutover-macbook.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP09 – Cutover: MacBook Pro

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

Install on the Mac, collapsing the triplicated PATH entries.

**Requirements**: FR-005, FR-009, FR-010

**Test criteria**: SC-005 satisfied; both machines pass identically.

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T048

Capture the baseline.

### Subtask T049

Run the installer.

### Subtask T050

Verify `~/.local/bin` now appears **once** (it currently appears 3×, at positions 3, 4 and 13) and that the five previously unaccounted entries — `~/go/bin`, `~/.npm-global/bin`, node and python Cellar libexec, VS Code CLI — sit in declared slots.

### Subtask T051

Full assertion run on **both** machines, confirming parity.

## Risks & Mitigations

Last, because it is the machine executing the mission — a shell broken here stops the arc.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
