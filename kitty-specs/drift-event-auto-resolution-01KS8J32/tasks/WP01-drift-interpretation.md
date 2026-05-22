---
work_package_id: WP01
title: drift_interpretation module + prompt
dependencies: []
requirement_refs:
- C-005
- C-006
- C-009
- FR-001
- FR-002
- FR-003
- FR-005
- FR-007
- FR-008
- FR-017
- NFR-002
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T19:45:00+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
history: []
authoritative_surface: scripts/doc_audit/judgment/
execution_mode: code_change
mission_id: 01KS8J321F8KE7369R3DA02329
mission_slug: drift-event-auto-resolution-01KS8J32
owned_files:
- scripts/doc_audit/judgment/drift_interpretation.py
- scripts/doc_audit/prompts/drift_interpretation.prompt.md
- tests/doc_audit/judgment/test_drift_interpretation.py
- tests/doc_audit/fixtures/drift_event_openclaw_cron.json
- tests/doc_audit/fixtures/drift_event_openclaw_json_hash.json
- tests/doc_audit/fixtures/drift_event_systemd_dropins.json
tags: []
---

# WP01 — drift_interpretation module + prompt

## Objective

Implement the Moment 0 LLM judgment surface. This is the load-bearing module of the entire mission — it produces the `DriftVerdict` that determines downstream routing. The module mirrors the structure of `scripts/doc_audit/judgment/tier_classification.py` (cache-aware prompt, `JudgmentClient` reuse, schema validation defense-in-depth).

## Context

- **Spec**: FR-001..FR-008, FR-017, NFR-002, NFR-004
- **Plan**: D1 (prompt structure), D2 (doc state truncation), D6 (retry policy), D7 (cost budget), D8 (test fixtures), D10 (CLI surface)
- **Data model**: E1 (DriftVerdict), E2 (DriftInterpretationContext), E5 (DriftInterpretationError)
- **API contract**: [contracts/api.md](../contracts/api.md) — `interpret()` signature
- **CLI contract**: [contracts/cli.md](../contracts/cli.md) — flags + exit codes 0/1/3/5
- **LLM JSON contract**: [contracts/llm-json.md](../contracts/llm-json.md) — 3 verdict shapes + validation rules
- **Pattern source**: `scripts/doc_audit/judgment/tier_classification.py` (read it first; mirror the structure)
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T001 — Module skeleton + dataclasses + module constants

**Purpose**: Establish the module surface + data structures.

**Steps**:

1. Create `scripts/doc_audit/judgment/drift_interpretation.py` with module docstring.
2. Imports: stdlib `json`, `time`, `logging`, `dataclasses`, `pathlib`, `typing`. From local: `JudgmentClient` (existing).
3. Module constants:
   ```python
   DEFAULT_MODEL = "claude-haiku-4-5-20251001"
   DEFAULT_TIMEOUT_SECONDS = 30
   DEFAULT_CONFIDENCE_THRESHOLD = 0.80
   DEFAULT_MAX_TOKENS = 512
   RETRY_DELAYS_SECONDS: tuple[int, ...] = (30, 60, 120)
   PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "drift_interpretation.prompt.md"
   VALID_VERDICTS = frozenset({"PROPOSED_EDIT", "JUDGMENT_REQUIRED", "NO_CHANGE_NEEDED"})
   ```
4. Define `DriftVerdict` frozen dataclass per E1.
5. Define `DocTarget` frozen dataclass.
6. Define `DriftInterpretationContext` frozen dataclass per E2.
7. Define `DriftInterpretationError(Exception)` with `cause`, `attempts`, and `to_diagnostic_block()` method per E5.

**Files**:
- `scripts/doc_audit/judgment/drift_interpretation.py` (~120 lines so far)

**Validation**:
- [ ] `python3 -c "from scripts.doc_audit.judgment.drift_interpretation import interpret, DriftVerdict, DriftInterpretationContext, DocTarget, DriftInterpretationError; print('ok')"` prints `ok`
- [ ] All dataclasses are `frozen=True` (immutability per E1, E2)

---

### T002 — Cache-aware prompt

**Purpose**: Author the system prompt that produces strict JSON output.

**Steps**:

