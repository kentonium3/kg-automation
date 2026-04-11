---
affected_files: []
cycle_number: 1
mission_slug: 026-vault-path-registry-and-folder-renumber
reproduction_command:
reviewed_at: '2026-04-11T04:09:14Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP04
---

**Issue**: WP04 halted during pre-deploy verification due to pre-existing repo-vs-office2 drift that predates mission 026.

**Details**: During Step 4 (capture office2 baseline hashes), I discovered that `scripts/openclaw/agents/felix-admin-capture/USER.md` and `TOOLS.md` have drifted between the repo (lane-a and main) and office2. Office2 has additional content (a "Date handling" section in USER.md from mission 025, and a "GitHub" section in TOOLS.md from mission 022) that does not exist in the repo. Running WP04's pre-rename deploy would SCP the regressed repo content to office2, overwriting working production state.

**Root cause**: Commit `8c1054c` ("docs: spec-kitty 023 specify — agent identity WhatsApp header") made by mission 023's specify phase silently stripped 189 lines from felix-admin-capture/AGENTS.md and 18 lines from TOOLS.md — including the entire GitHub routing support added by mission 022 WP02 (commit `0a1cfb6`). The USER.md "Date handling" drift is a separate issue: mission 025 appears to have patched office2 directly without committing the repo counterpart.

**Impact**: Mission 026 lane-a's `.tmpl` sources were generated from the regressed main state. Deploying them to office2 would cause real production regressions in felix-admin-capture (loss of GitHub routing + timezone handling).

**Required before WP04 can resume**:
1. Broader drift audit: compare every office2 file under /data/services/openclaw/ against its repo counterpart
2. Reconciliation: bring repo main into alignment with authoritative office2 production state
3. Filing a bug report against the 8c1054c regression pattern
4. Re-running mission 026 WP01/WP02/WP03 against the reconciled state (since lane-a's .tmpl sources were derived from the regressed baseline)

**Operator decision**: Halt mission 026 entirely, pursue reconciliation as a separate workstream, restart 026 after reconciliation merges.
