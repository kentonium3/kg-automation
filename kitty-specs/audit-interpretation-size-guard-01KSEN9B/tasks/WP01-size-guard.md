---
work_package_id: WP01
title: Add INPUT_TOKEN_GUARD_THRESHOLD + estimator + guard in _interpret_one_doc
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-audit-interpretation-size-guard-01KSEN9B
base_commit: f29768388f90aba1507a5456151d190b93b1f36a
created_at: '2026-05-25T04:16:02.935011+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: '82972'
history:
- event: planned
  timestamp: '2026-05-25T04:13:30Z'
  note: Created by /spec-kitty.tasks under mission audit-interpretation-size-guard-01KSEN9B
authoritative_surface: scripts/doc_audit/judgment/
execution_mode: code_change
mission_slug: audit-interpretation-size-guard-01KSEN9B
owned_files:
- scripts/doc_audit/judgment/audit_interpretation.py
- tests/doc_audit/judgment/test_audit_interpretation.py
tags: []
---

# WP01 — Add `INPUT_TOKEN_GUARD_THRESHOLD` + estimator + guard

## Objective

Implement Option A from #402 — an upfront input-token size guard in `_interpret_one_doc()` (in `scripts/doc_audit/judgment/audit_interpretation.py`). When the assembled per-doc prompt's estimated token count exceeds `INPUT_TOKEN_GUARD_THRESHOLD = 180_000`, return a synthetic `AuditVerdict(outcome=JUDGMENT_REQUIRED, confidence=0.0)` with an operator-readable rationale and skip the LLM call entirely. No diff truncation (out of scope, Option B). No drift_interpretation changes (out of scope, C-004).

## Context

- #402 body and root-cause analysis: oversized prompts (e.g., 217K tokens for issue #350) return 400 from the API; 4 retries × ~50s burn budget for nothing.
- `_interpret_one_doc` at `scripts/doc_audit/judgment/audit_interpretation.py:515`. `_build_prompt` at line 229. `_call_with_retry` at line 439.
- The synthetic JUDGMENT_REQUIRED pattern already exists for "retry exhausted" (around line 554 — the implementer should grep `JUDGMENT_REQUIRED` to confirm the exact construction).
- Read the full mission spec at [`../spec.md`](../spec.md) and plan at [`../plan.md`](../plan.md).

## Branch Strategy

- Planning base: `main` · Merge target: `main`
- Worktree allocated by `finalize-tasks`.

## Detailed guidance per subtask

### T001 — Add constant + estimator

**Steps**:
1. Open `scripts/doc_audit/judgment/audit_interpretation.py`.
2. Near other module-level constants (look for `DEFAULT_MAX_TOKENS`, `DEFAULT_MODEL`, etc., around lines 95-105), add:

```python
#: Conservative input-token guard threshold for audit_interpretation prompts.
#:
#: Haiku 4.5's context window is 200,000 input tokens. We reserve 10% margin
#: (20,000 tokens) for system prompt, output (DEFAULT_MAX_TOKENS=512), and
#: estimation conservatism. If the estimated input exceeds this threshold,
#: `_interpret_one_doc` short-circuits to a synthetic JUDGMENT_REQUIRED
#: rather than burning 4 × ~50s retries on a 400-guaranteed API call.
#: See issue #402 for diagnostic + rationale.
INPUT_TOKEN_GUARD_THRESHOLD: int = 180_000
```

3. Near other module-private helpers (`_truncate_doc_state`, `_demote_low_confidence`, etc.), add:

```python
def _estimate_input_tokens(text: str) -> int:
    """Estimate input token count for an LLM prompt.

    Uses a conservative char-based heuristic: ceiling-divide character
    count by 4 (Anthropic's English-text approximation). Conservative
    on purpose — for prompts near or over the guard threshold we want
    to over-estimate (triggers the guard earlier, safer behavior).

    Returns at least 1 to avoid degenerate empty-prompt edge cases.

    See issue #402.
    """
    if not text:
        return 1
    return max(1, (len(text) + 3) // 4)
```

**Validation**:
- [ ] Constant exists at module scope with docstring
- [ ] Helper exists with proper docstring, returns int, handles empty string

### T002 — Insert size-guard check

**Steps**:
1. Inspect the existing synthetic JUDGMENT_REQUIRED construction so the new short-circuit verdict matches its shape. Grep:
```bash
grep -B 2 -A 10 "JUDGMENT_REQUIRED" scripts/doc_audit/judgment/audit_interpretation.py | head -40
```
Identify the field shape (likely uses `AuditOutcome.JUDGMENT_REQUIRED`, `confidence=0.0`, `rationale="LLM retry exhausted"`-style string, etc.).

2. In `_interpret_one_doc()` (line ~515-538), modify the function. Original:

```python
def _interpret_one_doc(...) -> AuditVerdict:
    """..."""
    user_section = _build_prompt(doc, context)

    def _attempt() -> AuditVerdict:
        response = client.call(PROMPT_PATH, user_section)
        return _parse_verdict(response.content, doc)

    verdict = _call_with_retry(_attempt, no_retry=no_retry)
    return _demote_low_confidence(verdict, confidence_threshold)
```

