# Contract: graph-store memory series (C9)

1. **Measure**: the FalkorDB container's cgroup memory charge. It is read directly from `/sys/fs/cgroup/system.slice/docker-<full-id>.scope/memory.current` (cgroup v2, systemd driver) and includes page cache. It is recorded as `falkordb_cgroup_peak_mib` (rubric §5 @`ea3fbfc8`). It is never read via `docker stats`, and never recorded under an RSS name.
2. **Writer**: runs on the host inside `substrate.run()` for a harness run only. It starts before the runner, waits (bounded) for its first reading, and fails closed with a named error if none arrives. It is stopped in `finally`. The container id is resolved by `docker inspect` once.
3. **Interval**: the real interval is written in the series header and carried to the run record. Every freshness tolerance is a multiple of that recorded interval (stale > 5 intervals, gap > 5 intervals, where exactly 5 is allowed).
4. **Handoff**: the runner receives the series path and the expected container id through the environment. The harness refuses to bind the G sampler if either is absent.
5. **Reader**: the existing sample-and-hold reader (rubric §5 window reconstruction), unchanged in semantics. `require_breached` holds for every bound sampler.
7. **Per-question record (§5 @`a00abc03`)**: the figure is recorded once per question over [build start .. last graph query], as a container high-water mark that is NOT attributable to the question. The run also records the baseline and the all-resident total. Per-cell rows carry no graph-store column.
6. **Fail closed**: an absent, stale, gapped or wrong-container series means the cell is not started (`sampler_unreadable`). It is never a zero, never a pass.
