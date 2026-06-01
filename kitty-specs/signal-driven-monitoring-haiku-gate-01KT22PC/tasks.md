# Tasks — Signal-Driven Monitoring with Haiku Gate

**Mission**: `signal-driven-monitoring-haiku-gate-01KT22PC`
**Source issue**: [#490](https://github.com/kentonium3/kg-automation/issues/490)
**Spec**: [`spec.md`](./spec.md)
**Plan**: [`plan.md`](./plan.md)
**Branch contract**: planning base `main`, merge target `main`, matches: ✅

---

## Overview

Four sequential work packages (28 subtasks total) deliver a two-layer observation pipeline that replaces Felix's general-purpose Sonnet heartbeat. WP-01 builds deterministic signal-extraction primitives. WP-02 wires them into a tick orchestrator with a zero-LLM filing path plus a replay-based integration test against the 2026-06-01 incident log. WP-03 implements the Haiku-gated heartbeat with full fallback. WP-04 deploys everything to office2, updates architecture documentation per the standing CLAUDE.md requirement, and captures the pre-rollout token baseline that anchors NFR-001 validation.

The work-package boundaries are designed around file ownership: no two WPs touch the same file. WP dependency chain is strictly sequential (WP-02 → WP-01, WP-03 → WP-02 for digest format, WP-04 → all three for deployment).

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Signal config TOML schema + loader with validation | WP01 |  | [D] |
| T002 | Per-signal state persistence with atomic writes and cold-start recovery | WP01 | [D] |
| T003 | OpenClaw log tail/grep helper with cursor-based incremental reading | WP01 | [D] |
| T004 | Three signal extractor modules (creds_restore, watchdog_reconnect, unhandled_error) | WP01 |  | [D] |
| T005 | Seed `signals/config.toml` with FR-006 signals at calibrated thresholds | WP01 |  | [D] |
| T006 | Capture `openclaw-2026-06-01.log` as a checked-in test fixture | WP01 | [D] |
| T007 | Unit tests for config loader, state, log helper, signal extractors | WP01 |  | [D] |
| T008 | Filer module — subprocess invocation of `felix-file-issue.py` per contract | WP02 |  |
| T009 | Dedup-on-open-issue check (`gh issue view --json state` at filing time) | WP02 |  |
| T010 | Tick orchestrator — composes signals + state + filer, writes `last-tick.json` + ledger | WP02 |  |
| T011 | `--dry-run` CLI flag on tick orchestrator | WP02 |  |
| T012 | `--replay-log` CLI flag on tick orchestrator | WP02 |  |
| T013 | Filer + orchestrator unit tests (mocked subprocess, mocked gh CLI) | WP02 |  |
| T014 | Replay integration test against captured 2026-06-01 log (NFR-004, NFR-006) | WP02 |  |
| T015 | Gate context assembler — reads `last-tick.json` + HEARTBEAT.md + novelty markers | WP03 |  |
| T016 | Cache-aware Haiku routing prompt | WP03 |  |
| T017 | Anthropic SDK wrapper — invokes Haiku, parses 3-way response | WP03 |  |
| T018 | Escalator — invokes `openclaw system event --mode now` | WP03 | [P] |
| T019 | Gate ledger writer + atomic `last-gate-decision.json` writer | WP03 | [P] |
| T020 | Fallback path — on gate failure, invoke escalator with "gate fallback" reason | WP03 |  |
| T021 | Gate unit + behavioral tests (mocked Anthropic SDK, mocked subprocess) | WP03 |  |
| T022 | Pre-rollout token baseline capture and helper script | WP03 |  |
| T023 | Modify `felix-core-digest.service` to chain into tick orchestrator | WP04 |  |
| T024 | New `felix-heartbeat-gate.service` and `.timer` units | WP04 | [P] |
| T025 | Update `service-inventory.json` with new entries + felix-core-digest changes | WP04 | [P] |
| T026 | Update `credential-manifest.json` confirming kg-felix-bot scope | WP04 | [P] |
| T027 | Update `data-flows.json` with new flows + regenerate markdown views | WP04 |  |
| T028 | Deployment runbook + cutover-procedure documentation | WP04 |  |

`[P]` indicates a subtask that can execute in parallel with siblings inside its WP (touches different files / no in-WP dependency on the prior subtask).

---

## WP01 — Signal extraction primitives

**Goal**: deliver the deterministic, zero-LLM building blocks of the signal-extraction pipeline (config, state, log helpers, signal modules, fixtures, unit tests). No orchestration; no filing. WP-02 composes these into a working tick.

**Priority**: Foundation (blocks WP02, WP03, WP04).
**Independent test**: `pytest scripts/openclaw/observation/tests/test_signals_*.py test_state_persistence.py test_config_loader.py` passes with ≥85% line / ≥80% branch coverage.

**Included subtasks**:
- [x] T001 Signal config TOML schema + loader with validation (WP01)
- [x] T002 Per-signal state persistence with atomic writes and cold-start recovery (WP01) [P]
- [x] T003 OpenClaw log tail/grep helper with cursor-based incremental reading (WP01) [P]
- [x] T004 Three signal extractor modules (creds_restore, watchdog_reconnect, unhandled_error) (WP01)
- [x] T005 Seed `signals/config.toml` with FR-006 signals at calibrated thresholds (WP01)
- [x] T006 Capture `openclaw-2026-06-01.log` as a checked-in test fixture (WP01) [P]
- [x] T007 Unit tests for config loader, state, log helper, signal extractors (WP01)

**Implementation sketch**:
1. T001 + T002 + T003 + T006 are all independent file creations (parallel-safe within the WP).
2. T004 builds on the log helper from T003 and the config from T001.
3. T005 is config authoring; depends on T001 (loader exists).
4. T007 final coverage check.

**Dependencies**: none.
**Risks**: log cursor logic needs to be robust to OpenClaw's daily-file rotation (`/tmp/openclaw/openclaw-YYYY-MM-DD.log`). Mitigation: cursor stores `(path, inode, byte_offset, mtime)`; recovery logic re-reads last N cycles on inode change.
**Estimated prompt size**: ~500 lines.

**Prompt**: [`tasks/WP01-signal-extraction-primitives.md`](./tasks/WP01-signal-extraction-primitives.md)

---

## WP02 — Tick orchestrator + deterministic filer + replay test

**Goal**: compose WP-01's primitives into a tick orchestrator that extracts signals, evaluates thresholds, files issues deterministically via the existing `felix-file-issue.py` body builder, and writes `last-tick.json` + the JSONL ledger. Includes the replay integration test that validates NFR-004 (accuracy) and NFR-006 (time-to-action) against the captured 2026-06-01 log.

**Priority**: Core (blocks WP-03 because WP-03's gate reads `last-tick.json` format).
**Independent test**: `pytest scripts/openclaw/observation/tests/test_tick_orchestrator.py test_filer.py test_replay_20260601.py` passes; replay test confirms expected filings match ground truth within tolerance.

**Included subtasks**:
- [ ] T008 Filer module — subprocess invocation of `felix-file-issue.py` per contract (WP02)
- [ ] T009 Dedup-on-open-issue check (`gh issue view --json state` at filing time) (WP02)
- [ ] T010 Tick orchestrator — composes signals + state + filer, writes `last-tick.json` + ledger (WP02)
- [ ] T011 `--dry-run` CLI flag on tick orchestrator (WP02)
- [ ] T012 `--replay-log` CLI flag on tick orchestrator (WP02)
- [ ] T013 Filer + orchestrator unit tests (mocked subprocess, mocked gh CLI) (WP02)
- [ ] T014 Replay integration test against captured 2026-06-01 log (NFR-004, NFR-006) (WP02)

**Implementation sketch**:
1. T008 (filer) + T009 (dedup) can be developed in parallel — they're independent surfaces.
2. T010 wires both into the orchestrator.
3. T011 + T012 are CLI flag additions.
4. T013 + T014 validate.

**Dependencies**: WP-01 (consumes signals/, state.py, config_loader, openclaw_log helper).
**Risks**: the filer's subprocess contract is brittle to changes in `felix-file-issue.py`. Mitigation: T013 includes a contract test that invokes `felix-file-issue.py --dry-run` with the filer's constructed arguments and asserts no rejection.
**Estimated prompt size**: ~500 lines.

**Prompt**: [`tasks/WP02-tick-orchestrator-and-filer.md`](./tasks/WP02-tick-orchestrator-and-filer.md)

---

## WP03 — Heartbeat gate + pre-rollout baseline

**Goal**: implement the Haiku-fronted heartbeat gate per FR-007..FR-011, including the fallback path. Capture the pre-rollout token baseline that NFR-001 will be validated against post-deploy.

**Priority**: Core (independent of WP-01/WP-02 file-wise; logically depends on WP-02 for the `last-tick.json` format).
**Independent test**: `pytest scripts/openclaw/heartbeat_gate/tests/` passes; gate makes correct 3-way routing decision for each test scenario.

**Included subtasks**:
- [ ] T015 Gate context assembler — reads `last-tick.json` + HEARTBEAT.md + novelty markers (WP03)
- [ ] T016 Cache-aware Haiku routing prompt (WP03)
- [ ] T017 Anthropic SDK wrapper — invokes Haiku, parses 3-way response (WP03)
- [ ] T018 Escalator — invokes `openclaw system event --mode now` (WP03) [P]
- [ ] T019 Gate ledger writer + atomic `last-gate-decision.json` writer (WP03) [P]
- [ ] T020 Fallback path — on gate failure, invoke escalator with "gate fallback" reason (WP03)
- [ ] T021 Gate unit + behavioral tests (mocked Anthropic SDK, mocked subprocess) (WP03)
- [ ] T022 Pre-rollout token baseline capture and helper script (WP03)

**Implementation sketch**:
1. T015 + T016 are independent (assembler reads files; prompt is a markdown asset).
2. T017 wires the prompt to the SDK.
3. T018 + T019 are independent surfaces (escalator subprocess, ledger writer).
4. T020 composes the failure-mode wiring.
5. T021 validates.
6. T022 is its own concern — helper that estimates current Sonnet heartbeat cost from OpenClaw history, outputs a baseline JSON.

**Dependencies**: WP-02 (reads `last-tick.json` format per `contracts/tick-signal.contract.md`).
**Risks**:
- Anthropic SDK prompt caching only works when system portion is verbatim across calls; assembler must NOT inject dynamic content into the system portion. Mitigation: cache-aware structure pinned in `contracts/`-style notes inside the prompt file.
- Baseline capture (T022) depends on OpenClaw retaining enough heartbeat history. If not retained, baseline becomes an estimate not a measurement. Mitigation: document the data source and recapture window in the baseline JSON.

**Estimated prompt size**: ~550 lines.

**Prompt**: [`tasks/WP03-heartbeat-gate-and-baseline.md`](./tasks/WP03-heartbeat-gate-and-baseline.md)

---

## WP04 — Deployment + architecture documentation

**Goal**: deploy the new services to office2, update architecture documentation per the standing CLAUDE.md requirement, disable OpenClaw's internal heartbeat, and produce the deployment runbook + cutover procedure.

**Priority**: Final (depends on WP-01, WP-02, WP-03 being merged to the lane).
**Independent test**: post-deploy smoke check passes (`systemctl --user status felix-core-digest.timer felix-heartbeat-gate.timer` shows both active; `last-tick.json` and `last-gate-decision.json` both fresh within their respective cadences).

**Included subtasks**:
- [ ] T023 Modify `felix-core-digest.service` to chain into tick orchestrator (WP04)
- [ ] T024 New `felix-heartbeat-gate.service` and `.timer` units (WP04) [P]
- [ ] T025 Update `service-inventory.json` with new entries + felix-core-digest changes (WP04) [P]
- [ ] T026 Update `credential-manifest.json` confirming kg-felix-bot scope (WP04) [P]
- [ ] T027 Update `data-flows.json` with new flows + regenerate markdown views (WP04)
- [ ] T028 Deployment runbook + cutover-procedure documentation (WP04)

**Implementation sketch**:
1. T023 + T024 are systemd unit changes (parallel-safe; different files).
2. T025 + T026 + T027 are JSON updates per the CLAUDE.md architecture-doc protocol (parallel-safe; different files).
3. T028 captures the cutover procedure (including `openclaw system heartbeat disable` as the explicit Tier 2 step needing Restic snapshot confirmation per CLAUDE.md).

**Dependencies**: WP-01, WP-02, WP-03.
**Risks**:
- `openclaw system heartbeat disable` is a Tier 2 change to deployed state; T028 must include the Restic-snapshot precondition and the post-change verification step.
- `service-inventory.json` schema must match existing entries; mitigation: study a sibling entry (e.g., `felix-doc-auditor`) for shape before authoring new ones.
- Markdown view regeneration must match the existing automation pattern; mitigation: invoke the existing regenerator script rather than hand-editing markdown.

**Estimated prompt size**: ~400 lines.

**Prompt**: [`tasks/WP04-deployment-and-architecture-docs.md`](./tasks/WP04-deployment-and-architecture-docs.md)

---

## Cross-WP risks

- **Identity drift**: `felix-file-issue.py` rejects filings if active `gh` identity isn't `kg-felix-bot`. WP-02's tests must run with a mocked gh CLI; WP-04's deployment runbook must verify identity post-deploy.
- **Log path drift**: `/tmp/openclaw/openclaw-*.log` is the assumed source path. If OpenClaw upgrades change this path, all signal extractors break silently (extractor would see "source missing" warning, no error). Mitigation: T007 unit test covers the "source missing" path; WP-04 runbook documents how to check.
- **Concurrent heartbeats**: if OpenClaw's heartbeat is NOT disabled before the new gate timer activates, both will fire and the main agent gets double-invoked. WP-04's cutover procedure pins the disable step as a precondition to enabling the new timer.

## Parallelization opportunities

Within each WP:
- WP-01: T001/T002/T003/T006 parallel.
- WP-02: T008/T009 parallel.
- WP-03: T015/T016 parallel; T018/T019 parallel.
- WP-04: T023/T024 parallel; T025/T026/T027 parallel.

Across WPs: strictly sequential (WP-02 needs WP-01's modules; WP-03 needs WP-02's `last-tick.json` format; WP-04 needs all three).

## MVP scope

**WP-01 + WP-02 alone** would already deliver the accuracy improvement targeted by NFR-004 (the deterministic filer would file accurate issues), but without the cost reduction in NFR-001. If time pressure forces a partial mission, merging WP-01 + WP-02 + WP-04 (skipping WP-03 + the gate-specific deployment subtasks) would still ship the deterministic monitoring layer. WP-03 can follow as a separate mission.

That said: the spec is committed to delivering both layers in a single mission per Kent's specify-phase decision. WP-03 ships as planned.
