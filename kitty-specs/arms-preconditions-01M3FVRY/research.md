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

## D-2 — G runs behind one persistent event loop; cancellation never leaves a dirty driver

- **Decision**:
  - G's registration owns one asyncio loop on a dedicated daemon thread and one FalkorDB driver bound to it (`FalkorDriver(host="falkordb", port=6379)`, the compose service name, since the harness runs inside the runner container).
  - `build_graph`, `answer` and `drop_graph` are synchronous wrappers that submit through `asyncio.run_coroutine_threadsafe` and wait with the attempt's deadline, honouring `ctx.cancelled`.
  - **On any cancellation or timeout (correction B)**, the wrapper cancels the future, then closes and replaces the driver before the next submission (fresh connection). If the replacement cannot be established, it raises the arm's terminal `ArmRefusal`.
  - A `close()` on the registration shuts down the loop and the driver. The `Runtime` gains an optional close hook that the Session calls on stop.
- **Rationale**:
  - The FalkorDB async client is bound to the loop it first runs on (`arm_g.py` L32–34), while the harness runs every attempt on a fresh thread (`_call_with_timeout`, ~L680–710). A per-attempt `asyncio.run` would break loop affinity.
  - Cancelling a future does not guarantee the driver unwound mid-protocol, and a persistent driver would carry that damage into cell N+1 (design lead, correction B).
  - A fresh connection after a cancellation is the cheapest mechanism that makes "clean" a fact rather than a hope.
- **Executable interface (post-plan review, 2026-09-26):**
  - **Retrieval on the loop, serving off it.** `GraphArm.answer` today awaits `plan_and_assemble` and then makes the SYNCHRONOUS serving call (`arm_g.py` ~L534). If the whole of `answer` ran on the loop thread, that HTTP call would block the loop. So the G registration's synchronous `answer` wrapper submits **only** the retrieval coroutine (`plan_and_assemble`) to the loop. It then runs render / serialize / count / `ctx.serving.complete` on the attempt thread, exactly as D and R do. `GraphArm` gains a small `respond(block, plan, question, ctx)` for the synchronous half.
  - **Every operation gets a deadline.** `build_graph`, `drop_graph` and retrieval each receive an explicit deadline and the attempt's `cancelled` flag. The Session passes the attempt deadline it already computes for `_call_with_timeout`, and `CellContext` gains a read-only `deadline`.
  - **Bounded cancellation acknowledgement.** On timeout or cancel, the wrapper calls `future.cancel()` and then waits a bounded grace period (≤ 5 s) for the future to report done. If it does not, the bridge is declared POISONED: the thread is abandoned as a daemon, and a NEW loop, thread and driver are created before any further submission. The graph itself persists server-side in FalkorDB, keyed by the group. If the replacement cannot connect, the arm raises `ArmRefusal`, terminal for the cell, and every following G cell refuses until a healthy bridge exists.
  - **Unconditional cleanup.** `run_session` wraps the whole session in `try/finally: runtime.close()`. That covers normal completion, `--limit`, `stop()`, a raised exception and `KeyboardInterrupt`. Closing the registration never waits unboundedly on a blocked loop: it applies the same bounded grace, then abandons.
- **Alternatives**:
  - A new loop plus driver per attempt: rejected. It rebuilds indices per attempt, and G's graph lives across repeats.
  - A post-cancel health PING: rejected as insufficient. A PING succeeding does not prove the connection's protocol state for the next query.
  - "Cancel and carry on": ruled out by the design lead.

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
  - `substrate.run()` (the host process that blocks on `docker run` of the runner, ~L672–689) starts the writer before the subprocess and waits for the first reading, bounded, failing closed with a named error.
  - It passes the series path (`/runs/falkordb-cgroup.jsonl`) and the expected container id to the runner through `_runner_cmd(..., env_extra=…)` (~L494–521).
  - It stops the writer in `finally`.
  - Only harness runs start it; the self-test and gate phases do not.
  - No compose change: the runner is a plain `docker run`, and `RUNS_DIR` is already mounted `rw` at `/runs` (~L500–502).
- **Rationale**: `up`/`down` are separate short-lived CLI processes, so a writer thread there would die with the process.
- **Alternatives**: a sidecar container: rejected. It would need a compose change and a new moving part.

## D-7 — The harness binds the series reader; support is recorded in the row

- **Decision**:
  - `live_runtime` binds `rss_sampler=functools.partial(<series sampler>, path, expected_id)` from the environment (refusing if they are absent). It calls `sampler.require_breached()` on a constructed instance of each bound sampler.
  - A G ok row carries `falkordb_cgroup_peak_mib` plus a nested `memory_support` object (D-8). `grading`/export never reads it as a score.
