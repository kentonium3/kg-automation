# Contracts: entrypoints and operator helpers

All four print a one-line summary on stdout line 1, then detail lines. Exit codes: 0 success, 1 failure or refusal, 2 usage. No output contains production rows, user names or task titles (C-007), nor any secret.

## `scripts/deploy/deploy-vikunja-release-stage.py` (felix-deployer, as `claude`)

| Mode | Effects | Exit 0 when |
|---|---|---|
| `--dry-run` | none (read-only Docker inspection, file stat and hash) | the archive is present with the expected size and sha, Docker is reachable, the rollback image is present, and `active` is absent or points at 2.4.0 or the release; prints what `--apply` would do |
| `--apply` | `docker load`; `docker tag` for the release tag; `docker tag` for `active` → 2.4.0 only if absent | all identities verified (R-2), or already staged and verified (no-op) |

It refuses (exit 1, no load or tag) when: the archive is missing; its size or sha differs; the release tag exists but points elsewhere; `active` points at something other than 2.4.0 or the release; or the rollback image is absent.

## `scripts/deploy/deploy-vikunja-release-activate.py` (felix-deployer, as `claude`)

| Mode | Effects | Exit 0 when |
|---|---|---|
| `--dry-run` | none | the release tag is verified, the Compose file names `office2.local/vikunja:active`, `active` → 2.4.0 or the release, the data files are readable, there is room for the snapshot, and there is no marker or the marker says `success` |
| `--apply` | marker; `docker compose -f <file> down`; snapshot; `docker tag` release → `active`; `docker compose -f <file> up -d`; verify | `verified`, or the marker already says `success` |

On failure after the stop: `compose down`, logs kept, marker `failed`, exit 1. A marker present with a non-success outcome means exit 1, with no Docker or Compose call.

## `scripts/vikunja/stage-release-archive.sh` (operator, office4)

`stage-release-archive.sh [--dry-run]`: reads `services/vikunja/release.json` and the Office4 source paths, transfers both archives as in R-4, and prints the remote sha256 of each. With `--dry-run` it only checks the sources' sha, free space on office2, and that the destination does not exist.

## `scripts/vikunja/rollback-release.sh` (operator, through `office2-claude`)

`rollback-release.sh --snapshot <dir> [--dry-run]`: R-7. It pauses for Kent's restore confirmation (it types nothing on Kent's behalf). The guard refuses any DB whose sha differs from `<dir>/snapshot.json`, or that shows migration markers.

## Amendments (2026-10-30, post-plan review)

- ACTIVATE `--apply` order: preconditions by image identity, durable marker, `compose down`, **untag `active`**, snapshot, tag `active` to the release, `compose up -d`, verify (300 s outage deadline). Every failure exit after `compose down` leaves `active` untagged and the container removed, after the logs are captured privately (R-9, R-14).
- ACTIVATE replay: with marker `success`, exit 0 only if the running image ID is the release and `/api/v1/info` reports the release version; with marker `rolled_back`, exit 1 `ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST`; with a malformed marker, exit 1 `MARKER_UNREADABLE` (R-12).
- Every mode: stdout and stderr carry only allowlisted lines and stable error codes (R-16); every subprocess and HTTP call is time-bounded (R-15).
- Rollback guard order: no container, lock held, no `-wal`/`-shm`, sha equals the snapshot, read-only schema check on a private copy (R-11).
