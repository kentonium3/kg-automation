---
affected_files: []
cycle_number: 4
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-20T17:30:54Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: Test coverage for the lifted helper package is below the WP acceptance target. Running `PYTHONPATH=scripts python3 -m pytest tests/doc_audit/helpers/ --cov=scripts/doc_audit/helpers --cov-report=term-missing` reports 71% total coverage (`handle_audit_routing.py` 68%, `handle_drift_events.py` 77%), while T005 requires coverage of the new importable helper surface to be at least 80%.

**How to fix**: Add focused tests for the uncovered importable helper paths until the coverage command reports at least 80%. Good candidates are the untested routing appliers and failure legs (`version_bump`, `path_rename`, `dead_ref_removal`, `registry_entry_add`, `registry_autonomy_update`, gate-file failure, summary failure) plus the remaining `process_events` branches. WP03 and WP05 depend on WP01; dependent agents should rebase after the fix lands.
