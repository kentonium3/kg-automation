---
title: Vikunja Release Cutover (the go packet)
doc_type: runbook
audience: agents_and_humans
status: approved
tags: [1087, 1095]
created: 2026-10-30
last_updated: '2026-11-09'
---

# Vikunja Release Cutover (the go packet)

This is the repeat-cutover procedure for the reviewed release in
`services/vikunja/release.json`. Tracking: see #1095; first-cutover history:
see #1087. The release record supplies every public release, image, archive,
rollback and service identity. Do not substitute historical values.
The published image carries no revision label, as declared in the release record; identity rests on the pinned archive SHA256 and config digest.

**Authority.** Agent host steps and ingress are executed by the Claude session,
through `ssh office2-claude`. Codex implements and tests with synthetic data
locally; it does not read private copies or execute host steps. Kent performs
the privileged restore, browser acceptance and ACCEPT or ROLLBACK decision.
Kent or the program lead may merge the reviewed PRs once review and CI pass,
under the delegated merge authority. Public PR copy still needs Kent's sign-off.

**Evidence custody.** Production rows, task identities, aggregate values,
snapshot locations and times stay in the private operator packet. Never paste
them into git, manifest notes, PRs or deploy output. Public commands and checks
derive their identities from the reviewed release record.

## 1. Preconditions and custody

**Agent**, before PR1:

- Confirm the release acceptance and release CI, candidate review and exact
  candidate commit. Check current archive bytes, hash and size against the
  published download and the record; old custody evidence is insufficient.
- Retain the previous release image and its reviewed rollback ref, archive
  and keeper tag. The previous successful activation marker stays untouched.
- Existing `active`, Compose and private roots are expected. Compose already
  selects `office2.local/vikunja:active` with `pull_policy: never`. It does not
  change in either PR. Running container, active tag and API version must match
  the record's rollback identity.
- Check root ownership and permissions using the helpers. Private roots must
  be real, owned directories, mode 0700. Only the **new** per-release marker
  must be absent. Existing roots and historical markers are allowed.
- New custody, candidate, ingress and snapshot destinations are create-only.
  Never overwrite a destination or delete evidence to make a retry pass.
- The release record must bind the committed data-free baseline by contained
  path and SHA256. The baseline records exact migrations (including
  `SCHEMA_INIT`), previous version/config and pre/target schema identities.
  No fixed migration-count check or completed repeat conversion is rerun.

## 2. Candidate validation before merge (Agent)

Use the reviewed mission checkout on office4. Set `REPO` to that checkout,
`CAND` to the full reviewed candidate commit and `MISSION_BRANCH` to
`fix/vikunja-repeat-cutover`. These are local shell variables, not private
database locations.

```bash
git -C "$REPO" cat-file -e "$CAND^{commit}"
test "$(git -C "$REPO" rev-parse "$MISSION_BRANCH")" = "$CAND"
S12=${CAND:0:12}
```

If either check fails, stop and re-pin/review. Do not use an older candidate.
Copy the complete runtime package, preserving repository layout:

```bash
git -C "$REPO" archive --format=tar "$CAND" \
    scripts/deploy/deploy-vikunja-release-stage.py \
    scripts/deploy/deploy-vikunja-release-activate.py \
    scripts/deploy/vikunja_release \
    scripts/deploy/lib \
    scripts/vikunja/rollback_release.py \
    scripts/vikunja/preflight_release_baseline.py \
    scripts/vikunja/verify_release_upgrade.py \
    scripts/vikunja/build_release_baseline.py \
    services/vikunja/release.json \
    services/vikunja/baselines \
  | ssh office2-claude "umask 077 && mkdir /data/services/vikunja/candidate-$S12 && tar -x -C /data/services/vikunja/candidate-$S12"
```

Use `set -o pipefail` in the invoking shell and require exit 0.
The `mkdir` is create-only. The shared package already includes
`baseline.py`; do not duplicate it. `scripts/deploy/lib` supplies
`installed_report`. The baselines directory includes the artifact bound by
the candidate's release record. No private copies or receipts enter this archive.

Both entrypoints resolve imports and release metadata from their own repository
root. Candidate ACTIVATE still checks the **live** Compose file named in its
record. Run both read-only dry runs from the candidate root on Office2:

