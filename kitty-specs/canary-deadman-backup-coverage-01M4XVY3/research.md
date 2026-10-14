# Research: Canary dead-man's switch and backup coverage

All findings were probed live on office2 or read from source on 2026-10-14. Format: Decision / Rationale / Alternatives.

## Facts established (load-bearing)

- **F1 — The wrapper is already in the repo; the script is not.** `felix-health-check.service` runs `python3 -m scripts.office2.felix_health_check.run` from `/home/claude/kg-automation` (the felix-deployer checkout). `run.py` shells out to `HEALTH_CHECK_SCRIPT = /home/claude/helper-scripts/health-check.sh`, which is 40 lines dated 2026-04-07 and untracked. No OpenClaw cron references it: `openclaw cron list` shows no health job. The only remaining hits are `jobs.json.migrated` / `.bak`, which are inert. Its "Called by OpenClaw cron" header is stale since #676.
- **F2 — The reverse watch exists.** The canary's `felix-health-check` inventory entry is a `signal-file` probe of `last-run.json`, with `max_age_seconds` 46800, `success_status_values` `[ALL_HEALTHY, FAILURES_DETECTED]` and freshness anchor `ran_at_utc`. `UNKNOWN` / `SCRIPT_MISSING` fail it (#891).
- **F3 — The canary's per-component evaluation is pure and reusable.** `scripts.canary.registry.load_targets(inventory)` → `CanaryTarget`s; `scripts.canary.health.evaluate(target, now, *, http_get, run_cmd, read_state)` → `HealthResult(outcome ∈ {healthy, stale, failed, unknown, suppressed, …}, evidence)`. It never raises (INV-D), and its effects are injected. For `restic-backup` it dispatches to the ledger-aware freshness probe (`key_ledger` evaluator + anchor resolution). For `felix-canary` it dispatches to the legacy `tick-signal-file` freshness path: `completed_at_utc` anchor, 2100 s bound, `status` explicit-error conventions.
- **F4 — The live documents (2026-10-14 ~18:45Z).** `last-tick.json` = `{completed_at_utc, components_evaluated: 32, coverage_gaps: 0, duration_ms, emitted, errors: [], status: "success", suppressed_dedup, suppressed_status}`. `last-backup.json` is schema v2 with 14 keys (the 15:30:30Z manual snapshot). Both are captured verbatim as fixtures.
- **F5 — The incident pointer shape is derivable from the producer.** `restic-backup.sh` sets `BACKUP_RC=127` / `PRUNE_RC=127` sentinels, and an EXIT trap writes the pointer on every run. On "not mounted" it `exit 1`s before restic runs. `restic snapshots` against the missing repo fails, so `snapshot_timestamp_utc` / `snapshot_id` / `snapshot_count` are `null`; `du` / `df` / `restic stats` fail, so `repo_size_bytes` / `files_processed` / `repo_fs_free_bytes` are `null`; `last_integrity_check_utc` is carried forward. The 17-day fixture is built from that, not invented.
- **F6 — `_explicit_error` and `TIMESTAMP_KEYS` share a namespace with the run record.** The canary probes `last-run.json` through the legacy path, which reads these **top-level** keys: `restic_exit_code`, `prune_exit_code`, `exit_code` (non-zero int → fail), `exit_status`, `status` (allow-list), `errors` / `error` / `cycle_error` (truthy → fail). The anchor is the *first present* of `completed_at_utc`, `snapshot_timestamp_utc`, `script_finished_at_utc`, `ran_at_utc`, …. See [contracts/health-check-run-record.md](contracts/health-check-run-record.md).
- **F7 — Rebaseline on a no-drift audited edit is clean.** `rebaseline.reconcile` with D = ∅ → `pending_clean` within grace, then `cleared_clean` (`scripts/deploy/felix-deployer/rebaseline.py:833–845`). Editing `scripts/office2/deploy/felix-health-check.sh` (audited pattern `scripts/office2/deploy/*.sh`) without changing any deployed unit is therefore safe to declare.
- **F8 — The unit has no `OnFailure=`.** A crashing wrapper ends as systemd `failed` with no push. The backstop is the canary's 13 h freshness probe on `last-run.json`.

## Decisions

### R1 — Evaluate by calling `scripts.canary.health.evaluate` on the inventory target

