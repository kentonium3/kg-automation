---
title: Vikunja Release Cutover (the go packet)
doc_type: runbook
audience: agents_and_humans
status: approved
tags: [1087]
created: 2026-10-30
last_updated: '2026-10-30'
---

# Vikunja Release Cutover (the go packet)

This runbook moves office2's Vikunja from `vikunja/vikunja:2.4.0` to the private
RRULE release image through the manifest pipeline, and back if needed. It is the
durable form of the go packet for kentonium3/kg-automation#1087 (mission
`vikunja-image-deploy-01M65D3V`).

| | Value |
|---|---|
| From | `vikunja/vikunja:2.4.0`, image ID `sha256:60fe1ee8f729c17b057ba00a49b968adb4ed1e774cea36b5f4cc81340991a7d2` |
| To | release `v2.7.1-670-420c7bcb75`, built from `420c7bcb75231be9b6571fdfdf76a1a62f2aebd8` |
| Release image ID (config digest) | `sha256:35e1bc8790292deedf2addc3f3f196e38d84c2614219a95d6ef711c1f02afba5` |
| Release archive sha256 | `48008c5067a6555cb880200d5416a7989df6be06246cc41bc69d1da685581f79` |
| Rollback archive sha256 | `b63e5529ba35e695aec3b240f835a5ea412a2b0552f2a1b054e5d0d9a9aaa9ad` |
| Release record (trust root) | `services/vikunja/release.json` |
| Activation marker | `/data/services/vikunja/activation/v2.7.1-670-420c7bcb75.json` |

**Who does what.** Every step is marked **Agent** or **Kent**.

- **Every Agent step that runs a command on office2, and the ingress, is
  executed by the Claude Code session, through its own account
  `ssh office2-claude`.** This is CLAUDE.md's own-account rule.
- Codex sessions only review, locally. They never execute a remote step or
  the ingress. This go packet does not authorize any other agent, or any
  other account, to run these steps.
- Kent's privileged steps run through `ssh office2-kgale`, and only Kent uses
  it. Agents never use `office2-kgale`, and never `office2-codex`.
- Nothing from the mission merges to `main` before Kent merges it. There are two
  merges, both Kent's:
  - the STAGE merge, which is inert;
  - the ACTIVATE merge, which **is the cutover** and needs Kent's explicit go.

**No production data in this file.** Expected counts, task ids, snapshot paths
and times belong in the private final packet, never in a committed file.

## How the route works

- **STAGE** (`scripts/deploy/deploy-vikunja-release-stage.py`, manifest
  `deploys/queued/vikunja-release-stage.yaml`) loads and verifies the release
  archive, then tags it:
  - the release tag `office2.local/vikunja:v2.7.1-670-420c7bcb75` is created
    only after verification;
  - the indirection tag `office2.local/vikunja:active` is created pointing at
    2.4.0, and only when it is absent and no activation marker exists.

  STAGE never touches a container or the Compose file, and a re-run is a no-op.
  It holds `activation.lock` for its whole apply, the same lock ACTIVATE and
  the rollback helper hold, so none of them can interleave.
- **ACTIVATE** (`scripts/deploy/deploy-vikunja-release-activate.py`, manifest
  `deploys/queued/vikunja-release-activate.yaml`) is the one-shot cutover. It
  merges with the Compose change, which sets `image: office2.local/vikunja:active`
  and adds `pull_policy: never`. Its `--apply` runs these steps in order:
  1. hold `activation.lock`;
  2. check the preconditions;
  3. write the durable marker;
  4. `compose down`;
  5. untag `active`, which is the startup lock;
  6. take the write-boundary snapshot;
  7. tag `active` to the release;
  8. `compose up -d`;
  9. verify the image ID, `/api/v1/info` and the migration log.

  Steps 4 to 9 must finish inside a 300 s outage deadline.
- **Rollback** (`scripts/vikunja/rollback_release.py`) is an operator helper run
  through `ssh office2-claude`. It works in two phases, with Kent's restore
  between them.
- **Ingress** (`scripts/vikunja/stage_release_archive.py`) is an operator helper
  run on office4. It copies the two archives into a create-only 0700 folder on
  office2.

`scripts/vikunja/deploy.sh` is legacy and is not part of this route: it always
pulls from a registry and cannot select an archive.

### Contract amendments (recorded 2026-10-30)

These amend `kitty-specs/vikunja-image-deploy-01M65D3V/contracts/entrypoints.md`
and the plan's project structure (analysis finding I1):

- **Both operator helpers are Python, not shell.** The ingress helper is
  `scripts/vikunja/stage_release_archive.py`, not `stage-release-archive.sh`.
  The rollback helper is `scripts/vikunja/rollback_release.py`, not
  `rollback-release.sh`.
- **The rollback helper's modes** are `--dry-run [--snapshot <dir>]`,
  `--snapshot <dir> --prepare`,
  `--snapshot <dir> --finish --ack-post-cutover-writes <n>`, and
  `--recover-pre-snapshot`, which takes no other argument. The
  contract's single run that pauses for Kent's confirmation is replaced by two
  phases: Kent's restore runs between `--prepare` and `--finish`.
- **The Compose argv has no `-p`.** Both ACTIVATE and rollback run
  `docker compose -f /home/claude/kg-automation/services/vikunja/docker-compose.yml down`
  and `... up -d`. These are exactly the arguments `vikunja.service` uses (a
  system oneshot, `User=claude`). The WP04 prompt text said `-p vikunja`, which
  was wrong. Compose derives the project name `vikunja` from the Compose file's
  folder.

## 1. Preconditions

Tick every box before the STAGE merge. Record the evidence in the private packet.

- [ ] Release acceptance (Ring 4 and Ring 5) and the release CI are attached:
  fork CI run 41004713815 on snapshot `09a2bb834`, with 38 success and 1 skipped.
- [ ] `feat/vikunja-image-deploy` has passed its mission review and its
  post-merge review. Every lane is merged into it, and its HEAD is the
  **candidate SHA**.
- [ ] The host facts still hold. Check them read-only through `ssh office2-claude`:
  - `/data/services/vikunja` is `claude:claude` 775;
  - the data folder is `kgale:root` 775, and its files are 644;
  - Docker is 29.6.x on the classic overlay2 store, and Compose is 5.3.x;
  - `/usr/bin/curl` and `/usr/bin/jq` are present;
  - `/api/v1/info` reports `v2.4.0`.
- [ ] None of `/data/services/vikunja/release-artifacts`, `snapshots`,
  `activation` or `failures` exists yet. If any does, stop and find out why.
- [ ] The candidate validation (section 2) and the ingress (section 3) are done,
  and their output is attached.
- [ ] The PM's packet names the inputs that the acceptance checklist binds
  (section 7), and the list of automations to pause while writes are closed.

## 2. Candidate validation, before any merge (Agent)

This step runs both entrypoints' `--dry-run` from a private copy of the candidate
files on office2. It never uses the live checkout `/home/claude/kg-automation`
(research R-19). Each entrypoint finds its imports and `release.json` through
`Path(__file__).resolve().parents[2]`. The copy therefore keeps the repository
layout, with `scripts/` and `services/` directly under the candidate folder.

**Agent**: pin the candidate first. Every office4 step in sections 2, 3, 4a and
6b runs in the existing mission clone on office4,
`/home/kgale/repos/kg-automation-vikunja-deploy`, which holds the unpushed
`feat/vikunja-image-deploy`. Never use a fresh clone: it cannot resolve that
branch. `CAND` is the full candidate SHA recorded in the private packet (the
reviewed HEAD of `feat/vikunja-image-deploy`):

```bash
REPO=/home/kgale/repos/kg-automation-vikunja-deploy
CAND=<full candidate SHA from the packet>
git -C "$REPO" cat-file -e "$CAND^{commit}" && echo CAND_PRESENT
test "$(git -C "$REPO" rev-parse feat/vikunja-image-deploy)" = "$CAND" && echo CAND_IS_BRANCH_HEAD
S12=${CAND:0:12}
```

Both lines must print. If the branch has moved past `CAND`, stop: the candidate
must be re-reviewed, or the packet re-pinned.

**Agent**: copy the candidate files to office2:

```bash
git -C "$REPO" archive --format=tar "$CAND" \
    scripts/deploy/deploy-vikunja-release-stage.py \
    scripts/deploy/deploy-vikunja-release-activate.py \
    scripts/deploy/vikunja_release \
    scripts/deploy/lib \
    services/vikunja/release.json \
  | ssh office2-claude "umask 077 && mkdir /data/services/vikunja/candidate-$S12 && tar -x -C /data/services/vikunja/candidate-$S12"
```

The `mkdir` is create-only, so an existing candidate folder fails the command.
`scripts/deploy/lib` is included because `vikunja_release/dbsafety.py` imports
`scripts.deploy.lib.installed_report`.

**Agent**: run both dry runs from the candidate root:

```bash
ssh office2-claude "cd /data/services/vikunja/candidate-$S12 && PYTHONDONTWRITEBYTECODE=1 ./scripts/deploy/deploy-vikunja-release-activate.py --dry-run; echo exit=\$?"
ssh office2-claude "cd /data/services/vikunja/candidate-$S12 && PYTHONDONTWRITEBYTECODE=1 ./scripts/deploy/deploy-vikunja-release-stage.py --dry-run; echo exit=\$?"
```

Both dry runs are read-only: they make Docker inspect calls, read files and
probe the lock, and write nothing. The ACTIVATE dry run reads the **live**
Compose file named in `release.json`, which is still on 2.4.0.

**Expected ACTIVATE dry run before STAGE** (exit 1):

- line 1: `FAILED code=ACTIVATE_PRECONDITIONS_UNMET`;
- then `ACTIVATION_LOCK_FREE` and one `ACTIVATE_CHECK` line per precondition.

The unmet set must be exactly these three `ACTIVATE_CHECK` lines, because
STAGE has not created either tag yet:

