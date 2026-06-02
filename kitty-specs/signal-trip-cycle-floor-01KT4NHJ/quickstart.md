# Quickstart: Signal trip cycle floor

**Mission**: `signal-trip-cycle-floor-01KT4NHJ`

How to verify the fix locally and on office2.

## Local (unit + integration)

```bash
cd /Users/kentgale/repos/kg-automation
pytest scripts/openclaw/observation/tests/test_tick_orchestrator.py -v
```

Expected: all `_threshold_status` boundary cases (named in [contracts/trip-predicate.contract.md](contracts/trip-predicate.contract.md) → "Test obligations") pass green. Look in particular for the `quiet_hot_rolling` case (0, ≥1000, ...) returning `below`.

## office2 (post-deploy verification)

1. After merge, sync the office2 checkout:
   ```bash
   ssh office2-claude 'cd /home/claude/kg-automation && git fetch && git reset --hard origin/main'
   ```
2. Trigger one tick by hand (replay mode) using a synthetic log file containing only stale events:
   ```bash
   ssh office2-claude 'python3 /home/claude/kg-automation/scripts/openclaw/observation/tick.py \
     --replay-log /tmp/openclaw-replay-quiet-cycle.log \
     --dry-run \
     --last-tick /tmp/last-tick-replay.json \
     --ledger /tmp/replay-ledger.jsonl'
   ```
3. Inspect the resulting `/tmp/last-tick-replay.json`:
   - All signals should report `threshold_status == "below"`.
   - `issues_filed` must be empty.
   - `dry_run` is true.

## Real-world regression check

Once deployed, observe the next two scheduled tick cycles (≤30 min) via:
```bash
ssh office2-claude 'cat /data/services/openclaw/felix-core-digest-signals/last-tick.json | jq .signals_evaluated'
```
Expected: signals continue at `count_cycle = 0, threshold_status = below` for `whatsapp_creds_restore` and `web_watchdog_reconnect`. `openclaw_unhandled_error` may show occasional `count_cycle ≥ 1`; that is a legitimate sustained-condition path and is the expected behavior under the new semantics.

## Rollback

If a problem surfaces post-merge, revert the merge commit on `main`. There is no state-migration step to undo — the predicate change is pure logic over computed inputs.
