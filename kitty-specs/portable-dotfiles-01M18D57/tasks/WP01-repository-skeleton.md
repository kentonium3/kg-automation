---
work_package_id: WP01
title: Repository skeleton
dependencies: []
requirement_refs:
- C-002
- C-004
- FR-001
- FR-002
- FR-012
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Foundation
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: 'implementer-ivan'
authoritative_surface: dotfiles/
create_intent:
- dotfiles/core/
- dotfiles/machines/
- dotfiles/bin/
execution_mode: code_change
model: ''
owned_files:
- dotfiles/README.md
- dotfiles/secrets.example
- dotfiles/.gitignore
role: 'implementer'
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 – Repository skeleton

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

Fix the layout, override-selection convention, and README so later work packages build against a stable shape.

**Requirements**: FR-001, FR-002, FR-012, C-002, C-004

**Test criteria**: Tree matches plan.md Project Structure. `secrets.example` contains zero value-shaped strings.

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T001

Create the `core/`, `machines/`, `bin/` tree.

### Subtask T002

Write `README.md` stating the symlink model explicitly: `$HOME` entries are symlinks into the **local** clone, and GitHub is transport between machines, not a symlink target. This distinction was a real source of confusion during planning.

### Subtask T003

Create `machines/kg_macbook_pro/` and `machines/kg_office4/` stubs.

### Subtask T004

Write `secrets.example` — variable names only. A value appearing here is a defect, not a convenience.

### Subtask T005

Write `.gitignore` covering the local identity file and any install artefacts.

## Risks & Mitigations

Layout churn later is expensive — the installer and the helper both encode these paths.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
