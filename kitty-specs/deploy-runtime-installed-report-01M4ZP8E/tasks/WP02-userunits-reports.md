---
work_package_id: WP02
title: userunits reports what it installed
dependencies:
- WP01
requirement_refs:
- FR-001
- NFR-003
planning_base_branch: fix/deploy-runtime-installed-report
merge_target_branch: fix/deploy-runtime-installed-report
branch_strategy: Planning artifacts for this mission were generated on fix/deploy-runtime-installed-report. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deploy-runtime-installed-report unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-deploy-runtime-installed-report-01M4ZP8E
base_commit: 295a7c05a3e68a1b123e80b6351da8554799ec7a
created_at: '2026-10-15T12:17:18.129190+00:00'
subtasks:
- T005
- T006
history:
- at: '2026-10-15T09:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan revised after three post-plan reviews)
agent_profile: python-pedro
authoritative_surface: scripts/deploy/lib/
create_intent: []
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/deploy/lib/userunits.py
- tests/deploy/test_userunits.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 – userunits reports what it installed

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Branch Strategy

- **Planning base branch**: `fix/deploy-runtime-installed-report` · **Merge target branch**: `fix/deploy-runtime-installed-report`. Worktrees come from `lanes.json`.

## Context

Spec: `spec.md`, especially FR-001–FR-010 and C-001/C-002. Plan: `plan.md` (the IC named below). Contract: `contracts/installed-report.md`, which is authoritative for format, reader rules, mapper rules and result keys. Data model: `data-model.md`. Review dispositions: `research.md`.

## Objective (IC-02)

`userunits.install_units` calls `installed_report.record_installed(src, dst)` immediately after each successful `os.replace` of a **changed** file, and never for unchanged files.

## Subtasks

### T005 – Wire the producer

- Import the producer from `scripts.deploy.lib.installed_report`.
- Call it after `os.replace(tmp, dst)` succeeds, before `progress("installed", ...)`.
- Unchanged files report nothing.
- A partial install reports exactly the files that landed.
- Update the module docstring: the stderr write-failure marker is the library's only output.

### T006 – Tests (append to `tests/deploy/test_userunits.py`)

With the variable set to a `tmp_path` file:
- an install of two changed and one unchanged file reports exactly the two, with `dest` under `unit_dir`;
- a re-install of identical files reports nothing;
- a mid-install failure (monkeypatched `os.replace` raising on the 2nd file) reports only the 1st;
- with the variable unset, no file is created.

Non-vacuity: the writer cannot be removed without a test failing.

## Review Guidance

Check against the contract and C-002: nothing may widen expectations without proof. Every new behavior needs a test that fails when the behavior is removed.

## Progress & Status

`spec-kitty agent tasks add-history WP02 --note "…"` · implement: `spec-kitty agent action implement WP02 --agent claude --mission deploy-runtime-installed-report-01M4ZP8E`
