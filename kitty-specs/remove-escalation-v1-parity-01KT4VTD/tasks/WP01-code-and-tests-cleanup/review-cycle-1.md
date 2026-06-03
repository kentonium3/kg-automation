**Issue 1**: The WP's required final vestige grep still fails on the escalation test surface. `grep -rnE "_format_v1_comment|_COMMENT_PREFIX|_COMMENT_MARKER|_count_escalation_comments|phantom_subscription" scripts/escalation tests/escalation --exclude-dir=__pycache__` still returns `tests/escalation/test_reconcile_completions.py` matches for `phantom_subscription` at the module coverage note, the new regression-test docstring, and the negative assertion. The WP explicitly requires zero matches for `phantom_subscription` in active scripts/tests. Keep the no-phantom regression behavior, but remove the literal retired reason code from test text and assertions, for example by asserting `report.hard_fails == []` in that scenario and describing it without the retired code string.

Verification already run by reviewer:

- `python -m pytest tests/escalation tests/enrichment -v` -> 320 passed
- `python -m pytest tests/ -v` -> 2299 passed, 2 skipped

WP02 depends on WP01; after this cleanup lands, downstream agents should rebase.
