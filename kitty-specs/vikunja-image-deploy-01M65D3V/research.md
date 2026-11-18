# Research: Vikunja image-archive staging and activation deploy route

Each item gives the decision, the rationale and the alternatives considered. Host facts were read through `office2-claude` on 2026-10-30 unless marked otherwise. Pipeline facts come from the deployer code at `origin/main` 93f40d4a.

## R-1 Deployer contract that shapes the entrypoints

- The tick pulls first (`gitsync.py`: fetch, then `merge --ff-only origin/main`), then runs each queued entrypoint as `[path, "--dry-run"]` and then `[path, "--apply"]`. It runs as `claude` from `/home/claude/kg-automation`, with no timeout (`lib/apply.py:114-143`).
- A failed manifest stays queued and re-runs on every tick, producing a new failure record and alert each time (`felix-deployer/_tick.py:717-780`).
- The manifest has no argument fields, so all inputs come from a reviewed file in the repo.
- Tier 2 triggers `snapshot.ensure_recent_backup()` (24 h), which may run the NOPASSWD `backup.sh` (`lib/snapshot.py`).

**Decision**: entrypoints take only `--dry-run` and `--apply` and read `services/vikunja/release.json`. STAGE is idempotent. ACTIVATE is one-shot behind a marker (R-5).
**Alternatives**: environment variables (none are passed through); argument fields (not in the schema).

## R-2 Image identity after `docker load`

The archive is an OCI layout (`index.json`, `blobs/`) with `RepoTags: null`. Its identities:
- config digest `sha256:35e1bc87…afba5`;
- index digest `sha256:2be2b8c2…ffb6`;
- the config shows `amd64/linux`, `User 1000`, `org.opencontainers.image.revision=420c7bcb75…`, and `VIKUNJA_DATABASE_PATH=/db/vikunja.db` as the image default.

office2 runs Docker 29.6.2 on overlay2 (the classic image store), where the image ID is the config digest.

**Decision**:
- STAGE reads the image ID from `docker load` output and requires it to equal the config digest. The index digest is accepted only if `docker image inspect` reports the config digest through its config fields; any other ID fails.
- It then checks Architecture, Os, Config.User and the revision label against `release.json`.
- The version string is pinned in `release.json` from the build's own `version` output, checked again live at activation via `/api/v1/info`. No throwaway container is started.

**Alternatives**: `docker run --rm --network none … version`. That starts a container, which the spec's "never starts a container" wording discourages, and the config digest already pins the binary.

## R-3 Local names and the indirection tag

**Decision**:
- The release tag is `office2.local/vikunja:v2.7.1-670-420c7bcb75`; the active tag is `office2.local/vikunja:active`.
- The `office2.local/` registry prefix guarantees that a missing local tag fails resolution (an unreachable registry host) instead of silently pulling from Docker Hub.
- STAGE creates `active` → `60fe1ee8…` only if `active` is absent. If `active` exists, STAGE verifies it points at 2.4.0 or at the release, and otherwise fails.
- Compose's config hash changes when the image string changes, so the first `compose up` after the ACTIVATE merge recreates the container even when `active` still points at 2.4.0. That is harmless: same image, same DB, no migration.

**Alternatives**: `vikunja/vikunja:active` (a typo or a missing tag could pull from Hub); `pull_policy: never` (changes a second Compose line, against FR-007).

## R-4 Ingress

**Decision**: an operator helper on office4, `scripts/vikunja/stage-release-archive.sh`:
1. Runs `ssh office2-claude 'umask 077; mkdir /data/services/vikunja/release-artifacts/<sha12>'` (create-only; `mkdir` fails if the folder exists; the parent `/data/services/vikunja` is `claude:claude` 775).
2. Streams each archive with `ssh office2-claude 'set -o noclobber; cat > <dest>'`.
3. Re-hashes on office2 and compares with `release.json`. On any mismatch it deletes the partial file and fails.

The sources are the PM's Office4 custody copies:
- `/home/kgale/.local/share/rrule-office2-images/420c7bcb75…/image.tar`
- `/home/kgale/.local/share/rrule-office2-images/rollback-v2.4.0-60fe1ee8/vikunja-2.4.0.image.tar`

