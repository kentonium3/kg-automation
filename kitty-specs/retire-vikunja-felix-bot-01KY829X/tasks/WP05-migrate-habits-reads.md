---
work_package_id: WP05
title: Migrate habits (reads/misc) + dead-token cleanup
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-003
- NFR-001
tracker_refs: []
planning_base_branch: fix/860-retire-vikunja-felix-bot
merge_target_branch: fix/860-retire-vikunja-felix-bot
branch_strategy: Planning artifacts for this mission were generated on fix/860-retire-vikunja-felix-bot. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/860-retire-vikunja-felix-bot unless the human explicitly redirects the landing branch.
base_branch: fix/860-retire-vikunja-felix-bot
base_commit: 99db76c0f6102a6b0d86972b5b3ffccafba79626
created_at: '2026-07-23T21:04:52Z'
subtasks:
- T018
- T019
- T020
- T021
phase: Phase 1 - Migration
assignee: ''
agent: "claude:opus:reviewer-renata:reviewer"
agent_profile: python-pedro
role: implementer
shell_pid: "56408"
shell_pid_created_at: "1784845938.014625"
history:
- at: '2026-07-23T21:04:52Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/habits/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/habits/sweeper.py
- scripts/habits/identify_workout_task.py
- scripts/habits/backfill_jsonl_from_comments.py
- scripts/habits/reconcile_completions.py
- tests/habits/test_sweeper_unit.py
- tests/habits/test_sweeper_idempotent.py
- tests/habits/test_identify_workout_task.py
- tests/habits/test_backfill_jsonl_from_comments.py
- tests/habits/test_reconcile_completions.py
tags: []
---

# Work Package Prompt: WP05 — Migrate habits (reads/misc) + dead-token cleanup

## ⚡ Do This First: Load Agent Profile

Load your assigned agent profile via `/ad-hoc-profile-load` before anything else; adopt its
identity/governance/boundaries for this work package.

## Branch Strategy

- **Planning/base branch**: `fix/860-retire-vikunja-felix-bot`
- **Final merge target**: `fix/860-retire-vikunja-felix-bot`
- **Base may differ later**: `/spec-kitty.implement` populates `base_branch` on worktree creation.
- **If human instructions contradict these fields**: stop and resolve the landing branch.

**Depends on WP01.** Implement command: `spec-kitty agent action implement WP05 --agent <name>`.

---

## Objectives & Success Criteria

Migrate the read/lookup habits scripts onto `VikunjaClient`, **behavior-preserving**, and remove the
dead token reader in `reconcile_completions.py` that would otherwise noise the SC-001 grep gate.

**Success criteria**:

- [ ] No raw urllib / hand-loaded token remains in `sweeper.py`, `identify_workout_task.py`,
      `backfill_jsonl_from_comments.py`.
- [ ] `habits/reconcile_completions.py` has no dead `_read_token()` and still reads via the sync
      **cache** (not HTTP) — unchanged data path.
- [ ] `pytest tests/habits/test_sweeper*.py tests/habits/test_identify_workout_task.py tests/habits/test_backfill_jsonl_from_comments.py tests/habits/test_reconcile_completions.py` passes.
- [ ] No identity/token change (still felix-bot).

## Context & Constraints

- `scripts/habits/sweeper.py`, `identify_workout_task.py` (GET-only lookup helper, line ~89),
  `backfill_jsonl_from_comments.py` — inventory their urllib calls and map onto the client
  (reads → `get()`/`list_all_tasks()`; comments as needed via the WP01 comment op).
- `scripts/habits/reconcile_completions.py` reads Vikunja state via the **sync cache**
  (`scripts/common/sync_cache.py`), NOT raw HTTP — do **not** migrate its read path onto the client.
  It carries a **dead `_read_token()`** helper (unused — it reads from the cache). Delete the dead
  helper so SC-001's grep for `secrets/vikunja-api` token reads is unambiguous; confirm nothing else
  references it.

**Reference**: `plan.md` (IC-02 + assumptions), `research.md` (R1c), spec.md assumption re:
reconcile_completions cache-based.

## Subtasks & Detailed Guidance

### Subtask T018 — Migrate `habits/sweeper.py`

- **Steps**: map urllib calls onto the client; preserve idempotency behavior (there are dedicated
  `test_sweeper_idempotent.py` / `test_sweeper_unit.py` — extend both with parity). 
- **Parallel?**: [P].

### Subtask T019 — Migrate `habits/identify_workout_task.py`

- **Steps**: replace the GET-only urllib lookup (line ~89) with `VikunjaClient.get()` /
  `list_all_tasks()`; preserve the lookup return/error contract. Extend
  `tests/habits/test_identify_workout_task.py` with parity.
- **Parallel?**: [P].

### Subtask T020 — Migrate `habits/backfill_jsonl_from_comments.py`

- **Steps**: map its urllib calls (imports at line ~36) onto the client, preserving comment-read
  behavior. Extend `tests/habits/test_backfill_jsonl_from_comments.py` with parity.
- **Parallel?**: [P].

### Subtask T021 — Remove dead `_read_token()` from `reconcile_completions.py`

- **Steps**:
  1. Confirm `_read_token()` is unused (`grep -n _read_token scripts/habits/reconcile_completions.py`
     and repo-wide) and that the module reads via the sync cache.
  2. Delete the dead helper and any now-unused imports.
  3. Run `tests/habits/test_reconcile_completions.py` — behavior must be unchanged (cache path only).
- **Parallel?**: No — verification-sensitive; do after the migrations so the SC-001 grep is final.

## Definition of Done

- Three read scripts migrated; dead `_read_token()` removed; the listed tests green.
- SC-001 grep clean for these files; `reconcile_completions.py` still cache-based (no HTTP added).
- No identity/token change.

## Risks

- **Accidental HTTP in reconcile**: do NOT "migrate" `reconcile_completions.py` onto the client — it
  is intentionally cache-based; only remove the dead token reader.
- **Idempotency regression** in sweeper — keep both sweeper tests green.

## Reviewer Guidance

- Confirm the three reads go through the client; confirm `_read_token()` is gone and
  `reconcile_completions.py` is unchanged in data path; confirm parity tests exist.

## Activity Log

- 2026-07-23T22:19:37Z – claude:sonnet-5:python-pedro:implementer – shell_pid=45337 – Assigned agent via action command
- 2026-07-23T22:32:09Z – claude:sonnet-5:python-pedro:implementer – shell_pid=45337 – Ready for review — sweeper→replace_task_fields, identify_workout_task→get_task w/ OSError adapter, backfill→get+list_task_comments, reconcile_completions dead _read_token removed (cache-only preserved). 136 habits-read tests pass (+6 parity); flake8 baseline-clean. Commit ee738d23 on lane-e. Did not run move-task from lane (subagent).
- 2026-07-23T22:32:43Z – claude:opus:reviewer-renata:reviewer – shell_pid=56408 – Started review via action command
- 2026-07-23T22:37:27Z – user – shell_pid=56408 – Review passed (opus/reviewer-renata): no raw urllib in 3 read scripts; reconcile stays cache-only (dead _read_token removed, no HTTP added); OSError adapter preserves error contract across HTTP/network/timeout; parity tests drive real entrypoints; scope clean, no identity change. 136 tests pass.
