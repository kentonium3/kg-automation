# Phase 0 Research

**Mission**: `drift-ledger-retry-count-hardening-01KSC6AJ`
**Date**: 2026-05-24
**Method**: Deterministic code inspection — no LLM tasks dispatched. Every assumption was mechanically verifiable.

The spec ([spec.md](spec.md)) flagged four assumptions for plan-phase verification. All four resolved by reading code. One new finding emerged and was folded into scope.

---

## Decision 1: `retry_max = 1 + len(RETRY_DELAYS_SECONDS)` — derive from existing constant

**Rationale**: `_call_with_retry` at `scripts/doc_audit/judgment/drift_interpretation.py:593` constructs the delay sequence as `delays = (0,) if no_retry else (0, *RETRY_DELAYS_SECONDS)`. Each delay corresponds to one attempt. With `RETRY_DELAYS_SECONDS = (30, 60, 120)` (defined at `drift_interpretation.py:89`), the loop runs 4 times → `retry_max = 4`. Observed `exc.attempts = 4` in the 2026-05-24 04:50 UTC journal confirms.

Deriving from `RETRY_DELAYS_SECONDS` rather than hardcoding `4` means a future change to the retry policy (more or fewer delays) automatically propagates to the schema bound. No hidden coupling, no magic number.

**Alternatives considered**:
- **Hardcode `4` in the validator** — works today but plants a landmine. The next person who changes `RETRY_DELAYS_SECONDS` has no compiler/test signal that the schema also needs updating. Rejected.
- **Add a separate `RETRY_MAX` constant** — pure renaming; `1 + len(RETRY_DELAYS_SECONDS)` is already a one-line expression. Rejected as needless ceremony.
- **Pass `retry_max` through a config object** — overkill; retry policy is currently a module-level constant, not config-driven. Rejected as scope creep.

**Implementation note**: `output/drift_ledger.py` will need to import `RETRY_DELAYS_SECONDS` from `doc_audit.judgment.drift_interpretation`. There is one cross-module dependency now (`signals/drift_event.py` already imports from `judgment` peers), so this is consistent with the existing module graph.

---

## Decision 2: Widen schema bound to `[0, retry_max]`, not silent clamp

**Rationale**: The user (Q2 of specify discovery) chose **B** — ship contract widening with the clamp — over keeping the bound at `[0, 3]` and silently clamping. The contract should reflect reality. `retry_count = 4` is a true and useful piece of information: it tells operators "we used the entire retry budget on this event." Truncating to 3 silently loses that signal.

The widening is **additive**: every existing on-disk row has `retry_count ∈ [0, 3]`, which is a strict subset of `[0, retry_max]`. No reader breaks. No migration needed. NFR-005 is preserved.

