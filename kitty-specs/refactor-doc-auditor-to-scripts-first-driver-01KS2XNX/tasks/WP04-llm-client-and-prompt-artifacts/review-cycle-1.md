**Issue 1**: `tier_classification` does not treat a missing `rationale` as a schema violation.

The contract and prompt schema require both fields:

```json
{"tier": "tier_a" | "tier_b" | "judgment", "rationale": "<one-line>"}
```

`scripts/doc_audit/judgment/tier_classification.py::_parse_response()` currently allows `{"tier": "tier_a"}` to return `EditTier.TIER_A` with a placeholder rationale. That violates the WP requirement to validate the response schema and safe-default on malformed responses. A missing required field must log and demote to `EditTier.JUDGMENT`, not preserve the LLM's auto-edit tier.

How to fix:
- Update `_parse_response()` so missing/non-string/blank `rationale` is a schema violation that returns `EditTier.JUDGMENT`.
- Update `tests/doc_audit/judgment/test_tier_classification.py::test_classify_missing_rationale_still_returns` or replace it with a test that asserts demotion on missing rationale.

**Issue 2**: `cross_file_implication` keeps implications whose `untouched_file` is outside `in_scope_files`.

The contract says the LLM receives `in_scope_files` paths only, and the output schema says `untouched_file` must be a path that appears in `in_scope_files` and does not appear in `touched_files`. `scripts/doc_audit/judgment/cross_file_implication.py::_parse_response()` drops touched-file entries, but for out-of-scope targets it only logs and keeps the entry. That trusts an LLM schema violation and can cause the driver to file debt for docs outside the scoped audit surface.

How to fix:
- Drop entries whose `untouched_file` is not in `in_scope_files` when an in-scope list is provided.
- Add a unit test covering an out-of-scope implication and asserting it is filtered out.

Downstream note: WP06 depends on WP04. If WP06 has started from this lane, it should rebase after these fixes land.