- `check_code=PRE_RELEASE_TAG status_code=UNMET code=PRE_RELEASE_TAG_NOT_STAGED`
- `check_code=PRE_ACTIVE_TAG status_code=UNMET code=PRE_ACTIVE_ABSENT`
- `check_code=PRE_COMPOSE status_code=UNMET code=PRE_COMPOSE_NOT_ACTIVE`

`PRE_STORE`, `PRE_CONTAINER`, `PRE_DATA_READABLE`, `PRE_SPACE` and
`PRE_VERSION` must be `MET`, followed by
`ACTIVATE_MARKER ... status_code=ABSENT`. Any other unmet check is a stop.

**Expected STAGE dry run:**

- Before the ingress: exit 1, `FAILED code=ARCHIVE_MISSING`. This is expected.
  Re-run the STAGE dry run after section 3.
- After the ingress: exit 0, `STAGE_DRY_RUN_OK` followed by:
  - `STAGE_ARCHIVE_VERIFIED`, with the size `54450688` and the release archive sha;
  - `STAGE_STATE`, with `release_tag_id=-`, `active_id=-` and
    `rollback_id=sha256:60fe1ee8…`;
  - `STAGE_ACTIVATION_LOCK_FREE lock=/data/services/vikunja/activation/activation.lock`;
  - then `STAGE_PLAN_LOAD`, `STAGE_PLAN_TAG_RELEASE` and `STAGE_PLAN_CREATE_ACTIVE`.

  The STAGE dry run must pass in full before the STAGE merge, because the
  manifest's `verification.pre` runs this same dry run.

## 3. Ingress (Agent)

**Agent**, on office4, in `$REPO`. The helper runs from the working tree, so
first prove that the files it uses are byte-identical to `CAND`:

```bash
cd "$REPO"
test "$(git rev-parse HEAD)" = "$CAND" && echo HEAD_IS_CAND
git diff --quiet "$CAND" -- scripts/vikunja/stage_release_archive.py scripts/deploy/vikunja_release \
    services/vikunja/release.json && echo FILES_MATCH_CAND
```

Both lines must print. The helper reads both
office4 sources from `release.json` `roots.office4_sources`. These are the PM's
custody copies under `/home/kgale/.local/share/rrule-office2-images/`. The helper
refuses any source under `/home/codex`, which is custody evidence only and is
never read.

Dry run first. It makes no remote change:

```bash
python3 scripts/vikunja/stage_release_archive.py --dry-run; echo exit=$?
```

Expected output (exit 0):

- `INGRESS_DRY_RUN_OK dest=/data/services/vikunja/release-artifacts/48008c5067a6 files=2 total_bytes=169969152 avail_bytes=<n> parent_code=CREATE`
- two `INGRESS_SOURCE_VERIFIED` lines, with the release sha `48008c50…1f79` and
  the rollback sha `b63e5529…a9ad`;
- two `INGRESS_PLAN` lines, for `…/48008c5067a6/image.tar` and
  `…/48008c5067a6/vikunja-2.4.0.image.tar`.

Then the apply:

```bash
python3 scripts/vikunja/stage_release_archive.py --apply; echo exit=$?
```

Expected output (exit 0):

- `INGRESS_APPLIED dest=/data/services/vikunja/release-artifacts/48008c5067a6 files=2 total_bytes=169969152`
- `INGRESS_REMOTE_SHA remote=…/image.tar sha256=48008c5067a6555cb880200d5416a7989df6be06246cc41bc69d1da685581f79`
- `INGRESS_REMOTE_SHA remote=…/vikunja-2.4.0.image.tar sha256=b63e5529ba35e695aec3b240f835a5ea412a2b0552f2a1b054e5d0d9a9aaa9ad`

Record both remote shas. Then re-run the candidate STAGE dry run from section 2,
which must now pass.

**If the apply fails after creating the destination.** The helper creates
`/data/services/vikunja/release-artifacts/48008c5067a6/` before it transfers
anything, and it never removes that folder. A re-run then refuses with
`INGRESS_DEST_EXISTS`. Recover only **before the STAGE merge**: once STAGE has
loaded the archive, leave the folder alone.

1. **Agent**: inspect the folder and hash whatever arrived:

   ```bash
   ssh office2-claude 'ls -la /data/services/vikunja/release-artifacts/48008c5067a6/ && sha256sum /data/services/vikunja/release-artifacts/48008c5067a6/*.tar'
   ```

   If both final files are present and their shas are exactly
   `48008c5067a6555cb880200d5416a7989df6be06246cc41bc69d1da685581f79`
   (`image.tar`) and
   `b63e5529ba35e695aec3b240f835a5ea412a2b0552f2a1b054e5d0d9a9aaa9ad`
   (`vikunja-2.4.0.image.tar`), the ingress is complete. Do not redo it.
2. Otherwise the folder is empty or partial: a missing final, or a
   `.<name>.<nonce>.part` file. **Agent**: confirm that the path is exactly the
   per-sha folder named above, then remove that folder only:

   ```bash
   ssh office2-claude 'rm -rf -- /data/services/vikunja/release-artifacts/48008c5067a6'
   ```

   Never remove `/data/services/vikunja/release-artifacts` itself, and never use
   a glob or a variable in this command.
3. Re-run the dry run, which must again show the plan, then the apply.

## 4. STAGE merge

### 4a. Assemble the STAGE branch (Agent)

The STAGE merge is everything on `feat/vikunja-image-deploy` **except** the five
ACTIVATE paths. They are listed in `CUTOVER_PATHS` in
`tests/deploy/test_vikunja_cutover_change_set.py`:

- `services/vikunja/docker-compose.yml`
- `deploys/queued/vikunja-release-activate.yaml`
- `docs/design/architecture/data/service-inventory.json`
- `docs/design/architecture/service-inventory.md`
- `tests/deploy/test_vikunja_cutover_change_set.py`

**Agent**, in a new worktree of the mission clone `$REPO` on office4, built from
`origin/main`. This is never the live deployer clone on office2, and the
mission's own checkout is not switched. `CAND` is the pinned candidate SHA from
section 2; re-check it first:

```bash
REPO=/home/kgale/repos/kg-automation-vikunja-deploy
CAND=<full candidate SHA from the packet>
test "$(git -C "$REPO" rev-parse feat/vikunja-image-deploy)" = "$CAND" && echo CAND_IS_BRANCH_HEAD
git -C "$REPO" fetch origin main
git -C "$REPO" worktree add /home/kgale/repos/kg-automation-vikunja-stage -b feat/vikunja-release-stage origin/main
cd /home/kgale/repos/kg-automation-vikunja-stage
BASE=$(git merge-base origin/main "$CAND")
CUTOVER=(
  services/vikunja/docker-compose.yml
  deploys/queued/vikunja-release-activate.yaml
  docs/design/architecture/data/service-inventory.json
  docs/design/architecture/service-inventory.md
  tests/deploy/test_vikunja_cutover_change_set.py
)
EXCLUDE=(); for p in "${CUTOVER[@]}"; do EXCLUDE+=(":(exclude)$p"); done
git diff --binary "$BASE" "$CAND" -- . "${EXCLUDE[@]}" | git apply --index
git commit -m "feat(vikunja): STAGE the RRULE release image (#1087)"
```

If `git apply` reports a conflict, stop. It means `main` has moved over a mission
path.

**Agent**: verify the branch before opening the PR.

```bash
# 1. No cutover path differs from main. Expect no output.
git diff --name-only origin/main HEAD -- "${CUTOVER[@]}"
# 2. The branch is exactly the mission minus the cutover paths. Expect no output.
diff <(git diff --name-only "$BASE" "$CAND" -- . "${EXCLUDE[@]}") \
     <(git diff --name-only origin/main HEAD)
# 3. Exec bits survived. Expect 100755 on all four.
git ls-tree HEAD scripts/deploy/deploy-vikunja-release-stage.py \
    scripts/deploy/deploy-vikunja-release-activate.py \
    scripts/vikunja/rollback_release.py scripts/vikunja/stage_release_archive.py
# 4. The suite passes without the cutover set. A failure aborts here,
#    before any push or PR.
set -o pipefail; make test 2>&1 | tee /tmp/vikunja-stage-make-test.log || { echo "TESTS FAILED: stop"; exit 1; }
```

Push and open the PR only after all four checks pass.

**Agent**: push the branch and open the PR. Kent approves the PR copy first:

```bash
git push -u origin feat/vikunja-release-stage
gh pr create --repo kentonium3/kg-automation --base main --head feat/vikunja-release-stage \
  --title "feat(vikunja): STAGE the RRULE release image (#1087)" --body-file <approved-body.md>
```

### 4b. Merge STAGE (Kent)

**Kent**: merge the STAGE PR. It is inert: no container or Compose change.

```bash
gh pr merge <stage-pr-number> --repo kentonium3/kg-automation --merge
```

### 4c. What the deployer does

Within about 5 minutes the felix-deployer runs a tick, as `claude` from
`/home/claude/kg-automation`:

1. It pulls `origin/main`.
2. It holds the deploylock for the whole tick.
3. Because the manifest is tier 2, it runs the backup gate first; this may run
   `backup.sh`.
4. It runs `verification.pre`, which is the STAGE dry run, then the entrypoint's
   `--dry-run`, then its `--apply`, then the two `verification.post` image-ID
   checks.
5. On success it writes `deploys/applied/<NNNN>-vikunja-release-stage.yaml`,
   moves the manifest out of the queue, and commits and pushes.
6. The declared baseline `docker-images.txt` is rebaselined automatically
   (deferred-confirm), and the outcome is stamped on the applied record.

On failure the manifest stays queued and re-runs every tick (see section 12).

Expected STAGE apply output, in the tick log:

- `STAGE_APPLIED`
- `STAGE_ARCHIVE_VERIFIED` and `STAGE_STATE`
- `STAGE_LOADED id=sha256:35e1bc87…`
- `STAGE_IMAGE_VERIFIED`
- `STAGE_TAGGED_RELEASE`
- `STAGE_CREATED_ACTIVE id=sha256:60fe1ee8…`

