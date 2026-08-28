# Contract: backup integrity signals

Three defects in this mission shared one shape — a mechanism meant to make
failure visible did not. This file records the interfaces that resulted, and the
rules that keep them honest. It exists because in every case the failure was not
a wrong value but an *unenforced coupling*: two things that had to agree, with
nothing checking that they did.

## Signal 1 — `last-backup.json` (modified)

**Producer**: `scripts/office2/restic-backup.sh`, from its `EXIT` trap.
**Consumers**: the felix-canary freshness probe, and
`scripts/deploy/lib/snapshot.py`'s Tier-2 backup-recency gate.

| Field | Good set | Meaning |
|---|---|---|
| `restic_exit_code` | `{0, 3}` | The backup step. `3` is accepted because a backup exiting 3 completed with warnings but **still produced a snapshot**. |
| `prune_exit_code` | `{0}` | The `restic forget --prune` step. **Narrower on purpose.** `forget` exiting 3 means snapshots could not be removed, which is not a successful retention pass. `127` = never attempted. |
| `snapshot_timestamp_utc` | must be **parseable** | Not merely present, and not merely a non-empty string. |

### Rule 1 — the prune good-set must never be merged with the backup's

The single most likely future regression is someone noticing two near-identical
frozensets and tidying them into one. That would silently accept a prune that
never applied retention — the exact #902 failure. `_PRUNE_OK_EXIT_CODES` carries
a comment saying so, and a test pins it.

### Rule 2 — "usable timestamp" means parseable

`TIMESTAMP_KEYS` falls through: `completed_at_utc` → `snapshot_timestamp_utc` →
`script_finished_at_utc`. So a restic pointer whose snapshot timestamp is absent,
null, **or malformed** would resolve against the script-finished anchor and read
fresh, for a run that produced no snapshot at all.

A first attempt guarded only against absent/empty and was still wrong: a truthy
`"not-a-date"` passed. The guard is `_parse_iso(...) is not None`.

### Rule 3 — 127, never null

`_explicit_error` guards with `isinstance(code, int)`, so a non-integer is
*skipped*. A `null` "not attempted" value therefore reads **healthy**. The
sentinel is `127`, matching the existing `BACKUP_RC` convention.

### Rule 4 — alerting and gating are deliberately asymmetric

A prune failure makes the **component** unhealthy. It must **not** gate Tier-2
deploys: the snapshot is intact and restorable, which is all a pre-flight needs
to know. Retention failure is disk hygiene, not backup invalidity.

This asymmetry is load-bearing and counter-intuitive, so it is stated in three
places: `snapshot.py` reads only `restic_exit_code` and the timestamp; the
governance pre-flight check documents *why* it does not test prune; and the
component-health check does test it.

## Signal 2 — `script-drift-last-tick.json` (new)

**Producer**: `scripts/office2/backup_script_drift.py`, daily.

| `verdict` | `status` | `exit_code` | Healthy? |
|---|---|---|---|
| `match` | `success` | 0 | yes |
| `drift` | `error` | 1 | no |
| `inconclusive` | `error` | 2 | **no** |

### Rule 5 — not knowing is never agreement

`inconclusive` means the comparator could not read one side: missing, unreadable,
a symlink, or not a regular file. Reporting that as `match` would convert an
unknown into a false assurance — the failure this component exists to prevent.

### Rule 6 — reads must not follow symlinks

The deployed file is a `NOPASSWD` sudo target. If it were a symlink into
`/home/claude/kg-automation/`, following it would hash the repo copy and report
`match` — blessing precisely the condition where the sudo target has become
claude-controlled. Reads use `O_NOFOLLOW` and require `S_ISREG`.

### Rule 7 — this component never writes to the guarded directory

`/data/services/backup/scripts/` must stay non-claude-writable; a writable
directory on a NOPASSWD path is equivalent to `NOPASSWD: ALL` (#899). The
comparator observes only, and refuses a `--state-path` under that prefix so its
own write primitive cannot be aimed there.

### Rule 8 — declare `success_status_values`

Without an allow-list, `probes.py` treats `status` as a *deny-list*: any word it
does not recognise as a failure passes. A future verdict word would read healthy
by default. Verified: an unrecognised status reports `ok=False` only because the
allow-list is declared.

## Signal 3 — the captured crontab body

**Producer/reader**: `scripts/office2/crontab_capture.py`.

### Rule 9 — one implementation of "where the header ends"

`split_header()` is the only place that computes it. Capture is tolerant
(unrecognised content is body, backed up faithfully); `--emit-body` is strict
(unrecognised content is refused, because the output is piped into `crontab -`
and becomes executable schedule).

Header removal previously existed twice — once in code, once in prose — and the
prose rotted. Correcting the prose would have re-armed the trap; removing the
second implementation is what actually fixes it.

### Rule 10 — recognition requires an exact first line

A prefix match would accept a foreign file merely beginning with the header text
and, if the sentinel appeared later, emit only the tail — handing the operator a
silently **truncated** crontab rather than a refusal.

## How these rules are enforced

Not by review. Each has a test that fails if it is broken: the prune good-set is
pinned, the unparseable timestamp is asserted unhealthy, the drift guard fails if
the header format changes without the emitter, the symlink cases assert
`!= match`, and the inventory prose is asserted to mention `prune_exit_code`.
That last one exists because this mission would otherwise have fixed two
unenforced couplings and created a third.
