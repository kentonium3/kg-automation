# Data Model: Crontab Backup Coverage

Three artifacts. All are flat files on office2; there is no database.

## 1. Captured crontab artifact

**Path**: `/data/services/host-state/crontabs/claude.crontab`
**Owner**: `claude:claude`, mode `0644`
**Written by**: `scripts/office2/crontab_capture.py`
**Consumed by**: the restic backup (implicitly, as a file under a source path)
and by a human during recovery.

Content is the verbatim stdout of `crontab -l` for the `claude` user, preceded
by a comment header carrying provenance so the file is self-describing when
found in a snapshot months later:

```
# captured-by: crontab_capture.py
# captured-at-utc: 2026-08-28T01:00:04Z
# source-user: claude
# source-host: office2
# NOTE: reinstall with `crontab -` after stripping these header lines,
#       or `crontab <file>` — cron ignores leading comments.
```

**Invariants**

- The artifact is only ever replaced with a *non-empty* successful read. An
  empty or failed `crontab -l` leaves the previous content untouched (FR-004).
- **Shrink guard.** A successful but suspiciously truncated read is also refused:
  if a new body is more than 50% smaller than the existing artifact's body, the
  artifact is preserved and the run reports the anomaly exactly as the empty
  case does. `crontab -l` reading a local spool file is unlikely to return a
  partial success, but "unlikely" is not an invariant, and the cost of the guard
  is one comparison against a failure that silently destroys the thing this
  mission exists to protect. A genuine large deletion is recovered by rerunning
  with `--force`, which is logged.
- First run, with no existing artifact, is not a shrink and is never refused;
  only the empty/failed check applies.
- Replacement is atomic — write to a sibling temp file, then `os.replace`.
- The body below the header is byte-identical to `crontab -l` output, so the
  file is directly reinstallable (FR-003).
- Rewritten only when the body differs from what is already on disk, so an
  unchanged crontab produces no mtime churn (NFR-003).

## 2. Capture freshness pointer

**Path**: `/data/services/host-state/last-tick.json`
**Written by**: every run, success or failure — this is what makes a dead
capture visible rather than assumed-working.
**Consumed by**: the felix-canary freshness probe, via the `state-file`
health-check method.

```json
{
  "status": "success",
  "exit_code": 0,
  "completed_at_utc": "2026-08-28T01:00:04Z",
  "artifact_path": "/data/services/host-state/crontabs/claude.crontab",
  "artifact_bytes": 1043,
  "artifact_changed": false,
  "source_user": "claude"
}
```

**Field contract**

| Field | Meaning |
|---|---|
| `status` | `success` or `error`. Anything other than `success` is an explicit error to the probe. |
| `exit_code` | `0` on success; non-zero trips the canary's explicit-error path ahead of any freshness judgement. |
| `completed_at_utc` | The canary's preferred timestamp key; drives the staleness comparison. |
| `artifact_bytes` | Size of the body actually on disk, so a silently-truncated capture is visible. |
| `artifact_changed` | Whether this run rewrote the artifact. Diagnostic only; never affects health. |

**Invariants**

- `completed_at_utc` is always present — a pointer without it is uninterpretable
  to the probe and is reported as unknown, never healthy.
- On the FR-004 refusal path, `status` is `error` with a non-zero `exit_code`:
  preserving the old artifact is the correct data outcome but is *not* a healthy
  run, and must not read as one.
- Written atomically, same tmp + `os.replace` discipline as the artifact.

## 3. Drift-check freshness pointer

**Path**: `/data/services/openclaw/state/enforcement/last-tick.json`
**Written by**: `scripts/openclaw/enforcement/drift_check.py`, on every run.
**Consumed by**: the felix-canary freshness probe.

Follows the same field contract as (2), minus the artifact fields, **plus a
strict separation between runner health and drift result**:

```json
{
  "status": "success",
  "exit_code": 0,
  "completed_at_utc": "2026-08-28T06:00:11Z",
  "has_drift": true
}
```

**The exit-code mapping is the load-bearing part of this design.**
`drift_check.py:304` is `sys.exit(1 if has_drift else 0)`, and the canary treats
any non-zero `exit_code` in a pointer as an explicit failure that short-circuits
ahead of freshness (`probes.py:267-269`). Writing the process exit code straight
into the pointer would therefore make a perfectly healthy run that merely *found
drift* page as a broken component. The pointer's `exit_code` means "did the
runner execute correctly", never "was the result clean":

| Process exit | Meaning | `status` | pointer `exit_code` | `has_drift` |
|---|---|---|---|---|
| `0` | ran, no drift (or remediated) | `success` | `0` | `false` |
| `1` | ran, drift found (`report` mode) | `success` | `0` | `true` |
| `2` | runner errored | `error` | `2` | `null` |

**Invariants**

- Emitted for both the `check` and `report` subcommands, so the pointer reflects
  "the scheduled job ran", not "drift was found". Whether drift *exists* is a
  separate signal and must not be conflated with whether the check is alive —
  that conflation is what #891 fixed elsewhere, and inverting it here would
  manufacture false alarms instead of false silence.
- `has_drift` is diagnostic only and is deliberately **not** a field the canary's
  explicit-error scan looks at. Drift itself is reported by the drift-check's own
  alerting path, not by its liveness pointer.
- Pointer-write failure never aborts the run; a lost freshness signal is
  preferable to a crashed drift check, matching the established convention.

## Registration entries

Both components gain an entry in
`docs/design/architecture/data/service-inventory.json`:

| Component | `type` | `health_check.method` | `max_age_seconds` | Rationale |
|---|---|---|---|---|
| `crontab-capture` | `systemd_user_timer` | `state-file` | `7200` | Twice the hourly interval, per the sub-hourly convention. |
| `agent-drift-check` | `cron` | `state-file` | `108000` | 24h cycle plus 6h slack, mirroring `security-monitor`. |

Both declare an absolute `state_path` and an integer `max_age_seconds`, as
required by the canary data-guard test.