A later re-run reports `STAGE_ALREADY_STAGED`.

### 4d. Verify STAGE (Agent)

```bash
git fetch origin && git ls-tree --name-only origin/main deploys/applied/ | grep vikunja-release-stage
ssh office2-claude 'tail -5 /data/services/felix-deployer/logs/$(date -u +%F).jsonl'
ssh office2-claude "docker image inspect --format '{{.Id}}' office2.local/vikunja:v2.7.1-670-420c7bcb75 office2.local/vikunja:active vikunja/vikunja:2.4.0"
ssh office2-claude "docker inspect vikunja --format '{{.Image}} {{.Config.Image}}'"
ssh office2-claude 'curl -fsS --max-time 5 http://100.92.197.90:3456/api/v1/info | jq -r .version'
```

Pass requires all of the following:

- the applied record exists;
- the image IDs are `35e1bc87…`, `60fe1ee8…` and `60fe1ee8…`, in that order;
- the container still runs `sha256:60fe1ee8…` as `vikunja/vikunja:2.4.0`;
- `/api/v1/info` reports `v2.4.0`.

The service must be unchanged.

## 5. Host readiness after STAGE (Agent)

Re-run the candidate ACTIVATE dry run from section 2:

```bash
ssh office2-claude "cd /data/services/vikunja/candidate-$S12 && PYTHONDONTWRITEBYTECODE=1 ./scripts/deploy/deploy-vikunja-release-activate.py --dry-run; echo exit=\$?"
```

Expected: exit 1, `FAILED code=ACTIVATE_PRECONDITIONS_UNMET`, and **exactly one**
unmet check:

- `check_code=PRE_COMPOSE status_code=UNMET code=PRE_COMPOSE_NOT_ACTIVE`

Every other check, from `PRE_STORE` to `PRE_VERSION`, must be `MET`, and the
marker must be `ABSENT`. Record this output in the go packet. It is the host
readiness evidence. The release-exact readiness check is the ACTIVATE
manifest's own `verification.pre`, which the deployer runs after the ACTIVATE
merge.

## 6. ACTIVATE merge: the cutover (Kent's explicit go)

### 6a. Before the go

1. **Kent**: agree the window. During it, users are told the service will be
   down, and the automations listed in the private packet are paused so that
   no write reaches Vikunja. Writes stay closed until acceptance passes
   (section 7).
2. **Kent**: decide in advance who disposes of post-cutover writes. Only Kent
   does. Every write after the snapshot, including the acceptance probe task,
   is a post-cutover write. That includes rows the server creates by itself:
   B1's login inserts a `sessions` row (`pkg/models/sessions.go`
   `CreateSession`), and other server-generated rows may follow. So
   `ROLLBACK_POST_CUTOVER_WRITES` and the `--ack-post-cutover-writes <n>`
   disposition should expect tables beyond `tasks`.

### 6b. Assemble the ACTIVATE branch (Agent)

Run this only after section 4d has passed, so that `main` already carries
everything except the five cutover paths:

It uses the same mission clone and the same pinned `CAND` as section 4a:

```bash
REPO=/home/kgale/repos/kg-automation-vikunja-deploy
CAND=<full candidate SHA from the packet>
git -C "$REPO" fetch origin main
git -C "$REPO" worktree add /home/kgale/repos/kg-automation-vikunja-activate -b feat/vikunja-release-activate origin/main
cd /home/kgale/repos/kg-automation-vikunja-activate
git checkout "$CAND" -- \
  services/vikunja/docker-compose.yml \
  deploys/queued/vikunja-release-activate.yaml \
  docs/design/architecture/data/service-inventory.json \
  docs/design/architecture/service-inventory.md \
  tests/deploy/test_vikunja_cutover_change_set.py
git commit -m "feat(vikunja): ACTIVATE the RRULE release, the cutover (#1087)"
git diff --name-only origin/main HEAD          # expect exactly the five paths
git diff origin/main HEAD -- services/vikunja/docker-compose.yml   # expect -image, +image, +pull_policy only
set -o pipefail; make test 2>&1 | tee /tmp/vikunja-activate-make-test.log || { echo "TESTS FAILED: stop"; exit 1; }
git push -u origin feat/vikunja-release-activate
gh pr create --repo kentonium3/kg-automation --base main --head feat/vikunja-release-activate \
  --title "feat(vikunja): ACTIVATE the RRULE release (#1087)" --body-file <approved-body.md>
```

### 6c. The go (Kent)

**Kent**, and only with an explicit go:

```bash
gh pr merge <activate-pr-number> --repo kentonium3/kg-automation --merge
```

### 6d. What happens next

Within about 5 minutes the deployer pulls `main`. From that moment the live
Compose file selects `office2.local/vikunja:active`, which still points at 2.4.0,
so a restart at this point is harmless. The deployer then runs the tier-2 backup
gate, `verification.pre` (the ACTIVATE dry run, which must now be
`ACTIVATE_DRY_RUN_READY`), the dry run and `--apply`.

**Expected outage:** at most 300 s. The outage deadline runs from
`compose down` to a verified start, and it includes the 180 s readiness poll
and the log check. Missing the deadline is a failure
(`ACTIVATE_OUTAGE_DEADLINE`). After the apply, the manifest's `verification.post`
re-checks the running image ID, and `/api/v1/info` with a 5 s curl limit.

**Agent**: watch, read-only:

```bash
ssh office2-claude 'tail -5 /data/services/felix-deployer/logs/$(date -u +%F).jsonl'
ssh office2-claude 'cat /data/services/vikunja/activation/v2.7.1-670-420c7bcb75.json'
```

Success output: `ACTIVATE_VERIFIED release_version=v2.7.1-670-420c7bcb75 ... pre_version=v2.4.0 outage_seconds=<n>`,
with these lines among its details:

- `ACTIVATE_SNAPSHOT snapshot_dir=… db_sha256=… tasks_before=<n>`
- the `ACTIVATE_STEP` lines `stopped`, `snapshotted`, `retagged`, `started_new`
  and `verified`
- `ACTIVATE_LOGS private_log=…`
- `ACTIVATE_MIGRATION processed=… converted=… already_rrule=… unconvertible=… server_zone=…`

The marker then shows `phase: verified` and `outcome: success`, and the
deployer writes `deploys/applied/<NNNN>-vikunja-release-activate.yaml`.

Copy `snapshot_dir`, `db_sha256`, `tasks_before` and the migration counts into
the **private** packet only.

A failure prints `FAILED code=<code>`, then `ACTIVATE_FAILED_AT` and
`ACTIVATE_CLEANUP lock_code=HELD container_code=ABSENT ...`. That state means no
container exists, `active` is untagged and the marker says `failed`.

**`lock_code=NOT_CONFIRMED`** means the cleanup's untag did not complete, so
`active` may still be tagged. A reboot could then start whatever image it
names. The usual cause is that the image identity could not be proven.
Before any `docker image rm`, the untag requires the image `active` names to
also carry the release tag or `vikunja/vikunja:2.4.0`, with the matching ID.
Without that proof the code refuses with `ACTIVATE_UNTAG_UNSAFE` and never
attempts the removal. A failed removal shows the same `lock_code`. The cause is
in the private log `activate-cleanup-untag-failed`. **Stop**. The agent checks
`active` with the inspection in section 9 step 5. If that proof holds there,
the agent finishes the untag by hand as described there; otherwise Kent decides.
`container_code=PRESENT` or `UNKNOWN` is likewise a stop.

When the cleanup state is `HELD` and `ABSENT`:
- if the failure came before the retag and the marker has no `snapshot_dir`, go
  to section 9a;
- otherwise go to section 9 (rollback).

Section 12 lists every code.

## 7. Acceptance, with writes still closed

Acceptance follows the application checklist in
kentonium3/vikunja-harness, `harness` branch, commit `ad7f0c8e3`,
`harness-docs/plans/office2-post-cutover-acceptance.md`. Read it there; it is
not copied here. It has two outcomes: **ACCEPT**, after which writes reopen, or
**ROLLBACK**, which is section 9.

**Timing.** `T0` is the `ACTIVATE_VERIFIED` time. The checklist's 45-minute
budget starts at `T0`, after ACTIVATE's own 300 s outage deadline has been met.
It never extends that deadline or any other mandatory deadline: if ACTIVATE
fails, there is no acceptance run. If a step overruns, writes stay closed and
Kent decides whether to continue or roll back. Writes reopen only after ACCEPT.

**Binding the checklist's inputs.** Every expected value is bound to the
**fresh write-boundary snapshot that ACTIVATE took at the cutover**. Never use a
rehearsal figure: Ring 5 Run 3's 89 tasks and 8 legacy rows are not expected
values. All values go into the private packet only.

- **Snapshot identity and time:** `snapshot_dir`, `db_sha256` and `created_at`,
  from `<snapshot_dir>/snapshot.json`. The same values appear in the
  `ACTIVATE_SNAPSHOT` line and in the marker.
- **`N_tasks`:** `tasks_count` in `snapshot.json`, which is `tasks_before` in
  the marker. ACTIVATE counted every row in `tasks` on the consolidated snapshot.
- **`N_legacy`, and the legacy ids:** the rows in the snapshot with
  `repeat_after > 0 OR repeat_mode > 0`. Read them from the consolidated
  snapshot file, which has no WAL, with an immutable read-only open:

  ```bash
  ssh office2-claude python3 - <<'PY'
  import sqlite3
  snap = "<snapshot_dir>/vikunja.db"
  c = sqlite3.connect(f"file:{snap}?mode=ro&immutable=1", uri=True)
  print("N_tasks", c.execute("select count(*) from tasks").fetchone()[0])
  print("N_legacy", c.execute("select count(*) from tasks where repeat_after > 0 or repeat_mode > 0").fetchone()[0])
  print("legacy_ids", [r[0] for r in c.execute("select id from tasks where repeat_after > 0 or repeat_mode > 0 order by id")])
  PY
  ```

