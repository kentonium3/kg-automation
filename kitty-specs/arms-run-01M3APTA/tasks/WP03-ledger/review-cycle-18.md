---
affected_files: []
cycle_number: 18
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-26T01:45:02Z'
reviewer_agent: claude
wp_id: WP03
---

# WP03 REOPEN — design-lead M1 ruling (bus 20260925T221125657965Zb30b0038fa, 20260925T222320935007Z871e1c44e6)

Reopened after approval, because the M1 ruling changes what the ledger must enforce. This is not a defect in the approved code.
1. The resume Binding comparison EXCLUDES gate_host_sha and gate_container_sha, which bind the CREATING session only. The exclusions are a named constant with the reason in a comment. Every other field is still compared, type-aware.
2. `session_gates` joins the validated event vocabulary. Its detail requires session_id (non-empty str), passed (bool), and skipped (bool). Resume refuses malformed rows.
3. `begin_attempt` refuses unless THIS open Ledger instance has recorded a passing session_gates (passed:true, skipped:false). skipped:true is accepted only on a header that binds SKIP_GATES_SHA. The recording path is the existing `ledger.event("session_gates", {...})`, which is the harness's call site.
4. The ledger owns SKIP_GATES_SHA and binds_skip_gates, because grading imports ledger. grading re-exports both at merge time.
5. Can-fail tests for each rule.
