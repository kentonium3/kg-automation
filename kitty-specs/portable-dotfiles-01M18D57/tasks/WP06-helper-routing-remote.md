---
work_package_id: WP06
title: 'Assertion helper: routing, remote, secrets, drift'
dependencies:
- WP05
- WP02
requirement_refs:
- FR-008
- FR-015
- FR-016
subtasks:
- T031
- T032
- T033
- T034
- T035
- T036
- T037
phase: Phase 4 - Verification
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: ''
authoritative_surface: dotfiles/bin/verify-shell-env
create_intent: []
execution_mode: code_change
model: ''
owned_files:
- dotfiles/bin/verify-shell-env
role: ''
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP06 – Assertion helper: routing, remote, secrets, drift

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

The assertions needing the router API, a real SSH probe, or filesystem state.

**Requirements**: FR-008, FR-015, FR-016

**Test criteria**: A5 correct for 100% of sampled paths; A13 distinguishes missing secrets from a routing failure; A12 genuinely invokes ssh.

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T031

A5 — `claude_account_for_path` over sampled paths, including a `spec-kitty-*` repo that does **not yet exist**, since new repos in that namespace are expected.

### Subtask T032

A6 — patterns are an inspectable array; every entry either contains a glob metacharacter or is a deliberate exact-match exception. A bare literal duplicating an existing glob **fails**. Without constraining the representation this assertion is not mechanically checkable.

### Subtask T033

A7 — `CODEX_HOME` resolves to `~/.codex-work` in work repos, unset in personal.

### Subtask T034

A8 — direnv fires on `cd` into a directory containing `.envrc`.

### Subtask T035

A10 — the dotfiles clone is clean and not behind `origin`. This is what turns 'edited but never pushed' from silent drift into a caught failure.

### Subtask T036

A12 — a **real** `ssh office4-kgale 'cmd'` probe. `zsh -c` shares the shell mode but not sshd, PAM, login-shell selection, or non-TTY behaviour. Report separately; emit an explicit SKIP when unreachable — never a silent pass.

### Subtask T037

A13 — `~/.config/secrets` exists, is mode 600, and defines every name in `secrets.example`. Its absence is its **own** failure class, never surfacing as a routing failure.

## Risks & Mitigations

A5/A6 were written aspirationally in the first draft and had to be made mechanically checkable — do not weaken them back.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
