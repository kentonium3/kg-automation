---
work_package_id: WP03
title: Graph-store series and run-level report
dependencies:
- WP02
requirement_refs:
- FR-005
- FR-006
- FR-007
- FR-012
- NFR-004
planning_base_branch: feat/849-preconditions
merge_target_branch: feat/849-preconditions
branch_strategy: Planning artifacts for this mission were generated on feat/849-preconditions. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-preconditions unless the human explicitly redirects the landing branch.
subtasks:
- T013
- T014
- T015
- T016
phase: Phase 3 - Measurement
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/sampler.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/research/arms849/sampler.py
- scripts/research/arms849/substrate.py
- tests/research/test_arms849_sampler.py
- tests/research/test_arms849_substrate.py
- scripts/research/arms849/ledger.py
- scripts/research/arms849/grading.py
role: implementer
tracker_refs: []
tags: []
---

# Work Package Prompt: WP03 — Graph-store series and run-level report

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load` (the profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/849-preconditions`
- **Final merge target**: `feat/849-preconditions`
- `/spec-kitty.implement` populates the actual worktree `base_branch` from `lanes.json`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Measure the graph store's memory as rubric §5 now registers it (third correction @`91e679e6`). This is a RUN-LEVEL container footprint, never a per-question or per-cell cost. It is sampled across the whole run by an OBSERVATIONAL host-side writer, one never-truncated series per substrate generation, and reported as `baseline_mib`, `peak_mib` and `all_resident_mib`, with an honest `could_not_check: <reason>` whenever a figure cannot be established. **No cell is ever affected by this measure.**

