---
work_package_id: WP01
title: Ledger, grading and isolation inventory
dependencies: []
requirement_refs:
- FR-006
- FR-007
- FR-008
- FR-010
- FR-011
- NFR-005
planning_base_branch: feat/849-preconditions
merge_target_branch: feat/849-preconditions
branch_strategy: Planning artifacts for this mission were generated on feat/849-preconditions. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-preconditions unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1 - Foundations
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/ledger.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/research/arms849/ledger.py
- scripts/research/arms849/grading.py
- scripts/research/arms849/gates.py
- tests/research/test_arms849_ledger.py
- tests/research/test_arms849_grading.py
- tests/research/test_arms849_gates.py
- tests/research/test_arms849_isolation.py
- scripts/research/run_849_harness.py
role: implementer
tracker_refs: []
tags: []
---

# Work Package Prompt: WP01 — Ledger, grading and isolation inventory

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load` (the profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/849-preconditions`
- **Final merge target**: `feat/849-preconditions`
- `/spec-kitty.implement` populates the actual worktree `base_branch` from `lanes.json`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Give the ledger the words the later WPs need: two new terminal outcomes, the halt and stop events, the attempt's session id, the graph-store boundary events, the refusal of any per-cell graph-store column, and the smoke ledger identity. Also make the isolation inventory complete.

This WP writes NO harness behaviour, except the two recorded coupling edits named below.

**Read first:**
- `contracts/ledger-deltas.md` (every item is implemented here) and `data-model.md` (all of it);
- `research.md` D-7a and D-8;
- `contracts/memory-series.md` item 3 and item 4 (the event shapes only; the report itself is WP03);
- rubric §5 and §10 in `docs/design/research/` at HEAD (C4, C9, C11, C12, C13);
- the existing `ledger.py` (OUTCOMES ~L85, SCORED_ARM_FIELDS ~L76, `pending_keys` ~L603, `summarise` ~L648, replay ~L754), `grading.is_complete`/`export`, and `gates.REQUIRED_MODULES` (~L62).

## Subtasks

### T001 — Outcomes `exceeds_memory_ceiling` and `sampler_unreadable_at_send`
- Add both to `OUTCOMES`, validated identically on write and replay.
  - `exceeds_memory_ceiling` REQUIRES `memory_ceiling: {measured_gib: float, ceiling_gib: float, stage: "before_send"}`.
  - `sampler_unreadable_at_send` must NOT carry `memory_ceiling`. The two are never interchangeable.
- Both are terminal for the attempt, never scored, and never in any average or `Summary` statistic.
- `exceeds_memory_ceiling` is TERMINAL FOR THE CELL across sessions: `pending_keys` never returns a key that holds one, whether in this session or a reopened one (rubric §5 @`a00abc03`).
- A ledger containing either outcome on an un-scored cell cannot be primary-complete: extend `grading.is_complete` and the harness-facing completeness predicate that lives in ledger/grading.
- The pre-attempt `sampler_unreadable` event is unchanged.

### T002 — Events `premise_violated` and `session_stopped`
- `premise_violated{arm, reason: "tripwire"|"cross_group_leak", message, at_key}`.
- `session_stopped{reason, grace_s?}`. `reason` is one of `g_cancellation_unacknowledged`, `ceiling_breach_at_send`, `premise_violated`, `operator`, plus any existing stop reasons, and every reason is distinguishable. `grace_s` is required for `g_cancellation_unacknowledged`.
- Both are validated on write and replay.
- Correction C: a ledger containing `premise_violated` is refused
  - by the completeness predicate used for primaries;
  - by `grading.export` (`ExportRefused`);
  - AND by `Ledger.summarise()` (raise; never average).
  Rows stay untouched.
- Tests: a violation arriving on repeat 2 after scored rows, checked both immediately and after replay.

