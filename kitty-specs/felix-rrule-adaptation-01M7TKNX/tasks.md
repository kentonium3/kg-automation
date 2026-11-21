# Work Packages: Felix RRULE recurrence adaptation

**Inputs**: `kitty-specs/felix-rrule-adaptation-01M7TKNX/` (spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md, post-plan-review.md)
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/vikunja-client-v2.md, contracts/repair-and-inventory-cli.md
**Tests**: required by the spec (FR-020, NFR-002, NFR-003). Every write path gets a red-then-green round-trip test.
**Tracking issue**: kentonium3/kg-automation#1111. Its audit's WP01–WP08 split is the starting point, refined here by seam and ownership.

**Organization**: Subtasks (`Txxx`) roll up into work packages (`WPxx`). Subtask rows are reference rows. Record completion with `spec-kitty agent tasks mark-status <Txxx> --status done`.

**Cross-WP rule:** a WP that depends on WP02 uses only the client methods named in `contracts/vikunja-client-v2.md`. If a method is missing or wrong, the fix goes back to WP02; do not patch around it locally.

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | `vikunja_rule.normalise` / `same_rule` / `has_rule` | WP01 | |
| T002 | `rrule_text_to_parts` / `parts_to_rrule_text` | WP01 | [P] |
| T003 | `completion_outcome` + `exhaustion_expected` | WP01 | |
| T004 | New-shape v2 task fixture factory | WP01 | [P] |
| T005 | WP01 tests | WP01 | |
| T006 | v2 root + `_request` support for PATCH merge-patch, 304, v2 paths | WP02 | |
| T007 | `patch_task` with null refusal and writable-field allowlist | WP02 | |
| T008 | `end_series` resumable contract + `SeriesEndIncomplete` | WP02 | |
| T009 | `get_task_v2`, `create_task_v2`, `occurrences`, `preview_occurrences` | WP02 | [P] |
| T010 | `update_task_fields` guard + direct `post` | WP02 | |
| T011 | WP02 tests | WP02 | |
| T012 | Habit `record_completion` → `patch_task` + completion outcome | WP03 | |
| T013 | Sweeper: rule-driven next date via occurrences, skip+alert | WP03 | |
| T014 | `set_due_dates`: retire `--reconcile-schedule`, bulk mode → `patch_task` | WP03 | |
| T015 | Habits test conversion (record_completion, sweeper, set_due_dates, conftest) | WP03 | |
| T016 | Habits round-trip regression tests (red-then-green evidence) | WP03 | |
| T017 | Escalation helper done/reschedule → `patch_task` + outcome | WP04 | |
| T018 | Reconcile: recurring completion vs reschedule; series ended | WP04 | |
| T019 | Escalation agent docs + skill: no direct Vikunja writes | WP04 | |
| T020 | Doc guard test: no agent doc instructs a direct task write | WP04 | |
| T021 | Escalation tests + red-then-green evidence | WP04 | |
| T022 | `apply_reply`: drop allowlist, `patch_task` with changed fields, rule check | WP05 | |
| T023 | `apply_reply`: eliminate via `end_series`; `_is_recurring` | WP05 | |
| T024 | `migrate_tasks` + `migrate_date_only_due_dates` → `patch_task` + rule check | WP05 | |
| T025 | Intake/bulk tests + red-then-green evidence | WP05 | |
| T026 | Sync: track `repeat` + `repeats_from_current_date` with normaliser | WP06 | |
| T027 | Sync: seed-on-missing-key + `seed-ledger.jsonl` + `baseline_seeded` | WP06 | |
| T028 | Sync: downstream-affecting classification | WP06 | |
| T029 | Sync tests incl. first-cycle and post-seed loss | WP06 | |
| T030 | Schedule: `rrule` field, ratchet on rule, YAML habits block | WP07 | |
| T031 | Schedule: read-only `--check-live` drift check | WP07 | |
| T032 | `sync/cleanup.py` compatibility with the new habits block | WP07 | |
| T033 | Weekly report: classify from rule, scheduled days from rule | WP07 | |
| T034 | `query_active_habits_v2` + `identify_workout_task` emit the rule | WP07 | |
| T035 | WP07 tests + fixture conversion | WP07 | |
| T036 | `create_task --rrule` via `create_task_v2` with readback | WP08 | |
| T037 | Retire `migrate_schedule` (+ tests, references in code/tests) | WP08 | |
| T038 | Remove `replace_task_fields`; client docstrings | WP08 | |
| T039 | NFR-001 ratchet test: no retired fields in active code/docs | WP08 | |
| T040 | Full-suite run + architecture validation (NFR-003) | WP08 | |
| T041 | `preview_rule` helper (O5) | WP09 | |
| T042 | task-intelligence SKILL rewrite | WP09 | [P] |
| T043 | vikunja-api SKILL rewrite | WP09 | [P] |
| T044 | tasker + habits AGENTS.md updates | WP09 | [P] |
| T045 | WP09 tests (preview helper; doc-guard extension) | WP09 | |
| T046 | `rule_inventory` (read-only, classification, attribution, seed cross-check) | WP10 | |
| T047 | `rule_repair --dry-run` / `--apply` with drift check + journal | WP10 | |
| T048 | `rule_repair --resume` / `--restore` / `--emit-issue-markdown` | WP10 | |
| T049 | WP10 tests (no-write assertions, journal, restore algorithm) | WP10 | |
| T050 | Runbook `docs/runbooks/vikunja-task-repair.md` | WP10 | |
| T051 | Architecture data: data-flows, service-inventory, credential-manifest, mutation-surfaces | WP11 | |
| T052 | Architecture narrative views (.md / .view.md) | WP11 | [P] |
| T053 | Runbooks: habits-ops, escalation-ops, office2-deploy-paths, agent-prompt-sync-ops, rollout window | WP11 | |
| T054 | Process flow + INDEX + DEVELOPER_PORTAL | WP11 | [P] |
| T055 | Architecture validator + docs CI checks locally | WP11 | |

