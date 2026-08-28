# Mission Specification: Crontab Backup Coverage

**Mission Branch**: `feat/crontab-backup-coverage`
**Created**: 2026-08-28
**Status**: Draft
**Input**: GitHub issue #895 — "/var/spool/cron absent from restic source set; drift_check.py unregistered in service inventory", plus the pre-spec investigation recorded as issue comment 5446708916.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recover a destroyed crontab from backup (Priority: P1)

The operator discovers that the `claude` user's crontab on office2 is empty or
wrong — the schedule that runs the nightly backup, the security audit, the agent
drift check, the observation digest, and the sync heartbeat is gone. They go to
the backup, retrieve the most recent captured copy of the crontab, and reinstall
it. At no point do they depend on a file that exists for an unrelated purpose.

**Why this priority**: This is the failure that already happened on 2026-08-27.
The crontab was recoverable only from `crontabs.txt`, a security-monitor
*drift-detection* artifact, not a backup. Every other story here is prevention;
this one is the recovery path that was missing.

**Independent Test**: Destroy nothing — take the current backup, restore the
captured crontab artifact to a scratch path, and confirm it is a complete,
syntactically valid crontab matching the live one. Delivers the recovery
guarantee on its own, with no other story implemented.

### User Story 2 - Notice when a scheduled job stops existing (Priority: P2)

The operator wants a scheduled job's disappearance to be reported by a health
surface rather than inferred later from missing output. `drift_check.py` runs
daily but is absent from the service inventory, so it has no canary, no staleness
bound, and no coverage-gap signal — it stopped for roughly eight hours on
2026-08-27 and nothing would ever have said so.

**Why this priority**: A silent capability loss is worse than a loud one, but the
recovery path (Story 1) is what turns an incident into an inconvenience, so this
sits second.

**Independent Test**: Register the component, then confirm it appears in the
canary's evaluated-component count and reports healthy; separately, hold its
freshness signal past its staleness bound and confirm the canary reports it as
stale rather than silently passing.

### User Story 3 - Follow the rebaseline runbook without destroying evidence (Priority: P3)

The operator follows the documented rebaseline procedure. Its first action is
`rm /data/services/security-monitor/baselines/*`. Today that deletes
`crontabs.txt` — which, until Story 1 lands, is the only surviving copy of the
crontab. The operator should be warned, in the procedure itself, before running
the destructive step.

**Why this priority**: This is the interim guard. Once Story 1 lands the baseline
is no longer anyone's only copy, so the warning drops from load-bearing to
good-practice — but it must land *first*, because the work in Stories 1 and 2
itself edits the crontab and therefore invites a rebaseline.

**Independent Test**: Read the runbook prose and confirm the warning appears
above the destructive step in every prose copy of the procedure, and that the
machine-readable command is byte-unchanged.

### Edge Cases

- **The capture runs while the crontab is empty or absent.** It must not
  overwrite a good captured copy with an empty one; an empty crontab is
  indistinguishable from "capture ran during the destruction window".
- **The capture fails.** A failed capture that leaves a stale artifact in place
  must be observable, otherwise the artifact silently ages into uselessness and
  reads as a valid backup.
- **The capture runs after the backup.** A copy captured after the nightly
  backup does not reach the repository until the following night, silently
  widening the recovery gap by 24 hours.
- **`kgale` and `root` crontabs.** Neither is readable unprivileged and neither
  has ever been captured by any surface. Anything that claims to cover "the
  host's crontabs" while running as `claude` is making a false claim.
- **The change drifts the security baseline.** Adding or altering a scheduled job
  changes `crontabs.txt` and will alert as drift until rebaselined.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | Capture the crontab to backed-up storage | As the operator, I want the `claude` crontab written to a path the existing backup already covers, so a destroyed crontab is recoverable from a snapshot. | High | Open |
