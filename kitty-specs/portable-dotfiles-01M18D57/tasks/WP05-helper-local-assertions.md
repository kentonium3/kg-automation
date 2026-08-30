---
work_package_id: WP05
title: 'Assertion helper: local shell properties'
dependencies:
- WP01
requirement_refs:
- FR-008
- NFR-002
- NFR-004
subtasks:
- T024
- T025
- T026
- T027
- T028
- T029
- T030
phase: Phase 4 - Verification
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: 'implementer-ivan'
authoritative_surface: dotfiles/bin/verify-shell-env
create_intent:
- dotfiles/bin/verify-shell-env
execution_mode: code_change
model: ''
owned_files:
- dotfiles/bin/verify-shell-env
role: 'implementer'
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP05 – Assertion helper: local shell properties

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

The helper skeleton plus every assertion needing no network or router API.

**Requirements**: FR-008, NFR-002, NFR-004

**Test criteria**: Exits 0 on a correct machine; exits non-zero naming the assertion for each of 5 deliberately broken properties.

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T024

Harness — spawn `zsh -lic`, `zsh -ic`, `zsh -c`; PASS/FAIL/SKIP per assertion; `--verbose` prints resolved values so it doubles as the pre-cutover baseline capture.

### Subtask T025

A1 — every managed `$HOME` entry is a symlink resolving inside the clone.

### Subtask T026

A2 — `~/.local/bin` appears **exactly once**, ahead of the package-manager prefix, ahead of `/usr/bin`.

### Subtask T027

A3 — all three invocation types resolve identical `python3`, `git`, `node`.

### Subtask T028

A4 — `python3` matches the machine's intended interpreter.

### Subtask T029

A9 — login shell emits **0 bytes** on stderr.

### Subtask T030

A11 — `#!/bin/bash` and interactive zsh resolve the same `python3`.

## Risks & Mitigations

**Spawn, never introspect.** A helper that checks only the shell it runs in reproduces the exact blind spot this mission exists to close. No GNU-only tools — `timeout` does not exist on macOS.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