### T003 — `attempt_start.session_id`
- The field is required and must be a non-empty str.
- Replay requires that the most recent `session_gates` event above the attempt has the same `session_id`, `passed: true` and `skipped: false`. Skipped is allowed only under a `SKIP_GATES_SHA` header (ledger-deltas item 4).
- Check what `session_gates` records today. If it has no session id, add one there as well, in the same validation.
- **Coupled edit (declared in `owned_files`; record it in the review artifact):** the harness's `begin_attempt` call site in `scripts/research/run_849_harness.py` passes the session's id (one or two lines). Record the rationale ("suite must stay green; field is required") in the review artifact.

### T004 — Graph-store boundary events; no per-cell graph-store column
- Validate on write and replay, with canonical UTC timestamps and a known `series_id` (declared by an earlier `series_generation`):
  - `series_generation{series_id, path, container_id, interval_s, started_ts, writer_status, writer_reason?}`. The nullability rules are in data-model.md (review #6 fold).
  - `graph_store_first_build{ts, series_id, graphs_present}`.
  - `graph_store_all_resident{ts, series_id, n_graphs: 8}`, at most once per `series_id`.
- Retire `falkordb_rss_peak_mib`: remove it from `SCORED_ARM_FIELDS["G"]`. Refuse any per-cell row carrying a graph-store column, on write AND replay. Define the refused set as a named constant, including `falkordb_rss_peak_mib`, `falkordb_cgroup_peak_mib` and any `falkordb_*`/`graph_store_*` key, rather than as a single name.
- **Coupled edit (declared in `owned_files`; record it in the review artifact):** the harness's G row stops attaching `falkordb_rss_peak_mib` (`_record_ok` ~L655 and the required-column check). WP04 removes the rest of that sampler path. Keep this edit minimal and record it.
- `grep -rn falkordb_rss` afterwards. Every remaining hit must be in `run_849_harness.py`'s sampler path (WP04's job) or in dated history. Name them in the review artifact.

### T005 — Smoke ledger identity
- Header plan identity `SMOKE_PLAN`: a distinct integer constant for 10 cells, immutable like every header field. Its serving binding is the PRIMARY configuration (data-model § Smoke ledger identity).
- The completeness/primary predicate refuses it, and `grading.export` refuses it.
- Expose a predicate (for example `is_smoke(header)`) that WP04's `status`/`open_existing` will use.

### T006 — C4 isolation inventory (FR-010)
- `gates.REQUIRED_MODULES` names EVERY module of `scripts/research/arms849/` (17 today; SC-005).
- Add a two-way test:
  - every `.py` in the package (excluding `__init__` only if the gate itself excludes it; state which) is in the tuple;
  - every name in the tuple exists.
- This test is what makes correction A enforceable. It must fail today if the tuple is truncated.

## Tests (red-first, NFR-002)

For each FR above, at least one test is shown FAILING on the pre-change code; record the failing output in the review artifact. Cover:
- write and replay symmetry for every new field and event;
- a torn tail after each new record kind;
- the injected-defect cases:
  - a breach row without `memory_ceiling`;
  - an unreadable-at-send row WITH one;
  - an attempt whose `session_id` names another session;
  - an `all_resident` event for an unknown `series_id`;
  - a G row carrying `falkordb_cgroup_peak_mib`;
  - a smoke ledger passed to export.

## Definition of Done

- T001–T006 are implemented, and the tests are red-first with the evidence recorded.
- The full suite passes on office4 under `PYTHONHASHSEED=0` and `3`, with `ARMS849_CACHE=/home/kgale/repos/kg-automation/build/849-cache`.
- CI collection survives without `graphiti_core`.
- Both coupled harness edits are listed with their rationale.
- Correction A: if you add a module, `REQUIRED_MODULES` is updated in the same commit.

## Risks / reviewer guidance

- **Property to verify:** no path records an unmeasurable, refused, breached or premise-tainted cell as a score, a zero or a pass (NFR-005). Replay accepts exactly what live write accepts.
- `summarise()` must refuse, not skip, on `premise_violated`.
