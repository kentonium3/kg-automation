# Tasks: Refactor doc-auditor to scripts-first driver

**Mission**: `refactor-doc-auditor-to-scripts-first-driver-01KS2XNX`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)
**Date**: 2026-05-20
**Branch contract**: planning_base=main, merge_target=main, branch_matches_target=true

---

## Subtask Index

This index is for reference only. Per-WP tracking happens via checkboxes in the work-package sections below.

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Move `handle_drift_events.py` to `scripts/doc_audit/helpers/` | WP01 | | [D] |
| T002 | Move `handle_audit_routing.py` to `scripts/doc_audit/helpers/` | WP01 | | [D] |
| T003 | Refactor each helper: separate `main()` from internal functions; verify CLI still works | WP01 | | [D] |
| T004 | Update references in `docs/design/helper-script-conventions.md`, `docs/design/architecture/felix-d6-survey.md`, `docs/design/architecture/data/signal-to-doc-map.json` | WP01 | [D] |
| T005 | Unit tests for the new importable surfaces in `tests/doc_audit/helpers/` | WP01 | [D] |
| T006 | Create `scripts/doc_audit/` package scaffold (`__init__.py`, `README.md`) | WP02 | |
| T007 | Implement `data_model.py` with all 10 entities (E-001..E-010) | WP02 | |
| T008 | Implement `config.py` + `config.toml` (default config) | WP02 | |
| T009 | Conftest + fixtures for the test package | WP02 | |
| T010 | Unit tests for data-model entities (serialization, parsing, invariants) | WP02 | [P] |
| T011 | Define `SignalSource` Protocol + `Signal` dataclass in `signals/base.py` | WP03 | |
| T012 | Implement `GHIssueSignalSource` (`signals/gh_issue.py`) — consume Doc audit / Weekly / pending-approval | WP03 | |
| T013 | Implement `DriftEventSignalSource` (`signals/drift_event.py`) — wrap `helpers/handle_drift_events.py` imports | WP03 | |
| T014 | Unit tests for `GHIssueSignalSource` with mocked `gh` subprocess | WP03 | [P] |
| T015 | Unit tests for `DriftEventSignalSource` with mocked drift-events.jsonl fixture | WP03 | [P] |
| T016 | Implement `judgment/client.py` — Anthropic SDK wrapper + prompt-cache helpers | WP04 | |
| T017 | Write `prompts/tier_classification.prompt.md` (cache-aware template) | WP04 | |
| T018 | Write `prompts/debt_body_generation.prompt.md` (cache-aware template) | WP04 | |
| T019 | Write `prompts/cross_file_implication.prompt.md` (cache-aware template) | WP04 | |
| T020 | Implement `judgment/tier_classification.py` + `judgment/debt_body_generation.py` + `judgment/cross_file_implication.py` | WP04 | |
| T021 | Unit tests for each judgment moment (mocked `anthropic.Anthropic` client) | WP04 | [P] |
| T022 | Implement `routing/apply_decisions.py` — wraps `helpers/handle_audit_routing.py` imports | WP05 | |
| T023 | Implement `output/tick_signal.py` — atomic write of `last-tick.json` (E-009, NFR-003/004) | WP05 | |
| T024 | Implement `output/activity_log.py` — preserved-format append to `/home/kgale/second-brain/agents/logs/` (C-005, FR-009) | WP05 | |
| T025 | Unit tests for routing + output layers | WP05 | [P] |
| T026 | Implement `scripts/doc_audit/run.py` — CLI entry point (D6, driver-invocation contract) | WP06 | |
| T027 | Implement top-level orchestration loop: pending-approvals → new audits → drift events (FR-004) | WP06 | |
| T028 | Implement stuck-lock recovery logic (FR-014) | WP06 | |
| T029 | Wire error-handling per spec edge cases (LLM outage, rate-limit, missing-file, stuck-lock) | WP06 | |
| T030 | Integration tests covering 5 tick outcomes (empty, debt-only, Tier-A, pending-approval-apply, pending-approval-reject) | WP06 | [P] |
| T031 | Integration tests covering 4 edge cases | WP06 | [P] |
| T032 | Write `tests/doc_audit/test_smoke_live.py` (gated by `pytest -m live_smoke`) | WP07 | |
| T033 | Run pre-rework baseline measurement against current openclaw-agent (3+ representative ticks) | WP07 | |
| T034 | Write `docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json` | WP07 | |
| T035 | Document measurement methodology in baseline file's `methodology` field | WP07 | |
| T036 | Update `scripts/office2/felix-doc-auditor.service` ExecStart from `openclaw agent ...` to `python3 scripts/doc_audit/run.py` | WP08 | |
| T037 | Write `scripts/office2/deploy/felix-doc-auditor-driver.sh` (rsync code + create dirs + install systemd + retire openclaw agent) | WP08 | |
| T038 | Test deploy script in `--dry-run` mode against office2 | WP08 | |
| T039 | Document deploy operation in deploy script comment header | WP08 | |
| T040 | Pre-cutover: drain queue, confirm zero open `status:in-progress` audits and zero pending-approvals without decision labels | WP09 | |
| T041 | Execute cutover: merge to main, run `felix-doc-auditor-driver.sh --apply` on office2 | WP09 | |
| T042 | Verify first tick: `systemctl --user start --wait felix-doc-auditor.service`; inspect `last-tick.json` and journal | WP09 | |
| T043 | Run post-rework measurement: 3+ representative ticks under new driver | WP09 | |
| T044 | Write `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json` | WP09 | |
| T045 | Verify ≥80% reduction; record per-outcome breakdown (NFR-001) | WP09 | |
| T046 | Update `docs/design/architecture/data/service-inventory.json` — felix-doc-auditor entry: new invocation, deps, no openclaw session storage | WP10 | |
| T047 | Update `docs/design/architecture/data/data-flows.json` — remove openclaw-session edges; add direct-API edges | WP10 | |
| T048 | Update `docs/design/architecture/data/credential-manifest.json` — note Anthropic key used by driver process | WP10 | |
| T049 | Append a note to `docs/design/architecture/felix-d6-survey.md` acknowledging that #343 obsoletes the prior "low priority" verdict for felix-doc-auditor | WP10 | |
| T050 | Write `docs/runbooks/doc-auditor-driver-ops.md` (FR-013) | WP10 | |
| T051 | Update memory file `~/.claude/projects/-Users-kentgale-repos-kg-automation/memory/reference_felix_doc_auditor_ops.md` | WP10 | [P] |