- **Decision**: `coverage.py` loads the inventory (repo checkout path resolved from `__file__`, not the CWD), calls `registry.load_targets`, selects the targets named `felix-canary` and `restic-backup`, and calls `health.evaluate` on each.
- **Rationale**: this is the canary's exact path from declaration to verdict, gate and fail-safe included. Agreement (FR-003) then holds by construction, and the agreement test is a ratchet against a future parallel implementation. C-001 is satisfied: no predicate text is copied.
- **Alternatives**: (a) call `probes.run_probe` directly. Rejected: it skips the alert-eligibility gate and the outcome mapping, which would make a second mapping that can drift. (b) Call `ledger.evaluate` only for restic. Rejected: that misses anchor-freshness resolution, which lives in `probes.py`, and would need a second code path for the canary. (c) Ask the canary for its last verdict, i.e. read the canary ledger. Rejected: it depends on the canary *running*, which is the thing being watched (C-002).

### R2 — Outcome → verdict mapping

| canary `HealthResult.outcome` | finding class | contributes |
|---|---|---|
| `healthy` | ok | nothing |
| `stale`, `failed`, `degraded` | failure | `FAILURES_DETECTED` |
| `unknown` | unknown | `UNKNOWN` |
| `suppressed` (declaration not alert-eligible) | unknown | `UNKNOWN` (see R3) |
| any other or new string | unknown | `UNKNOWN` (fail closed on vocabulary drift) |

- **Rationale**: the canary withholds alerts on a *first-seen* `unknown`, because its dedup persistence decides that. The health check runs only twice a day and has no persistence layer, so it alerts on unknown immediately. That is consistent with its existing behavior (UNKNOWN already alerts) and with principle 14.

### R3 — `suppressed` is unknown, not healthy

- **Decision**: if either coverage component's declared status leaves it not alert-eligible (`suspended`, `deprecated`, …), the finding is unknown, with evidence naming the status.
- **Rationale**: these two components are the dead-man's targets. Suspending either one silently disables the switch, and that is a coverage hole Kent should hear about twice a day until it is undone. The canary's own suppression means "don't page about this component". The health check's question is different: "can I vouch for backup and canary health?", and the answer is no.
- **Alternative**: honour suppression silently, as the canary does. Rejected, because it reintroduces a "healthy verdict that never looked".

### R4 — Effects: file reads only; refuse the rest

- **Decision**: pass `read_state` = a JSON file reader. Pass `http_get` / `run_cmd` = functions that **raise** (`RuntimeError("coverage checks are file-read only")`). `health.evaluate` turns that into `unknown`.
- **Rationale**: both current declarations are file methods (`tick-signal-file`, `state-file`). If someone later repoints either to an `http` / `shell` method, the health check fails closed and visibly; it never silently executes an inventory-declared shell command from a twice-daily timer. This also bounds run time (NFR-002).

### R5 — Inability handling and the import boundary

- **Decision**: `run.py` imports `coverage` lazily inside a guarded call. Any exception from loading or evaluating coverage (ImportError, inventory unreadable or malformed JSON, target missing) becomes one unknown finding per affected component, with evidence; it never escapes `main`. The coverage checks run **regardless** of the shell script's outcome (missing, timeout, normal).
- **Rationale**: NFR-003. The unit has no `OnFailure=` (F8), so a crash is silent for up to 13 h. Coverage independence: a missing shell script must not also blind the dead-man's switch.
- **Alternative**: add `OnFailure=` to the unit. Rejected for this mission: it changes deployed unit content (rebaseline drift) and duplicates the canary's freshness backstop. Fail-closed in-process is the primary defense.

### R6 — Verdict precedence

`FAILURES_DETECTED` (any script failure token or coverage failure) > `SCRIPT_MISSING` > `UNKNOWN` (script unknown/timeout, or any coverage unknown) > `ALL_HEALTHY`. The existing `classify()` is reused unchanged for the script's own output and then combined. This keeps the canary-visible status vocabulary closed: no new status words (FR-006).

- **Consequence, accepted**: when the script is missing *and* a coverage check fails, the status is `FAILURES_DETECTED`, which the canary's probe reads as a healthy runner. Kent is still told, because the alert body names the missing script. The record shows it too, through `exit_code: null` and `script_path`. Documented in the contract.

### R7 — The run record gains exactly two keys: `coverage_checks` (list) and `script_path` (string)

- **Decision**: `coverage_checks: [{"component": str, "outcome": <canary outcome>, "finding": "ok"|"failure"|"unknown", "evidence": str}]` and `script_path: str`. Nested objects carry **no** top-level key from F6's lists, and no timestamp.
- **Rationale**: FR-006/F6. A top-level `errors` or `status`-like key, or a `completed_at_utc` hoisted from the canary's tick, would change how the canary judges the health check. With `completed_at_utc` the canary would anchor on the *canary's* tick time instead of `ran_at_utc`. That is a silent watch-swap. A contract test pins it: the canary's real probe, run against a record written by a failing-coverage run, still reports the health check healthy and anchors on `ran_at_utc`.

