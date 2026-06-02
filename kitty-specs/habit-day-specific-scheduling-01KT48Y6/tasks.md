# Tasks — Day-Specific Habit Scheduling with Auto-Skip on Miss

**Mission**: `habit-day-specific-scheduling-01KT48Y6`
**Source issue**: [#408](https://github.com/kentonium3/kg-automation/issues/408)
**Spec**: [`spec.md`](./spec.md)
**Plan**: [`plan.md`](./plan.md)
**Branch contract**: planning base `main`, merge target `main`, matches: ✅

---

## Overview

Two sequential work packages (14 subtasks total) deliver the day-of-week scheduling fix plus the 48hr response window. WP-01 builds the foundation — schedule extension, day-of-week filter in the morning check-in, and the operator-facing reconciliation command. WP-02 adds the sweeper (auto-skip after 48hr), extends the reply parser for cross-day correlation, and deploys the systemd timer + architecture docs + runbook updates.

The WP boundaries follow ownership lines: no two WPs touch the same file. WP-02 depends on WP-01's `schedule_loader.py` (imported by the sweeper for day-specific habit detection). Per the lane-rebase pattern documented in mission #59 / issue #492, expect to manually reset lane-b's HEAD to lane-a's tip before WP-02 starts.

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Extend `phase3-schedule.yaml` with `designated_weekdays` field; seed Wed/Fri strength training entries | WP01 |  | [D] |
| T002 | New `schedule_loader.py` — central loader returning typed entries with day-of-week metadata | WP01 | [D] |
| T003 | Extend `query_active_habits_v2.py` with day-of-week filtering (consumes schedule_loader) | WP01 |  | [D] |
| T004 | Wire day-of-week filter into `morning_checkin_list.py` integration | WP01 |  | [D] |
| T005 | Add `--reconcile-schedule` flag to `set_due_dates.py` + reconciliation record writer | WP01 | [D] |
| T006 | Unit + fixture tests for schedule_loader, day-of-week filter, reconciliation flag | WP01 |  | [D] |
| T007 | Read existing `parse_morning_reply.py`; resolve OD-4; extend for 48hr window correlation | WP02 |  |
| T008 | New `sweeper.py` — entrypoint, dry-run, idempotency, Vikunja due_date advancement | WP02 |  |
| T009 | Extend `exclude_completed_v2.py` to tolerate `auto_skipped` event_type (if needed per T007 research) | WP02 | [P] |
| T010 | New systemd `felix-habit-sweeper.service` + `.timer` units (OnCalendar 07:30 America/New_York) | WP02 | [P] |
| T011 | Update architecture data: `service-inventory.json` + `.md` + `service-dependencies.view.md` | WP02 | [P] |
| T012 | Extend `docs/runbooks/habits-ops.md` with sweeper section + 48hr semantics + cutover procedure | WP02 | [P] |
| T013 | Sweeper unit + idempotency tests (mocked Vikunja, fixture-driven) | WP02 |  |
| T014 | Parser tests for 48hr cross-day correlation | WP02 |  |

`[P]` indicates a subtask that can execute in parallel with siblings inside its WP (touches different files / no in-WP ordering dependency).

---

## WP01 — Schedule extension + day-of-week filtering + reconciliation

**Goal**: deliver the foundation — schedule shape with `designated_weekdays`, the day-of-week filter applied by the morning check-in, and the operator-facing `--reconcile-schedule` flag.

**Priority**: Foundation (blocks WP02 via `schedule_loader.py` import).
**Independent test**: `pytest scripts/habits/tests/test_schedule_loader.py test_query_active_habits_v2_day_of_week.py test_morning_checkin_list_day_of_week.py test_set_due_dates_reconcile.py` passes with ≥85% line / ≥80% branch coverage on new modules.

**Included subtasks**:
- [x] T001 Extend `phase3-schedule.yaml` with `designated_weekdays` field; seed Wed/Fri strength training entries (WP01)
- [x] T002 New `schedule_loader.py` — central loader (WP01) [P]
- [x] T003 Extend `query_active_habits_v2.py` with day-of-week filtering (WP01)
- [x] T004 Wire day-of-week filter into `morning_checkin_list.py` (WP01)
- [x] T005 Add `--reconcile-schedule` flag to `set_due_dates.py` + reconciliation record writer (WP01) [P]
- [x] T006 Unit + fixture tests (WP01)

**Implementation sketch**:
1. T001 + T002 + T005 can execute in parallel (different files, no in-WP dependency).
2. T003 depends on T002 (consumes schedule_loader).
3. T004 depends on T003 (wires it through morning_checkin_list).
4. T006 covers all of the above with unit + fixture tests.

**Dependencies**: none.
**Risks**: existing `migrate_schedule.py` may have assumptions about the YAML shape; T001 must verify schema-additive change doesn't break it. Mitigation: T006 includes a test that runs the existing migration against the extended YAML.
**Estimated prompt size**: ~450 lines.

**Prompt**: [`tasks/WP01-schedule-extension-and-day-filter.md`](./tasks/WP01-schedule-extension-and-day-filter.md)

---

## WP02 — 48hr sweeper + parser correlation + deployment

**Goal**: build the sweeper (auto-skip after 48hr with day-specific due_date advancement), extend the reply parser for 48hr window correlation, deploy the systemd timer, and update architecture docs + runbook.

**Priority**: Core (depends on WP01's `schedule_loader.py`).
**Independent test**: `pytest scripts/habits/tests/test_sweeper_*.py test_parse_morning_reply_48hr_correlation.py` passes; sweeper integration test confirms idempotent auto-skip behavior against fixture set.

**Included subtasks**:
- [ ] T007 Read `parse_morning_reply.py`; resolve OD-4; extend for 48hr window correlation (WP02)
- [ ] T008 New `sweeper.py` — entrypoint, dry-run, idempotency, Vikunja due_date advancement (WP02)
- [ ] T009 Extend `exclude_completed_v2.py` to tolerate `auto_skipped` (if needed per T007 research) (WP02) [P]
- [ ] T010 New systemd `felix-habit-sweeper.service` + `.timer` units (WP02) [P]
- [ ] T011 Update architecture data (service-inventory.json + .md + service-dependencies.view.md) (WP02) [P]
- [ ] T012 Extend `docs/runbooks/habits-ops.md` (WP02) [P]
- [ ] T013 Sweeper unit + idempotency tests (WP02)
- [ ] T014 Parser 48hr correlation tests (WP02)

**Implementation sketch**:
1. T007 is research-heavy: implementer reads `parse_morning_reply.py` first, then decides whether 48hr support is a parser extension (most likely) or needs more involved changes. Determines whether T009 is needed.
2. T008 (sweeper) builds independently; uses schedule_loader from WP01.
3. T009, T010, T011, T012 can execute in parallel (different files).
4. T013 + T014 validate sweeper + parser behavior.

**Dependencies**: WP-01 (imports `schedule_loader.py`).
**Risks**:
- T007's parser-extension may require WhatsApp quote-reply metadata that the inbound channel doesn't forward. Fallback: most-recent-unresolved correlation (per `contracts/reply-correlation.contract.md`).
- T010's systemd unit ExecStart path — per the mission #59 cutover lesson, must use `/home/claude/kg-automation/...` (canonical path on office2), NOT `/home/claude/repos/kg-automation/...`. Same lesson: use a dedicated venv if `anthropic` isn't needed (it isn't for this mission — no LLM), but `PyYAML` MUST be importable. Plan-phase research may need to verify system python's PyYAML availability OR provision a venv.
- T011's `service-dependencies.view.md` is Mermaid — edits should preserve the existing diagram conventions.

**Estimated prompt size**: ~550 lines.

**Prompt**: [`tasks/WP02-sweeper-parser-deployment.md`](./tasks/WP02-sweeper-parser-deployment.md)

---

## Cross-WP risks

- **Lane-base propagation gap** (#492): expect to manually `git reset --hard kitty/mission-...-lane-a` on lane-b's worktree before WP-02 starts. Same as mission #59 workaround.
- **Existing `migrate_schedule.py` compatibility**: WP-01's T001 + T006 must verify the migration still works against the extended YAML. Migration is unchanged but is sensitive to schema additions.
- **Vikunja test mocking**: both WPs touch Vikunja PUT paths. The mocking pattern in existing `scripts/habits/tests/` should be reused (rather than each WP inventing its own).
- **No regression in existing morning check-in behavior**: NFR-003 explicitly forbids it. Both WPs must run the full existing test suite green.

## Parallelization opportunities

Within each WP:
- WP-01: T001 + T002 + T005 parallel.
- WP-02: T009 + T010 + T011 + T012 parallel.

Across WPs: strictly sequential (WP-02 imports from WP-01).

## MVP scope

**WP-01 alone** would land the visibility fix (day-specific habits no longer appear on wrong days) plus the operator reconciliation tool. That's a meaningful partial value — the original #408 ask. WP-02 adds the 48hr response window (which Kent re-asserted as a historical requirement) and the auto-skip sweeper. The full mission ships both per Kent's specify-phase decision.