**Total**: 51 subtasks across 10 work packages. Average 5.1 subtasks/WP — within ideal range.

---

## Dependency Graph

```
WP01 ──┐
       ├─→ WP03 ──┐
WP02 ──┤          ├─→ WP06 ──┐
       ├─→ WP04 ──┤          ├─→ WP09 ──→ WP10
       └─→ WP05 ──┘          │
                  WP07 ──────┤
                  WP08 ──────┘
```

- WP01 (helpers) + WP02 (data model) are foundational; can run in parallel
- WP03/WP04/WP05 depend on WP01+WP02; can run in parallel after that
- WP06 (driver) depends on WP03+WP04+WP05
- WP07 (baseline measurement) depends on WP06 (needs the comparison endpoint defined)
- WP08 (deploy) depends on WP06 (needs the driver to deploy)
- WP09 (cutover) depends on WP06+WP07+WP08
- WP10 (docs) depends on WP09 (needs the final state)

---

## Work Packages

### WP01 — Lift and refactor existing helpers

**Goal**: Move the two reusable helper scripts (`handle_drift_events.py`, `handle_audit_routing.py`) from `scripts/openclaw/agents/felix-doc-auditor/` into `scripts/doc_audit/helpers/`. Refactor each to expose its internal functions as importable Python while preserving the existing CLI entry point. Update docs that reference the old paths.

**Priority**: P1 (foundational — WP03, WP05 depend on the import surface)
**Independent test**: Each helper's existing CLI invocation continues to work unchanged; new importable functions can be called from Python without subprocess overhead.
**Estimated prompt size**: ~350 lines

**Included subtasks**:
- [x] T001 Move `handle_drift_events.py` to `scripts/doc_audit/helpers/`
- [x] T002 Move `handle_audit_routing.py` to `scripts/doc_audit/helpers/`
- [x] T003 Refactor each helper: separate `main()` from internal functions; verify CLI still works
- [x] T004 [P] Update doc references (`helper-script-conventions.md`, `felix-d6-survey.md`, `signal-to-doc-map.json`)
- [x] T005 [P] Unit tests for the new importable surfaces in `tests/doc_audit/helpers/`

