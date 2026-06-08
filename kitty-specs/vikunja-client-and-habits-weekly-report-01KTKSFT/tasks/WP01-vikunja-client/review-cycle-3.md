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
