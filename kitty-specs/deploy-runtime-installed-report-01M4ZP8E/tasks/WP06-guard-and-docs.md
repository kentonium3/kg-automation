---
work_package_id: WP06
title: Recurrence guard and docs
dependencies:
- WP05
requirement_refs:
- FR-008
- FR-010
- NFR-001
- C-003
- C-004
- SC-004
planning_base_branch: fix/deploy-runtime-installed-report
merge_target_branch: fix/deploy-runtime-installed-report
branch_strategy: Planning artifacts for this mission were generated on fix/deploy-runtime-installed-report. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deploy-runtime-installed-report unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-deploy-runtime-installed-report-01M4ZP8E
base_commit: 295a7c05a3e68a1b123e80b6351da8554799ec7a
created_at: '2026-10-15T12:36:00.285286+00:00'
subtasks:
- T019
- T020
- T021
history:
- at: '2026-10-15T09:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan revised after three post-plan reviews)
agent_profile: python-pedro
authoritative_surface: docs/
create_intent:
- tests/deploy/test_host_copies_report.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- tests/deploy/test_host_copies_report.py
- docs/runbooks/deployment.md
- docs/runbooks/deploy/discipline.md
- scripts/deploy/lib/README.md
- CLAUDE.md
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data-flows.md
- docs/runbooks/security-baseline-ops.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP06 – Recurrence guard and docs

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

## Objective (IC-06)

## Subtasks

### T019 – Guard `tests/deploy/test_host_copies_report.py`

- **Scope**: Python files named as `entrypoint:` by any manifest in `deploys/queued/` or `deploys/applied/`, plus top-level `scripts/deploy/deploy-*.py` and `install-*.py`. Never `felix-deployer/`, `lib/` or helper modules.
- **Offense**: an AST call to `shutil.copy`, `copy2`, `copyfile`, `copytree` or `os.replace`, or an attribute call to `write_text` or `write_bytes`, without an AST import of `scripts.deploy.lib.userunits` or `scripts.deploy.lib.installed_report`.
- **Exemption**: the file is the entrypoint of an applied deploy numbered ≤ 0032. It is evidence-bound (parse `deploys/applied/NNNN-*.yaml`) and shrink-only; a stale or redundant exemption fails.
- **Non-vacuity**: run in `tmp_path`, with a prohibited copy flagged and an adopter not flagged.
- **Stated limit**: copies delegated to helper modules escape the guard.

### T020 – Docs

- **`deployment.md` § Manifest `expected_baselines` declaration**: library installs (`userunits`) are now automatic, through the installed-file report. `expected_baselines` stays **required** for every other drift. List the historical episodes as examples: runtime `openclaw-config` ×2, 0030's shell entrypoint, and 0027-style non-repo drift (a correct alert).
- **`discipline.md`**: a line on the automatic path.
- **`lib/README.md`**: an `installed_report` row plus a contract section (the variable, format, marker, result keys).
- **`CLAUDE.md` rebaseline caveat paragraph**: one sentence on the automatic path.
- **`security-baseline-ops.md`**: the reported path.
- **`data-flows.json` + `data-flows.md`**: add the report file to the felix-deployer flow, using text insertion into the JSON.

### T021 – Validators

`validate_docs.py`, `validate_architecture_data.py`, `pytest tests/tooling` (the link checks), and a full suite run.

## Review Guidance

Check against the contract and C-002: nothing may widen expectations without proof. Every new behavior needs a test that fails when the behavior is removed.

## Progress & Status

`spec-kitty agent tasks add-history WP06 --note "…"` · implement: `spec-kitty agent action implement WP06 --agent claude --mission deploy-runtime-installed-report-01M4ZP8E`
