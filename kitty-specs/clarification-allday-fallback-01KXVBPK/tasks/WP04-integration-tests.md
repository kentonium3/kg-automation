---
work_package_id: WP04
title: Integration/scenario tests for the fallback invariants
dependencies:
- WP03
requirement_refs:
- FR-004
- FR-005
- FR-008
- FR-009
tracker_refs: []
planning_base_branch: feat/clarification-allday-fallback
merge_target_branch: feat/clarification-allday-fallback
branch_strategy: Planning artifacts for this mission were generated on feat/clarification-allday-fallback. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/clarification-allday-fallback unless the human explicitly redirects the landing branch.
subtasks:
- T010
- T011
- T012
- T013
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "90266"
shell_pid_created_at: "1784415400.764365"
history:
- '2026-07-18: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: tests/inbox/test_clarification_sweep_finalize.py
create_intent:
- tests/inbox/test_clarification_sweep_finalize.py
execution_mode: code_change
owned_files:
- tests/inbox/test_clarification_sweep_finalize.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

Adopt its identity, governance scope, and boundaries before reading further.

## Objective

Prove the safety invariants of the sweep-finalize path (WP03) end-to-end against the
**real** `route_and_finalize` transaction with a **fake calendar** (no live Google
API). These tests are the acceptance evidence for SC-001..004, NFR-004, and the
Codex-surfaced risks (idempotency, reconciliation, boundary, fail-closed, week-drift).

## Context (read `quickstart.md`, `data-model.md` invariants, `spec.md` SC/FR)

- New test file `tests/inbox/test_clarification_sweep_finalize.py`.
- Fake the calendar create at the lowest deterministic seam (e.g. the
  `calendar_helper create` subprocess / service) using the existing test patterns in
  `tests/inbox/test_route_and_finalize.py` and `test_route_calendar_event.py` — reuse
  their fixtures/fakes; grep those files first ([[feedback_wp_prompts_grep_codebase]]).
- Use a fixed injected "now"/tick and a temp state file + temp inbox note; assert on
  the routing log, the note's processed state, the state file contents, and the
  number of calendar creates.
- Mind `tests/inbox/conftest.py` and the deep-`__init__` pytest package rules
  ([[reference_pytest_test_package_init]]).

## Subtasks

### T010 — Eligible age-out → all-day create (happy path)

Seed one aged-out (created >8h ago) **eligible** record
(`missing_fields` timing-only, `start_date` set, `title` set) + its inbox note. Run
the sweep-finalize. Assert: exactly **one** all-day event created with `start_date`
and `end_date = start_date + 1`; the note is marked processed; a distinct
`calendar_all_day_fallback` marker is in the routing log; the pending record is
removed.

### T011 — Idempotency across retry + reconciliation

1. **create+mark then remove-fail**: simulate the record-removal failing after the
   transaction marked the note processed; run the sweep again → assert **exactly one**
   event total (idempotency-key dedup), the note stays processed, and the stale record
   is now removed via reconciliation (no re-create). [FR-009, INV-6]
2. **mark-fail then retry**: simulate a failure before mark on the first pass → record
   retained, note unprocessed; second pass → exactly one event. [FR-008]

### T012 — Boundary + legacy (no leakage)

Seed aged-out records: (a) missing **title**; (b) a **non-timing** missing field
alongside start_time; (c) a **legacy** record with no `missing_fields`/`start_date`.
Assert **zero** all-day events created and each follows **delete-and-release** (record
removed, note left for re-scan; NOT marked processed). [FR-002, FR-005, SC-002]

### T013 — Fail-closed + week-drift

1. **Fail-closed**: eligible record but the calendar create errors → the pending
   record is **retained** and the note is **unprocessed**; no partial event. [FR-008]
2. **Week-drift**: an eligible record whose `start_natural` would re-parse to a
   *different* date at sweep time than the persisted `start_date` → assert the created
   event's date equals the **persisted `start_date`**, proving no NL re-parse. [INV-5]

Run: `python3 -m pytest tests/inbox/test_clarification_sweep_finalize.py -q`

## Branch Strategy

Planning/base + merge target: `feat/clarification-allday-fallback` (single_branch).
Execution worktree per computed lane in `lanes.json`.

## Definition of Done

- [ ] All four scenario groups implemented and green.
- [ ] Tests use a fake calendar (no live API) and injected now/tick (deterministic).
- [ ] Exactly-once, reconciliation, boundary/no-leakage, fail-closed, and week-drift are each explicitly asserted.
- [ ] `make test` green.

## Risks / reviewer guidance

- Reviewer confirms T011 actually exercises the **create+mark-then-remove-fail** interleaving (the Codex HIGH-3 case), not just a clean retry.
- Confirm the boundary tests assert **zero** creates (not just "no exception").
- Confirm the fake is at a seam that still exercises the **real** `_run_finalize` (so atomicity/log-before-mark is genuinely tested), not a mock of the whole path.

## Activity Log

- 2026-07-18T22:47:12Z – claude:sonnet:python-pedro:implementer – shell_pid=86676 – Assigned agent via action command
- 2026-07-18T22:57:01Z – claude:sonnet:python-pedro:implementer – shell_pid=86676 – Integration suite: 8 tests, all 4 groups incl. mark-fail→reconcile marker; fakes only calendar subprocess; 488 tests green
- 2026-07-18T22:57:10Z – claude:opus:reviewer-renata:reviewer – shell_pid=90266 – Started review via action command
