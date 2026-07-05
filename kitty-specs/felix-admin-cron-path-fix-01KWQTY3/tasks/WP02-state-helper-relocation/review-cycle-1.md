**Issue 1**: `tests/inbox/test_routing_log.py::test_default_routing_log_path_under_second_brain` still asserts that `DEFAULT_ROUTING_LOG_PATH` contains `second-brain`, so the nearby routing-log test suite now fails after WP02 repoints the production default to `/data/services/openclaw/state/inbox-routing.jsonl`.

Evidence:

```bash
python3 -m pytest tests/inbox/test_routing_log.py -q
```

Result: `1 failed, 14 passed`; the failing assertion is `assert "second-brain" in str(DEFAULT_ROUTING_LOG_PATH)`.

How to fix: update the stale test to assert the new canonical `/data/services/openclaw/state/inbox-routing.jsonl` path, or remove it if `tests/inbox/test_state_paths.py` is now the authoritative coverage. Re-run both:

```bash
python3 -m pytest tests/inbox/test_state_paths.py tests/inbox/test_routing_log.py -q
```

Downstream note: WP05 and WP06 depend on WP02; if this lane changes after the fix, those agents should rebase before continuing.
