---
work_package_id: WP01
title: Add _strip_code_fence helper + wire into _parse_verdict + tests
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-drift-interpretation-fence-strip-fix-01KSEM6S
base_commit: 99db654e4e4e773aa658f13cb474b58452015fac
created_at: '2026-05-25T03:56:50.458886+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: '77428'
history:
- event: planned
  timestamp: '2026-05-25T03:54:30Z'
  note: Created by /spec-kitty.tasks under mission drift-interpretation-fence-strip-fix-01KSEM6S
authoritative_surface: scripts/doc_audit/judgment/
execution_mode: code_change
mission_slug: drift-interpretation-fence-strip-fix-01KSEM6S
owned_files:
- scripts/doc_audit/judgment/drift_interpretation.py
- tests/doc_audit/judgment/test_drift_interpretation.py
tags: []
---

# WP01 — Add `_strip_code_fence` helper + wire into `_parse_verdict` + tests

## Objective

Restore `drift_interpretation` end-to-end functionality by stripping markdown code fences before `json.loads()` in `_parse_verdict`. Haiku 4.5 wraps JSON responses in ` ```json … ``` ` despite the prompt at `scripts/doc_audit/prompts/drift_interpretation.prompt.md:21-22` explicitly saying "No code fences." The prompt-side instruction exists and is ignored — the parser-side fix is mandatory.

## Context

- Mission #54 captured 6 raw payloads on office2 confirming the fence-wrapping pattern. Diagnostic at `docs/diagnostics/drift-interpretation-payload-shape.md`.
- Mission #53 shipped `_log_raw_response_if_debug` — preserve its call site (the capture path must continue to see the RAW response, not the stripped one).
- Issue #411 has the canonical fix shape. This WP implements Option A (parser-side strip). Option B (additional prompt tightening) is NOT in scope — the existing prompt instruction is sufficient evidence that prompt-tightening won't help.
- Read the full mission spec at [`../spec.md`](../spec.md) and plan at [`../plan.md`](../plan.md).

## Branch Strategy

- Planning base: `main` · Merge target: `main`
- Worktree allocated by `finalize-tasks`; path from `spec-kitty agent context resolve --mission <slug> --wp WP01 --json`.

## Detailed guidance per subtask

### T001 — Add `_strip_code_fence(text: str) -> str` helper

**Purpose**: Centralize fence-stripping logic in a small, named, testable helper.

