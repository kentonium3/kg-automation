---
affected_files: []
cycle_number: 4
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-20T19:24:27Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP04
---

**Issue 1**: `debt_body_generation` can falsely accept a different issue number as the originating audit reference.

`scripts/doc_audit/judgment/debt_body_generation.py::_parse_and_validate()` checks `audit_ref = f"#{originating_audit_number}"` with a substring test. If the LLM returns a Cross-references section containing `#3200` and the originating audit is `320`, the function treats `#320` as present and does not inject the required `Refs #320 (originating audit)` line. That violates the debt-body contract and WP requirement that generated debt issues include a backlink to the originating audit.

Fix:
- Validate the originating audit reference as an exact issue reference, not a substring. A simple regex boundary check for `Refs #<originating_audit_number>` is enough.
- Keep the existing injection behavior when the exact originating audit ref is absent.
- Add a regression test where the LLM output includes `#3200` but `originating_audit_number=320`; expected body must still contain `Refs #320`.
