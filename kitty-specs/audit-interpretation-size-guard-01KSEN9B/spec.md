# Specification: Audit Interpretation Size Guard

**Mission**: audit-interpretation-size-guard-01KSEN9B
**Source**: GitHub issue [#402](https://github.com/kentonium3/kg-automation/issues/402)
**Mission type**: software-dev
**Target branch**: main

---

## Summary

Add an upfront size guard to `scripts/doc_audit/judgment/audit_interpretation.py::_interpret_one_doc`. After `_build_prompt()` constructs the per-doc user section, estimate the total input token count (system prompt + user section). If the estimate exceeds a safe threshold (e.g., 180,000 tokens — leaving headroom under Haiku 4.5's 200,000-token context window plus the output `max_tokens` reservation), short-circuit to a synthetic `JUDGMENT_REQUIRED` verdict with operator-readable rationale and skip the LLM call entirely. The fix prevents API budget burn (4 × ~50 s retries per oversized doc on a request that cannot succeed). Diff-truncation (Option B from #402) is OUT of scope for this mission and may follow in a separate mission if signal loss from auto-parks proves material.

---

## User Scenarios & Testing

### Primary scenario

Operator triggers a doc-audit tick. A pending audit issue's backing commit produces a diff that, plus the in-scope doc + prompt scaffolding, exceeds Haiku's context window. Before this mission: each in-scope doc burns 4 retries × ~50 s before the driver emits a synthetic `JUDGMENT_REQUIRED` (post-retry). After this mission: each oversized in-scope doc emits the synthetic `JUDGMENT_REQUIRED` immediately with zero API calls and an operator-readable rationale that names the threshold and the actual estimated size.

### Acceptance scenarios

- **AS1**: An `_interpret_one_doc()` call whose `_build_prompt()` output (combined with system prompt) estimates ≥ 180K tokens returns a synthetic `AuditVerdict(outcome=JUDGMENT_REQUIRED, confidence=0.0, rationale="oversized prompt: ~N tokens > threshold T; operator review required (size-guard short-circuit)")` and makes ZERO API calls (no `client.call(...)`).
- **AS2**: An `_interpret_one_doc()` call below the threshold proceeds normally to `_call_with_retry()` — no regression.
- **AS3**: The token-estimation function is conservative — it never UNDERESTIMATES enough to let an actual oversized prompt slip through to the API. (Tested by comparing the estimator's output against `len(prompt)` heuristics for a known-oversized fixture.)
- **AS4**: The synthetic verdict produced by the size-guard short-circuit is structurally indistinguishable from the existing "retry exhausted" synthetic `JUDGMENT_REQUIRED`, so downstream ledger / issue-routing logic doesn't need to be changed. The only difference is the rationale string.
- **AS5**: The threshold constant is module-level and named (e.g., `INPUT_TOKEN_GUARD_THRESHOLD`), so it can be tuned without touching call sites.
- **AS6**: The full pytest suite for `tests/doc_audit/judgment/` passes.

### Edge cases

- **EC1 — exact-boundary prompt**: a prompt whose estimate is exactly at the threshold (180K). Behavior: short-circuit (use `>=`). One more byte and the actual call would fail, so being conservative at the boundary is correct.
- **EC2 — token-count estimation underestimates by ~5%**: anthropic.com docs note ~4 chars per token for English; the actual ratio varies. The threshold (180K out of 200K) leaves ~10% safety margin — a 5% underestimate still leaves headroom. Document this margin in the constant's docstring.
- **EC3 — operator unparks an audit that's still oversized**: the unparked audit hits the size guard, emits synthetic `JUDGMENT_REQUIRED`, and the routing logic re-parks it (or marks it for operator) per existing behavior. No new operator action required.
- **EC4 — multiple in-scope docs in one audit, some oversized and some not**: per-doc evaluation is independent. Oversized docs short-circuit individually; smaller docs proceed normally. No "all-or-nothing" failure mode.

---

## Requirements

### Functional Requirements

| ID | Description | Status |
|----|-------------|--------|
| FR-001 | `_interpret_one_doc()` MUST estimate input token count after `_build_prompt()` and BEFORE calling `_call_with_retry()`. | Required |
| FR-002 | If the estimate ≥ `INPUT_TOKEN_GUARD_THRESHOLD`, `_interpret_one_doc()` MUST return a synthetic `AuditVerdict(outcome=JUDGMENT_REQUIRED, confidence=0.0)` and MUST NOT call `_call_with_retry()` or `client.call()`. | Required |
| FR-003 | The synthetic verdict's `rationale` field MUST be operator-readable and name both the threshold and the actual estimated size. Example: `"oversized prompt: ~207000 tokens >= threshold 180000; operator review required (size-guard short-circuit)"`. | Required |
| FR-004 | The token-count estimation MUST be conservative (over-estimate rather than under-estimate). A simple char-count-based heuristic (e.g., `len(text) / 4`) is acceptable; more sophisticated counting (e.g., tiktoken / anthropic SDK helpers) is out of scope. | Required |
| FR-005 | The threshold MUST live as a named module-level constant (e.g., `INPUT_TOKEN_GUARD_THRESHOLD = 180_000`) so future tuning is one-line. | Required |
| FR-006 | Existing call paths (small prompts) MUST NOT be affected — no change in retry behavior, confidence demotion, or downstream verdict shape for any below-threshold call. | Required |
| FR-007 | The synthetic short-circuit verdict MUST flow through `_demote_low_confidence()` the same way the existing retry-exhausted synthetic verdict does, so confidence-threshold behavior is consistent. | Required |
| FR-008 | The fix MUST NOT alter the existing retry-exhausted synthetic-verdict path. Both paths now emit synthetic `JUDGMENT_REQUIRED` but for different reasons. Operators can distinguish via the rationale string. | Required |

### Non-Functional Requirements

| ID | Description | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Existing pytest suite for `tests/doc_audit/judgment/` MUST remain green. | 100% pass rate. | Required |
| NFR-002 | Token estimation overhead per call MUST be negligible. | O(n) char-based estimation; <1 ms for typical prompts. | Required |
| NFR-003 | The change MUST NOT modify the audit-interpretation prompt file. The fix is parser/dispatch-side. | `git diff scripts/doc_audit/prompts/audit_interpretation.prompt.md` shows zero changes. | Required |

### Constraints

| ID | Description | Status |
|----|-------------|--------|
| C-001 | This is NOT a bulk edit. Two files touched: `scripts/doc_audit/judgment/audit_interpretation.py` (helper + guard) and `tests/doc_audit/judgment/test_audit_interpretation.py` (tests). `change_mode: "regular"` set in meta.json. | Required |
| C-002 | Mission scope is code change + tests ONLY. Operational verification happens AFTER merge as a manual step (or follow-up mission), per the lesson from missions #53/#54. | Required |
| C-003 | Option B (diff truncation) is OUT of scope. May follow as a separate mission if Option A's auto-park rate proves material. | Required |
| C-004 | Sibling `drift_interpretation.py` is NOT in scope for this mission, even though it shares `_truncate_doc_state` with the audit path. Drift events rarely carry large diffs (per #402's root-cause hypothesis). If a similar guard becomes necessary for drift, file a follow-up. | Required |

---

## Success Criteria

- **SC-001**: Oversized-commit audits produce a `JUDGMENT_REQUIRED` outcome in < 1 second per in-scope doc (vs ~3.5 minutes today). API budget for those docs drops to zero.
- **SC-002**: Audit #350 (commit `f655876`, the canonical oversized-commit canary) can be unparked and processes cleanly on the next tick.
- **SC-003**: `felix-doc-auditor.timer` becomes eligible for steady-state re-enablement after this fix + the operational verification of #411 land.
- **SC-004**: Ledger entries for oversized-commit audits reflect the new outcome cleanly: a single row with the synthetic verdict, no 4× retry rows preceding it.

---

## Out of Scope

- Option B (diff truncation preserving file headers + per-file hunks).
- Option C (per-file chunked LLM calls).
- Applying the same guard to `drift_interpretation.py`.
- Re-enabling the timer (operator decision post-#411 verification + this fix).
- Switching to a different model with a larger context window.
- Tokenizer-based exact counts (e.g., tiktoken, anthropic count_tokens) — char-based estimation suffices for the guard threshold.

---

## Dependencies

- **#411** (closed in mission #55, merged at `0e87918f`): drift_interpretation fix is the precondition for any post-merge operational verification — without it, ticks still burn on drift events.
- **#350** (parked with `status:judgment-required`): the operational canary for this fix.

---

## Discovery Decisions (recorded for audit)

1. **Scope = Option A only**: per #402's recommended sequence ("ship A first").
2. **Code-change-only mission**: no office2 deploy → no chicken-and-egg risk.
3. **Threshold = 180,000 tokens**: 10% safety margin under Haiku's 200K context window. Leaves room for system prompt + `DEFAULT_MAX_TOKENS=512` output + estimation conservatism.
4. **Char-based estimation, not tokenizer**: simpler, no new dependencies, conservative enough for a guard (vs. an exact accounting requirement).
5. **Sibling `drift_interpretation.py` not modified**: per C-004 — drift events rarely carry large diffs. If a similar guard becomes needed, file a follow-up.
