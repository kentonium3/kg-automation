---
affected_files: []
cycle_number: 6
mission_slug: arms-preconditions-01M3FVRY
reproduction_command:
reviewed_at: '2026-09-27T22:01:38Z'
reviewer_agent: claude
wp_id: WP02
---

# WP02 review cycle 6 — REVISE

Reviewed exact clean commit `c6f4d2eb` with Codex Astra in a read-only detached checkout.

## Blocking findings

1. **P1 — foreign-gated writer bypasses poisoning.** `GatedConnection._writer` accepts any `_GatedWriter` without verifying its gate identity. Reproduction: pause connection A's public `send_command("PING")` in `check_health`, poison A, assign `A._writer = B._writer` while B's gate remains open, then resume. The server receives 14 additional bytes, replies `PONG`, and the send returns success. Preserve A's own gate when accepting a replacement and add a regression test for an already-gated writer from another connection/gate.

2. **P2 — fingerprint does not bind the exact graph build view.** `view_fingerprint` hashes identifiers but omits graph-relevant record contents. After building `COM_REVIEW` as a `Commitment`, changing its kind to `Person` and changing its description leaves the fingerprint identical. Retrieval issues nine queries and accepts the result with `foreign_items=0`. Include graph-relevant event/entity/edge/link contents in the fingerprint and add a same-ID content-change regression.

## Nonblocking observation

Lifecycle tests emitted unawaited-coroutine, finalizer, and pending-task cleanup warnings.

## Evidence

- Full reviewer transcript: `/tmp/arms-wp02-c6-review-output.txt`
- Focused suite: 192 passed, 54 skipped.
- Corpus/cache-enabled suite: 135 passed, one checkout-local corpus-path failure; rerun with the path corrected in memory passed.
- Reviewer checkout remained clean at `c6f4d2eb`.
