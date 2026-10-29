# Data Model: Canary dead-man's switch and backup coverage

## Entities

### CoverageFinding (new; in-memory → serialized into the run record)

| Field | Type | Rule |
|---|---|---|
| `component` | str | One of `COVERAGE_COMPONENTS = ("felix-canary", "restic-backup")`, fixed order |
| `outcome` | str | `HealthResult.outcome` verbatim, or `"unavailable"` |
| `finding` | `"ok" \| "failure" \| "unknown"` | Derived by the R2 mapping. Any unrecognised outcome → `"unknown"` |
| `evidence` | str | `HealthResult.evidence`, or the exception text for `"unavailable"` |

### Run verdict (existing `status`, now combined)

State, by precedence (highest wins):

```
inputs: script_status ∈ {ALL_HEALTHY, FAILURES_DETECTED, UNKNOWN, SCRIPT_MISSING}
        findings: [CoverageFinding × 2]

FAILURES_DETECTED  if script_status == FAILURES_DETECTED or any finding == failure
SCRIPT_MISSING     elif script_status == SCRIPT_MISSING
UNKNOWN            elif script_status == UNKNOWN or any finding == unknown
ALL_HEALTHY        otherwise   (script ALL_HEALTHY with rc 0, and both findings ok)
```

Alerting statuses are unchanged: everything except `ALL_HEALTHY`.

### Read-only inputs (owned elsewhere; never written here)

- **Inventory declarations**: `service-inventory.json` → `services[name=felix-canary].health_check` (`tick-signal-file`, `state_path` `/data/services/felix-canary/state/last-tick.json`, `max_age_seconds` 2100) and `services[name=restic-backup].health_check` (`state-file`, `state_path` `/data/services/backup/state/last-backup.json`, `max_age_seconds` 100800, `key_ledger` with 10 adjudicated keys).
- **Canary tick signal** and **backup pointer**: shapes in research F4/F5.

## Invariants

- I1: the health check never writes either input document, nor any canary or backup state.
- I2: `ALL_HEALTHY` ⇒ both findings `ok` (and the script affirmed health).
- I3: one run yields exactly one record and at most one alert.