**Dependencies**: None
**Risks**: Breaking the existing AGENTS.md §2 bash invocation by mis-moving the file; mitigation = retain CLI entry; ensure absolute paths in the move don't leave dangling refs.

**Prompt file**: [`tasks/WP01-lift-and-refactor-helpers.md`](./tasks/WP01-lift-and-refactor-helpers.md)

---

### WP02 — Package scaffolding + data model

**Goal**: Create the `scripts/doc_audit/` Python package with config layer and the 10 entity dataclasses from `data-model.md`. This is the foundation every subsequent WP imports from.

**Priority**: P1 (foundational)
**Independent test**: Package imports cleanly; data-model serialization round-trips for each entity; config loads from default TOML and overridable via `--config`.
**Estimated prompt size**: ~400 lines

**Included subtasks**:
- [ ] T006 Create `scripts/doc_audit/` package scaffold (`__init__.py`, `README.md`)
- [ ] T007 Implement `data_model.py` with all 10 entities (E-001..E-010)
- [ ] T008 Implement `config.py` + `config.toml` (default config)
- [ ] T009 Conftest + fixtures for the test package
- [ ] T010 [P] Unit tests for data-model entities

**Dependencies**: None
**Risks**: Misaligning entity shapes with what consumers expect; mitigation = explicit reference to `data-model.md` E-001..E-010 in each dataclass docstring.

**Prompt file**: [`tasks/WP02-package-scaffolding-and-data-model.md`](./tasks/WP02-package-scaffolding-and-data-model.md)

---

### WP03 — Signal source adapters

**Goal**: Implement the `SignalSource` Protocol and its two initial concrete adapters (`GHIssueSignalSource`, `DriftEventSignalSource`). These ingest signals from GitHub issues and from drift-events.jsonl respectively, normalize them to `Signal` instances, and feed the driver.

**Priority**: P1 (driver depends on this)
**Independent test**: Each adapter's `pending()` returns the expected `Signal` list against mocked external surfaces; `commit()` advances cursor (drift) or no-ops (gh).
**Estimated prompt size**: ~450 lines

**Included subtasks**:
- [ ] T011 Define `SignalSource` Protocol + `Signal` dataclass
- [ ] T012 Implement `GHIssueSignalSource`
- [ ] T013 Implement `DriftEventSignalSource` (wraps helpers)
- [ ] T014 [P] Unit tests for `GHIssueSignalSource`
- [ ] T015 [P] Unit tests for `DriftEventSignalSource`

**Dependencies**: WP01, WP02
**Risks**: Adapter behavior diverges from existing AGENTS.md §2 semantics; mitigation = explicit fixture tests against expected I/O.

**Prompt file**: [`tasks/WP03-signal-source-adapters.md`](./tasks/WP03-signal-source-adapters.md)

---

### WP04 — LLM client + prompt artifacts

**Goal**: Implement the Anthropic SDK wrapper with prompt-cache support, plus the three checked-in judgment-prompt templates (`tier_classification`, `debt_body_generation`, `cross_file_implication`) and their per-moment Python modules. This is the LLM surface the driver hits at narrow judgment points.

**Priority**: P1 (driver depends on this)
**Independent test**: Each judgment moment's Python wrapper, against mocked Anthropic SDK responses, produces structured outputs matching the contract schemas.
**Estimated prompt size**: ~500 lines

**Included subtasks**:
- [ ] T016 Implement `judgment/client.py` — SDK wrapper + cache helpers
- [ ] T017 Write `prompts/tier_classification.prompt.md`
- [ ] T018 Write `prompts/debt_body_generation.prompt.md`
- [ ] T019 Write `prompts/cross_file_implication.prompt.md`
- [ ] T020 Implement three judgment modules
- [ ] T021 [P] Unit tests with mocked Anthropic SDK

**Dependencies**: WP02
**Risks**: Prompts under-specified → LLM hallucination; mitigation = response-schema validation in the driver per `contracts/judgment-prompts.contract.md`.

**Prompt file**: [`tasks/WP04-llm-client-and-prompt-artifacts.md`](./tasks/WP04-llm-client-and-prompt-artifacts.md)

---

### WP05 — Routing + output layers

**Goal**: Implement the routing layer (wrapping `helpers/handle_audit_routing.py`) and the output layer (tick-signal artifact writer + activity-log appender). These are the side-effect surfaces the driver invokes after judgment.

