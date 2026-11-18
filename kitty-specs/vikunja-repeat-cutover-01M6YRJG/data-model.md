# Data Model: Vikunja repeat cutover support

## Release record (`services/vikunja/release.json`)

Adds one optional object to the existing schema. Unknown keys stay rejected. A repeat cutover needs it: the ACTIVATE gate fails closed when it is absent, and the change-set tests require it for the current release.

| Field | Rule |
|---|---|
| `baseline.path` | Repository-relative, contained under `services/vikunja/baselines/` |
| `baseline.sha256` | Lowercase hex; matches the exact bytes that are parsed |

The release and rollback versions, archives, hashes, sizes, config IDs and tags follow the existing schema. `version` must match the extended version pattern.

## Qualified baseline (committed, data-free)

| Field | Rule |
|---|---|
| `schema_version` | Integer, currently 1 |
| `previous_version`, `previous_image_config` | Must equal the release record's rollback identity |
| `pre_upgrade_migration_ids` | Sorted, unique |
| `added_migration_ids` | Sorted, unique, disjoint from pre-upgrade IDs |
| `schema_identity.algorithm` | `sqlite-master-sha256-v1` |
| `schema_identity.pre_upgrade`, `schema_identity.target` | Lowercase hex |

No row counts, repeat hashes, paths or times.

## Private baseline receipt (Office2 only)

`<snapshot_dir>/baseline.json`, directory 0700, file 0600, exclusive and no-follow, fsynced with its parent directory before the image is retagged.

Binds the snapshot SHA, baseline SHA, release version and config ID to the migration set, schema identity, task count, repeat count and hash, expected task subscription total, and existing duplicate excess.

`repeat_hash` is the SHA256 of canonical JSON of `(id, repeats, repeats_from_current_date)` tuples, ordered by `id`, for rows with a non-empty rule. Canonical JSON keeps explicit nulls.

## Activation marker

Existing phases are unchanged: `started → stopped → snapshotted → retagged → started_new → verified`.

| Transition | Marker result |
|---|---|
| Gate pass | Advances to `retagged` after the receipt is durable |
| Gate failure | `phase=snapshotted`, `failed_phase=retagged`, `outcome=failed`, `error=<gate code>` |
| Outage deadline during gate | `error=ACTIVATE_OUTAGE_DEADLINE` |

Invariants:

- The new image is never selected unless the receipt is durable.
- `--recover-pre-snapshot` admits failed markers before the snapshot and unfinished `started` or `stopped` markers, and never admits `snapshotted` or later.
- A rollback requires the restored hash to equal the snapshot's and the snapshot `pre_version` to equal the rollback version exactly.
- The previous successful marker for `v2.7.1-670-420c7bcb75` stays on disk; the marker for the new release must be absent before STAGE.

## Gate error codes

`GATE_BASELINE_UNREADABLE`, `GATE_MIGRATIONS_MISMATCH`, `GATE_SCHEMA_MISMATCH`, `GATE_AGGREGATE_FAILED`, `GATE_RECEIPT_WRITE_FAILED`, `GATE_DEADLINE`. Codes name the failing check and carry no values.

## Post-cutover write count

`repeats` is counted. The subscription backfill is labelled as included in the private receipt and is not subtracted, so the acknowledged count stays conservative.
