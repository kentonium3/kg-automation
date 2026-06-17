# Feature Specification: Auto-Rebaseline Security Baselines on Deploy

**Mission**: auto-rebaseline-on-deploy-01KVAYJN
**Source**: GitHub issue [#618](https://github.com/kentonium3/kg-automation/issues/618)
**Status**: Draft

## Overview

felix-deployer (the office2 pull-based applier) currently applies changes to
office2 but does not reset the security-monitor baselines when a change touches
an audited surface. The reset ("rebaseline") is a manual operator action. A
forgotten reset produces a false-positive drift alert on the next security
audit, which erodes trust in the security signal.

This feature makes the rebaseline an **automatic, silent step of the deploy
pipeline on the happy path** — an intentional audited-surface change applied
through felix-deployer rebaselines itself with no human in the loop. A human is
pulled in only off the happy path: an out-of-band change the pipeline cannot
see (caught by the existing daily audit as drift), or a rebaseline that fails
after a clean apply (which raises an explicit alert).

## User Scenarios & Testing

### Primary scenario (happy path)
1. An operator (or automation) lands a commit on the deploy target that changes
   an audited surface — e.g. an OpenClaw config, an agent prompt, a systemd
   unit, or a Python dependency manifest.
2. felix-deployer ticks, pulls the change, passes its gate, and applies it.
3. The deployer detects that the change set intersects the audited-surface
   registry and, once the surface's drift is actually observed, resets and
   regenerates the security-monitor baselines, verifies they are healthy, and
   records `rebaseline: completed` on the deploy record — with **no operator
   interaction**.
4. The next scheduled security audit reports no drift.

### Exception: applied change touches no audited surface
- The deployer records `rebaseline: not required` (with reason) and performs no
  reset.

### Exception: rebaseline fails after a clean apply
- The code change is already applied and working; only the baseline reset
  failed (regeneration error, baseline count mismatch, or audit not clear).
- The deployer emits a single push notification alerting an operator, records
  the failure on the deploy record, and **leaves the applied code in place**
  (no rollback).

### Exception: out-of-band change (not via the pipeline)
- A change made directly on office2 (not through felix-deployer) is invisible
  to the hook. The existing daily security audit surfaces it as drift, prompting
  a human to investigate and rebaseline manually. This is the correct off-happy-
  path behavior.

### Exception: unexpected drift (beyond what the change should touch)
- When the observed drift extends beyond the baselines the pending change is
  expected to affect, the deployer does **not** auto-reset; it raises an
  operator alert (potential security event) and leaves the baselines intact.

### Rule that must always hold
- The rebaseline fires **only** for a clean, gated, successfully-applied change
  whose expected drift has actually been observed. A failed or partially-applied
  deploy, or drift outside the expected set, never triggers an auto-rebaseline.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | After felix-deployer pulls and applies a deploy, the system determines whether the applied change set touched any audited surface, using the canonical audited-surface registry. | Approved |
| FR-002 | When an applied change set touches at least one audited surface and the expected drift is confirmed, the system resets and regenerates the security-monitor baselines with no human interaction required. | Approved |
| FR-003 | The system records the rebaseline outcome on the corresponding deploy record (completed with timestamp, not-required with reason, or failed with error summary). | Approved |
| FR-004 | When the applied change set touches no audited surface, the system records `rebaseline: not required` and performs no reset. | Approved |
| FR-005 | After regenerating baselines, the system verifies they are healthy — the expected baseline count is restored and the audit reports clear — before recording the rebaseline as completed. | Approved |
| FR-006 | When a rebaseline fails after a successful apply, the system emits exactly one operator push notification, records the failure on the deploy record, and leaves the already-applied code change in place (no rollback). | Approved |
| FR-007 | The rebaseline is triggered only for a clean, gated, successfully-applied change whose expected drift has been confirmed; a failed or partially-applied deploy never triggers a rebaseline. | Approved |
| FR-008 | The audited-surface determination covers the full set of commits included in a single apply (a batch/range), not only the most recent commit. | Approved |
| FR-009 | When observed drift extends beyond the baselines the pending change is expected to affect, the system does not auto-reset; it emits exactly one operator push notification and leaves the baselines intact. | Approved |

### Non-Functional Requirements

| ID | Requirement | Threshold / Measure | Status |
|----|-------------|---------------------|--------|
| NFR-001 | The deploy-time audited-surface check and the existing repo-side CI reminder must share one source of truth so they cannot diverge. | Zero duplicate surface-pattern lists; both consume the same registry + detection logic. | Approved |
| NFR-002 | The rebaseline plus verification must not stall subsequent deploys. | Completes within one deployer tick window (≤ 5 minutes), verified by an explicit budget assertion or documented bound. | Approved |
| NFR-003 | Out-of-band (non-pipeline) audited-surface changes remain covered. | The existing daily security audit continues to run unchanged and still surfaces unexpected drift. | Approved |
| NFR-004 | The happy path requires zero operator interactions. | No prompts, confirmations, or manual commands on a successful audited-surface deploy. | Approved |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | The rebaseline must run as the claude user without sudo (documented `sg docker` audit path). | Approved |
| C-002 | This change to felix-deployer must itself flow through the `deploys/queued/<name>.yaml` manifest discipline. | Approved |
| C-003 | The change is Tier 3 (logic/workflow) under the change-risk taxonomy. | Approved |
| C-004 | This supersedes the manual "operator is responsible for running the reset" rule for pipeline-driven changes; CLAUDE.md and the charter Rebaseline Obligation section must be updated so automation is the documented happy path and manual reset is the out-of-band exception. | Approved |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | An intentional audited-surface change applied via the pipeline results in clean, healthy baselines with no human action. |
| SC-002 | After such a change, the next scheduled security audit reports no drift attributable to the intentional change (zero false-positive drift alerts). |
| SC-003 | A deploy that touches no audited surface records "rebaseline not required" and triggers no reset. |
| SC-004 | A simulated rebaseline failure produces exactly one operator alert and a failure annotation on the deploy record, with the applied code left in place. |
| SC-005 | Operator manual-rebaseline actions for pipeline-driven changes fall to zero over subsequent audited-surface deploys. |

## Key Entities

- **Deploy record** — the per-deploy artifact felix-deployer writes (applied / failed), extended to carry rebaseline status.
- **Rebaseline-pending token** — runtime state recording that an audited-surface change has been observed and is awaiting drift confirmation (matched surface ids + expected baselines).
- **Audited-surface registry** — `docs/design/architecture/data/audited-surfaces.json`: the canonical path→baseline map and `expected_baseline_count`.
- **Security-monitor baseline set** — the baseline files on office2 (currently 14) that the daily audit hashes against.
- **Audit result** — the clear/drift outcome of the security audit run.

## Domain Language

- **Audited surface** — a repo path whose change alters the office2 security-monitor baselines (per the audited-surface registry).
- **Rebaseline** — deleting and regenerating the security-monitor baselines so they reflect the current intended state.
- **Happy path** — an intentional change applied through the deploy pipeline (as opposed to out-of-band).
- **Out-of-band change** — an audited-surface change made directly on office2, bypassing felix-deployer.
- **Expected drift** — drift confined to the baselines the observed audited-surface change is expected to affect.
- **Unexpected drift** — drift extending beyond the expected baseline set; a potential security event requiring a human.

## Assumptions

- felix-deployer can determine the changed paths of the commit range it pulled/applied (diff of the pulled range).
- The push-notification substrate is ntfy (the canonical alert path used by security-monitor).
- `expected_baseline_count` is read from the audited-surface registry, not hardcoded in the deployer.
- The existing audited-surface detection logic (`tooling/scripts/check_audited_surface_drift.py`) can be reused or shared so the deploy-time check matches the CI reminder.
- The audit run with baselines present is a non-destructive drift check, distinct from the `rm baselines/* && audit.sh` regenerate path (to be confirmed by a live office2 probe during planning/implementation).
