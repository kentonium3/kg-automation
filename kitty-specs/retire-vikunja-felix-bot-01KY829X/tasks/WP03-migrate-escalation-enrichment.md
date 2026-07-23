---
work_package_id: WP03
title: Migrate escalation + enrichment
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
- T010
- T011
- T012
- T013
phase: Phase 1 - Migration
assignee: ''
agent: "claude:sonnet-5:python-pedro:implementer"
agent_profile: python-pedro
role: implementer
shell_pid: "45337"
shell_pid_created_at: "1784845116.939297"
history:
- at: '2026-07-23T21:04:52Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/escalation/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/escalation/record_completion.py
- scripts/escalation/reconcile_completions.py
- scripts/enrichment/record_completion.py
- scripts/enrichment/reconcile_completions.py
- tests/escalation/test_record_completion.py
- tests/escalation/test_reconcile_completions.py
- tests/enrichment/test_record_completion.py
- tests/enrichment/test_reconcile_completions.py
tags: []
---

# Work Package Prompt: WP03 — Migrate escalation + enrichment

## ⚡ Do This First: Load Agent Profile

Load your assigned agent profile via `/ad-hoc-profile-load` before anything else; adopt its
identity/governance/boundaries for this work package.

## Branch Strategy

- **Planning/base branch**: `fix/860-retire-vikunja-felix-bot`
- **Final merge target**: `fix/860-retire-vikunja-felix-bot`
- **Base may differ later**: `/spec-kitty.implement` populates `base_branch` on worktree creation.
- **If human instructions contradict these fields**: stop and resolve the landing branch.

**Depends on WP01.** Implement command: `spec-kitty agent action implement WP03 --agent <name>`.

---

## Objectives & Success Criteria

Migrate the four escalation/enrichment completion + reconcile modules off raw urllib onto
`VikunjaClient`, **behavior-preserving**. These are structurally similar (escalation and enrichment
mirror each other's urllib helper).

**Success criteria**:

- [ ] No raw urllib / hand-loaded token remains in the four modules.
- [ ] `pytest tests/escalation/ tests/enrichment/` passes.
- [ ] Each consumer has a parity test proving identical requests **and** domain effects (emitted
      records/state, exit codes, error strings).
- [ ] escalation's `PATCH /tasks/{id}` (done / due_date) now goes through the WP01 `patch()` method.
- [ ] No identity/token change (still felix-bot).

## Context & Constraints

- `scripts/escalation/record_completion.py:452` calls `_http_request("PATCH", url, token, body=…)`
  for `done` and due_date updates — uses the WP01 `patch()` method now. Its message names the failed
  sub-step (`PATCH done` / `PATCH due_date`) — preserve that error surface.
- `scripts/escalation/reconcile_completions.py` — Vikunja state is authoritative; check whether it
  reads Vikunja directly or only records (migrate only real HTTP paths).
- `scripts/enrichment/{record_completion,reconcile_completions}.py` — mirror escalation's urllib
  helper (`_http_request`, GET-returns-parsed-JSON-or-`None`). Preserve the return/error contract via
  the WP01 adapter option.

**Reference**: `plan.md` (IC-02), `research.md` (R1d PATCH + return/error semantics).

## Subtasks & Detailed Guidance

### Subtask T010 — Migrate `escalation/record_completion.py`

- **Steps**:
  1. Replace the urllib `_http_request` helper with `VikunjaClient` calls; the `done`/due_date
     updates use `patch()` (`PATCH /tasks/{id}`).
  2. Preserve the sub-step-named error messages (`PATCH done` / `PATCH due_date`) and the
     "Vikunja already committed the side-effect" idempotency handling.
  3. Extend `tests/escalation/test_record_completion.py` with parity assertions (request + emitted
     record + exit code + error message).
- **Parallel?**: [P] with T011–T013 (distinct files).

### Subtask T011 — Migrate `escalation/reconcile_completions.py`

- **Steps**:
  1. Migrate any direct Vikunja HTTP onto the client (if it only records, note that and scope
     narrowly).
  2. Preserve reconcile behavior and emitted records.
  3. Extend `tests/escalation/test_reconcile_completions.py` with parity assertions.
- **Parallel?**: [P].

### Subtask T012 — Migrate `enrichment/record_completion.py`

- **Steps**:
  1. Replace the urllib helper with `VikunjaClient`; preserve the GET-returns-`None`-on-empty and
     error-body semantics via the WP01 adapter option.
  2. Extend `tests/enrichment/test_record_completion.py` with parity assertions.
- **Parallel?**: [P].

### Subtask T013 — Migrate `enrichment/reconcile_completions.py`

- **Steps**:
  1. Migrate the urllib GET helper (`reconcile_completions.py:293` returns parsed JSON or `None`)
     onto the client, preserving return/error behavior.
  2. Extend `tests/enrichment/test_reconcile_completions.py` with parity assertions.
- **Parallel?**: [P].

## Definition of Done

- All four modules migrated; `pytest tests/escalation/ tests/enrichment/` green.
- SC-001 grep clean for these four files.
- escalation PATCH via WP01 `patch()`; return/error semantics preserved per consumer.
- No identity/token change.

## Risks

- **Error-surface drift**: escalation's failure messages name the sub-step — a naive migration that
  swallows or renames them changes observable behavior. Preserve them.
- **Silent return change**: enrichment's GET-returns-`None` contract must survive (use the WP01
  adapter option), else callers mis-handle empty results.

## Reviewer Guidance

- Confirm PATCH via `patch()`; confirm each consumer's error messages / return values are unchanged;
  confirm parity tests assert emitted records + exit codes, not just request bodies.

## Activity Log

- 2026-07-23T22:18:52Z – claude:sonnet-5:python-pedro:implementer – shell_pid=45337 – Assigned agent via action command
- 2026-07-23T22:39:25Z – claude:sonnet-5:python-pedro:implementer – shell_pid=45337 – Ready for review — escalation/record_completion via patch() adapter (error substrings + JSONL ordering preserved); escalation/reconcile has NO direct HTTP (record_event skip_vikunja=True, invariant test added); enrichment/record_completion via create_comment (non-JSON-2xx tolerance preserved); enrichment/reconcile via list_task_comments (OSError re-raise routes exit-1, {}-vs-None fixed). 383 tests pass; flake8 exit 0. Note: implementer also cleaned pre-existing lint in owned files. Commit 37aa80b0 lane-c.
