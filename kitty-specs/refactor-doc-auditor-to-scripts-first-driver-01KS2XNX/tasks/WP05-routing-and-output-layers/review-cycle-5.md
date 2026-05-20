---
affected_files: []
cycle_number: 5
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-20T19:51:58Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP05
---

**Issue 1**: Activity-log appends do not leave the required blank line between audit entries.

The WP05 validation checklist requires "Subsequent calls append entries with one blank line between." The current formatter in `scripts/doc_audit/output/activity_log.py` returns exactly one trailing newline after `- Errors: ...` (lines 140-144), so the next append writes the next `## Audit run` header immediately on the following line with no blank line between entries. The implementation docstring also explicitly says "then no extra blank line" (lines 95-101), which contradicts the work-package validation requirement.

Fix: update `_format_audit_entry()` / append behavior so repeated entries are separated by one blank line while preserving the canonical single-entry shape as needed. Add or adjust a test in `tests/doc_audit/output/test_activity_log.py::test_multiple_appends_accumulate` to assert the separator exactly, for example that `"- Errors: 0\n\n## Audit run — 2026-05-20T14:30:00-0400"` appears between the first and second entries.

Because WP06 depends on WP05, the WP06 agent should rebase after this correction lands.
