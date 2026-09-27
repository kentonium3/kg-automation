---
work_package_id: WP04
title: Harness integration
dependencies:
- WP03
requirement_refs:
- FR-001
- FR-002
- FR-004
- FR-005
- FR-008
- FR-013
- NFR-003
- NFR-005
planning_base_branch: feat/849-preconditions
merge_target_branch: feat/849-preconditions
branch_strategy: Planning artifacts for this mission were generated on feat/849-preconditions. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-preconditions unless the human explicitly redirects the landing branch.
subtasks:
- T017
- T018
- T019
- T020
- T021
- T022
- T023
- T024
phase: Phase 4 - Integration
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/run_849_harness.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/research/run_849_harness.py
- tests/research/test_run_849_harness.py
- tests/research/test_arms849_integration.py
- scripts/research/arms849/sampler.py
- tests/research/test_arms849_sampler.py
role: implementer
tracker_refs: []
tags: []
---

# Work Package Prompt: WP04 — Harness integration

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load` (the profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/849-preconditions`
- **Final merge target**: `feat/849-preconditions`
- `/spec-kitty.implement` populates the actual worktree `base_branch` from `lanes.json`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Wire WP01–WP03 into the harness so a live session:
- registers G, D and R (C13);
- halts on a broken premise and stops on an unacknowledged G cancellation;
- emits the run-level graph-store events and no per-cell graph-store figure (C9);
- checks the ceiling at send (C11);
- offers `--smoke` and the T039 `--measure` tool.

**Read first:**
- `contracts/arm-registration.md`, `contracts/before-send.md`, `contracts/memory-series.md` items 3, 4 and 7;
- `research.md` D-1, D-2 (especially the `_call_with_timeout` propagation paragraph), D-3, D-7a, D-9;
- `data-model.md` (Smoke ledger identity; State transitions);
- `quickstart.md`;
- the WP01–WP03 review artifacts: the env variable names from WP03, the `is_smoke` predicate from WP01, and the bridge API from WP02;
- `run_849_harness.py` in full: `ArmRegistration` ~L273, `Resources` ~L311, `Runtime` ~L383, `Session` ~L414–680, `_call_with_timeout` ~L680–712, `run_session` ~L729, `live_runtime` ~L1235, `live_secondary_gate` ~L1276, `main` ~L1405.

## Subtasks

### T017 — Registration (FR-001, FR-004; C13)
- `ARM_FACTORIES` maps exactly `{"G","D","R"}` to factories taking `Resources`. Each factory imports its arm module INSIDE the factory: importing the harness must never import `graphiti_core` (add a test that imports the harness with a `graphiti_core` stub raising `ModuleNotFoundError`). The shapes:
  - D is `bind(text)`;
  - R is `bind=lambda cache: arm_r.bind(text, cache)` plus `calibration_inputs`;
  - G is WP02's bridge (`answer`, `build_graph`, `drop_graph`, `close`, graph listing).