- **The legacy id set, and the expected rule and `repeats_from_current_date`
  for each legacy id:** bound by running the Ring 4 harness on a copy of the
  fresh snapshot (below). Counts alone never establish B4.
- **Month-end and undated mode-0 task ids:** read them from the same snapshot
  copy, as the checklist describes.

**Binding B4 with the Ring 4 harness (Agent, on office4).** Start this as soon as
`ACTIVATE_VERIFIED` is in, while the Kent UI checks run. Everything it produces
is production data. It stays in one private 0700 folder on office4 and in the
private packet, and never enters a repository.

1. Make the private folder and copy the fresh snapshot's single consolidated
   file into it. `<snapshot_dir>` and `<db_sha256>` come from the marker or
   `<snapshot_dir>/snapshot.json`:

   ```bash
   umask 077
   P=$(mktemp -d "$HOME/.local/state/vikunja-acceptance-XXXXXX")
   mkdir "$P/snapshot" "$P/b4"
   ssh office2-claude 'cat <snapshot_dir>/vikunja.db' > "$P/snapshot/vikunja.db"
   sha256sum "$P/snapshot/vikunja.db"     # must equal <db_sha256>
   ```

2. Check out the harness at the reviewed commit, `ad7f0c8e3` or a later
   reviewed `origin/harness`, as a detached worktree. Use the accepted release
   binary that the PM retained beside the archive, and check it:

   ```bash
   git -C /home/kgale/repos/vikunja-harness fetch origin harness
   git -C /home/kgale/repos/vikunja-harness worktree add --detach "$P/harness" ad7f0c8e3
   BIN=/home/kgale/.local/share/rrule-office2-images/420c7bcb75231be9b6571fdfdf76a1a62f2aebd8/vikunja
   sha256sum "$BIN"     # must be 049a3f1cb5ff8e4d69de077172a7c1b860ef1f83c996b9291043989a64e47414
   "$BIN" version       # must print: Vikunja api version v2.7.1-670-420c7bcb75
   ```

   The expected sha is `binary_sha256` in that folder's `artifact-manifest.json`.
   The harness needs `go`, `sqlite3` 3.38 or later and `python3` on office4.

3. Run the harness against the copy. The `--timezone` is office2's
   `service.timezone`. The Compose file sets no `VIKUNJA_SERVICE_TIMEZONE`, so
   it is Vikunja's default, `GMT`. `--test-dir` must not contain the input,
   because the harness wipes it:

   ```bash
   set -o pipefail
   "$P/harness/harness-docs/testing/vikunja-prod-test-env.sh" \
     --binary "$BIN" \
     --input-db "$P/snapshot/vikunja.db" \
     --input-sha256 <db_sha256> \
     --snapshot-ref "ACTIVATE write-boundary snapshot <snapshot_dir>, VACUUM INTO, created_at <created_at>" \
     --timezone GMT \
     --test-dir "$P/ring4" 2>&1 | tee "$P/ring4.log" || { echo "RING4 FAILED: stop"; exit 1; }
   grep -E '^ring4_verdict=' "$P/ring4/run-record.txt"     # must be ring4_verdict=passed
   ```

   It must exit 0. Its outputs in `$P/ring4/` bind B4:
   - `legacy-originals.txt` holds `id|repeat_after|repeat_mode|due_date|owner_tz`
     for every legacy row (`repeat_after > 0 OR repeat_mode > 0`). Its id column
     is the legacy id set, and `wc -l` gives `N_legacy`.
   - `rrule-expected.txt` holds `id|repeats|repeats_from_current_date` (flag
     0 or 1): the oracle's expected rule and flag for each legacy id. An empty
     rule marks an unconvertible row, and there must be none, because U = 0.
   - The harness also checks the migrated copy itself: the backup table equals
     the originals, and every legacy row has the oracle's rule and flag.

**Check B3 (`N_tasks` live, taken before the probe).** Take a commit-consistent
private copy of the live data files and count on the copy. Never open the live
file for writing, never use `immutable=1` (it ignores the WAL and gives a stale
count), and never count on the live file.

Method: the **hash-stable double copy** (lead decision, bus fac65941). Copy
`vikunja.db`, `-wal` and `-shm` into a private folder, copy them again into a
second folder, and accept only when both rounds hash identically; otherwise
retake. With writes closed this converges at once. The SQLite online-backup API
from a `mode=ro` URI was the preferred method, but its read-only proof against
the live database under `office2-claude` was not run: the permission classifier
held it (2026-10-30). It stays unproven and is not used here.

```bash
ssh office2-claude python3 - <<'PY'
import glob, hashlib, os, shutil, sqlite3, tempfile
os.umask(0o077)
L = "/data/services/vikunja/data"
def take():
    d = tempfile.mkdtemp(prefix="acceptance-", dir="/data/services/vikunja/failures")
    for f in sorted(glob.glob(L + "/vikunja.db*")):
        shutil.copy2(f, d)
    h = {os.path.basename(f): hashlib.sha256(open(f, "rb").read()).hexdigest()
         for f in sorted(glob.glob(d + "/vikunja.db*"))}
    return d, h
for attempt in range(5):
    d1, h1 = take()
    d2, h2 = take()
    shutil.rmtree(d2)
    if h1 == h2:
        break
    shutil.rmtree(d1)
else:
    raise SystemExit("B3_COPY_UNSTABLE")
c = sqlite3.connect(os.path.join(d1, "vikunja.db"))
print("copy", d1)
print("integrity", c.execute("pragma integrity_check").fetchone()[0])
print("N_tasks", c.execute("select count(*) from tasks").fetchone()[0])
PY
```

`integrity` must print `ok`. `B3_COPY_UNSTABLE` after five rounds means
something is still writing, so stop and find the writer. If B3 or B4 then
mismatches, retake the copy once, removing the first copy folder, before calling
a FAIL.

**Check B4 (the live conversion, on the same pre-probe copy as B3).** The columns
are those of the migration `pkg/migration/20261022220000.go`:
`tasks.repeats`, `tasks.repeats_from_current_date`, and the backup table
`task_repeat_legacy_backup(id, repeat_after, repeat_mode)`. Dump them from the
private copy that B3 made on office2 into the private folder `$P` on office4.
The formats match the Ring 4 harness exactly:

```bash
ssh office2-claude python3 - <copy dir from B3>/vikunja.db <<'PY' > "$P/b4/live-backup.txt"
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
for r in c.execute("select id, repeat_after, repeat_mode from task_repeat_legacy_backup order by id"):
    print("|".join("" if v is None else str(v) for v in r))
PY
ssh office2-claude python3 - <copy dir from B3>/vikunja.db <<'PY' > "$P/b4/live-rules.txt"
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
for i, rule, flag in c.execute("select id, coalesce(repeats, ''), case when repeats_from_current_date then 1 else 0 end from tasks"):
    print(f"{i}|{rule}|{flag}")
PY
```

Then compare on office4. Each check must print its PASS word:

```bash
R4="$P/ring4"
# The backup table holds exactly the snapshot's legacy rows, with their original values.
cut -d'|' -f1-3 "$R4/legacy-originals.txt" | cmp -s - "$P/b4/live-backup.txt" && echo B4_BACKUP_PASS
# Every legacy id has the expected rule and flag.
BAD=$(awk -F'|' 'NR == FNR { got[$1] = $2 "|" $3; seen[$1] = 1; next }
  !($1 in seen) || got[$1] != $2 "|" $3 { printf "%s ", $1 }' "$P/b4/live-rules.txt" "$R4/rrule-expected.txt")
[ -z "$BAD" ] && echo B4_RULES_PASS || echo "B4_RULES_FAIL ids: $BAD"
# No legacy row is unconvertible.
awk -F'|' '$2 == "" { n++ } END { exit n > 0 }' "$R4/rrule-expected.txt" && echo B4_NO_UNCONVERTIBLE_PASS
```

The checklist's B4 also requires the migration summary line. ACTIVATE recorded
it as `ACTIVATE_MIGRATION`, and it must show `processed` equal to
`wc -l < "$R4/legacy-originals.txt"` and `unconvertible=0`. That is a
**further** condition. It is not a substitute for the per-id comparisons above.

After the packet closes, remove the copies:

- on office4: `rm -rf -- "$P"`, then
  `git -C /home/kgale/repos/vikunja-harness worktree prune`;
- on office2, the B3 copy: `ssh office2-claude 'rm -rf -- <copy dir from B3>'`.

**Check D (the write probe).** The disposable probe task is a real write after
the snapshot. Tasks are soft-deleted, so its row stays in the DB after the
delete. If anything later leads to a rollback, the probe is one of the rows
counted in `ROLLBACK_POST_CUTOVER_WRITES` and acknowledged with
`--ack-post-cutover-writes` (section 9). The expected disposition is to discard
it. Deleting the probe does not make a rollback lossless.

**Kent**: run the checklist's UI checks:

- A4: the usual HTTPS URL loads the login page (the proxy path; A1 only probes
  the Tailscale port);
- B1: owner login;
- B2: the task list and one project;
- C1 to C3: recurrence, read-only;
- D1 to D4: the probe. **Start D1 only after the agent reports the B3 copy
  path and `N_tasks`.** The probe adds a row that its deletion keeps, so a B3
  taken after D1 would give a false FAIL.

Then decide ACCEPT or ROLLBACK in the record.

**Agent**: run the checks that need the host:

- A1: `/api/v1/info`;
- A2: the running image ID, which is the `verification.post` check, and exactly
  one container under the existing unit and Compose project;
- A3: the startup and migration log, from the private `ACTIVATE_LOGS` file.
  This build logs in logfmt (`time=… level=INFO msg="…"`). ACTIVATE already
  required a record at `level=INFO` whose `msg` is exactly
  `Ran all migrations successfully.`; a `msg` that merely contains that
  phrase, or unstructured text, does not count. ACTIVATE read the RRULE
  summary counts from the record whose `msg` is the
  `RRULE migration: … processed — …` summary;
- B3 and B4. Take B3 **before** Kent starts D1, then report the copy path and
  `N_tasks` to Kent; that report is the handoff that releases D1;
