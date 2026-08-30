---
work_package_id: WP04
title: Transactional installer
dependencies:
- WP02
- WP03
requirement_refs:
- C-003
- C-006
- FR-003
- FR-014
- NFR-001
- NFR-003
- NFR-005
planning_base_branch: feat/portable-dotfiles
merge_target_branch: feat/portable-dotfiles
branch_strategy: Planning artifacts for this mission were generated on feat/portable-dotfiles. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/portable-dotfiles unless the human explicitly redirects the landing branch.
subtasks:
- T017
- T018
- T019
- T020
- T021
- T022
- T023
phase: Phase 3 - Installer
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: dotfiles/install.sh
create_intent:
- dotfiles/install.sh
execution_mode: code_change
model: ''
owned_files:
- dotfiles/install.sh
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP04 – Transactional installer

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

`install.sh` — preflight, manifest, backup, trap-guarded swap, generated `restore.sh`.

**Requirements**: FR-003, FR-014, NFR-001, NFR-003, NFR-005, C-006

**Test criteria**: Induced failure at 3 distinct points leaves state byte-identical to the pre-run baseline (SC-012). Rollback restores all 3 prior states — file, symlink, absent (SC-013).

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T017

Platform detection via `uname -s` + hostname as a **convenience only**. `--platform` always wins. Ambiguous or unrecognised detection must **refuse** and change nothing — never guess. Write a local untracked identity file on success.

### Subtask T018

Preflight every managed target and directory. Any problem exits **before** the first modification.

### Subtask T019

Write a manifest recording each managed path's prior **type** (file / symlink / **absent**), target, and mode. This is what makes rollback correct — a backup of existing files cannot describe a `.bashrc` that did not previously exist.

### Subtask T020

Back up every existing target to `~/.dotfiles-backup-<UTC-timestamp>/`.

### Subtask T021

Install under a `trap` that restores from the manifest on any error or signal. Swap each entry by writing a temporary symlink and `mv`-ing it into place, so no entry is momentarily missing. A partial install is worse than none — it can leave a mixed environment on the machine you are logged into.

### Subtask T022

Generate a self-contained `restore.sh` into the backup dir. It must **remove** managed symlinks first (copying over a live symlink writes *through* it into the clone), restore prior type and mode, and **delete** entries that were absent before install. It must not require the clone.

### Subtask T023

Idempotency — a second run changes nothing, stacks no PATH entries, and creates no second backup.

## Risks & Mitigations

This is the highest-risk executable in the mission: it rewrites the shell of the machine running it.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
