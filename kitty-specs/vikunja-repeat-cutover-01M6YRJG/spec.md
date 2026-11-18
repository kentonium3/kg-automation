# Mission Specification: Vikunja repeat cutover support

**Mission Branch**: `fix/vikunja-repeat-cutover`
**Created**: 2026-11-08
**Status**: Draft
**Input**: Kent confirmed the intent summary and requirement set on 2026-11-08 (decision 01M6YRJZXFHYBYXZCV72ZR6FW8). Tracking: see #1095. Follow-up to #1087.

## Intent Summary

The deployer and Claude run a second Vikunja cutover on Office2, triggered by STAGE and ACTIVATE merges made by Kent or the program lead. Office2 moves from `v2.7.1-670-420c7bcb75` to the published `v2.8.0-rrule.2`, with a verified restore point and a rollback that works. The new image never starts unless the snapshot and its checks have passed, and the previous image never starts on an upgraded database.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stage the published release (Priority: P1)

The operator stages the exact published release archive on Office2 while the running service stays untouched.

**Why this priority**: Without this, the release cannot reach Office2 at all; today the route rejects the version and the archive.

**Independent Test**: Run the stage path against a fixture archive shaped like the published one and confirm it verifies the bytes, loads the image and records its identity.

**Acceptance Scenarios**:

1. **Given** a release record for `v2.8.0-rrule.2` and the published gzip archive, **When** STAGE runs, **Then** the archive's exact bytes are verified against the record and the loaded image identity matches the record.
2. **Given** an archive whose bytes differ from the record, **When** STAGE runs, **Then** it stops before loading anything.
3. **Given** a malformed version string in the record, **When** any route step validates it, **Then** the step refuses it.

---

### User Story 2 - Activate only behind a verified restore point (Priority: P1)

ACTIVATE stops the old service, takes the write-boundary snapshot, proves the snapshot and the database it came from are what the release was qualified against, and only then selects and starts the new image.

**Why this priority**: The migrations are one-way, so a start without a proven restore point cannot be undone.

**Independent Test**: Run ACTIVATE's gate against fixture snapshots that match and do not match the qualified baseline; confirm the image selection changes only in the matching case.

**Acceptance Scenarios**:

1. **Given** a snapshot matching the baseline, **When** ACTIVATE reaches the gate, **Then** the private receipt is durably recorded before the image is retagged.
2. **Given** a snapshot with a missing, extra or different migration ID, a schema difference, or a receipt that cannot be written, **When** ACTIVATE reaches the gate, **Then** it stops, the new image is not selected, and the marker records why.

---

### User Story 3 - Roll back to the snapshot (Priority: P1)

After a failed or rejected cutover, Claude and Kent restore the write-boundary snapshot and bring the previous image back.

**Why this priority**: Today the route refuses to restore the correct snapshot, so the safety net Kent is relying on would fail when needed.

**Independent Test**: Run the rollback path against a restored fixture matching the snapshot and against one that differs.

**Acceptance Scenarios**:

1. **Given** a restored file whose hash equals the snapshot's and a snapshot whose recorded previous version equals the rollback version, **When** the finish step runs, **Then** it proceeds, even though the database has the RRULE schema.
2. **Given** a restored file with a different hash, or a snapshot from another version, **When** the finish step runs, **Then** it refuses and does not start the previous image.
3. **Given** a stop before any snapshot exists, **When** pre-snapshot recovery runs, **Then** it decides from the activation marker alone.
4. **Given** edits to `repeats` after the snapshot, **When** the write count is produced, **Then** they are counted, and the subscription backfill is labelled in the receipt.

---

### User Story 4 - Accept the cutover (Priority: P2)

With writes closed, Claude runs a reviewed acceptance procedure and reports aggregates to Kent, who decides ACCEPT or ROLLBACK.

**Why this priority**: Kent's decision depends on evidence that data survived, but the decision can follow the cutover.

**Independent Test**: Run the procedure on fixture snapshot and post-upgrade pairs, including ones with a lost migration, changed repeat rule or wrong subscription count.

**Acceptance Scenarios**:

1. **Given** an upgraded copy, **When** the procedure runs, **Then** it passes only if all pre-upgrade migration IDs remain, exactly the ten reviewed IDs were added, repeat count and hash match the snapshot, integrity is `ok`, and subscriptions equal the computed expectation.

---

### Edge Cases

