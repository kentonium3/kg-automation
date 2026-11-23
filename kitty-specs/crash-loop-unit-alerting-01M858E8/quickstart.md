# Quickstart: Crash-loop unit alerting

## Offline (any dev machine)

```bash
cd ~/repos/kg-automation
.venv/bin/python -m pytest tests/canary -q                       # new + existing canary suite (FR-013 ratchet)
.venv/bin/python -m pytest tests/deploy/test_deploy_crash_loop_unit_alerting.py -q
.venv/bin/python -m pytest -q -p no:cacheprovider                # full suite; pre-mission baseline 10907 passed, 51 skipped, 1 xfailed
```

The incident replay (SC-001) is `tests/canary/test_crash_loop.py::test_incident_replay_obsidian_sync_39_restarts`. Tick 1 reads 0 with the unit `active (running)`. Tick 2, 16 minutes later, reads 39 with the unit `active (running)`. The test expects exactly one ERROR alert naming `system:obsidian-sync.service`: Δ = 39 over 16 minutes gives m = 2 and a bound of 5, so the crossing is proven.

## On office2 (read-only preview; no writes, no alerts)

**Run this only after the code is on office2, which means after the merge Kent approves.**

```bash
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.canary.run --dry-run | grep crash-loop'
ssh office2-claude 'cd ~/kg-automation && scripts/deploy/deploy-crash-loop-unit-alerting.py --dry-run'
```

The dry-run reads the real counters and prints the scope lines, any would-be events and the read time (NFR-002). It writes nothing and emits nothing.

## After deploy (post-merge live verification; owned by the deploy entrypoint)

felix-deployer applies `deploys/queued/<NNNN>-crash-loop-unit-alerting.yaml`, which runs `deploy-crash-loop-unit-alerting.py --apply`. That:

1. starts `felix-canary.service` once and waits for it to finish, and starts it once more if the first start joined a pass that was already running;
2. asserts that `crash-loop.json` `updated_at_utc` is from this run;
3. asserts that today's canary ledger has `crash-loop:system`, `crash-loop:user` and `crash-loop:container` lines from this run, **all three `healthy`**;
4. asserts that `last-tick.json` `errors` has no `crash_loop:` entry, and that any crash-loop event from this run was delivered.

The first tick after deploy only records baselines (FR-010). obsidian-sync's 39 is a baseline, not an alert.

## Seven-day acceptance (SC-003, NFR-004, NFR-005); owned follow-up on kentonium3/kg-automation#1133

Seven days after the deploy is applied, follow the procedure in `docs/runbooks/canary-registry-ops.md` (research R-14):

- Every crash-loop alert, re-remind or aggregate in the alert-bus ledger has canary-ledger event lines whose interval meets the proven-crossing bound `delta ≥ m·(threshold−1)+1`, where `m = ceil(period/window)`.
- No canary pass recorded a `crash_loop:` error.
- `felix-canary.service` never exited non-zero.

## Tuning

Edit `scripts/canary/crash_loop_config.json` (threshold, window, K, per-tick cap, read budget, and the ignore list with reasons), commit it, and let it reach office2 through the normal pipeline. To reset the history, run `rm /data/services/felix-canary/state/crash-loop.json`: every unit is then first-seen on the next tick, and nothing alerts.
