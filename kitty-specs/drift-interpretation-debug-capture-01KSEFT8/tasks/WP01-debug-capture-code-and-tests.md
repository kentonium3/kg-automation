---
work_package_id: WP01
title: Add env-var-gated debug capture to drift_interpretation with unit tests
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-drift-interpretation-debug-capture-01KSEFT8
base_commit: a5e730ce0c6e582abe433e46f6d25580ac39f77d
created_at: '2026-05-25T02:51:48.764448+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
shell_pid: "60752"
agent: "codex:gpt-5:spec-kitty-review:reviewer"
history:
- event: planned
  timestamp: '2026-05-25T02:42:46Z'
  note: Created by /spec-kitty.tasks under mission drift-interpretation-debug-capture-01KSEFT8
authoritative_surface: scripts/doc_audit/judgment/
execution_mode: code_change
mission_slug: drift-interpretation-debug-capture-01KSEFT8
owned_files:
- scripts/doc_audit/judgment/drift_interpretation.py
- tests/doc_audit/judgment/test_drift_interpretation.py
tags: []
---

# WP01 — Add env-var-gated debug capture to drift_interpretation with unit tests

## Objective

Modify `scripts/doc_audit/judgment/drift_interpretation.py` so that when the env var `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` is set, every `_RetrySchemaError` raise site in `_parse_verdict` logs the raw 200-OK LLM response body to stderr at `WARNING` level with the stable prefix `drift_interpretation.schema_fail`, immediately before re-raising the exception. Pair the code change with unit tests covering acceptance scenarios AS1–AS4 from the spec.

The capture is observation-only — it MUST NOT alter the existing exception behavior in any way (same exception type, same message, same retry semantics).

## Context

