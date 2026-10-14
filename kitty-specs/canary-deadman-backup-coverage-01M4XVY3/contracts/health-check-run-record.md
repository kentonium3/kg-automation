# Contract: felix-health-check run record (`last-run.json`)

**Path**: `/data/services/openclaw/felix-health-check/last-run.json`. Written atomically (tempfile → fsync → rename) by `scripts/office2/felix_health_check/run.py` on every run, alerting or not.
**Consumers**: (1) `felix-canary`'s `signal-file` probe (inventory entry `felix-health-check`, #891); (2) humans and the deploy post-check (this mission).

## Keys

| Key | Type | Status | Meaning |
|---|---|---|---|
| `status` | `"ALL_HEALTHY" \| "FAILURES_DETECTED" \| "UNKNOWN" \| "SCRIPT_MISSING"` | **unchanged, closed** | Combined verdict (precedence in research R6). No new words; the canary's allow-list is `[ALL_HEALTHY, FAILURES_DETECTED]`. |
| `ran_at_utc` | ISO-8601 `Z` string | **unchanged** | Run start. **Must remain the canary's freshness anchor.** |
| `exit_code` | int \| null | **unchanged** | The shell script's exit code; `null` if it did not run (missing, timeout). |
| `delivery` | `{attempted: bool, sent: bool, detail: str}` | **unchanged** | Alert-bus delivery record. |
| `script_path` | string | **NEW** | Absolute path of the shell script this run executed (or tried to). Repo path after this mission. |
| `coverage_checks` | list of objects | **NEW** | One entry per coverage component, in fixed order `felix-canary`, `restic-backup`. |

`coverage_checks[]` entry: `{"component": str, "outcome": str, "finding": "ok"|"failure"|"unknown", "evidence": str}`. `outcome` is the canary's `HealthResult.outcome` verbatim, or `"unavailable"` when evaluation could not start (import, inventory or target failure).

## Invariants (each pinned by a test)

1. **No new top-level key is in `_explicit_error`'s vocabulary**: `restic_exit_code`, `prune_exit_code`, `exit_status`, `errors`, `error`, `cycle_error` are never written. `status` and `exit_code` keep their existing meaning.
2. **No timestamp key that ranks before `ran_at_utc` in `scripts.canary.probes.TIMESTAMP_KEYS`** is written at top level: `completed_at_utc`, `snapshot_timestamp_utc`, `script_finished_at_utc`. Nested entries carry no timestamps at all; evidence strings may *mention* times.
3. **The canary's verdict on the health check is a function of `status` + `ran_at_utc` + `exit_code` only.** Test: run the canary's real `run_probe` with the real inventory `felix-health-check` declaration over records written by (a) all-healthy, (b) coverage failure, (c) coverage unknown. Expect (a) healthy, (b) healthy (runner fine, data bad), (c) failed (status UNKNOWN), each anchored on `ran_at_utc`.
4. `coverage_checks` is present on **every** record, including script-missing and timeout runs, with exactly two entries.

## Alert body (via `felix-alert` bus, source `felix-health-check/run`, unchanged)

The shell script's output (truncated at 4 KB as today), then a `Coverage:` block with one line per non-ok finding: `<FINDING> <component>: <evidence>`. Title and severity are unchanged.