```bash
ssh office2-claude "cd /data/services/vikunja/candidate-$S12 && PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/deploy-vikunja-release-activate.py --dry-run"
ssh office2-claude "cd /data/services/vikunja/candidate-$S12 && PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/deploy-vikunja-release-stage.py --dry-run"
```

Before STAGE, only `PRE_RELEASE_TAG_NOT_STAGED` may be unmet if the new
release is not loaded. Existing active and Compose must pass; do not expect
`PRE_ACTIVE_ABSENT` or `PRE_COMPOSE_NOT_ACTIVE`. Every other check must be MET,
the activation lock free and the new marker ABSENT. If the release is already
staged, ACTIVATE must report `ACTIVATE_DRY_RUN_READY`.

Before ingress STAGE may report `ARCHIVE_MISSING`. After ingress it must
report `STAGE_DRY_RUN_OK`, with exact archive identities and a plan that
retains the previous image and existing active. Reject unexpected identity,
store, lock or permission failures.

### Baseline preparation boundary

Claude prepares the committed data-free baseline from authorized private copies
before candidate review, using the required expected-count input:

```bash
python3 scripts/vikunja/build_release_baseline.py "$PRE_COPY" "$POST_COPY" "$RELEASE_RECORD" "$NEW_OUTPUT" --expected-added-count N
```

`PRE_COPY` is consolidated through the reviewed snapshot route; `POST_COPY`
is the qualified post-upgrade copy. The release record supplies rollback identity.
Set `N` to the number of migration IDs added in the Vikunja source between the
rollback and release source revisions. Record that reviewed count in the packet;
the builder checks it against the rehearsal's observed migration-set difference.
Zero is valid when the release adds no migrations. A count mismatch or a lost
predecessor ID refuses the build before any output is written.
Review the generated artifact and bind its exact bytes in the release record.
This is preparation, never an outage step. Codex must use synthetic inputs only.

## 3. Archive ingress (Agent)

The ingress destination already exists from an earlier candidate; do not redo ingress when its two files match the record's hashes and sizes.

From the reviewed checkout, confirm HEAD equals `CAND` and the ingress helper,
shared package and release record match it:

```bash
test "$(git -C "$REPO" rev-parse HEAD)" = "$CAND"
git -C "$REPO" diff --exit-code "$CAND" -- scripts/vikunja/stage_release_archive.py scripts/deploy/vikunja_release services/vikunja/release.json
cd "$REPO"
python3 scripts/vikunja/stage_release_archive.py --dry-run
python3 scripts/vikunja/stage_release_archive.py --apply
```

The helper reads custody sources from `roots.office4_sources`, verifies both
archives and transfers them into the new create-only per-sha destination.
Require `INGRESS_DRY_RUN_OK`, then `INGRESS_APPLIED`, and both remote hashes
equal the record. Re-run candidate STAGE dry-run after ingress.

On partial transfer, stop and inspect **that exact destination**. If both final
files match hash and size, ingress is complete; do not redo it. Otherwise retain
evidence and obtain an authorized cleanup of only the new partial destination
before retry. Never remove a root, previous custody, snapshot or rollback archive.
`INGRESS_DEST_EXISTS` is a refusal, not permission to overwrite.

## 4. PR1: STAGE

### 4a. Assemble and verify the exact change set (Agent)

The complete mission branch is never merged wholesale to main. PR1 contains
every mission change **except** these three WP07 paths:

```text
deploys/queued/vikunja-release-activate.yaml
docs/design/architecture/data/service-inventory.json
docs/design/architecture/service-inventory.md
```

It includes the phase-aware tests, runbook, release record, baseline, helpers
and queued STAGE manifest. Inventory still describes the previous deployed
release. Applied manifests 0033/0034 and Compose remain unchanged.

Use a clean assembly branch from current main, keeping the mission checkout
intact. Set `BASE` to the reviewed mission/main merge base and `CAND` to the
reviewed candidate. In that assembly checkout, use the same array for assembly
and verification:

```bash
CUTOVER=(
  deploys/queued/vikunja-release-activate.yaml
  docs/design/architecture/data/service-inventory.json
  docs/design/architecture/service-inventory.md
)
EXCLUDE=()
for p in "${CUTOVER[@]}"; do EXCLUDE+=(":(exclude)$p"); done
git -C "$REPO" diff --binary "$BASE" "$CAND" -- . "${EXCLUDE[@]}" | git apply --index
git diff --cached --name-only -- "${CUTOVER[@]}"
diff <(git -C "$REPO" diff --name-only "$BASE" "$CAND" -- . "${EXCLUDE[@]}" | sort) \
     <(git diff --cached --name-only | sort)
git diff --cached --exit-code -- services/vikunja/docker-compose.yml deploys/applied/0033-vikunja-release-stage.yaml deploys/applied/0034-vikunja-release-activate.yaml
```

Use `set -o pipefail`; any apply conflict or difference stops assembly.
The cutover-path command must print nothing and the sorted path comparison
must match exactly. Review the actual content diff and executable modes too.
After the assembly commit, repeat these checks against
`git diff origin/main HEAD`, not an empty index. Constants/existence tests
alone do not prove PR contents. Run the focused phase tests, full non-live
suite and doc validator in the actual PR1 tree before pushing/opening its PR.

### 4b. Apply and verify STAGE (Agent / merge authority)

Merge PR1 after review and green CI. The deployer runs the tier-2 backup gate,
STAGE pre-verification, dry run, apply and image postchecks. It then moves the
manifest to an applied record and rebaselines `docker-images.txt`
(deferred-confirm). Record the actual rebaseline outcome.

Require the applied STAGE record for the **current** release, successful
postchecks of its new local release tag/config and retained rollback ref/ID.
Inspect the running container and API: both still match the rollback identity.
An existing active tag is retained. A tagged archive may also retain its
imported tag; that does not replace local release/rollback keeper refs.
Do not select historical 0033 as evidence of current STAGE.

## 5. Readiness and preflight before any outage (Agent)

Do these in order after current STAGE is applied:

1. Check notification disposition for the subscription backfill. Proceed if
   only Kent can be notified, or mail is off and nothing reacts. Ask Kent first
   if anybody else could be notified or an automation cannot be paused.
2. Confirm a Restic backup at most 24 hours old and record evidence privately.
3. Pause the Felix crons identified in the private packet and
   `felix-vikunja-sync.timer`. Keep writes closed through acceptance.
4. Re-run candidate ACTIVATE dry-run. Require
   `ACTIVATE_DRY_RUN_READY`, all preconditions MET and the new marker ABSENT.
5. On Office2 as `claude`, from the candidate root, run:

```bash
python3 scripts/vikunja/preflight_release_baseline.py services/vikunja/release.json
```

Require exit 0 and `PREFLIGHT_OK`. Comparison must fit within 25 seconds;
consolidation plus comparison must fit within 90 seconds. Otherwise the helper
returns `PREFLIGHT_OVER_BUDGET`. These limits leave room for the durable receipt
within the gate's 30 seconds, the readiness poll's 180 seconds and Docker work
inside the 300-second total outage. Record the timing privately before any go.

Preflight takes a B3 stable double copy, consolidates in private storage and
runs the shared comparison. It removes its copies on exit and supplies no
receipt that ACTIVATE trusts. `PREFLIGHT_COPY_UNSTABLE` after five rounds is
**inconclusive**: locate the writer and obtain a pass before proceeding.
A mismatch, over-budget result or cleanup failure stops the cutover. Do not
treat an unstable copy as either a baseline match or mismatch.

After these checks, send the lead a one-line handoff recording current STAGE
applied, notification disposition accepted, backup fresh, writers paused,
preflight passed within budget and ready for PR2. Keep private values out of
that handoff. PR2 must not merge before it.

## 6. PR2: ACTIVATE (the cutover)

### 6a. Exact assembly and go

**Agent**: prepare a separate branch from main after PR1 merges and STAGE and
section 5 pass. It adds **exactly** the three WP07 paths above. No Compose,
test, helper, release-record or baseline change belongs in PR2.

```bash
git checkout "$CAND" -- "${CUTOVER[@]}"
diff <(printf '%s\n' "${CUTOVER[@]}" | sort) \
     <(git diff --cached --name-only | sort)
git diff --cached --exit-code -- services/vikunja/docker-compose.yml
```

