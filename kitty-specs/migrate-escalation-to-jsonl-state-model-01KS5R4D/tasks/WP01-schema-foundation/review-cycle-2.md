---
affected_files: []
cycle_number: 2
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
reproduction_command:
reviewed_at: '2026-05-21T19:42:05Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: `validate_event_params` does not validate optional `reason` type.

The WP prompt and data model require `reason` to be `str` when present (`reason` is optional on `dismissed` and `done`). The current implementation documents that contract, but there is no runtime check in `scripts/escalation/schema.py`; for example, `{"state": "done", "project_id": 4, "reason": 123}` is accepted.

Fix: add a `reason` check in `validate_event_params` that raises `EscalationSchemaError` when `reason` is present and is not a `str`, with a field-named message. Add a regression test for a non-string `reason`. Keep `note` behavior unchanged; the prompt explicitly says Phase 2 `validate_record` owns `note` type errors.

Downstream note: WP02 depends on WP01, so dependent agents should rebase after this fix lands.
