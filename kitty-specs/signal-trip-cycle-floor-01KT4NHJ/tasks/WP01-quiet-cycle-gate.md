---
work_package_id: WP01
title: Quiet-cycle gate
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- NFR-001
- NFR-002
- NFR-003
- C-001
- C-002
- C-003
- C-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-signal-trip-cycle-floor-01KT4NHJ
base_commit: 1f43282d1bc4b33431b560ba3b70bd85312cf283
created_at: '2026-06-02T17:27:27.081664+00:00'
subtasks:
- T001
- T002
- T003
shell_pid: "63470"
agent: "codex"
history:
- timestamp: '2026-06-02T17:25:00Z'
  actor: claude:opus-4-7:planner
  action: created
authoritative_surface: scripts/openclaw/observation/
execution_mode: code_change
owned_files:
- scripts/openclaw/observation/tick.py
- scripts/openclaw/observation/tests/test_tick_orchestrator.py
- kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md
tags: []
---

# WP01 — Quiet-cycle gate

**Mission**: `signal-trip-cycle-floor-01KT4NHJ` — [spec.md](../spec.md), [plan.md](../plan.md), [contracts/trip-predicate.contract.md](../contracts/trip-predicate.contract.md), [data-model.md](../data-model.md)
**Source issue**: [#512](https://github.com/kentonium3/kg-automation/issues/512)

## Objective

Land a one-predicate change in `scripts/openclaw/observation/tick.py::_threshold_status` that introduces a quiet-cycle gate on the rolling branch: the function MUST return `below` whenever `count_cycle == 0`, regardless of how high `count_rolling` is. Pair the code change with a "Trip predicate" section in mission #490's authoritative contract and full pytest coverage of the four trip outcomes (`below`, `tripped_cycle`, `tripped_rolling`, `tripped_both`) at the new semantics' boundaries.

## Context

Mission #490 (`signal-driven-monitoring-haiku-gate-01KT22PC`) delivered the signal-extraction pipeline that walks OpenClaw logs every 15 minutes and files GitHub issues when thresholds trip. The trip evaluator currently uses an OR-of-branches rule: it fires whenever `count_cycle ≥ cycle_threshold` OR `count_rolling ≥ rolling_threshold`. On 2026-06-01 → 2026-06-02 a real upstream noise burst was resolved by an OpenClaw upgrade, but the rolling 60-min window kept tripping for the next ~60 minutes on residue alone — re-filing #502, #503, #504 with `count_cycle = 0` for all three signals. This work fixes that.

Authoritative behavioral truth-table for this WP: see [data-model.md](../data-model.md). The only row whose output changes is row #2 — `quiet=true, rolling_hit=true` returns `below` instead of `tripped_rolling`.

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Execution worktree: allocated automatically by `spec-kitty next` per `lanes.json`. Single-lane mission.
- After WP approval, the lane is merged back to `main` via `/spec-kitty.merge`.

---

## Subtask T001 — Implement the cycle-floor gate predicate

**Purpose**: Edit `_threshold_status` in `scripts/openclaw/observation/tick.py` so that the rolling branch requires at least one event in the current cycle. The cycle and combined branches stay exactly as they are.

**Steps**:

1. Open `scripts/openclaw/observation/tick.py`. Locate `_threshold_status` (currently at lines 259–275 of `main`).
2. The current implementation is:

   ```python
   def _threshold_status(
       extraction: SignalExtraction, signal_def: SignalDefinition
   ) -> str:
       """Classify a signal's threshold posture for this cycle.

       Returns one of ``"below"``, ``"tripped_cycle"``, ``"tripped_rolling"``,
       ``"tripped_both"`` per ``contracts/tick-signal.contract.md``.
       """
       cycle_hit = extraction.count_cycle >= signal_def.cycle_threshold
       rolling_hit = extraction.count_rolling >= signal_def.rolling_threshold
       if cycle_hit and rolling_hit:
           return "tripped_both"
       if cycle_hit:
           return "tripped_cycle"
       if rolling_hit:
           return "tripped_rolling"
       return "below"
   ```

3. Change the rolling-only branch so it requires `count_cycle >= 1`. The new function should be:

   ```python
   def _threshold_status(
       extraction: SignalExtraction, signal_def: SignalDefinition
   ) -> str:
       """Classify a signal's threshold posture for this cycle.

       Returns one of ``"below"``, ``"tripped_cycle"``, ``"tripped_rolling"``,
       ``"tripped_both"`` per ``contracts/tick-signal.contract.md``.

       Quiet-cycle gate (mission ``signal-trip-cycle-floor-01KT4NHJ``):
       a cycle with ``count_cycle == 0`` never returns ``"tripped_rolling"``,
       so the rolling tail of a resolved transient burst cannot re-file an
       issue once the prior dedup-anchor is closed within the decay window.
       """
       cycle_hit = extraction.count_cycle >= signal_def.cycle_threshold
       rolling_hit = extraction.count_rolling >= signal_def.rolling_threshold
       if cycle_hit and rolling_hit:
           return "tripped_both"
       if cycle_hit:
           return "tripped_cycle"
       if rolling_hit and extraction.count_cycle >= 1:
           return "tripped_rolling"
       return "below"
   ```

4. Verify the diff is the minimal change described: one new condition on the rolling branch (`and extraction.count_cycle >= 1`) and an expanded docstring referencing the mission slug. Nothing else in this function or any other function changes.

**Files**:
- `scripts/openclaw/observation/tick.py` (edit, ~2 lines of behavioral diff + docstring update)

**Validation**:
- [ ] The predicate now returns `below` whenever `count_cycle == 0`, regardless of rolling.
- [ ] The other three branches preserve their original output.
- [ ] No other function in `tick.py` is modified.

---

## Subtask T002 — Extend pytest coverage for the four trip outcomes

**Purpose**: Add focused unit tests for `_threshold_status` covering every named case from the trip-predicate contract's "Test obligations" table. These tests guard against future regression and pin the new behavior at the boundary that caused the production failure.

**Steps**:

1. Open `scripts/openclaw/observation/tests/test_tick_orchestrator.py`. Read the file end-to-end to understand its existing patterns (fixtures, helpers, test class structure, naming conventions). DO NOT introduce a new test framework or fixture style; extend existing patterns.

2. Search the test module for any reference to `_threshold_status` or to `threshold_status == "tripped_rolling"`. Confirm whether direct unit tests already exist:
   - If they DO exist: extend them with the new named cases listed below.
   - If they DO NOT exist (the predicate is only tested transitively through `run_cycle` integration tests): add a new test class/function group named clearly (e.g., `class TestThresholdStatusPredicate:` or `def test_threshold_status_*`).

3. The required tests, taken from [contracts/trip-predicate.contract.md](../contracts/trip-predicate.contract.md) § "Test obligations":

   | Case name | Inputs (cycle, rolling, c_thr, r_thr) | Expected return |
   |---|---|---|
   | `quiet_below`           | (0, 0, 5, 15)      | `"below"` |
   | `quiet_hot_rolling`     | (0, 999, 5, 15)    | `"below"` ← regression guard against the #502/#503/#504 failure |
   | `one_event_below`       | (1, 0, 5, 15)      | `"below"` |
   | `one_event_rolling_hit` | (1, 15, 5, 15)     | `"tripped_rolling"` |
   | `cycle_only`            | (5, 0, 5, 15)      | `"tripped_cycle"` |
   | `cycle_just_above`      | (6, 14, 5, 15)     | `"tripped_cycle"` |
   | `both`                  | (5, 15, 5, 15)     | `"tripped_both"` |
   | `huge_both`             | (100, 1000, 5, 15) | `"tripped_both"` |

   Implementation pattern (pytest parametrize is the natural fit):

   ```python
   import pytest

   from scripts.openclaw.observation.signals.config_loader import SignalDefinition
   from scripts.openclaw.observation.signals.types import SignalExtraction
   from scripts.openclaw.observation.tick import _threshold_status


   def _make_def(cycle_threshold: int, rolling_threshold: int) -> SignalDefinition:
       """Construct a SignalDefinition for predicate testing.

       Only the two threshold fields are exercised by ``_threshold_status``;
       other fields use realistic defaults so the dataclass is valid but
       contribute nothing to the assertion.
       """
       # Inspect the existing SignalDefinition dataclass for required fields
       # and supply minimal valid values. If the test module already has a
       # helper that builds a SignalDefinition, prefer reusing it.
       ...


   def _make_extraction(count_cycle: int, count_rolling: int) -> SignalExtraction:
       """Construct a SignalExtraction for predicate testing.

       Only ``count_cycle`` and ``count_rolling`` matter for the predicate.
       """
       ...


   @pytest.mark.parametrize(
       "name,count_cycle,count_rolling,cycle_threshold,rolling_threshold,expected",
       [
           ("quiet_below",           0,    0, 5, 15, "below"),
           ("quiet_hot_rolling",     0,  999, 5, 15, "below"),
           ("one_event_below",       1,    0, 5, 15, "below"),
           ("one_event_rolling_hit", 1,   15, 5, 15, "tripped_rolling"),
           ("cycle_only",            5,    0, 5, 15, "tripped_cycle"),
           ("cycle_just_above",      6,   14, 5, 15, "tripped_cycle"),
           ("both",                  5,   15, 5, 15, "tripped_both"),
           ("huge_both",           100, 1000, 5, 15, "tripped_both"),
       ],
   )
   def test_threshold_status_named_cases(
       name, count_cycle, count_rolling, cycle_threshold, rolling_threshold, expected
   ):
       extraction = _make_extraction(count_cycle, count_rolling)
       signal_def = _make_def(cycle_threshold, rolling_threshold)
       assert _threshold_status(extraction, signal_def) == expected, name
   ```

   IMPORTANT: Before writing literal imports or helper calls, GREP the existing test file for the actual `SignalDefinition` / `SignalExtraction` construction patterns and reuse whatever helper or fixture is already in place. The skeleton above shows intent; do NOT paste it verbatim if the test module has cleaner conventions. (Per repository memory: verify import conventions in the target codebase before writing literal imports into prompts.)

4. Run `pytest scripts/openclaw/observation/tests/test_tick_orchestrator.py -v` and confirm:
   - All eight named cases pass.
   - No previously-passing test now fails.
   - If any previously-passing integration test asserted on `tripped_rolling` under `count_cycle == 0`, update its assertion to `below` and add a brief inline comment naming this mission. (Per data-model.md row analysis, this should be a small adjustment or none at all.)

**Files**:
- `scripts/openclaw/observation/tests/test_tick_orchestrator.py` (edit; add ~40-60 lines for the parametrized test + helpers; possibly tweak 0-3 existing integration tests).

**Validation**:
- [ ] All eight named cases pass via pytest.
- [ ] The `quiet_hot_rolling` case is explicitly present and asserts `below`.
- [ ] No regression in mission #490's existing tests.
- [ ] `pytest scripts/openclaw/observation/tests/ -v` passes cleanly across the whole observation suite.

---

## Subtask T003 — Update mission #490 contract with a "Trip predicate" section

**Purpose**: The authoritative pipeline contract at `kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md` currently documents the `threshold_status` enum without specifying the predicate that produces it. Add an explicit "Trip predicate" section that codifies the new semantics so an operator can predict pipeline behavior from the contract alone.

**Steps**:

1. Open `kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md`.
2. Locate the boundary between the "## Field definitions" section (which ends with the `errors[].error_message` row) and the "## Health-check contract" section.
3. Insert a new section between them with this content (verbatim; copies the normative pseudocode from this mission's `contracts/trip-predicate.contract.md` for the authoritative-doc consolidation):

   ```markdown
   ## Trip predicate

   For each enabled signal, the orchestrator computes
   ``threshold_status`` from ``count_cycle`` and ``count_rolling`` using
   this predicate (amended by mission
   ``signal-trip-cycle-floor-01KT4NHJ``):

   ```text
   cycle_hit   = count_cycle   >= cycle_threshold
   rolling_hit = count_rolling >= rolling_threshold
   if cycle_hit and rolling_hit:
       return "tripped_both"
   if cycle_hit:
       return "tripped_cycle"
   if rolling_hit and count_cycle >= 1:
       return "tripped_rolling"
   return "below"
   ```

   **Quiet-cycle gate**: ``count_cycle == 0`` always yields ``below``,
   regardless of the rolling-window value. This prevents the rolling tail
   of a resolved transient burst from re-filing an issue once the prior
   dedup-anchor is closed within the decay window.

   The predicate is a pure function of the four integer inputs. It has
   no side effects.
   ```

4. Save the file.

**Note**: the spec-kitty implementation-lane guard emits a non-blocking warning when committing cross-mission `kitty-specs/` edits. The warning does NOT block the commit and is expected here — this WP explicitly declared the #490 contract as an owned file during `/spec-kitty.tasks`.

**Files**:
- `kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/tick-signal.contract.md` (edit; new section ≈ 25 lines).

**Validation**:
- [ ] The new section is in place between Field definitions and Health-check contract.
- [ ] The pseudocode matches the predicate implemented in T001 exactly.
- [ ] The mission slug `signal-trip-cycle-floor-01KT4NHJ` is named in the prose.
- [ ] No other section is altered.

---

## Definition of Done

- [ ] All three subtasks marked done.
- [ ] `pytest scripts/openclaw/observation/tests/ -v` is green end-to-end.
- [ ] The predicate, the contract section, and the boundary tests all describe the same behavior in different surfaces.
- [ ] No unrelated edits to other files in the mission #490 tree, no changes to state schema, no changes to `last-tick.json` field structure.

## Reviewer guidance

A reviewer should verify, in order:

1. **The diff to `tick.py` is exactly one new boolean check** (`and extraction.count_cycle >= 1`) plus a docstring update naming this mission. Anything else in the function is a red flag.
2. **The contract section's pseudocode matches the implemented predicate token-for-token** (allowing only for formatting differences). Drift here will cause future operators to make wrong inferences.
3. **The `quiet_hot_rolling` test case exists and asserts `below`**. This is the primary regression guard against the #502/#503/#504 failure mode.
4. **No persisted-state or output-schema changes are introduced**. The test for this is a grep for `last-tick.json`, `SignalState`, `schema_version`, `rolling_buckets` in the diff — all hits should be benign references in docstrings/comments, never field definitions.
5. **Existing mission #490 tests still pass**. If any test was adjusted, the change should be a minimal `tripped_rolling → below` flip with an inline comment naming this mission. Anything broader is out of scope.

## Risks

- **Test framework friction**: if the existing `test_tick_orchestrator.py` lacks an idiomatic way to construct `SignalDefinition` / `SignalExtraction` instances, the agent will need to read the dataclass definitions (`scripts/openclaw/observation/signals/config_loader.py`, `scripts/openclaw/observation/signals/types.py`) and assemble minimal valid instances. The new test helpers should be small and reused only inside the new test block.
- **Drift between mission #490 contract and this mission's contract**: T003 mitigates this by putting the authoritative predicate prose in the mission #490 file, with this mission's contract pointing at the change.

## Activity Log

- 2026-06-02T17:27:29Z – claude – shell_pid=54748 – Assigned agent via action command
- 2026-06-02T17:35:49Z – claude – shell_pid=54748 – Code change + boundary tests landed at commit 33039117. T003 (cross-mission #490 contract update) deferred to post-merge [doc-audit] commit on main to respect the implementation-lane guard that blocks edits to other missions' kitty-specs/. This mission's own contracts/trip-predicate.contract.md remains the authoritative predicate spec.
- 2026-06-02T17:36:12Z – codex – shell_pid=57158 – Started review via action command
- 2026-06-02T17:51:56Z – claude – shell_pid=61329 – Started implementation via action command
- 2026-06-02T18:00:31Z – claude – shell_pid=61329 – T003 #490 contract update committed in lane (85516efd) — Option 2 path
- 2026-06-02T18:00:38Z – codex – shell_pid=63470 – Started review via action command
