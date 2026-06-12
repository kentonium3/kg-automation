# Specification: Pull-Based Deploy Pipeline with Tier Guard and Doctrinal Anchor

**Mission**: `pull-based-deploy-pipeline-01KTYQQS`
**Mission type**: software-dev
**Source issue**: kentonium3/kg-automation#136 (Epic parent #533, supersedes #154, captures #549)

---

## Intent Summary

Replace ad-hoc, per-mission deploy wrappers with a **manifest-driven pull-based pipeline** AND anchor the deploy discipline in **agent-facing documentation surfaces** so future specify/plan runs automatically incorporate it without operator prompting.

- **Primary actor**: a future spec-kitty agent (or other coding agent) writing a plan for any feature/infra issue that touches office2-hosted artifacts.
- **Trigger**: a new feature/infra issue is filed whose work requires deploying to office2.
- **Success outcome**: the agent's plan automatically references the deploy discipline runbook and produces a manifest entry referencing the shared deploy library — without the operator having to remind it. The autonomous applier on office2 picks up the manifest on its next tick, applies the deploy, and records the outcome.
- **Rule that must always hold**: Tier 0 changes are rejected by both CI (at PR time) and the applier (at execute time). Defense in depth.
- **Most common exception**: a deploy fails at apply time. The applier records the failure, notifies the operator by WhatsApp DM, leaves the manifest in queue, does not auto-retry. The operator fixes the deploy script (or cancels the manifest), and the next applier tick re-attempts.

---

## Domain Language

Use these canonical terms throughout planning and implementation:

- **manifest** — a file in `deploys/queued/` declaring a deploy intent. Not "queue entry", not "deploy request".
- **applier** — the office2-side autonomous process that runs queued deploys on a schedule. Not "deployer service", not "agent".
- **discipline** — the operational + doctrinal regime this mission establishes. Not "pattern", not "process", not "framework".
- **tier guard** — the CI + runtime check enforcing tier policy at both gates.
- **doctrine layer** — the set of agent-facing docs that make the discipline discoverable (project charter rule, canonical runbook, CLAUDE.md section, issue-template hooks, signal-to-doc-map entries).
- **bootstrap deploy** — the one-time manual deploy of the applier itself, performed via a one-shot wrapper following the canonical `deploy-149.sh` shape.

---

## User Scenarios & Testing

### Primary scenario — Agent auto-discovery

A specify/plan agent working on a new feature issue that requires deploying code to office2 reads the project's session-start agent context (CLAUDE.md), follows its reference to the deploy discipline runbook, consults the architecture signal-to-doc map for the relevant change class, and produces a plan that includes a `deploys/queued/<name>` manifest entry referencing the shared deploy library. The operator does not have to remind the agent to do this.

### Secondary scenario — Tier 0 rejection (defense in depth)

An operator (or agent) authors a PR containing a manifest entry declaring `tier: 0`. The CI tier guard rejects the PR with a message pointing at the canonical deploy discipline rule. If a Tier 0 manifest somehow reaches the applied state without CI catching it, the applier's runtime tier guard rejects it at execute time and records the rejection.

### Exception scenario — Failed deploy

