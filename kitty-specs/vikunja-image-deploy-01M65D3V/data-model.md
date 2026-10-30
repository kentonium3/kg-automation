# Data Model: Vikunja image-archive staging and activation deploy route

## ReleaseRecord (`services/vikunja/release.json`, git-tracked, reviewed)

| Field | Example | Rule |
|---|---|---|
| `schema_version` | `1` | exact |
| `release_version` | `v2.7.1-670-420c7bcb75` | must equal `/api/v1/info` `version` after activation |
| `source_revision` | `420c7bcb75231be9b6571fdfdf76a1a62f2aebd8` | must equal the image label `org.opencontainers.image.revision` |
| `archive.path` | `/data/services/vikunja/release-artifacts/48008c5067a6/image.tar` | absolute; under the ingress root |
| `archive.sha256` / `archive.size` | `48008c50…1f79` / `54450688` | verified before `docker load` |
| `image.config_digest` | `sha256:35e1bc87…afba5` | the image ID after load (R-2) |
| `image.index_digest` | `sha256:2be2b8c2…ffb6` | accepted only as a load alias that resolves to `config_digest` |
| `image.platform` / `image.user` | `linux/amd64` / `1000` | exact |
| `tags.release` / `tags.active` | `office2.local/vikunja:v2.7.1-670-420c7bcb75` / `office2.local/vikunja:active` | fixed |
| `rollback.image_id` / `rollback.ref` | `sha256:60fe1ee8…7d2` / `vikunja/vikunja:2.4.0` | must be present; never removed |
| `rollback.archive.path` / `.sha256` / `.size` | `…/release-artifacts/48008c5067a6/vikunja-2.4.0.image.tar` / `b63e5529…a9ad` / `115518464` | second line of defence |
| `service.compose_file` / `service.project` / `service.container` | `/home/claude/kg-automation/services/vikunja/docker-compose.yml` / `vikunja` / `vikunja` | the unit's exact arguments |
| `service.info_url` | `http://100.92.197.90:3456/api/v1/info` | bound address |
| `service.data_dir` | `/data/services/vikunja/data` | read-only to `claude` |

## ActivationMarker (`/data/services/vikunja/activation/<release_version>.json`, office2)

States: `started` → `stopped` → `snapshotted` → `retagged` → `started_new` → `verified` (outcome `success`), or any state → outcome `failed` with `failed_phase` and `error`.

- It is created once with an exclusive create before `compose down`.
- It is never deleted by code.
- Its presence blocks any further stop or start.

## Snapshot (`/data/services/vikunja/snapshots/<UTC>/`, office2, 0700)

- `raw/`: a verbatim copy of `vikunja.db` plus any `-wal`/`-shm`, with their sha256 values.
- `vikunja.db`: the single-file consolidated copy, with its sha256, `integrity_check = ok`, and a tasks count (aggregate).
- `snapshot.json`: the above, plus the release version and the image ID the DB was running under.

Invariant: a snapshot taken by ACTIVATE is the unmigrated pre-upgrade DB. It has no `task_repeat_legacy_backup` table and no `tasks.repeats` column. The rollback guard re-checks this on the restored file.

## Image-tag state (office2 Docker)

| State | `active` → | release tag | Who moves it |
|---|---|---|---|
| Before STAGE | absent | absent | — |
| After STAGE | `60fe1ee8` (2.4.0) | `35e1bc87` | STAGE (creates `active` only if absent) |
| After ACTIVATE success | `35e1bc87` | `35e1bc87` | ACTIVATE, after the snapshot passes |
| After rollback | `60fe1ee8` | `35e1bc87` (kept) | rollback helper, after Kent's restore and the guard |
