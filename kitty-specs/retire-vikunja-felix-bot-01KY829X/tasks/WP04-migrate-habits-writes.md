---
work_package_id: WP04
title: Migrate habits (writes)
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
- T014
- T015
- T016
- T017
phase: Phase 1 - Migration
assignee: ''
agent: "claude:opus:reviewer-renata:reviewer"
agent_profile: python-pedro
role: implementer
shell_pid: "71492"
shell_pid_created_at: "1784846399.646192"
history:
- at: '2026-07-23T21:04:52Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/habits/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/habits/record_completion.py
- scripts/habits/set_due_dates.py
- scripts/habits/exclude_completed.py
- scripts/habits/migrate_schedule.py
- tests/habits/test_record_completion.py
- tests/habits/test_set_due_dates.py
- tests/habits/test_set_due_dates_reconcile.py
- tests/habits/test_exclude_completed.py
- tests/habits/test_exclude_completed_v2.py
- tests/habits/test_migrate_schedule.py
tags: []
---

# Work Package Prompt: WP04 — Migrate habits (writes)

## ⚡ Do This First: Load Agent Profile

Load your assigned agent profile via `/ad-hoc-profile-load` before anything else; adopt its
identity/governance/boundaries for this work package.

## Branch Strategy

- **Planning/base branch**: `fix/860-retire-vikunja-felix-bot`
- **Final merge target**: `fix/860-retire-vikunja-felix-bot`
- **Base may differ later**: `/spec-kitty.implement` populates `base_branch` on worktree creation.
- **If human instructions contradict these fields**: stop and resolve the landing branch.

**Depends on WP01.** Implement command: `spec-kitty agent action implement WP04 --agent <name>`.

---

## Objectives & Success Criteria

Migrate the four write-path habits scripts onto `VikunjaClient`, **behavior-preserving**. This is the
**highest-quirk** group — it exercises the v0.24.6 POST-partial-replace zeroing behavior in two
opposite ways, so it is the primary consumer of WP01's two update methods.

**Success criteria**:

- [ ] No raw urllib / hand-loaded token remains in the four scripts.
- [ ] `pytest tests/habits/test_record_completion.py tests/habits/test_set_due_dates*.py tests/habits/test_exclude_completed*.py tests/habits/test_migrate_schedule.py` passes.
- [ ] `record_completion.py` preserves `repeat_after`/`repeat_mode` (read-modify-write); a parity
      test proves the POSTed body still carries `repeat_after` after `done=true`.
- [ ] `migrate_schedule.py` still POSTs its intentional narrow bodies (raw-replace).
- [ ] No identity/token change (still felix-bot).

## Context & Constraints

- `scripts/habits/record_completion.py:275-280` documents the quirk explicitly: *"WHY the GET first
  (read-modify-write): Vikunja v0.24.6 treats POST … Posting {done: true} alone clears
  repeat_after."* → migrate using WP01's **read-modify-write** method (`update_task_fields`). It also
  PUTs comments (G4: PUT not POST) — use the WP01 comment op.
- `scripts/habits/migrate_schedule.py` intentionally POSTs **narrow** bodies for patch/retire/
  rollback → use WP01's **raw POST-replace** method (`replace_task_fields`). Do NOT route it through
  read-modify-write (that would change its deliberate narrow-write behavior).
- `scripts/habits/set_due_dates.py` and `exclude_completed.py` — inventory their urllib calls
  (set_due_dates has multiple HTTPError/URLError handlers at lines ~447/738; exclude_completed at
  ~255) and map each onto the client, preserving error handling.

**Reference**: `plan.md` (IC-01/IC-02), `research.md` (R1d two update shapes), and the memory
`reference_vikunja_post_partial_replace` / `reference_vikunja_recurrence_model`.

## Subtasks & Detailed Guidance

### Subtask T014 — Migrate `habits/record_completion.py` (GET-before-POST)

- **Steps**:
  1. Replace the urllib helper. For the `done=true` write, use WP01's **read-modify-write** method so
     `repeat_after`/`repeat_mode` survive (the Vikunja auto-advance trigger depends on this).
  2. Use WP01's comment op for the UI-visible mirror (PUT `/tasks/{id}/comments`, G4).
  3. Extend `tests/habits/test_record_completion.py`: assert the POSTed body after `done=true` still
     carries `repeat_after` (proves the quirk is defeated), plus emitted JSONL + exit code parity.
- **Parallel?**: [P].

### Subtask T015 — Migrate `habits/set_due_dates.py`

- **Steps**:
  1. Map each urllib call onto the client; preserve the multiple HTTPError/URLError handling paths
     and their outcomes.
  2. Extend `tests/habits/test_set_due_dates.py` + `test_set_due_dates_reconcile.py` with parity.
- **Parallel?**: [P].

### Subtask T016 — Migrate `habits/exclude_completed.py`

- **Steps**:
  1. Map the urllib request (line ~97) + URLError handling (~255) onto the client, preserving
     behavior.
  2. Extend `tests/habits/test_exclude_completed.py` + `test_exclude_completed_v2.py` with parity.
- **Parallel?**: [P].

### Subtask T017 — Migrate `habits/migrate_schedule.py` (narrow POST)

- **Steps**:
  1. Replace the urllib helper. Use WP01's **raw POST-replace** method — migrate_schedule's narrow
     bodies for patch/retire/rollback are intentional; preserve them exactly.
  2. Extend `tests/habits/test_migrate_schedule.py`: assert the POST bodies are the same narrow
     shapes as before (do not accidentally widen them via read-modify-write).
- **Parallel?**: [P].

## Definition of Done

- All four scripts migrated; the listed tests green.
- SC-001 grep clean for these four files.
- `record_completion` uses read-modify-write (repeat_after preserved); `migrate_schedule` uses
  raw-replace (narrow bodies preserved). The two are NOT conflated.
- No identity/token change.

## Risks

- **The zeroing trap**: routing `migrate_schedule` through read-modify-write, or `record_completion`
  through raw-replace, changes observable behavior. Match each script to the correct WP01 method.
- **Recurrence breakage**: losing `repeat_after` on completion breaks Vikunja auto-advance — the
  parity test guarding it is mandatory.

## Reviewer Guidance

- Confirm the correct update method per script; confirm the `repeat_after`-survives test and the
  narrow-POST-shape test both exist and pass; confirm error handling paths preserved.

## Activity Log

- 2026-07-23T22:19:15Z – claude:sonnet-5:python-pedro:implementer – shell_pid=45337 – Assigned agent via action command
- 2026-07-23T22:40:22Z – claude:sonnet-5:python-pedro:implementer – shell_pid=45337 – Ready for review — full-echo caveat resolved via inline narrow RMW: record_completion uses get_task()+replace_task_fields() (narrow 3-field), NOT update_task_fields; migrate_schedule uses replace_task_fields (narrow) + create_task_in_project; set_due_dates/exclude_completed migrated; exclude_completed_v2 untouched (no HTTP). No client-file edits. 209/209 target + 1188/1188 sweep; flake8 exit 0. Commit f3bd9423 lane-d.
- 2026-07-23T22:41:26Z – claude:opus:reviewer-renata:reviewer – shell_pid=71492 – Started review via action command
- 2026-07-23T22:47:50Z – user – shell_pid=71492 – Review passed (opus): narrow-body preservation VERIFIED — record_completion inline narrow RMW (get_task+replace_task_fields, NOT update_task_fields full-echo); migrate_schedule raw narrow replace; byte-narrow parity tests pass; create_comment(PUT)/create_task_in_project(PUT); client file untouched; 209 tests pass, token unchanged.