| FR-002 | Capture ahead of the backup | As the operator, I want each capture to land before the nightly backup run, so the copy in tonight's snapshot reflects today's schedule. | High | Open |
| FR-003 | Restorable, not merely stored | As the operator, I want the captured artifact to be reinstallable as a working crontab without hand-editing, so recovery is a copy, not a reconstruction. | High | Open |
| FR-004 | Refuse to overwrite good state with empty state | As the operator, I want a capture that reads an empty or unreadable crontab to preserve the previous copy and signal the anomaly, so the destruction window cannot erase the backup too. | High | Open |
| FR-005 | Capture health is observable | As the operator, I want capture success, failure, and staleness surfaced through the existing health surface, so a quietly dead capture is reported rather than assumed working. | High | Open |
| FR-006 | Register the drift check | As the operator, I want `drift_check.py` present in the service inventory with a health check and a staleness bound, so its absence or stall is reported. | Medium | Open |
| FR-007 | Warn before the destructive rebaseline step | As the operator, I want the rebaseline procedure to warn, above its `rm`, that baselines may hold the only copy of host state and should be archived or transcribed first. | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Snapshot grouping is unchanged | After the change, newly written snapshots carry the identical path set as the 17 existing snapshots — verified by comparing the `Paths` field of the newest snapshot against a pre-change snapshot. | Reliability | High | Open |
| NFR-002 | Recovery window under 24 hours | The captured crontab in the most recent snapshot is never more than one backup cycle (24h) behind the live crontab under normal operation. | Reliability | High | Open |
| NFR-003 | Capture is idempotent | Running the capture repeatedly with an unchanged crontab produces an unchanged artifact and no side effects beyond a refreshed freshness signal. | Reliability | Medium | Open |
| NFR-004 | Staleness bound is explicit | Every health check introduced or modified carries a staleness bound sized to its cycle plus margin, so liveness-only checks cannot pass a dead component. | Observability | High | Open |
| NFR-005 | Capture cost is negligible | The capture completes in under 5 seconds and adds under 100 KB per snapshot. | Performance | Low | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Do not alter the rebaseline command string | `rebaseline_command` in `docs/design/architecture/data/audited-surfaces.json` must remain byte-identical. It is parsed by `scripts/deploy/felix-deployer/rebaseline.py:585-586`, which asserts the first token is `rm` and otherwise falls back to `["true"]`, silently making every deferred-confirm rebaseline audit inconclusive. FR-007 is satisfied in prose copies only. | Technical | High | Open |
| C-002 | Do not add a restic source path | The source set stays exactly `/data/services`, `/data/transcripts`, `/home/claude`, `/home/kgale`. `restic forget` runs without `--group-by`, so it defaults to `host,paths`; a fifth path would split the snapshot group and freeze the existing 17 snapshots from ever being pruned again. | Technical | High | Open |
| C-003 | Unprivileged, `claude` scope only | The work runs as the `claude` user with no sudo. `crontab -u kgale -l` and `crontab -u root -l` both return permission denied, so only the `claude` crontab is in scope, and no artifact or document may imply broader coverage. | Technical | High | Open |
| C-004 | Deploy through the manifest pipeline | Any host-side change ships as a `deploys/queued/<name>.yaml` manifest consumed by felix-deployer. Editing the live `restic-backup.sh` is excluded: it is `root:root` and hand-installed, which would reintroduce a manual sudo step (tracked separately as #903). | Technical | High | Open |
| C-005 | Land the warning before touching the crontab | FR-007 must merge before any work that edits the crontab. A crontab edit drifts `crontabs.txt` and invites the rebaseline whose `rm` destroys the only copy — the exact 2026-08-27 sequence. | Technical | High | Open |
| C-006 | Tier 3 change control, with a snapshot pre-check | Scoped to Tier 3 during planning: the chosen design installs a systemd user timer and a helper and makes **no** change to backup configuration, matching the `0018-habits-weekly-driver` precedent. The filed issue assumed Tier 2 because it assumed editing the restic source set, which C-002 now forbids. A restic-recency pre-check is still run voluntarily. | Regulatory | High | Amended |
| C-007 | Audited-surface rebaseline obligation | The change touches audited surfaces; the merge must record a rebaseline outcome per `docs/runbooks/security-baseline-ops.md`. | Regulatory | Medium | Open |

### Key Entities

- **Captured crontab artifact**: A point-in-time copy of the `claude` user's
  crontab, stored beneath an already-backed-up path, carrying enough provenance
  (capture time, source user, host) to be trusted at recovery time.
- **Capture freshness signal**: The record of when the capture last ran and
  whether it succeeded — the thing a health check reads to distinguish "working"
  from "has not run since Tuesday".
- **Service inventory entry**: The registration that gives a scheduled component
  a health check and a staleness bound, and therefore makes its disappearance
  reportable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The `claude` crontab is recoverable from the most recent backup
  without reading any security-monitor baseline file, demonstrated by an actual
  restore to a scratch path.
- **SC-002**: The restored copy is byte-identical to the live crontab at capture
  time, and is at most 24 hours old.
- **SC-003**: Newly written snapshots carry the same path set as snapshots taken
  before the change — zero new path groups.
- **SC-004**: A deliberately stalled capture is reported as stale by the health
  surface within its declared bound, rather than passing.
- **SC-005**: `drift_check.py` appears in the evaluated-component count of the
  health surface and reports a definite verdict.
- **SC-006**: Every prose copy of the rebaseline procedure carries the
  archive-or-transcribe-first warning above its destructive step, while the
  machine-readable command remains byte-identical.

## Assumptions

- **Discovery was deliberately minimized.** The operator's standing instruction
  for this run is to decide vehicles autonomously and stop only for actions
  requiring elevated privilege. Issue #895 plus the verified investigation
  comment are treated as the confirmed intent; the assumptions below stand in
  for answers that would otherwise have been asked.
- **Recovery is manual and rare.** Restoring a crontab is an operator action
  during an incident, not an automated reconciliation. Automatic reinstallation
  of a captured crontab is explicitly out of scope — it would be a reconciler,
  which is #890's subject, not this mission's.
- **Daily capture cadence is sufficient.** The backup itself runs daily, so
  capturing more often than once per backup cycle cannot reduce the recovery
  window and only adds noise.
- **`/data/services` remains a backup source path.** The whole design rests on
  this; if it ceased to be true the artifact would silently stop being backed
  up. NFR-001's verification is what detects that.
- **The existing health surface is the right home for FR-005 and FR-006.** No new
  alerting channel is introduced.

## Out of Scope

- Bringing the `kgale` or `root` crontabs under backup (needs privilege, C-003).
- Placing the five existing cron jobs under repo control or building a
  reconciler — that is #890.
- Fixing repo/host divergence of `restic-backup.sh` — that is #903.
- Changing backup schedule, retention policy, repository location, or the
  remaining four source paths.
- Making the rebaseline procedure archive rather than delete (blocked by C-001).
