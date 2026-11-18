# Contract: Baseline comparison, gate, preflight and acceptance

## Schema identity (`sqlite-master-sha256-v1`)

SHA256 of canonical UTF-8 JSON (sorted keys, compact separators, nulls preserved) of the rows from:

```sql
SELECT type, name, tbl_name, sql
FROM main.sqlite_master
ORDER BY type COLLATE BINARY, name COLLATE BINARY, tbl_name COLLATE BINARY;
```

The hash excludes `rootpage`, the schema cookie and file layout. It is computed on a consolidated copy. SQL text is not normalised, so a difference fails for review.

## `baseline.compare(snapshot_path, baseline) -> Result`

| Check | Pass condition |
|---|---|
| Migrations | The snapshot's IDs equal `pre_upgrade_migration_ids` exactly |
| Schema | Schema identity equals `schema_identity.pre_upgrade` |
| Aggregates | Task count, repeat count and hash, expected subscriptions and duplicate excess are all computable |

Used by the gate and preflight. Returns a stable code and, separately, a private aggregate object that is never printed.

## Expected subscriptions

Computed on the pre-upgrade snapshot. Eligible pairs are task creators and assignees that join to an existing user; `UNION` removes duplicates. Expected total is the count of `subscriptions` rows with `entity_type = 3`, plus eligible pairs that have no such row. Full SQL: `research.md`, Subscription expectation.

## Gate (inside ACTIVATE)

- Deadline: `min(30 seconds, remaining outage)`.
- Order: load baseline, compare, write the receipt durably, then return.
- Any failure raises a stable gate code. No `docker tag` or Compose `up` call follows.
- `GATE_DEADLINE` means the gate's own deadline expired. `ACTIVATE_OUTAGE_DEADLINE` means the overall outage limit did, and takes precedence when both apply.

## `preflight_release_baseline.py`

- Run on Office2 by the `claude` user, after STAGE and before ACTIVATE.
- Arguments: release record path.
- Exit 0 prints `PREFLIGHT_OK` and elapsed seconds. Any other outcome prints one stable code and exits non-zero.
- `PREFLIGHT_COPY_UNSTABLE` after five rounds means a writer is active and the copy could not settle. It is inconclusive, not a baseline result, and the cutover does not proceed.
- Comparison alone must take at most 25 seconds, which leaves room for the receipt inside the gate's 30-second limit. Consolidation plus comparison must take at most 90 seconds, which leaves the 180-second readiness poll and about 30 seconds of Docker work inside the 300-second limit. Over that it prints `PREFLIGHT_OVER_BUDGET` and exits non-zero.
- Removes its private copy on every exit path, and prints no path or value.

## `build_release_baseline.py`

- Arguments: a consolidated pre-upgrade copy, a post-upgrade copy, the release record that supplies the rollback identity, and an output path.
- Writes only the fields in the Qualified baseline entity of `data-model.md`, and refuses to write anything else.
- Run once by Claude Opus 5.5 from private copies when preparing the STAGE package. It is not part of the cutover.

## `verify_release_upgrade.py`

- Arguments: private snapshot directory and a stable private post-upgrade copy.
- Runs with writes closed, before the disposable write probe.
- Passes only when all of these hold:
  - All pre-upgrade migration IDs remain and exactly the ten reviewed IDs were added.
  - Schema identity equals `schema_identity.target`.
  - Task count and repeat count and hash match the receipt.
  - `integrity_check` is `ok`.
  - Task subscriptions equal the expected total, no eligible pair is missing, duplicate excess is unchanged, and existing subscription keys and muted choices are preserved.
- Prints per-check pass or fail codes. Aggregates are written only to a private file under the snapshot directory for Claude to report to Kent.
