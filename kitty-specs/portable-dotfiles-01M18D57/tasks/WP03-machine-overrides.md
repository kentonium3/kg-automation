---
work_package_id: WP03
title: Per-machine overrides
dependencies:
- WP02
requirement_refs:
- FR-002
- FR-006
subtasks:
- T013
- T014
- T015
- T016
phase: Phase 2 - Configuration
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: ''
authoritative_surface: dotfiles/machines/
create_intent:
- dotfiles/machines/
execution_mode: code_change
model: ''
owned_files:
- dotfiles/machines/kg_macbook_pro/local.zsh
- dotfiles/machines/kg_office4/local.zsh
role: ''
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 – Per-machine overrides

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

Supply the platform-specific members the core deliberately omits.

**Requirements**: FR-002, FR-006

**Test criteria**: Each override references only paths that exist on its own machine.

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T013

`kg_macbook_pro/local.zsh` — Homebrew `/usr/local`, `python@3.13` and `node` Cellar libexec paths, VS Code CLI, `~/go/bin` (gopls, mage), `~/.npm-global/bin` (clasp, pnpm). The last five were absent from the original constraint and are all in use.

### Subtask T014

`kg_office4/local.zsh` — linuxbrew prefix, uv-managed `python3` shim, and PATH placed in `.zshenv`. office4 is driven by `ssh office4-kgale 'cmd'`, which reads **only** `.zshenv`.

### Subtask T015

Document why the two differ, so neither is later normalised into the core. Same `python3` version (3.13.15) on both, different mechanism — Cellar libexec versus uv shim.

### Subtask T016

`KG_PLATFORM` is written **by** the installer and read **by** the config. Never both directions, or the dependency is circular.

## Risks & Mitigations

Normalising these into the core breaks one machine or the other.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
