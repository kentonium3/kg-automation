**Issue 1**: `BackfillReport.comments_replayed` reports attempted duplicate records on rerun instead of the number of new JSONL records actually replayed.

`backfill_project()` currently calls `record_event()` and increments `comments_replayed` unconditionally after the call (`scripts/escalation/backfill_jsonl_from_comments.py:806`). `record_event()` delegates dedup to `_append_jsonl()`, but its return value does not indicate whether an append happened. The result is that a second backfill run writes 0 new JSONL lines but still returns/prints `comments_replayed > 0`.

This violates the API contract's "comments_replayed" meaning as replayed JSONL records and leaves the WP06 idempotency acceptance incomplete: rerun must report 0 new records, not just keep the file unchanged.

Remediation:
- Use the existing `idempotent_record_event()` API or another explicit pre-check that can distinguish deduped records from appended records.
- Increment `comments_replayed` only when a new JSONL record is actually written.
- Strengthen `tests/escalation/test_backfill.py::TestIdempotency::test_backfill_idempotent_on_rerun` to assert `report2.comments_replayed == 0`.

Note: the known pre-existing failures in `tests/common/test_state_log_{append,read}.py` that reference the old `triggered` enum are acknowledged as a WP01 cleanup issue and are not part of this WP06 rejection.
