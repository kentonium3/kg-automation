---
work_package_id: WP10
title: Bootstrap runbook and registration
dependencies:
- WP09
requirement_refs:
- FR-011
- FR-015
subtasks:
- T052
- T053
- T054
- T055
phase: Phase 6 - Documentation
history:
- at: '2026-08-30T04:39:38.714264+00:00'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: 'curator-carla'
authoritative_surface: docs/runbooks/
create_intent:
- docs/runbooks/new-machine-bootstrap.md
execution_mode: code_change
model: ''
owned_files:
- docs/runbooks/new-machine-bootstrap.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
role: 'curator'
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP10 – Bootstrap runbook and registration

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile named in the frontmatter before parsing the rest of this prompt. If none is set, run `spec-kitty agent profile list` and pick the best match for this WP's `task_type` and `authoritative_surface`.

---

## Review Feedback

_None yet. Reviewers append here; address every item before requesting re-review._

## Objectives & Success Criteria

Document bringing up a machine from nothing, and register it.

**Requirements**: FR-011, FR-015

**Test criteria**: `validate_docs.py` passes; the runbook appears in both indexes.

## Context & Constraints

This mission's deliverable is the **private `kentonium3/dotfiles` repo** plus `$HOME` on two machines — the MacBook Pro (macOS 26, Intel) and office4 (Linux Mint 22.3). Read `spec.md`, `plan.md`, `research.md` and `contracts/` in the mission directory before starting.

Four defects motivated this mission, all found by *testing* rather than reading, and all of the shape *"it works in the shell I happened to test"*: a work repo silently routed to the personal account; Homebrew captured `python3` at 3.14 through a transitive node dependency; direnv was hooked into bash while the login shell was zsh; and PATH in `.zprofile` was invisible to `ssh host 'cmd'`.

**Constraints**: no office2 change (C-001) · `~/.config/secrets` never committed, mode 600 (C-002) · no new package sources (C-003) · the repo stays private (C-004) · no routing changes beyond the applied glob fix (C-005) · symlinks are created locally and never committed (C-006).

## Branch Strategy

Mission branch `feat/portable-dotfiles`, topology `single_branch`. Work in your lane worktree; do not commit to `main`.

## Subtasks & Detailed Guidance

### Subtask T052

Write `docs/runbooks/new-machine-bootstrap.md`. Two ordering constraints make it usable on a genuinely fresh machine: **auth before config** (the repo is private, so a machine cannot fetch its shell config before authenticating) and **secrets before verification**.

### Subtask T053

Register in `docs/INDEX.md`.

### Subtask T054

Register in `docs/DEVELOPER_PORTAL.md`.

### Subtask T055

Document rollback via the generated `restore.sh` — explicitly **not** `cp -a backup/. ~/`, which copies through live symlinks and cannot delete entries that did not previously exist.

## Risks & Mitigations

Document what was actually done in WP08/WP09, not what was intended.

## Review Guidance

Check that the code does what the subtask says **and** that its assertion is genuinely mechanical rather than aspirational — the post-plan review found two assertions that could not actually be checked as written. Verify no GNU-only tool is assumed (`timeout` is absent on macOS). Confirm nothing writes to office2 or to `~/.config/secrets`.

## Activity Log

_Append entries as work proceeds._