Review content, commit through the approved workflow and repeat the exact path
comparison against `git diff origin/main HEAD`. Run the phase tests and full
suite on this ACTIVATE tree. Only then open the PR with approved copy.
The merge authority records the explicit go for the agreed window after CI
and independent review pass. The merge is the production decision.

### 6b. Gate and output

The deployer runs backup and dry-run checks, then ACTIVATE holds the shared
`activation.lock`, records its marker, stops Compose, removes active,
proves no container, snapshots and records `snapshotted`. It then loads the
bound baseline, compares the private snapshot and fsyncs the private receipt
**before** tagging active or starting the new image.

The gate has `min(30 seconds, remaining outage)`; all outage work, including
the readiness poll and migration-log check, has at most 300 seconds.
`ACTIVATE_OUTAGE_DEADLINE` takes precedence when the overall limit expires.
There is no new marker phase.

A gate failure records `phase=snapshotted`, `failed_phase=retagged`,
`outcome=failed`, and the stable gate error. No release tag selection or
new container start follows. Recovery is section 9's snapshot rollback,
**never** `--recover-pre-snapshot`.

The snapshot directory is obtained privately from the release-specific marker.
`snapshot.json` and `vikunja.db` are accompanied by `baseline.json`:
the durable gate receipt binding snapshot/baseline/release identity, migrations,
schema, task/repeat evidence and expected subscriptions. Directories are 0700,
receipts 0600, exclusively created and fsynced with their parent.

Public output uses stable status codes:
`ACTIVATE_SNAPSHOT status_code=PERSISTED`,
`ACTIVATE_LOGS status_code=CAPTURED`,
`ACTIVATE_MIGRATION status_code=VERIFIED`, and `ACTIVATE_VERIFIED`.
It does not print snapshot locations, hashes, counts, log paths or elapsed
outage. Obtain private details from the marker, receipts and private logs;
never expect the former conversion summary in deploy output.

On failure, inspect `ACTIVATE_FAILED_AT`, the marker and
`ACTIVATE_CLEANUP`. Only `lock_code=HELD container_code=ABSENT` confirms the
startup lock and absent container. `NOT_CONFIRMED`, PRESENT or UNKNOWN means
cleanup is incomplete: stop and inspect. Never assume cleanup succeeded.
Never blindly retry a one-shot marker or remove it.

## 7. Acceptance with writes closed

**Agent**: verify A1 exact API version, A2 exact container config plus exactly
one container in the existing Compose project, and A3 structured startup logs.
The required INFO message is exactly `Ran all migrations successfully.`;
unstructured text or a containing substring is insufficient. A completed
historical repeat conversion is not required to emit a new conversion summary.

Run A1/A2 from the reviewed root on Office2, using the record as the public
identity oracle. Every command must exit 0:

```bash
REC=services/vikunja/release.json
curl -fsS --max-time 5 "$(jq -r .service.info_url "$REC")" \
  | jq -e --arg expected "$(jq -r .release_version "$REC")" '.version == $expected'
docker inspect "$(jq -r .service.container "$REC")" --format '{{.Image}}' \
  | grep -qx "$(jq -r .image.config_digest "$REC")"
test "$(docker ps -a --filter "label=com.docker.compose.project=$(jq -r .service.project "$REC")" --format '{{.Names}}')" = "$(jq -r .service.container "$REC")"
```

Use `set -o pipefail`. For A3, read the `verify_log` named in the current
release marker privately; retain the structured migration-success evidence
and check for startup errors. Do not paste raw container logs into the PR.

**B3: stable double copy.** Copy the live `vikunja.db` and, if present, its
`-wal` into a new private 0700 destination; hash both files. Repeat into a
second new private destination and compare file-name sets and hashes. Accept
only equal rounds, otherwise discard only these disposable copies and retry,
at most five times. Never copy `-shm`; SQLite rebuilds the WAL index. Never
open the live database with SQLite or use `immutable=1` on a WAL database.
An unstable copy means writes are not closed: stop and find the writer.

**Agent**, from the candidate root on Office2, run this B3 copy procedure in a
private operator terminal. Its one output is a private copy location, never
deployer output or committed evidence:

```bash
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

os.umask(0o077)
record = json.loads(Path("services/vikunja/release.json").read_text())
source = Path(record["service"]["data_dir"])
root = Path(record["roots"]["private_logs"])

def take():
    folder = Path(tempfile.mkdtemp(prefix="acceptance-copy-", dir=root))
    try:
        names = ["vikunja.db"]
        if (source / "vikunja.db-wal").exists():
            names.append("vikunja.db-wal")
        for name in names:
            shutil.copyfile(source / name, folder / name)
        hashes = {}
        for name in names:
            with (folder / name).open("rb") as stream:
                hashes[name] = hashlib.file_digest(stream, "sha256").hexdigest()
        return folder, hashes
    except BaseException:
        shutil.rmtree(folder)
        raise

for attempt in range(5):
    first = second = None
    keep = False
    try:
        first, hashes = take()
        second, repeated = take()
        if hashes == repeated:
            keep = True
            print(first / "vikunja.db")
            break
    except FileNotFoundError:
        pass
    finally:
        if second is not None:
            shutil.rmtree(second)
        if first is not None and not keep:
            shutil.rmtree(first)
else:
    raise SystemExit("B3_COPY_UNSTABLE")
PY
```

Retain the accepted copy until verification and Kent's decision. If a check
fails, keep the first evidence; do not erase it to manufacture a passing retry.

**B4: reviewed acceptance verifier.** On Office2 from the reviewed candidate
(or matching PR1 checkout), set `SNAPSHOT` privately from the current marker
and `POST_DB` to the accepted B3 copy's `vikunja.db`. Pass the file, not
the copy directory:

```bash
python3 scripts/vikunja/verify_release_upgrade.py "$SNAPSHOT" "$POST_DB"
```

The verifier consolidates a present WAL in disposable private storage itself.
Do not manually open or mutate the B3 copy beforehand. Require exit 0 and
all per-check `ACCEPTANCE_*_PASS` codes. It checks exact preservation of
pre-upgrade migration IDs (including `SCHEMA_INIT`), exactly the reviewed
baseline's added IDs (including an empty list), target schema, task count,
repeat count/hash, integrity `ok`,
expected task subscriptions, no missing eligible pairs, unchanged duplicate
excess and preserved existing keys/muted choices.

Aggregates stay in the create-only `upgrade-acceptance.json` under the snapshot
directory for Claude to report privately to Kent. Running again on that same
snapshot fails with `ACCEPTANCE_EVIDENCE_WRITE_FAILED`. Read the first evidence
or take a newly reviewed approach; **do not delete the evidence** to retry.
The durable gate receipt also remains untouched. A failure keeps writes closed.

Only after A1–A3, B3 and B4 and this verifier pass may **Kent** perform the
disposable write probe, plus browser/login/task-list and read-only recurrence
checks. Login can create session rows. The probe is soft-deleted, so deleting
it does not undo the post-snapshot write or make rollback lossless.

Kent records **ACCEPT** or **ROLLBACK**. Keep crons and the sync timer paused
until ACCEPT; only then reopen writes and resume them. Preserve snapshots and
receipts per the private packet's retention decision. Remove only the reviewed
candidate/disposable-copy destinations when authorized.

## 8. Residual crash risk

A crash after retag can let systemd restart the unverified new release on its
upgraded database. The snapshot and gate receipt already exist; they protect
the restore point, not verification of that restarted service. Inspect the
marker and image, finish acceptance or roll back. Do not claim that reboot
cannot start an unverified release.

A crash before `snapshotted` is recorded can leave phase `started` or
`stopped` with outcome null. It has a supported pre-snapshot recovery path
(section 9a), including a crash between Compose down and active removal.
Never restart the previous image on a database a new image may have touched.

## 9. Snapshot rollback (Agent / Kent)

Use for any gate failure, any marker at `snapshotted` or later, or rejected
acceptance. The helper uses the live PR1 checkout at `/home/claude/kg-automation` (run `rollback_release.py` from there) and both deployer and activation
locks. Busy locks refuse before Docker calls; wait for the owning operation.
Set `SNAPSHOT` only to the current marker's private snapshot directory.
On Office2 as `claude`:

```bash
python3 scripts/vikunja/rollback_release.py --snapshot "$SNAPSHOT" --dry-run
python3 scripts/vikunja/rollback_release.py --snapshot "$SNAPSHOT" --prepare
```

Prepare captures private logs, stops Compose, removes active, preserves the
failed database privately and counts post-snapshot writes on copies. The
private prepare receipt labels the subscription backfill as included; it is
not subtracted. Edits to `repeats`, server rows, logins and probes count.
This is a conservative write-loss acknowledgement, not just a task count.

**Kent** dispositions those writes in writing, then executes the exact privileged
restore command printed by prepare through `office2-kgale`. It installs the
snapshot with the required ownership/mode and removes live WAL/SHM. Agents
never perform that restore. Confirm no container and no active tag before it.

**Agent**, only after Kent's restore and acknowledgement, with `ACK` equal
to the prepared count:

```bash
python3 scripts/vikunja/rollback_release.py --snapshot "$SNAPSHOT" --finish --ack-post-cutover-writes "$ACK"
```

Finish requires no container, active absent, no WAL/SHM, exact restored snapshot
hash and exact snapshot `pre_version` equal to the rollback version derived
from the reviewed ref (prepend v only if absent). A preexisting RRULE schema
is valid; there is no broad version or unmigrated-schema fallback.
It then tags active to the exact rollback ID, starts with the systemd unit's
Compose argv, verifies exact previous version and records `rolled_back`.

If start/readiness fails, cleanup is best effort. Check container absence and
active absence before Kent restores **again**, then retry finish only after
the cause is understood. Do not rerun prepare: `ROLLBACK_ALREADY_PREPARED`
means use its existing evidence. The previous image may have written the
restored database, so the exact hash guard intentionally refuses a blind retry.

For incomplete cleanup, stop Compose with the unit's own argv. Inspect active's
ID and all RepoTags. Remove **only active**, and only when its ID matches a
reviewed release/rollback identity and the matching local release/rollback
keeper ref also exists. Never remove by image ID. If a container survives or
the proof fails, stop; Kent decides. Never restore into a running service.

`MARKER_DURABILITY_UNCERTAIN` after a verified rollback means the service is
up and the marker reads rolled_back, but its final durability step failed.
Confirm the marker read-only, record the event for Kent and perform the printed
follow-ups manually. Do not tear down the verified service just to repeat it.

Run the helper's manual rebaseline follow-up using
[Security Baseline Operations](<./security-baseline-ops.md>), then cancel/reconcile
the queued manifest and inventory (section 10). Writes reopen only on Kent's
decision after the exact restored version passes. Budget at most 15 minutes
from prepare to finished, including Kent's restore.

After a rollback, keep the paused crons and `felix-vikunja-sync.timer` stopped until the restored version passes its checks and Kent says to resume them.

## 9a. Failure or crash before snapshot is recorded

Run `rollback_release.py` from `/home/claude/kg-automation`, as in section 9.

Use only for phase `started` or `stopped`. A failed marker must name the
corresponding next attempted phase; an unfinished marker must have outcome
null and no failed phase. The helper checks exact release version, config,
rollback image and pre-version identity. It refuses success/rolled-back
markers and all `snapshotted` or later phases, even if retag never happened.

On Office2 as `claude`:

```bash
python3 scripts/vikunja/rollback_release.py --dry-run
python3 scripts/vikunja/rollback_release.py --recover-pre-snapshot
```

The recovery mode takes no snapshot or acknowledgement argument. Require
eligible marker, free locks and present data. It holds both locks, requires no
container and permits active only absent or still at the exact rollback image
(crash before untag). Any other active ID refuses. It preserves a private copy,
starts and verifies the exact previous version and marks rolled_back.
Existing repeats/WAL do not mean that this new release has run; there is no
legacy migration-signal rejection. No privileged restore is needed here.

On refusal stop; inspect the code and state. On post-start failure check cleanup
before considering recovery again. Never retire a marker to bypass a guard.
Durability uncertainty and manual rebaseline follow-ups are the same as section 9.

## 10. Cancel and authorized retry

A failed/unfinished marker prevents another stop/start on subsequent ticks.
A rolled-back marker returns `ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST`.
Queued manifests continue generating failure alerts until reconciled.

