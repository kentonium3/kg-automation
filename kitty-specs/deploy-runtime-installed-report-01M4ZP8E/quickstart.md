# Quickstart

```bash
python3 -m pytest tests/deploy/test_userunits.py tests/deploy/test_apply_installed_report.py \
  tests/deploy/test_rebaseline_reported.py tests/deploy/test_tick_rebaseline.py -q
```

Post-merge live check (form b): after the deployer pulls the merge, its next tick log has no `tick_error`, and the merge's deploy-pipeline token ends `cleared_clean`:

```bash
ssh office2-claude 'grep -E "rebaseline_(observe|reconcile)|tick_error" /data/services/felix-deployer/logs/$(date -u +%F).jsonl | tail -5'
```
