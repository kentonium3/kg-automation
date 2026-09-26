# Contract: before_send ceiling guard (C11)

1. `serving.complete(..., before_send)` invokes `before_send()` after the token count and the permitted-limit check, and immediately before the HTTP send. Nothing wraps it.
2. `ServingFacade` refuses to send without a `before_send`. Every live cell provides one.
3. The harness's callback reads the cell's GTT sampler. If the reading is strictly above the ceiling (57.5 GiB, NFR-004), it raises `CeilingBreached(measured_gib, ceiling_gib)`, which subclasses neither `ContextExceeded` nor `ArmRefusal`.
4. No arm catches `CeilingBreached`. It reaches the Session unaltered, and the Session records outcome `exceeds_memory_ceiling` (ledger-deltas.md item 1). On a breach, zero bytes are sent.
5. The secondary-configuration probe uses the same callback.
