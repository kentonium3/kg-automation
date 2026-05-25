# Spec: Audit Judgment Fence-Strip Hardening

**Mission**: `audit-judgment-fence-strip-hardening-01KSESPD`
**Type**: software-dev (bug fix)
**Source**: GitHub issue [#416](https://github.com/kentonium3/kg-automation/issues/416)
**Created**: 2026-05-25

## Why

The doc-auditor's judgment scripts call `json.loads()` directly on raw responses from Claude Haiku 4.5. Haiku 4.5 wraps JSON in markdown code fences (` ```json … ``` `) despite prompt instructions to the contrary. Each unprotected call site fails its first JSON parse, then burns four retries on `_RetrySchemaError` (~3.5 minutes wall-clock per failed call). With the timer disabled, no budget is being burned — but the doc-auditor remains non-operational.

Mission #55 fixed this for `drift_interpretation.py` by adding a `_strip_code_fence` helper. Mission #56 added a 180K-token size guard to `audit_interpretation` that, as a side effect, exposed the same fence-wrap bug for smaller audits. Pre-spec analysis confirmed the bug class affects two additional, previously-undocumented call sites in `cross_file_implication.py` and `tier_classification.py`.

## Scope

**In scope** — fix the fence-wrap bug class across all three remaining vulnerable `json.loads()` call sites in `scripts/doc_audit/judgment/`:

| File:line | Function | Action |
|---|---|---|
| `drift_interpretation.py:477` | `_parse_verdict` | already fence-stripped (mission #55) — re-point to shared helper |
| `audit_interpretation.py:289` | `_parse_verdict` | apply shared helper |
| `cross_file_implication.py:151` | parse helper | apply shared helper |
| `tier_classification.py:157` | parse helper | apply shared helper |

Extract `_strip_code_fence` to a shared module (e.g., `scripts/doc_audit/judgment/_llm_response.py`) so all four scripts import the same canonical implementation. Add unit tests for the shared helper plus regression tests at each call site covering fenced and unfenced inputs.

**Out of scope** — explicitly deferred to separate issues if operational evidence warrants:
- Extending mission #56's 180K-token size guard to `cross_file_implication` and `tier_classification`
- Diff truncation for oversized prompts (mission #402 Option B)
- Migrating to Anthropic structured-output JSON mode
- Any change to `debt_body_generation.py` (it doesn't call `json.loads` on LLM output)
- Any change to `_parse_context_document` helpers (they read internal artifacts, not LLM output)

## User Scenarios & Testing

### Primary scenario (operator) — Resume hourly doc-audit ticks

**Pre-conditions:** `felix-doc-auditor.timer` is disabled; recent commits to main have open audit issues in the queue with in-scope docs both above and below the 180K-token threshold.

1. Operator merges this mission and pulls on office2 (`ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'`).
2. Operator triggers one tick (`systemctl --user start felix-doc-auditor.service`) and watches the journal.
3. Journal shows: (a) zero `_RetrySchemaError` lines from `audit_interpretation`, (b) zero `_RetrySchemaError` lines from `cross_file_implication`, (c) zero `_RetrySchemaError` lines from `tier_classification`, (d) `size-guard short-circuit` lines for oversized prompts, (e) real verdicts (`NO_CHANGE_NEEDED`, `CONFIRMED`, `JUDGMENT_REQUIRED`, etc.) for below-threshold prompts.
4. Operator enables the timer (`systemctl --user enable --now felix-doc-auditor.timer`) and confirms one timer-driven hourly tick produces the same clean output.

### Edge cases

- **Fenced + leading/trailing whitespace** — model wraps with leading `\n` or trailing trailing whitespace; helper strips cleanly.
- **Fenced with language tag** (` ```json `) vs no tag (` ``` `) — both are handled.
- **Unfenced (model occasionally complies)** — helper passes through unchanged.
- **Fenced but malformed JSON inside** — helper strips fences; downstream `json.loads()` raises `JSONDecodeError`; existing retry path triggers (this is the only legitimate `_RetrySchemaError` path that remains after the fix).
- **Empty or near-empty response** — helper returns the empty/whitespace string; `json.loads()` raises and the retry path handles it.

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | A shared module under `scripts/doc_audit/judgment/` MUST expose `_strip_code_fence` (or equivalent) as the canonical implementation that strips markdown code fences from an LLM response string before JSON parsing. | proposed |
| FR-002 | `audit_interpretation._parse_verdict` MUST call the shared helper before its `json.loads()` invocation. | proposed |
| FR-003 | `cross_file_implication`'s `json.loads()` call site MUST call the shared helper before its `json.loads()` invocation. | proposed |
| FR-004 | `tier_classification`'s `json.loads()` call site MUST call the shared helper before its `json.loads()` invocation. | proposed |
| FR-005 | `drift_interpretation._parse_verdict` MUST import the helper from the shared module rather than re-defining it locally. The local definition MUST be removed. | proposed |
| FR-006 | When the LLM response is wrapped in ` ```json … ``` ` or ` ``` … ``` ` (with or without leading/trailing whitespace), the shared helper MUST produce a string that `json.loads()` parses cleanly when the wrapped content is valid JSON. | proposed |
| FR-007 | When the LLM response is NOT wrapped in code fences, the shared helper MUST return a string that produces the same `json.loads()` result it would have produced without the helper. | proposed |

## Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-001 | Helper invocation MUST add ≤ 1ms of overhead per call on typical (≤ 200KB) response strings. | proposed |
| NFR-002 | Helper MUST be a pure function: no I/O, no logging, no global state. | proposed |
| NFR-003 | Helper MUST be covered by unit tests at ≥ 95% branch coverage. | proposed |
| NFR-004 | Each of the four `_parse_*` call sites MUST be covered by at least one regression test exercising a fenced input and at least one exercising an unfenced input. | proposed |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | The shared module name MUST start with a single underscore (e.g., `_llm_response.py`) to signal it is private to `scripts/doc_audit/judgment/`. | proposed |
| C-002 | No public API surface of `audit_interpretation`, `cross_file_implication`, `tier_classification`, or `drift_interpretation` may change. The fix is internal. | proposed |
| C-003 | No change to prompt files (`scripts/doc_audit/prompts/*.prompt.md`). The fence-wrap is a defensive parse-side fix, not a prompt change. | proposed |
| C-004 | No change to `felix-doc-auditor.service` or `felix-doc-auditor.timer` systemd units. | proposed |
| C-005 | The 180K-token size guard introduced in mission #56 MUST NOT be removed or modified. | proposed |
| C-006 | The shared helper's behavior on unfenced input MUST be transparent (identity-like for valid JSON-bearing strings) to preserve `drift_interpretation`'s post-#55 behavior. | proposed |

## Success Criteria

- **SC-001** — On the next operator-triggered doc-audit tick after merge + deploy, the journal shows zero `_RetrySchemaError` lines attributable to fence-wrapping from any of the three newly-protected scripts. (Operationally verifiable via `journalctl --user -u felix-doc-auditor.service` over one tick.)
- **SC-002** — Audits whose in-scope docs are all below the 180K-token threshold produce real verdicts (no `_RetrySchemaError` rejections) within the existing retry budget.
- **SC-003** — The `felix-doc-auditor.timer` is re-enabled and runs one hourly-driven tick with no fence-wrap-attributable failures.
- **SC-004** — After unparking issue #350 (`gh issue edit 350 --remove-label "status:judgment-required"`), its next audit produces JUDGMENT_REQUIRED outcomes for its oversized docs (40+ docs all above the size-guard threshold) without any `_RetrySchemaError` from `audit_interpretation`.
- **SC-005** — Unit tests on the shared helper pass; regression tests at all four call sites pass.

## Key Entities

- **Shared module** (new) — `scripts/doc_audit/judgment/_llm_response.py`. Exposes the canonical `_strip_code_fence` helper. Imported by the four judgment scripts.
- **Judgment scripts** (existing, modified) — `drift_interpretation.py`, `audit_interpretation.py`, `cross_file_implication.py`, `tier_classification.py`. Each has one or more `json.loads()` call sites operating on raw LLM responses.
- **felix-doc-auditor service** (existing, unchanged) — the systemd user service whose hourly ticks invoke the judgment pipeline. Currently `disabled` pending this fix.

## Assumptions

- Haiku 4.5's fence-wrap behavior is consistent across the three remaining call sites (same model, same default markdown convention). Inferred from operational evidence on `drift_interpretation` and `audit_interpretation`. The fix is defensive — even if a future model variant stops fence-wrapping, the helper is a no-op pass-through for unfenced input.
- No external callers import from `scripts/doc_audit/judgment/` outside the doc-audit pipeline itself. The internal-only refactor is safe to land without a deprecation period.
- `cross_file_implication.py:151` and `tier_classification.py:157` are not blocked by other unrelated bugs that would also need fixing before this mission's success criteria become verifiable. (Pre-spec inspection showed both have the same call-site shape as `audit_interpretation._parse_verdict`. If operational verification surfaces a separate bug, file a follow-up.)

## Dependencies

- Requires mission #55 (`_strip_code_fence` in `drift_interpretation.py`, merged `0e87918f`) — used as the implementation reference for the extracted helper.
- Requires mission #56 (size guard in `audit_interpretation.py`, merged `3356b9b0`) — present on main; this mission does not modify it.
- No upstream dependency on any open issue.

## Risks

- **R-001** (low) — Helper's regex/parsing logic might be slightly different from the inlined implementation in `drift_interpretation.py`. Mitigation: copy the existing implementation verbatim into the shared module, then re-point. Regression tests cover the existing behavior.
- **R-002** (low) — Adding a new module path under `scripts/doc_audit/judgment/` may interact with how the doc-audit driver discovers/imports the package. Mitigation: confirm the module is importable in the existing test environment before declaring done.
