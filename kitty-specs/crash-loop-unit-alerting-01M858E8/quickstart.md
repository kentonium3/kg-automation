# Quickstart: Crash-loop unit alerting

## Offline (any dev machine)

```bash
cd ~/repos/kg-automation
.venv/bin/python -m pytest tests/canary -q                       # new + existing canary suite (FR-013 ratchet)
.venv/bin/python -m pytest tests/deploy/test_deploy_crash_loop_unit_alerting.py -q
.venv/bin/python -m pytest -q                                    # full suite; compare with the pre-mission count
```

The incident replay (SC-001) is `tests/canary/test_crash_loop.py::test_incident_replay_obsidian_sync_39_restarts`. Tick 1 reads 0 with the unit `active (running)`. Tick 2, 16 minutes later, reads 39 with the unit `active (running)`. The test expects exactly one ERROR alert naming `system:obsidian-sync.service`.

## On office2 (read-only preview; no writes, no alerts)

```bash
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.canary.run --dry-run | grep crash-loop'
ssh office2-claude 'cd ~/kg-automation && scripts/deploy/deploy-crash-loop-unit-alerting.py --dry-run'
```

The `--dry-run` reads the real counters and prints the scope lines and any would-be events. It writes nothing and emits nothing. **Run this only after the code is on office2, which happens after the merge Kent approves.**

## After deploy (post-merge live verification; owned by the deploy entrypoint)

felix-deployer applies `deploys/queued/<NNNN>-crash-loop-unit-alerting.yaml`, which runs `deploy-crash-loop-unit-alerting.py --apply`. That:

1. starts `felix-canary.service` once and waits for it to finish;
2. asserts that `/data/services/felix-canary/state/crash-loop.json` was written by this run;
3. asserts that today's canary ledger has `crash-loop:system`, `crash-loop:user` and `crash-loop:container` lines from this run, and that `system` and `user` are not `unknown`;
4. asserts that `last-tick.json` `errors` has no `crash_loop:` entry.

The first tick after deploy only records baselines (FR-010). obsidian-sync's 39 is a baseline, not an alert.

## Tuning

Edit `scripts/canary/crash_loop_config.json` (threshold, window, K, ignore list with reasons). Commit it and let it reach office2 through the normal pipeline. To reset the history: `rm /data/services/felix-canary/state/crash-loop.json`. Every unit is then first-seen on the next tick, and nothing alerts.