---

## Work Package WP01: Rule library + new-shape fixtures (Priority: P0)

**Goal**: A pure, network-free library for comparing and classifying Vikunja rules, plus a shared fixture factory that mirrors the real v2 task body.
**Independent Test**: `pytest tests/common/test_vikunja_rule.py` passes. The factory output's key set equals the live v2 sample in research.md R-003.
**Prompt**: `tasks/WP01-rule-library-and-fixtures.md`
**Requirement Refs**: FR-014, FR-020

### Included Subtasks

T001 `vikunja_rule.normalise` / `same_rule` / `has_rule` (WP01)
T002 [P] `rrule_text_to_parts` / `parts_to_rrule_text` (WP01)
T003 `completion_outcome` + `exhaustion_expected` (WP01)
T004 [P] New-shape v2 task fixture factory (WP01)
T005 WP01 tests (WP01)

### Dependencies

None (starting package).

### Risks & Mitigations

- The library diverging from server casing. Mirror R-003: lowercase parts, uppercase rule text.

---

## Work Package WP02: Client seam — v2 partial update first (Priority: P0)

**Goal**: `VikunjaClient` gains the v2 write and read primitives in `contracts/vikunja-client-v2.md`. The v1 fallback is guarded.
**Independent Test**: `pytest tests/common/test_vikunja_client.py` passes, covering null refusal, 304, both end_series failure points, the guard and the 401 messages.
**Prompt**: `tasks/WP02-client-seam-v2.md`
**Requirement Refs**: FR-001, FR-002, C-001, C-006

### Included Subtasks

T006 v2 root + `_request` support for PATCH merge-patch, 304, v2 paths (WP02)
T007 `patch_task` with null refusal and writable-field allowlist (WP02)
T008 `end_series` resumable contract + `SeriesEndIncomplete` (WP02)
T009 [P] `get_task_v2`, `create_task_v2`, `occurrences`, `preview_occurrences` (WP02)
T010 `update_task_fields` guard + direct `post` (WP02)
T011 WP02 tests (WP02)

### Dependencies

Depends on WP01.

### Risks & Mitigations

- Loosening the `/api/v1` base URL contract: derive v2, do not change the regex.
- `replace_task_fields` stays until WP08 removes it, once its callers have moved.

---

## Work Package WP03: Habits writes keep the rule (Priority: P1)

**Goal**: Habit completion, sweeper auto-skip and the due-date setter use `patch_task`. The sweeper is rule-driven (O1).
**Independent Test**: The habits tests pass. A completion round-trip test and an auto-skip round-trip test each fail against `cc4f2154` and pass after the change.
**Prompt**: `tasks/WP03-habits-writes.md`
**Requirement Refs**: FR-003, FR-004, FR-005, FR-014, FR-020, NFR-002

### Included Subtasks

T012 Habit `record_completion` → `patch_task` + completion outcome (WP03)
T013 Sweeper: rule-driven next date via occurrences, skip+alert (WP03)
T014 `set_due_dates`: retire `--reconcile-schedule`, bulk mode → `patch_task` (WP03)
T015 Habits test conversion (WP03)
T016 Habits round-trip regression tests (WP03)

### Dependencies

Depends on WP01, WP02.

### Risks & Mitigations

- The sweeper must still never write daily habits.
- A 401 from occurrences must become a tick error, not a guessed date.

---

## Work Package WP04: Escalation — the agent never writes Vikunja (Priority: P1)

