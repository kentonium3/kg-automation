# Tasks: Canary dead-man's switch and backup coverage in felix-health-check

**Mission**: `canary-deadman-backup-coverage-01M4XVY3` · **Issue**: kentonium3/kg-automation#1063
**Branch**: `fix/canary-deadman-backup-coverage` (planning base = merge target)
**Inputs**: [spec.md](spec.md) · [plan.md](plan.md) · [research.md](research.md) (R1–R12 + review dispositions) · [data-model.md](data-model.md) · [contracts/health-check-run-record.md](contracts/health-check-run-record.md) · [quickstart.md](quickstart.md)

The WPs are a strict chain (WP01 → WP02 → WP03 → WP04 → WP05). Each one consumes the previous one's surface: the ledger is a declaration precondition for coverage; coverage feeds the wrapper; the wrapper's record is what the deploy verifies; the docs describe what was built.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Declare the `felix-canary` `key_ledger` in service-inventory.json | WP01 | |
| T002 | Tick-signal reconciliation harness executing `run_pass` | WP01 | |
| T003 | Evaluator tests: the tick ledger rejects the do-nothing and partial shapes | WP01 | [P] |
| T004 | Inventory prose: `felix-health-check` purpose/expected/note/dependencies; `felix-canary` note | WP01 | [P] |
| T005 | Validators and the full canary and restic suites green together | WP01 | |
| T006 | `coverage.py`: per-component findings via `health.evaluate` + outcome mapping | WP02 | |
| T007 | Declaration preconditions (R12) at runtime + CI test on the real inventory | WP02 | |
| T008 | Fail-closed paths: inventory, target, import, refused effects | WP02 | |
| T009 | Sentinel fixtures + agreement corpus (SC-001, SC-003) | WP02 | [P] |
| T010 | Post-boot evidence suffix; different-CWD test | WP02 | [P] |
| T011 | Move `health-check.sh` into the repo; resolve its path from `__file__` | WP03 | |
| T012 | Restructure `main`: coverage first, shell exceptions → UNKNOWN, combined precedence | WP03 | |
| T013 | Run record: `coverage_checks`, `script_status`, `script_path` | WP03 | |
| T014 | Alert details ordering, tested through the real bus renderer | WP03 | |
| T015 | Run-record contract tests (dynamic `TIMESTAMP_KEYS`, canary verdicts a–d) | WP03 | |
| T016 | Deploy entrypoint `--dry-run` / `--apply` with per-entry verification and retire-by-move | WP04 | |
| T017 | Deploy entrypoint tests (injected effects) | WP04 | |
| T018 | Manifest `deploys/queued/health-check-coverage.yaml` | WP04 | |
| T019 | Repoint `felix-health-check.sh` and `deploy-deterministic-monitoring-checks.py` | WP04 | [P] |
| T020 | `observability-and-alerting.md`: mutual watch + shared-fate limit | WP05 | [P] |
| T021 | `service-inventory.md` narrative entries | WP05 | [P] |
| T022 | `restic-backup-ops.md`: "what tells you backups stopped" | WP05 | [P] |
| T023 | Reference sweep for the retired path + doc validators | WP05 | |

---

## WP01 — The canary's tick declaration becomes affirmative (IC-05)