**Priority**: P1 (driver depends on this)
**Independent test**: Routing applies a mocked audit-state decision correctly; tick-signal writer produces a valid JSON artifact matching the contract; activity-log appender preserves the existing format.
**Estimated prompt size**: ~350 lines

**Included subtasks**:
- [ ] T022 Implement `routing/apply_decisions.py`
- [ ] T023 Implement `output/tick_signal.py`
- [ ] T024 Implement `output/activity_log.py`
- [ ] T025 [P] Unit tests for routing + output

**Dependencies**: WP01, WP02
**Risks**: Tick-signal JSON schema drift; mitigation = round-trip parser test against the contract's example.

**Prompt file**: [`tasks/WP05-routing-and-output-layers.md`](./tasks/WP05-routing-and-output-layers.md)

---

### WP06 — Driver entrypoint + integration tests

**Goal**: Implement `scripts/doc_audit/run.py` CLI, the top-level orchestration loop (priority-ordered signal processing), stuck-lock recovery, and error-handling. Add integration tests covering all 5 tick outcomes and the 4 documented edge cases.

**Priority**: P1 (the synthesis WP — this is where it all comes together)
**Independent test**: Full-driver run with mocked external surfaces processes a synthetic queue end-to-end for each of the 5 outcomes; edge cases exit with the expected status codes and signals.
**Estimated prompt size**: ~600 lines

**Included subtasks**:
- [ ] T026 Implement `run.py` CLI entry point
- [ ] T027 Implement orchestration loop
- [ ] T028 Implement stuck-lock recovery (FR-014)
- [ ] T029 Wire error-handling per spec edge cases
- [ ] T030 [P] Integration tests for 5 tick outcomes
- [ ] T031 [P] Integration tests for 4 edge cases

**Dependencies**: WP03, WP04, WP05
**Risks**: Subtle dispatch bugs (wrong priority order, off-by-one on cursor advance, etc.); mitigation = explicit dispatch-table tests + fixture-driven integration.

**Prompt file**: [`tasks/WP06-driver-entrypoint-and-integration-tests.md`](./tasks/WP06-driver-entrypoint-and-integration-tests.md)

---

### WP07 — Live smoke + pre-rework baseline measurement

**Goal**: Write the live smoke test and run the pre-rework token-cost baseline measurement against the current openclaw-agent auditor. Capture the methodology and data in a committed JSON file. This produces the numerator for the NFR-001 ≥80% reduction acceptance.

**Priority**: P2 (depends on WP06; gates WP09)
**Independent test**: Live smoke (when gated env present) hits real GH + real Anthropic and the assertion holds; baseline JSON exists with all required fields populated.
**Estimated prompt size**: ~250 lines

**Included subtasks**:
- [ ] T032 Write `tests/doc_audit/test_smoke_live.py`
- [ ] T033 Run pre-rework baseline measurement
- [ ] T034 Write `baselines/felix-doc-auditor-pre-rework.json`
- [ ] T035 Document methodology in the baseline file

**Dependencies**: WP06
**Risks**: Baseline measurement on a live system perturbs the system; mitigation = run in `--dry-run`-equivalent mode against a known-empty queue.

**Prompt file**: [`tasks/WP07-live-smoke-and-baseline-measurement.md`](./tasks/WP07-live-smoke-and-baseline-measurement.md)

---

### WP08 — Deploy script + systemd unit update

**Goal**: Update the systemd unit ExecStart and write the deploy script that lands the new driver on office2 and retires the old openclaw-agent definition.

**Priority**: P2 (depends on WP06; gates WP09)
**Independent test**: Deploy script's `--dry-run` mode prints all intended operations correctly without making any changes; systemd unit syntax-checks via `systemd-analyze verify` (or equivalent).
**Estimated prompt size**: ~300 lines

**Included subtasks**:
- [ ] T036 Update `scripts/office2/felix-doc-auditor.service` ExecStart
- [ ] T037 Write `scripts/office2/deploy/felix-doc-auditor-driver.sh`
- [ ] T038 Test deploy script in `--dry-run` mode
- [ ] T039 Document deploy operation in script comment header

**Dependencies**: WP06
**Risks**: Deploy script does too much (deleting old workspace + retiring openclaw + installing new = several failure points); mitigation = each step is idempotent and reports clearly.

