# Contract: graph-store memory series (C9)

This contract governs the run-level measure registered in rubric §5 third correction @`91e679e6` and §10 C9 @`91e679e6`.

1. **Measure**: the FalkorDB container's cgroup memory charge, read directly from `/sys/fs/cgroup/system.slice/docker-<full-id>.scope/memory.current` (cgroup v2, systemd driver). It includes page cache and retained allocator heap, so it is a high-water mark. It is never read via `docker stats`, and never recorded under an RSS name.
2. **Writer**: runs on the host inside `substrate.run()` for a harness run only, at a 1.0 s target interval, and records the REAL interval in the series header. The container id is resolved once (`docker inspect`). **The writer is observational.** If it cannot start or produces no reading, that failure is recorded, and the run proceeds with the graph-store figure `could_not_check`. It never blocks the runner or refuses a cell.
3. **Generations**: each `substrate.run` writes its own series file, `RUNS_DIR/falkordb-cgroup-<series_id>.jsonl`. It is created exclusively and never truncated or reused; the existing writer's `"w"` open at `sampler.py` ~L420 changes accordingly. Its header binds `series_id`, `container_id` and `interval_s`. The harness records a `series_generation` ledger event with those values before any graph activity.
4. **Run-level figures**, computed at summary and export time from the series files and two harness events:
   - `baseline_mib`: the reading held at `graph_store_first_build` (the first `build_graph` start of the run);
   - `peak_mib`: the maximum over the run's series;
   - `all_resident_mib`: the reading held at `graph_store_all_resident`, emitted when the last question's repeat-1 build succeeds while no graph has yet been RETIRED by the harness. The idempotent pre-build clear inside `GraphArm.build_graph` does not count as a retirement.
   - The marginal per-graph figure `(all_resident_mib − baseline_mib) / n_graphs` is derivable.
5. **Freshness**: each figure's reading must be no staler than 5 recorded intervals, and the series must have no gap over 5 intervals around it; exactly 5 is allowed. Otherwise that figure is `could_not_check` with the reason. A figure whose reading comes from a different generation than its boundary event, or from a file whose header container differs from its `series_generation` descriptor, is `could_not_check`.
6. **Two sampler roles, two failure modes.** The ceiling guard's LIVE sampler, unreadable at send, refuses the cell: a safety property (before-send.md). The graph-store figure unavailable is `could_not_check` in the report, and **no cell is ever affected**: it is a reported column, about 0.4 % of the ceiling, outside §7.
7. **No per-cell or per-question graph-store figure exists.** The per-attempt graph-store sampler path in the harness (`run_849_harness.py` ~L543, L551, L655) is REMOVED. Per-cell rows carrying any graph-store column are refused.
