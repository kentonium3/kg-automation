---
affected_files: []
cycle_number: 4
mission_slug: vikunja-client-and-habits-weekly-report-01KTKSFT
reproduction_command:
reviewed_at: '2026-06-08T15:59:54Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
review_artifact_override_at: "2026-06-08T16:16:13Z"
review_artifact_override_actor: "operator"
review_artifact_override_wp_id: "WP01"
review_artifact_override_reason: "Arbiter override: codex cycle-3 review verdict PASS (all 4 cycle-1 substantive issues fixed). 45 tests, 100% line+branch coverage. Issue-matrix verdicts now have explicit Follow-up handles."
---

**Issue 1 (blocking — FR-011 coverage gate command fails)**: The exact
Definition-of-Done command uses
`--cov=scripts/common/vikunja_client`. With pytest-cov, that value is treated
as a module name; the run reports that `scripts/common/vikunja_client` was
never imported, collects no coverage data, and fails at 0% even though all 45
tests pass. The dotted target works and reports 100% line/branch coverage:
`--cov=scripts.common.vikunja_client`. Update the WP-owned test documentation
and any canonical invocation to use the dotted module target, then verify the
documented command succeeds from a clean checkout.

Cycle-2 verification note: URL query merging, `{}` for empty successful
responses, and method-driven `Content-Type: application/json` for bodyless
POST/PUT are implemented and covered by direct regression tests.
