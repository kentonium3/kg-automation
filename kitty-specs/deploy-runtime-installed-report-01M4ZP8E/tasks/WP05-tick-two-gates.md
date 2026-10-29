---
work_package_id: WP05
title: Tick folds reported baselines with two named gates
dependencies:
- WP03
- WP04
requirement_refs:
- FR-003
- FR-005
- FR-006
- FR-007
- SC-001
- SC-002
- SC-003
planning_base_branch: fix/deploy-runtime-installed-report
merge_target_branch: fix/deploy-runtime-installed-report
branch_strategy: Planning artifacts for this mission were generated on fix/deploy-runtime-installed-report. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deploy-runtime-installed-report unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-deploy-runtime-installed-report-01M4ZP8E
base_commit: 295a7c05a3e68a1b123e80b6351da8554799ec7a
created_at: '2026-10-15T12:31:54.050243+00:00'
subtasks:
- T016
- T017
- T018
history:
- at: '2026-10-15T09:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan revised after three post-plan reviews)
agent_profile: python-pedro
authoritative_surface: scripts/deploy/felix-deployer/
create_intent: []
execution_mode: code_change
lane: planned
model: claude-opus-5-5
owned_files:
- scripts/deploy/felix-deployer/_tick.py
- tests/deploy/test_tick_rebaseline.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP05 – Tick folds reported baselines with two named gates

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

## Objective (IC-05, tick half)

## Subtasks

### T016 – Two named gates

In the manifest loop:

- `declared_baselines` stays success-only and unchanged.
- New `reported_baselines` comes from **every** result whose details carry `installed_report`, whatever the outcome. Map it through `_rebaseline.baselines_for_installed_report(details["installed_report"], repo_root, Path.home())`.
- New `reported_contributors`, separate from `applied_this_tick`.
- Wrap each manifest's mapping in `try/except Exception`; a failure becomes a warning event, never a tick error.
- At the fold call, use `declared_baselines | reported_baselines` with the one-line rationale: *declared = intent (success only); reported = evidence of what landed (any outcome)*. Pass `manifest_names = applied_this_tick + reported_contributors`, deduplicated.
- Never add a failed manifest to `applied_this_tick` or to the stamping.

### T017 – Observability

Log `rebaseline_reported` per manifest whose result carried `installed_report`. Fields: `manifest_name`, `apply_ok`, `entries`, `baselines`, `rejected`, `missing`, `warnings`, `write_failed`, and `absorbed` (true when baselines are non-empty, noting that out-of-band drift on these files is absorbed).

### T018 – Tick tests (`tests/deploy/test_tick_rebaseline.py`)

Use **real reconcile** with an injected audit runner; do not stub reconcile, unlike the existing declared test at about line 1241. Use the existing harness (`_git_mock`, `_wp04_seams`, `fake_repo_with_manifest`).

- **0029 replay**: `dry_run_then_apply_gate` returns ok with `installed_report` entries mapping to the systemd surface. The audit reports `systemd-user-unit-contents.txt` drifted, so the outcome is `completed`. The same fixture without the report gives `unexpected_drift` (the control).
- A scratch destination gives `unexpected_drift`.
- A failed apply with a declared baseline folds nothing, while a failed apply with a report folds; this is the paired test.
- A post-verification failure with a report folds.
- No report gives a token identical to before (SC-003).
- A malformed `installed_report` makes the tick complete with a warning event.
- The mapper raising makes the tick complete.
- A failed manifest never appears in `rebaseline_stamped.applied_manifests`.

## Review Guidance

Check against the contract and C-002: nothing may widen expectations without proof. Every new behavior needs a test that fails when the behavior is removed.

## Progress & Status

`spec-kitty agent tasks add-history WP05 --note "…"` · implement: `spec-kitty agent action implement WP05 --agent claude --mission deploy-runtime-installed-report-01M4ZP8E`
