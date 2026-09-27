---
affected_files: []
cycle_number: 5
mission_slug: arms-preconditions-01M3FVRY
reproduction_command:
reviewed_at: '2026-09-27T13:59:43Z'
reviewer_agent: codex-gpt-6-astra
wp_id: WP02
---

# WP02 review cycle 5 — REVISE

Reviewer: Codex (gpt-6-astra), read-only, cross-vendor. Implementer: Claude Opus 5.5 (python-pedro). 2026-09-27. Scope 5dc9f553..45edc774.

## Findings
[BLOCKER] scripts/research/arms849/arm_g.py:819 — A connection paused **before** `open_connection` survives fatal cancellation — reproduced with the production 10-second grace: `GCancellationUnacknowledged` propagated, resuming accepted a new socket, and it remained open after `close()`. The stopped loop never reaches the post-open check at line 821. Zero application bytes were sent, but the socket-survival invariant fails — ensure pending opens retain an abort path despite loop shutdown; add this exact pre-open regression.
[MAJOR] scripts/research/arms849/arm_g.py:571 — Retrieved identities are validated against the build cache without checking the supplied view — building C1 with `COM_REVIEW`, then retrieving with a view excluding it, succeeds with `foreign_items=0`, `items_assembled=1`, and empty `block.record_keys`. Assembly silently discards the foreign-to-current-view item — bind each graph to its built view and refuse mismatches, or validate retrieved items against the current view before assembly.

## Orchestrator disposition
- BLOCKER: the gate OWNS its sockets. _connect creates the socket itself and registers it with the gate under the lock (refused if shut) before connecting; the poison, under the same lock and from the poisoning thread, calls shutdown(SHUT_RDWR) on every registered socket. No socket survives, whether or not the loop runs; this also retires the idle-connection residual.
- MAJOR: bind each built graph to its view (fingerprint) and refuse a mismatch, or validate retrieved items against the current view before assembly; a foreign-to-view item is ArmRefusal, never silently dropped.

VERDICT: REVISE
