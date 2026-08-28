# Data Model: Backup Integrity Observability

## 1. Backup state pointer (modified)

**Path**: `/data/services/backup/state/last-backup.json`
**Written by**: `restic-backup.sh`, via its `EXIT` trap, on every run.
**Consumed by**: the felix-canary freshness probe (`state-file`), and Tier-2
pre-flight checks that read backup currency.

```json
{
  "schema_version": 1,
  "snapshot_timestamp_utc": "2026-08-28T11:01:57Z",
  "snapshot_id": "29fd275e...",
  "restic_exit_code": 0,
  "prune_exit_code": 0,
  "script_finished_at_utc": "2026-08-28T11:02:05Z",
  "repo_size_bytes": 3822232961,
  "snapshot_count": 14,
  "integrity_check_run": false,
  "integrity_check_passed": null
}
```

**The one new field**

| Field | Meaning |
|---|---|
| `prune_exit_code` | Exit status of `restic forget --prune`. `0` = retention applied. Non-zero = it failed. **`127` = never attempted** — the run died before reaching the prune step. |

**Invariants**

- Initialised to `127` before anything runs, matching the existing
  `BACKUP_RC=127` convention. Never `null`: a non-integer is skipped by the
  explicit-error scan and would read as healthy, which is the silent-success path
  being closed.
- Every other field keeps its name, type, and meaning. A pointer written before
  this change stays interpretable — the new key is simply absent, and the scan
  ignores absent keys (NFR-002).
- Written by the same `EXIT` trap as the rest of the pointer, so it is recorded
  on failure paths too.

## 2. Backup-script drift pointer (new)

**Path**: `/data/services/backup/state/script-drift-last-tick.json`
**Written by**: `backup_script_drift.py`, every run.
**Consumed by**: the felix-canary freshness probe.

```json
{
  "status": "success",
  "exit_code": 0,
  "completed_at_utc": "2026-08-28T12:00:04Z",
  "verdict": "match",
  "repo_md5": "767da888...",
  "deployed_md5": "767da888..."
}
```

**Verdict vocabulary** — `verdict` is diagnostic; `status`/`exit_code` carry health:

| `verdict` | Meaning | `status` | `exit_code` |
|---|---|---|---|
| `match` | Both copies present and identical | `success` | `0` |
| `drift` | Both present, contents differ | `error` | `1` |
| `inconclusive` | Deployed copy missing or unreadable | `error` | `2` |

Registration MUST declare `success_status_values: ["success"]`. Without an
allow-list, `probes.py` treats `status` as a deny-list — any word it does not
recognise as a failure passes. A future verdict word would then read healthy by
default. This is the #891 affirmative-health rule.

**Invariants**

- `inconclusive` is never healthy. A comparator that cannot see the deployed copy
  knows nothing, and reporting nothing-known as agreement is the failure it
  exists to prevent (R-05).
- Observe-only. It never writes to `/data/services/backup/scripts/` — that
  directory must stay non-claude-writable (C-001), and remediation is the
  operator's privileged step.
- `verdict` is deliberately named to avoid the explicit-error scan's keys
  (`error`, `errors`, `exit_status`, `cycle_error`), so health is carried only by
  `status` and `exit_code`.

## 3. Captured crontab artifact (unchanged shape, new access path)

No format change. What changes is that the body can now be obtained through the
writer's own `strip_header()` rather than a hand-written pattern:

```
python3 scripts/office2/crontab_capture.py --emit-body
```

**One parser, not two.** Today's `strip_header()` returns its input unchanged
when the first line does not match *and* when the first line matches but the
sentinel is missing — it cannot tell a caller whether a header was recognised.
Reusing it as-is would let `--emit-body` emit a headerless or truncated file as
though it had been verified, which during recovery installs wrong content
silently.

So `strip_header()` is refactored into one shared parser returning both the body
and whether a well-formed header was recognised. Capture keeps today's tolerant
behaviour; `--emit-body` fails closed on unrecognised or malformed input. The
point is to keep exactly one implementation — adding a second recogniser in the
CLI path would recreate the coupling this mission exists to remove.

**Invariants**

- Writes nothing. It is used during recovery, when the artifact must not be
  disturbed.
- Output is byte-identical to the `crontab -l` input that produced the artifact —
  enforced by a round-trip test, so a header-format change that is not matched by
  the emitter fails the suite (NFR-003, SC-005).
- Exits non-zero if the artifact is missing or has no recognisable header, rather
  than emitting a partial or headerless body that would silently install wrong
  content.

## Registration

| Component | `type` | `health_check.method` | `max_age_seconds` | Rationale |
|---|---|---|---|---|
| `restic-backup` (modified) | `cron` | `state-file` | `100800` (unchanged) | `expected` prose corrected to state the prune rule, which will otherwise be false. |
| `backup-script-drift` (new) | `systemd_user_timer` | `state-file` | `108000` | Daily cadence plus slack, mirroring `security-monitor`. |
