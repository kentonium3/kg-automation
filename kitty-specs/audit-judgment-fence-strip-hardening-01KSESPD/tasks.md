# Tasks: Audit Judgment Fence-Strip Hardening

**Mission**: `audit-judgment-fence-strip-hardening-01KSESPD`
**Planning base**: `main`
**Merge target**: `main`
**Branch matches target**: yes
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Source issue**: [GitHub #416](https://github.com/kentonium3/kg-automation/issues/416)

## Overview

Two work packages. WP01 introduces the shared `_strip_code_fence` helper and re-points the already-fixed `drift_interpretation` to it. WP02 depends on WP01 and applies the helper at the three remaining vulnerable call sites with regression coverage. Combined: 11 subtasks across 2 WPs.

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `scripts/doc_audit/judgment/_llm_response.py` with `_strip_code_fence` extracted verbatim | WP01 | | [D] |
| T002 | Create `tests/doc_audit/judgment/test_llm_response.py` covering FR-006/007 + edge cases | WP01 | [P after T001] | [D] |
| T003 | Re-point `drift_interpretation.py` to import shared helper; remove local def | WP01 | | [D] |
| T004 | Verify `test_drift_interpretation.py` still passes after re-point | WP01 | | [D] |
| T005 | Patch `audit_interpretation.py` line 289 — import + apply helper | WP02 | [P] |
| T006 | Add fenced + unfenced regression cases to `test_audit_interpretation.py` | WP02 | [P after T005] |
| T007 | Patch `cross_file_implication.py` line 151 — import + apply helper | WP02 | [P] |
| T008 | Add fenced + unfenced regression cases to `test_cross_file_implication.py` | WP02 | [P after T007] |
| T009 | Patch `tier_classification.py` line 157 — import + apply helper | WP02 | [P] |
| T010 | Add fenced + unfenced regression cases to `test_tier_classification.py` | WP02 | [P after T009] |
| T011 | Run full `pytest tests/doc_audit/judgment/ -v`; confirm all pass | WP02 | |

The `[P]` markers indicate parallel-safe items in WP02 — the three script patches touch different files and can be done in any order or simultaneously by an agent.

## WP01 — Shared `_strip_code_fence` foundation

**Goal**: Establish the canonical shared helper module and migrate `drift_interpretation` (the previously-fixed site) to use it. No behavior change for `drift_interpretation`; the migration is a refactor that prevents future divergence.

**Priority**: P0 (blocks WP02).

**Independent test**: `pytest tests/doc_audit/judgment/test_llm_response.py tests/doc_audit/judgment/test_drift_interpretation.py` passes on a fresh checkout with WP01 applied.

**Prompt**: [`tasks/WP01-shared-fence-strip-helper.md`](tasks/WP01-shared-fence-strip-helper.md)

**Estimated prompt size**: ~280 lines.

**Included subtasks**:

- [x] T001 Create `scripts/doc_audit/judgment/_llm_response.py` with `_strip_code_fence` extracted verbatim (WP01)
- [x] T002 Create `tests/doc_audit/judgment/test_llm_response.py` covering FR-006/007 + edge cases (WP01)
- [x] T003 Re-point `drift_interpretation.py` to import shared helper; remove local def (WP01)
- [x] T004 Verify `test_drift_interpretation.py` still passes after re-point (WP01)

**Implementation sketch**:
1. Copy lines 436-458 of `drift_interpretation.py` into a new `_llm_response.py` (preserve the docstring; add a module-level docstring explaining the helper is private to `scripts/doc_audit/judgment/`).
2. Write `test_llm_response.py` enumerating the helper's behavior: fenced-with-tag, fenced-without-tag, fenced-with-whitespace, unfenced (identity), empty, whitespace-only, fenced-but-malformed-inside.
3. In `drift_interpretation.py`, add an import line (placed with other absolute-import siblings near the top of the module) and delete the local `_strip_code_fence` definition (lines 436-458 inclusive).
4. Run the existing `test_drift_interpretation.py` to confirm zero regression. If a test specifically references the local helper symbol, update the import in the test as well.

**Parallel opportunities**: T002 can start as soon as T001 has the module skeleton.

**Dependencies**: None (foundational WP).

**Risks**: Low. The implementation is being moved, not rewritten. Risk vectors are limited to (a) misplacing the import, (b) accidentally introducing a typo during the copy. Both are caught by the existing test suite.

## WP02 — Apply helper at three remaining vulnerable sites

**Goal**: Wire the shared helper into the three previously-undefended `json.loads()` call sites and add regression coverage at each site.

**Priority**: P0 (completes the bug-class fix; restores doc-auditor for timer re-enable).

**Independent test**: `pytest tests/doc_audit/judgment/` passes; per spec SC-001, a post-merge office2 tick shows zero `_RetrySchemaError` lines from any of the three protected scripts.

**Prompt**: [`tasks/WP02-apply-helper-three-sites.md`](tasks/WP02-apply-helper-three-sites.md)

**Estimated prompt size**: ~440 lines.

**Included subtasks**:

- [ ] T005 Patch `audit_interpretation.py` line 289 — import + apply helper (WP02)
- [ ] T006 Add fenced + unfenced regression cases to `test_audit_interpretation.py` (WP02)
- [ ] T007 Patch `cross_file_implication.py` line 151 — import + apply helper (WP02)
- [ ] T008 Add fenced + unfenced regression cases to `test_cross_file_implication.py` (WP02)
- [ ] T009 Patch `tier_classification.py` line 157 — import + apply helper (WP02)
- [ ] T010 Add fenced + unfenced regression cases to `test_tier_classification.py` (WP02)
- [ ] T011 Run full `pytest tests/doc_audit/judgment/ -v`; confirm all pass (WP02)

**Implementation sketch**:
1. For each of the three scripts (`audit_interpretation.py`, `cross_file_implication.py`, `tier_classification.py`):
   a. Add an import: `from doc_audit.judgment._llm_response import _strip_code_fence` (placed alongside other absolute imports; the codebase uses `doc_audit.X` form thanks to the conftest sys.path bootstrap).
   b. Change the `json.loads(text)` (or equivalent variable name) call to `json.loads(_strip_code_fence(text))` at the documented line.
2. For each script's test file, add at least one fenced-input regression case (input wrapped in ` ```json\n…\n``` `) and at least one unfenced-input regression case (input is bare JSON). Each case asserts that the relevant parser function produces the expected verdict/data structure.
3. Run the full judgment-package test suite to confirm no regressions.

**Parallel opportunities**: The three (script-patch + test-extension) pairs are file-independent and can be executed in any order. An agent working from this prompt can choose to handle one script at a time end-to-end OR all three patches first then all three test extensions.

**Dependencies**: WP01 (shared helper must exist before this WP's imports resolve).

**Risks**:
- **R-WP02-001** (low) — A previously-passing test in one of the three scripts could break if a test mocks `_parse_verdict`-or-equivalent in a way that bypasses `_strip_code_fence`. Mitigation: run the full judgment-package suite after each patch; investigate failures by reading the test, not by rewriting the helper.
- **R-WP02-002** (low) — Line numbers may shift after T005's edit if subsequent edits change line counts. Mitigation: the prompt identifies sites by symbol/context, not by absolute line number alone.

## Branch Strategy

All planning artifacts (this file plus prompts) commit to `main`. Implementation work happens in execution lanes assigned at `finalize-tasks` time; each lane gets one worktree. WP02 depends on WP01 — `finalize-tasks` may assign them to the same lane (since the dependency is sequential and there are only two WPs).

## MVP Recommendation

Both WPs are required. WP01 is the foundation; WP02 is the consumer. There is no smaller useful slice — landing WP01 alone leaves `audit_interpretation`, `cross_file_implication`, and `tier_classification` unprotected, and the doc-auditor timer cannot be re-enabled. Treat the two WPs as a single deliverable for operator purposes.
