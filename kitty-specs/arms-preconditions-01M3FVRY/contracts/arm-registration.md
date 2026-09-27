# Contract: arm registration (C13)

This contract amends arms-run-01M3APTA `contracts/arm-interface.md` @`42056e57`, which is otherwise unchanged. It records design-lead rulings 2026-09-26 (bus 20260926T220353449460Z6a87ff79f3, 20260926T220457953295Zd7af0f572f, 20260926T222035097212Zd8a3ed1773).

1. `ARM_FACTORIES` maps exactly `{"G", "D", "R"}` to factories taking `Resources`. A factory imports its arm module lazily. Importing the harness must never import `graphiti_core`.
2. `live_runtime` constructs ONE embedder and sets it on both `Resources.embedder` and `Runtime.embedder`. `ctx.embedder` is never `None` in a live cell.
3. All three arms raise the ONE shared `ArmRefusal` for configuration defects. Terminality is decided by identity. An `ArmRefusal` is terminal on the first attempt and never retried.
4. G refuses (via `ArmRefusal`, per cell) on: foreign items in its view, a graph not built, and an incoherent context limit. The last is checked against `ctx.config` exactly as D and R check it.
5. G raises `PremiseViolated`, which is NOT an `ArmRefusal`, on: the no-LLM tripwire firing, or retrieval crossing the per-question graph boundary. The Session stops the run and records `premise_violated` (see ledger-deltas.md). The ledger is then unusable as a primary.
6. The arms read the configuration only from `ctx.config`. The `ctx.serving.config` fallback no longer exists.
7. G is served exactly as D and R are: same model, same prompt template, and `cache_prompt: true`.
8. G's graph RETRIEVAL runs on ONE persistent event loop owned by its registration. Serving runs on the attempt thread. A cancelled coroutine must acknowledge termination within `G_CANCEL_GRACE_S` (10 s). If it does not, the Session stops with reason `g_cancellation_unacknowledged` (recorded with `grace_s`), and resume happens in a fresh process. There is no driver replacement. `run_session`'s `finally` calls the registration's `close()`.
10. **Database routing (defect fix)**: every G operation — writes, indices, pulls, expansion, hybrid search, drop — uses one per-question database (`driver.clone(database=group)`). The live test asserts the hybrid step RETURNS ≥ 1 expected hit (identified from the frozen corpus) for at least one question.
9. **Condition A:** a session run with `ARM_FACTORIES == {}` records every cell `not_implemented`, and the resulting ledger is refused by `require_complete_primary` and by the grading export. The post-plan review measured that the existing code ALREADY refuses this, so this test is a REGRESSION guard, and it must stay green. The RED-FIRST evidence for C13 is the live registration test: `live_runtime` exposes G, D and R with their refusal class and a non-None embedder. That test fails on the pre-change code, where `ARM_FACTORIES` is empty and the embedder is None.
11. **Dated addition (2026-09-27; orchestrator decision bus 20260927T085058813482Z6baf3dc083, design-lead ruling 20260927T085156195841Zf6c8b07323; WP02 review cycles 1–3): G's transport gate and its one accepted residual.**
   - **The invariant.** After G's fatal cancellation signal (`GCancellationUnacknowledged`), zero bytes reach FalkorDB.
   - **Where it is enforced:** at the socket. The bridge builds one `redis.asyncio.ConnectionPool` whose connections gate `send_packed_command` and `connect`, with the poison state scoped per POOL. The pool is passed to `FalkorDB(connection_pool=…)`, so every async command is covered: queries, schema refresh, pipelines and retries.
   - **The residual.** `FalkorDB.__init__` unconditionally runs `Is_Cluster`, and `Is_Cluster` issues one `INFO` over its own synchronous redis client (`falkordb/asyncio/cluster.py`), which the async gate cannot see.
   - **Why the residual is acceptable.** It runs only at construction, strictly before any poison can exist, and a poisoned bridge is never reconstructed, so it cannot violate the invariant.
   - **What pins it.** Tests assert exactly N=1 synchronous command at construction, and zero synchronous connections or commands afterwards across every operation and a poison. Growth on either side fails.
   - **Alternatives rejected.**
     - Forwarding a gate through `redis_connect_func` would still leave the TCP handshake ungated.
     - Reimplementing `FalkorDB.__init__` would be fragile across library upgrades.
   - **What remains open.** An unreachable FalkorDB at registration is NOT addressed by the gate. That stays with WP04: registration failure terminates loudly, and completeness is judged against the header plan grid (ledger-deltas item 7).
   **Dated addition to item 11 (2026-09-27; design lead bus 20260927T100641041260Zed34d20185, team lead 20260927T101357771700Z302b0a7421):** the socket gate put the client on a caller-supplied pool, and that change had a side effect: redis-py makes client-level kwargs INERT once `connection_pool=` is supplied, and nothing errors. The rule that follows is prescriptive:
   - every client argument the bridge depends on (today `protocol=2` and `decode_responses=True`) MUST be set on the pool;
   - each one is pinned by a BEHAVIOURAL test that observes the effect (a `str` round-trip; the negotiated protocol), never by asserting the configuration dict;
   - adding a new dependency at the client level is a defect, even though nothing errors.
   The review question this adds for any future change to the pool: *what did this fix make inert?*