- `live_runtime` builds ONE `embed.Embedder(<cache>/fastembed)` and sets it on BOTH `Resources.embedder` and `Runtime.embedder`.
- `run_session` wraps the session in `try/finally` that calls every registration's `close()`. This covers completion, `--limit`, `stop()`, exceptions and `KeyboardInterrupt`.
- **Red-first test (C13's evidence):** the live registration test. `live_runtime` exposes G, D and R with the shared refusal class and a non-None embedder. It fails on the pre-change code. Give it a stable node ID for WP05's required list.
- **Condition A (FR-004):** a session with `ARM_FACTORIES == {}` records every cell `not_implemented`, and the ledger is refused by `require_complete_primary` AND by the export. This is a REGRESSION guard; it is green before and after the change, which is expected (NFR-002 exemption).

### T018 — `_call_with_timeout` grace path (research D-2 propagation)
- After the grace wait, (a) re-raise a non-`Exception` `BaseException` exactly as on the normal path, AND (b) return a worker exception as `("raised", exc)`, never `("timeout", None)`. Then `PremiseViolated`, `CeilingBreached`, `CeilingUnreadable` and `ArmRefusal` are classified exactly as on the normal path.
- **Race tests:** a breach, an unreadable-at-send and a premise violation, each raised DURING the grace wait. Each must be classified, never turned into a retryable timeout. These fail on the pre-change code.

### T019 — Halts and stops (FR-002; NFR-003)
- `CellContext` gains a read-only `deadline` (the Session already computes it).
- `PremiseViolated` works like `CalibrationPopulationIncomplete`: record `premise_violated{arm, reason, message, at_key}`, record `session_stopped{reason: "premise_violated"}`, then stop the run.
- `GCancellationUnacknowledged` passes through `_one_attempt` and `_drop_graph` (which catches `Exception` only). The Session records `session_stopped{reason: "g_cancellation_unacknowledged", grace_s}`, issues NO further retrieval, drop or cleanup query, and the process exits non-zero. Resume is a fresh process.
- The existing "zombie" path keeps its behaviour.

### T020 — Graph-store events; remove the per-attempt path (FR-005; memory-series item 7)
- REMOVE the per-attempt graph-store sampler path: the sampler entry ~L543, the column plumbing ~L551, `_record_ok` ~L655 and the refusal when that sampler is unreadable ~L555.
- Delete the now-dead RSS classes in `sampler.py` and their tests. This is a **coupled edit** (declared in `owned_files`), per the no-vestiges rule; WP03 left them for you. Afterwards `grep -rn "falkordb_rss\|RssS"` must show no live code.
- At session start, if the WP03 env descriptor is present, record `series_generation` from it before any graph activity. If the descriptor is absent (the self-test, or a non-substrate run), record nothing; the report says `could_not_check`.
- Before the FIRST `build_graph` of the generation, list FalkorDB graphs read-only via the bridge. ALWAYS record `graph_store_first_build{ts, series_id, graphs_present}`.
- After THIS process's eighth successful build in this generation, and before any harness retirement, record `graph_store_all_resident{ts, series_id, n_graphs: 8}` once, with `ts` taken after the eighth build succeeds. Harness retirement (the drop after repeat 3) is distinct from `build_graph`'s own pre-build clear.
- A graph-store failure never refuses or affects a cell.

### T021 — Ceiling guard at send (FR-008; SC-003)
- The Session supplies `before_send` as a closure over the cell's GTT sampler:
  - a reading strictly above the ceiling raises `CeilingBreached(measured, ceiling)`;
  - a failed read raises `CeilingUnreadable`.
- `ServingFacade.complete` REFUSES to send without a `before_send`.
- Outcome mapping:
  - **breach:** record `exceeds_memory_ceiling` with `memory_ceiling{measured_gib, ceiling_gib, stage: "before_send"}`, then `session_stopped{reason: "ceiling_breach_at_send"}`, then STOP via its OWN signal (never the window `breached` flag). The cell is terminal and never retried.
  - **unreadable at send:** record `sampler_unreadable_at_send`. The cell is refused, and the session CONTINUES.
- `live_secondary_gate`'s probe uses the same callback.
- Update the test facade fakes (about 100 sites). Prefer a shared helper over 100 hand edits.
- Test that zero bytes are sent on a breach, with a fake transport counting sends.

### T022 — `--smoke` (quickstart; data-model § Smoke ledger identity)
- `plan("smoke")` produces, in order: G r1 ×8, then calibration, then D C1 r1, then R C1 r1. Use WP01's `SMOKE_PLAN` header identity with the PRIMARY serving binding.
- `status` reports a smoke ledger as `smoke`, and `open_existing` reopens it only as smoke.
- A smoke ledger is never primary.

### T023 — `--measure` (FR-013; T039 is a freeze GATE, correction D)
- On the current commit, compute all 8 exact serialised requests, including block tokens and token-level prefix sharing.
- VERIFY that the set of questions exceeding the native context equals the REGISTERED six (rubric §2). If not, fail with a NAMED error and produce no table.
- Bind the output to the commit SHA and `preflight_sha`.
- Make `PROCESS_START` injectable (WP05's C8 test needs it).
- The measurement RUN itself is a freeze-time step, not part of this WP. The tool is tested here with fakes, including the mismatch error.

### T024 — NFR-003 soak
- Run 100 consecutive attempts with injected timeouts and cancellations against a fake graph store.
- No NEW attempt may start before the previous one's termination is acknowledged.
- An unacknowledged cancellation stops the session as in T019.
- Keep it fast: patch the grace constant small, and assert the production value.

## Tests (red-first, NFR-002)

- FR-001, FR-002, FR-005 (event emission), FR-008 and FR-013 each have a failing-first test, recorded.
- Condition A is the recorded exemption.
- Run the integration suite end to end with fakes for G, D and R.

## Definition of Done

- T017–T024 are done.
- The full suite passes on office4 under both seeds.
- The fresh-worktree CI simulation passes: `git worktree add --detach`, no `build/`, a stub `graphiti_core` raising `ModuleNotFoundError` on PYTHONPATH, then `pytest -q --ignore=docs/archive`.
- The coupled sampler cleanup is listed.
- The stable node IDs of the live and required tests are listed for WP05.

## Risks / reviewer guidance

- **Properties to verify:**
  - no terminal domain exception can become a retryable timeout on any path;
  - no bytes are sent after a breach;
  - no graph-store failure touches a cell;
  - importing the harness never imports `graphiti_core`;
  - `close()` runs on every exit path;
  - after `g_cancellation_unacknowledged`, no further G query is issued.
