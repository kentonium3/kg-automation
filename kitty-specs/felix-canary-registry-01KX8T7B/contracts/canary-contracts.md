# Contracts: Felix component-health canary registry

Revised 2026-07-11 after the post-plan Codex review (folds F3, F4, F9).
A local batch runner, not an HTTP service — the "contracts" are the module boundary, the CLI surface,
the alert-bus API, and the inventory schema delta.

## 1. `health_check` schema delta (service-inventory.json)

One additive, optional field; existing structure unchanged.

```jsonc
"health_check": {
  "method": "tick-signal-file",      // existing; real vocabulary: http | shell | systemd-status |
                                     //   tick-signal-file | signal-file | state-file | log-tail |
                                     //   journal | self-check-command | self-test | none
  "endpoint": "...",                 // existing — command to run, URL, OR (for some) the freshness pointer path
  "expected": "...",                 // existing — prose or int status
  "timeout_seconds": 5,              // existing
  "state_path": "...",               // existing — freshness pointer path (when present)
  "note": "...",                     // existing
  "max_age_seconds": 100800          // NEW, optional — freshness bound for freshness/log-scan checks
}
```

- **Pointer-path resolution (F4):** for freshness probes the pointer path is
  `state_path` if present, **else** `endpoint`. (restic sets `state_path`; agent-prompt-sync et al. put
  the path in `endpoint`.)
- Validator: `max_age_seconds`, if present, is a positive int; warn (not block) when an alert-eligible
  freshness/log-scan check omits it.

## 2. Method → probe dispatch (probes.py) — REVISED (F1)

| method(s) | probe | healthy iff | stale iff | failed iff | unknown iff |
|-----------|-------|-------------|-----------|-----------|-------------|
| `http` | http GET `endpoint` | status == `expected` int within `timeout_seconds` | — | status ≠ expected | connection inconclusive |
| `shell` | run `endpoint` | exit 0 (+ expected marker if the check emits one) | — | non-zero exit | spawn error |
| `systemd-status` | run `endpoint` (`systemctl [--user] status`) | unit active/running | — | inactive/failed | systemctl error |
| `tick-signal-file`/`signal-file`/`state-file` | read pointer JSON (path per F4) | good success/exit/errors fields AND ts within `max_age_seconds` | ts older than `max_age_seconds` | explicit error fields in pointer | unreadable/malformed |
| `log-tail`/`journal` | run `endpoint` (tail/journalctl[+grep]) | expected marker present in window | marker older than `max_age_seconds` (if declared) | command error with output | inconclusive |
| `self-check-command`/`self-test` | run the component's own self-check `endpoint` | exit 0 | — | non-zero | spawn error |
| `none` / missing / unhandled | — | — | — | — | ⇒ **coverage gap** (not a probe) |

## 3. Evaluation contract (`probes.py` + `health.py`)

```
evaluate(target: CanaryTarget, now: datetime, *, http_get=..., run_cmd=..., read_state=...) -> HealthResult
```

- **Gate-before-probe (F6):** if `not target.alert_eligible` → return `HealthResult(outcome="suppressed",
  should_emit=False)` WITHOUT probing.
- **Pure w.r.t. injected effects**: network/subprocess/filesystem passed in → deterministic offline tests.
- **Guarantees**:
  - Returns exactly one `HealthResult` for every target (INV-B).
  - `should_emit == True` ⟹ `target.alert_eligible == True` (INV-A).
  - A raised exception inside a probe is caught → `outcome=unknown`, `evidence` names the error; caller
    records it in `errors[]` (INV-D). `evaluate` never raises for component-level failures.
  - No LLM invocation (INV-E).

## 4. Alert emission contract (reuse #701 — CORRECTED to the real API, F3)

Emit via `from scripts.common.alert_bus import emit, Alert, Severity`:

```python
emit(Alert(
    source="felix-canary",                       # stable signal identity (NOT a "signal_id" field)
    severity=Severity.ERROR,                      # enum: INFO | WARN | ERROR | CRITICAL (not "warning")
    title=f"{component_id} health: {outcome}",
    description=f"{message} — {evidence}",        # the message text lives in `description`
    action=None,
    details={"component_id": component_id, "outcome": outcome, "evidence": evidence},
))
```

- Severity map (R6): failed/stale → `ERROR`; degraded/gap/persistent-unknown → `WARN`; recovery → `INFO`.
- `emit()` returns `AlertResult`; the #706 ledger records every attempt+result (INV-C). No new delivery
  path (C-002).

## 5. CLI contract (`python3 -m scripts.canary.run`)

| Invocation | Behavior | Exit |
|---|---|---|
| `python3 -m scripts.canary.run [--once]` | one full pass: evaluate all → dedup → emit → write tick-signal + per-component ledger. The deployed timer form. | 0 on a completed pass (unhealthy components emit; they do not fail the exit); non-zero only on runner-level failure (which also triggers `OnFailure`). |
| `python3 -m scripts.canary.run --dry-run` | evaluate + print; NO emission, no dedup/tick/ledger writes | 0 |
| `python3 -m scripts.canary.run --self-check` | validate inventory readable + alert-bus importable + state dir writable; print `status=ok`/`status=error` | 0 / 1 |

- Module form (`python3 -m scripts.canary.run`) — never a bare script path (the `-m` trap).
- The deployed systemd `ExecStart` string and the deploy-time verification MUST be **byte-identical** (the
  #703 bare-python3 lesson): the deploy self-test runs the *exact* `ExecStart`, not a hand-typed variant.

## 6. Deploy contract (office2) — STRENGTHENED (F9)

`deploys/queued/00NN-felix-canary-registry.yaml`:
1. Installs `felix-canary.service` + `felix-canary.timer` (15-min) + the `OnFailure=` alert-shim unit;
   sets `EnvironmentFile` for the alert-bus topic (same pattern as felix-trust-scan); `daemon-reload`.
2. **Verify before enable (F9 — not just --self-check/--dry-run):**
   a. run `--self-check` (config/bus/state-dir) — must print `status=ok`;
   b. **run the real unit once** via `systemctl --user start felix-canary.service` (the actual `ExecStart`,
      under the unit's user + `EnvironmentFile`), then **assert** `last-tick.json` was written with a
      fresh `completed_at_utc` and a ledger line landed — proving the deployed command can write state +
      ledger under systemd (closes the #703 gap that `--dry-run` alone cannot, since `--dry-run` writes
      nothing);
   c. only then enable the timer.
3. **Rebaseline required** (systemd unit = audited surface); declare `expected_baselines` if any
   CLI-mutation drift has no repo-file signal.

## 7. Inventory registration (this mission adds two entries + one field)

- `felix-canary` runner: new inventory entry (`systemd-timer`, `active`, `tick-signal-file` health_check on
  its own `last-tick.json`, `max_age_seconds` ~2100) — FR-010 self-observability.
- restic-backup: **already registered** (F10) — only add `max_age_seconds: 100800` so the uniform freshness
  probe drives it.
