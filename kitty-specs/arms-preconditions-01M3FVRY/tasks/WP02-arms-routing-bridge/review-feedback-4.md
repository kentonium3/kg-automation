# WP02 review cycle 4 — REVISE

Reviewer: Codex (gpt-6-astra), read-only, cross-vendor. Implementer: Claude Opus 5.5 (python-pedro). 2026-09-27. Scope 5dc9f553..c429a9f4 (the design correction).

## Findings
[BLOCKER] [scripts/research/arms849/arm_g.py:751](/home/kgale/repos/kg-automation/.worktrees/arms-preconditions-01M3FVRY-lane-a/scripts/research/arms849/arm_g.py:751) — **Invariant A remains violated: gate checking is not atomic with socket activity.** — With default production settings, I paused `Bridge.list_graphs()` immediately before Redis’s `writelines`, allowed actual `GCancellationUnacknowledged` to propagate, then resumed: the server received `GRAPH.LIST`, increasing bytes **246→267 while the gate was shut**. Pausing before `asyncio.open_connection` likewise allowed connections **1→2 after fatal cancellation**. Superclass awaits also permit writes after poisoning during a health check or handshake. — Synchronize poisoning with physical writes/opens, including resumed operations and retries; add regressions that poison after the entry check.
[MAJOR] [scripts/research/arms849/arm_g.py:1014](/home/kgale/repos/kg-automation/.worktrees/arms-preconditions-01M3FVRY-lane-a/scripts/research/arms849/arm_g.py:1014) — **Invariant B still has an unguarded submission window.** — `run_coroutine_threadsafe` executes before the `try/finally`. Injecting `KeyboardInterrupt` at line 1015 left `_poisoned=None` and the gate open; the submitted coroutine subsequently issued `GRAPH.LIST`. The existing interruption test injects inside `_wait`, missing this boundary. — Initialize the guard before submission and include submission within its protected frame; test interruption immediately after scheduling.

## Orchestrator disposition
- A: make the gate check and the byte enqueue a single critical section: a per-pool threading.Lock held across check-then-writelines (synchronous). A connection opened after the poison is aborted before any byte is written. The TCP-handshake-in-flight residual is pinned and documented.
- B: include run_coroutine_threadsafe inside the guarded frame; test an interrupt immediately after scheduling.

VERDICT: REVISE
