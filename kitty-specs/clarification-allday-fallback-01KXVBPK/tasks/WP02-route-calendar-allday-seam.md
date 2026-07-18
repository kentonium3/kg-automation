---
work_package_id: WP02
title: All-day support in the calendar delegation seam
dependencies: []
requirement_refs:
- FR-006
tracker_refs: []
planning_base_branch: feat/clarification-allday-fallback
merge_target_branch: feat/clarification-allday-fallback
branch_strategy: Planning artifacts for this mission were generated on feat/clarification-allday-fallback. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/clarification-allday-fallback unless the human explicitly redirects the landing branch.
subtasks:
- T003
- T004
agent: "claude:sonnet:python-pedro:implementer"
shell_pid: "51527"
shell_pid_created_at: "1784410041.160614"
history:
- '2026-07-18: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/inbox/route_calendar_event.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/inbox/route_calendar_event.py
- tests/inbox/test_route_calendar_event.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

Adopt its identity, governance scope, and boundaries before reading further.

## Objective

Teach the calendar delegation layer `scripts/inbox/route_calendar_event.py` to
accept and pass through an **all-day** payload (`start_date`/`end_date`) so the
#746 transaction (`_run_finalize` → `_adapt_calendar` → `route_calendar_event` →
`calendar_helper create --payload-file`) can route an all-day create end-to-end.
**Without regressing the existing timed path.**

## Context (read `research.md` R1, `data-model.md` C2)

- The transaction already routes `kind:"calendar"` blocks, but the delegation layer
  is **timed-only**: `REQUIRED_FIELDS = ("title", "start")` (~L66), `validate_payload`
  (~L151) requires `start`, and `build_delegation_payload` (~L205) hard-maps
  `start → start_rfc3339` / `end → end_rfc3339` (~L221-235) with no `start_date`
  branch.
- `calendar_helper` **already supports all-day** via `--payload-file` JSON keyed on
  `start_date` (`_create_fields_from_payload` ~L266 sets `all_day = payload.get("start_date") is not None`). All-day uses `start.date`/`end.date` with an **exclusive** end (`end_date = start_date + 1 day` for a single day).
- So this WP is purely the delegation layer learning the all-day shape and emitting a payload-file that carries `start_date`/`end_date` unchanged.

## Subtasks

### T003 — Accept + delegate all-day payloads

**File**: `scripts/inbox/route_calendar_event.py`

1. **Validation**: accept an all-day payload — one with `start_date` (and
   `end_date`) instead of `start`/`end`. Update `REQUIRED_FIELDS` handling /
   `validate_payload` so a valid payload is `title` + **either** (`start`) **or**
   (`start_date`). Reject a payload with neither, and (recommended) reject a payload
   that mixes timed + all-day keys ambiguously.
2. **Delegation**: in `build_delegation_payload`, when the payload is all-day, emit
   `start_date`/`end_date` into the delegated payload-file (pass-through) instead of
   `start_rfc3339`/`end_rfc3339`. Do not fabricate a time. Preserve the exclusive-end
   convention as received (WP03 computes `end_date = start_date + 1`).
3. Keep the **timed path byte-for-byte unchanged** — a payload with `start` still
   maps to `start_rfc3339` exactly as today.
4. Grep the file for its existing import + helper conventions before editing; match
   them ([[feedback_wp_prompts_grep_codebase]]).

**Validation**: an all-day payload `{"title","start_date","end_date"}` validates and
`build_delegation_payload` produces a payload-file with `start_date`/`end_date`; a
timed payload is unchanged.

### T004 [P] — Tests

**File**: `tests/inbox/test_route_calendar_event.py` (extend existing)

1. **All-day acceptance**: an all-day payload validates and delegates with
   `start_date`/`end_date` (exclusive end preserved).
2. **Timed regression**: existing timed payloads still validate and map to
   `start_rfc3339`/`end_rfc3339` unchanged (copy/keep the existing timed assertions).
3. **Rejection**: a payload with neither `start` nor `start_date` is rejected with
   the usual error/exit contract.
4. (If practical) an integration-style assertion that an all-day payload fed through
   `--finalize --dry-run` yields the all-day delegated shape.

Run: `python3 -m pytest tests/inbox/test_route_calendar_event.py -q`

## Branch Strategy

Planning/base + merge target: `feat/clarification-allday-fallback` (single_branch).
Execution worktree per computed lane in `lanes.json`.

## Definition of Done

- [ ] All-day payloads validate + delegate (`start_date`/`end_date`, exclusive end).
- [ ] Timed path unchanged (regression tests green).
- [ ] Neither-start rejection preserved.
- [ ] `python3 -m pytest tests/inbox/test_route_calendar_event.py -q` green; `make test` unaffected.

## Risks / reviewer guidance

- **Timed regression** is the top risk — reviewer confirms the timed mapping is untouched and its tests still pass verbatim.
- Confirm no time is fabricated for the all-day form (no `T00:00:00` sneaking in).
- Confirm the delegated payload-file keys are exactly what `calendar_helper._create_fields_from_payload` expects (`start_date`/`end_date`).

## Activity Log

- 2026-07-18T21:27:33Z – claude:sonnet:python-pedro:implementer – shell_pid=51527 – Assigned agent via action command
