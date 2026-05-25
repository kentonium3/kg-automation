---
work_package_id: WP01
title: Shared _strip_code_fence helper foundation
dependencies: []
requirement_refs:
- FR-001
- FR-005
- FR-006
- FR-007
- NFR-001
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-audit-judgment-fence-strip-hardening-01KSESPD
base_commit: 29f287299a9f48f428d251f34028fd1e7b5490a5
created_at: '2026-05-25T05:41:05.618029+00:00'
subtasks:
- T001
- T002
- T003
- T004
shell_pid: "19419"
agent: "codex:gpt-5:spec-kitty-review:reviewer"
history:
- event: created
  by: spec-kitty.tasks orchestrator
  at: '2026-05-25T05:35:51Z'
authoritative_surface: scripts/doc_audit/judgment/_llm_response.py
execution_mode: code_change
owned_files:
- scripts/doc_audit/judgment/_llm_response.py
- scripts/doc_audit/judgment/drift_interpretation.py
- tests/doc_audit/judgment/test_llm_response.py
- tests/doc_audit/judgment/test_drift_interpretation.py
tags: []
---

# WP01 — Shared `_strip_code_fence` helper foundation

**Mission**: `audit-judgment-fence-strip-hardening-01KSESPD`
**Source issue**: [GitHub #416](https://github.com/kentonium3/kg-automation/issues/416)
**Spec**: [../spec.md](../spec.md)
**Plan**: [../plan.md](../plan.md)

## Objective

Centralize the existing `_strip_code_fence` markdown-code-fence-stripping helper into a private shared module under `scripts/doc_audit/judgment/`. Re-point `drift_interpretation.py` (the previously-fixed site from mission #55) to import the helper from the shared module instead of defining its own copy. No behavior change for `drift_interpretation`; this WP is a refactor that prevents future divergence between the four judgment scripts.

## Context

Claude Haiku 4.5 wraps every JSON response in markdown code fences (` ```json … ``` `) despite explicit prompt instructions against this. Mission #55 added a defensive parse-side stripper to `drift_interpretation._parse_verdict`. Mission #56 added a 180K-token size guard to `audit_interpretation` that, as a side effect, made the same fence-wrap bug observable in three other call sites. WP01 establishes the canonical helper that WP02 will consume.

The helper's current implementation (mission #55) lives at `scripts/doc_audit/judgment/drift_interpretation.py:436-458` and is reproduced here for reference:

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

## Branch Strategy

- **Planning base**: `main`
- **Merge target**: `main`
- The execution worktree for this WP is allocated by `spec-kitty agent action implement WP01 --agent <name>`. Implementation commits go into that worktree, NOT into the main repo checkout. Merge happens at `/spec-kitty.merge`.

## Subtasks

### T001 — Create the shared module

**Purpose**: Establish `scripts/doc_audit/judgment/_llm_response.py` as the canonical home for the fence-stripping helper.

**Steps**:
1. Create a new file `scripts/doc_audit/judgment/_llm_response.py`.
2. Add a module-level docstring at the top describing the module's purpose: "Private helpers for parsing raw LLM responses in the doc-audit judgment pipeline. Imported by sibling modules under `scripts/doc_audit/judgment/`; not part of the package's public API (single-underscore prefix)."
3. Copy the `_strip_code_fence` function definition (including its docstring) verbatim from `scripts/doc_audit/judgment/drift_interpretation.py` lines 436-458 into the new module. Do not modify the implementation.
4. Confirm the file is syntactically valid Python. The doc-audit codebase puts `scripts/` on `sys.path` via the test conftest at `tests/doc_audit/conftest.py`, so the canonical package root is `doc_audit.X`, not `scripts.doc_audit.X`. Smoke-test: `python -c "import sys; sys.path.insert(0, 'scripts'); import doc_audit.judgment._llm_response as m; print(m._strip_code_fence)"`.

**Files**:
- `scripts/doc_audit/judgment/_llm_response.py` (new, ~25 LoC including docstring)

**Validation**:
- [ ] File exists at the correct path.
- [ ] File parses as Python (no syntax errors).
- [ ] `_strip_code_fence` is callable from a python interpreter import.
- [ ] The function body is byte-for-byte identical to the source in `drift_interpretation.py:436-458` (excluding the relocated docstring, which can remain as-is).

### T002 — Write unit tests for the shared helper

**Purpose**: Lock in the helper's contract with explicit unit tests at ≥ 95% branch coverage (NFR-003) and cover all the edge cases that the spec's User Scenarios section enumerates.

**Steps**:
1. Create a new file `tests/doc_audit/judgment/test_llm_response.py`.
2. Add a module docstring referencing the source module under test.
3. Import the helper using the codebase convention (conftest puts `scripts/` on `sys.path`, so `doc_audit.X` is the package root used throughout `scripts/doc_audit/`): `from doc_audit.judgment._llm_response import _strip_code_fence`.
4. Write one test function per case below. Test names should be descriptive (e.g., `test_fenced_with_json_tag_strips_cleanly`).

**Required test cases** (one assertion each):

| Test case | Input (literal) | Expected output |
|---|---|---|
| Fenced with `json` tag | `` "```json\n{\"foo\": 1}\n```" `` | `'{"foo": 1}'` |
| Fenced without tag | `` "```\n{\"foo\": 1}\n```" `` | `'{"foo": 1}'` |
| Fenced with surrounding whitespace | `` "  \n```json\n{\"foo\": 1}\n```\n  " `` | `'{"foo": 1}'` |
| Unfenced (identity-preserving for JSON) | `'{"foo": 1}'` | `'{"foo": 1}'` |
| Empty string | `""` | `""` |
| Whitespace-only | `"   \n  \t  "` | `"   \n  \t  "` (input returned unchanged because no fence) |
| Fenced but malformed JSON inside | `` "```json\n{not valid\n```" `` | `'{not valid'` (helper does not validate JSON; it only strips fences) |

**Notes on test style**:
- Use `pytest`'s plain `assert` style.
- For the unfenced case, also assert that `json.loads(_strip_code_fence(input))` round-trips correctly when the input is valid JSON — this documents the helper's no-op-on-unfenced behavior (FR-007).
- For the fenced-with-malformed case, do NOT call `json.loads` on the output; the test is about the helper's behavior, not downstream parsing.

**Files**:
- `tests/doc_audit/judgment/test_llm_response.py` (new, ~80-100 LoC)

**Validation**:
- [ ] `pytest tests/doc_audit/judgment/test_llm_response.py -v` runs and all tests pass.
- [ ] Branch coverage on `_strip_code_fence` is ≥ 95% (verify with `pytest --cov=doc_audit.judgment._llm_response tests/doc_audit/judgment/test_llm_response.py`).

### T003 — Re-point `drift_interpretation` to the shared helper

**Purpose**: Delete the local `_strip_code_fence` from `drift_interpretation.py` and use the shared one. Zero behavior change at runtime.

**Steps**:
1. Open `scripts/doc_audit/judgment/drift_interpretation.py`.
2. Locate the existing absolute imports near the top of the file. The codebase uses the `doc_audit.X` form for intra-package imports (see `from doc_audit.judgment.client import JudgmentClient` in this same file pre-edit). Match that convention. Add a new line: `from doc_audit.judgment._llm_response import _strip_code_fence`. Place it alphabetically with the other intra-package imports if such an ordering exists; otherwise group it logically with adjacent imports.
3. Delete the local `_strip_code_fence` function definition (lines 436-458, inclusive of the trailing blank line if it serves as a separator before the next definition). Verify the call site at the previous line 477 still references the symbol — it will now resolve to the shared import.
4. Confirm the module imports cleanly post-edit. The canonical verification is `pytest tests/doc_audit/judgment/test_drift_interpretation.py -v` (uses the conftest sys.path bootstrap). For a standalone one-liner smoke test, set the path first: `python -c "import sys; sys.path.insert(0, 'scripts'); from doc_audit.judgment.drift_interpretation import _parse_verdict; print(_parse_verdict)"`.

**Files**:
- `scripts/doc_audit/judgment/drift_interpretation.py` (modified — 1 added import line, ~23 deleted lines)

**Validation**:
- [ ] The local `_strip_code_fence` definition is gone from `drift_interpretation.py`.
- [ ] An `import` line for the shared helper appears near the top of the file.
- [ ] The module imports without errors.
- [ ] `grep -n _strip_code_fence scripts/doc_audit/judgment/drift_interpretation.py` shows the import line and the existing call site only (no local def).

### T004 — Verify `test_drift_interpretation.py` still passes

**Purpose**: Confirm zero regression. Mission #55's existing test coverage continues to pass after the re-point.

**Steps**:
1. Run `pytest tests/doc_audit/judgment/test_drift_interpretation.py -v`.
2. If the test file imports `_strip_code_fence` directly from `drift_interpretation` (e.g., for white-box testing), update the import to use the new shared module path: `from doc_audit.judgment._llm_response import _strip_code_fence` (codebase convention; conftest at `tests/doc_audit/conftest.py` puts `scripts/` on sys.path). No other test changes should be required.
3. Confirm all tests pass.

**Files**:
- `tests/doc_audit/judgment/test_drift_interpretation.py` (modified ONLY if it imports `_strip_code_fence` directly — likely no change)

**Validation**:
- [ ] `pytest tests/doc_audit/judgment/test_drift_interpretation.py -v` passes with no failures, no errors, no skips beyond any that were already skipped pre-WP.
- [ ] If the test file was modified, the modification is limited to the one import line.

## Definition of Done

- [ ] All four subtasks (T001-T004) marked complete.
- [ ] `scripts/doc_audit/judgment/_llm_response.py` exists and exports `_strip_code_fence`.
- [ ] `tests/doc_audit/judgment/test_llm_response.py` exists and passes at ≥ 95% branch coverage on the helper.
- [ ] `scripts/doc_audit/judgment/drift_interpretation.py` no longer contains a local `_strip_code_fence`; it imports from the shared module.
- [ ] `pytest tests/doc_audit/judgment/test_llm_response.py tests/doc_audit/judgment/test_drift_interpretation.py -v` is fully green.
- [ ] No file outside this WP's `owned_files` list was modified.

## Risks & Mitigations

- **Risk**: Misplacing the import (e.g., introducing a circular import). **Mitigation**: The shared module has no imports from any other doc-audit module; it's a leaf. Circular import is structurally impossible.
- **Risk**: Subtle typo during the copy of the helper's body. **Mitigation**: T002's tests exercise the helper's edge cases; T004's existing tests exercise its integration with `_parse_verdict`. Both must pass.
- **Risk**: The existing test file imports `_strip_code_fence` from `drift_interpretation` for white-box testing, requiring a test-file edit. **Mitigation**: T004's step 2 covers this.

## Reviewer Guidance

When reviewing this WP, focus on:

1. **Faithful extraction**: The function body in `_llm_response.py` must match the source in `drift_interpretation.py:436-458` (pre-edit) byte-for-byte. Any divergence is a red flag.
2. **Import correctness**: The new import line in `drift_interpretation.py` should resolve. Run the file's tests to verify.
3. **Test coverage**: `test_llm_response.py` should cover all seven cases in T002's table. Branch coverage report should show ≥ 95% on the helper.
4. **No collateral changes**: This WP should NOT modify `audit_interpretation.py`, `cross_file_implication.py`, `tier_classification.py`, or their tests. Those are WP02's domain.

## Next: WP02

After WP01 lands, WP02 imports the same shared helper into the three remaining vulnerable scripts. Implementation command: `spec-kitty agent action implement WP02 --agent <name>`.

## Activity Log

- 2026-05-25T05:41:08Z – claude:opus-4-7:python-implementer:implementer – shell_pid=4249 – Assigned agent via action command
- 2026-05-25T06:00:25Z – claude:opus-4-7:python-implementer:implementer – shell_pid=4249 – Ready for review: shared _strip_code_fence helper extracted; drift_interpretation re-pointed; all tests pass.
- 2026-05-25T06:00:48Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=9123 – Started review via action command
- 2026-05-25T06:05:03Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=9123 – Review reject (cycle 1/3) — codex sandbox failed move-task; orchestrator executing on reviewer's behalf
- 2026-05-25T06:05:09Z – claude:opus-4-7:python-implementer:implementer – shell_pid=10754 – Started implementation via action command
- 2026-05-25T06:13:57Z – claude:opus-4-7:python-implementer:implementer – shell_pid=10754 – Fix cycle 1: aligned test imports with scripts.doc_audit.judgment._llm_response path; coverage command now produces a report; test_drift_interpretation now imports _strip_code_fence from the shared helper module
- 2026-05-25T06:14:20Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=13106 – Started review via action command
- 2026-05-25T06:22:55Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=13106 – Review reject (cycle 2/3) — codex sandbox failed move-task; orchestrator executing on reviewer's behalf. Root cause: WP01 prompt specified scripts.doc_audit.X imports, but codebase convention is from doc_audit.X (conftest adds scripts/ to sys.path). Fix path: align planning artifacts + tests to codebase convention.
- 2026-05-25T06:30:07Z – claude:opus-4-7:python-implementer:implementer – shell_pid=17163 – Started implementation via action command
- 2026-05-25T06:39:36Z – claude:opus-4-7:python-implementer:implementer – shell_pid=17163 – Fix cycle 2: aligned test imports to 'from doc_audit.judgment._llm_response import _strip_code_fence' (codebase convention; conftest puts scripts/ on sys.path). WP01 prompt + planning docs already updated in main (commit 4ec7a02a) to reflect this. All 171 tests pass; coverage now reports 100% on _llm_response.py with --cov=doc_audit.judgment._llm_response.
- 2026-05-25T06:39:43Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=19419 – Started review via action command