The PM's `/home/codex/...` copy stays custody evidence and is never read. The transfer runs only after this plan passes its post-plan review (lead 734fe894).
**Alternatives**: a manifest (it cannot reach office4); committing the archive (170 MB binary in git).
**Note**: the ingress writes data, not configuration, into a claude-owned area. It is not a deploy under the discipline, and the rollback image is already present, so its archive is a second line of defence.

## R-5 One-shot activation marker

**Decision**: `/data/services/vikunja/activation/<release-version>.json`.
- It is created with `O_CREAT|O_EXCL` before the first stop and records `{phase, started_at, snapshot_dir, snapshot_sha, outcome}`, updated at each phase.
- On a later run: `outcome=success` reports and exits 0, so the manifest becomes applied on a retried tick after a push failure. Any other outcome exits 1 with the marker contents, without touching Docker.
- The dry run reports the marker's state.
- Kent clears it only as part of a decided retry, which is listed in the packet.

**Alternatives**: no marker (every tick would stop the service again); a git-tracked marker (the entrypoint cannot commit).

## R-6 Write-boundary snapshot and the host-copies guard

Host facts:
- `/data/services/vikunja/data` is `kgale:root` 775; `vikunja.db`, `-wal` and `-shm` are `kgale:root` 644; `claude` (1001) can read them but not write.
- The live WAL is 4 MB, so committed data may sit outside the main file.

**Decision**:
1. After `compose down`, check that no container is running and that the file mtimes are stable.
2. Copy `vikunja.db` plus any `-wal`/`-shm` into `snapshots/<UTC>/raw/`.
3. Open the copy with `sqlite3` in that writable folder, run `PRAGMA wal_checkpoint(TRUNCATE)` and `VACUUM INTO snapshots/<UTC>/vikunja.db`, then `PRAGMA integrity_check` on the result. Record the sha and the task count (an aggregate only).

The repo's `tests/deploy/test_host_copies_report.py` fails entrypoints that copy files unless they report through `installed_report`. **Decision**: report each snapshot file through `installed_report.record_installed`. Whether `installed_report` is the right reporting class for data snapshots is a question for the post-plan review.

**Alternatives**:
- Open the live DB read-only: `immutable=1` ignores the WAL and would lose committed data, and a normal open needs write access to create the `-shm`.
- Copy only the main file: same loss.

## R-7 Rollback route

**Decision**: an operator helper run through `office2-claude`, `scripts/vikunja/rollback-release.sh`:
1. `compose down` with the unit's arguments.
2. Copy the failed DB files and `docker logs` into `snapshots/<UTC>-failed/`.
3. Print Kent's exact restore command: `sudo install -o kgale -g root -m 644 <snapshot>/vikunja.db /data/services/vikunja/data/vikunja.db && sudo rm -f /data/services/vikunja/data/vikunja.db-wal /data/services/vikunja/data/vikunja.db-shm`, run through `office2-kgale` by Kent.
4. After Kent confirms, verify the DB in place (sha equals the snapshot, no `task_repeat_legacy_backup`, no `tasks.repeats`).
5. Retag `active` → `60fe1ee8…`, `compose up -d`, and verify `/api/v1/info` reports 2.4.0.

