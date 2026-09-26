# Contract: arm registration (C13)

This contract amends arms-run-01M3APTA `contracts/arm-interface.md` @`42056e57`, which is otherwise unchanged. It records design-lead rulings 2026-09-26 (bus 20260926T220353449460Z6a87ff79f3, 20260926T220457953295Zd7af0f572f, 20260926T222035097212Zd8a3ed1773).

1. `ARM_FACTORIES` maps exactly `{"G", "D", "R"}` to factories taking `Resources`. A factory imports its arm module lazily. Importing the harness must never import `graphiti_core`.
2. `live_runtime` constructs ONE embedder and sets it on both `Resources.embedder` and `Runtime.embedder`. `ctx.embedder` is never `None` in a live cell.
3. All three arms raise the ONE shared `ArmRefusal` for configuration defects. Terminality is decided by identity. An `ArmRefusal` is terminal on the first attempt and never retried.
4. G refuses (via `ArmRefusal`, per cell) on: foreign items in its view, a graph not built, and an incoherent context limit. The last is checked against `ctx.config` exactly as D and R check it.
5. G raises `PremiseViolated`, which is NOT an `ArmRefusal`, on: the no-LLM tripwire firing, or retrieval crossing the per-question graph boundary. The Session stops the run and records `premise_violated` (see ledger-deltas.md). The ledger is then unusable as a primary.
6. The arms read the configuration only from `ctx.config`. The `ctx.serving.config` fallback no longer exists.
7. G is served exactly as D and R are: same model, same prompt template, and `cache_prompt: true`.
8. G's graph work runs on ONE persistent event loop owned by its registration. After any cancellation or timeout, the driver is replaced before the next submission; if it cannot be, the arm raises `ArmRefusal`. The registration's `close()` shuts down the loop and the driver, and the Session calls it on stop.
9. **Condition A:** a session run with `ARM_FACTORIES == {}` records every cell `not_implemented`, and the resulting ledger is refused by `require_complete_primary` and by the grading export.
