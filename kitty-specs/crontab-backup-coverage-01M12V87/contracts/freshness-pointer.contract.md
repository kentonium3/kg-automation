# Contract: freshness pointers emitted by this mission

Both components this mission adds or registers communicate their health through a
single interface: a small JSON pointer on disk, read by the felix-canary
freshness probe. This file is the contract for that interface. It exists because
the interesting failure is not "the file is malformed" — it is "the file is
well-formed and says the wrong thing", which no schema catches.

**Consumer**: `scripts/canary/probes.py` — `_probe_freshness` for staleness,
`_explicit_error` for failure, via `health_check.method: state-file`.

## Field contract

| Field | Required | Meaning |
|---|---|---|
| `completed_at_utc` | yes | ISO-8601 UTC, `%Y-%m-%dT%H:%M:%SZ`. The canary's first-choice timestamp key. **A pointer without it is uninterpretable and is judged `unknown`, never healthy.** |
| `status` | yes | `success` or `error`. Any non-success value is an explicit failure. |
| `exit_code` | yes | `0` on a healthy run. **Non-zero short-circuits ahead of freshness.** |

Producers may add diagnostic fields, subject to the naming rule below.

## Rule 1 — `exit_code` means "the runner executed", never "the result was clean"

This is the load-bearing rule and the one a future reader is most likely to
"fix" back into a bug.

`drift_check.py` ends with `sys.exit(1 if has_drift else 0)`. Exit `1` therefore
means **"I ran correctly and found drift"** — a successful run. But
`probes.py:267-269` treats any non-zero `exit_code` in a pointer as an explicit
failure. Copying the process exit code into the pointer would make every
drift-finding run page as a broken component, which trains the operator to
ignore the alert, which is how a real failure gets missed.

The mapping is therefore:

| Process exit | Meaning | `status` | pointer `exit_code` | `has_drift` |
|---|---|---|---|---|
| `0` | ran, no drift | `success` | `0` | `false` |
| `1` | ran, found drift | `success` | `0` | `true` |
| `2` | runner errored | `error` | `2` | `null` |

The *result* rides in a separate field. The pointer answers one question only:
did the scheduled work happen.

## Rule 2 — diagnostic field names must avoid the explicit-error scan

`_explicit_error` inspects `restic_exit_code`, `exit_code`, `exit_status`,
`status`, `errors`, `error`, and `cycle_error`. A diagnostic field must not use
any of those names, or it will silently become a health signal.

This is why the fields are `has_drift`, `artifact_changed`, and `artifact_bytes`
rather than the more natural `error_count` or `drift_status`.

## Rule 3 — a refusal is not a success

`crontab_capture.py` refuses to overwrite a good artifact with an empty, failed,
or suspiciously truncated read. Preserving the prior artifact is the correct
*data* outcome, but it is **not** a healthy run: it means the capture is not
currently protecting anything new. A refusal writes `status: error` with a
non-zero `exit_code`.

The temptation is to treat "nothing to do" as success. That would produce a
component that reports healthy for as long as the crontab is unreadable — the
#891 defect class, a check that cannot fail.

## Rule 4 — write on every exit path

The pointer must be written on success, on refusal, and on unexpected failure.
A run that dies without writing is indistinguishable from a run that never
started, and only becomes visible after `max_age_seconds` elapses — hours later
for a daily component. Both producers wrap their run so any escape records an
error pointer before propagating.

Pointer-write failure itself is never fatal: losing the freshness signal is
strictly better than crashing the work the signal describes.

## Rule 5 — not under `/tmp`

`systemd-tmpfiles --remove --boot` empties `/tmp`, so a pointer there vanishes on
reboot and produces a spurious staleness alert.
`tests/canary/test_inventory_health_checks.py:131` pins the set of components
probing `/tmp`; only `obsidian-sync-heartbeat` is grandfathered, owned by #894.

## Registration requirements

A `state-file` health check must declare an **absolute** `state_path` and an
integer `max_age_seconds`. Omitting the bound silently degrades the probe to
liveness-only, which passes forever. Sizing convention: roughly twice the
interval for sub-hourly and hourly components; cycle plus slack for daily ones.

| Component | Pointer | `max_age_seconds` |
|---|---|---|
| `crontab-capture` | `/data/services/host-state/last-tick.json` | `7200` (2× hourly) |
| `agent-drift-check` | `/data/services/openclaw/state/enforcement/last-tick.json` | `108000` (24h + 6h) |

## How this contract is verified

Not by reading the JSON. At WP review each registered check was driven through
the real `scripts.canary.probes.run_probe` and required to satisfy all four:

- fresh + success → healthy, not stale
- aged past `max_age_seconds` → **stale** (proves the check can fail)
- runner error → **not ok**
- drift found → **healthy** (proves Rule 1 holds)