- The archive carries an embedded `kentonium3/vikunja:v2.8.0-rrule.2` tag, so "loaded untagged" no longer holds; cleanup and rollback must not treat that tag as stray or remove the wrong image.
- The previous successful marker for `v2.7.1-670-420c7bcb75` remains on disk and must not block the new release; the new release's marker must be absent.
- Existing subscription duplicates are not removed by the migration, so acceptance compares against a baseline rather than assuming zero.
- A crash after retag can restart an unverified new image; the snapshot already exists by then.
- The earlier RRULE repeat conversion is complete and must not be required to run again.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status | Delivery | No-op passable? |
|----|-------|------------|----------|--------|----------|-----------------|
| FR-001 | Accept rrule release versions | As the operator, I want `vX.Y.Z-rrule.N` accepted everywhere the route validates a version, and malformed versions still refused, so that this release can pass through the route. | High | Open | [build] | no |
| FR-002 | Accept the gzip release archive | As the operator, I want the gzip archive accepted while the exact published bytes stay pinned, so that what runs is what was published. | High | Open | [build] | no |
| FR-003 | Handle tagged image load | As the operator, I want tagged image-load output handled, the loaded identity verified and the imported tag accounted for in cleanup, so that the wrong image cannot be selected or removed. | High | Open | [build] | no |
| FR-004 | Rollback restore criterion | As Kent, I want a restore accepted when the restored file's hash equals the snapshot's and the snapshot's previous version equals the rollback version, so that a valid restore is not refused. | High | Open | [build] | no |
| FR-005 | Pre-snapshot recovery criterion | As Kent, I want pre-snapshot recovery decided from the activation marker, including a marker left unfinished by a crash before the snapshot phase is recorded, so that it works when no snapshot exists and the service is not stranded. Crash case added 2026-11-08 from the post-plan review. | High | Open | [build] | no |
| FR-006 | Complete post-snapshot write count | As Kent, I want `repeats` edits counted as post-snapshot writes and the subscription backfill labelled in the receipt, so that my write-loss decision is accurate. | High | Open | [build] | no |
| FR-007 | Exact previous version on rollback | As Kent, I want rollback to require the snapshot's exact previous version with no broad version fallback, so that a snapshot from another version cannot be restored. | High | Open | [build] | no |
| FR-008 | Fail-closed gate before image selection | As Kent, I want ACTIVATE to stop before selecting the new image unless the snapshot receipt, exact pre-upgrade migration IDs, schema identity, repeat count and hash, and expected subscription count are privately recorded, so that the new image never starts without a proven restore point. | High | Open | [build] | no |
| FR-009 | Acceptance procedure | As Kent, I want a reviewed procedure checking the ten expected new migrations, repeat preservation, integrity and subscriptions, so that I decide ACCEPT or ROLLBACK on evidence. | High | Open | [build] | no |
| FR-010 | STAGE change set | As the operator, I want the release record, queued STAGE manifest and updated change-set tests for `v2.8.0-rrule.2`, so that the merge carries exact release identities. | High | Open | [build] | no |
| FR-011 | ACTIVATE change set | As the operator, I want the ACTIVATE manifest and inventory updates prepared in this mission and delivered as a second change once STAGE applies, so that the cutover is a separate decision. | High | Open | [build] | no |
| FR-012 | Repeat-cutover runbook | As the operator, I want the cutover runbook to describe repeat cutovers, so that the historical first-cutover values are not executed. | Medium | Open | [build] | no |
| FR-014 | Documentation synchronisation | As the operator, I want the architecture JSON and its markdown view, the cutover runbook, and INDEX and roadmap status kept consistent with the change, so that the docs describe what is deployed. INDEX and roadmap need an update only if the implementer finds an entry affected; otherwise the WP records that none was. Added 2026-11-09 from the readiness analysis. | Medium | Open | [build] | no |
| FR-013 | Baseline preflight before the outage | As Kent, I want the gate's baseline comparison run on a private copy of the live database after STAGE and before ACTIVATE, so that a baseline mismatch is found while the service is still running. Added 2026-11-08, planning decision 01M6Z0BCB1XHDQ4MZ14PYBA1P6. | High | Open | [build] | no |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Outage limit | The added gate keeps the total ACTIVATE outage within the existing 300-second limit, including the 180-second readiness poll, and adds at most 30 seconds on a database of the deployed size. | Performance | High | Open |
| NFR-002 | Private evidence | Zero production rows, per-task values, aggregate values, snapshot paths or times appear in git or in deployer output retained in git. | Security | High | Open |
| NFR-003 | Fail closed | In 100% of tested gate failures the new image is not selected and the marker records the failing check. | Reliability | High | Open |
| NFR-004 | History preserved | 100% of existing first-cutover route tests that still describe valid behaviour keep passing. | Reliability | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | No Compose change | The service keeps selecting `office2.local/vikunja:active` with `pull_policy: never`. | Technical | High | Open |
| C-002 | Tier and audit kept | Both new manifests stay tier 2 with audited surface and pre and post verification. | Technical | High | Open |
| C-003 | History untouched | Applied manifests 0033 and 0034 and the earlier activation marker are not modified. | Technical | High | Open |
| C-004 | No repeat conversion requirement | The route does not require the completed repeat conversion to run again. | Technical | High | Open |
| C-005 | Live database access | The gate reads only the private snapshot; no check opens the live database for writing. | Technical | High | Open |
| C-006 | Review independence | The model that implements a change does not review it. Codex implements the code packages, Claude Opus 5.5 implements the baseline package because its inputs are private, and Claude Sonnet reviews. | Process | High | Open |
| C-007 | Merge authority | Changes go by PR. Kent, the program lead, or the core worker under Kent's 2026-11-08 delegation merges them once review and CI pass. | Process | High | Open |

### Key Entities

- **Release record**: the trust root naming the release and rollback versions, archives, hashes, sizes and image identities.
- **Activation marker**: the durable per-release record of cutover phase and outcome.
- **Write-boundary snapshot**: the consolidated database copy and its record, taken after the service stops and before the new image starts.
- **Baseline receipt**: the private record of the snapshot's migration set, schema identity and data aggregates.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fixture shaped like the published release passes STAGE, and each altered-byte, wrong-identity and malformed-version variant is refused. — [build] · no-op passable: no
- **SC-002**: The new image is selected in 0 of the tested gate-failure cases and in the one matching case. — [build] · no-op passable: no
- **SC-003**: A correct snapshot restore is accepted and every wrong-hash or wrong-version restore is refused. — [build] · no-op passable: no
- **SC-004**: The acceptance procedure passes a correct upgrade and fails each seeded data-loss case. — [build] · no-op passable: no
- **SC-005**: After the change, Office2 can complete STAGE and ACTIVATE for `v2.8.0-rrule.2` within the 300-second outage limit. — [build] · no-op passable: no

## Assumptions

- The published archive keeps its inspected shape: one outer index descriptor and one manifest entry.
- The previous image remains in Office2's Docker store, so the rollback archive is used only by ingress.
- Verifying the index-to-manifest-to-config chain explicitly is a follow-up, as the current archive already passes the existing checks.
