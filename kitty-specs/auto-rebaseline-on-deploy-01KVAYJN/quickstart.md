# Quickstart: Auto-Rebaseline on Deploy

## What it does
When a commit that changes an audited surface lands on main, felix-deployer
(on office2) notices it on `git pull`, waits until the surface's drift actually
shows up in a read-only audit, then resets the security-monitor baselines
automatically and records the outcome — no human on the happy path. Unexpected
drift, rebaseline failures, and never-confirming changes raise ntfy alerts.

## Verify locally (unit tests, no office2)
```
cd /Users/kentgale/repos/kg-automation
pytest tests/deploy/test_rebaseline.py tests/deploy/test_audited_surfaces.py tests/deploy/test_tick_rebaseline.py -v
```

## Verify on office2 (post-merge integration canary — the WP05-equivalent gate)
1. Confirm the shared matcher parity:
   ```
   python3 tooling/scripts/check_audited_surface_drift.py --range HEAD~1...HEAD
   ```
2. Land a benign audited-surface change (e.g. an agent prompt), let the
   agent-prompt-sync timer deploy it, and watch the felix-deployer tick log:
   ```
   ssh office2-claude 'tail -f /data/services/felix-deployer/logs/$(date -u +%F).jsonl'
   ```
   Expect `pending_set` → (later tick) `completed`, and:
   ```
   ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l'   # == 14
   ```
3. Confirm the next daily audit reports "All clear" with no drift alert (SC-002).
4. A no-audited-surface deploy records `not_required` (SC-003).
5. Simulate a rebaseline failure → exactly one ntfy + failure annotation, code left in place (SC-004).

Record the canary outcome as the mission's merge acceptance criterion.

## Key paths
- Pending token: `/data/services/felix-deployer/state/rebaseline-pending.json`
- Tick log: `/data/services/felix-deployer/logs/<date>.jsonl`
- Registry: `docs/design/architecture/data/audited-surfaces.json`
- Manual fallback (out-of-band): `docs/runbooks/security-baseline-ops.md`