- E1: the container log from `T0`.

These are the commands for A1, A2 and E1:

```bash
ssh office2-claude 'curl -fsS --max-time 5 http://100.92.197.90:3456/api/v1/info | jq -r .version'
ssh office2-claude "docker inspect vikunja --format '{{.Image}}'"
ssh office2-claude "docker ps -a --filter label=com.docker.compose.project=vikunja --format '{{.Names}} {{.Image}}'"   # expect exactly one row
ssh office2-claude 'docker logs --since <T0> vikunja 2>&1 | grep -ciE "level=(error|fatal|panic)|panic|(^|[[:space:]])status=5[0-9]{2}([[:space:]]|$)"'
```

Log contents and task data stay on office2 and in the private packet.

**After ACCEPT:** writes reopen, and the paused automations resume as the
packet says. Remove the candidate folder:
`ssh office2-claude 'rm -rf /data/services/vikunja/candidate-<sha12>'`.

## 8. Residual risk (R-21), in plain words

The design guarantees two things, on every startup path including a reboot:

- **The old 2.4.0 image never runs on a possibly-migrated database.** After
  ACTIVATE points `active` at the release, nothing points it back at 2.4.0
  except the rollback helper, and only after its guard has proven that the
  unmigrated snapshot is back in place.
- **Nothing writes the database while the snapshot is copied.** The order is
  stop, untag `active`, prove no container exists, then copy.

What it does **not** guarantee: if office2 crashes or reboots **after** `active`
points at the release, `vikunja.service` may start the release image at boot
on its own migrated database before anyone has verified it. This can happen
during `compose up`, during verification, or during failure cleanup. The
release would then be running unverified. No data is lost: the snapshot was
already taken, and this is the target image on the target schema. The marker's
last `phase` tells the operator where it stopped:

- `retagged` or `started_new`: finish the verification by hand (section 7, A1
  to A3), or roll back (section 9).
- `failed` with cleanup interrupted: roll back (section 9).

A crash between `compose down` and the untag restarts **2.4.0 on the
unmigrated database**. That is safe: no data is at risk. But the marker is left
at phase `stopped` with no outcome, because ACTIVATE died before it could record
one, and every later tick replays `ACTIVATE_PRIOR_ATTEMPT_STOPPED`. No scripted
path covers this state:
- the section 9a recovery requires outcome `failed` and no container;
- the section 9 rollback requires a snapshot.

**Stop.** The agent records the marker, `docker inspect vikunja --format '{{.Image}}'`
and the `active` tag's ID. Kent decides the next step.

## 9. Rollback

Use this when ACTIVATE failed after its snapshot, or when acceptance says
ROLLBACK. The helper runs from the live checkout, which has carried it since
the STAGE merge. `--prepare` and `--finish` each hold both the felix-deployer
deploylock and ACTIVATE's `activation.lock`; `--dry-run` only probes them. A
busy lock refuses before any Docker call:
`ROLLBACK_DEPLOYER_BUSY` means a tick is running, so wait and re-run;
`ROLLBACK_ACTIVATION_RUNNING` means an ACTIVATE is still alive.

`<snapshot_dir>` is the marker's `snapshot_dir`.

**If the marker has no `snapshot_dir`**, ACTIVATE failed before its snapshot
completed. The rollback below cannot run, because there is no snapshot to
restore. Use section 9a instead.

1. **Agent**: check the state, read-only:

   ```bash
   ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py --snapshot <snapshot_dir> --dry-run'
   ```

   It prints one `ROLLBACK_STATE` line: marker phase and outcome, snapshot sha,
   `pre_version`, container image, `active`, data sha, sidecars, and whether
   both locks are free.

2. **Agent**: prepare.

   ```bash
   ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py --snapshot <snapshot_dir> --prepare'
   ```

   The helper:
   - captures the container's logs privately;
   - runs `compose down` and untags `active`;
   - copies the failed DB into `/data/services/vikunja/failures/<UTC>-rollback/`;
   - counts the rows written after the snapshot on a private copy (aggregates
     only).

   It prints:
   - `ROLLBACK_POST_CUTOVER_WRITES count=<n> tables=<t> snapshot_at=…`
   - a `post-cutover writes: table=… added=… removed=… changed=…` line per table
   - `ROLLBACK_PREPARED … post_cutover_writes=<n>`
   - `ROLLBACK_KENT_RESTORE_COMMAND`
   - the exact restore line

   A `success` marker adds `ROLLBACK_OF_VERIFIED_ACTIVATION`.

3. **Kent**: dispose of the post-cutover writes in writing. The acceptance
   probe is one of them. This sets `<n>`.

4. **Kent**: run the printed restore command through `office2-kgale`. Use the
   line exactly as printed. Its form is:

   ```bash
   ssh office2-kgale
   sudo install -o kgale -g root -m 644 <snapshot_dir>/vikunja.db /data/services/vikunja/data/vikunja.db && sudo rm -f /data/services/vikunja/data/vikunja.db-wal /data/services/vikunja/data/vikunja.db-shm
   ```

5. **Agent**: finish, with the acknowledged count:

   ```bash
   ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py --snapshot <snapshot_dir> --finish --ack-post-cutover-writes <n>'
   ```

   It refuses with `ROLLBACK_ACK_MISMATCH` unless `<n>` equals the prepared
   count. The guard then checks, in order:
   1. no container (`GUARD_CONTAINER_PRESENT`);
   2. the lock is held (`GUARD_LOCK_NOT_HELD`);
   3. no `-wal` or `-shm` (`GUARD_SIDECAR_PRESENT`);
   4. the sha equals the snapshot (`GUARD_SHA_MISMATCH`);
   5. no migration signal on a private read-only copy (`GUARD_DB_MIGRATED`).

   Then it tags `active` to 2.4.0, runs `compose up -d`, checks the running
   image, and waits for `/api/v1/info` to report the recorded `pre_version`.
   It then sets the marker to `rolled_back`. On success it prints:
   - `ROLLBACK_GUARD_PASSED`, `ROLLBACK_STARTED`, `ROLLBACK_READY version=v2.4.0`
     and `ROLLBACK_FINISHED … outcome=rolled_back`;
   - the follow-ups `ROLLBACK_FOLLOWUP_REBASELINE` (with the two commands) and
     `ROLLBACK_FOLLOWUP_QUEUE`.

   **`MARKER_DURABILITY_UNCERTAIN`.** The output is
   `ROLLBACK_MARKER_DURABILITY_UNCERTAIN service_up=1 … marker_outcome=rolled_back`,
   then `FAILED code=MARKER_DURABILITY_UNCERTAIN`. The service **is** up on
   2.4.0 and verified, and the marker reads `rolled_back`. Only the marker
   write's final durability step failed, and nothing was torn down. Treat the
   rollback as finished: the agent confirms the marker by reading it (as in
   section 9a), runs steps 6 and 7 by hand, and notes the event for Kent.

   **Readiness failure after the start.** If `compose up`, the image check or
   readiness fails after the tag, the helper cleans up: logs privately, then
   `compose down`, then untag `active`. It prints
   `ROLLBACK_CLEANUP container=<0|1|-1> active=<id or -> down_code=<code or -> untag_code=<code or ->`
   and leaves the marker unchanged. 2.4.0 may have written the restored DB in
   the meantime, so **a retry needs Kent's restore again** (step 4) before
   `--finish` is re-run. The guard's sha check refuses (`GUARD_SHA_MISMATCH`)
   until it is. Do not re-run `--prepare`: it refuses with
   `ROLLBACK_ALREADY_PREPARED`.

   The cleanup is best effort, so it can leave the container running or
   `active` tagged. **Before Kent restores again**, the agent must confirm both
   of the following. Never restore over a DB that a running container may be
   writing.

   ```bash
   # 1. No vikunja container exists. Expect no output.
   ssh office2-claude 'docker ps -a --filter name=^vikunja$ -q'
   # 2. active is untagged. Expect ACTIVE_ABSENT.
   ssh office2-claude 'docker image inspect office2.local/vikunja:active >/dev/null 2>&1 && echo ACTIVE_PRESENT || echo ACTIVE_ABSENT'
   # 3. The helper's own view. Expect container_image=- and active=-.
   ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py --snapshot <snapshot_dir> --dry-run'
   ```

   **If the cleanup failed** (a container exists, or `active` is present), the
   agent finishes it by hand, in this order, and then re-runs the three checks
   above:

   ```bash
   # a. Stop the service with the unit's own arguments.
   ssh office2-claude 'docker compose -f /home/claude/kg-automation/services/vikunja/docker-compose.yml down'
   ssh office2-claude 'docker ps -a --filter name=^vikunja$ -q'          # expect no output
   # b. Untag active, only if it still names a known image under another name
   #    as well, so that the rm removes the tag and never an image.
   ssh office2-claude "docker image inspect --format '{{.Id}}{{range .RepoTags}} {{.}}{{end}}' office2.local/vikunja:active"
   ```

   This is the same proof the code makes before an untag
   (`dbsafety.untag_active`). The output is the ID, then every tag on that
   image. Remove the tag only if one of these holds:
   - the ID is `sha256:60fe1ee8…` and the tags include `vikunja/vikunja:2.4.0`;
   - the ID is `sha256:35e1bc87…` and the tags include
     `office2.local/vikunja:v2.7.1-670-420c7bcb75`.

   Otherwise `active` is that image's last name, and `docker image rm` would
   delete the image itself. **Stop** in that case. Otherwise remove the tag:

   ```bash
   ssh office2-claude 'docker image rm office2.local/vikunja:active'
   ssh office2-claude 'docker image inspect office2.local/vikunja:active >/dev/null 2>&1 && echo ACTIVE_PRESENT || echo ACTIVE_ABSENT'   # expect ACTIVE_ABSENT
   ```

   If `compose down` fails, or a container survives it, **stop**. Kent decides;
   the restore must not run. Only once all three checks pass does Kent re-run
   step 4, and the agent re-run step 5.

