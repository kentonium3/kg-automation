# Research — 849 Arms Run Pre-Run Preconditions

Sources:
- two read-only sizing investigations, 2026-09-26 (all facts cited file:line in the #1023 thread and the implementer's scratchpad);
- the design-lead rulings `20260926T220353449460Z6a87ff79f3`, `20260926T220457953295Zd7af0f572f` and `20260926T222035097212Zd8a3ed1773`;
- rubric §5 @`ea3fbfc8`, §10 @`4bf375ef`;
- a read-only probe on office4 (below).

## D-1 — Arm registration lives in the harness; the arms are imported lazily

- **Decision**: `ARM_FACTORIES` in `run_849_harness.py` maps `G`/`D`/`R` to factories taking `Resources`. Each factory imports its arm module **inside** the factory.
  - **D**: `bind(text)`.
  - **R**: `bind=lambda cache: arm_r.bind(text, cache)` plus `calibration_inputs=lambda views, cache: arm_r.calibration_inputs(text, tok, emb, views, cache)`. This is the shape the Session already calls (`run_849_harness.py` ~L292–293, L456).
  - **G**: the loop bridge (D-2).
  - `live_runtime` builds ONE `embed.Embedder(<cache>/fastembed)` and sets it on BOTH `Resources.embedder` and `Runtime.embedder`. Today `Runtime.embedder` is never set, so `ctx.embedder` is `None`.
- **Rationale**:
  - `arm_g` and `embed` (and so `arm_r`) import `graphiti_core` at module top. Eager imports from the harness would break CI collection, where `graphiti_core` is absent by Kent's ruling.
  - Registration next to `ArmRegistration` keeps one owner.
- **Alternatives**:
  - Arms self-register on import: rejected. It is the false comment the post-merge review caught, and it needs eager imports.
  - A separate `registry.py`: acceptable. If chosen, it goes in `REQUIRED_MODULES` in the same commit (correction A).

## D-2 — G runs behind one persistent event loop; an unacknowledged cancellation stops the session

- **Decision** (design lead: correction B, then 20260926T231025320954Z444929a640, which approved dropping the driver-replacement design):
  - **One loop, one driver.** G's registration owns one asyncio loop on a dedicated thread and one FalkorDB driver bound to it: `FalkorDriver(host="falkordb", port=6379)`, the compose service name, since the harness runs inside the runner container.
  - **Retrieval on the loop, serving off it.** The synchronous `answer` wrapper submits ONLY the retrieval coroutine (`plan_and_assemble`) via `asyncio.run_coroutine_threadsafe`, then runs render / serialize / count / `ctx.serving.complete` on the attempt thread, exactly as D and R do. `GraphArm` gains a synchronous `respond(block, plan, question, ctx)`. Today `answer` makes the serving call synchronously INSIDE the coroutine (`arm_g.py` ~L534), which would block the loop.
  - **Every operation gets a deadline.** `build_graph`, `drop_graph` and retrieval each receive the attempt's deadline and `cancelled` flag. `CellContext` gains a read-only `deadline`, which the Session already computes for `_call_with_timeout`.
  - **Cancellation is acknowledged by the coroutine, or the session stops.**
    - On timeout or cancel, the wrapper cancels the loop-side task.
    - It then waits up to `G_CANCEL_GRACE_S` (a named constant, 10 s) for an acknowledgement from the coroutine's own `finally`/cleanup, a flag it sets. `future.done()` is not used for this: it can report done while the coroutine is still unwinding (post-plan review).
    - If no acknowledgement arrives in time, the G wrapper raises `GCancellationUnacknowledged`, a `BaseException` and NOT an `Exception`, so no ordinary handler can absorb it. **Propagation (post-plan review):**
      - `_call_with_timeout` currently discards the worker's exception after its grace wait and returns a retryable `("timeout", None)` (`run_849_harness.py` ~L702–705). After the grace wait it must (a) re-raise a non-`Exception` `BaseException`, exactly as on the normal path, AND (b) return any exception the worker raised as `("raised", exc)` instead of `("timeout", None)`. Then the terminal DOMAIN exceptions (`PremiseViolated`, `CeilingBreached`, `CeilingUnreadable`, `ArmRefusal`) are classified exactly as on the normal path, never turned into a retryable timeout (post-plan review #4: a probe returned a retryable timeout for late premise-violation and ceiling-breach exceptions). Race tests cover a breach, an unreadable-at-send and a premise violation, each raised during the grace wait.
      - `_drop_graph` catches `Exception` only, so the stop passes through.
      - The Session records `session_stopped{reason: "g_cancellation_unacknowledged", grace_s}`, issues NO further retrieval, drop or cleanup query, and the process exits.
      - The existing "zombie" path (a worker that never exits) keeps stopping the session as it does today.
    - **Hybrid search must use the per-question driver** (post-plan review #4). `Graphiti.clients` is bound to the ORIGINAL driver (`arm_g.py` ~L315), and the `@handle_multiple_group_ids` decorator re-clones whenever that driver's database differs from the group, even overriding an explicitly passed driver (installed `decorators.py` ~L60–68). So G builds ONE `Graphiti` instance PER QUESTION, bound to that question's cached per-question driver. The decorator's `gid == driver._database` branch then applies and no further clone is created. Tests assert the clone count and task quiescence.
    - **Quiescence includes G's own background tasks.** `FalkorDriver.__init__` schedules a detached `_init_task` (index build) on the running loop, and every `clone()` constructs a new driver (installed `falkordb_driver.py` ~L178–182, L331–342). The per-question clone is created ONCE and cached per question, and its `_init_task` is AWAITED before first use, so index readiness per database is owned. The cancellation acknowledgement is given only when every task the G bridge started for that question is done. `GraphArm`'s single global `_indices_built` flag becomes per-database.
    - Resume runs in a FRESH process. All G state (graphs, UUID maps, `graph_stats`) is reconstructible from the frozen corpus, so nothing stale survives.
  - **No driver replacement exists.** Replacing the driver would leave stale references in `Graphiti.clients`, in `GraphArm`'s UUID maps and in `Session.graph_stats`.
  - **Unconditional cleanup.** `run_session` wraps the whole session in `try/finally: runtime.close()`: completion, `--limit`, `stop()`, exceptions and `KeyboardInterrupt`. `close()` applies the same bounded grace, then abandons the loop thread.
- **Rationale**: a cleanup that cannot verify itself is worse than a refusal, because it looks like it worked (design lead). A session stop plus a fresh-process resume makes "clean" a fact.
- **Alternatives**: a new loop and driver per attempt (breaks the graph's life across repeats and rebuilds indices); a post-cancel PING (proves nothing about protocol state); replacing the driver (stale references); "cancel and carry on" (ruled out).

## D-2b — G retrieval database routing (DEFECT FIX, own FR)

- **Decision** (design lead, 20260926T231025320954Z444929a640; a defect fix, not a design change, and no registered property moves):
  - EVERY G operation — node, edge and episode writes, index build, typed pulls, anchored expansion, hybrid search and drop — runs through ONE per-question database: `self.driver.clone(database=group)`.
- **The defect**:
  - `build_graph` writes through the default driver, which targets database `default_db` (`arm_g.py` ~L348).
  - `hybrid_search` calls `Graphiti.search_(..., group_ids=[group])` (`arm_g.py` L461). That method is decorated `@handle_multiple_group_ids` (graphiti `graphiti.py` L1661), which for FalkorDB with one group id clones the driver to `database=<group>` (`decorators.py` L59–68).
  - So every hybrid search queried an EMPTY graph.
  - The typed pulls and anchored expansion read `default_db` and worked.
  - The approved live test asserted only that a hybrid step APPEARED in the plan, so it passed at zero hits.
- **Test**: the live test asserts the hybrid step returns ≥ 1 hit for at least one question, with the expected item identified from the frozen corpus (not from the oracle). It fails on the pre-change code.
- **Sweep**: every G assertion that checks a step RAN, rather than that it PRODUCED, is listed in the WP review artifact with its disposition. The count is reported, never fixed silently.

## D-3 — G's errors: halt versus per-cell refusal; G served identically

- **Decision**:
  - A new `PremiseViolated` class (name provisional), an Exception that is NOT an `ArmRefusal`, for **the no-LLM tripwire firing** and **a cross-group retrieval leak**. The Session treats it like `CalibrationPopulationIncomplete`: stop the run, and record a premise-violation halt (D-8) naming the arm.
  - **Foreign items** and **graph not built** become G's `ArmRefusal`, terminal for the cell on the first attempt.
  - G's context-limit cross-check reuses the D/R check (it is today duplicated verbatim in `arm_d.py` L171–199 and `arm_r.py` L293–318, and is unified in D-4).
  - G does **not** refuse `cache_prompt`.
- **Rationale**: design-lead ruling (c). The test is whether a retry could succeed, plus blast radius: a premise violation taints already-recorded cells. Identical serving is Kent's model-of-record ruling (C-008).
- **Alternatives**: all four terminal per-cell refusals: rejected, because the tripwire and the leak invalidate prior cells, not just this one.

## D-4 — One refusal class; the transitional fallbacks removed

- **Decision**:
  - One `ArmRefusal(RuntimeError)` in a shared place: `serving.py`, or a small `arms849/errors.py`, which then joins `REQUIRED_MODULES` in the same commit.
  - `arm_d.ArmRefusal` and `arm_r.ArmRefusal` become aliases of it, so the tests' `D.ArmRefusal`/`R.ArmRefusal` stay valid.
  - The shared `_check_limit` moves beside it.
  - The `ctx.serving.config` fallbacks in D and R are removed, and the affected test ctxs gain `config`.
  - Terminality stays decided by identity (`isinstance(exc, reg.refusal)`).
- **Rationale**: the harness docstring (~L280–281) already plans it. It stops three classes from diverging, and `ctx.config` is the contract name (arm-interface @`42056e57`).

## D-5 — The memory series measures the cgroup charge, read directly

- **Decision**:
  - The host-side series writer reads `/sys/fs/cgroup/system.slice/docker-<full-container-id>.scope/memory.current` (bytes → MiB) at a 1.0 s interval. It records the real interval in the series header, which the run record then carries.
  - The container id is resolved once by `docker inspect` on the host. The reader keeps its container-id check.
  - The column is renamed `falkordb_cgroup_peak_mib`, and `falkordb_rss_peak_mib` is retired everywhere (rubric §5 amendment @`ea3fbfc8`).
- **Rationale**: design-lead ruling (a), measured on office4 2026-09-26 (read-only):
  - cgroup filesystem `cgroup2fs`;
  - Docker cgroup driver `systemd`, CgroupVersion 2;
  - the scope path exists and `memory.current` is world-readable;
  - **100 reads in 0.8 ms**, so a 1 Hz interval is trivially sustainable.
  `docker stats` took about 1–2 s per reading against a 1 s slot (sizing investigation), which would silently loosen every §5 freshness tolerance, since they are multiples of the interval.
- **Alternatives**:
  - `docker stats`: rejected (latency, and the cgroup figure under an RSS name).
  - Process `VmRSS`: rejected by the design lead, because it understates the container's cost to the host for the deployability question.

## D-6 — The writer lives in `substrate.run()`

- **Decision**:
  - `substrate.run()` (the host process that blocks on `docker run` of the runner, ~L672–689) starts the writer before the subprocess. **The writer is observational**: if it cannot start or produces no reading, that is recorded (`series_generation` carries its status), and the run proceeds with the graph-store figure `could_not_check`. It never blocks the runner or refuses a cell.
  - It creates a generation-specific series file `falkordb-cgroup-<series_id>.jsonl` (exclusive create; never truncated; the writer's current `"w"` open at `sampler.py` ~L420 changes accordingly). It passes the generation descriptor `{series_id, path, container_id, interval_s}` to the runner through `_runner_cmd(..., env_extra=…)` (~L494–521), and the harness records it as a `series_generation` event before any graph activity.
  - It stops the writer in `finally`.
  - Only harness runs start it; the self-test and gate phases do not.
  - No compose change: the runner is a plain `docker run`, and `RUNS_DIR` is already mounted `rw` at `/runs` (~L500–502).
- **Rationale**: `up`/`down` are separate short-lived CLI processes, so a writer thread there would die with the process.
- **Alternatives**: a sidecar container: rejected. It would need a compose change and a new moving part.

## D-7a — The graph-store figure is RUN-LEVEL (rubric §5 third correction @`91e679e6`); per-cell rows carry no graph-store column

- **Decision** (Kent's selection ~23:2xZ of the design lead's recommendation `20260926T232216689769Z288a70b37a`; team-lead boundary ruling `20260926T232439481956Z612434ad98`; registered @`91e679e6`):
  - The container's cgroup memory is sampled across the whole run by the host-side writer (D-5, D-6), with one never-truncated series per substrate generation, bound by a `series_generation` event.
  - The run reports `baseline_mib`, `peak_mib` and `all_resident_mib`, using two harness events: `graph_store_first_build` and `graph_store_all_resident`. The marginal per-graph figure is derivable (contracts/memory-series.md item 4).
  - Any unavailable figure is `could_not_check` with a reason. **No cell is ever affected** (two sampler roles).
  - Per-cell rows carry NO graph-store column. The per-attempt graph-store sampler path in the harness is REMOVED.
- **Rationale**: measured on a throwaway sandbox (#1023): builds take 0.54–2.02 s; the cgroup charge is a high-water mark that never drops after `drop_graph`; the whole footprint is about 150–230 MiB, roughly 0.4 % of the ceiling. A per-question figure is not attributable under any ordering.
- **Deliberately avoided machinery** (team-lead instruction: record it, so the plan got smaller deliberately and not by omission):
  - per-question windows;
  - attempt-level boundary events (`graph_build_started` / `graph_build_result` / `graph_query_done` / `graph_dropped`);
  - a historical-window evaluator;
  - `could_not_check: interrupted` on a generation crossing;
  - `memory_support` as a windowed structure (held reading, in-window counts, `last_ts`).
  Earlier designs were rejected too: question-major order (prompt-cache bias on G's cost axis), build-and-drop per cell (defeated by the high-water mark), and a fresh container per cell (false precision).
- Graph-store memory is not, and never was, a primary-completeness condition.

## D-8 — Ledger additions

- **Decision**:
  - A new outcome `exceeds_memory_ceiling`: terminal for the attempt, never averaged, not scored, carrying the measured peak and the ceiling. Distinct from both `error` and an unreadable sampler (ruling (b); precedent `exceeds_model_context`).
  - The graph-store boundary events (`series_generation`, `graph_store_first_build`, `graph_store_all_resident`) are validated on write and replay. The run-level report is computed and validated when produced (D-7a); there is no persisted `memory_support`.
  - `attempt_start` carries `session_id`. Replay requires the attempt's `session_id` to match the most recent passing `session_gates` of **that** session.
  - A premise-violation halt record (event kind `premise_violated`, naming the arm and the reason). **Any ledger containing it is refused as a primary, by the grading export, AND by `Ledger.summarise()` (`ledger.py` ~L648), which today averages every `ok` row without looking at events** (correction C; post-plan review). Rows stay untouched but unusable. Tests cover a violation arriving on repeat 2, after scored rows, both immediately and after replay.
  - ledger-schema item 2 gets a dated sentence in this mission's `contracts/ledger-deltas.md`, noting that the per-session clause is now enforceable.
- **Rationale**: the design-lead rulings; the post-merge residual (`attempt_start` had no session id); correction C (untouched must not mean usable).

## D-9 — before_send

- **Decision**:
  - `serving.complete(..., before_send)` calls `before_send()` after `count_tokens` and the permitted-limit check, immediately before `urlopen`, with no try/except around it.
  - `ServingFacade` refuses to send without one.
  - The harness supplies a closure over the cell's GTT sampler that raises `CeilingBreached(peak, ceiling)`. This is a new class, subclassing neither `ContextExceeded` nor `ArmRefusal`, so no arm's handler catches it.
  - The Session maps it to the D-8 outcome. The secondary probe uses the same callback.
  - **Rulings 2 and 3** (design lead, 20260926T223312278643Zbb9e71a68a). These honour the registered text, so they are not amendments.
    - A **send-time breach STOPS THE SESSION** via its OWN stop signal. It never reuses the window `breached` flag: a send-time breach states the host's current state, while the window flag is an after-the-fact observation.
    - **A breached cell is TERMINAL**: it is never retried, by this session or a later one (rubric §5 amendment @`a00abc03`, Kent's selection 2026-09-26 22:41Z). A ledger holding an unresolved breach cannot be primary-complete.
    - A **GTT read that FAILS at send** (after `begin_attempt` has durably written `attempt_start`) keeps the attempt. It records a DISTINCT outcome, `sampler_unreadable_at_send` (could-not-check), sends nothing, and **refuses the cell**. It does **NOT** stop the session: §5 registers "refuses the cell", and every later cell is refused in turn, so nothing runs unguarded (design lead narrowed ruling 2, 22:34Z). It is never recorded as a breach, a pass or a zero.
- **Rationale**: rubric §5's ceiling guard (the last point the protocol controls) and ruling (b).

## D-10 — Environment gating and the pre-merge record

- **Decision**:
  - One session-scoped fixture in `tests/research/conftest.py` declares the research environment (`graphiti_core` importable, rendered corpus present, tokenizer and fastembed caches present). Research tests that need it skip with one named reason, and the counts appear in the summary.
  - The existing per-module guards (`importorskip`, `needs_corpus`) remain valid and can delegate to it.
  - `scripts/research/check_849_premerge.py` (name provisional) runs:
    1. the office4 suite under both seeds;
    2. the fresh-worktree CI simulation (a detached worktree of HEAD, no `build/`, a stub `graphiti_core` via PYTHONPATH);
    3. the live smoke (REQUIRED).
    It writes a record (commit, results, skip counts), and the merge to main cites it.
  - **Mandatory, non-skipped coverage (post-plan review):** the checker holds a named list of REQUIRED test node IDs that must EXECUTE AND PASS on office4. These are the precondition tests of FR-001–FR-016 (including FR-016's expected-hybrid-hit live test) plus the post-merge C-list tests (C-1, C-2, C-5). The checker reads pytest's junit-xml. Any required node missing, deselected, skipped or failed makes the record FAIL, whatever the exit code. The fresh-worktree CI simulation must also show zero failures and zero collection errors.
  - **The live smoke is REQUIRED, not optional** (plan.md Charter Check). The record binds every result to the exact commit SHA, and it is invalid for any other commit.
- **Rationale**: CI does not exercise the arms (Kent). The simulation is what reproduced CI exactly on 2026-09-26 and distinguished a real second layer from an imagined third. The design lead: "keep it as a gate, not a habit."

## Adversarial evidence

No dependency is added, upgraded or removed, so no supply-chain adversarial pass is required. The plan's contested points (correction B's mechanism; D-5's measure) are recorded above as design-lead dispositions (`accepted`).
