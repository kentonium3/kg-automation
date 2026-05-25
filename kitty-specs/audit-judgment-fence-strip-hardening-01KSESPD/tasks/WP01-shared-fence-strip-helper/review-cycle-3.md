---
affected_files: []
cycle_number: 3
mission_slug: audit-judgment-fence-strip-hardening-01KSESPD
reproduction_command:
reviewed_at: '2026-05-25T06:03:31Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: The required coverage validation path does not measure the helper.

`tests/doc_audit/judgment/test_llm_response.py` imports `_strip_code_fence` from `doc_audit.judgment._llm_response`, but WP01's validation requires `pytest --cov=scripts.doc_audit.judgment._llm_response tests/doc_audit/judgment/test_llm_response.py`. Running that required command produces coverage warnings that `scripts.doc_audit.judgment._llm_response` was never imported and no coverage report is generated, so the WP cannot demonstrate the required >=95% branch coverage on the specified module path.

Fix by aligning the test/import surface with the WP's required module path, or otherwise updating the implementation so the exact required coverage command reports coverage for `_strip_code_fence`.

**Issue 2**: `test_drift_interpretation.py` still imports `_strip_code_fence` through `drift_interpretation`.

T004 says that if the existing drift test file imports `_strip_code_fence` directly from `drift_interpretation`, update that import to the shared module path. The current file still includes `_strip_code_fence` in the `from doc_audit.judgment.drift_interpretation import (...)` block, so the white-box helper tests continue to bind through the old owning module instead of the new shared helper module.

Fix by moving that test import to the shared helper module and leaving the rest of the drift test changes scoped to that import adjustment.

Downstream note: WP02 depends on WP01, so WP02 agents should rebase after this WP is corrected.