**Steps**:
1. Open `scripts/doc_audit/judgment/drift_interpretation.py`.
2. Locate the `_parse_verdict` function (around line 396 in current main; grep `def _parse_verdict` to confirm).
3. Add the helper IMMEDIATELY ABOVE `_parse_verdict` (or alongside `_log_raw_response_if_debug` from mission #53, which is currently nearby). Code:

```python
def _strip_code_fence(text: str) -> str:
    """Strip markdown code fences from an LLM response.

    Returns the input unchanged if no fence is present. Otherwise drops the
    opening fence line (e.g. ``` ```json ``` or just ``` ``` ```) and the
    trailing fence line, then re-strips whitespace.

    Observed Haiku 4.5 behavior: every JSON response is wrapped in
    ``` ```json ... ``` ``` despite the prompt explicitly instructing the
    model to emit no code fences. See diagnostic doc
    ``docs/diagnostics/drift-interpretation-payload-shape.md``.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    # Drop opening fence (e.g., ```json or just ```)
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    # Drop trailing fence
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
```

**Validation**:
- [ ] Helper exists at module scope
- [ ] Returns input unchanged for non-fenced text
- [ ] Handles fence with language hint (` ```json `) and without (just ` ``` `)
- [ ] Returns stripped string (no leading/trailing whitespace) on fenced input

### T002 — Wire helper into `_parse_verdict`

**Purpose**: Apply the helper at the single call site.

**Steps**:
1. In `_parse_verdict`, locate the line that calls `json.loads()` on the response. Currently:
```python
data = json.loads(response_text)
```
(Around line 453-455 in main; the exact line is inside the `try:` block before the existing `except json.JSONDecodeError as exc:` handler.)

2. Change to:
```python
data = json.loads(_strip_code_fence(response_text))
```

3. CRITICAL: do NOT change the `_log_raw_response_if_debug(response_text, ...)` call site. The capture path must continue to see the RAW response, not the stripped one. The debug log line should still show the fence-wrapped content so future operators can confirm the model is still wrapping.

4. Verify by grep:
```bash
grep -n "_log_raw_response_if_debug\|_strip_code_fence\|json.loads" scripts/doc_audit/judgment/drift_interpretation.py
```
Expected pattern:
- `_log_raw_response_if_debug(response_text, "invalid JSON: …")` ← BEFORE the raise
- `_log_raw_response_if_debug` call sites unchanged (still get raw `response_text`)
- `json.loads(_strip_code_fence(response_text))` ← the only `json.loads` call in `_parse_verdict`

**Validation**:
- [ ] `json.loads` in `_parse_verdict` receives stripped text
- [ ] `_log_raw_response_if_debug` call sites unchanged (still receive raw `response_text`)
- [ ] No other call sites of `json.loads` in the file accidentally modified

### T003 — Unit tests for AS1 + AS2 + AS3

**Purpose**: Verify fence handling on the happy paths.

**Steps**:
1. Open `tests/doc_audit/judgment/test_drift_interpretation.py`. Read the existing test patterns (mission #53 added several; reuse the mock structure they established).

2. Add tests:

```python
def test_parse_verdict_strips_json_fence():
    """AS1: ```json wrapper does not defeat parsing."""
    body = '```json\n{"verdict": "NO_CHANGE_NEEDED", "confidence": 0.9, "rationale": "ok"}\n```'
    result = _parse_verdict(body)
    assert result.verdict == "NO_CHANGE_NEEDED"
    assert result.confidence == 0.9
    assert result.rationale == "ok"


def test_parse_verdict_strips_bare_fence():
    """AS2: ``` wrapper without language hint also works."""
    body = '```\n{"verdict": "NO_CHANGE_NEEDED", "confidence": 0.9, "rationale": "ok"}\n```'
    result = _parse_verdict(body)
    assert result.verdict == "NO_CHANGE_NEEDED"


def test_parse_verdict_unfenced_still_works():
    """AS3: unfenced response (the historical happy path) still parses."""
    body = '{"verdict": "NO_CHANGE_NEEDED", "confidence": 0.9, "rationale": "ok"}'
    result = _parse_verdict(body)
    assert result.verdict == "NO_CHANGE_NEEDED"
```

3. Adjust the verdict shape if the actual `DriftVerdict` dataclass requires different fields (e.g., `tier`, `rationale_quality`). Use whatever shape the existing successful tests use.

**Validation**:
- [ ] AS1, AS2, AS3 tests pass

### T004 — Unit tests for AS4 + edge cases

**Purpose**: Verify the fence-stripping doesn't mask genuine errors.

**Steps**:
1. Add tests:

```python
def test_parse_verdict_malformed_inner_json_still_raises(monkeypatch):
    """AS4: ```json with malformed inner JSON still raises _RetrySchemaError."""
    monkeypatch.delenv("DOC_AUDIT_DEBUG_DRIFT_PAYLOADS", raising=False)
    body = '```json\n{not valid json\n```'
    with pytest.raises(_RetrySchemaError, match="invalid JSON"):
        _parse_verdict(body)


def test_parse_verdict_empty_after_strip_raises(monkeypatch):
    """EC1: ```json fence with no content falls through to empty-response branch."""
    monkeypatch.delenv("DOC_AUDIT_DEBUG_DRIFT_PAYLOADS", raising=False)
    body = '```json\n\n```'
    with pytest.raises(_RetrySchemaError, match="empty LLM response|invalid JSON"):
        _parse_verdict(body)


def test_parse_verdict_leading_whitespace_before_fence():
    """EC5: leading whitespace before opening fence is handled."""
    body = '  \n```json\n{"verdict": "NO_CHANGE_NEEDED", "confidence": 0.9, "rationale": "ok"}\n```'
    result = _parse_verdict(body)
    assert result.verdict == "NO_CHANGE_NEEDED"


def test_strip_code_fence_returns_unchanged_on_non_fenced():
    """The helper itself should return unmodified input when no fence is present."""
    text = '{"verdict": "NO_CHANGE_NEEDED"}'
    assert _strip_code_fence(text) == text


def test_strip_code_fence_handles_json_hint():
    """The helper strips ```json hint correctly."""
    body = '```json\n{"a": 1}\n```'
    assert _strip_code_fence(body) == '{"a": 1}'
```

2. The `_RetrySchemaError(match=...)` regex accepts either the "empty LLM response" path OR the "invalid JSON" path — depending on how the helper handles the empty-after-strip case (returns empty string → falls through to empty branch in `_parse_verdict`, OR returns whitespace → falls through to invalid-JSON branch). Either outcome is acceptable as long as `_RetrySchemaError` fires.

**Validation**:
- [ ] All edge case tests pass
- [ ] `_RetrySchemaError` is still raised for genuinely bad input (after stripping)
- [ ] The `_strip_code_fence` helper itself is unit-tested for its two main behaviors

### T005 — Pytest + commit + transition

**Steps**:
```bash
cd <worktree-path>
pytest tests/doc_audit/ -v
```
Zero failures required.

```bash
git status
git add scripts/doc_audit/judgment/drift_interpretation.py tests/doc_audit/judgment/test_drift_interpretation.py
git diff --cached  # sanity-check the diff is tight
git commit -m "fix(WP01): strip markdown code fences in _parse_verdict (closes #411 root cause)

Haiku 4.5 wraps JSON responses in ```json fences despite the prompt's
'no code fences' instruction. Adds _strip_code_fence helper applied before
json.loads() in _parse_verdict. Capture path unchanged (still sees raw text).
Tests cover fenced/unfenced/edge cases per spec AS1-AS5."

spec-kitty agent tasks mark-status T001 T002 T003 T004 T005 --status done --mission drift-interpretation-fence-strip-fix-01KSEM6S

spec-kitty agent tasks move-task WP01 --to for_review --mission drift-interpretation-fence-strip-fix-01KSEM6S --note "Helper + wire-in + tests landed; ready for review"
```

## Hard rules

- Stay within `owned_files`. No prompt changes (NFR-003).
- Do not modify `_log_raw_response_if_debug` call sites (FR-007).
- Do not push to origin from the worktree.
- All pytest must pass before move-task.

## Definition of Done

- [ ] All 5 subtasks complete
- [ ] Full pytest suite green
- [ ] `_strip_code_fence` helper at module scope
- [ ] Wire-in is the ONLY `json.loads` call site change
- [ ] `_log_raw_response_if_debug` call sites unchanged
- [ ] At least 5 new tests covering fenced/unfenced/edge cases
- [ ] WP01 transitioned to for_review

## Branch / Implement / Review Commands

```bash
spec-kitty agent action implement WP01 --agent claude:opus:python-implementer:implementer --mission drift-interpretation-fence-strip-fix-01KSEM6S
spec-kitty agent tasks move-task WP01 --to for_review --mission drift-interpretation-fence-strip-fix-01KSEM6S --note "Ready for review"
spec-kitty agent action review WP01 --agent codex:gpt-5:spec-kitty-review:reviewer --mission drift-interpretation-fence-strip-fix-01KSEM6S
```
