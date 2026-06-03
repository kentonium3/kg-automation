# Quickstart: Sweeper tick signal extractor

**Mission**: `sweeper-tick-signal-extractor-01KT6MJP`

How to verify the extractor locally and on office2.

## Local (unit + integration)

```bash
cd /Users/kentgale/repos/kg-automation
pytest scripts/openclaw/observation/tests/test_signals_sweeper_tick.py -v
```

Expected: all eight named cases from `contracts/sweeper-tick-extractor.contract.md` § "Test obligations" pass green.

Then run the broader observation suite to confirm no regression:

```bash
pytest scripts/openclaw/observation/tests/ -v
```

Expected: all tests pass, including the existing mission #490 / #61 tests for the other extractors and the tick orchestrator.

## office2 (post-deploy verification)

1. After merge, sync office2:
   ```bash
   ssh office2-claude 'cd /home/claude/kg-automation && git fetch && git reset --hard origin/main'
   ```
2. Trigger one tick by hand:
   ```bash
   ssh office2-claude 'python3 -m scripts.openclaw.observation.tick --dry-run --last-tick /tmp/last-tick-sweeper-verify.json --ledger /tmp/sweeper-verify-ledger.jsonl'
   ```
3. Inspect the resulting `/tmp/last-tick-sweeper-verify.json`. The `signals_evaluated` array MUST now contain a `sweeper_tick` entry. Expected fields:
   - `signal_id == "sweeper_tick"`
   - `count_cycle` ∈ {0, 1}
   - `threshold_status` ∈ {`"below"`, `"tripped_cycle"`, `"tripped_rolling"`, `"tripped_both"`}
4. If `count_cycle == 1`, inspect the cause via the live ledger:
   ```bash
   ssh office2-claude 'tail -1 /data/services/openclaw/state/habits/sweeper-ledger.jsonl | jq "{started_at_utc, exit_status, errors, dry_run}"'
   ```
   The triggering field should be visible (failed exit_status, non-empty errors, or stale timestamp).

## Real-world regression check

After the next two natural 12:30 UTC sweeper ticks (06-04 and 06-05), inspect the most recent signal-extraction tick:

```bash
ssh office2-claude 'cat /data/services/openclaw/state/felix-core-digest-signals/last-tick.json | jq ".signals_evaluated[] | select(.signal_id == \"sweeper_tick\")"'
```

Expected: `count_cycle = 0, threshold_status = "below"` while the sweeper is healthy.

## Simulating a failure (manual test)

To confirm the extractor actually trips on a real failure, the safest manual test is the replay path via a synthetic ledger:

```bash
# On the dev laptop:
cat > /tmp/synthetic-sweeper-ledger.jsonl <<'EOF'
{"schema_version":1,"tick_id":"01TEST","started_at_utc":"2026-06-03T11:30:00Z","duration_ms":5000,"dry_run":false,"errors":[],"exit_status":"vikunja_unreachable"}
EOF

pytest scripts/openclaw/observation/tests/test_signals_sweeper_tick.py::test_failed_exit -v
```

The synthetic ledger + the test together verify the trip path end-to-end without touching production.

## Rollback

If a problem surfaces post-merge, revert the merge commit on `main`. The extractor adds a new signal_id; reverting removes it from the dispatch table and the config. No state schema change to undo.
