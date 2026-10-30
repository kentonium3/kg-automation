# Mission Specification: Vikunja image-archive staging and activation deploy route

**Mission Branch**: `feat/vikunja-image-deploy` (planning, base and merge target; nothing in this mission merges to `main`)
**Created**: 2026-10-30
**Status**: Draft
**Tracking issue**: #1087
**Input**: The Vikunja dedicated lead's assignment (bus message 374ffdde, with the ingress requirement 734fe894), the program manager's Office2 deployment handoff and `OFFICE2-ROLLOUT.md`, and Kent's answers in the specify interview (2026-10-30).

## Context

The Vikunja RRULE release (application source `420c7bcb75231be9b6571fdfdf76a1a62f2aebd8`, version `v2.7.1-670-420c7bcb75`) has passed its release suites and its production-data rehearsals (Ring 4 and Ring 5) and is built as a private image archive. Office2 runs `vikunja/vikunja:2.4.0` through `vikunja.service`, which runs Docker Compose as `claude` against the Compose file in the self-pulling `kg-automation` checkout.

The legacy `scripts/vikunja/deploy.sh` can only pull a registry image, has no archive selector and no dry-run/apply contract. The previous image change (#853, 0.24.6 → 2.4.0) was run supervised by hand. This mission gives the upgrade a governed route through the manifest pipeline instead: an inert **stage** step and a separate **activate** step, plus a scripted **rollback**.

Three host facts shape the requirements (read through `office2-claude` on 2026-10-30):

- The felix-deployer pulls `main` **before** it runs any entrypoint. A merged image-line change is therefore live in the Compose file at once, and any later restart starts the new image whether or not the activate step ran.
- A failed manifest stays queued and is **re-attempted every 5 minutes**.
- The Vikunja data folder and DB files are owned by `kgale`. `claude` can read them but cannot write them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stage the release image without touching the running service (Priority: P1)

Kent merges the stage manifest. Within one deployer tick the exact release image is loaded on Office2, verified against the identities recorded when it was built, and given a stable local name, while the running 2.4.0 service is untouched.

**Why this priority**: Every later step depends on the right image being present and proven. Staging is reversible and has no user-visible effect, so it can happen well before the cutover.

**Independent Test**: Run the stage entrypoint's dry run and apply against a fake Docker and a fixture archive; then, on Office2, run the dry run read-only and compare its report with the archive's recorded identities.

**Acceptance Scenarios**:

1. **Given** the release archive is in the ingress folder with the expected hash, **When** the stage step applies, **Then** the image is loaded, carries the stable local name, and its config digest, platform, version and user match the recorded values, and the running container, its image and the Compose file are unchanged.
2. **Given** the archive's hash differs from the recorded value, **When** the stage step runs, **Then** it refuses before loading anything and reports the mismatch.
3. **Given** the image is already staged and verified, **When** the stage step runs again, **Then** it changes nothing and succeeds.
4. **Given** the 2.4.0 rollback image is missing from Office2, **When** the stage step runs, **Then** it fails and says so.

---

### User Story 2 - Switch production to the release with a verified fallback point (Priority: P1)

On Kent's go, Kent merges the activate manifest. Within one deployer tick the service is stopped at the write boundary, a consistent copy of the database is taken and verified, the service is started on the staged image, and the result is checked. Kent gets a clear pass or fail with the evidence.

**Why this priority**: This is the production cutover, and the reason for the mission.

**Independent Test**: Run the activate entrypoint against fakes for Docker, the database files and the HTTP endpoint, covering the success path and each failure point; run its dry run read-only on Office2.

**Acceptance Scenarios**:

1. **Given** the image is staged and the Compose file names it, **When** the activate step applies, **Then** the service is stopped, the database snapshot is taken with the service stopped and passes an integrity check, the service starts on the staged image, `/api/v1/info` returns 200 with the release version, and the migration completed in the startup log.
2. **Given** the snapshot fails its integrity check, **When** the activate step applies, **Then** the service is not started on the new image and the step fails with the evidence.
3. **Given** the new service does not answer correctly within the time limit, **When** the activate step applies, **Then** it stops the new container, keeps its logs, and fails, leaving the rollback inputs ready.
4. **Given** the activate step has already run once, successfully or not, **When** the deployer re-attempts the manifest, **Then** the step does not stop or start the service again.

---

### User Story 3 - Roll back to 2.4.0 under pressure (Priority: P2)

If the release fails acceptance, Kent and the agent restore the pre-upgrade database and the 2.4.0 image with a scripted procedure and get the old service back, with the failed state kept for diagnosis.

**Why this priority**: The fallback must exist and be rehearsed before the cutover, but it runs only on failure.

**Independent Test**: Run the rollback procedure against fakes, covering the refusal to start 2.4.0 on a migrated database.

**Acceptance Scenarios**:

1. **Given** a failed cutover and a verified pre-upgrade snapshot, **When** the rollback runs, **Then** the failed database and logs are kept privately, the snapshot is restored (Kent's step), the service runs 2.4.0, and `/api/v1/info` returns 200 with version 2.4.0.
2. **Given** the database in place has already been migrated, **When** anyone tries to start 2.4.0 on it through the rollback, **Then** it refuses.

### Edge Cases

- The deployer re-runs a failed manifest every 5 minutes: stage must be idempotent, and activate must not repeat the stop/start.
- The stable local name already exists but points at a different image: stage refuses and does not retag.
- The 24-hour backup gate is stale: the pipeline's own gate refreshes it or holds the manifest; this mission does not bypass it.
- A host restart between the activate merge and the activate run would start the new image without the snapshot; the plan must bound or close this window.
- Writes accepted after the cutover cannot be silently discarded by a rollback.
- The ingress folder already exists with other content: the transfer refuses.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Requirement | Status | Delivery | No-op passable? |
|---|---|---|---|---|
| FR-001 | The stage step's dry run reports the archive's presence, size and hash, the Docker state, whether the stable local name exists and what it points at, and whether the rollback image is present, and changes nothing on the host. | Proposed | [build] | no |
| FR-002 | The stage step's apply verifies the archive hash, loads the image, gives it the stable local name, and verifies the loaded image's config digest (`sha256:35e1bc87…afba5`), platform (linux/amd64), application version (`v2.7.1-670-420c7bcb75`) and user (1000). | Proposed | [build] | no |
| FR-003 | The stage step refuses, without loading or retagging anything, on a hash mismatch, a missing archive, or a stable name that already points at a different image; it fails if any loaded identity differs from the recorded value. | Proposed | [build] | no |
| FR-004 | The stage step verifies that the rollback image `vikunja/vikunja:2.4.0` (image ID `sha256:60fe1ee8…`) is still present, and never starts, stops or recreates a container or edits the Compose file. | Proposed | [build] | no |
| FR-005 | Re-running the stage step on an already staged, verified image changes nothing and succeeds. | Proposed | [build] | no |
| FR-006 | The archive reaches Office2 through the agent's own `office2-claude` account into a create-only folder owned by `claude` with mode 0700, from the program manager's retained Office4 archives, with each archive's hash re-verified on arrival; the release archive's hash is `48008c50…1f79` and the rollback archive's is `b63e5529…a9ad`. No step reads another account's home folder. | Proposed | [build] | no |
| FR-007 | The activate change alters only the image selection in `services/vikunja/docker-compose.yml`: the `image:` line and one added `pull_policy: never` line (amended 2026-10-30, post-plan review, research R-9). Every other line (mounts, the `100.92.197.90:3456` bind, the environment including the database path, the restart policy and the container name) stays byte-identical. | Proposed | [build] | no |
| FR-008 | The activate step's dry run reports the staged image's identity, the running container and its image, the Compose file's image selection, the database files' state, the backup gate's state and free space, and changes nothing. | Proposed | [build] | no |
| FR-009 | The activate step's apply stops the service with the same Compose command and identity the service unit uses, then takes a consistent database snapshot with the service stopped into a private folder owned by `claude`, records its hash and passes an integrity check before anything starts. | Proposed | [build] | no |
| FR-010 | After the snapshot passes, the activate step starts the service with the unit's own Compose command and verifies: the container runs the staged image, `/api/v1/info` answers 200 with the release version within a bounded time, and the startup log shows the migration completed without error. | Proposed | [build] | no |
| FR-011 | If any activate check fails, the step stops the new container, keeps its logs and the snapshot, records what failed, and exits with failure; it never starts the old image on a migrated database itself. | Proposed | [build] | no |
| FR-012 | The activate step stops and starts the service at most once: a durable marker written before the first stop makes every later run, including the deployer's automatic re-attempts, report and exit without touching the service. | Proposed | [build] | no |
| FR-013 | A scripted rollback keeps the failed database and logs privately, restores the pre-upgrade snapshot (as an explicit Kent operator step, since the data folder is `kgale`-owned), returns the image selection to `vikunja/vikunja:2.4.0`, starts the service and verifies `/api/v1/info` answers 200 with version 2.4.0. | Proposed | [build] | no |
| FR-014 | The rollback refuses to start 2.4.0 when the database in place is migrated. | Proposed | [build] | no |
| FR-015 | Each step that needs Kent (the stage merge, the activate merge as the cutover go, the database restore in rollback, any `sudo` action) is written out as an explicit operator step with the exact command, and no step obtains elevated rights another way. | Proposed | [build] | no |
| FR-016 | The architecture records (`service-inventory.json` and its markdown view) state the new image and version once activated, the stale Vikunja operations runbook is corrected to describe the Compose-based upgrade route, and the deploy-discipline runbook's retry and rebaseline statements are corrected (amended 2026-10-30, research R-20). | Proposed | [build] | no |
| FR-017 | The rollback image never runs on a possibly migrated database, and nothing writes the database while the write-boundary snapshot is copied, on every startup path including the service unit at host boot. A crash after the release is selected may let the unverified release restart on its own migrated database; that residual risk is stated in the go packet (amended 2026-10-30, confirmation pass, research R-21 to R-23). | Proposed | [build] | no |
| FR-018 | Every operation the steps perform has a time limit, and the activation outage has an overall deadline matching NFR-001; exceeding it is handled as a failure with the service held down (added 2026-10-30, research R-15). | Proposed | [build] | no |
| FR-019 | Public output, markers and records carry only fixed summaries, stable error codes, identities, hashes, timestamps, counts and paths; raw command output and container logs stay in private folders (added 2026-10-30, research R-16). | Proposed | [build] | no |
| FR-020 | After a rollback or a decision not to proceed, the queued activate instruction can be cancelled through a reviewed change, and an authorized retry is a distinct, explicit operator act; a replayed success is accepted only when the running service is verifiably the release (added 2026-10-30, research R-12, R-17). | Proposed | [build] | no |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | Service outage during a successful cutover | ≤ 5 minutes from stop to a passing `/api/v1/info` check | Proposed |
| NFR-002 | Dry runs have no side effects | 0 changes to images, containers, files or the Compose selection across a dry run, checked by test | Proposed |
| NFR-003 | Automated test coverage of the entrypoints | Every FR-001…FR-014 path has at least one test, including each refusal with a same-fixture positive control | Proposed |
| NFR-004 | Time to complete a rollback once started | ≤ 15 minutes including Kent's restore step | Proposed |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Nothing from this mission merges to `main` without Kent. The stage merge is a Kent step; the activate merge is the production cutover and needs Kent's explicit go. | Active |
| C-002 | Agents use only their own accounts (`office2-claude` for Claude); never `office2-kgale` or `office2-codex`, and no account or permission change. | Active |
| C-003 | The active Compose file on Office2 is never edited in place; the image selection changes only through git and the manifest pipeline. | Active |
| C-004 | The service unit, accounts, firewall, network fabric, mounts, bind address and database location do not change. | Active |
| C-005 | The change is Tier 2 under the change-risk taxonomy, and the pipeline's 24-hour backup gate applies unmodified. | Active |
| C-006 | The image comes only from the verified archive; no registry pull and no rebuild. | Active |
| C-007 | No production rows, names or titles appear in logs, records or messages produced by these steps. | Active |

### Key Entities

- **Release archive**: the private image archive for `420c7bcb75…`; identified by its sha256, size, config digest, platform, version and user.
- **Rollback archive and image**: the `vikunja/vikunja:2.4.0` image (`60fe1ee8…`) and its archive (`b63e5529…`).
- **Stable local name**: the local image reference that the Compose file selects after activation.
- **Ingress folder**: the create-only, `claude`-owned 0700 folder on Office2 that receives the archives.
- **Pre-upgrade snapshot**: the database copy taken at the write boundary, with its hash and integrity result.
- **Activation marker**: the durable record that the activate step has started, which prevents a second stop/start.

## Success Criteria *(mandatory)*

- **SC-001**: The release image is present on Office2 with every recorded identity matching, while the running service, its image and the Compose selection are unchanged. — [build] · no-op passable: no
- **SC-002**: After the cutover, users reach the release through the existing address, with the release version reported and their data intact (task count unchanged), within the outage limit in NFR-001. — [build] · no-op passable: no
- **SC-003**: A rehearsed rollback, run against fakes, returns the service to 2.4.0 from the pre-upgrade snapshot, and the refusal on a migrated database is demonstrated. — [build] · no-op passable: no
- **SC-004**: Kent's go packet lists every operator step with an exact command, and nothing in the mission merges to `main` before he acts. — [build] · no-op passable: no

## Assumptions

- The program manager's Office4 archives are the custody source; their hashes are as recorded in the handoff.
- `claude` stays in the `docker` group on Office2, and `vikunja.service` keeps running Compose as `claude`.
- Running the service unit's own Compose commands as `claude` is the agreed way to stop and start at cutover (Kent, specify interview, 2026-10-30); `systemctl` reports the unit as active either way because it is a oneshot with `RemainAfterExit`.
- The fork CI run, the final write-boundary snapshot policy and the cutover timing stay with Kent and the program manager; this mission supplies the route and the go packet, not the go.
