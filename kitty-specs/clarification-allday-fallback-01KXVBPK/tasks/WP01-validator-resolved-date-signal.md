---
work_package_id: WP01
title: Validator surfaces resolved date + missing_fields
dependencies: []
requirement_refs:
- FR-001
- FR-006
tracker_refs: []
planning_base_branch: feat/clarification-allday-fallback
merge_target_branch: feat/clarification-allday-fallback
branch_strategy: Planning artifacts for this mission were generated on feat/clarification-allday-fallback. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/clarification-allday-fallback unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
agent: claude
history:
- '2026-07-18: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/calendar_routing/validate_calendar_event.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/calendar_routing/validate_calendar_event.py
- tests/calendar/test_validate_calendar_event.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your agent profile:

```
/ad-hoc-profile-load python-pedro
```

Adopt its identity, governance scope, and boundaries for this work package.

## Objective

Make `scripts/calendar_routing/validate_calendar_event.py::validate` surface the
**resolved `start_date`** and the `missing_fields` list on **every** result where
`start_time` is missing (not only an exact `missing == ["start_time"]` case), so the
downstream sweep-finalize path (WP03) has a stable, tick-anchored date and the
eligibility signal. This is the add-time foundation for the all-day fallback.

## Context (read `spec.md` FR-001/FR-005/FR-006, `research.md` R2)

- `validate` (validate_calendar_event.py:~525) already computes the resolved
  `start_dt` (~L535) and already emits `start_date` on the **complete** all-day
  branch (~L607-631), but **discards** the resolved date when the event is
  incomplete — returning only `{"complete": False, "missing_fields": [...],
  "fields_so_far": {...}}` (~L582-587). `fields_so_far` carries `start_natural`
  ("Thursday") but **no resolved date**.
- Re-parsing `start_natural` later (in the sweep, hours after capture) resolves to
  the **wrong week** — a silent-wrong-date bug. The date MUST be resolved once, at
  capture time, and persisted. This WP makes `validate` surface it.
- The canonical "Meet Rob Thursday" with no stated duration yields
  `missing_fields = ["start_time", "end_or_duration"]` (verify against the real
  output — see T001). Both are timing fields; the record is still all-day-eligible.

## Subtasks

### T001 — Emit resolved `start_date` + `missing_fields` on start-time-missing results

**File**: `scripts/calendar_routing/validate_calendar_event.py`

1. In the incomplete-result path, whenever `start_dt` was resolved but `start_time`
   is among the missing fields, include the resolved date in the returned payload
   (e.g. add `start_date: start_dt.date().isoformat()` into `fields_so_far` or the
   result dict — match the shape the complete all-day branch already uses at
   ~L607-631 for consistency). Also ensure `missing_fields` is present in the
   returned incomplete result (it already is).
2. Do **not** change behavior for: complete events (timed or all-day), or cases
   where `start_dt` did **not** resolve (unparseable/absent date) — those must NOT
   gain a `start_date`. A record with no resolved date must remain ineligible
   downstream (fail-closed).
3. Keep the function **pure** (no clock reads; it resolves against the caller's
   `tick_iso`). Do not import `scripts.common.*` in a way that changes the pure
   contract; match existing import conventions in the file (grep the file's head
   before adding imports — see [[feedback_wp_prompts_grep_codebase]]).

**Validation**: for a block "Meet Rob Thursday" (date resolvable, no time, no
duration) at a fixed `tick_iso`, `validate` returns `complete=False`,
`missing_fields` containing `start_time`, and a `start_date` equal to the
tick-anchored Thursday.

### T002 [P] — Unit tests

**File**: `tests/calendar/test_validate_calendar_event.py` (extend existing)

Add tests asserting:
1. **start_date emitted**: incomplete start-time-missing result carries a
   `start_date` matching the tick-anchored resolved date.
2. **Week-drift anchoring**: the same natural phrase at two different `tick_iso`
   values (spanning a week boundary) yields two different `start_date`s — proving
   the date is resolved against the tick, not "now".
3. **missing_fields shape**: capture the real `missing_fields` for the no-time /
   no-duration case (document whether it is `["start_time"]` or
   `["start_time","end_or_duration"]`) — WP03's eligibility gate keys off this, so
   this test is the source of truth for that vocabulary.
4. **Unresolved date → no start_date**: an unparseable date does NOT gain a
   `start_date` (stays ineligible).
5. **Complete events unaffected**: a complete timed event and a complete all-day
   event return exactly as before (regression).

Run: `python3 -m pytest tests/calendar/test_validate_calendar_event.py -q`

## Branch Strategy

Planning/base + merge target: `feat/clarification-allday-fallback` (single_branch).
Execution worktree is allocated per the computed lane in `lanes.json`. No PR;
the mission merges to the feature branch, which merges to `main` after the mission.

## Definition of Done

- [ ] `validate` surfaces `start_date` on every start-time-missing **resolvable-date** result; no `start_date` when the date is unresolved.
- [ ] Complete timed/all-day paths unchanged (regression tests green).
- [ ] The real `missing_fields` vocabulary for the no-time/no-duration case is captured in a test and noted for WP03.
- [ ] `python3 -m pytest tests/calendar/test_validate_calendar_event.py -q` green; full `make test` unaffected.

## Risks / reviewer guidance

- **Purity**: reviewer confirms no clock reads were introduced; resolution stays against `tick_iso`.
- **Over-emission**: confirm an *unresolved* date does not produce a `start_date` (would let an un-dateable record become all-day downstream — fail-closed violation).
- **Shape consistency**: the emitted `start_date` key/location must match what WP03's gate and the all-day complete branch expect.