### R8 — Script location and retirement

- **Decision**: the script moves to `scripts/office2/felix_health_check/health-check.sh` (git mode 100755), resolved as `Path(__file__).with_name("health-check.sh")`. The deploy apply moves `~/helper-scripts/health-check.sh` to `/data/services/openclaw/felix-health-check/retired/health-check.sh.<UTC date>`. It is not deleted, so the move is reversible. The now-empty `~/helper-scripts/` directory is left alone (memory: helper-scripts is a known location on both accounts).
- **Rationale**: FR-007/FR-008. Moving instead of deleting avoids `rm`-class risk and keeps the 2026-04-07 original for forensics.
- **Retirement ordering**: retire only *after* a verified run that recorded `script_path` = the repo path. The old copy is then provably unused when it is moved.

### R9 — Post-downtime catch-up alert is accepted

The timer is `OnCalendar` + `Persistent=true` (calendar-only, so the #1062 guard permits it). After downtime spanning 11:00 or 23:00 it fires at manager start, possibly before the canary's first post-boot tick, and reports the canary stale. That is true and informative after an outage. A grace window would hide a canary that is dead from boot, which is exactly #1062. Rejected.

### R10 — Duplicate backup alerts

When the canary is alive and the backup fails, both watchers alert: the canary per its dedup windows, the health check at most twice a day. They are distinct, labeled sources (`felix-canary/…` vs `felix-health-check/run`). Accepted as redundancy; no cross-suppression, since cross-suppression is the coupling C-002 forbids.

## Open risks for reviewers

- R3 (suppressed → unknown) is a judgment call; reviewers should challenge it.
- ~~Import cost / side effects of `scripts.canary.*`~~: measured at 0.025 s, with no I/O at import (2026-10-14).
- ~~Is `scripts/office2/felix_health_check/tests/` collected?~~ Yes: a bare `pytest` from the repo root collects it (16 existing tests).

## Post-plan review dispositions (2026-10-14)

Reviewers: **Codex** (GPT, `codex exec -s read-only`): REJECT. **paula-patterns** (Claude Sonnet): APPROVE-WITH-CHANGES. **debugger-debbie** (Claude Sonnet): CONFIRMED-WITH-GAPS. Implementer: Claude Opus 5.5. Codex's HIGH 1 and HIGH 3 were reproduced by the implementer before acceptance.

Debbie's incident replay through the real code with the real inventory: on 2026-09-28 11:00Z, `restic-backup` → `failed` ("restic_exit_code=127 not in good_values [0, 3]") and `felix-canary` → `stale` (age 54003 s vs 2100 s). So the plan does close the 17-day silence.

| # | Finding | Disposition |
|---|---|---|
| Codex-1 HIGH | `felix-canary`'s legacy `tick-signal-file` path reads missing/`partial` status, a broken anchor plus a fresh fallback timestamp, and `components_evaluated: 0` as **healthy** (reproduced: all four `healthy`). The dead-man's switch would be blind to a canary that ticks but does nothing. | **Accepted → R11 / FR-011.** `felix-canary` adopts a `key_ledger` (the contract's "second producer" path) with its own reconciliation harness. |
| Codex-2 HIGH | Deploy verification on combined status can accept missing coverage or failed delivery. | **Accepted → IC-03.** Verify per entry: exactly the two components, neither `unknown`/`unavailable`/`suppressed`; shell ran (`exit_code` is an int, classified); `delivery.sent` is true whenever an alert was required; the record's `ran_at_utc` ≥ the apply start. |
| Codex-3 HIGH | The bus truncates each `details` value to 500 chars (`render.py:25`), so coverage appended after shell output is lost (reproduced: `DETAIL_VALUE_MAX = 500`). | **Accepted → FR-005 / contract.** Each non-ok coverage finding is its own `details` entry (`coverage:<component>`), inserted before `output`. Tested through the real bus renderer. |
| Codex-4 MED | Removing `max_age_seconds` silently turns freshness into liveness-only. | **Accepted → R12 / FR-012.** Declaration preconditions are checked before evaluation (unknown at runtime) and pinned in CI against the real inventory. |
| Codex-5 MED | Invariant 3(b) holds only when the shell exit code is 0 or null. | **Accepted.** Contract scoped; shell-failure-plus-coverage cases added. The shell script exits 0 by construction (it echoes a verdict), and existing behavior is preserved. |
| Codex-6 MED | Only `TimeoutExpired` is caught around the shell run. | **Accepted → R5 widened.** Any exception from launching or decoding the shell run → script result `UNKNOWN` with evidence. Coverage is evaluated before the shell run and independently of it. One record/alert path. |
| Codex-7 MED | The inventory `felix-health-check` dependency field and `scripts/deploy/deploy-deterministic-monitoring-checks.py` still reference the retired path. | **Accepted → IC-03/IC-04.** Dependency fields are updated. The old entrypoint's preflight is repointed to the repo script (it is an applied record's entrypoint, so it is updated, not deleted). |
| Paula-1 / Debbie-3 MED | Shared fate: same code, host, checkout and alert channel. | **Partly accepted.** (a) The limit is documented in `observability-and-alerting.md` and the inventory note. (b) Named sentinel fixtures (the incident's 127 pointer and a 17-day-dead tick) assert `failed`/`stale` through the real evaluator, so a canary-code regression fails CI. (c) **Declined:** a runtime mtime leg would be a second, hand-authored freshness definition (violates C-001). The evaluator only changes through CI, which (b) guards. Off-host heartbeat and channel loss → follow-up issue. |
| Paula-2 MED | The run-record key namespace is coupled to `_explicit_error` / `TIMESTAMP_KEYS`. | **Accepted (test) + follow-up (structure).** The contract test derives the ranked timestamp keys from `probes.TIMESTAMP_KEYS` at runtime and drives the real probe over each forbidden-key variant. Structural fix (give `felix-health-check` a `key_ledger` too) → follow-up issue. |
| Paula-3 LOW | R3 is right; make the evidence actionable. | **Accepted:** evidence reads "status '<s>' not alert-eligible: coverage withheld". |
| Paula-4 MED | The hard-coded tuple can drift from the inventory. | **Accepted → FR-012 CI test:** both components exist, are alert-eligible and meet the declaration preconditions. A third dead-man target triggers the declarative inventory flag (rule of three). |
| Paula-5 LOW | Script-missing masked by `FAILURES_DETECTED`. | **Accepted:** the alert lists `script` first; test asserts both appear in the rendered body. |
| Paula-6 / Debbie LOW | No uncaught path; different-CWD test. | **Accepted:** a test raises inside coverage and asserts exit 0 plus an `UNKNOWN` record. Another runs from a different CWD. |
| Paula-7 LOW | Re-apply idempotency. | **Accepted:** the second apply, with the host copy already retired, succeeds. |
| Debbie-2 LOW | `load_targets` returns `(targets, gaps)`. | Noted for the implementer. |
| Debbie-3 LOW | Future-dated fixture; post-boot catch-up wording. | **Accepted:** a future-dated tick fixture is added. Stale-canary evidence appends "(host up <N> min: may be a post-boot catch-up)" when uptime is below the canary bound. Informative only; never changes the finding. |
| Debbie-1 MED | Direct backup alert deferred. | Already tracked: kentonium3/kg-automation#1067. |

### R11 — `felix-canary` adopts a key ledger

`adjudicated`:
- `status` with `good_values ["success"]`. The canary writes `"error"` iff `errors` is non-empty (`run.py:462`), so `status` subsumes the legacy truthy-`errors` rule.
- `completed_at_utc` with `freshness` and `anchor: true`. The bound comes from the existing `max_age_seconds` 2100.
- `components_evaluated` with `minimum: 1`. A canary that evaluates nothing is not alive.

`diagnostic_only`: `errors` (summarised by `status`), `emitted`, `suppressed_dedup`, `suppressed_status`, `coverage_gaps` (the canary already pages gaps itself) and `duration_ms`.

`reconciliation_harness`: `tests/canary/test_tick_ledger_reconciliation.py`. It executes `scripts.canary.run.run_pass` under injected effects and reconciles the written tick document. The existing restic harness's selection test (`assert_selection_matches(set(REAL_LEDGERS), …)`) picks the new ledger up automatically.

This also strengthens the canary's self-probe, an accepted side effect that is documented in the inventory note.

### R12 — Declaration preconditions (validation, not predicate)

Before evaluating, `coverage.py` requires that each target's `health_check` has a numeric `max_age_seconds` > 0 and a `key_ledger` with exactly one `anchor: true` freshness key. Otherwise the finding is `unknown`, "declaration lacks a freshness bound/anchor". The same function runs in CI against the real inventory. This checks the *shape* of the declaration the evaluator needs and restates no value from it.
