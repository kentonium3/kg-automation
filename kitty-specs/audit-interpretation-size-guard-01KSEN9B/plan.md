# Implementation Plan: Audit Interpretation Size Guard

**Mission**: audit-interpretation-size-guard-01KSEN9B
**Date**: 2026-05-25
**Spec**: [spec.md](spec.md)
**Branch**: target=`main`, planning-base=`main`, merge-target=`main` (matches)

---

## Summary

Add an upfront size guard to `_interpret_one_doc()` in `scripts/doc_audit/judgment/audit_interpretation.py`. Estimate input tokens after `_build_prompt()` using a conservative char-based heuristic (`len(text) / 4` rounded up). If the estimate is ≥ `INPUT_TOKEN_GUARD_THRESHOLD` (180,000), return a synthetic `AuditVerdict(outcome=JUDGMENT_REQUIRED, confidence=0.0)` with an operator-readable rationale and skip the LLM call entirely. Pair with unit tests for AS1–AS6.

---

## Technical Context

**Language/Version**: Python 3.13.
**Primary Dependencies**: stdlib only.
**Storage**: n/a.
**Testing**: pytest. Extend `tests/doc_audit/judgment/test_audit_interpretation.py`.
**Target Platform**: pytest locally; production on office2.
**Project Type**: single project.
**Performance Goals**: estimator O(n) in prompt length; <1 ms typical.
**Constraints**: no prompt-file change (NFR-003); no change to drift_interpretation (C-004); no diff truncation (C-003).
**Scale/Scope**: 2 files modified. ~30 lines of helper + guard + 1 constant + ~60 lines of tests.

---

## Charter Check

**Tier 3 (Standard)**: Python logic change in a judgment script. No host config, no schema changes, no service deploy. Pre- and post-design Charter Check passes.

Charter governance unresolved (memory `project_charter_tool_registry_mismatch`). Compact mode.

---

## Project Structure

```
scripts/doc_audit/judgment/audit_interpretation.py     # MODIFIED
tests/doc_audit/judgment/test_audit_interpretation.py  # MODIFIED
```

---

## Phase 0/1 — Research + Design (consolidated)

**D1 — Guard placement**: in `_interpret_one_doc()` (around line 515 in current main), immediately after `_build_prompt()` (line 530) and before `_call_with_retry()` (line 536). Synthetic verdict construction and short-circuit return live in the same function.

**D2 — Constant**: `INPUT_TOKEN_GUARD_THRESHOLD: int = 180_000` at module scope alongside other named constants. 10% margin under Haiku 4.5's 200K context window. Leaves headroom for system prompt + `DEFAULT_MAX_TOKENS=512` output + estimation conservatism.

**D3 — Token estimation function**: `_estimate_input_tokens(prompt: str) -> int` near other helpers. Returns `max(1, (len(prompt) + 3) // 4)` — ceiling-divide-by-4. Conservative because:
- Anthropic's English-prompt ratio is roughly 4 chars/token; this matches
- Non-English text (rare in audit prompts) often has fewer chars/token, so 4 is an UNDER-estimate for non-English → we add a +3 ceiling buffer
- For prompts under 180K-token guard threshold, this is precise enough; for prompts near or over threshold, conservative over-estimation triggers the guard earlier (safer behavior)

**D4 — Synthetic verdict construction**: matches the existing retry-exhausted synthetic verdict (line ~554 in current main). Only the rationale differs:
```python
return AuditVerdict(
    outcome=AuditOutcome.JUDGMENT_REQUIRED,
    confidence=0.0,
    rationale=f"oversized prompt: ~{estimated} tokens >= threshold {INPUT_TOKEN_GUARD_THRESHOLD}; operator review required (size-guard short-circuit)",
    proposed_edit=None,
    question=None,
    doc_path=doc.path,
    target_path=None,
)
```
Verdict's full field shape is determined by inspecting the existing `_demote_low_confidence()` synthetic-verdict path during implementation.

**D5 — Confidence-demotion pass-through**: the synthetic verdict flows through `_demote_low_confidence()` like any other verdict (FR-007). With `confidence=0.0`, the demotion is a no-op (already below any reasonable threshold). Verified by reading `_demote_low_confidence()` during implementation.

**D6 — Test mocking**: extend the existing pytest patterns in `test_audit_interpretation.py`. Use a mocked `JudgmentClient` that asserts `client.call` is NOT invoked when over threshold (AS1) and IS invoked when under threshold (AS2). Don't rely on actual LLM calls.

No NEEDS CLARIFICATION items.

---

## Single WP Decision

One WP, 5 subtasks. Within ideal size envelope.

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Estimator under-counts for a prompt near 180K, lets a slightly-oversized prompt through to API (which still 400s). | Low | Low | Conservative ceiling estimate + 10% margin. Worst case: occasional 400 + retry burn on a single doc, which is the pre-fix steady state for that one doc — strictly better than today. |
| Synthetic verdict shape diverges from existing retry-exhausted synthetic verdict, breaking downstream ledger logic. | Low | Medium | FR-008 + test AS4 verify shape parity. Implementer must inspect existing synthetic-verdict construction before writing the new one. |
| Threshold tuning needed in practice (e.g., 180K is too aggressive and parks audits that would have succeeded). | Medium | Low | Threshold is a single-line constant (FR-005). Tune in a follow-up commit if needed. Initial value chosen conservatively. |
| Guard fires on small docs accidentally because token estimator is wrong. | Very Low | Medium | Char-based heuristic is mature; the test for AS3 verifies a known small fixture stays under threshold. |

---

## Branch Contract — Final Restatement

- Current branch: `main`
- Planning/base: `main`
- Merge target: `main`
- Matches target: `true`

---

## Next Suggested Command

`/spec-kitty.tasks`.
