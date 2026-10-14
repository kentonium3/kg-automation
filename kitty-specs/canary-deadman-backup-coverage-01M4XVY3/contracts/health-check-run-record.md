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
3. **The canary's verdict on the health check is a function of `status` + `ran_at_utc` + `exit_code` only.** Test: run the canary's real `run_probe` with the real inventory `felix-health-check` declaration over records written by the real wrapper for (a) all-healthy, (b) coverage failure with the shell exiting 0, (c) coverage unknown, and (d) coverage failure with the shell exiting non-zero. Expect (a) healthy; (b) healthy, because the runner is fine and only the data is bad; (c) failed (status UNKNOWN); (d) failed, because a non-zero `exit_code` is a legacy explicit error, which is existing behavior and preserved (Codex-5). Each is anchored on `ran_at_utc`. Invariants 1–2 are tested by deriving the ranked timestamp keys from `scripts.canary.probes.TIMESTAMP_KEYS` at runtime (not a copied list) and driving the real probe over a record variant carrying each forbidden key (paula-2).
4. `coverage_checks` is present on **every** record, including script-missing and timeout runs, with exactly two entries.

## Alert body (via `felix-alert` bus, source `felix-health-check/run`, unchanged)

The bus truncates every `details` value to 500 characters (`scripts/common/alert_bus/render.py` `DETAIL_VALUE_MAX`), so findings are **separate detail entries**, in this order:

1. `script`: present only when the script is missing, timed out, or failed to launch (it is listed first; paula-5);
2. `coverage:<component>`: one per non-ok coverage finding, `"<FINDING> (<outcome>): <evidence>"`;
3. `status`, then `output` (shell output, as today).

`description` names the components with non-ok findings, so the headline line alone tells Kent what failed. Title and severity are unchanged. Tested against the real bus renderer with more than 4 KB of shell output.
