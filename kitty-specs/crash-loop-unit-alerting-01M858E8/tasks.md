# Tasks: Crash-loop unit alerting

**Mission**: `crash-loop-unit-alerting-01M858E8` · **Issue**: kentonium3/kg-automation#1133 · **Planning branch**: `kitty/mission-crash-loop-unit-alerting-01M858E8` · **Merge target**: `fix/crash-loop-unit-alerting`

**Inputs:** [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/) and [quickstart.md](quickstart.md). Read the "Post-plan Codex review dispositions" table in plan.md first. The revised research decisions (R-02, R-05 to R-11, R-13 to R-15) override any earlier reading.

**Suite floor:** `.venv/bin/python -m pytest -q -p no:cacheprovider` gave 10907 passed, 51 skipped and 1 xfailed before the mission. Never finish a WP below that floor, except for the new tests the WP adds.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Value types: `RestartObservation`, `ScopeReading`, `CrashLoopEvent`, `UnverifiedRise` | WP01 | |
| T002 | `CrashLoopConfig` strict loader + `scripts/canary/crash_loop_config.json` | WP01 | |
| T003 | State load with semantic validation and clock clamping | WP01 | |
| T004 | Atomic save + non-blocking `flock` helper | WP01 | |
| T005 | WP01 tests | WP01 | |
| T006 | Interval rule: horizon baseline, Δ, history retention/thinning | WP02 | [P] |
| T007 | Resets, generations, first sight, removal, incomplete scopes, ignore list | WP02 | [P] |
| T008 | Episode state machine: alert, pending resend, re-remind, cleared + rebase | WP02 | [P] |
| T009 | `apply_delivery`, emission plan (cap + aggregate), Alert rendering | WP02 | [P] |
| T010 | WP02 tests (SC-001, SC-002, US1–US3, Codex sequences) | WP02 | [P] |
| T011 | Command runner: argv, minimal env, shared deadline | WP03 | [P] |
| T012 | systemd `list-units` / `show` parsers with reconciliation | WP03 | [P] |
| T013 | System + user scope readers and boot ID | WP03 | [P] |
| T014 | Docker reader with isolated `DOCKER_CONFIG` and pinned `DOCKER_HOST` | WP03 | [P] |
| T015 | Real-output fixtures + WP03 tests | WP03 | [P] |
| T016 | `CrashLoopCheck` and its default builder | WP04 | |
| T017 | Crash-loop stage inside `run_pass` | WP04 | |
| T018 | `main()` wiring + signature-only adaptation of existing fakes | WP04 | |
| T019 | WP04 tests: paired disabled/enabled, key ledger, faults, dry-run, dead-man | WP04 | |
| T020 | Deploy entrypoint `--dry-run` / `--apply` | WP05 | [P] |
| T021 | Manifest `deploys/queued/0043-crash-loop-unit-alerting.yaml` | WP05 | [P] |
| T022 | WP05 tests + audited-surface check record | WP05 | [P] |
| T023 | Architecture data: service-inventory, data-flows (JSON + markdown) | WP06 | [P] |
| T024 | service-dependencies view, observability-and-alerting, roadmap review | WP06 | [P] |
| T025 | canary-registry-ops runbook section (tuning, ignore, reset, 7-day procedure) + docs/INDEX.md | WP06 | [P] |
| T026 | Docs validation run | WP06 | [P] |

## WP01 — Crash-loop model, config and state persistence

**Prompt**: [tasks/WP01-model-config-state.md](tasks/WP01-model-config-state.md) · **Priority**: P1 (foundation) · **Depends on**: none

**Goal**: The shared value types, the strictly validated configuration and the fail-safe, locked, atomic state store that every other WP builds on.

**Independent test**: `.venv/bin/python -m pytest tests/canary/test_crash_loop_model.py tests/canary/test_crash_loop_state.py -q`

T001 (WP01)
T002 (WP01)
T003 (WP01)
T004 (WP01)
T005 (WP01)

**Risks**: Getting the state validation wrong silently drops episodes. Every rejection rule needs a test.

## WP02 — Crash-loop decision core

**Prompt**: [tasks/WP02-decision-core.md](tasks/WP02-decision-core.md) · **Priority**: P1 (MVP: US1–US3) · **Depends on**: WP01

**Goal**: A pure `evaluate_tick` that turns scope readings and the prior state into events, unverified rises, scope status and a new state, plus the pure delivery and emission-plan helpers.

**Independent test**: `.venv/bin/python -m pytest tests/canary/test_crash_loop.py -q`, including `test_incident_replay_obsidian_sync_39_restarts`.

T006 (WP02)
T007 (WP02)
T008 (WP02)
T009 (WP02)
T010 (WP02)

**Parallel**: WP02 and WP03 touch disjoint files and can run in parallel once WP01 is approved.

## WP03 — Restart-count readers

**Prompt**: [tasks/WP03-readers.md](tasks/WP03-readers.md) · **Priority**: P1 · **Depends on**: WP01

**Goal**: Read the system, `claude` user and docker scopes without privilege, inside one deadline, and report incomplete scopes as could-not-check.

**Independent test**: `.venv/bin/python -m pytest tests/canary/test_crash_loop_readers.py -q`

T011 (WP03)
T012 (WP03)
T013 (WP03)
T014 (WP03)
T015 (WP03)

## WP04 — Canary integration and fault isolation

**Prompt**: [tasks/WP04-canary-integration.md](tasks/WP04-canary-integration.md) · **Priority**: P1 · **Depends on**: WP02, WP03

**Goal**: The stage runs inside `run_pass`, `main()` enables it, and every existing component behaves the same.

**Independent test**: `.venv/bin/python -m pytest tests/canary -q` (the whole canary suite).

T016 (WP04)
T017 (WP04)
T018 (WP04)
T019 (WP04)

## WP05 — Deploy entrypoint and manifest

**Prompt**: [tasks/WP05-deploy.md](tasks/WP05-deploy.md) · **Priority**: P2 · **Depends on**: WP04

**Goal**: A felix-deployer manifest whose entrypoint proves, on office2, that all three scopes are being read. **The manifest is authored but must not reach `main` without Kent's approval.**

**Independent test**: `.venv/bin/python -m pytest tests/deploy/test_deploy_crash_loop_unit_alerting.py -q`

T020 (WP05)
T021 (WP05)
T022 (WP05)

## WP06 — Living documentation

**Prompt**: [tasks/WP06-docs.md](tasks/WP06-docs.md) · **Priority**: P2 · **Depends on**: WP04

**Goal**: FR-014 and C-007. The architecture data, the narrative views, the runbook (with the 7-day acceptance procedure) and the docs index all describe crash-loop detection.

**Independent test**: `.venv/bin/python tooling/scripts/validate_docs.py` plus `.venv/bin/python -m pytest tests/docs tests/tooling -q`.

T023 (WP06)
T024 (WP06)
T025 (WP06)
T026 (WP06)

**Parallel**: WP05 and WP06 touch disjoint files and can run in parallel after WP04.

## Dependency graph

```
WP01 ──┬── WP02 ──┐
       └── WP03 ──┴── WP04 ──┬── WP05
                             └── WP06
```

MVP: WP01 + WP02 + WP03 + WP04 deliver detection. WP05 and WP06 deliver deployment and documentation.