**Kent / merge authority**: cancel through a reviewed commit deleting the queued
ACTIVATE and restoring inventory to the actual previous deployment. Compose
stays on active/never. Keep marker, snapshots, gate receipt and acceptance
evidence. If ACTIVATE already applied, reconcile inventory and the phase tests
explicitly in that follow-up; applied history cannot describe the rollback as
a currently running new release. Do not conceal that state by selecting 0034.

Retry needs Kent's separate explicit go, verified full rollback, and understood
failure cause. Only then may the agent archive the **new release's** rolled-back
marker to a unique retired name without overwrite; keep the earlier successful
release marker. If ACTIVATE is still queued, retiring starts the next attempt
on the next tick. If cancelled or already applied, a separately reviewed requeue
PR is required. Repeat section 5 before the new go. A retry takes a fresh
snapshot and every acceptance input binds to it.

## 11. Tagged STAGE partial-failure cleanup

`docker load` can import a tag before subsequent identity/fact verification
fails. The image is not necessarily untagged. Do not follow historical 0033's
image-ID removal advice on the repeat route.

**Agent**: inspect the specific imported tag named by the reviewed archive and
its resolved config ID/RepoTags. Compare with the archive and release record;
inspect containers and verify local release and rollback keeper refs survive.
If the imported tag is unexpected or collides with a keeper, stop for review.
When cleanup is authorized, remove **only that exact imported tag**, preserving
all local release/rollback refs, active and containers. Never blindly run
`docker image rm <image-id>`; it could delete the retained rollback image.

An untagged load also requires identity, reference and container review before
any deletion is authorized. Rebaseline out-of-band changes using section 9's
follow-up. Preserve logs and report cleanup failures. The queued STAGE retries
on every tick, so understand the cause or cancel its queue entry through a
reviewed PR before retrying. A matching already-staged release tag is reverified.

## 12. Stable refusal codes

Deployer-retained ACTIVATE output contains stable codes only. Locate raw logs
privately using the configured roots and marker; do not expect a public
`private_log=` path. Any unexpected result stops the sequence.

