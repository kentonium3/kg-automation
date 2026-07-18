# Tasks: All-Day Fallback for Unanswered Clarifications

**Mission**: clarification-allday-fallback-01KXVBPK · **Branch**: `feat/clarification-allday-fallback` · single_branch
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Post-plan Codex review folded** ([reviews/codex-postplan.md](./reviews/codex-postplan.md))

6 work packages, 19 subtasks. WP01/WP02 are parallel foundations; WP03 is the core (depends on both); WP04 (integration tests), WP05 (agent prompts/deploy), and WP06 (process-flow doc) depend on WP03. WP06 documents the calendar-clarification process flow as a discoverable design doc (the exemplar for #794's systemic back-fill).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | `validate` surfaces resolved `start_date` on every start-time-missing result | WP01 | |
| T002 | Unit tests: start_date emitted, tick-anchored (week-drift), missing_fields shape, complete-event unaffected | WP01 | [P] |
| T003 | `route_calendar_event` accepts + delegates all-day (`start_date`/`end_date`) payloads | WP02 | |
| T004 | Tests: all-day acceptance (exclusive end) + timed-path regression | WP02 | [P] |
| T005 | New `clarification_sweep_finalize` module: partition aged-out into eligible/ineligible (timing-only-gap gate) | WP03 | |
| T006 | Build single-block all-day RoutingPlan (canonical abs inbox path) + call `_run_finalize` | WP03 | |
| T007 | Reconciliation + fail-closed (FR-008/FR-009): reconcile-after-mark, retain-before-mark, remove-on-success | WP03 | |
| T008 | Ineligible aged-out → delete-and-release; `SWEEP_MAX_AGE` 24h→8h (C-006); non-aged-out untouched | WP03 | |
| T009 | Observability marker (`calendar_all_day_fallback`) extending the `calendar_event_clarification_timeout` vocab (C-007) | WP03 | |
| T010 | Integration: eligible age-out → one all-day event, note processed, distinct marker, record removed | WP04 | |
| T011 | Integration: idempotency across retry + reconciliation (create+mark then remove-fail → no double-create) | WP04 | |
| T012 | Integration: boundary + legacy (missing-title / non-timing / no-signal → zero all-day, delete-and-release) | WP04 | |
| T013 | Integration: fail-closed (create error → retain, unprocessed) + week-drift (event date == persisted start_date) | WP04 | |
| T014 | felix-admin-capture AGENTS.md Step 3c: partial_payload carries `missing_fields` + `start_date` | WP05 | |
| T015 | felix-admin-capture AGENTS.md Step 1a: invoke sweep-finalize in place of bare `sweep` | WP05 | |
| T016 | TOOLS.md + runbook doc: the new sweep-finalize command + all-day fallback behavior | WP05 | |
| T017 | Author the calendar-clarification **process-flow doc** (actors, trigger, 8h window, timed/all-day/delete branches, operating rules + invariants, code seams) | WP06 | |
| T018 | Register the flow doc for **machine + human discovery** (signal-to-doc-map.json + docs/INDEX.md) | WP06 | |
| T019 | Cross-link the flow doc to #780/#794 and the implementing seams; establish the reusable shape for #794's back-fill | WP06 | |

---

## WP01 — Validator surfaces resolved date + missing_fields

**Goal**: Give the deterministic sweep the two facts it needs from add-time — the `missing_fields` eligibility signal and a **stable resolved `start_date`** — by having `validate_calendar_event.validate` emit them on **every** start-time-missing result (not only the exact-`["start_time"]` branch). **Priority**: P1 (foundation). **Depends on**: none. **Independent test**: feed a no-time block at a fixed tick → incomplete result carries `missing_fields` + a tick-anchored `start_date`.

- [x] T001 `validate` surfaces resolved `start_date` on every start-time-missing result (WP01)
- [x] T002 Unit tests: start_date emitted, tick-anchored (week-drift), missing_fields shape, complete-event unaffected (WP01)

**Prompt**: [tasks/WP01-validator-resolved-date-signal.md](./tasks/WP01-validator-resolved-date-signal.md) · ~200 lines

## WP02 — All-day support in the calendar delegation seam

**Goal**: Teach `route_calendar_event` (`REQUIRED_FIELDS` / `validate_payload` / `build_delegation_payload`) the all-day (`start_date`/`end_date`) shape so the #746 transaction can route an all-day create end-to-end, **without regressing the timed path**. **Priority**: P1 (foundation). **Depends on**: none. **Independent test**: an all-day payload validates + builds a `--payload-file` with `start_date`/`end_date`; timed payloads unchanged.

- [x] T003 `route_calendar_event` accepts + delegates all-day (`start_date`/`end_date`) payloads (WP02)
- [x] T004 Tests: all-day acceptance (exclusive end) + timed-path regression (WP02)

**Prompt**: [tasks/WP02-route-calendar-allday-seam.md](./tasks/WP02-route-calendar-allday-seam.md) · ~200 lines

## WP03 — Deterministic sweep-finalize path + observability

**Goal**: The core. A new deterministic module that, for each aged-out **eligible** record, builds an all-day plan and routes it through `_run_finalize` (create→log→mark) with reconciliation + fail-closed semantics; ineligible aged-out records keep delete-and-release; the timeout window drops to 8h. **Priority**: P1 (core). **Depends on**: WP01, WP02. **Independent test**: the full eligible/ineligible/reconcile/fail-closed matrix against fakes (exercised deeply in WP04).

- [x] T005 New `clarification_sweep_finalize` module: partition aged-out into eligible/ineligible (timing-only-gap gate) (WP03)
- [x] T006 Build single-block all-day RoutingPlan (canonical abs inbox path) + call `_run_finalize` (WP03)
- [x] T007 Reconciliation + fail-closed (FR-008/FR-009): reconcile-after-mark, retain-before-mark, remove-on-success (WP03)
- [x] T008 Ineligible aged-out → delete-and-release; `SWEEP_MAX_AGE` 24h→8h (C-006); non-aged-out untouched (WP03)
- [x] T009 Observability marker (`calendar_all_day_fallback`) extending the `calendar_event_clarification_timeout` vocab (C-007) (WP03)

**Prompt**: [tasks/WP03-sweep-finalize-path.md](./tasks/WP03-sweep-finalize-path.md) · ~420 lines

## WP04 — Integration/scenario tests for the fallback invariants

**Goal**: Prove the safety invariants end-to-end against the real transaction + fake calendar: exactly-once, reconciliation, boundary, fail-closed, week-drift. **Priority**: P1. **Depends on**: WP03. **Independent test**: the WP04 suite is the test.

- [x] T010 Integration: eligible age-out → one all-day event, note processed, distinct marker, record removed (WP04)
- [x] T011 Integration: idempotency across retry + reconciliation (create+mark then remove-fail → no double-create) (WP04)
- [x] T012 Integration: boundary + legacy (missing-title / non-timing / no-signal → zero all-day, delete-and-release) (WP04)
- [x] T013 Integration: fail-closed (create error → retain, unprocessed) + week-drift (event date == persisted start_date) (WP04)

**Prompt**: [tasks/WP04-integration-tests.md](./tasks/WP04-integration-tests.md) · ~260 lines

## WP05 — Agent prompt edits + docs (deploy surface)

**Goal**: Make new records carry the signal (capture Step 3c) and invoke the sweep-finalize path (capture Step 1a); document the new command. Deploys via `agent-prompt-sync`. **Priority**: P2 (deploy-time). **Depends on**: WP03. **Independent test**: prompt review + doc render; the AGENTS.md examples name the exact new command.

- [x] T014 felix-admin-capture AGENTS.md Step 3c: partial_payload carries `missing_fields` + `start_date` (WP05)
- [x] T015 felix-admin-capture AGENTS.md Step 1a: invoke sweep-finalize in place of bare `sweep` (WP05)
- [x] T016 TOOLS.md + runbook doc: the new sweep-finalize command + all-day fallback behavior (WP05)

**Prompt**: [tasks/WP05-agent-prompts-and-docs.md](./tasks/WP05-agent-prompts-and-docs.md) · ~200 lines

## WP06 — Calendar-clarification process-flow doc (discoverable design doc)

**Goal**: Document the calendar-clarification **user process flow** and its operating rules as a canonical, discoverable design doc so future missions find it instead of spelunking prior mission specs — the exemplar convention for #794's systemic back-fill. **Priority**: P2 (docs). **Depends on**: WP03, WP05 (documents the implemented + wired behavior). **Independent test**: a fresh agent, given only `signal-to-doc-map.json` + `INDEX`, can locate the flow doc and read the current-state rules (8h window, timed/all-day/delete branches, eligibility, invariants) without opening any `kitty-specs/` mission.

- [ ] T017 Author the calendar-clarification **process-flow doc** (actors, trigger, 8h window, timed/all-day/delete branches, operating rules + invariants, code seams) (WP06)
- [ ] T018 Register the flow doc for **machine + human discovery** (signal-to-doc-map.json + docs/INDEX.md) (WP06)
- [ ] T019 Cross-link the flow doc to #780/#794 and the implementing seams; establish the reusable shape for #794's back-fill (WP06)

**Prompt**: [tasks/WP06-calendar-clarification-flow-doc.md](./tasks/WP06-calendar-clarification-flow-doc.md) · ~220 lines

---

## Dependencies

```
WP01 ┐
WP02 ┴─► WP03 ─┬─► WP04
              ├─► WP05 ─► WP06
              └─────────► (WP06 also depends on WP03)
```

## MVP scope

WP01 + WP02 + WP03 deliver the functional fallback (deterministic path). WP04 proves it; WP05 wires + deploys it; WP06 documents the flow discoverably (exemplar for #794). All six are required for a shippable, deployed, *and discoverable* feature.
