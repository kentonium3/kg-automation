# tests/common

Unit tests for `scripts/common/*` helpers.

## Vikunja client (mission `vikunja-client-and-habits-weekly-report-01KTKSFT`, WP01)

Canonical invocation that enforces the WP01 coverage gate:

```bash
pytest tests/common/test_vikunja_client.py \
    --cov=scripts.common.vikunja_client \
    --cov-branch \
    --cov-fail-under=90
```

The `.coveragerc` at the repo root pins the same source + floor, so the
shorter form below works too:

```bash
pytest tests/common/test_vikunja_client.py --cov --cov-branch
```

### Test layout

- `test_vikunja_client.py` — 40 unit tests covering construction,
  request execution, param encoding, error mapping, and the redaction
  policy from FR-012.
- `fixtures/vikunja_client_responses.json` — 13 canned scenarios
  (success bodies, every mapped HTTP error class, timeouts, URL errors,
  non-JSON body, 204 empty body).
- `conftest.py` — `vikunja_client_responses` + `mock_vikunja_urlopen`
  fixtures that turn a scenario name into a monkeypatched
  `urllib.request.urlopen` callable.

### Other modules in this directory

- `test_state_log_*` — state log helper tests (existing).
- `test_sync_cache.py` — sync cache helper tests (mission #519).