**Alternatives considered**:
- **Keep bound at `[0, 3]`, clamp at write site only** (Q2 option A) — minimal change but loses fidelity. Rejected.
- **Widen and remove clamp entirely, trust callers** — defense-in-depth lost. If the retry policy ever advances past `retry_max` for any reason, the validator becomes the only gate, and a validator failure is a `ValueError` that crashes the tick (exactly the bug we're fixing). Rejected.

---

## Decision 3: Contract doc lifted to `docs/design/architecture/contracts/`

**Rationale**: The user (planning Q1) chose **B** — lift the contract to a live docs location.

The existing `kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/ledger-schema.md` is workflow-managed (`kitty-specs/` is read-only per global CLAUDE.md) and therefore cannot be edited to reflect schema changes. New live location: `docs/design/architecture/contracts/drift-ledger-schema.md` — new `contracts/` subdirectory sibling to the existing `data/` subdirectory (which holds the canonical machine-readable arch JSON). This pattern leaves room for future contract docs (e.g., audit-ledger, event format, signal contracts) without re-litigating the location question.

**Alternatives considered**:
- **A. Edit the file in-place inside kitty-specs/** — violates the workflow read-only rule. Rejected.
- **C. Make the dataclass docstring the canonical source** — minimal scope, but worse for operators who want to read schema docs without grepping the codebase, and provides no pattern for non-code contracts (event formats, signal maps). Rejected in favor of B.

---

## Decision 4: Widen the existing clamp at `handle_drift_events.py:645` too — new finding

**Rationale**: Not flagged in the spec. Discovered during research:

```python
# scripts/doc_audit/helpers/handle_drift_events.py:644-645
# Clamp retry_count to the ledger schema's [0, 3] bound.
retry_count = min(3, max(0, int(attempts)))
```

This clamp lives on the "happy path" RETRY_EXHAUSTED write (via `_append_ledger_entry`), parallel to the buggy write at `signals/drift_event.py:464`. If the schema bound widens but this clamp keeps `min(3, ...)`, then:
- The new write site (`signals/drift_event.py:464`, post-fix) will record `retry_count = 4`
- This sister site will silently record `retry_count = 3` for the same scenario

Fidelity is half-met. Two write sites would record different values for the same exhaustion event. Folded into scope: update this clamp to `min(retry_max, max(0, int(attempts)))` and refresh the comment.

**Alternatives considered**:
- **Leave this clamp as-is and only fix the crash** — half-fidelity is worse than no fix because operators would observe inconsistent `retry_count` values across rows depending on which code path wrote them. Rejected.
- **Refactor the two near-duplicate RETRY_EXHAUSTED write paths into a single helper** — would eliminate the original sin (clamp duplication). But adds significant scope, and the duplication has other small differences too (latency_ms handling, issue-filing semantics). Out of scope per C-001; noted as a code-smell candidate for a future cleanup mission.

---

## Decision 5: Update three existing tests that pin `retry_count` to the old bound

**Rationale**: Grep found three tests that encode the old bound as fixture values:

| File | Line | Current | Update to |
|---|---|---|---|
| `tests/doc_audit/output/test_drift_ledger.py` | 307 | `_make_entry(retry_count=4)` (asserted to raise) | `_make_entry(retry_count=retry_max+1)` (or hardcoded new out-of-range value) |
| `tests/doc_audit/signals/test_drift_event.py` | 925 | `assert entry.retry_count == 3` | `assert entry.retry_count == 4` |
| `tests/doc_audit/helpers/test_handle_drift_events.py` | 1076 | `assert row["retry_count"] == 3` | `assert row["retry_count"] == 4` |

These are not bugs in the tests — they correctly encoded the old contract. They are now fixture updates that ride along with the contract widening. The plan calls them out explicitly so the WP that lands the schema change also lands the test updates atomically (a half-landed change would leave CI red).

**Alternatives considered**:
- **Keep the existing tests and only ADD the new regression test** — half the existing tests would fail in CI immediately. Rejected; tests must stay green.

---

## Decision 6: New regression test in `test_drift_event.py`

**Rationale**: Per NFR-002, parametrized over `exc.attempts ∈ {0, 1, retry_max-1, retry_max}`, exercising the full `drift_event.commit` ledger-write path with each value. Asserts no exception raised, and the resulting ledger row's `retry_count` equals the input.

Placed in `test_drift_event.py` (not `test_drift_ledger.py`) because the bug surface is the write-site path, not the validator directly. The validator's positive/negative cases are already covered in `test_drift_ledger.py`; the new test ensures the integration between the retry policy's `exc.attempts` value and the validator's bound is exercised end-to-end.

**Alternatives considered**:
- **Test the validator directly** — already covered. Wouldn't catch the bug (the bug is in the write-site path, not the validator).
- **Test via a real LLM call mock** — overkill for a regression test that's about value plumbing.

---

## Out-of-scope items confirmed during research

- **Root cause of `_RetrySchemaError` on every call** — open question is whether the prompt regressed, the model output regressed, or the schema changed. Not investigated in this mission. → **#404**.
- **The two near-duplicate RETRY_EXHAUSTED write paths** — code smell, would clean up several adjacent issues. Out of scope per C-001. Candidate for a future cleanup mission.
- **audit_interpretation parallel code** — `_RetrySchemaError` and the retry helper are duplicated in `audit_interpretation.py`. The audit-ledger `AuditLedgerEntry` does not have a `retry_count` field, so the same bug shape cannot manifest there. No work needed.
