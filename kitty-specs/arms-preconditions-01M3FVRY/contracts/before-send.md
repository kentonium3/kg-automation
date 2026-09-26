# Contract: before_send ceiling guard (C11)

1. `serving.complete(..., before_send)` invokes `before_send()` after the token count and the permitted-limit check, and immediately before the HTTP send. Nothing wraps it.
2. `ServingFacade` refuses to send without a `before_send`. Every live cell provides one.
3. The harness's callback reads the cell's GTT sampler. If the reading is strictly above the ceiling (57.5 GiB, NFR-004), it raises `CeilingBreached(measured_gib, ceiling_gib)`, which subclasses neither `ContextExceeded` nor `ArmRefusal`.
4. No arm catches `CeilingBreached`. It reaches the Session unaltered, and the Session records outcome `exceeds_memory_ceiling` (ledger-deltas.md item 1). On a breach, zero bytes are sent.
6. A breach at send STOPS the session through its own stop signal (not the window `breached` flag). The cell is TERMINAL and never retried by any session (rubric §5 @`a00abc03`).
7. If the GTT reading itself fails at send, the callback raises `CeilingUnreadable`, not a breach. The Session records `sampler_unreadable_at_send`, sends nothing, and refuses the cell. The session continues (§5: "refuses the cell").
5. The secondary-configuration probe uses the same callback.
