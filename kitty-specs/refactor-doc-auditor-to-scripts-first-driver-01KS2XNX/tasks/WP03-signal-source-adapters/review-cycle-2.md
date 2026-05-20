---
affected_files: []
cycle_number: 2
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-20T18:15:10Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
---

**Issue 1**: `DriftEventSignalSource` does not wrap the `handle_drift_events.process_events()` library surface required by WP03.

The WP objective and T013 require `DriftEventSignalSource` to wrap `doc_audit.helpers.handle_drift_events.process_events()` rather than re-implement drift-event processing. The current implementation in `scripts/doc_audit/signals/drift_event.py` imports only `read_cursor` and `write_cursor_atomic`, reads/parses `drift-events.jsonl` itself, skips malformed JSON itself, and advances the cursor directly in `commit()`. The module docstring explicitly rejects the `process_events()` approach. That means the adapter can diverge from the helper's real classification, unmapped-event routing, issue filing behavior, limit/error handling, and cursor semantics.

Fix: change `DriftEventSignalSource` so it imports and uses `process_events`/`ProcessResult` from `doc_audit.helpers.handle_drift_events` as the wrapped library surface. `pending()` may use `process_events(..., dry_run=True)` or a thin helper-derived read path if needed for idempotent signal construction, but `commit()` must invoke the helper surface for the committed event so mapped events and unmapped events are processed consistently with `handle_drift_events.py` and the cursor advances only through that helper. Add/update tests that mock or spy on `process_events()` so this integration cannot regress.

Downstream note: WP06 depends on WP03, so WP06 should rebase after this fix lands.
