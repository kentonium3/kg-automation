---
work_package_id: WP02
title: Route the 6 habits consumers through the token seam
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- NFR-001
tracker_refs: []
planning_base_branch: feat/vikunja-token-seam-kent-cutover
merge_target_branch: feat/vikunja-token-seam-kent-cutover
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-token-seam-kent-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-token-seam-kent-cutover unless the human explicitly redirects the landing branch.
subtasks:
- T004
- T005
phase: Phase 1 - Consumers
history: []
agent_profile: python-pedro
authoritative_surface: scripts/habits/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/habits/sweeper.py
- scripts/habits/record_completion.py
- scripts/habits/exclude_completed.py
- scripts/habits/set_due_dates.py
- scripts/habits/identify_workout_task.py
- scripts/habits/migrate_schedule.py
- tests/habits/test_sweeper_unit.py
- tests/habits/test_sweeper_idempotent.py
- tests/habits/test_record_completion.py
- tests/habits/test_exclude_completed.py
- tests/habits/test_exclude_completed_v2.py
- tests/habits/test_set_due_dates.py
- tests/habits/test_set_due_dates_reconcile.py
- tests/habits/test_identify_workout_task.py
- tests/habits/test_migrate_schedule.py
role: implementer
tags: []
agent: "claude"
shell_pid: "71576"
shell_pid_created_at: "1784864130.123723"
---

# Work Package Prompt: WP02 — Habits consumers

## ⚡ Do This First: Load Agent Profile

Load your assigned agent profile (`agent_profile` frontmatter) via `/ad-hoc-profile-load` before anything else.

## Branch Strategy
- Planning/base + merge target: `feat/vikunja-token-seam-kent-cutover`. `/spec-kitty.implement` sets the worktree base.

## Objective
Route the six habits consumers' token resolution through WP01's `get_vikunja_token_path()`. **Behavior-
preserving** (NFR-001): the only change is *where the token path comes from* — every request shape, exit
code, emitted record, and error string is unchanged vs HEAD. These scripts run on office2 with **no**
token CLI args, so the default is what matters.

## Subtasks

### T004 — Route the 6 scripts through the helper
For each of `sweeper.py`, `record_completion.py`, `exclude_completed.py`, `set_due_dates.py`,
`identify_workout_task.py`, `migrate_schedule.py`:
- Replace the module-level `DEFAULT_TOKEN_PATH`/`DEFAULT_VIKUNJA_TOKEN_PATH` felix-bot literal so the
  `--token-path`/`--vikunja-token-path` CLI **default** is `get_vikunja_token_path()`
  (`from scripts.common.vikunja_config import get_vikunja_token_path`).
- Keep the CLI override arg working (testing surface). Keep each script's own token-file existence check +
  error message *shape* if present (behavior-preserving) — but the default path now comes from the helper.
- After this WP, `git grep -nE "secrets/vikunja-api([^-]|$)" -- scripts/habits ':!**/__pycache__/**'`
  returns **no** match in these 6 files (the one-shot `backfill_jsonl_from_comments.py` is out of scope,
  allowlisted).

### T005 — Tests green
- Update any test that pins the old felix-bot literal to assert helper-based resolution instead.
- `python3 -m pytest tests/habits/ -q` green; behavior parity preserved.

## Definition of Done
- All 6 habits scripts resolve their default token via `get_vikunja_token_path()`; no felix-bot literal remains in them.
- `--token-path` overrides still work; habits test suite green; zero behavior change vs HEAD (still mock-level felix-bot semantics).

## Reviewer guidance
- Verify NO behavior change beyond token-path sourcing (diff each script; the delta should be the constant + import only).
- Verify the CLI override still defaults correctly and the existence-check UX is preserved.

## Activity Log

- 2026-07-24T03:36:11Z – claude – shell_pid=71576 – Assigned agent via action command