**Prompt**: [tasks/WP01-canary-tick-ledger.md
**Goal**: `felix-canary`'s inventory `health_check` gains a `key_ledger`, with its reconciliation harness. A canary that ticks with a missing or non-success status, an unusable `completed_at_utc`, or zero evaluated components is no longer read as alive. All inventory edits for the mission land here (single owner of `service-inventory.json`).
**Independent test**: the four reproduced shapes go from `healthy` to non-healthy through `health.evaluate`; the real 2026-10-14 tick stays `healthy`.

T001 Declare the `felix-canary` `key_ledger` in service-inventory.json (WP01)
T002 Tick-signal reconciliation harness executing `run_pass` (WP01)
T003 Evaluator tests: the tick ledger rejects the do-nothing and partial shapes (WP01)
T004 Inventory prose: `felix-health-check` purpose/expected/note/dependencies; `felix-canary` note (WP01)
T005 Validators and the full canary and restic suites green together (WP01)

**Risks**: this changes the canary's live self-probe (stricter). The restic harness's selection test discovers the new ledger, so the new harness must exist in the same commit.

## WP02 — Coverage evaluation through the canary's own path (IC-01)

**Prompt**: [tasks/WP02-coverage-evaluation.md
**Goal**: `scripts/office2/felix_health_check/coverage.py` returns exactly two findings (`felix-canary`, `restic-backup`), each decided by `scripts.canary.health.evaluate` on the inventory target. Every inability fails closed to `unknown`.
**Independent test**: the incident replay (17-day-dead tick, 127/null pointer) yields `stale` and `failed`; the real 2026-10-14 documents yield `healthy` twice.

T006 `coverage.py`: per-component findings via `health.evaluate` + outcome mapping (WP02)
T007 Declaration preconditions (R12) at runtime + CI test on the real inventory (WP02)
T008 Fail-closed paths: inventory, target, import, refused effects (WP02)
T009 Sentinel fixtures + agreement corpus (SC-001, SC-003) (WP02)
T010 Post-boot evidence suffix; different-CWD test (WP02)

## WP03 — Wrapper integration: verdict, alert, record, script location (IC-02)

**Prompt**: [tasks/WP03-wrapper-integration.md
**Goal**: `run.py` evaluates coverage first and runs the repo-tracked shell script with every exception contained. It combines the two by precedence, emits bus-safe alert details, and writes the extended run record per the contract.
**Independent test**: SC-001 end to end through `main()`: the incident fixtures produce `FAILURES_DETECTED`, and the rendered alert shows both findings despite more than 4 KB of shell output.

T011 Move `health-check.sh` into the repo; resolve its path from `__file__` (WP03)
T012 Restructure `main`: coverage first, shell exceptions → UNKNOWN, combined precedence (WP03)
T013 Run record: `coverage_checks`, `script_status`, `script_path` (WP03)
T014 Alert details ordering, tested through the real bus renderer (WP03)
T015 Run-record contract tests (dynamic `TIMESTAMP_KEYS`, canary verdicts a–d) (WP03)

## WP04 — Deploy, retire the host copy, live proof (IC-03)

**Prompt**: [tasks/WP04-deploy-and-retire.md
**Goal**: a queued manifest whose entrypoint proves the new coverage live, through per-entry checks on a fresh run record, and only then moves `~/helper-scripts/health-check.sh` to a dated retired file. The entrypoint is idempotent.
**Independent test**: the entrypoint tests with injected effects. The pre-merge `--dry-run` runs against live office2 state via `git archive` (quickstart).

T016 Deploy entrypoint `--dry-run` / `--apply` with per-entry verification and retire-by-move (WP04)
T017 Deploy entrypoint tests (injected effects) (WP04)
T018 Manifest `deploys/queued/health-check-coverage.yaml` (WP04)
T019 Repoint `felix-health-check.sh` and `deploy-deterministic-monitoring-checks.py` (WP04)

## WP05 — Architecture docs and runbooks (IC-04)

**Prompt**: [tasks/WP05-docs.md
**Goal**: the narrative docs describe the mutual watch, the shared-fate limit (#1069) and where a backup failure is reported. No active reference to the retired path remains.

T020 `observability-and-alerting.md`: mutual watch + shared-fate limit (WP05)
T021 `service-inventory.md` narrative entries (WP05)
T022 `restic-backup-ops.md`: "what tells you backups stopped" (WP05)
T023 Reference sweep for the retired path + doc validators (WP05)

---

## MVP

WP01 + WP02 + WP03 is the behavior fix (the dead-man's switch is live as soon as felix-deployer's checkout advances, because the unit runs from the checkout). WP04 retires the host copy and records the live proof; WP05 is documentation.

## Requirement coverage

| WP | Requirements |
|----|--------------|
| WP01 | FR-011, FR-003, FR-010 |
| WP02 | FR-001, FR-002, FR-003, FR-004, FR-012, NFR-002, NFR-004, C-001, C-002 |
| WP03 | FR-004, FR-005, FR-006, FR-007, NFR-003, C-003 |
| WP04 | FR-008, FR-009, C-004 |
| WP05 | FR-010, NFR-001, C-005 |