6. **Agent**: the manual rebaseline. The rollback is an out-of-band change.
   Run the two commands `--finish` printed. Take the archive first, then the
   reset, as in [Security Baseline Operations](<./security-baseline-ops.md>):

   ```bash
   ssh office2-claude 'cp -a /data/services/security-monitor/baselines /tmp/baselines-$(date +%s)'
   ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
   ```

   The helper prints these commands only while that runbook still contains
   them verbatim. Otherwise it prints a pointer to the runbook's Manual reset
   procedure.

7. **Kent**: cancel the queued ACTIVATE manifest (section 10). Writes reopen
   only after the restored 2.4.0 service passes its endpoint check.

NFR-004 budget: at most 15 minutes from the start of `--prepare` to
`ROLLBACK_FINISHED`, including Kent's restore.

## 9a. Recovery after a pre-snapshot ACTIVATE failure

**When to use it.** ACTIVATE failed before it tagged `active` to the release,
so the release never ran and the DB is unmigrated. The marker shows this:
- `outcome` is `failed`;
- `failed_phase` (the phase ACTIVATE was entering) is `started`, `stopped` or
  `snapshotted`;
- `phase` (the last phase it reached) is `started` or `stopped`.

These are failures in `compose down`, the untag, the no-container check or the
snapshot. Such a marker has no `snapshot_dir`. ACTIVATE's cleanup normally
leaves no container and `active` untagged
(`ACTIVATE_CLEANUP lock_code=HELD container_code=ABSENT`).

The service is down. The section 9 rollback cannot run, because it needs a
snapshot to restore. No Kent restore is needed here: the DB in place was never
migrated, and the helper proves that before it starts anything.

Section 9a does not apply in two cases:

- **A marker that got past the retag.** `phase` is `snapshotted` or later and
  the marker has a `snapshot_dir`. This gives `RECOVER_MARKER_PAST_RETAG`. Use
  section 9 instead.
- **A marker whose outcome is not `failed`.** This includes the crash case in
  section 8, and gives `RECOVER_MARKER_NOT_FAILED`. **Stop**; Kent decides.

1. **Agent**: read the marker, then check eligibility, read-only. Run the
   dry run **without** `--snapshot`:

   ```bash
   ssh office2-claude 'cat /data/services/vikunja/activation/v2.7.1-670-420c7bcb75.json'
   ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py --dry-run'
   ```

   Besides the `ROLLBACK_STATE` line, it prints:

   `ROLLBACK_RECOVER_ELIGIBILITY prelim_eligible=<0|1> checks_run=6 recover_code=<CODE|-> db_present=<0|1> db_migration_checked=0 deployer_lock_free=<0|1> activation_lock_free=<0|1>`

   Go on only with `prelim_eligible=1`, `recover_code=-` and `db_present=1`.
   `prelim_eligible` covers only the read-only guards. The migration check
   runs only in the real mode, so `db_migration_checked=0` is expected here.
   If either lock shows `0`, a tick or an ACTIVATE is running: wait and re-run
   the dry run.

2. **Agent**: recover. The mode takes no other argument: adding `--snapshot`
   or `--ack-post-cutover-writes` is a usage error (exit 2).

   ```bash
   ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py --recover-pre-snapshot'
   ```

**What it checks.** It holds both the felix-deployer deploylock and
`activation.lock` for the whole run. A busy lock refuses before any Docker call,
with `ROLLBACK_DEPLOYER_BUSY` or `ROLLBACK_ACTIVATION_RUNNING`. It then runs
these guards in order. The first one that fails refuses, before anything
changes:

1. `RECOVER_MARKER_MISSING`: there is no marker.
2. `RECOVER_MARKER_NOT_FAILED`: the marker's outcome is not `failed`.
3. `RECOVER_MARKER_PAST_RETAG`: `failed_phase` or `phase` is outside the
   pre-retag sets above.
4. `RECOVER_CONTAINER_PRESENT`: a `vikunja` container exists.
5. `RECOVER_LOCK_NOT_HELD`: `office2.local/vikunja:active` is still tagged.
6. `RECOVER_ROLLBACK_IMAGE_MISSING`: `vikunja/vikunja:2.4.0` does not resolve
   to `60fe1ee8…`.
7. `RECOVER_DB_MIGRATED`: a private copy of the **live** DB, with its `-wal`
   and `-shm`, shows a migration signal, which is a `task_repeat_legacy_backup`
   table or a `tasks.repeats` column. An inspection error, such as
   `DB_INSPECT_FAILED`, also refuses. So do `RECOVER_DATA_DB_MISSING` and
   `RECOVER_DB_COPY_FAILED`. The copy goes to
   `/data/services/vikunja/failures/<UTC>-recover/`.

On every refusal, **stop**. Nothing has been started, and Kent decides.

**On success.** It prints `ROLLBACK_RECOVER_GUARDS_PASSED`. Then it:
1. tags `active` to `60fe1ee8…`;
2. runs `compose up -d` with the unit's arguments;
3. checks the running image (`ROLLBACK_STARTED`);
4. waits for `/api/v1/info` to report `v2.4.0` (`ROLLBACK_READY`);
5. sets the marker outcome to `rolled_back`, with `recovered_pre_snapshot: 1`.

It then prints
`ROLLBACK_FINISHED … outcome=rolled_back … recovered_pre_snapshot=1` and the
follow-ups `ROLLBACK_FOLLOWUP_REBASELINE` and `ROLLBACK_FOLLOWUP_QUEUE`.

**On a failure after the tag**, such as a non-zero `compose up`,
`TIMEOUT_COMPOSE_UP_D`, the wrong image or the wrong version, the helper:
1. captures the logs privately;
2. runs `compose down` and untags `active`;
3. prints `ROLLBACK_CLEANUP`;
4. leaves the marker unchanged and exits 1.

Run the container and `active` checks in section 9 step 5, and finish the
cleanup by hand there if it failed. Then, after the cause is understood,
re-run step 1 of this section. No restore is involved, because the guard
re-proves on a fresh copy that the DB is unmigrated.

**`MARKER_DURABILITY_UNCERTAIN`** (also possible from `--finish`). The output
is `ROLLBACK_MARKER_DURABILITY_UNCERTAIN service_up=1 … marker_outcome=rolled_back`,
then `FAILED code=MARKER_DURABILITY_UNCERTAIN`.

What happened: the service **is** up on 2.4.0 and verified, and the marker
reads `rolled_back`. Only the final durability step of the marker write failed.
The helper deliberately keeps the service running. Treat the recovery as done,
then:

1. **Agent**: confirm the marker by reading it (`outcome` must be
   `rolled_back`):

   ```bash
   ssh office2-claude 'cat /data/services/vikunja/activation/v2.7.1-670-420c7bcb75.json'
   ```

2. **Agent**: run the follow-ups below by hand, because the helper did not print
   them.
3. **Agent**: note the event for Kent in the packet.

**Follow-ups:**
1. **Agent**: the manual rebaseline, with the two commands in section 9 step 6.
   The recovery is an out-of-band change.
2. **Kent**: cancel the queued ACTIVATE manifest (section 10).
3. A later attempt is an authorized retry (section 10). The marker is now
   `rolled_back` and 2.4.0 is running, which is what a retry requires.

## 10. Cancel and retry (R-17, R-24)

After a failed ACTIVATE, the manifest stays queued. Every tick, about every 5
minutes, re-runs it and gets the same result. It never stops or starts the
service again:

- a `failed` marker exits 1 with `ACTIVATE_PRIOR_ATTEMPT_<PHASE>`;
- after a rollback, the marker is `rolled_back` and the run exits 1 with
  `ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST`.

Each tick writes a new failure record and sends an alert, until the manifest is
cancelled or a retry succeeds.

**Cancel (Kent).** Kent merges a reviewed commit that deletes
`deploys/queued/vikunja-release-activate.yaml`. Compose stays on the indirection,
`image: office2.local/vikunja:active`, which the rollback has pinned to 2.4.0.
The marker stays as history, with outcome `rolled_back`.

- The same reviewed commit must keep the suite green.
  `tests/deploy/test_vikunja_cutover_change_set.py` reads that manifest from
  `deploys/queued/`, or from `deploys/applied/` if it was applied.
- The same commit must also correct the service inventory row, because the
  release is not running.

**Agent**: prepare that commit for review. **Kent**: merge it with
`gh pr merge <cancel-pr-number> --repo kentonium3/kg-automation --merge`.

If ACTIVATE had succeeded and acceptance then led to the rollback, the manifest
is already in `deploys/applied/`. Nothing is queued, so the cancel commit only
corrects the inventory and the test.

**Authorized retry.** A retry is allowed only after a **full rollback**: 2.4.0
running on the restored DB, and the marker `rolled_back`. It also needs Kent's
explicit retry go, as a distinct act. Retiring the marker without the rollback
is refused by procedure. It is also refused mechanically: the ACTIVATE
preconditions require the running image and `active` to be `60fe1ee8…`.

**Archiving the marker alone starts nothing** unless the ACTIVATE manifest is
in `deploys/queued/` on `main`. Whether it is depends on what happened before:

- **Not yet cancelled** (still queued after a failed ACTIVATE): the manifest is
  queued, and the next tick after the marker is archived runs the cutover.
- **Cancelled** (section 10 cancel merged), or **already applied** (acceptance
  led to the rollback): nothing is queued. A retry needs a Kent-merged,
  reviewed commit that does three things:
  - restores `deploys/queued/vikunja-release-activate.yaml` from the reviewed
    candidate;
  - restores `tests/deploy/test_vikunja_cutover_change_set.py` if the cancel
    changed it;
  - restores the service inventory files if the cancel reverted them.

  That merge is then the moment the cutover starts. The next tick runs it.

1. **Kent**: give the explicit retry go for an agreed window, as in section 6a.
2. **Agent**: archive the marker:

   ```bash
   ssh office2-claude 'cd /data/services/vikunja/activation && mv -n v2.7.1-670-420c7bcb75.json v2.7.1-670-420c7bcb75.$(date -u +%Y%m%dT%H%M%SZ).retired.json'
   ssh office2-claude 'ls /data/services/vikunja/activation/'      # the .json marker is gone; the .retired.json is present
   ```

   If the manifest is still queued, the cutover starts on the next tick, within
   about 5 minutes.
