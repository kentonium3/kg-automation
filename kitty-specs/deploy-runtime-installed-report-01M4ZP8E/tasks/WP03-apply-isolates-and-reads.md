---
work_package_id: WP03
title: apply provides, isolates and reads the report
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-004
- FR-007
planning_base_branch: fix/deploy-runtime-installed-report
merge_target_branch: fix/deploy-runtime-installed-report
branch_strategy: Planning artifacts for this mission were generated on fix/deploy-runtime-installed-report. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deploy-runtime-installed-report unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
history:
- at: '2026-10-15T09:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan revised after three post-plan reviews)
agent_profile: python-pedro
authoritative_surface: scripts/deploy/lib/
create_intent:
- tests/deploy/test_apply_installed_report.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/deploy/lib/apply.py
- tests/deploy/test_apply_installed_report.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 – apply provides, isolates and reads the report

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

## Objective (IC-03)

`dry_run_then_apply_gate`:
- removes the variable from every command's environment;
- sets it to a fresh `mkdtemp` report path for `--apply` only;
- reads the report back;
- merges `installed_report` and `installed_report_write_failed` into **every** result returned after `--apply` ran (apply failure, post-verification failure, success).

## Subtasks

### T007 – `_run_shell(cmd, *, env=None)`

- Pass `env` through to `subprocess.run`.
- Scan the **complete** `proc.stderr` for `installed_report.WRITE_FAILED_MARKER` **before** any truncation, and set `details["installed_report_write_failed"]` (bool).
- Update the docstring to name the channel explicitly; it is not general plumbing.

### T008 – Environment isolation

- Build `base_env = {k: v for k, v in os.environ.items() if k != ENV_VAR}`.
- Every pre and post verification command and the `--dry-run` call get `env=base_env`.
- `--apply` gets `{**base_env, ENV_VAR: str(report_path)}`, where `report_path` is inside `tempfile.mkdtemp(prefix="felix-installed-report-")`.

### T009 – Read and merge on every post-apply return

- After `--apply` returns, success or failure, call `installed_report.read_report(report_path)`.
- Merge `installed_report` and `installed_report_write_failed` into the returned `LibResult.details`. This applies to the apply-failure return, the post-verification-failure return, and the success return.
- Clean up the temp directory with `shutil.rmtree(..., ignore_errors=True)`. Any setup, read or cleanup error becomes a warning in `installed_report.warnings`, never an exception.
- **Never** include these keys in returns from before `--apply` ran (tier guard, snapshot, pre-check, dry-run failure).

### T010 – Tests (`tests/deploy/test_apply_installed_report.py`)

Use real throwaway entrypoint scripts in `tmp_path` (Python with `#!/usr/bin/env python3`, `chmod +x`):

- `--dry-run` sees no variable;
- pre and post commands (`sh -c 'test -z "$FELIX_DEPLOY_INSTALLED_REPORT"'`) see none, **even when the parent environment already has it set** (monkeypatch `os.environ`);
- `--apply` sees a fresh path;
- the entrypoint writes two lines, and the result carries them;
- `--apply` exits 1 after writing, and the report is still present;
- `--apply` succeeds but the post-check fails, and the report is still present;
- the marker on stderr appears after 5000 chars of noise, giving `installed_report_write_failed` True on success;
- an entrypoint that never writes gives `missing` True;
- the temp directory is gone afterwards;
- other environment variables are preserved (set `FOO=bar` and assert the entrypoint sees it).

## Review Guidance

Check against the contract and C-002: nothing may widen expectations without proof. Every new behavior needs a test that fails when the behavior is removed.

## Progress & Status

`spec-kitty agent tasks add-history WP03 --note "…"` · implement: `spec-kitty agent action implement WP03 --agent claude --mission deploy-runtime-installed-report-01M4ZP8E`
