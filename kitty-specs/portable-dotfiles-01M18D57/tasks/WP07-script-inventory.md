---
work_package_id: WP07
title: PATH-adjacent script inventory
dependencies:
- WP02
requirement_refs:
- FR-017
planning_base_branch: feat/portable-dotfiles
merge_target_branch: feat/portable-dotfiles
branch_strategy: Planning artifacts for this mission were generated on feat/portable-dotfiles. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/portable-dotfiles unless the human explicitly redirects the landing branch.
subtasks:
- T038
- T039
- T040
phase: Phase 4 - Verification
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: dotfiles/docs/
create_intent:
- dotfiles/docs/script-inventory.md
execution_mode: code_change
model: ''
owned_files:
- dotfiles/docs/script-inventory.md
role: curator
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP07 – PATH-adjacent script inventory

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

Decide, per script, whether it is managed or explicitly out of scope — and assert the outcome either way.

**Requirements**: FR-017

**Test criteria**: Every inventoried script is classified with a rationale; A14 passes on both machines.

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T038

Inventory every PATH entry and shell-referenced helper on both machines — `~/bin`, `~/helper-scripts`, `~/.local/bin`, `~/.npm-global/bin`, `~/go/bin`.

### Subtask T039

Classify each: bring into `dotfiles/bin`, or scope out with a written rationale. Scoping out is acceptable; scoping out **silently** is not.

### Subtask T040

Migrate those brought in scope. `claim_and_run.sh` already reads `KG_PLATFORM`; `codex-review*.sh` serve the mandatory review checkpoints.

### Subtask T041

A14 — assert resolved paths. An unmanaged entry shadowing a managed one **fails**.

## Risks & Mitigations

Unmanaged scripts on PATH can shadow managed ones and diverge between machines — which would undermine the mission's central claim.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