3. If nothing is queued, **Agent**: prepare the requeue commit for review, in a
   new worktree from `origin/main` as in section 6b, with
   `git checkout "$CAND" -- <the paths above>`. Then **Kent** merges it, with
   `gh pr merge <requeue-pr-number> --repo kentonium3/kg-automation --merge`.
4. The tick re-runs the manifest with the preconditions holding again. It
   takes a **new** snapshot, so section 7's inputs bind to that new snapshot.

## 11. STAGE partial-failure recovery (R-18)

STAGE creates no tag until verification passes. If verification fails after a
`docker load`, the loaded image stays **untagged**. STAGE then prints
`FAILED code=STAGE_VERIFY_FAILED`, or `STAGE_LOADED_ID_UNEXPECTED`, followed by
`STAGE_LOADED_UNTAGGED loaded_id=<id>`.

1. **Agent**: confirm that the image is untagged and is not the rollback image.
   Then remove it:

   ```bash
   ssh office2-claude "docker image inspect --format '{{.Id}} {{.RepoTags}}' <loaded_id>"   # expect: <loaded_id> []
   ssh office2-claude 'docker image rm <loaded_id>'
   ```

   Never remove `sha256:60fe1ee8…`.

2. **Agent**: run the manual rebaseline of `docker-images.txt`, using the two
   commands in section 9 step 6. The removal is out-of-band.
3. The STAGE manifest is still queued and re-runs every tick, so each tick loads
   the archive again. Find the cause before the next tick, or have Kent cancel
   the STAGE manifest with a reviewed commit that deletes
   `deploys/queued/vikunja-release-stage.yaml`.

`STAGE_TAG_RELEASE_FAILED` and `STAGE_ACTIVE_TAG_FAILED` need no cleanup: the
next tick re-verifies and completes the tags. A release tag that already points
at the config digest is re-verified, not reloaded.

## 12. Error codes

Every refusal prints `FAILED code=<code>` on line 1 and exits 1. A usage error
exits 2. Raw Docker, Compose and container output never appears. It goes to
the private 0700 folder:

- `/data/services/vikunja/failures/` on office2;
- `~/.local/state/vikunja-release-ingress/failures/` on office4, for the ingress.

The `private_log=` field names the file.

