# Tasks: Signal trip cycle floor

**Mission**: `signal-trip-cycle-floor-01KT4NHJ`
**Planning base**: `main` | **Merge target**: `main`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Implement cycle-floor gate in `_threshold_status` | WP01 |  |
| T002 | Extend pytest coverage for the four trip outcomes (new boundary cases) | WP01 |  |
| T003 | Update mission #490's `tick-signal.contract.md` with a "Trip predicate" section | WP01 | [P] |

Three subtasks roll into a single work package. T003 is parallel-safe relative to T001/T002 (different file, no code dependency), but the WP is small enough that a single agent can sequence them efficiently.

## Work Package WP01 — Quiet-cycle gate

**Goal**: Land the cycle-floor gate that makes `_threshold_status` return `below` whenever `count_cycle == 0`, regardless of the rolling-window count. Update the matching contract documentation and extend tests to cover all four named outcomes under the new semantics.

**Priority**: P1 (sole WP for the mission)

**Independent test**: Run `pytest scripts/openclaw/observation/tests/test_tick_orchestrator.py -v` and observe every named case from `contracts/trip-predicate.contract.md` § "Test obligations" passing.

**Estimated prompt size**: ~350 lines

### Included subtasks

- [ ] T001 Implement cycle-floor gate in `_threshold_status` (WP01)
- [ ] T002 Extend pytest coverage for the four trip outcomes (WP01)
- [ ] T003 Update mission #490's `tick-signal.contract.md` with a "Trip predicate" section (WP01)

### Implementation sketch

1. Read the current predicate at `scripts/openclaw/observation/tick.py::_threshold_status` (≈ 17 lines).
2. Add one boolean comparison — `count_cycle >= 1` — to the rolling-only branch's condition; preserve everything else.
3. Open `scripts/openclaw/observation/tests/test_tick_orchestrator.py`, locate any existing direct test of `_threshold_status` (there may be none — it's currently tested transitively through `run_cycle` integration tests). Add a focused unit test class (or set of test functions) covering each named case from the trip-predicate contract.
4. Update `kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md` to add a new "## Trip predicate" section between the field definitions and the health-check contract. Use the normative pseudocode from this mission's contract doc.
5. Run the full mission #490 test suite (`pytest scripts/openclaw/observation/tests/ -v`) to verify no transitive regression. Adjust any integration test that asserted on `tripped_rolling` under `count_cycle == 0` semantics (per data-model.md, only row #2 changes — there should be at most a small number of such assertions, possibly none).

### Parallel opportunities

- T003 (contract update) touches a different file than T001/T002 and can be authored independently. For a one-agent WP, sequence T001 → T002 → T003 to keep the test loop tight; for two agents, T003 can land in parallel.

### Dependencies

None. The WP depends only on artifacts already in this mission's `kitty-specs/` tree and on the existing mission #490 code.

### Risks

- Predicate regression — covered by the boundary tests added in T002.
- Contract drift — covered by T003 + reviewer comparison against this mission's `contracts/trip-predicate.contract.md`.
- Surprise test breakage — if mission #490's integration tests exercise the `count_cycle=0, count_rolling=high` case under the old semantics, they will need updating. Per data-model.md row analysis, this is plausible but bounded; address as encountered.

## Branch strategy

- Planning base: `main`
- Merge target: `main`
- Execution worktree: created by `spec-kitty next` per `lanes.json` (single lane, since there's only one WP).
