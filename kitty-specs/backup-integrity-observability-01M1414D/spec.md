# Mission Specification: Backup Integrity Observability

**Mission Branch**: `feat/backup-integrity-observability`
**Created**: 2026-08-28
**Status**: Draft
**Input**: Issues #902 (second half), #903, #906 — three defects sharing one shape: the mechanism meant to make a failure visible did not.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Notice when retention silently stops (Priority: P1)

On 2026-08-27 a stale lock blocked `restic forget --prune` for ten hours across
three snapshot cycles. Every health surface reported the backup healthy the whole
time, correctly — because the backup *was* healthy. Only the prune had failed,
and nothing recorded that. The operator wants a prune failure to be as visible as
a backup failure.

**Why this priority**: retention silently not running is a slow disk-exhaustion
failure with no alarm. It was found by accident, during unrelated work.

**Independent Test**: Construct a state pointer representing a successful backup
whose prune failed, and confirm the health surface reports it unhealthy. Today
that pointer cannot even be constructed, because the field does not exist.

### User Story 2 - Trust that the deployed backup script is the one in the repo (Priority: P2)

The operator edits `scripts/office2/restic-backup.sh` and wants to know whether
the change actually reached the host. Today nothing compares the two; #889
changed the repo copy with no manifest and the live file was installed by hand.
They currently match, which is luck rather than enforcement.

**Why this priority**: this is the delivery path for User Story 1. A prune fix
that never lands on the host is worse than no fix, because the repo then asserts
a protection that does not exist.

**Independent Test**: Point the comparator at a deliberately altered copy and
confirm it reports drift; point it at the real pair and confirm it reports match.

### User Story 3 - Recover the crontab without hand-typing an incantation (Priority: P2)

During an incident the operator restores the captured crontab and reinstalls it.
The documented procedure strips the provenance header with a hand-written `grep`
pattern that no longer matches the header the capture writes.

**Why this priority**: the failure lands exactly when the operator is under
pressure and least able to debug their recovery tool.

**Independent Test**: Emit the body from a captured artifact and confirm it is
byte-identical to the original `crontab -l` input, with no hand-written pattern
anywhere in the path.

### Edge Cases

- **The script dies between backup and prune.** The pointer must not read as a
  clean prune; "not attempted" and "attempted and succeeded" must be
  distinguishable.
- **A new pointer field the health surface does not read.** Adding a field the
  explicit-error scan ignores produces a pointer that faithfully records the
  failure beside a health check that still reports healthy — the original defect
  with the evidence sitting unread.
- **The comparator runs while an install is mid-flight**, seeing a partially
  written file.
- **The header format changes again.** Any recovery path that re-implements
  header stripping will silently rot the same way.
- **The deployed script is unreadable to the comparator**, which must report that
  as inconclusive rather than as a match.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | Record the prune outcome | As the operator, I want each backup run to record whether retention was applied, so a prune failure is representable at all. | High | Open |