The run ends with a manual-rebaseline note, because the change is out-of-band (CLAUDE.md "Out-of-band exception").
**Alternatives**: a rollback manifest (needs a merge to `main` and a 5-minute tick, and still needs Kent's sudo in the middle).

## R-8 Post-start verification

**Decision**:
- Poll `http://100.92.197.90:3456/api/v1/info` (the bound address; `localhost` is not bound) every 5 s for up to 180 s.
- Pass requires HTTP 200 and `version == "v2.7.1-670-420c7bcb75"`.
- The container's `.Image` must equal the release image ID.
- `docker logs vikunja` must contain "Ran all migrations successfully". The RRULE migration summary line is recorded; it holds aggregate counts only.
- A token login check uses an existing v1 consumer's token through that consumer's own check, as a manifest `verification.post` command.
- Kent's interactive UI login is an acceptance step in the go packet, not an entrypoint check, because the agent holds no user password.

**Alternatives**: HEAD requests (unsuitable, per the handoff); a Docker HEALTHCHECK (the image has none).

## Post-plan review fold-in (2026-10-30)

Reviewer: Codex `gpt-6.1-sol` (OpenAI), read-only, 2026-10-30. The implementer is Claude Opus 5.5, a different vendor. Verdict: NOT READY, with 2 BLOCKER, 8 HIGH and 4 MEDIUM findings. Every finding is accepted. The dispositions below amend R-1 to R-8 where they conflict, and take precedence over them.

### R-9 The `active` tag is the startup lock (findings 1, 7)

`vikunja.service` runs `compose up -d` at boot no matter what the marker says, so the marker alone cannot keep the service down.

**Decision**: whenever the service must stay down (between `compose down` and the verified start in ACTIVATE, after any ACTIVATE failure, and throughout rollback until the guard passes), the code removes the `office2.local/vikunja:active` tag with `docker image rm` on the tag only. The image itself stays. The Compose service gains `pull_policy: never`, so a startup with the tag missing fails at once with "no such image". It does not try a registry.

This closes every reboot window the review listed:
- mid-snapshot: nothing starts while files are copied;
- after a failed activation: the rejected release cannot restart;
- mid-rollback after Kent's restore: nothing can migrate the restored DB.

**Spec amendment**: FR-007 now allows exactly two lines to change, `image:` and a new `pull_policy: never`. FR-017 is added for the lock. Both are recorded in spec.md.
**Alternatives**: a systemd drop-in or `systemctl disable` (needs sudo and changes the unit, against C-004); a guard script in the unit (changes the unit).

### R-10 Activation preconditions are checked by image identity (finding 2)

**Decision**: before the first activation, the running container's `.Image` must equal the rollback image ID `60fe1ee8…`, whether its configured reference is `vikunja/vikunja:2.4.0` or `office2.local/vikunja:active`. `active` must resolve to `60fe1ee8…`. A container already running the release ID is refused, unless the marker says `success` (R-12).

### R-11 Rollback guard fails closed on sidecars (finding 3)

**Decision**: the guard requires, in this order:
1. no `vikunja` container exists;
2. `active` is untagged (the lock is held);
3. `vikunja.db-wal` and `vikunja.db-shm` are both absent in the data folder.

Only then does it hash the file and compare it with `snapshot.json`. The old schema is checked on a private copy opened `mode=ro`; with the sidecars proven absent, that is side-effect free. Any inspection error refuses. The tests cover a residual migrated WAL and a non-writable data folder.

### R-12 Marker durability and a reconciled success replay (findings 4, 5)

**Decision**:
- The marker is created with `O_CREAT|O_EXCL`, written and `fsync`ed, and its parent folder is `fsync`ed before `compose down`.
- Every phase update is a write to a temp file, then `fsync`, `os.replace` and a parent `fsync`.
- A malformed or unreadable marker is a refusal that names a recovery (exit 1, no Docker call).
- A `success` replay re-checks, read-only, that the running container's image is the release ID and that `/api/v1/info` reports the release version. Anything else is exit 1.
- The rollback helper writes `outcome: rolled_back`. ACTIVATE then exits 1 with the code `ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST`.
- The manifest's `verification.post` runs the ACTIVATE entrypoint's read-only status check, so the outer verification is release-exact.

### R-13 Docker identity contract (finding 6)

Captured on office2 (2026-10-30): `docker info` gives `Driver=overlay2` with no containerd snapshotter, so this is the classic image store, where the image ID is the config digest. `vikunja/vikunja:2.4.0` has `Id=sha256:60fe1ee8…7d2`, Arch `amd64`, Os `linux`, User `1000`. The container has `.Image=sha256:60fe1ee8…` and `.Config.Image=vikunja/vikunja:2.4.0`.

**Decision**:
- The preflight requires `Driver == overlay2` and no `driver-type io.containerd.snapshotter` entry in `DriverStatus`; anything else refuses (`DOCKER_STORE_UNSUPPORTED`).
- The accepted daemon identity of the release is `docker image inspect .Id == release.json image.config_digest`. It is used for the release tag, `active`, and every running-container check.
- The archive's chain is checked offline before load: `index.json` → index digest `2be2b8c2…`, then `manifest.json` Config → `blobs/sha256/35e1bc87…`. The config's sha256 must equal its name, and the config's Architecture, Os, User and revision label must match `release.json`.
- The test fixtures are these captured shapes plus the real archive's `manifest.json`, `index.json` and config JSON. These carry no production data.

### R-14 Evidence before teardown (finding 8)

**Decision**: on any failure after a container starts, the code first writes `docker logs --timestamps vikunja` (bounded at 10 MB and 30 s) to the private failure folder (0700), then runs `compose down`. A failed log capture is recorded but never blocks the shutdown. Rollback does the same.

### R-15 Deadlines (finding 9)

**Decision**:
- Every subprocess call has a `timeout`: Compose up and down 120 s; `docker load` 300 s (before the stop, so it does not count as outage); tag, rm and inspect 30 s; logs 30 s.
- Each HTTP request has a 5 s timeout, and the readiness loop is bounded at 180 s.
- SQLite work runs with a busy timeout, under a 120 s overall budget.
- The activation outage window runs from `down` to a verified start, with a monotonic deadline of 300 s (NFR-001). Missing it is a failure, handled as in R-14 with the lock taken.
- Cleanup has its own 120 s budget.
- The tests inject hangs as `TimeoutExpired` from the fake runner and an opener that times out.

### R-16 Output allowlist (finding 10)

**Decision**:
- Public stdout and stderr, marker fields and `snapshot.json` contain only fixed summary lines, stable error codes (`ARCHIVE_SHA_MISMATCH`, `ACTIVE_TAG_UNEXPECTED`, and so on), image IDs, hashes, timestamps, counts and file paths.
- Raw command output (Docker errors, container logs) goes only to the private 0700 folders and is never echoed.
- The token consumer check is dropped from the entrypoints. The outer `verification.post` uses the release-exact status check (R-12), and Kent's UI login is a go-packet acceptance step.
- The tests seed fake secrets, names and titles into fake Docker output and logs, and assert none of them appear in stdout, stderr or the marker.

### R-17 Queue disposition (finding 11)

**Decision**: the go packet defines both paths explicitly.
- **Cancel**, after a rollback or a decision not to proceed: Kent merges a reviewed commit that deletes `deploys/queued/vikunja-release-activate.yaml` and sets Compose back to the indirection with `active` pinned to 2.4.0. The marker is left as `rolled_back`, as history.
- **Authorized retry**: Kent first archives the marker to `activation/<version>.<UTC>.retired.json`, through the agent with his explicit retry go.

The tier-2 backup gate running before the marker check is accepted and documented: it can only refresh a backup.

### R-18 Partial STAGE failure (finding 12)

**Decision**: STAGE creates no tag until verification passes: it loads, verifies, then tags. When verification fails after a load, the loaded image stays untagged. STAGE reports `STAGE_VERIFY_FAILED` with the loaded ID, and the go packet's recovery is: the agent runs `docker image rm <id>` through `office2-claude`, then a manual rebaseline of `docker-images.txt`, since it is out-of-band. Tests cover the composition through `apply.dry_run_then_apply_gate` with a fake runner.

### R-19 Candidate validation is separate from host readiness (finding 13)

**Decision**:
- **Candidate validation, before merge**: copy the branch's `scripts/deploy/vikunja_release.py`, both entrypoints and `release.json` to `/data/services/vikunja/candidate-<sha12>/` (claude-owned, 0700; never the live checkout) and run both `--dry-run`s there. The STAGE dry run must pass in full once ingress is done. The ACTIVATE dry run must report every precondition, and the only expected unmet ones are "release tag absent" (before STAGE) and "Compose not on `active`" (before the ACTIVATE merge).
- **Host readiness**: after STAGE applies, the candidate ACTIVATE dry run must show "Compose not on `active`" as its only unmet precondition. The go packet records that output.
- The release-exact readiness is the ACTIVATE manifest's own dry run, run by the deployer.

### R-20 Deploy-runbook corrections (finding 14)

**Decision**: FR-016 now includes correcting `docs/runbooks/deploy/discipline.md`:
- `:470-475`: failure records do not block retries; the manifest re-runs every tick;
- `:612-614`: the applier does rebaseline (deferred-confirm).

The ACTIVATE cancel and retry paths (R-17) are added there.

## Confirmation pass fold-in (2026-10-30)

Reviewer: Codex `gpt-6.1-sol`, read-only, 2026-10-30. Of the 14 findings, 11 are RESOLVED and 3 PARTIAL (1, 7, 11). It raised 1 new BLOCKER and 2 new HIGH, with the verdict NOT READY. All are accepted. R-21 to R-24 take precedence over R-9 to R-20 where they conflict.

### R-21 Restate the lock as hazard invariants (new BLOCKER; PARTIAL 1, 7)

With the unit unchanged (C-004), the plan cannot guarantee that nothing ever starts after a host crash. R-9's claim that the lock closes "every reboot window" is withdrawn. The design instead guarantees two data-safety invariants and records the residual risk.

- **INV-1: the rollback image never runs on a possibly-migrated database.**
  - From the moment ACTIVATE tags `active` to the release, `active` never points at `60fe1ee8…` again until the rollback guard (R-11) has verified that the unmigrated snapshot is back in place.
  - No code path tags `active` to 2.4.0 while an activation marker exists, except the rollback helper after its guard.
- **INV-2: nothing writes the database while the snapshot is copied.**
  - The order is `compose down`, untag `active`, verify that no container exists, then copy.
  - A crash between `down` and untag restarts 2.4.0 on the **unmigrated** DB at boot. That is safe: the marker shows `stopped`, and a retry follows the R-24 procedure.
- **Accepted residual risk, stated in the go packet:** a crash after `active` is tagged to the release (during `up`, verification or failure cleanup) lets the unverified release restart at boot on its own migrated DB. That is the target image on the target schema, with the snapshot already taken, so no data is lost. The marker's last phase tells the operator to finish verification or roll back. Failure cleanup releases the lock in the order `docker logs`, `down`, untag, so a crash mid-cleanup leaves at worst the release restartable.

### R-22 Engine fail-closed behaviour must be evidenced (new HIGH)

Fakes cannot prove what Compose v5.3.1 does with a missing image and `pull_policy: never`.

**Decision**:
- A work package runs an **isolated sandbox** on office2 (the CLAUDE.md sandbox carve-out). The record is posted to #1087 before it runs.
- Sandbox definition:
  - project `vikunja-lock-sandbox`;
  - its own network; no ports; no mounts of production paths;
  - `image: office2.local/sandbox:absent` with `pull_policy: never` and `restart: unless-stopped`;
  - a 64 MB memory ceiling;
  - torn down with `docker compose -p vikunja-lock-sandbox down --remove-orphans` and `docker network prune --filter label=com.docker.compose.project=vikunja-lock-sandbox -f`.
- It records:
  - the exit code and output of `up -d`;
  - which resources exist after a failed `up` (`docker ps -a`, `docker network ls`, filtered by project label);
  - that no pull is attempted (`docker events` filtered on `type=image`, `action=pull`, during the run);
  - that after a `down` of a running container, untagging its image succeeds with the image ID kept.
- The result is committed as test evidence. If Compose does not fail closed, the lock design is invalid and the mission stops for a decision.
- A sandbox `docker network ls` entry or created container during a failed `up` is acceptable only if `up` exits non-zero and no container reaches `running`.

### R-23 STAGE must not release a hold (new HIGH)

**Decision**: STAGE creates `active` → `60fe1ee8…` only when **no activation marker of any outcome exists** for this release, so that `active` is absent only because it was never created. With a marker present and `active` absent, STAGE exits 1 with `STAGE_ACTIVE_HELD_BY_ACTIVATION`. STAGE never retags `active`.

### R-24 Retry requires a completed rollback (PARTIAL 11)

**Decision**: an authorized retry after a failed activation is defined as follows.
1. A full rollback (R-7/R-11), ending with 2.4.0 running on the restored DB and the marker `rolled_back`.
2. Kent's explicit retry go.
3. The agent archives the marker to `activation/<version>.<UTC>.retired.json`.
4. The ACTIVATE preconditions (R-10) then hold again, and the still-queued manifest re-runs on the next tick.

Retiring the marker without the rollback is refused by procedure, and the ACTIVATE preconditions reject it mechanically: the running image must be `60fe1ee8…` and `active` must resolve to it.