**Goal**: `N done` and reschedules go only through the helper, which writes v2. Reconcile labels recurring completions correctly.
**Independent Test**: The escalation tests pass. The doc-guard test fails on today's AGENTS.md and passes after the change.
**Prompt**: `tasks/WP04-escalation.md`
**Requirement Refs**: FR-006, FR-014, FR-015, FR-020, NFR-002

### Included Subtasks

T017 Escalation helper done/reschedule → `patch_task` + outcome (WP04)
T018 Reconcile: recurring completion vs reschedule; series ended (WP04)
T019 Escalation agent docs + skill: no direct Vikunja writes (WP04)
T020 Doc guard test (WP04)
T021 Escalation tests + red-then-green evidence (WP04)

### Dependencies

Depends on WP01, WP02, WP06. Reconcile reads `repeat` from the sync cache, which WP06 adds.

### Risks & Mitigations

- Helper and docs deploy by different paths. Handled by the quickstart rollout window, not in code.

---

## Work Package WP05: Intake and bulk tools (Priority: P2)

**Goal**: Intake replies and the bulk move/date tools send only the fields they change, and check the rule after every write. Eliminate ends a series properly.
**Independent Test**: The intake and vikunja tests pass, including a stripped-rule readback case that must fail the write.
**Prompt**: `tasks/WP05-intake-and-bulk-tools.md`
**Requirement Refs**: FR-007, FR-008, FR-009, FR-010, FR-020, NFR-002

### Included Subtasks

T022 `apply_reply`: drop allowlist, `patch_task` with changed fields, rule check (WP05)
T023 `apply_reply`: eliminate via `end_series`; `_is_recurring` (WP05)
T024 `migrate_tasks` + `migrate_date_only_due_dates` → `patch_task` + rule check (WP05)
T025 Intake/bulk tests + red-then-green evidence (WP05)

### Dependencies

Depends on WP01, WP02.

### Risks & Mitigations

- The two allowlists (R-007): remove both.
- A project move through PATCH `project_id` must be pinned by a test.

---

## Work Package WP06: Sync sees the rule (Priority: P2)

**Goal**: The sync tracks the rule and the from-current flag, seeds them once with a ledger, and flags later rule loss as unsafe.
**Independent Test**: The first cycle over a pre-upgrade cache gives 0 divergences and N seeds. A rule removed afterwards gives exactly 1 unsafe divergence.
**Prompt**: `tasks/WP06-sync-tracks-rule.md`
**Requirement Refs**: FR-016, NFR-004

### Included Subtasks

T026 Sync: track `repeat` + `repeats_from_current_date` with normaliser (WP06)
T027 Sync: seed-on-missing-key + `seed-ledger.jsonl` + `baseline_seeded` (WP06)
T028 Sync: downstream-affecting classification (WP06)
T029 Sync tests (WP06)

### Dependencies

Depends on WP01.

---

## Work Package WP07: Habits reads, schedule and weekly report (Priority: P2)

**Goal**: The schedule declares rules and checks them live (read-only). The weekly report and reporters read the rule.
**Independent Test**: The habits read-side tests pass. On the converted fixture, the weekly report lists all 7 daily habits.
**Prompt**: `tasks/WP07-habits-reads-schedule-report.md`
**Requirement Refs**: FR-012, FR-013, FR-017, C-005, C-008

### Included Subtasks

T030 Schedule: `rrule` field, ratchet on rule, YAML habits block (WP07)
T031 Schedule: read-only `--check-live` drift check (WP07)
T032 `sync/cleanup.py` compatibility (WP07)
T033 Weekly report: classify from rule, scheduled days from rule (WP07)
T034 `query_active_habits_v2` + `identify_workout_task` emit the rule (WP07)
T035 WP07 tests + fixture conversion (WP07)

### Dependencies

Depends on WP01, WP02.

---

## Work Package WP08: Create path, retirement, final client cleanup (Priority: P2)

**Goal**: Recurring creates work. `migrate_schedule` and `replace_task_fields` are gone. A ratchet test pins NFR-001. The full suite is green.
**Independent Test**: `make test` is green; `validate_architecture_data.py --strict` is OK; the NFR-001 ratchet test passes.
**Prompt**: `tasks/WP08-create-retire-cleanup.md`
**Requirement Refs**: FR-011, FR-018, NFR-001, NFR-002, NFR-003, C-003

### Included Subtasks

T036 `create_task --rrule` via `create_task_v2` with readback (WP08)
T037 Retire `migrate_schedule` (WP08)
T038 Remove `replace_task_fields`; client docstrings (WP08)
T039 NFR-001 ratchet test (WP08)
T040 Full-suite run + architecture validation (WP08)

### Dependencies

Depends on WP03, WP04, WP05, WP06, WP07. All `replace_task_fields` callers must already have moved.

---