| FR-002 | Distinguish not-attempted from succeeded | As the operator, I want a run that never reached the prune step to be distinguishable from one that pruned cleanly, so an aborted run cannot read as success. | High | Open |
| FR-003 | The health surface must act on it | As the operator, I want a recorded prune failure to make the component unhealthy, so the record is not merely archival. | High | Open |
| FR-004 | Detect repo/host divergence of the backup script | As the operator, I want the repo copy and the deployed copy compared, so divergence is reported rather than assumed absent. | Medium | Open |
| FR-005 | Comparator health is observable | As the operator, I want the comparator's own result surfaced through the existing health surface, including an inconclusive result when the deployed copy cannot be read. | Medium | Open |
| FR-006 | Recover without a hand-written strip | As the operator, I want the capture helper itself to emit the reinstallable body, so recovery cannot drift from the header format. | Medium | Open |
| FR-007 | Recovery procedure lives where an operator looks | As the operator, I want the crontab recovery procedure in a runbook rather than in a merged mission's planning artifact. | Medium | Open |
| FR-008 | The backup script's deploy story is written down | As the operator, I want the chosen deployment story for `restic-backup.sh` recorded, including why it stays manual. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | The new health signal can fail | Each health check added or modified is demonstrated to report unhealthy for its failure condition, exercised through the real probe rather than a reimplementation. | Observability | High | Open |
| NFR-002 | No regression to existing pointer consumers | Existing fields keep their names, types, and meanings; a pointer written before this change remains interpretable. | Reliability | High | Open |
| NFR-003 | Header round-trip is enforced by test | A change to the provenance header format that is not matched by the body emitter fails the suite. | Reliability | High | Open |
| NFR-004 | Comparator cost is negligible | The comparison completes in under 5 seconds and reads no more than the two files it compares. | Performance | Low | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | The backup script's directory must stay non-claude-writable | `/data/services/backup/scripts/` must remain `root:root` and not writable by `claude`. It holds a `NOPASSWD` sudo target, and a claude-writable directory on that path is equivalent to `NOPASSWD: ALL` — the exact defect of #899, fixed on 2026-08-27. Any deploy design that requires the pipeline to write there is therefore rejected outright. | Regulatory | High | Open |
| C-002 | Installing the backup script stays a privileged manual step | Following from C-001, the deploy story for `restic-backup.sh` is a manual `sudo install` by the operator. This mission makes divergence *visible*; it does not automate the install. | Technical | High | Open |
| C-003 | New pointer fields must be readable by the explicit-error scan | A field the scan ignores is inert. Either use a scanned key or extend the scan; adding an unread field is not an acceptable outcome. | Technical | High | Open |
| C-004 | One implementation of header stripping | The body emitter must reuse the same function the writer uses. A second implementation, in code or prose, is the defect being fixed. | Technical | High | Open |
| C-005 | Tier 3 | Helper changes, a comparator, a canary probe extension, and docs. The privileged install is the operator's step and is out of the pipeline. | Regulatory | Medium | Open |

### Key Entities

- **Backup state pointer** — `/data/services/backup/state/last-backup.json`. Gains
  a prune outcome alongside the existing backup outcome.
- **Backup script pair** — the repo copy `scripts/office2/restic-backup.sh` and
  the deployed copy `/data/services/backup/scripts/backup.sh`, which are supposed
  to be identical and are currently only incidentally so.
- **Captured crontab artifact** — carries a provenance header whose removal must
  have exactly one implementation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A backup run whose prune fails is reported unhealthy by the health
  surface, demonstrated by driving the real probe.
- **SC-002**: A run that never reached the prune step is distinguishable from one
  that pruned cleanly, and does not read as success.
- **SC-003**: Divergence between the repo and deployed backup script is detected
  and reported; an unreadable deployed copy reports inconclusive, never match.
- **SC-004**: The crontab body can be emitted for reinstallation with no
  hand-written header pattern anywhere in the path, and the result is
  byte-identical to `crontab -l`.
- **SC-005**: Changing the provenance header format without updating the emitter
  fails the test suite.
- **SC-006**: The deploy story for `restic-backup.sh` is written down, including
  the security reason it stays manual.

## Assumptions

- **Discovery was minimized** under the operator's standing instruction to drive
  the work and surface only privileged steps.
- **The operator will perform one privileged install** of the updated backup
  script. Until then the repo and host legitimately differ, and the new
  comparator is expected to report exactly that — its first act being to detect
  the change this mission itself introduces.
- **A prune failure makes the whole backup component unhealthy.** The backup may
  well have succeeded, but retention is part of the service's job and silent
  non-retention is the failure being fixed.

## Out of Scope

- Automating the install of `restic-backup.sh` (C-001, C-002).
- Changing backup schedule, retention policy, repository location, or source set.
- The stale `quickstart.md` prose in the merged #895 mission; `kitty-specs/` is
  workflow-owned. The new runbook supersedes it.
- Relocating the backup script to a claude-owned path, or narrowing the sudoers
  rule — both are Tier 0 and touch the #899 boundary.
