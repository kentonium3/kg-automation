---
affected_files: []
cycle_number: 3
mission_slug: arms-preconditions-01M3FVRY
reproduction_command:
reviewed_at: '2026-09-27T08:31:24Z'
reviewer_agent: codex-gpt-6-astra
wp_id: WP02
---

# WP02 review cycle 3 — REVISE

Reviewer: Codex (gpt-6-astra), read-only, cross-vendor. Implementer: Claude Opus 5.5 (python-pedro). 2026-09-27. Scope 5dc9f553..31366e1b.

## Findings
[MAJOR] scripts/research/arms849/arm_g.py:734 — **Invariant A fails: new queries can reach transport after poison** — the gate checks only entry into the outer coroutine. Installed `AsyncGraph` retains raw `execute_command`; schema refresh, Redis pool acquisition and retries run beneath that gate. A full-Bridge offline probe received `GCancellationUnacknowledged`, then released blocked work and observed **three new GRAPH.RO_QUERY commands**: DB.LABELS, DB.RELATIONSHIPTYPES and DB.PROPERTYKEYS — enforce the gate at the actual transport-send boundary, including internal queries, retries and pipelines.
[MAJOR] scripts/research/arms849/arm_g.py:924 — **Invariant B fails: caller-side exceptions bypass `_conclude`** — injecting `KeyboardInterrupt` during `_wait` propagated immediately with the gate open and bridge unpoisoned; the abandoned operation subsequently issued GRAPH.LIST. The AST test sees explicit `return`/`raise` statements but misses exceptions raised by callees — protect the submitted operation with exception-safe cancellation and acknowledgement cleanup before propagating caller interruption.
[MAJOR] scripts/research/arms849/arm_g.py:494 — **Invariant C fails after a partial build** — ownership is recorded only after the entire build succeeds. Failing the second embedding after the first node save left that written UUID unowned; returning it during another question’s retrieval under that question’s group produced `ArmRefusal`, concealing a cross-question leak — reserve append-only ownership before each write attempt, including writes whose server outcome becomes uncertain.
[MINOR] tests/research/test_arms849_arm_g.py:1343 — **Derived tests overstate protection against additions** — the object walk stops at gates and skips function closures; an added closure retaining raw Redis passed. Adding a potentially raising helper call to `_wait` also passed the AST exit test at line 1438 — add behavioral mutation checks at the actual send and operation-exit boundaries; inspect callable captures where retaining the structural check.

## Orchestrator disposition (cycle-4 marker hit: a finding inside each of invariants A, B and C)
Boundaries were drawn above the layer where the thing happens. Design correction, not a patch:
- A: gate at the socket, a redis ConnectionPool with a gated Connection subclass (send_packed_command/connect) passed to FalkorDB(connection_pool=);
- B: single exit enforced by try/finally on the frame (any BaseException poisons);
- C: ownership reserved before each write attempt.

VERDICT: REVISE