## Work Package WP09: Agent guidance teaches the rule model (Priority: P3)

**Goal**: The skills and agent docs teach rules, partial updates and COUNT/UNTIL, and route writes through helpers. Proposals are checked with a preview helper.
**Independent Test**: The preview helper tests pass, and the WP04 doc-guard test (extended here) passes across all agent and skill docs.
**Prompt**: `tasks/WP09-agent-guidance.md`
**Requirement Refs**: FR-019

### Included Subtasks

T041 `preview_rule` helper (WP09)
T042 [P] task-intelligence SKILL rewrite (WP09)
T043 [P] vikunja-api SKILL rewrite (WP09)
T044 [P] tasker + habits AGENTS.md updates (WP09)
T045 WP09 tests (WP09)

### Dependencies

Depends on WP04, WP08, so the docs only name helpers that already exist.

---

## Work Package WP10: Live-data inventory and reversible repair (Priority: P1)

**Goal**: A read-only inventory, and a snapshot-first, journalled, resumable repair and restore helper, plus a runbook.
**Independent Test** (diff-inspectable): The WP10 tests pass. Dry-run and inventory make zero write calls (asserted). The journal records an intent before every write and an outcome for every attempt. The runbook exists. Live use is an operator step outside the WP.
**Prompt**: `tasks/WP10-inventory-and-repair.md`
**Requirement Refs**: FR-021, FR-022, NFR-005, C-004

### Included Subtasks

T046 `rule_inventory` (WP10)
T047 `rule_repair --dry-run` / `--apply` (WP10)
T048 `rule_repair --resume` / `--restore` / `--emit-issue-markdown` (WP10)
T049 WP10 tests (WP10)
T050 Runbook `docs/runbooks/vikunja-task-repair.md` (WP10)

### Dependencies

Depends on WP01, WP02. It runs live only after the deploy.

---

## Work Package WP11: Architecture docs, runbooks, rollout (Priority: P3)

**Goal**: The architecture data, docs and runbooks describe what shipped: v2 flows, token permissions, the retired component, the rollout window, and the sweeper re-enable.
**Independent Test**: `validate_architecture_data.py --strict` and `validate_docs.py` pass. Every signal-to-doc-map target for the applicable change classes has been reviewed.
**Prompt**: `tasks/WP11-architecture-docs-and-rollout.md`
**Requirement Refs**: FR-023, FR-024, C-002

### Included Subtasks

T051 Architecture data JSON (WP11)
T052 [P] Architecture narrative views (WP11)
T053 Runbooks (WP11)
T054 [P] Process flow + INDEX + DEVELOPER_PORTAL (WP11)
T055 Architecture validator + docs checks (WP11)

### Dependencies

Depends on WP08, WP09, WP10, WP12 (WP12 added 2026-11-20).

---

## Work Package WP12: Existing-task and habit-management helpers (Priority: P1)

*Added in-mission 2026-11-20 (Kent's ruling A on #1111). WP09 found that tasker enrichment of existing tasks and habit pause/resume/remove had no safe write path.*

**Goal**: `update_task` changes an existing task's fields through v2 PATCH and checks the result on readback. `manage_habit` pauses, resumes or removes a habit. Paused habits are really skipped by the morning list and the sweeper. The WP09-disabled doc paths are re-enabled.
**Independent Test**: The WP12 tests pass. Round trips keep the rule, the from-completion flag and reminders, and corruption controls exit non-zero. Refusals make zero writes. Remove never sends DELETE. A paused habit is absent from the morning list and untouched by a sweeper tick.
**Prompt**: `tasks/WP12-existing-task-and-habit-helpers.md`
**Requirement Refs**: FR-025, FR-026

### Included Subtasks

T056 `update_task` helper + tests (WP12)
T057 `manage_habit` pause/resume/remove + tests (WP12)
T058 Paused habits skipped by the morning list and the sweeper + tests (WP12)
T059 Re-enable the tasker and habits doc paths and the vikunja-api helper list (WP12)
T060 Full validation (WP12)

### Dependencies

Depends on WP09, which owns the agent docs this WP re-enables.

---

## Sequencing

```
WP01 ─► WP02 ─┬─► WP03 ───────────┐
   │          ├─► WP05 ───────────┤
   │          ├─► WP07 ───────────┼─► WP08 ─► WP09 ─► WP12 ─┐
   └─► WP06 ──┴─► WP04 (needs WP06)┘                        ├─► WP11
              WP02 ─► WP10 ─────────────────────────────────┘
```

**MVP**: WP01 + WP02 + WP03 + WP04 fix every destructive write on a live path.

**After the mission (operator, per quickstart.md, Kent's gates):** re-issue the token → merge `fix/felix-rrule-adaptation` → `main` → rollout window → canary → inventory and repair → sweeper re-enable.