**Prompt file**: [`tasks/WP08-deploy-script-and-systemd-unit.md`](./tasks/WP08-deploy-script-and-systemd-unit.md)

---

### WP09 — Cutover execution + post-rework measurement

**Goal**: Execute the cutover (drain queue → merge to main → deploy on office2 → verify first tick → run post-rework measurement → verify ≥80% reduction). This is the operationally-most-consequential WP.

**Priority**: P2 (depends on WP06+WP07+WP08)
**Independent test**: After cutover, the next hourly tick produces a `last-tick.json` with `status: success`; post-rework baseline JSON shows ≥80% token reduction vs pre-rework.
**Estimated prompt size**: ~400 lines

**Included subtasks**:
- [ ] T040 Pre-cutover: drain queue, confirm no in-flight pending-approvals
- [ ] T041 Execute cutover: merge to main + run deploy script
- [ ] T042 Verify first tick
- [ ] T043 Run post-rework measurement (3+ representative ticks)
- [ ] T044 Write `baselines/felix-doc-auditor-post-rework.json`
- [ ] T045 Verify ≥80% reduction; record per-outcome breakdown

**Dependencies**: WP06, WP07, WP08
**Risks**: Cutover failure with no rollback (per C-007 fail-forward); mitigation = pre-flight checks + verification tick before next cron fire.

**Prompt file**: [`tasks/WP09-cutover-and-post-rework-measurement.md`](./tasks/WP09-cutover-and-post-rework-measurement.md)

---

### WP10 — Architecture docs + operator runbook

**Goal**: Update the architecture JSON sources (service-inventory, data-flows, credential-manifest), append a note to felix-d6-survey, write the new operator runbook, and update the memory file. Closes FR-012 + FR-013.

**Priority**: P2 (final cleanup)
**Independent test**: All architecture JSON files have `updated_by` set to issue #343; markdown views match JSON; new runbook is discoverable from `docs/INDEX.md` (or filed as docs-debt if INDEX update is out-of-scope per spec).
**Estimated prompt size**: ~300 lines

**Included subtasks**:
- [ ] T046 Update `service-inventory.json` — felix-doc-auditor entry
- [ ] T047 Update `data-flows.json` — remove openclaw-session edges; add direct-API edges
- [ ] T048 Update `credential-manifest.json` — note Anthropic key used by driver process
- [ ] T049 Append note to `felix-d6-survey.md` acknowledging #343 obsoletes the prior verdict
- [ ] T050 Write `docs/runbooks/doc-auditor-driver-ops.md`
- [ ] T051 [P] Update memory file `reference_felix_doc_auditor_ops.md`

**Dependencies**: WP09 (needs the final-state to be live and verified)
**Risks**: Doc drift if any architecture JSON has unrelated outstanding edits; mitigation = `updated_by` discipline + cross-check against markdown views.

**Prompt file**: [`tasks/WP10-architecture-docs-and-runbook.md`](./tasks/WP10-architecture-docs-and-runbook.md)

---

## Parallelization Strategy

The dependency graph permits the following execution lanes (computed by `finalize-tasks`):

- **Lane A (foundation)**: WP01 → WP05 → WP06 → WP08 → WP09 → WP10
- **Lane B (foundation parallel)**: WP02 → WP03 → WP06 (joins)
- **Lane C (judgment parallel)**: WP04 → WP06 (joins)
- **Lane D (measurement parallel)**: WP07 (after WP06)

WP06 is the join point; WP09 is the deploy serialization point. Up to 3 lanes can advance simultaneously between WP02 completion and WP06 start.

## MVP Scope Recommendation

If the mission ever needs an MVP shipping target (it doesn't, by spec — the full rework is the deliverable), it would be **WP01 + WP02 + WP06's orchestration shell** running only the GH-issue signal source with one judgment moment (tier_classification). This is NOT recommended — ship the full mission.

## Cross-references

- **Spec**: [spec.md](./spec.md)
- **Plan**: [plan.md](./plan.md)
- **Research (D1-D14)**: [research.md](./research.md)
- **Data model (E-001..E-010)**: [data-model.md](./data-model.md)
- **Contracts**: [contracts/](./contracts/)
- **Quickstart**: [quickstart.md](./quickstart.md)
- **GitHub issue**: [#343](https://github.com/kentonium3/kg-automation/issues/343)
