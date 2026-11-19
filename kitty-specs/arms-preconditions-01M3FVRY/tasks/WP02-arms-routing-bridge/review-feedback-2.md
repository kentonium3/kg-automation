# WP02 review cycle 2 — REVISE

Reviewer: Codex (gpt-6-astra), read-only, cross-vendor. Implementer: Claude Opus 5.5 (python-pedro). 2026-09-27. Scope 5dc9f553..17c6c9fe. The cycle-1 probes were re-run against HEAD.

## Findings
[MAJOR] scripts/research/arms849/arm_g.py:811 — Failed quiescence still returns success — `_quiesce()` returns `False`, but `_guarded` returns `"ok"` and `_run:850` accepts future completion without acknowledgement. Probe: `answer()` returned `"ans"` with **one unfinished task**, and subsequent `list_graphs()` issued another query — require acknowledgement on every completion path; poison the bridge when draining fails, and test deadlines longer than the drain grace.
[MAJOR] scripts/research/arms849/arm_g.py:859 — Loop-stop timeout does not prevent subsequent queries — `_halt_loop()` can return `False`, which is ignored before raising `GCancellationUnacknowledged`. Probe using a blocked synchronous embedder: the loop remained alive at the fatal signal; releasing it produced **eight subsequent transport queries** — enforce poisoning at the transport boundary before signaling failure, and test blocked synchronous work.
[MAJOR] scripts/research/arms849/arm_g.py:526 — Dropping a graph erases provenance needed to recognize a leak — `drop_graph:498` deletes its UUID map. Probe: build A and C1, drop A, then return A’s known UUID labeled C1; retrieval raises **ArmRefusal**, downgrading a run-invalidating leak to a cell refusal — retain historical UUID ownership separately from graph-built state and test this lifecycle.

VERDICT: REVISE
