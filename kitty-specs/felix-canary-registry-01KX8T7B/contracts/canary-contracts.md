# Contracts: Felix component-health canary registry

This is a local batch runner, not an HTTP service — the "contracts" are the module boundary, the CLI
surface, and the inventory schema delta.

## 1. `health_check` schema delta (service-inventory.json)

Only ONE additive, optional field is introduced. Existing `health_check` structure is unchanged.

```jsonc
"health_check": {
  "method": "shell",                 // existing: http | shell | tick-signal-file (freshness)
  "endpoint": "...",                 // existing
  "expected": "...",                 // existing
  "timeout_seconds": 5,              // existing
  "state_path": "...",               // existing (freshness pointer path)
  "note": "...",                     // existing
  "max_age_seconds": 100800          // NEW, optional: freshness bound (e.g. 28h = 100800) for freshness checks
}
```

Validator (`validate_architecture_data.py`):
- `max_age_seconds`, if present, MUST be a positive integer.
- Warn (not block) when an alert-eligible freshness-based `health_check` omits `max_age_seconds`
  (warn→strict rollout, matching the existing STATUS_ENUM/health-check pattern).

## 2. Evaluation contract (`probes.py` + `health.py`)

```
evaluate(target: CanaryTarget, now: datetime, *, http_get=..., run_shell=..., read_state=...) -> HealthResult
```

- **Pure w.r.t. injected effects**: network/subprocess/filesystem are passed in (dependency-injected) so
  unit tests are deterministic and offline.
- **Guarantees**:
  - Returns exactly one `HealthResult` for every input target (INV-B).
  - `should_emit == True` ⟹ `target.alert_eligible == True` (INV-A). A suspended target ⇒ `should_emit=False`.
  - A raised exception inside a probe is caught → `health=unknown`, `evidence` names the error, and the
    caller records it in `errors[]` (INV-D). `evaluate` itself never raises for component-level failures.
  - No LLM invocation (INV-E).

Health mapping (from §data-model state set):
| Probe outcome | health |
|---|---|
| not evaluable | `unknown` |
| ok & fresh (or no freshness bound) | `healthy` |
| ok & stale (freshness bound exceeded) | `stale` |
| not ok | `failed` |
| self-reported partial | `degraded` |

## 3. CLI contract (`python -m scripts.canary.run`)

| Invocation | Behavior | Exit |
|---|---|---|
| `python -m scripts.canary.run` | one full pass: evaluate all → dedup → emit → write tick-signal + ledger. Deployed timer form. | 0 on completed pass (even if components were unhealthy — emission is the signal, not the exit); non-zero only on runner-level failure (which also triggers `OnFailure`). |
| `python -m scripts.canary.run --dry-run` | evaluate + print results; **no** emission, no dedup mutation, no tick-signal write | 0 |
| `python -m scripts.canary.run --self-check` | validate config/inventory readability + alert-bus availability; print `status=ok`/`status=error` | 0 ok / 1 error |
| `python -m scripts.canary.run --once` | alias for a single pass (explicit; the timer uses this) | as above |

- Invocation form is `python3 -m scripts.canary.run` (module form — NOT a bare script path; honors the
  `-m` convention for `scripts.*`-importing code, per the repeated `-m`-trap lessons).
- The deployed systemd `ExecStart` uses the office2 interpreter that actually has the deps on PATH
  (stdlib-only here, so system `python3` suffices — but the deploy self-test MUST invoke the identical
  command string the unit uses, per the #703 bare-python3 go-live lesson).

## 4. Alert emission contract (reuse #701)

- Emission goes through `scripts/common/alert_bus/` `emit()` with the existing Alert model. No new
  delivery path (C-002).
- Alert fields: `severity` (error/warning per §research R6), a stable `signal_id`
  (`canary.<component_id>.<health>`), `title`/`message` naming the component + health + evidence,
  `details` carrying evidence (redaction rules of the bus apply).
- The #706 ledger records every emit attempt + result (INV-C).

## 5. Deploy contract (office2)

- `deploys/queued/00NN-felix-canary-registry.yaml` installs `felix-canary.service` + `felix-canary.timer`
  (15-min), sets `EnvironmentFile` for the alert-bus topic (same pattern as felix-trust-scan), installs
  the `OnFailure=` alert shim, `daemon-reload`, enables the timer, and runs a `--self-check` +
  `--dry-run` gate before enabling (per the #711 deploy-self-test-dry-run-first lesson).
- **Rebaseline required** (systemd unit is an audited surface); `expected_baselines` declared if any
  CLI-mutation drift has no repo-file signal.