| Code | Action |
|---|---|
| `PREFLIGHT_COPY_UNSTABLE` | Inconclusive; find the writer and obtain a stable passing preflight. |
| `PREFLIGHT_OVER_BUDGET` | Comparison exceeded 25 seconds or consolidation plus comparison exceeded 90; no outage go. |
| `PREFLIGHT_FAILED`, `PREFLIGHT_CLEANUP_FAILED` | Stop and inspect privately; cleanup must finish safely. |
| `GATE_BASELINE_UNREADABLE` | Missing, malformed, unbound or identity-mismatched baseline; stop. |
| `GATE_MIGRATIONS_MISMATCH`, `GATE_SCHEMA_MISMATCH`, `GATE_AGGREGATE_FAILED` | Comparison refused; before outage stop, at gate use snapshot rollback. |
| `GATE_RECEIPT_WRITE_FAILED`, `GATE_DEADLINE` | Snapshot gate failed before image selection; section 9. |
| `ACTIVATE_OUTAGE_DEADLINE` | Overall 300-second limit expired; inspect marker to choose section 9 or 9a. |
| `ACCEPTANCE_*_FAIL`, `ACCEPTANCE_RECEIPT_FAILED`, `ACCEPTANCE_COMPUTE_FAILED`, `ACCEPTANCE_FAILED`, `ACCEPTANCE_CLEANUP_FAILED` | Keep writes closed; inspect private evidence and bring Kent the result. |
| `ACCEPTANCE_EVIDENCE_WRITE_FAILED` | Create-only evidence exists or cannot be written; read first evidence, never delete to retry. |
| `INGRESS_DEST_EXISTS`, `INGRESS_DEST_FILE_EXISTS` | Do not overwrite; inspect only this ingress destination (section 3). |
| `ARCHIVE_MISSING`, `ARCHIVE_*_MISMATCH`, `ARCHIVE_UNREADABLE` | Establish exact reviewed archive before loading. |
| `STAGE_IMPORT_TAG_CONFLICT`, `STAGE_IMPORT_CLEANUP_REQUIRED`, `STAGE_LOADED_ID_UNEXPECTED`, `STAGE_VERIFY_FAILED` | Inspect imported tag and keepers; section 11, no image-ID cleanup. |
| `STAGE_RELEASE_TAG_UNEXPECTED`, `STAGE_ACTIVE_UNEXPECTED`, `STAGE_ROLLBACK_IMAGE_MISSING`, `STAGE_ROLLBACK_IMAGE_UNEXPECTED` | Stop; record and local Docker identities disagree. |
| `ACTIVATE_PRECONDITIONS_UNMET`, `PRE_COMPOSE_NOT_ACTIVE`, `PRE_VERSION_UNREADABLE` | Stop; existing Compose and exact previous version must pass on repeat cutover. |
| `ACTIVATE_PRIOR_ATTEMPT_<PHASE>` | No blind replay; inspect marker and choose section 9 or 9a. |
| `ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST` | Cancel or explicitly authorize retry (section 10). |
| `ACTIVATE_UNTAG_UNSAFE`, `ACTIVE_TAG_UNEXPECTED`, `ACTIVE_UNTAG_FAILED`, `CLEANUP_*` | Do not assume the startup lock; inspect container, active and keeper refs. |
| `ROLLBACK_DEPLOYER_BUSY`, `ROLLBACK_ACTIVATION_RUNNING`, `ACTIVATE_LOCK_BUSY` | Wait for the owner; never delete a lock file. |
| `ROLLBACK_ACK_MISMATCH` | Kent must acknowledge exactly the prepared conservative write count. |
| `ROLLBACK_ALREADY_PREPARED`, `ROLLBACK_NOT_PREPARED` | Follow prepare/restore/finish ordering; do not replace evidence. |
| `GUARD_SHA_MISMATCH`, `GUARD_SIDECAR_PRESENT` | Prove no writer, then Kent restores the snapshot and removes WAL/SHM again. |
| `GUARD_PRE_VERSION_MISMATCH` | Snapshot pre-version differs from exact reviewed rollback version; stop. |
| `GUARD_CONTAINER_PRESENT`, `GUARD_LOCK_NOT_HELD` | Something started or active was recreated; stop before restore. |
| `RECOVER_MARKER_PAST_RETAG` | Includes snapshotted gate failure; section 9, never pre-snapshot recovery. |
| `RECOVER_MARKER_IDENTITY_MISMATCH`, `RECOVER_MARKER_NOT_FAILED`, `RECOVER_MARKER_MISSING` | Marker is ineligible; do not edit or retire it to bypass checks. |
| `RECOVER_CONTAINER_PRESENT`, `RECOVER_LOCK_NOT_HELD`, `RECOVER_ROLLBACK_IMAGE_MISSING` | Inspect state and exact previous identity; no blind cleanup. |
| `MARKER_DURABILITY_UNCERTAIN` | Confirm verified service and rolled-back marker; record event and finish follow-ups. |

Other `FAILED code=<code>` results remain refusals. Preserve the first evidence,
consult the matching helper and bring unexpected failures to the lead.

## Historical first cutover (reference only)

Applied `0033-vikunja-release-stage.yaml` and
`0034-vikunja-release-activate.yaml` are immutable records, identified explicitly
by filename and issue identity (see #1087). The original Compose two-line
reversal test and frozen first-cutover fixture preserve that contract.
They are not evidence that a new STAGE or ACTIVATE has applied.

The first cutover introduced RRULE storage and used Ring 4 legacy originals,
per-task expected rules, the backup table and a conversion summary to qualify
that one-time migration. The repeat route preserves existing rules and checks
the newly reviewed migrations/schema and subscription backfill. It does not
rerun conversion or require historical converted-row counts. Historical
first-install assumptions about absent roots, active tag or old Compose must
never be executed as current preconditions.

## Related documents

- [Vikunja Operations](<./vikunja-ops.md>): day-to-day service operations.
- [Deploy Discipline](<./deploy/discipline.md>): manifest pipeline and one-shot operations.
- [Security Baseline Operations](<./security-baseline-ops.md>): automatic/manual rebaseline.
- [Vikunja Downstream Development and Releases](<./vikunja-downstream-releases.md>): qualification and published artifacts.
