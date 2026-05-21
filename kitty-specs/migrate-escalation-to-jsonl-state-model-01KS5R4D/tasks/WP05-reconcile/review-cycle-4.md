---
affected_files: []
cycle_number: 4
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
reproduction_command:
reviewed_at: '2026-05-21T21:10:42Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP05
---

**Issue 1**: Malformed JSONL lines are silently ignored instead of routing through Q10 hard-fail.

Research D8 says reconcile must trigger Q10 hard-fail for any malformed JSONL line, including lines that fail JSON parsing, non-object payloads, and records that fail schema or event-parameter validation. The current implementation collects malformed snippets in `_load_records_for_task()` and `_enumerate_subscribed_tasks()`, but `reconcile_project()` ignores the `_malformed` values at `scripts/escalation/reconcile_completions.py:903` and the phantom path ignores them at `scripts/escalation/reconcile_completions.py:953`. The only test for malformed raw lines, `tests/escalation/test_reconcile_completions.py:1233`, asserts that reconcile continues scanning, but does not assert a hard-fail. As a result, a corrupt JSONL file can pass the tick without `hard_fail.file_hard_fail_bug(reason="malformed_jsonl_record")`.

Fix: validate every JSONL line read by reconcile and file one hard-fail per affected task/reason/tick with `reason="malformed_jsonl_record"`. For unparseable or unkeyed lines where no task_id can be trusted, choose a deterministic operator-triage strategy that does not silently drop the error, and cover it with tests. Keep the sweep processing other valid tasks after filing the hard-fail.

Required tests:
- A raw malformed JSON line causes `file_hard_fail_bug` with `reason="malformed_jsonl_record"` and does not emit synthetic records for that malformed unit.
- A JSON object with invalid escalation parameters, such as `level_sent` missing `level`, still hard-fails with the expected D8 reason path already covered for derive-state inconsistency if that remains the intended classification.
- Within-tick dedup still files at most one hard-fail per `(task_id, reason)`.

Downstream note: WP07 depends on WP05 and should rebase after this correction.
