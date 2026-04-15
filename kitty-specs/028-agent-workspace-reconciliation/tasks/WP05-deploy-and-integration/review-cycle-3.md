---
affected_files: []
cycle_number: 3
mission_slug: 028-agent-workspace-reconciliation
reproduction_command:
reviewed_at: '2026-04-13T19:14:24Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP05
---

**Issue 1**: The deploy wrapper does not update the office2 repo clone before installing the cron-driven enforcement workflow. `scripts/deploy/deploy-028.sh` copies files into `/home/claude/kg-automation`, but it never executes the required `ssh office2-claude 'cd /home/claude/kg-automation && git pull'` step from T021. Add an explicit repo-sync step before copying/installing enforcement artifacts, and fail the deploy if that sync does not succeed.

**Issue 2**: The post-flight verification does not enforce the zero-drift acceptance gate and does not run the required smoke-test command. At [scripts/deploy/deploy-028.sh](/Users/kentgale/repos/kg-automation/.worktrees/028-agent-workspace-reconciliation-lane-a/scripts/deploy/deploy-028.sh:237), apply mode runs `drift_check.py report --json`, while the WP requires `drift_check.py check --dry-run --json`. The script also treats any smoke-test failure as non-fatal and never fails when drift remains (`warn "Smoke test failed (non-fatal)"`). Change this step so it runs the required `check --dry-run --json` command, verifies all 25 tracked files return `no_change`, and exits non-zero on any drift or command failure.

**Issue 3**: There is no committed implementation or evidence for T023's controlled drift verification. The WP requires a real `REPO_CHANGED` test, a real `OFFICE2_CHANGED` test, and cleanup back to zero drift. The branch contains the deploy script and an updated manifest, but no committed runbook/log/test artifact showing those actions were executed and verified. Add a committed verification artifact for the drift exercise (commands run, observed states, cleanup confirmation), or otherwise encode the controlled test procedure/output in a reviewable form that proves T023 was completed.
