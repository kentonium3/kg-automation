# Tasks: Deterministic escalation + weekly-report crons

**Mission**: deterministic-cron-hardening-01KXA4PX
**Branch**: `fix/deterministic-cron-hardening` (planning base + merge target); mission merges here, then feat→main.
**Governing amendments**: `contracts/post-plan-review-resolutions.md` (authoritative where it conflicts with earlier artifacts).

Tests are in scope (NFR-003). Deploy executes post-merge via felix-deployer (WP04 creates the artifacts).

## Dependency graph

```
WP01 (scope config, foundation)
 ├─► WP02 (escalation enumerate helper + prompt)   ┐
 └─► WP03 (weekly driver + systemd units)          ┼─► WP04 (observability + deploy)
                                                    ┘
WP02 ∥ WP03 (parallel; both depend only on WP01)
```

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Create `scripts/common/vikunja_scope.py` (selectors + accessors) | WP01 | |
| T002 | Refactor `query_active_habits_weekly.py` to read habit project id from scope | WP01 | |
| T003 | Tests for `vikunja_scope` (accessors + label-form round-trip) | WP01 | [P] |
| T004 | Regression: weekly helper works with config-sourced id (+ >50 pagination fixture) | WP01 | |
| T005 | Create `scripts/escalation/enumerate_candidates.py` (/tasks/all → §1 filter → JSON) | WP02 | |
| T006 | Tests for `enumerate_candidates` (qualification, due-date boundary/DST, pagination, error) | WP02 | [P] |
| T007 | Rewrite `felix-admin-escalation/AGENTS.md` Step 2 (call helper; derive_state gate; failure propagation) | WP02 | |
| T008 | Update escalation `SKILL.md` §1 (helper as mechanism; pre-candidates + derive_state gate) | WP02 | |
| T009 | Create `scripts/habits/weekly_report_driver.py` (helper → compose → send → confirm → tick; --self-test/--dry-run) | WP03 | |
| T010 | Create systemd units `felix-habits-weekly.{service,timer,onfailure}` (contracted fields) | WP03 | [P] |
| T011 | Tests for `weekly_report_driver` (happy, helper-fail, send-unconfirmed, --self-test, --dry-run) | WP03 | [P] |
| T012 | Update `service-inventory.json` (add weekly-driver service; strip retired cron from habit-checkin) | WP04 | |
| T013 | Create deploy entrypoint `deploy-habits-weekly-driver.py` (install, --self-test gate, transactional cutover, postcheck, #701) | WP04 | |
| T014 | Create `deploys/queued/00NN-habits-weekly-driver.yaml` (expected_baselines for retired cron) | WP04 | [P] |

---

## WP01 — Shared Vikunja scope config (foundation)

**Goal**: Externalize the Vikunja selectors (escalation excluded projects; habit identity) into one importable module so #714 is a config swap; wire the weekly helper to it.
**Priority**: P1 (foundation — WP02 + WP03 depend on it).
**Independent test**: `pytest tests/common/test_vikunja_scope.py` green; `query_active_habits_weekly --output text` still produces the full report on office2 with the id now config-sourced.
**Requirements**: FR-008, NFR-004, C-006.
**Dependencies**: none.
**Prompt**: `tasks/WP01-vikunja-scope-config.md` (~250 lines)

- [x] T001 Create `scripts/common/vikunja_scope.py` — selectors + accessors (WP01)
- [x] T002 Refactor `query_active_habits_weekly.py` to read habit project id from the scope module (WP01)
- [x] T003 Tests `tests/common/test_vikunja_scope.py` — accessors + label-form round-trip (WP01)
- [x] T004 Regression fixture: weekly helper with config-sourced id + a >50-task pagination fixture (WP01)

## WP02 — Escalation enumeration helper + prompt rewrite

**Goal**: Replace the agent's improvised fetch + inline python3 with a deterministic pre-candidate enumeration helper; rewrite the standing orders to call it and gate on `derive_state`.
**Priority**: P1.
**Independent test**: `pytest tests/escalation/test_enumerate_candidates.py` green; live `python3 -m scripts.escalation.enumerate_candidates` on office2 returns a sane JSON array cross-checked against the Vikunja UI.
**Requirements**: FR-001, FR-002, FR-003, C-001, C-002.
**Dependencies**: WP01.
**Prompt**: `tasks/WP02-escalation-enumerate-helper.md` (~350 lines)

- [x] T005 Create `scripts/escalation/enumerate_candidates.py` (WP02)
- [x] T006 Tests `tests/escalation/test_enumerate_candidates.py` (WP02)
- [x] T007 Rewrite `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` Step 2 (WP02)
- [x] T008 Update `scripts/openclaw/skills/escalation/SKILL.md` §1 (WP02)

## WP03 — Weekly-report deterministic driver + systemd units

**Goal**: Produce + deliver the weekly report with no LLM turn: a driver that runs the helper, delivers via `openclaw message send`, confirms delivery, and writes a freshness tick; plus contracted systemd units.
**Priority**: P1.
**Independent test**: `pytest tests/habits/test_weekly_report_driver.py` green; `python3 -m scripts.habits.weekly_report_driver --self-test` on office2 writes a fresh tick and issues a dry-run send (no real message).
**Requirements**: FR-004, FR-005, FR-006, FR-007.
**Dependencies**: WP01.
**Prompt**: `tasks/WP03-weekly-report-driver.md` (~350 lines)

- [x] T009 Create `scripts/habits/weekly_report_driver.py` (WP03)
- [x] T010 Create systemd units `scripts/office2/felix-habits-weekly.{service,timer,onfailure}` (WP03)
- [x] T011 Tests `tests/habits/test_weekly_report_driver.py` (WP03)

## WP04 — Observability + deploy

**Goal**: Keep both jobs canary-observable and deploy safely: add the weekly-driver freshness service, strip the retired cron from habit-checkin, and create the deploy entrypoint (transactional cutover, exactly-one-producer postcheck) + manifest with `expected_baselines`.
**Priority**: P2 (integration/deploy — last).
**Independent test**: `pytest` green; the deploy entrypoint `--self-test` path (dry-run) passes offline; architecture-data validator green on the service-inventory change.
**Requirements**: FR-009, FR-010, C-003, C-004.
**Dependencies**: WP02, WP03.
**Prompt**: `tasks/WP04-observability-and-deploy.md` (~350 lines)

- [ ] T012 Update `docs/design/architecture/data/service-inventory.json` (WP04)
- [ ] T013 Create `scripts/deploy/deploy-habits-weekly-driver.py` (WP04)
- [ ] T014 Create `deploys/queued/00NN-habits-weekly-driver.yaml` (WP04)

## MVP / sequencing

WP01 is the foundation and unblocks WP02 ∥ WP03 (parallelizable). WP04 integrates + deploys last. The actual office2 deploy runs post-merge (felix-deployer applies the WP04 manifest); the operator handles the careful cutover verification.