| Code | Where | Action |
|---|---|---|
| `INGRESS_SOURCE_FORBIDDEN`, `INGRESS_DEST_FORBIDDEN` | ingress | The record names a forbidden path. Stop: `release.json` is wrong. |
| `INGRESS_SOURCE_UNREADABLE`, `ARCHIVE_SIZE_MISMATCH`, `ARCHIVE_SHA_MISMATCH` (ingress) | ingress | An office4 source is missing or differs from the record. Stop, and ask the PM about custody. |
| `INGRESS_DEST_EXISTS`, `INGRESS_DEST_FILE_EXISTS` | ingress | The destination already exists. Do not overwrite it. Follow the recovery at the end of section 3. |
| `INGRESS_DEST_PARENT_UNSAFE`, `INGRESS_DEST_PARENT_CREATE_FAILED`, `INGRESS_MKDIR_FAILED` | ingress | `release-artifacts` is not a claude-owned 0700 real folder. Inspect it read-only, then stop. |
| `INGRESS_SPACE_INSUFFICIENT`, `INGRESS_SPACE_UNPARSEABLE` | ingress | Free space on `/data` is below twice the archives' size. Stop. |
| `INGRESS_SSH_FAILED`, `INGRESS_TRANSFER_TIMEOUT`, `INGRESS_EXEC_FAILED` | ingress | A transport failure. Only this run's `.part` file is removed, but the per-sha folder stays, so a re-run refuses with `INGRESS_DEST_EXISTS`. Follow the recovery at the end of section 3. |
| `INGRESS_SHA_MISMATCH`, `INGRESS_PART_REMOVE_FAILED` | ingress | The arrived bytes differ. The part is removed, or `INGRESS_PART_KEPT` names it. Follow the recovery at the end of section 3. |
| `ARCHIVE_MISSING` | STAGE | The ingress has not run. Run section 3. The manifest re-runs every tick. |
| `ARCHIVE_SIZE_MISMATCH`, `ARCHIVE_SHA_MISMATCH`, `ARCHIVE_UNREADABLE`, `ARCHIVE_*_MISMATCH`, `ARCHIVE_MEMBER_*`, `ARCHIVE_CONFIG_*` | STAGE | The archive on office2 is not the pinned one. Stop: nothing was loaded. |
| `DOCKER_UNREACHABLE`, `DOCKER_STORE_UNSUPPORTED` | STAGE, ACTIVATE | Docker is down, or it is not on the classic overlay2 store. Stop. The identity model depends on that store. |
| `STAGE_RELEASE_TAG_UNEXPECTED`, `STAGE_ACTIVE_UNEXPECTED` | STAGE | A tag points at an unknown image. Stop. Nothing is retagged. |
| `STAGE_ROLLBACK_IMAGE_MISSING`, `STAGE_ROLLBACK_IMAGE_UNEXPECTED` | STAGE | `vikunja/vikunja:2.4.0` is absent or changed. Stop. It can be restored from the rollback archive with `docker load`, as a reviewed step. |
| `STAGE_ACTIVATION_LOCK_BUSY`, `STAGE_ACTIVATION_LOCK_UNAVAILABLE` | STAGE | STAGE now holds `activation.lock`, as ACTIVATE and the rollback helper do. Another STAGE, an ACTIVATE or a rollback holds it, or the lock or its folder is unsafe. The dry run refuses the same way. The manifest re-runs next tick; never delete the lock file. |
| `STAGE_ACTIVE_HELD_BY_ACTIVATION` | STAGE | A marker exists and `active` is absent. An activation holds the lock. Never create `active` by hand. Read the marker (sections 8 to 10). |
| `STAGE_LOAD_FAILED`, `STAGE_LOAD_OUTPUT_UNPARSEABLE` | STAGE | `docker load` failed. Read the private log. The next tick retries. |
| `STAGE_LOADED_ID_UNEXPECTED`, `STAGE_VERIFY_FAILED` | STAGE | Section 11. |
| `STAGE_TAG_RELEASE_FAILED`, `STAGE_ACTIVE_TAG_FAILED` | STAGE | The next tick completes the tags. Check the private log. |
| `ACTIVATE_PRECONDITIONS_UNMET` | ACTIVATE dry run | Read the `ACTIVATE_CHECK ... UNMET code=` lines. The expected sets are in sections 2 and 5. |
| `PRE_RELEASE_TAG_NOT_STAGED`, `PRE_RELEASE_FACTS_MISMATCH` | ACTIVATE check | STAGE has not been applied, or the release image changed. Run section 4. |
| `PRE_ACTIVE_ABSENT`, `PRE_ACTIVE_NOT_ROLLBACK` | ACTIVATE check | `active` is missing or not at 2.4.0. Before STAGE this is expected; after STAGE, stop. |
| `PRE_CONTAINER_ABSENT`, `PRE_CONTAINER_NOT_ROLLBACK`, `PRE_CONTAINER_REF_UNEXPECTED` | ACTIVATE check | The service is not running 2.4.0 as expected. Stop. |
| `PRE_COMPOSE_NOT_ACTIVE` | ACTIVATE check | Expected until the ACTIVATE merge. |
| `PRE_COMPOSE_UNREADABLE`, `PRE_COMPOSE_SERVICE_MISSING`, `PRE_COMPOSE_PULL_POLICY` | ACTIVATE check | The live Compose file is not the reviewed two-line change. Stop. |
| `PRE_DATA_UNREADABLE`, `PRE_SPACE_UNKNOWN`, `PRE_SPACE_LOW` | ACTIVATE check | The data files cannot be read, or there is no room for the snapshot (3 x DB + WAL). Stop. |
| `PRE_VERSION_UNREADABLE` | ACTIVATE check | `/api/v1/info` did not report `v2.4.0` within 15 s. Check the service. |
| `ACTIVATE_LOCK_BUSY`, `ACTIVATE_LOCK_UNAVAILABLE` | ACTIVATE | Another ACTIVATE or a rollback holds `activation.lock`, or the lock is unsafe. Wait. Never delete the lock file. |
| `MARKER_UNREADABLE` | STAGE, ACTIVATE | The marker is malformed. Stop. Kent decides. Do not edit it. |
| `MARKER_EXISTS`, `MARKER_WRITE_FAILED`, `MARKER_MISSING`, `MARKER_INVALID`, `MARKER_TOO_LARGE` | ACTIVATE apply | The marker could not be created or updated. If `MARKER_EXISTS`, another run created it first: re-run the dry run, which replays it. Otherwise read the marker and the cleanup line, then stop. |
| `ACTIVATE_REPLAY_INTERNAL_ERROR` | ACTIVATE replay | A defect on the read-only replay path. Nothing was touched. Stop. |
| `ACTIVATE_PRIOR_ATTEMPT_<PHASE>` | ACTIVATE replay | An earlier attempt failed at `<PHASE>`. Section 9 if the marker has a `snapshot_dir`; section 9a if it failed before the retag without one; the crash case in section 8 if its outcome is unset. |
| `ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST` | ACTIVATE replay | A rollback is complete. Cancel, or run an authorized retry (section 10). |
| `ACTIVATE_SUCCESS_NOT_RECONCILED` | ACTIVATE replay | The marker says success, but the running image or version disagrees. Stop. Check the container (section 8). |
| `ACTIVATE_COMPOSE_DOWN_FAILED`, `ACTIVATE_UNTAG_FAILED`, `ACTIVATE_CONTAINER_STILL_PRESENT`, `ACTIVATE_ROLLBACK_IMAGE_LOST` | ACTIVATE apply, before the snapshot | There is no snapshot. Check `ACTIVATE_CLEANUP` (section 6d), then section 9a. |
| `ACTIVATE_UNTAG_UNSAFE` | ACTIVATE apply or its cleanup | The image `active` names does not also carry the release tag or `vikunja/vikunja:2.4.0`, so `image rm` would delete it. The removal was not attempted, and `active` is still tagged (`lock_code=NOT_CONFIRMED`). Stop. Section 6d; Kent decides. |
| `SNAPSHOT_DEADLINE` | ACTIVATE apply | A snapshot copy or hash ran out of its time budget (checked before each chunk). The partial snapshot is not used, and the release never started. Section 9a. |
| `SNAPSHOT_*` (for example `SNAPSHOT_INTEGRITY_FAILED`, `SNAPSHOT_BUSY`, `SNAPSHOT_SOURCE_CHANGED`, `SNAPSHOT_SOURCE_MISSING`, `SNAPSHOT_COPY_FAILED`, `SNAPSHOT_WRITE_FAILED`, `SNAPSHOT_SQLITE_FAILED`, `SNAPSHOT_DIR_EXISTS`, `SNAPSHOT_RECORD_INVALID`) | ACTIVATE apply | The snapshot failed. The release never started. Section 9a. |
| `CLEANUP_LOGS_NOT_CAPTURED`, `CLEANUP_DOWN_FAILED`, `CLEANUP_UNTAG_FAILED`, `CLEANUP_CONTAINER_PRESENT`, `CLEANUP_MARKER_WRITE_FAILED` (as `cleanup_code=`), `CLEANUP_DEADLINE` | ACTIVATE cleanup | The first cleanup step that failed. Any other than `CLEANUP_LOGS_NOT_CAPTURED` means the cleanup is incomplete: stop and check the container and `active` (section 6d and section 9 step 5). |
| `ACTIVATE_TAG_ACTIVE_FAILED`, `ACTIVATE_COMPOSE_UP_FAILED`, `ACTIVATE_CONTAINER_IMAGE_WRONG`, `READY_TIMEOUT`, `READY_WRONG_VERSION`, `READY_PROBE_UNAVAILABLE`, `ACTIVATE_LOGS_NOT_CAPTURED`, `ACTIVATE_MIGRATION_LOG_MISSING`, `ACTIVATE_OUTAGE_DEADLINE`, `ACTIVATE_INTERNAL_ERROR` | ACTIVATE apply, after the stop | Cleanup ran: no container, `active` untagged. Check `ACTIVATE_CLEANUP lock_code=HELD container_code=ABSENT`. Then read the marker: if it records a `snapshot_dir`, roll back (section 9); if it does not (`ACTIVATE_OUTAGE_DEADLINE` and `ACTIVATE_INTERNAL_ERROR` can occur before the snapshot), use section 9a. |
| `FAILURES_ROOT_*`, `SNAPSHOT_ROOT_*`, `ACTIVATION_ROOT_*` (`_PARENT_MISSING`, `_CREATE_FAILED`, `_PARENT_SYNC_FAILED`, `_UNSAFE`) | STAGE, ACTIVATE, rollback | A private root is missing, foreign-owned or not 0700, or its parent directory could not be synced to disk. Inspect it read-only, then stop. |
| `DOCKER_INSPECT_FAILED`, `DOCKER_INSPECT_UNPARSEABLE` | any | A read-only Docker inspection failed. Read the private log and re-run once Docker answers. |
| `PRIVATE_LOG_WRITE_FAILED`, `PRIVATE_LOG_NAME_INVALID` | any | A private log could not be written. Inspect the private folder read-only. |
| `TIMEOUT_<STEP>`, `EXEC_FAILED_<STEP>`, `<STEP>_DEADLINE` | any | A bounded subprocess timed out or could not run. Read the private log. |
| `ROLLBACK_DEPLOYER_BUSY`, `ROLLBACK_ACTIVATION_RUNNING`, `ROLLBACK_DEPLOYER_LOCK_ERROR`, `ACTIVATION_LOCK_UNSAFE` | rollback | A tick or an ACTIVATE is running, or a lock is unsafe. Wait for the tick, then re-run. |
| `ROLLBACK_MARKER_MISSING`, `ROLLBACK_SNAPSHOT_NOT_MARKER`, `ROLLBACK_SNAPSHOT_PATH_INVALID` | rollback | Wrong `--snapshot`. Use the marker's `snapshot_dir`. |
| `ROLLBACK_SNAPSHOT_SHA_MISMATCH`, `ROLLBACK_SNAPSHOT_DB_UNREADABLE`, `SNAPSHOT_RECORD_UNREADABLE` | rollback | The snapshot is damaged. Stop. Kent decides. |
| `ROLLBACK_ALREADY_ROLLED_BACK` | rollback | Already done. Go to section 10. |
| `ROLLBACK_ALREADY_PREPARED` | rollback `--prepare` | Go on to Kent's restore and `--finish`. |
| `ROLLBACK_NOT_PREPARED` | rollback `--finish` | Run `--prepare` first. |
| `ROLLBACK_ACK_MISMATCH` | rollback `--finish` | `<n>` must equal `post_cutover_writes` from `ROLLBACK_PREPARED`, as Kent dispositioned it. |
| `COMPOSE_DOWN_FAILED`, `DOCKER_PS_FAILED`, `ROLLBACK_WRITES_UNCOUNTABLE`, `ROLLBACK_DATA_DB_MISSING`, `ROLLBACK_CONTAINER_STILL_PRESENT`, `FAILURES_DIR_EXISTS` | rollback `--prepare` | Stop and read the private log. Nothing has been restored. |
| `ACTIVE_TAG_UNEXPECTED`, `ACTIVE_UNTAG_FAILED` | rollback | `ACTIVE_TAG_UNEXPECTED` is the rollback helper's safe-untag refusal: the image `active` names does not also carry the release tag or `vikunja/vikunja:2.4.0`, so the removal was not attempted. `ACTIVE_UNTAG_FAILED` is a failed or unconfirmed removal. Stop either way. |
| `ROLLBACK_PREPARE_RECORD_UNREADABLE` | rollback `--finish`, `--prepare`, `--dry-run` | `<snapshot_dir>/rollback-prepare.json` is damaged. Stop. Do not edit it. |
| `GUARD_CONTAINER_PRESENT`, `GUARD_LOCK_NOT_HELD` | rollback `--finish` | Something started, or `active` was re-created. Stop. Find out what did it before anything else. |
| `GUARD_SIDECAR_PRESENT` | rollback `--finish` | A `-wal` or `-shm` file is present. Kent's restore must remove both. Re-run the restore. |
| `GUARD_SHA_MISMATCH` | rollback `--finish` | The DB in place is not the snapshot. Run the container and `active` checks in section 9 step 5 first; then Kent re-runs the restore (section 9 step 4). |
| `GUARD_DB_MIGRATED`, `GUARD_INSPECTION_ERROR` | rollback `--finish` | The DB in place is migrated, or cannot be proven unmigrated. Never start 2.4.0 on it. Stop. |
| `ROLLBACK_IMAGE_MISSING`, `ACTIVE_TAG_FAILED`, `COMPOSE_UP_D_FAILED`, `ROLLBACK_WRONG_IMAGE_RUNNING` | rollback `--finish` | Cleanup ran (`ROLLBACK_CLEANUP`). Confirm that no container exists and `active` is untagged, finishing the cleanup by hand if needed (section 9 step 5). Then Kent's restore again, then `--finish`. |
| `RECOVER_MARKER_MISSING`, `RECOVER_MARKER_NOT_FAILED` | `--recover-pre-snapshot` | Not a failed pre-retag activation. Stop; Kent decides (section 8 for an unset outcome). |
| `RECOVER_MARKER_PAST_RETAG` | `--recover-pre-snapshot` | ACTIVATE got past the retag. Use the section 9 rollback with the marker's `snapshot_dir`. |
| `RECOVER_CONTAINER_PRESENT`, `RECOVER_LOCK_NOT_HELD` | `--recover-pre-snapshot` | A container exists, or `active` is tagged. Stop. Find out what started or tagged it; do not clean it up blindly. |
| `RECOVER_ROLLBACK_IMAGE_MISSING` | `--recover-pre-snapshot` | `vikunja/vikunja:2.4.0` is absent or changed. Stop. |
| `RECOVER_DB_MIGRATED`, `DB_INSPECT_FAILED`, `DB_TASKS_TABLE_MISSING`, `RECOVER_DATA_DB_MISSING`, `RECOVER_DB_COPY_FAILED` | `--recover-pre-snapshot` | The live DB is migrated, or cannot be proven unmigrated. Never start 2.4.0 on it. Stop; Kent decides. |
| `MARKER_DURABILITY_UNCERTAIN` | `--finish`, `--recover-pre-snapshot` | The service is up on 2.4.0 and the marker reads `rolled_back`. Treat as done: read the marker, run the follow-ups by hand, and note it for Kent (section 9a). |
| `TIMEOUT_COMPOSE_UP_D` | `--finish`, `--recover-pre-snapshot` | Cleanup ran. Check it (section 9 step 5), then re-run the mode once the cause is understood. |
| `OUTPUT_VALUE_UNSAFE`, `INTERNAL_ERROR` | any | A defect. Stop and read the private log. |

## Related documents

- [Vikunja Operations](<./vikunja-ops.md>): day-to-day operations of the service.
- [Deploy Discipline](<./deploy/discipline.md>): the manifest pipeline, and the
  one-shot manifest pattern this route uses.
- [Security Baseline Operations](<./security-baseline-ops.md>): the automatic
  and manual rebaseline.
- `docs/design/architecture/evidence/vikunja-lock-sandbox-2026-10.md`: the
  office2 evidence that Compose fails closed with `pull_policy: never` and a
  missing tag (FAIL-CLOSED: CONFIRMED).
- `kitty-specs/vikunja-image-deploy-01M65D3V/`: the spec, plan, research (R-1 to
  R-24) and contracts.
