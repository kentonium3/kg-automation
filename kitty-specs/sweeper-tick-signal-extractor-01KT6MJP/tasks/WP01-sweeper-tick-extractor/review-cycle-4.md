**Issue 1: `sweeper_tick.extract` does not exactly match the existing extractor signatures.**

The WP reviewer guidance makes this the first gate: the new extractor's `extract()` signature must match the three existing extractors exactly, including same arg order, same types, and same return type. The current implementation differs from all three existing extractors in the `state_dir` annotation and in the missing defaults for `prior_cursor` and `prior_rolling_count`.

Observed signatures:

```text
creds_restore       (state_dir: 'Union[Path, str]', signal_def: 'SignalDefinition', now_utc: 'datetime', prior_cursor: 'Optional[LogCursor]' = None, prior_rolling_count: 'int' = 0) -> 'SignalExtraction'
watchdog_reconnect  (state_dir: 'Union[Path, str]', signal_def: 'SignalDefinition', now_utc: 'datetime', prior_cursor: 'Optional[LogCursor]' = None, prior_rolling_count: 'int' = 0) -> 'SignalExtraction'
unhandled_error     (state_dir: 'Union[Path, str]', signal_def: 'SignalDefinition', now_utc: 'datetime', prior_cursor: 'Optional[LogCursor]' = None, prior_rolling_count: 'int' = 0) -> 'SignalExtraction'
sweeper_tick        (state_dir: 'Path', signal_def: 'SignalDefinition', now_utc: 'datetime', prior_cursor: 'Optional[LogCursor]', prior_rolling_count: 'int') -> 'SignalExtraction'
```

Remediation:

- Update `scripts/openclaw/observation/signals/sweeper_tick.py` so `extract()` matches the existing extractor signature exactly:

```python
def extract(
    state_dir: Union[Path, str],
    signal_def: SignalDefinition,
    now_utc: datetime,
    prior_cursor: Optional[LogCursor] = None,
    prior_rolling_count: int = 0,
) -> SignalExtraction:
```

- Add the needed `Union` import or use the repo's established equivalent style.
- Re-run the signature comparison and the observation suite.

Validation already run during review:

- `python3 -m pytest scripts/openclaw/observation/tests/test_signals_sweeper_tick.py -v` passed: 14 passed.
- `python3 -m pytest scripts/openclaw/observation/tests/test_config_loader.py -v` passed: 18 passed.
- `python3 -m pytest scripts/openclaw/observation/tests/ -v` passed: 221 passed.
- `jq empty docs/design/architecture/data/signal-to-doc-map.json && python tooling/scripts/validate_docs.py` passed.
- `python3 -m pytest tests/ -v` had one existing broader-suite failure outside WP01's owned files: `tests/habits/test_parse_morning_reply_48hr_correlation.py::TestCliCorrelation::test_explicit_iso_date_in_reply_swaps_correlation` expected `2026-06-01` but got `2026-06-02`.
