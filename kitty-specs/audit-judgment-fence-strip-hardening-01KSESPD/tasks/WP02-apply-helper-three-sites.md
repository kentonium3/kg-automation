---
work_package_id: WP02
title: Apply shared helper at three remaining vulnerable sites
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-003
- FR-004
- FR-006
- FR-007
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T005
- T006
- T007
- T008
- T009
- T010
- T011
agent: "claude:opus-4-7:python-implementer:implementer"
shell_pid: "23944"
history:
- event: created
  by: spec-kitty.tasks orchestrator
  at: '2026-05-25T05:35:51Z'
authoritative_surface: scripts/doc_audit/judgment/audit_interpretation.py
execution_mode: code_change
owned_files:
- scripts/doc_audit/judgment/audit_interpretation.py
- scripts/doc_audit/judgment/cross_file_implication.py
- scripts/doc_audit/judgment/tier_classification.py
- tests/doc_audit/judgment/test_audit_interpretation.py
- tests/doc_audit/judgment/test_cross_file_implication.py
- tests/doc_audit/judgment/test_tier_classification.py
tags: []
---

# WP02 — Apply shared helper at three remaining vulnerable sites

**Mission**: `audit-judgment-fence-strip-hardening-01KSESPD`
**Source issue**: [GitHub #416](https://github.com/kentonium3/kg-automation/issues/416)
**Spec**: [../spec.md](../spec.md)
**Plan**: [../plan.md](../plan.md)

## Objective

Wire the shared `_strip_code_fence` helper (introduced by WP01 at `scripts/doc_audit/judgment/_llm_response.py`) into the three remaining vulnerable `json.loads()` call sites in the doc-audit judgment pipeline: `audit_interpretation.py` line 289, `cross_file_implication.py` line 151, and `tier_classification.py` line 157. Add fenced + unfenced regression coverage at each site. Confirm the full judgment-package test suite passes. After this WP merges, `felix-doc-auditor.timer` can be re-enabled (the timer is currently disabled per spec User Scenarios).

## Context

The same Haiku-4.5 fence-wrap bug class affects four judgment scripts. Mission #55 fixed it in `drift_interpretation.py` only. Pre-mission analysis confirmed three more vulnerable sites:

| File:line | Function | LLM-response call |
|---|---|---|
| `audit_interpretation.py:289` | `_parse_verdict` | `parsed = json.loads(text)` |
| `cross_file_implication.py:151` | parse helper | `parsed = json.loads(text)` |
| `tier_classification.py:157` | parse helper | `parsed = json.loads(text)` |

WP01 has already established the shared helper. WP02 patches the call sites. Without this WP, `audit_interpretation` (and likely the two siblings under load) burns four retries per failed call (~3.5 min wall-clock) on `_RetrySchemaError`, and the timer remains disabled.

## Branch Strategy

- **Planning base**: `main`
- **Merge target**: `main`
- **Dependency**: WP01 must complete first so the import target exists.
- The execution worktree for this WP is allocated by `spec-kitty agent action implement WP02 --agent <name>`. If `finalize-tasks` places WP01 and WP02 in the same lane, they share a worktree and the lane's base already includes WP01's commits. Implementation commits go into that worktree; merge happens at `/spec-kitty.merge`.

## Subtasks

### T005 — Patch `audit_interpretation.py` (line 289)

**Purpose**: Apply the shared helper at the line currently causing `_RetrySchemaError` failures in operational verification.

**Steps**:
1. Open `scripts/doc_audit/judgment/audit_interpretation.py`.
2. Add an import near the top of the file (with other absolute imports): `from doc_audit.judgment._llm_response import _strip_code_fence`.
3. Locate the call site. As of pre-mission verification it is at line 289:
   ```python
   parsed = json.loads(text)
   ```
   Note: line numbers may shift slightly after the import addition; locate by surrounding context (it is inside `_parse_verdict`, immediately after a `try:` block opens, the variable name is `text`).
4. Change the call to:
   ```python
   parsed = json.loads(_strip_code_fence(text))
   ```
5. No other changes to this file. Specifically: do NOT touch the size guard logic introduced by mission #56; the 180K-token threshold remains as-is (spec C-005).

**Files**:
- `scripts/doc_audit/judgment/audit_interpretation.py` (modified — 1 added import, 1 modified call line)

**Validation**:
- [ ] `grep -n "_strip_code_fence" scripts/doc_audit/judgment/audit_interpretation.py` shows the import and the call site.
- [ ] The module imports cleanly via pytest: `pytest tests/doc_audit/judgment/test_audit_interpretation.py -v` (the conftest at `tests/doc_audit/conftest.py` puts `scripts/` on sys.path; the codebase uses the `doc_audit.X` form, not `scripts.doc_audit.X`).
- [ ] No accidental change to the size-guard logic — diff this file before commit and confirm only the import and the one `json.loads` line changed.

### T006 — Regression tests in `test_audit_interpretation.py`

**Purpose**: Lock in the fence-handling behavior at `audit_interpretation._parse_verdict` so the bug cannot silently regress.

**Steps**:
1. Open `tests/doc_audit/judgment/test_audit_interpretation.py`.
2. Add at least one test that calls `_parse_verdict` (or whichever public surface exercises line 289) with a fenced input string that wraps valid JSON. Example shape:
   ```python
   fenced_input = "```json\n" + valid_json_str + "\n```"
   verdict = _parse_verdict(fenced_input, fixture_context)
   assert verdict.<field> == <expected>
   ```
   Construct `fixture_context` and `valid_json_str` using the same factories/fixtures the existing test file uses for other `_parse_verdict` tests; if no such factory exists, follow the pattern in `test_drift_interpretation.py` for inspiration.
3. Add at least one corresponding unfenced regression case: same JSON content, no fences. Assert the same parse result.
4. The two regression cases should be functionally distinct tests (separate `def test_*` functions), each with a descriptive name (e.g., `test_parse_verdict_strips_json_fenced_response`, `test_parse_verdict_handles_unfenced_response`).

**Files**:
- `tests/doc_audit/judgment/test_audit_interpretation.py` (modified — 2 added test functions, ~30-40 lines added)

**Validation**:
- [ ] `pytest tests/doc_audit/judgment/test_audit_interpretation.py -v -k "fenced or unfenced"` runs and the new tests pass.
- [ ] All pre-existing tests in the file still pass.

### T007 — Patch `cross_file_implication.py` (line 151)

**Purpose**: Apply the shared helper at the cross-file-implication call site.

**Steps**:
1. Open `scripts/doc_audit/judgment/cross_file_implication.py`.
2. Add an import: `from doc_audit.judgment._llm_response import _strip_code_fence`.
3. Locate the call site (line 151, inside a parse helper, `parsed = json.loads(text)`); change to `parsed = json.loads(_strip_code_fence(text))`.
4. No other changes to this file.

**Files**:
- `scripts/doc_audit/judgment/cross_file_implication.py` (modified — 1 added import, 1 modified call line)

**Validation**:
- [ ] `grep -n "_strip_code_fence" scripts/doc_audit/judgment/cross_file_implication.py` shows the import and the call site.
- [ ] The module imports cleanly.

### T008 — Regression tests in `test_cross_file_implication.py`

**Purpose**: Lock in the fence-handling behavior at the cross-file-implication parse site.

**Steps**:
1. Open `tests/doc_audit/judgment/test_cross_file_implication.py`.
2. Add at least one fenced-input regression test exercising the function that calls `json.loads` at line 151. Use the same general shape as T006: build a fenced wrapper around a valid JSON fixture, call the parser, assert correct output.
3. Add at least one unfenced regression test with identical content.
4. Use descriptive test names matching the existing file's conventions.

**Files**:
- `tests/doc_audit/judgment/test_cross_file_implication.py` (modified — 2 added test functions)

**Validation**:
- [ ] `pytest tests/doc_audit/judgment/test_cross_file_implication.py -v -k "fenced or unfenced"` runs and the new tests pass.
- [ ] All pre-existing tests in the file still pass.

### T009 — Patch `tier_classification.py` (line 157)

**Purpose**: Apply the shared helper at the tier-classification call site.

**Steps**:
1. Open `scripts/doc_audit/judgment/tier_classification.py`.
2. Add an import: `from doc_audit.judgment._llm_response import _strip_code_fence`.
3. Locate the call site (line 157, inside a parse helper, `parsed = json.loads(text)`); change to `parsed = json.loads(_strip_code_fence(text))`.
4. No other changes to this file.

**Files**:
- `scripts/doc_audit/judgment/tier_classification.py` (modified — 1 added import, 1 modified call line)

**Validation**:
- [ ] `grep -n "_strip_code_fence" scripts/doc_audit/judgment/tier_classification.py` shows the import and the call site.
- [ ] The module imports cleanly.

### T010 — Regression tests in `test_tier_classification.py`

**Purpose**: Lock in the fence-handling behavior at the tier-classification parse site.

**Steps**:
1. Open `tests/doc_audit/judgment/test_tier_classification.py`.
2. Add at least one fenced-input regression test exercising the function that calls `json.loads` at line 157. Existing fixture variants at `tests/doc_audit/fixtures/anthropic_responses/tier_classification_tier_*.json` may help you construct a realistic input; but the regression case itself should be inline (per planning D-003).
3. Add at least one unfenced regression test with identical content.
4. Use descriptive test names matching the existing file's conventions.

**Files**:
- `tests/doc_audit/judgment/test_tier_classification.py` (modified — 2 added test functions)

**Validation**:
- [ ] `pytest tests/doc_audit/judgment/test_tier_classification.py -v -k "fenced or unfenced"` runs and the new tests pass.
- [ ] All pre-existing tests in the file still pass.

### T011 — Full judgment-package test sweep

**Purpose**: Confirm zero regressions across the entire judgment-package test surface.

**Steps**:
1. From the lane worktree root: `pytest tests/doc_audit/judgment/ -v`.
2. Confirm all tests pass — no failures, no errors. Skips that pre-date this WP are acceptable.
3. If any failures occur, investigate immediately. Likely causes: a test mocks the parse path in a way that bypasses `_strip_code_fence` (revisit the test, not the helper); a typo in one of T005/T007/T009's edits; an import-order issue. Do NOT alter the shared helper to "fix" the issue — the helper is canonical from WP01.

**Files**: none (this is a verification step).

**Validation**:
- [ ] `pytest tests/doc_audit/judgment/ -v` completes with exit code 0.
- [ ] No new test was skipped beyond pre-existing skips.

## Definition of Done

- [ ] All seven subtasks (T005-T011) marked complete.
- [ ] All three target source files have an import for `_strip_code_fence` from `_llm_response`.
- [ ] All three target source files have their `json.loads(text)` call replaced with `json.loads(_strip_code_fence(text))`.
- [ ] All three target test files have at least one fenced + one unfenced regression case.
- [ ] `pytest tests/doc_audit/judgment/ -v` is fully green.
- [ ] No file outside this WP's `owned_files` list was modified.
- [ ] No prompt template under `scripts/doc_audit/prompts/` was modified (C-003).
- [ ] No systemd unit was modified (C-004).
- [ ] The 180K-token size guard from mission #56 in `audit_interpretation.py` is intact (C-005).

## Operational verification (out of WP scope, but informs success criteria)

After WP02 merges and operator pulls on office2:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'
ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
# wait ~3-5 minutes
ssh office2-claude 'journalctl --user -u felix-doc-auditor.service -n 200 --no-pager'
```

Per spec SC-001/SC-002: journal should show zero `_RetrySchemaError` lines attributable to fence-wrapping from any of the three protected scripts; `size-guard short-circuit` lines for oversized prompts; real verdicts for below-threshold prompts. The operator (not this WP's implementer) performs this verification.

## Risks & Mitigations

- **R-WP02-001** (low) — A pre-existing test mocks `_parse_verdict`-or-equivalent in a way that bypasses `_strip_code_fence` and so passes incorrectly. **Mitigation**: T006/T008/T010 each add at least one *fenced-input* test that exercises the real parse path. If a pre-existing test starts failing because it was mocking the unfenced path, that is a signal the test was incomplete — read the test and decide whether to update it or add an additional case.
- **R-WP02-002** (low) — Line numbers may shift after T005 changes `audit_interpretation.py` if subsequent edits modify line counts upstream of the call site. **Mitigation**: This WP's edits are localized; the prompt identifies sites by surrounding context (variable name `text`, function name, `try:` block) as well as line number.
- **R-WP02-003** (low) — A test fixture for one of the three scripts may not include a verdict-producing valid JSON payload, requiring scaffolding. **Mitigation**: Use the same fixture conventions as the existing tests in the same file; if none exist, construct a minimal inline dict + `json.dumps` and wrap it.

## Reviewer Guidance

When reviewing this WP, focus on:

1. **All three call sites patched**: `grep -rn "_strip_code_fence" scripts/doc_audit/judgment/` should show four files (the shared module plus the three patched scripts) plus `drift_interpretation.py` (already-imported in WP01).
2. **No collateral damage**: prompts directory, systemd units, and the size guard logic in `audit_interpretation.py` are untouched. Diff each modified script and confirm only the import + the one call-site line changed.
3. **Test coverage at all three sites**: every test file now has at least one fenced + one unfenced regression case.
4. **All tests pass**: `pytest tests/doc_audit/judgment/ -v` is green in the lane worktree before for-review transition.

## Next: merge

After WP02 lands, `/spec-kitty.merge` consolidates both WPs to `main`. Post-merge, the operator runs the verification per the spec's Primary Scenario and unparks issue #350 / re-enables the timer.

## Activity Log

- 2026-05-25T06:53:05Z – claude:opus-4-7:python-implementer:implementer – shell_pid=23944 – Started implementation via action command