**Read first:**
- `contracts/memory-series.md` (every item; item 4 is the report's exact rules);
- `data-model.md` § Memory series files, § Graph-store report, and the `series_generation`/`graph_store_*` event rows;
- `research.md` D-5, D-6, D-7a (including the **deliberately avoided machinery**: do NOT build per-question windows, attempt-level boundary events, a historical-window evaluator, or a windowed `memory_support`);
- the existing `sampler.py` (`RssSeriesWriter` ~L381, `"w"` open ~L420, `RssSeriesSampler` ~L480, `_parse_ts` ~L276) and `substrate.py` (`_runner_argv`/`_runner_cmd` ~L495–521, `run` ~L672).

## Subtasks

### T013 — Host cgroup reader and generation series file (FR-005, C-009)
- The reader reads `/sys/fs/cgroup/system.slice/docker-<full-id>.scope/memory.current`, converts bytes to MiB, and resolves the container id once via `docker inspect`. Make the cgroup root injectable for tests. Never read via `docker stats`, and never record under an RSS name.
- The writer targets a 1.0 s interval and records the REAL interval.
- The file is `RUNS_DIR/falkordb-cgroup-<series_id>.jsonl`, created EXCLUSIVELY (`"x"`): never truncated and never reused. A pre-existing path is a writer failure, not an overwrite.
- Records follow data-model.md:
  - header `{series: "arms849-falkordb-cgroup/1", series_id, started, container, container_id, interval_s}`;
  - records `{ts, cgroup_mib, container_id}`;
  - a trailer `{closed, readings, failures}` written only on a clean stop.
  - A failed read writes no line.
- Names say cgroup, not RSS. The harness still uses the old RSS classes until WP04 removes that path, so leave them in place, and note in the review artifact that WP04 deletes them (no vestiges).

### T014 — `substrate.run()` owns the writer (research D-6)
- For a harness run only (not self-test or gate phases), `run()`:
  1. resolves the FalkorDB container id;
  2. mints a `series_id`;
  3. starts the writer thread before the runner subprocess;
  4. passes the generation descriptor to the runner via `env_extra`, as environment variables whose names you document for WP04. The descriptor carries `series_id`, `path` (as seen INSIDE the runner, under `/runs`), `container_id`, `interval_s`, `started_ts`, `writer_status` and `writer_reason`;
  5. stops the writer in `finally`.
- **Observational:** if the id cannot be resolved or the writer cannot start, the runner STILL launches. The descriptor carries `writer_status: "failed"` plus a reason, with nullable unresolved fields (data-model, review #6 fold). Nothing is blocked or refused.
- There is no compose change.

### T015 — The run-level report (FR-006, FR-007; contracts/memory-series.md item 4)
- Write a pure function over the ledger's events and the series files, for example `graph_store_report(events, runs_dir) -> dict`. It returns `{baseline_mib, peak_mib, all_resident_mib, marginal_per_graph_mib, interval_s, series_ids, source_series_ids}`, where each figure is a number or `"could_not_check: <reason>"` and `source_series_ids` records the ordered generation provenance of every scalar. Implement the EXACT rules of item 4, including its 2026-09-28 resumed-generation selector amendment:
  - **baseline:** requires `graph_store_first_build.graphs_present == false`. It is the latest reading at or before that `ts`, no staler than 5 intervals.
  - **all_resident:** exists only via `graph_store_all_resident`. It is the FIRST reading STRICTLY AFTER its `ts`, within 5 intervals. Otherwise `could_not_check: not_all_resident_in_one_process`.
  - **peak:** the max over every generation whose header matches its `series_generation` descriptor and which has:
    - a clean trailer;
    - first and last readings within 5 intervals of the generation's own start and close;
    - no internal gap over 5 intervals.
    Coverage is judged against the generation's own bounds, NEVER against export time. If any generation fails, the result is `could_not_check: coverage`.
  - **marginal:** `(all_resident − baseline)/8`, only when both come from the SAME generation.
  - **resume selector:** baseline uses the first generation in ledger order; all-resident uses the first schema-valid all-resident event and never skips a CTC result for a later number; interval is numeric only when every running generation agrees; every scalar records its source generation IDs.
  - A `writer_status: "failed"` generation yields `could_not_check: writer_failed` for the figures depending on it.
- Validate the report when produced. It is never persisted, never a score, and never a completeness condition.
- **Coupled wiring (declared in `owned_files`; record it):**
  - `Ledger.summarise()`'s caller-facing summary and `grading.export`'s admin output include the report;
  - an unreadable series never raises into cells or blocks export (the premise and completeness refusals from WP01 still apply).
  - Keep the edits minimal, and record them.

### T016 — C12 and freshness boundaries (FR-012, NFR-004)
- Series and sampler timestamps are accepted ONLY in canonical UTC isoformat, exactly what the writer emits. Offsets other than `+00:00`, naive stamps, `Z` variants (if the writer does not emit them) and non-canonical precision are all rejected.
- Boundary tests at exactly 5 intervals (allowed) and just over 5 (`could_not_check`), for staleness, gaps and trailing coverage.

## Tests (red-first, NFR-002)

- **End to end (SC-002):** drive a synthetic series through the REAL writer (against a fake cgroup root), then the real reader and report. The report carries all three figures from real samples.
- **The 4 unavailable conditions:** absent, stale, gapped and wrong container. Each yields `could_not_check` with its reason.
- **Further cases:**
  - a header/descriptor mismatch;
  - no trailer;
  - `graphs_present: true`;
  - a reading held from before the last build (it must not count as all-resident);
  - a resumed generation without its own `all_resident` event;
  - a pre-existing series path (the writer fails, and the runner still launches in the `substrate.run` test with a fake `docker`).

## Definition of Done

- T013–T016 are done, and red-first evidence is recorded.
- The full suite passes on office4 under both seeds, and CI collection survives.
- The env variable names for WP04 are documented in the review artifact and in the `substrate.run` docstring.
- The coupled wiring edits are listed.
- **No dead code (charter, mandatory before `for_review`):** grep for the live callers of every new or changed public symbol, and list each symbol's production caller in the review artifact. Symbols whose caller lands in a later WP name that WP. This WP: the cgroup writer (reached from `substrate.run`), `graph_store_report` (reached from summary/export).

## Risks / reviewer guidance

- **Properties to verify:**
  - no failure of the writer or reader can refuse, block or alter a cell;
  - no figure is ever a zero, a guess, or taken from a reading that predates its boundary;
  - series files are never truncated or reused;
  - a partial generation can never yield a numeric peak.