1. Create `scripts/doc_audit/prompts/` directory if not present (it exists already).
2. Write `scripts/doc_audit/prompts/drift_interpretation.prompt.md` with this structure:
   - Frontmatter: `name: drift_interpretation`, `version: 0.1.0`, `last_updated: 2026-05-22`, `inherits_classification_from: scripts/openclaw/skills/doc-audit/SKILL.md §4`
   - `[CACHE_PREFIX_START]` marker
   - Role + task description ("You are the felix-doc-auditor drift interpreter...")
   - The 3 valid output shapes (PROPOSED_EDIT, JUDGMENT_REQUIRED, NO_CHANGE_NEEDED) per contracts/llm-json.md
   - Rules: confidence calibration, when to choose each verdict, examples in prompt
   - Constitutional guardrails reference (driver-enforced; LLM never sees guardrailed paths)
   - "Return STRICT JSON. No commentary. No code fences. No prose."
   - 3 worked examples (one per verdict) using synthetic but realistic drift events
   - `[CACHE_PREFIX_END]` marker
   - User-template section: drift event metadata + diff + mapping config + doc_targets
3. Target system-prompt portion ~1,200 tokens (cache prefix ~80-90% of prompt by tokens).

**Files**:
- `scripts/doc_audit/prompts/drift_interpretation.prompt.md` (~150 lines)

**Validation**:
- [ ] Prompt has both `[CACHE_PREFIX_START]` / `[CACHE_PREFIX_END]` markers (matches `tier_classification.prompt.md` shape)
- [ ] All 3 verdict shapes documented with exact JSON keys
- [ ] At least 3 worked examples (one per verdict)
- [ ] "STRICT JSON" directive present

---

### T003 — Doc-state truncation helper

**Purpose**: Implement D2 tiered strategy.

**Steps**:

1. Add helper `_truncate_doc_state(contents: str, diff: str) -> tuple[str, bool, str]` returning `(truncated_contents, was_truncated, strategy)`.
2. Logic:
   ```python
   size = len(contents)
   if size <= 8 * 1024:
       return contents, False, "full"
   if size <= 32 * 1024:
       # head (first 30 lines) + relevant_region (diff context ±20 lines) + tail (last 10 lines)
       strategy = "head_region_tail"
       ...
   else:
       # region only, ±10 lines
       strategy = "region_only"
       ...
   ```
3. Region extraction: parse the diff hunks (`@@ -A,B +C,D @@` headers) and pull line numbers; extract `contents` lines in that range ± N.
4. Insert literal `"\n...truncated...\n"` markers at truncation boundaries.

**Files**: same module, +~80 lines.

**Validation**:
- [ ] Unit tests cover all 3 size tiers (≤8KB, 8-32KB, >32KB)
- [ ] Truncation markers are visible in output
- [ ] Returned strategy string matches the actual strategy applied

---

### T004 — interpret() core function

**Purpose**: The LLM call + response parsing + validation per E1 invariants.

**Steps**:

1. `_build_prompt(context: DriftInterpretationContext) -> tuple[str, str]` — load PROMPT_PATH, split into (system, user_template); format user template with context fields. The truncation helper from T003 is applied to each `DocTarget.contents` before insertion.
2. `_parse_verdict(response_text: str, context: DriftInterpretationContext) -> DriftVerdict`:
   - JSON parse; on failure: raise `DriftInterpretationError("invalid JSON")` (caller's retry boundary)
   - Validate `verdict` is in `VALID_VERDICTS`; otherwise raise
   - Validate `confidence` is float in [0.0, 1.0]; otherwise raise
   - Validate `rationale` is non-empty string
   - If `verdict == "PROPOSED_EDIT"`:
     - Validate `proposed_edit` object present with `doc_path`, `current_value`, `proposed_value`
     - Validate `proposed_edit["doc_path"]` ∈ {t.path for t in context.doc_targets} — if not, raise (exit 5 semantic violation)
   - If `verdict == "JUDGMENT_REQUIRED"`: validate `question` present, non-empty, ≤500 chars
   - Build `DriftVerdict` dataclass
3. `_demote_low_confidence(verdict: DriftVerdict, threshold: float) -> DriftVerdict`:
   - If `verdict.verdict in {PROPOSED_EDIT, NO_CHANGE_NEEDED}` and `verdict.confidence < threshold`:
     - Return new `DriftVerdict(verdict="JUDGMENT_REQUIRED", confidence=verdict.confidence, rationale="Demoted from " + verdict.verdict + " (confidence " + str(verdict.confidence) + " < " + str(threshold) + "). Original rationale: " + verdict.rationale, question="Original verdict was " + verdict.verdict + " but confidence was below threshold. Please review and decide.")`
   - Else: return verdict unchanged
4. `interpret(client, context, *, model=..., timeout=..., confidence_threshold=..., no_retry=False) -> DriftVerdict`:
   - Build prompt
   - Call client (with retry wrapper from T005 unless `no_retry`)
   - Parse + validate response
   - Demote on low confidence
   - Return verdict

**Files**: same module, +~150 lines.

**Validation**:
- [ ] Out-of-set `doc_path` is rejected (no retry; semantic violation)
- [ ] All E1 invariants enforced
- [ ] Demotion logic produces well-formed JUDGMENT_REQUIRED with question

---

### T005 — Retry policy wrapper

**Purpose**: Implement D6 retry policy.

**Steps**:

1. `_call_with_retry(fn, *args, _no_retry=False, **kwargs)`:
   - Retryable exceptions: `(anthropic.APIError, anthropic.APITimeoutError, anthropic.RateLimitError, json.JSONDecodeError, ValueError)` — but NOT `DriftInterpretationError` raised for semantic violations (out-of-set doc_path). Implementation: separate exception class `_RetrySchemaError(Exception)` raised by `_parse_verdict` for retry-eligible schema violations vs `DriftInterpretationError` (subclass) for out-of-set
   - Delays: `RETRY_DELAYS_SECONDS = (30, 60, 120)`
   - First attempt immediate; sleep before retries
   - Log each retry to module logger at INFO
   - After all retries exhausted: raise `DriftInterpretationError("retry exhausted", cause=last_exc, attempts=4)`
2. Update `interpret()` to use `_call_with_retry` for the LLM-call segment only (not for prompt building or final demotion logic).

**Files**: same module, +~50 lines.

**Validation**:
- [ ] Retry delays match `(30, 60, 120)` exactly
- [ ] Semantic violations (out-of-set doc_path) do NOT retry
- [ ] Schema violations (malformed JSON, bad field types) DO retry
- [ ] Total max wait = 210s (matches NFR-006 envelope)

---

### T006 — CLI surface

**Purpose**: Per contracts/cli.md.

**Steps**:

1. `def main(argv=None) -> int` with argparse:
   - `--input-file <path>` (optional; stdin if absent)
   - `--output-file <path>` (optional; stdout if absent)
   - `--model <str>` (default `DEFAULT_MODEL`)
   - `--api-key-path <path>` (default `/data/services/openclaw/secrets/anthropic`)
   - `--timeout <int>` (default 30)
   - `--no-retry` (flag; for testing)
2. Read input JSON; deserialize to `DriftInterpretationContext` (manual JSON-to-dataclass; no third-party schema lib).
3. Build `JudgmentClient` with `api_key_path` (use existing `JudgmentClient(api_key_path=...)` pattern from `scripts/doc_audit/judgment/client.py`).
4. Call `interpret()`.
5. Serialize result to JSON; emit to `--output-file` or stdout.
6. Exit codes per contracts/cli.md: 0 success / 1 operational error / 3 invalid input JSON / 5 out-of-set proposed doc_path.
7. `if __name__ == "__main__": sys.exit(main())`.

**Files**: same module, +~70 lines.

**Validation**:
- [ ] `python3 -m scripts.doc_audit.judgment.drift_interpretation --help` exits 0
- [ ] Exit 3 on malformed input JSON
- [ ] Exit 5 on out-of-set doc_path (mocked SDK returning out-of-set)

---

### T007 — Tests

**Purpose**: ≥85% coverage; verify all paths.

**Steps**:

1. Create `tests/doc_audit/judgment/test_drift_interpretation.py`.
2. Mock `JudgmentClient` via monkeypatch or `unittest.mock`.
3. Create 3 fixture files in `tests/doc_audit/fixtures/`:
   - `drift_event_openclaw_cron.json` — `deliveryMode "none" → "announce"` diff against a stub service-inventory.json
   - `drift_event_openclaw_json_hash.json` — hash drift with no clear inventory mapping
   - `drift_event_systemd_dropins.json` — new dropin file added
4. Test cases:
   - **NO_CHANGE_NEEDED happy path**: mock returns valid JSON with `verdict: "NO_CHANGE_NEEDED"`, confidence 0.92. Assert verdict.verdict == "NO_CHANGE_NEEDED".
   - **PROPOSED_EDIT happy path**: mock returns valid JSON with proposed_edit present. Assert all fields populated correctly.
   - **JUDGMENT_REQUIRED happy path**: mock returns valid JSON with question.
   - **Confidence demotion (PROPOSED_EDIT, conf <0.80)**: assert returned verdict is JUDGMENT_REQUIRED with original rationale folded in.
   - **Confidence demotion (NO_CHANGE_NEEDED, conf <0.80)**: assert demoted.
   - **Out-of-set doc_path**: mock returns proposed_edit with doc_path not in context.doc_targets. Assert `DriftInterpretationError` raised with "out-of-set" in message.
   - **Malformed JSON, retry exhausts**: mock returns non-JSON 4 times. Assert `DriftInterpretationError("retry exhausted")` raised.
   - **Schema violation retry**: mock returns malformed-schema JSON on first call, valid JSON on second. Assert succeeds.
   - **API timeout retry**: mock raises `APITimeoutError` on first call, valid response on second. Assert succeeds.
   - **No-retry flag**: pass `no_retry=True`; on first failure, immediately raise (no sleep).
   - **Truncation tiers**: build fixtures of size 5KB, 20KB, 50KB; assert correct strategy applied.
   - **CLI exit 0 success**: invoke main with valid input + mocked SDK; assert returns 0.
   - **CLI exit 3 on bad input**: invoke main with malformed input JSON; assert returns 3.
   - **CLI exit 5 on out-of-set**: invoke main with mocked SDK returning out-of-set doc_path; assert returns 5.
   - **Cache-control marker assertion**: verify the `messages.create()` call (via mock) had `system` parameter with cache_control structure.

**Files**: `tests/doc_audit/judgment/test_drift_interpretation.py` (~280 lines, ~16 tests); 3 fixture JSON files (~30 lines each).

**Validation**:
- [ ] `pytest tests/doc_audit/judgment/test_drift_interpretation.py -v` ≥85% coverage
- [ ] No live Anthropic API calls
- [ ] All 3 verdict paths + 3 retry paths + CLI exit codes covered

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

pytest with mocked `JudgmentClient`. No live LLM calls. ≥85% coverage including all error paths.

## Definition of Done

- [ ] All 7 subtasks complete.
- [ ] `pytest tests/doc_audit/judgment/test_drift_interpretation.py -v` passes with ≥85% coverage.
- [ ] CLI smoke: `python3 -m scripts.doc_audit.judgment.drift_interpretation --help` exits 0.
- [ ] Manual fixture run with mocked SDK produces a valid `DriftVerdict` for each verdict shape.
- [ ] No regression on existing `scripts/doc_audit/judgment/tier_classification.py` (it should compile and its tests should still pass).

## Risks

- **Prompt drift**: small system-prompt changes can break JSON parsing. Tests must cover edge cases (Unicode in rationale, very long rationales, etc.).
- **Anthropic SDK signature**: pin SDK behavior expectations in tests; if SDK signature changes, tests catch it.
- **Truncation strategy**: D2 heuristics are best-effort; if real-world drift events surface unexpected behavior, the v2 plan can refine.

## Reviewer Guidance

1. Verify the prompt has both cache markers (`[CACHE_PREFIX_START]` / `[CACHE_PREFIX_END]`).
2. Verify out-of-set `doc_path` rejection — this is the load-bearing safety check.
3. Verify retry policy delays match `(30, 60, 120)` exactly.
4. Verify confidence demotion fires correctly at the 0.80 boundary.
5. Coverage ≥85%.

## Implementation Command

```bash
spec-kitty agent action implement WP01 --mission drift-event-auto-resolution-01KS8J32 --agent claude:opus:python-implementer:implementer
```