- **Rationale**: the harness surface is unchanged (a zero-arg factory, a context manager, `peak_mib` read pre-arm and post-window), so this is the one-line swap the WP04 reopen designed for. Support is nested in the row, not in a sibling event (design lead ruling 4 at the post-merge checkpoint: nothing separable from the number it qualifies).

## D-8 — Ledger additions

- **Decision**:
  - A new outcome `exceeds_memory_ceiling`: terminal for the attempt, never averaged, not scored, carrying the measured peak and the ceiling. Distinct from both `error` and an unreadable sampler (ruling (b); precedent `exceeds_model_context`).
  - `memory_support` is validated on write and on replay:
    - exact keys;
    - canonical UTC timestamps;
    - window end ≥ start;
    - a non-negative int count;
    - `held_ts` a string or None;
    - `peak_source` ∈ {held, in_window};
    - held ⇒ `held_ts` present;
    - zero in-window samples ⇒ held.
  - `attempt_start` carries `session_id`. Replay requires the attempt's `session_id` to match the most recent passing `session_gates` of **that** session.
  - A premise-violation halt record (event kind `premise_violated`, naming the arm and the reason). **Any ledger containing it is refused as a primary, by the grading export, AND by `Ledger.summarise()` (`ledger.py` ~L648), which today averages every `ok` row without looking at events** (correction C; post-plan review). Rows stay untouched but unusable. Tests cover a violation arriving on repeat 2, after scored rows, both immediately and after replay.
  - **`memory_support` validation is internally consistent** (post-plan review):
    - `interval_s` is finite and > 0;
    - `held` ⇒ `held_ts` is present, STRICTLY before `window_start`, and no more than `GAP_INTERVALS × interval_s` before it;
    - `in_window` ⇒ `in_window_readings ≥ 1`;
    - a new `last_ts` (the latest reading used) is ≤ `window_end` and no more than `STALE_INTERVALS × interval_s` before it.
    A support object that describes a window §5 would have refused is itself refused, on write and on replay.
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
    - **Whether a breached cell is TERMINAL (never retried by a later session) is PENDING KENT.** It is a validity question, and the design lead is drafting it as a dated §5 addition for his sign-off (20260926T223436721075Z2f274189c3). **Do not build either terminality until it is ruled.** Whichever way it goes, a ledger containing an un-retried breach cannot be primary-complete.
    - A **GTT read that FAILS at send** (after `begin_attempt` has durably written `attempt_start`) keeps the attempt. It records a DISTINCT outcome, `sampler_unreadable_at_send` (could-not-check), sends nothing, and **refuses the cell**. It does **NOT** stop the session: §5 registers "refuses the cell", and every later cell is refused in turn, so nothing runs unguarded (design lead narrowed ruling 2, 22:34Z). It is never recorded as a breach, a pass or a zero.
- **Rationale**: rubric §5's ceiling guard (the last point the protocol controls) and ruling (b).

## D-10 — Environment gating and the pre-merge record

- **Decision**:
  - One session-scoped fixture in `tests/research/conftest.py` declares the research environment (`graphiti_core` importable, rendered corpus present, tokenizer and fastembed caches present). Research tests that need it skip with one named reason, and the counts appear in the summary.
  - The existing per-module guards (`importorskip`, `needs_corpus`) remain valid and can delegate to it.
  - `scripts/research/check_849_premerge.py` (name provisional) runs:
    1. the office4 suite under both seeds;
    2. the fresh-worktree CI simulation (a detached worktree of HEAD, no `build/`, a stub `graphiti_core` via PYTHONPATH);
    3. optionally the live smoke.
    It writes a record (commit, results, skip counts), and the merge to main cites it.
  - **Mandatory, non-skipped coverage (post-plan review):** the checker holds a named list of REQUIRED test node IDs that must EXECUTE AND PASS on office4. These are the precondition tests of FR-001–FR-012 plus the post-merge C-list tests (C-1, C-2, C-5). The checker reads pytest's junit-xml. Any required node missing, deselected, skipped or failed makes the record FAIL, whatever the exit code. The fresh-worktree CI simulation must also show zero failures and zero collection errors.
  - **The live smoke is REQUIRED, not optional** (plan.md Charter Check). The record binds every result to the exact commit SHA, and it is invalid for any other commit.
- **Rationale**: CI does not exercise the arms (Kent). The simulation is what reproduced CI exactly on 2026-09-26 and distinguished a real second layer from an imagined third. The design lead: "keep it as a gate, not a habit."

## Adversarial evidence

No dependency is added, upgraded or removed, so no supply-chain adversarial pass is required. The plan's contested points (correction B's mechanism; D-5's measure) are recorded above as design-lead dispositions (`accepted`).
