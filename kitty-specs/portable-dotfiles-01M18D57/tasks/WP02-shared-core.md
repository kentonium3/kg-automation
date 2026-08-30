---
work_package_id: WP02
title: Shared core
dependencies:
- WP01
requirement_refs:
- C-005
- FR-002
- FR-004
- FR-005
- FR-007
- FR-013
- FR-015
- FR-016
subtasks:
- T006
- T007
- T008
- T009
- T010
- T011
- T012
phase: Phase 2 - Configuration
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: ''
authoritative_surface: dotfiles/core/
create_intent:
- dotfiles/core/
execution_mode: code_change
model: ''
owned_files:
- dotfiles/core/zshenv
- dotfiles/core/zshrc
- dotfiles/core/zprofile
- dotfiles/core/bashrc
role: ''
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 – Shared core

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

The platform-agnostic configuration: PATH composition, account router, direnv hook, bash parity.

**Requirements**: FR-002, FR-004, FR-005, FR-007, FR-013, FR-015, FR-016, C-005

**Test criteria**: `claude_account_for_path` correct for sampled work and personal paths; PATH contains no duplicates; login shell emits 0 bytes on stderr.

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T006

`core/zshenv` — compose PATH from declared, ordered slots (user-local → language toolchains → package manager → system) and apply `typeset -U path`. PATH must be **composed**, never accumulated: `~/.local/bin` currently appears 3× on the MacBook because four separate prepends stack.

### Subtask T007

`core/zshrc` — port the account router verbatim. Hold work-repo patterns in an **inspectable array**. The list must stay a **glob** over the employer namespace; converting it back to an enumeration is exactly what silently routed a work repo to the personal account. Its explanatory comment is load-bearing — carry it.

### Subtask T008

Expose a pure `claude_account_for_path <path>` returning the config dir for a path, with no side effects. This is the observable API the helper asserts against; a banner or env var does not prove which account `claude` authenticates as.

### Subtask T009

Install the direnv hook in `zshrc` — interactive-only by design, because direnv hooks `precmd`.

### Subtask T010

`core/zprofile` — login-only concerns.

### Subtask T011

`core/bashrc` — thin PATH parity only. Roughly ten lines. Without it, `#!/bin/bash` scripts inherit the system default PATH while interactive zsh gets the composed one, so a script's `python3` differs from yours, silently.

### Subtask T012

Source `~/.config/secrets` **conditionally** — a missing file must produce zero output, so a fresh machine's first shell is silent.

## Risks & Mitigations

The glob and its comment are the highest-risk items — the natural instinct is to 'tidy' a glob into an explicit list, which is the defect.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
