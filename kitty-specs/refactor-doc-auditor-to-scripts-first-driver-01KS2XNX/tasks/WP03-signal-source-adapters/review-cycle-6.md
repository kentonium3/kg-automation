---
affected_files: []
cycle_number: 6
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-20T18:27:17Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
---

**Issue 1**: `DriftEventSignalSource.commit()` can advance the cursor past unprocessed drift events.

`scripts/doc_audit/signals/drift_event.py` computes `new_cursor = line_number + 1` and writes it whenever `new_cursor > current`. If the driver commits a signal for line 2 while the cursor is still 0, the cursor becomes 3 and lines 0 and 1 are permanently skipped. This violates WP03's requirement that `commit()` "advances the cursor exactly one event" and is unsafe because the driver sorts all pending signals by `(priority, created_utc)`, not by drift-event file line number. Out-of-order event timestamps, same-timestamp tie behavior, or future queue changes can therefore cause data loss.

Fix by making drift cursor advancement contiguous. A commit should only process the current cursor line, or it should refuse/defer out-of-order drift-event commits without moving the cursor. Add a regression test with at least three drift events where a later-line signal is committed first; assert the cursor does not jump past earlier unprocessed lines.

WP06 depends on WP03, so downstream agents should rebase after this WP is corrected.
