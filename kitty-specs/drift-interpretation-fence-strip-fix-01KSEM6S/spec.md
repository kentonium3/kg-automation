# Specification: Drift Interpretation Fence Strip Fix

**Mission**: drift-interpretation-fence-strip-fix-01KSEM6S
**Source**: GitHub issue [#411](https://github.com/kentonium3/kg-automation/issues/411); diagnostic at [`docs/diagnostics/drift-interpretation-payload-shape.md`](../../docs/diagnostics/drift-interpretation-payload-shape.md)
**Mission type**: software-dev
**Target branch**: main

---

## Summary

Add markdown-code-fence stripping to `_parse_verdict` in `scripts/doc_audit/judgment/drift_interpretation.py` so that fence-wrapped LLM responses parse as JSON. Haiku 4.5 (the model in use) consistently wraps every JSON response in ` ```json … ``` ` despite the prompt at `scripts/doc_audit/prompts/drift_interpretation.prompt.md:21-22` explicitly saying "No code fences. No prose." Mission #54's captured payloads (across 6 attempts and 2 distinct drift events) confirm the inner JSON is structurally valid and on-schema — only the outer fence wrapping defeats `json.loads()`. The prompt-side fix is already in place and ignored by the model; the parser-side fix is the load-bearing change.

---

## User Scenarios & Testing

### Primary scenario

After this mission lands, drift events that today return `RETRY_EXHAUSTED` will return real verdicts on the vast majority of calls. The doc-auditor's drift evaluation pipeline becomes functional. After #402 (oversized-diff fix) also lands, the operator can re-enable `felix-doc-auditor.timer` for steady-state operation.

### Acceptance scenarios

- **AS1**: A `_parse_verdict()` call with a response body ` ```json\n{"verdict": "...", "confidence": 0.9, "rationale": "..."}\n``` ` returns a valid `DriftVerdict` (no `_RetrySchemaError`).
- **AS2**: A `_parse_verdict()` call with a response body ` ```\n{...}\n``` ` (fence without language hint) also returns a valid `DriftVerdict`.
- **AS3**: A `_parse_verdict()` call with an unfenced response body (the spec-compliant shape) ALSO returns a valid `DriftVerdict` — the fix does not regress the historical happy path.
- **AS4**: A `_parse_verdict()` call with malformed inner JSON (after fence stripping) still raises `_RetrySchemaError` with the same `invalid JSON: …` message family.
- **AS5**: The full pytest suite for `tests/doc_audit/judgment/` is green after the change.

### Edge cases

- **EC1 — fence-only-no-content**: ` ```json\n\n``` ` — fence stripping yields empty string → falls through to the existing empty-response branch (`raise _RetrySchemaError("empty LLM response")`).
- **EC2 — multi-fence response**: the LLM emits two distinct fenced blocks (extremely unlikely for this prompt, but possible if the model adds prose with examples). Behavior: strip ONLY the outermost fence; if inner content still isn't valid JSON, `_RetrySchemaError("invalid JSON: …")` fires as today.
- **EC3 — fence with language hint other than `json`** (e.g., ` ```javascript ` or just ` ```{ `): treat the same as `json` fence — drop the first line if it starts with `` ` ``. Per Haiku 4.5 observed behavior the hint is always `json`, but defensive coding shouldn't depend on this.
- **EC4 — trailing characters after closing fence**: drop trailing fence and any subsequent whitespace; if non-whitespace text remains after the JSON, fall through to existing branches (don't try to be clever).
- **EC5 — leading whitespace before opening fence**: strip whitespace first, then check for fence.

---

## Requirements

### Functional Requirements

| ID | Description | Status |
|----|-------------|--------|
| FR-001 | `_parse_verdict` MUST successfully parse responses wrapped in ` ```json … ``` ` markdown code fences (Haiku 4.5's observed default behavior). | Required |
| FR-002 | `_parse_verdict` MUST successfully parse responses wrapped in ` ``` … ``` ` (fence without language hint). | Required |
| FR-003 | `_parse_verdict` MUST continue to successfully parse unfenced JSON responses (no regression of the historical happy path). | Required |
| FR-004 | `_parse_verdict` MUST continue to raise `_RetrySchemaError` for genuinely malformed JSON (after any fence stripping), preserving the existing exception message family `"invalid JSON: …"`. | Required |
| FR-005 | The fence-stripping logic MUST live in a small named helper (e.g., `_strip_code_fence(text: str) -> str`) for mechanical reviewability, NOT inlined in `_parse_verdict`. | Required |
| FR-006 | The helper MUST be observation-aware: when called on a non-fenced string, return the string unchanged. | Required |
| FR-007 | Existing call sites that pass `response_text` to `_log_raw_response_if_debug` (from mission #53) MUST be preserved — the capture path continues to log the RAW (pre-stripping) response for diagnostic value. | Required |

### Non-Functional Requirements

| ID | Description | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Existing pytest suite for `tests/doc_audit/judgment/` MUST remain green. | 100% pass rate. | Required |
| NFR-002 | Fence-stripping overhead MUST be O(n) in the response length (no regex backtracking, no quadratic patterns). | Linear performance verified by reading the helper code. | Required |
| NFR-003 | The change MUST NOT alter the prompt sent to the LLM in this mission. The existing "No code fences" instruction at `drift_interpretation.prompt.md:21-22` stays as-is (already correct but ignored by the model). | `git diff scripts/doc_audit/prompts/drift_interpretation.prompt.md` shows zero changes. | Required |

### Constraints

| ID | Description | Status |
|----|-------------|--------|
| C-001 | This is NOT a bulk edit. Two files touched: `scripts/doc_audit/judgment/drift_interpretation.py` and `tests/doc_audit/judgment/test_drift_interpretation.py`. `change_mode: "regular"` set in meta.json. | Required |
| C-002 | Mission scope is code change + tests ONLY. Operational verification on office2 happens AFTER merge as a manual step (or in a future mission), per the lesson from missions #53/#54. | Required |
| C-003 | The fence-stripping helper MUST handle UTF-8 input correctly (no byte-level operations that could break multi-byte characters). String-level slicing only. | Required |

---

## Success Criteria

- **SC-001**: After deploy, `_parse_verdict` succeeds on ≥ 95% of `drift_interpretation` LLM responses in steady state (measured by re-running the office2 capture from mission #54's quickstart and observing `drift_interpretation.schema_fail` lines drop dramatically).
- **SC-002**: `felix-doc-auditor.timer` becomes eligible for steady-state re-enablement once this fix AND #402 both land.
- **SC-003**: Unit tests document the canonical Haiku-4.5 fenced response shape, so future model rotations can be evaluated against the same fixtures.

---

## Out of Scope

- Operational verification on office2 (post-merge manual step OR follow-up mission).
- Generalization of fence stripping to other judgment scripts (`audit_interpretation`, `tier_classification`, etc.). Each script can grow its own fence handler if/when its captured failures show the same pattern. `audit_interpretation` is already broken in a different way (#402) and may need this same fix once its oversized-diff issue is resolved — but that's #402's call.
- Re-enabling the timer long-term (operator decision, awaits this fix AND #402).
- Switching to a structured-output / tool-use API pattern instead of free-form JSON (Option C in #411). Larger surface change deferred unless this fix proves insufficient.
- Hardening against future model behavior changes (e.g., adding a "JSON shape repair" layer for arbitrary wrappings). The fence-stripping is targeted at the observed Haiku 4.5 behavior, not a general-purpose normalizer.

---

## Dependencies

- **#404** (closed by mission #54): the investigation that surfaced this.
- **mission #53** (merged at `fbfe2a0f`): shipped the debug capture path that enabled mission #54's payload capture.
- **mission #54** (merged at `cd5bf7f3`): captured the payload and identified the root cause; closed #404; filed #411.

---

## Discovery Decisions (recorded for audit)

1. **Scope = code change + tests only** (no office2 deploy in same mission). Lesson from missions #53/#54 → memory `feedback_speckitty_split_code_and_deploy_missions`.
2. **Single WP**: small, tightly-coupled work (helper + wire-in + tests).
3. **Helper approach over inline strip**: per the issue's recommended fix shape (FR-005). Keeps the change mechanically reviewable and future-extensible.
4. **No prompt change in this mission**: NFR-003 records the choice. The existing prompt instruction is already correct; the LLM ignores it. Tightening the prompt further is unlikely to help (Haiku 4.5's fence-wrapping is consistent and aggressive) and risks introducing other regressions.
5. **No structured-output migration in this mission**: Option C in #411 is deferred per the standard "smallest fix first" pattern. If the parser-side strip proves brittle, structured output is the natural next step.