A queued deploy fails at apply time (e.g., a Python error in a library primitive, or a remote-host condition the script can't recover from). The applier writes a failure record next to the manifest with timestamp and error summary, sends a WhatsApp DM to the operator with the manifest name and failure summary, leaves the manifest in the queue (does not move to applied), and does not auto-retry. The operator fixes the deploy script and the next applier tick picks it up — or deletes the manifest entry to cancel.

### Bootstrap scenario — Deploying the applier itself

The very first deploy of the applier cannot use the manifest discipline because the manifest discipline does not yet exist on office2. It is performed via a one-shot wrapper script following the canonical `deploy-149.sh` shape (dry-run / apply modes, no system crontab, manual rollback instructions in the header). This bootstrap procedure is documented as the canonical example of "one-shot followed by everything-via-manifest from that point forward."

### Edge cases

- **Git pull fails on office2 tick** (network blip or merge conflict): the applier logs the failure, skips the tick, retries on the next interval. No manifest state change.
- **Multiple manifests queued simultaneously**: applier processes them in deterministic order (alphabetical by filename) and applies them sequentially within a single tick.
- **Manifest deleted between CI and applier**: applier finds no file, no-op, logs the absence.
- **Applier process crash mid-deploy**: applier records partial-success state to the failure file and the next tick treats it as failed (manifest stays in queue).

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Operators and agents can declare a deploy intent by adding a manifest file to a designated queue directory in the repository. | required |
| FR-002 | The applier reads the queue directory on a regular schedule and processes pending manifests. | required |
| FR-003 | Successfully applied deploys are recorded as applied with success metadata; their manifests are moved out of the queue. | required |
| FR-004 | Failed deploys are recorded with failure metadata; their manifests remain in the queue until operator action. | required |
| FR-005 | A shared library of vetted deploy primitives is available for use by deploy scripts (at minimum: cron pause/resume via OpenClaw, backup-recency verification, file-presence checks, stale-literal absence checks). | required |
| FR-006 | A CI check rejects PR-time manifest entries declaring Tier 0. | required |
| FR-007 | The applier rejects Tier 0 manifests at execute time and records the rejection. | required |
| FR-008 | Manifest entries for Tier 1 or Tier 2 changes must include a verification block; entries without one are rejected by the same CI check. | required |
| FR-009 | On apply failure, the operator receives a WhatsApp DM with manifest name, tier, and failure summary. | required |
| FR-010 | A single canonical runbook documents the deploy discipline (queue layout, manifest schema summary, library primitives, tier policy, bootstrap procedure). | required |
| FR-011 | The project charter Deployment Constraints rule is rewritten to describe the manifest discipline; the existing per-script rule and the proposed amendment in #154 are replaced. | required |
| FR-012 | The project-root CLAUDE.md includes a "Deploys to office2" section referencing the canonical deploy discipline runbook. | required |
| FR-013 | The architecture signal-to-doc map contains entries for deploy-related change classes whose doc_targets point at the discipline runbook and at the library documentation. | required |
| FR-014 | The feature and infra issue templates include a "Deploy required?" prompt linking to the discipline runbook. | required |
| FR-015 | The bootstrap deploy of the applier itself is performed via a one-shot wrapper following the existing canonical pattern; the wrapper is preserved in the repository as the canonical bootstrap example. | required |
| FR-016 | The discipline's doctrinal cross-links (CLAUDE.md ↔ runbook ↔ charter ↔ signal-to-doc-map ↔ issue templates) are validated by CI on every PR; broken links fail the build. | required |
| FR-017 | The bootstrap wrapper, the applier, and the shared library all refuse to touch the system crontab; all cron operations route through the OpenClaw cron interface. | required |
| FR-018 | A `Rebaseline: completed at <ts>` line is recorded in the merge commit per the audited-surface protocol (this mission touches deploy scripts + new systemd user units). | required |

## Non-Functional Requirements

| ID | Requirement | Status | Threshold |
|---|---|---|---|
| NFR-001 | The applier processes pending manifest entries within 10 minutes of the manifest's merge to main. | required | ≤ 10 min end-to-end (poll interval ≤ 5 min + apply time ≤ 5 min for a typical small deploy) |
| NFR-002 | The applier's tick produces a stable, machine-parseable log line per tick (poll + outcome summary) suitable for operator scanning. | required | One JSON-shaped line per tick at info level; one line per processed manifest. |
| NFR-003 | A deploy that fails at apply time produces a WhatsApp DM to the operator within 60 seconds of failure detection. | required | ≤ 60 s from applier failure-record write to DM dispatch. |
| NFR-004 | The library API documentation accurately describes every public primitive in the shipped library (verified by import-and-introspect test in CI). | required | Zero undocumented public primitives; zero documented-but-missing primitives. |
| NFR-005 | Doctrinal cross-link verification runs in CI on every PR and runs the full check in under 30 seconds. | required | ≤ 30 s wall clock on the CI runner. |
| NFR-006 | The applier is observable from the office2 host via `systemctl --user status` and via its log file location, both documented in the discipline runbook. | required | Both surfaces documented; both reachable from operator session. |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Pull-only architecture. office2 pulls from GitHub. Mac never pushes directly to office2 as part of this pipeline. | binding |
| C-002 | No new public-internet exposure. Deploy infrastructure is Tailscale-internal and repository-local. | binding |
| C-003 | No system crontab mutation. All cron operations route through the OpenClaw cron interface. Inherits existing constitutional rule. | binding |
| C-004 | Tier 0 changes are not executable via this pipeline at any time. They remain manual via `ssh office2-kgale`. | binding |
| C-005 | Existing seven deploy scripts in `scripts/deploy/` are grandfathered and not modified by this mission. | binding |
| C-006 | WhatsApp DM is the failure-notification substrate. Vikunja is not used for deploy tracking. | binding |
| C-007 | Cleanup and classification of the seven grandfathered scripts is out of scope; handled by sibling issue #548 post-merge. | binding |
| C-008 | The Felix Constitution is not amended; existing Directive 6 (deterministic helpers) and the change-risk taxonomy already cover the relevant principles. | binding |
| C-009 | No webhook receiver or push-triggered deploy mechanism is built. Pull-only. | binding |
| C-010 | Only office2 is a deploy target. Cross-host or multi-host orchestration is out of scope. | binding |

---

## Success Criteria

Measurable, technology-agnostic outcomes that determine mission success at acceptance and post-merge review.

- **SC-001** — A doctrinal cross-link CI check passes on the merge commit: CLAUDE.md → discipline runbook, charter rule → manifest discipline, signal-to-doc-map → discipline runbook + library docs, issue templates → discipline runbook. All four edges are present and reachable.
- **SC-002** — Within 10 minutes of a non-bootstrap manifest being merged to main, the applier processes it and records an outcome (applied or failed).
- **SC-003** — A deliberately Tier-0 manifest entry in a PR produces a red CI build with a message pointing at the canonical discipline runbook.
- **SC-004** — A deliberately failing deploy produces a WhatsApp DM to the operator within 60 seconds, and the manifest remains in queue with a failure record beside it.
- **SC-005** — The applier is visible to the operator on office2 via `systemctl --user status`; the discipline runbook documents how to find it.
- **SC-006** — The seven grandfathered deploy scripts continue to work unchanged (smoke-tested by re-running at least one in dry-run mode at acceptance time).
- **SC-007** — Sibling issues #154 (charter amendment) and #549 (runbook) are closed as superseded/captured by this mission's merge.
- **SC-008** — The merge commit records `Rebaseline: completed at <ts>` per the audited-surface protocol.

---

## Key Entities

- **Deploy Manifest** — A file in the queue directory declaring a deploy intent. Fields include: name, referenced deploy entrypoint, tier, audited-surface flag, requester (mission or issue), and a verification block.
- **Deploy Applier** — The autonomous office2-side process responsible for reading the queue, applying deploys, and recording outcomes.
- **Deploy Library** — The shared set of vetted primitives reusable by all deploy entrypoints. Contains cron management (OpenClaw-only), backup-recency verification, file-presence checks, stale-literal-absence checks, and a tier guard.
- **Tier Guard** — The CI-time and runtime check that enforces the change-risk-taxonomy tier policy. Has two surfaces: CI (rejects PRs) and runtime (rejects at execute time).
- **Doctrine Layer** — The set of agent-facing surfaces collectively. Includes the project charter Deployment Constraints rule, the canonical discipline runbook, the CLAUDE.md "Deploys to office2" section, the feature and infra issue template hooks, and the architecture signal-to-doc-map entries.
- **Bootstrap Wrapper** — The one-shot deploy script used to deploy the applier itself; the canonical example of "before the manifest discipline exists on office2."

---

## Assumptions

- The existing OpenClaw cron interface remains the canonical surface for managing scheduled jobs on office2.
- The existing `restic` backup pipeline remains the canonical snapshot mechanism for Tier 2 verification.
- The `spec-kitty charter sync` command continues to propagate charter edits correctly (verified in past missions).
- The architecture signal-to-doc map schema (mappings array with `id`, `match`, `doc_targets`, `rationale`, optional `issue_title_prefix` and `issue_labels`) extends to mission-architecture-impact source types without schema migration.
- The Felix Bot WhatsApp DM surface is available for failure notifications using existing recipient configuration.
- The `claude` user on office2 has permission to manage its own systemd user units (verified by the existing `felix-doc-auditor` precedent).

---

## Out of Scope

- Cleanup, classification, or migration of the seven existing deploy scripts (delivered by sibling issue #548 post-merge).
- Cross-host deploys (office2 is the only target).
- Webhook receivers and push-triggered deploy mechanisms.
- Felix Constitution amendments.
- Retroactive migration of shipped missions or their deploy records.
- Vikunja-based deploy tracking or any per-deploy operator-facing UI.
- A "deploy preview" or "deploy plan" surface in the dashboard.
- A universal deploy framework usable from other repositories.
- Continuous deployment from main without an explicit manifest entry.

---

## Notes

- This spec deliberately leaves implementation choices (manifest format, library language, applier scheduling mechanism, schema validation library) to the plan phase. The Functional and Non-Functional requirements describe outcomes and observable behavior.
- The "Mechanism" and "Doctrine" deliverables in issue #136 land in the same mission so that the doctrine references and the code/paths it references match from the merge commit forward.
- Existing deploy scripts in `scripts/deploy/` are observed and referenced but not modified by this mission's work packages.