Modified shape:

```python
def _interpret_one_doc(...) -> AuditVerdict:
    """..."""
    user_section = _build_prompt(doc, context)

    estimated_tokens = _estimate_input_tokens(user_section)
    if estimated_tokens >= INPUT_TOKEN_GUARD_THRESHOLD:
        synthetic = AuditVerdict(
            outcome=AuditOutcome.JUDGMENT_REQUIRED,
            confidence=0.0,
            rationale=(
                f"oversized prompt: ~{estimated_tokens} tokens "
                f">= threshold {INPUT_TOKEN_GUARD_THRESHOLD}; "
                "operator review required (size-guard short-circuit)"
            ),
            doc_path=doc.path,
            # Match other fields from the existing synthetic JUDGMENT_REQUIRED
            # construction — implementer fills these in based on the grep from
            # the start of this subtask.
        )
        return _demote_low_confidence(synthetic, confidence_threshold)

    def _attempt() -> AuditVerdict:
        response = client.call(PROMPT_PATH, user_section)
        return _parse_verdict(response.content, doc)

    verdict = _call_with_retry(_attempt, no_retry=no_retry)
    return _demote_low_confidence(verdict, confidence_threshold)
```

The estimator only sees `user_section` (per `_build_prompt`'s output); the system prompt (`PROMPT_PATH` content) is loaded by `client.call`. The 20K-token margin is intentionally generous to cover the system prompt. If implementer thinks the system prompt is so large that this margin is insufficient, they can add the system prompt's char count to the estimate — but the simpler approach (user-section only + generous margin) is preferred.

**CRITICAL**: Do NOT remove the existing `_call_with_retry` call site. The guard is an early-return; the original retry path stays intact for below-threshold prompts.

**Validation**:
- [ ] `_interpret_one_doc` has guard check after `_build_prompt` and before `_attempt`
- [ ] Over-threshold path short-circuits with synthetic verdict
- [ ] Under-threshold path proceeds to existing `_call_with_retry` unchanged
- [ ] Synthetic verdict goes through `_demote_low_confidence` (FR-007)

### T003 — Unit tests for AS1 + AS2

**Steps**:
1. Open `tests/doc_audit/judgment/test_audit_interpretation.py`. Read existing patterns; sibling tests should already use a mocked `JudgmentClient` for `_interpret_one_doc` or `interpret_audit`.

2. Add tests:

```python
def test_interpret_one_doc_short_circuits_on_oversized_prompt(monkeypatch):
    """AS1: when estimated tokens >= threshold, no LLM call is made."""
    from doc_audit.judgment.audit_interpretation import (
        INPUT_TOKEN_GUARD_THRESHOLD,
        _interpret_one_doc,
    )
    # Build a doc whose _build_prompt output will be huge.
    # Use a known-large doc body + a diff that pushes prompt over threshold.
    huge_doc = make_doc_target(path="docs/big.md", contents="x" * (INPUT_TOKEN_GUARD_THRESHOLD * 4 + 1000))
    huge_context = make_context_with_doc(huge_doc)

    call_count = {"n": 0}
    class FakeClient:
        def call(self, *args, **kwargs):
            call_count["n"] += 1
            raise AssertionError("client.call should not be invoked when over threshold")

    verdict = _interpret_one_doc(FakeClient(), huge_doc, huge_context,
                                  confidence_threshold=0.7, no_retry=True)

    assert call_count["n"] == 0  # zero API calls
    assert verdict.outcome == AuditOutcome.JUDGMENT_REQUIRED
    assert verdict.confidence == 0.0
    assert "size-guard short-circuit" in verdict.rationale
    assert "oversized prompt" in verdict.rationale


def test_interpret_one_doc_proceeds_on_normal_prompt(monkeypatch):
    """AS2: under-threshold prompts proceed to LLM call as before."""
    from doc_audit.judgment.audit_interpretation import _interpret_one_doc
    small_doc = make_doc_target(path="docs/small.md", contents="hello world")
    small_context = make_context_with_doc(small_doc)

    call_count = {"n": 0}
    class FakeClient:
        def call(self, *args, **kwargs):
            call_count["n"] += 1
            return make_fake_llm_response(verdict="NO_CHANGE_NEEDED", confidence=0.9, rationale="ok")

    verdict = _interpret_one_doc(FakeClient(), small_doc, small_context,
                                  confidence_threshold=0.7, no_retry=True)

    assert call_count["n"] == 1  # exactly one API call
    # outcome shape depends on _parse_verdict's behavior on the fake response
```

3. The helper names (`make_doc_target`, `make_context_with_doc`, `make_fake_llm_response`) are placeholders — use whatever fixtures / factories the existing test file already establishes. Read the file's first 100 lines to find the patterns.

**Validation**:
- [ ] AS1 test asserts ZERO `client.call` invocations on over-threshold prompts
- [ ] AS2 test asserts EXACTLY ONE `client.call` invocation on under-threshold prompts
- [ ] Both tests pass

### T004 — Unit tests for AS3 + AS4 + AS5

**Steps**:
1. Add tests:

```python
def test_estimate_input_tokens_is_conservative():
    """AS3: estimator over-counts rather than under-counts."""
    from doc_audit.judgment.audit_interpretation import _estimate_input_tokens
    # Empty input
    assert _estimate_input_tokens("") == 1
    assert _estimate_input_tokens(None or "") == 1  # defensive
    # 4-char input → 1 token (ceiling-divide-by-4 of 4 = 1)
    assert _estimate_input_tokens("abcd") == 1
    # 5-char input → 2 tokens (ceiling-divide-by-4 of 5 = 2) — over-count vs floor
    assert _estimate_input_tokens("abcde") == 2
    # 1000-char input → 251 tokens (ceiling)
    assert _estimate_input_tokens("x" * 1000) == 251


def test_synthetic_verdict_matches_existing_judgment_required_shape():
    """AS4: size-guard synthetic verdict is structurally indistinguishable
    from the existing retry-exhausted synthetic verdict (only rationale differs)."""
    from doc_audit.judgment.audit_interpretation import (
        AuditOutcome,
        INPUT_TOKEN_GUARD_THRESHOLD,
        _interpret_one_doc,
    )
    huge_doc = make_doc_target(path="docs/big.md", contents="y" * (INPUT_TOKEN_GUARD_THRESHOLD * 4 + 1000))
    huge_context = make_context_with_doc(huge_doc)
    class FakeClient:
        def call(self, *args, **kwargs):
            raise AssertionError("should not be called")
    verdict = _interpret_one_doc(FakeClient(), huge_doc, huge_context,
                                  confidence_threshold=0.7, no_retry=True)
    # Shape parity with existing JUDGMENT_REQUIRED verdicts
    assert verdict.outcome == AuditOutcome.JUDGMENT_REQUIRED
    assert verdict.confidence == 0.0
    assert verdict.doc_path == "docs/big.md"
    # rationale is the only distinguishing feature
    assert "size-guard short-circuit" in verdict.rationale


def test_threshold_constant_exists_and_is_tunable():
    """AS5: INPUT_TOKEN_GUARD_THRESHOLD is module-level and named for easy tuning."""
    from doc_audit.judgment import audit_interpretation
    assert hasattr(audit_interpretation, "INPUT_TOKEN_GUARD_THRESHOLD")
    assert isinstance(audit_interpretation.INPUT_TOKEN_GUARD_THRESHOLD, int)
    # Sanity: leave at least 10% margin under 200K
    assert audit_interpretation.INPUT_TOKEN_GUARD_THRESHOLD <= 180_000
```

2. Adjust import paths and fixture helpers to match the existing test file. If `AuditOutcome` is imported differently, adapt.

**Validation**:
- [ ] AS3 (estimator conservatism) test passes
- [ ] AS4 (verdict shape parity) test passes
- [ ] AS5 (constant tunability) test passes

### T005 — Pytest + commit + transition

**Steps**:
```bash
cd <worktree-path>
pytest tests/doc_audit/ -v
```
Zero failures required.

```bash
git status
git add scripts/doc_audit/judgment/audit_interpretation.py tests/doc_audit/judgment/test_audit_interpretation.py
git diff --cached
git commit -m "fix(WP01): add input-token size guard in audit_interpretation (closes #402 root cause)

Oversized audit prompts now short-circuit to synthetic JUDGMENT_REQUIRED
before the LLM call, instead of burning 4 × ~50s retries on a
guaranteed-400 request. Threshold INPUT_TOKEN_GUARD_THRESHOLD=180_000
leaves ~10% margin under Haiku 4.5's 200K context window.

Char-based estimator (_estimate_input_tokens) is conservative — over-counts
near threshold for safer guard behavior. Synthetic verdict mirrors the
existing retry-exhausted JUDGMENT_REQUIRED shape; only rationale differs.

Diff truncation (Option B) and drift_interpretation guard (C-004) deferred
to follow-up missions if needed."

spec-kitty agent tasks mark-status T001 T002 T003 T004 T005 --status done --mission audit-interpretation-size-guard-01KSEN9B

spec-kitty agent tasks move-task WP01 --to for_review --mission audit-interpretation-size-guard-01KSEN9B --note "Helper + guard + tests landed; ready for review"
```

## Hard rules

- Stay within `owned_files`. No prompt change. No drift_interpretation change.
- Synthetic verdict shape must match existing JUDGMENT_REQUIRED construction (FR-008).
- Do not push to origin.
- All pytest must pass before move-task.

## Definition of Done

- [ ] Constant + estimator + guard wired
- [ ] AS1–AS5 unit tests pass
- [ ] Full pytest green
- [ ] WP01 transitioned to for_review

## Branch / Implement / Review Commands

```bash
spec-kitty agent action implement WP01 --agent claude:opus:python-implementer:implementer --mission audit-interpretation-size-guard-01KSEN9B
spec-kitty agent tasks move-task WP01 --to for_review --mission audit-interpretation-size-guard-01KSEN9B --note "Ready for review"
spec-kitty agent action review WP01 --agent codex:gpt-5:spec-kitty-review:reviewer --mission audit-interpretation-size-guard-01KSEN9B
```