- This mission is split from issue [#404](https://github.com/kentonium3/kg-automation/issues/404). Read the issue body for background.
- Sibling mission #403 already merged the retry_count crash fix (commit `1b0768c`), so this code path can be exercised on office2 once WP01 merges, without re-triggering the prior crash.
- The full plan is at [`../plan.md`](../plan.md). Read it for the technical context, Charter Check, and risk register.
- Research decisions are in [`../research.md`](../research.md). Key decisions to honor:
  - **R1**: Use stdlib `logging` at WARNING level
  - **R2**: Env var accepts exact string `"1"` only
  - **R3**: Use existing exception messages as raise-site identifiers (no new ID scheme)
  - **R4**: Truncate to 4096 bytes with `[truncated]` suffix
  - **R5**: Tests use inline mock payloads, no external fixtures
- Env var contract is at [`../contracts/env-vars.md`](../contracts/env-vars.md).

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target branch**: `main`
- **Execution lane**: lane allocated by `finalize-tasks` from `lanes.json`; the lane worktree lives at the path printed by `spec-kitty agent context resolve --mission <slug> --wp WP01 --json` (look for `workspace_path`).
- Do NOT create worktrees manually. Use `spec-kitty agent action implement WP01 --agent <name>`. The Python wrapper handles worktree creation.

## Detailed guidance per subtask

### T001 — Add module-level logger setup if not already present

**Purpose**: Ensure `scripts/doc_audit/judgment/drift_interpretation.py` has a module-level `logger` available for the WARNING emissions in T002–T003.

**Steps**:
1. Open `scripts/doc_audit/judgment/drift_interpretation.py`.
2. Grep for `import logging` and `logger = logging.getLogger`. If both exist, T001 is a no-op — move on to T002.
3. If either is missing, add at the top of the imports block:
   ```python
   import logging
   ```
   And in the module-level constants/setup block (alongside `RETRY_DELAYS_SECONDS`):
   ```python
   logger = logging.getLogger(__name__)
   ```

**Files**:
- `scripts/doc_audit/judgment/drift_interpretation.py`

**Validation**:
- [ ] Module imports `logging` at the top of the file
- [ ] Module defines `logger = logging.getLogger(__name__)` at module scope

### T002 — Add `_log_raw_response_if_debug` helper function

**Purpose**: Centralize the env-var gating, truncation, and WARNING emission so the ~10 raise sites in T003 can call a single helper.

**Steps**:
1. Add the helper near other module-private helpers in `drift_interpretation.py` (above `_parse_verdict`, or in the same region as other underscore-prefixed helpers):

   ```python
   _DEBUG_CAPTURE_ENV_VAR = "DOC_AUDIT_DEBUG_DRIFT_PAYLOADS"
   _DEBUG_CAPTURE_MAX_BYTES = 4096


   def _log_raw_response_if_debug(response_text: str, error_message: str) -> None:
       """Emit the raw LLM response body to the log when debug capture is enabled.

       Gated by the env var DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1 (exact match).
       Truncates oversized bodies to _DEBUG_CAPTURE_MAX_BYTES with a [truncated] suffix.
       Emits WARNING-level so the line surfaces in default journalctl output.

       Observation-only — does not raise, return values, or otherwise affect control flow.
       """
       import os  # local import OK; matches existing pattern, avoids touching the import block beyond T001
       if os.environ.get(_DEBUG_CAPTURE_ENV_VAR) != "1":
           return
       if response_text is None:
           body = "<none>"
       else:
           raw = response_text.encode("utf-8", errors="replace")
           if len(raw) > _DEBUG_CAPTURE_MAX_BYTES:
               body = raw[:_DEBUG_CAPTURE_MAX_BYTES].decode("utf-8", errors="replace") + "[truncated]"
           else:
               body = response_text
       logger.warning("drift_interpretation.schema_fail | %s | %s", error_message, body)
   ```

2. Adjust import placement: if the file already imports `os` at module level, drop the `import os` line inside the helper (keep the body cleaner). Confirm by grepping `import os` in the file.

**Files**:
- `scripts/doc_audit/judgment/drift_interpretation.py`

**Validation**:
- [ ] `_log_raw_response_if_debug` exists at module scope
- [ ] Returns early when env var is not the string `"1"`
- [ ] Truncates at 4096 bytes with `[truncated]` suffix
- [ ] Emits at WARNING level via the module logger
- [ ] Handles `None` response_text gracefully (logs `<none>`, not a TypeError)

### T003 — Wire helper into every `_RetrySchemaError` raise site in `_parse_verdict`

**Purpose**: Each existing `raise _RetrySchemaError(...)` site in `_parse_verdict` (and any helpers it calls) gets a paired call to `_log_raw_response_if_debug(response_text, "<the same message>")` immediately before the raise.

**Steps**:
1. Inside `_parse_verdict` (currently at line ~388 of `drift_interpretation.py`, but the implementer should grep to confirm line numbers haven't shifted):
   ```bash
   grep -n "raise _RetrySchemaError" scripts/doc_audit/judgment/drift_interpretation.py
   ```
   Expect ~10 hits, all inside or downstream of `_parse_verdict`.

2. For each hit, identify the local variable holding the raw response text. Most likely names: `response_text`, `response`, `text`, `body`, `raw`. Confirm by inspecting the surrounding lines (typically the line that called `json.loads(response_text)` or similar).

3. Insert one line immediately before each `raise _RetrySchemaError(...)`:
   ```python
   _log_raw_response_if_debug(response_text, "<exact string from the existing _RetrySchemaError(...)>")
   raise _RetrySchemaError("<exact same string>")
   ```

4. Use the same string for both the helper's `error_message` argument and the exception. If the existing raise uses an f-string (e.g., `raise _RetrySchemaError(f"invalid JSON: {exc}")`), pass the same f-string to the helper:
   ```python
   _log_raw_response_if_debug(response_text, f"invalid JSON: {exc}")
   raise _RetrySchemaError(f"invalid JSON: {exc}") from exc
   ```

5. Special cases to watch for:
   - **Per-doc payload validation** (lines ~466, 473): the response_text may be a sub-payload extracted from the top-level response. Pass the variable that holds the substring being validated, not necessarily the top-level body — the diagnostic value is in seeing what failed validation, not always the entire response.
   - **Missing-field raises** (lines ~412, 418, 428, 433): pass the full `response_text` so the operator can see the full structure.
   - **Raises that aren't inside `_parse_verdict`** (e.g., helpers like `_parse_doc_verdict` if it exists): apply the same pattern.

6. After all raise sites are wired, double-check by running:
   ```bash
   grep -B 1 "raise _RetrySchemaError" scripts/doc_audit/judgment/drift_interpretation.py
   ```
   Every `raise _RetrySchemaError` must be preceded by a `_log_raw_response_if_debug` call.

**Files**:
- `scripts/doc_audit/judgment/drift_interpretation.py`

**Validation**:
- [ ] `grep -B 1 "raise _RetrySchemaError" scripts/doc_audit/judgment/drift_interpretation.py` shows a `_log_raw_response_if_debug` line before every raise
- [ ] Exception messages are byte-identical to the pre-change version (no behavior change per FR-006)
- [ ] The implementation does NOT swallow or reorder exceptions

### T004 — Unit tests for AS1 + AS2 + AS3

**Purpose**: Cover the gating behavior: env-var-on + invalid → log captured; env-var-unset + invalid → no log; env-var-on + valid → no log.

**Steps**:
1. Open `tests/doc_audit/judgment/test_drift_interpretation.py`. Read the existing test patterns to understand the mock approach used in the file (look for fixtures like `client`, `mock_response`, etc.).

2. Add a fixture for clearing the debug env var to prevent leakage between tests:
   ```python
   @pytest.fixture
   def clean_debug_env(monkeypatch):
       monkeypatch.delenv("DOC_AUDIT_DEBUG_DRIFT_PAYLOADS", raising=False)
   ```

3. Add three tests:
   ```python
   def test_debug_capture_emits_log_when_env_var_set(monkeypatch, caplog):
       monkeypatch.setenv("DOC_AUDIT_DEBUG_DRIFT_PAYLOADS", "1")
       # Trigger a known-failing parse (e.g., empty response or invalid JSON)
       with caplog.at_level(logging.WARNING):
           with pytest.raises(_RetrySchemaError):
               _parse_verdict("not-valid-json-{")
       # Assert capture is present
       assert any("drift_interpretation.schema_fail" in rec.message for rec in caplog.records)
       # Assert original response text is in the log
       assert any("not-valid-json-{" in rec.message for rec in caplog.records)


   def test_debug_capture_silent_when_env_var_unset(clean_debug_env, caplog):
       with caplog.at_level(logging.WARNING):
           with pytest.raises(_RetrySchemaError):
               _parse_verdict("not-valid-json-{")
       # Assert NO capture
       assert not any("drift_interpretation.schema_fail" in rec.message for rec in caplog.records)


   def test_debug_capture_silent_on_valid_response(monkeypatch, caplog):
       monkeypatch.setenv("DOC_AUDIT_DEBUG_DRIFT_PAYLOADS", "1")
       valid_response = build_valid_drift_response()  # use existing helper or build inline
       with caplog.at_level(logging.WARNING):
           result = _parse_verdict(valid_response)
       assert result is not None
       assert not any("drift_interpretation.schema_fail" in rec.message for rec in caplog.records)
   ```

4. Adjust the function names (`_parse_verdict`, `_RetrySchemaError`) to match the actual exports of `drift_interpretation.py` (these are underscore-prefixed and may need an explicit import or test-module access).

5. The `build_valid_drift_response()` call assumes there's an existing helper. If not, build one inline returning a minimal valid response.

**Files**:
- `tests/doc_audit/judgment/test_drift_interpretation.py`

**Validation**:
- [ ] Three new tests added covering AS1, AS2, AS3
- [ ] Tests use `monkeypatch` + `caplog` (standard pytest fixtures)
- [ ] No env-var leakage between tests (use `clean_debug_env` fixture or `monkeypatch.delenv`)

### T005 — Parametrized unit test for AS4

**Purpose**: Verify each `_RetrySchemaError` raise site (not just one of them) emits a capture line. A parametrized test over `(mock_response, expected_substring_in_log)` does this.

**Steps**:
1. Add a parametrized test:
   ```python
   @pytest.mark.parametrize(
       "mock_response,expected_message_substring",
       [
           ("", "empty LLM response"),
           ("{not-json", "invalid JSON"),
           ('{"missing_field": true}', "missing"),  # adjust to match real schema
           # ... one entry per raise site
       ],
   )
   def test_debug_capture_for_each_raise_site(monkeypatch, caplog, mock_response, expected_message_substring):
       monkeypatch.setenv("DOC_AUDIT_DEBUG_DRIFT_PAYLOADS", "1")
       with caplog.at_level(logging.WARNING):
           with pytest.raises(_RetrySchemaError) as exc_info:
               _parse_verdict(mock_response)
       # Assert capture present
       captures = [rec.message for rec in caplog.records if "drift_interpretation.schema_fail" in rec.message]
       assert captures, f"No capture for response: {mock_response!r}"
       # Assert capture references the expected raise site
       assert any(expected_message_substring in cap for cap in captures)
       # Assert exception message also references the same raise site
       assert expected_message_substring in str(exc_info.value)
   ```

2. The number of parametrized entries should equal (or come close to) the number of distinct `_RetrySchemaError` raise sites in `_parse_verdict`. Implementer enumerates by running:
   ```bash
   grep "raise _RetrySchemaError" scripts/doc_audit/judgment/drift_interpretation.py
   ```
   and crafting a minimal failing input for each.

3. Where a raise site is hard to trigger from `_parse_verdict` alone (e.g., it requires a particular nested structure), use a comment in the parametrize block explaining the case and mock the input accordingly.

**Files**:
- `tests/doc_audit/judgment/test_drift_interpretation.py`

**Validation**:
- [ ] Parametrized test exists with at least 5 cases (covering the most common raise sites)
- [ ] Each case verifies both the log capture AND the exception message
- [ ] Test passes for all cases

### T006 — Confirm full test suite passes; commit; transition WP01 → for_review

**Purpose**: Final pre-review check + handoff.

**Steps**:
1. Run the full test suite from the worktree root:
   ```bash
   cd <worktree_path>
   pytest tests/doc_audit/ -v
   ```
   All tests must pass. If any pre-existing test now fails, investigate — likely T003 changed exception behavior unexpectedly.

2. Verify the changes via `git diff`:
   ```bash
   git diff scripts/doc_audit/judgment/drift_interpretation.py
   git diff tests/doc_audit/judgment/test_drift_interpretation.py
   ```
   Confirm changes match the WP01 plan.

3. Commit:
   ```bash
   git add scripts/doc_audit/judgment/drift_interpretation.py tests/doc_audit/judgment/test_drift_interpretation.py
   git commit -m "feat(WP01): add env-var-gated debug capture to drift_interpretation"
   ```

4. Transition WP01 to `for_review`:
   ```bash
   spec-kitty agent tasks move-task WP01 --to for_review --note "Code + tests landed; ready for review"
   ```

**Files**: (no new files in this subtask — verification + commit + state transition only)

**Validation**:
- [ ] `pytest tests/doc_audit/ -v` passes (zero failures, zero errors)
- [ ] `git diff main` is clean of unrelated changes (only the two files in `owned_files`)
- [ ] Commit lands in the lane branch
- [ ] WP01 lane is `for_review` after `move-task`

## Test Strategy

Unit tests only — no integration tests. The acceptance scenarios AS1–AS4 are all unit-testable via mocked LLM responses and pytest's `caplog` + `monkeypatch`. No live API calls. No office2 dependency for this WP.

The operational verification (a real tick on office2) is WP02's responsibility, not WP01's.

## Definition of Done

- [ ] All 6 subtasks complete (T001–T006)
- [ ] Full pytest suite green
- [ ] New unit tests cover AS1, AS2, AS3, AS4
- [ ] No changes to exception types or messages (FR-006 preserved)
- [ ] No new dependencies added
- [ ] `git diff` shows only the two files in `owned_files`
- [ ] WP01 lane transitioned to `for_review`

## Risks

- **Variable-name drift**: response-text variable may be named differently at different raise sites. Implementer must inspect each raise site individually.
- **Test brittleness**: pre-existing tests may assert "no WARNING-level logs" without using `caplog`. If T003 emits a WARNING and an existing test parses captured stderr without the filter, it could fail spuriously. Investigate and use `caplog.at_level` properly.
- **Import order**: if `os` is not imported at module level, the local `import os` inside the helper is fine for now but slightly inefficient. Acceptable trade-off for keeping the import block untouched.

## Reviewer Guidance

Focus on:
1. **Behavior preservation** — confirm no exception messages or types changed.
2. **Coverage** — confirm every `raise _RetrySchemaError` is preceded by a capture call (grep validation).
3. **Truncation correctness** — confirm 4096-byte truncation works for both small and oversized payloads (the parametrized test should cover this implicitly).
4. **Env-var semantics** — confirm only exact `"1"` enables capture (test AS2 verifies this for the unset case; reviewer should also check the helper code for accidental truthy-evaluation bugs).
5. **No incidental changes** — `git diff` should be tight; reject if it touches unrelated files.

## Branch / Implement / Review Commands

```bash
# Implement (creates lane worktree, claims WP01)
spec-kitty agent action implement WP01 --agent claude --mission drift-interpretation-debug-capture-01KSEFT8

# After committing in the worktree, transition to for_review
spec-kitty agent tasks move-task WP01 --to for_review --note "Code + tests landed; ready for review"

# Review (claimed by codex with the spec-kitty-review profile)
spec-kitty agent action review WP01 --agent codex:gpt-5:spec-kitty-review:reviewer --mission drift-interpretation-debug-capture-01KSEFT8
```

## Activity Log

- 2026-05-25T02:51:51Z – claude:opus:python-implementer:implementer – shell_pid=59443 – Assigned agent via action command
- 2026-05-25T02:56:21Z – claude:opus:python-implementer:implementer – shell_pid=59443 – Code + tests landed; ready for review
- 2026-05-25T02:56:47Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=60752 – Started review via action command
