# Specification: Refactor doc-auditor to scripts-first driver

**Mission ID**: 01KS2XNXGQVC18MEF7801JKCYR
**Mission slug**: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
**Mission type**: software-dev
**Source**: GitHub issue [#343](https://github.com/kentonium3/kg-automation/issues/343)
**Target branch**: main

---

## Overview

The `felix-doc-auditor` pipeline detects and remediates documentation drift triggered by repo commits. Today it runs as an LLM-first procedural agent that interprets a large prose procedure (~57 KB across two files) on every hourly tick, consumes ~14 M+ tokens/month for largely deterministic work, and accumulates session state until it silently fails. This mission rebuilds the auditor as a deterministic driver that calls an LLM only at narrow, named judgment moments — eliminating session state, reducing per-tick token consumption by ≥80%, and producing a structured tick signal that future alerting (issue #327) can consume.

The old openclaw-agent path is fully retired at cutover — no parallel path, no automatic rollback, fail-forward.

---

## User Scenarios & Testing

### Primary scenario — documentation drift detected after a commit

A repo commit lands on `main`. Upstream automation files a `Doc audit:` issue tagged with the `area/*` label(s) covered by the commit. The hourly auditor:

1. Reads the queue of open `Doc audit:` issues
2. For each in-scope file, compares its current state against the commit's implications using the existing Tier-A vs judgment classification policy
3. Applies Tier-A frontmatter-only edits autonomously
4. Files docs-debt issues for judgment-required gaps using the canonical issue-filing surface
5. Posts an audit summary comment and closes the audit issue
6. Records the activity log entry
7. Emits a structured success/failure signal

Expected behavior: the queue is processed without operator intervention, the auditor surfaces a clear signal on every tick, and per-tick token spend is small.

### Secondary scenario — operator approves or rejects a pending-approval

The auditor previously surfaced a proposed edit as a pending-approval issue. Operator labels the issue with `audit-approve`, `audit-reject`, or `audit-skip`. On the next tick:

1. Auditor reads the pending-approval queue first (before new audits)
2. Applies approved edits to the repo
3. Closes the pending-approval issue with the outcome reflected in a summary comment
4. Proceeds to new-audit selection

Expected behavior: operator decisions are honored within one tick window; the apply step never silently fails.

### Tertiary scenario — backlog recovery after an outage

After a multi-day failure (analogous to the #342 incident), the queue holds 8+ unprocessed `Doc audit:` issues. On the first healthy tick, the auditor processes the **entire queue** in one pass, draining the backlog without artificial throttle.

Expected behavior: backlog clears in one tick under normal load; per-tick token spend scales linearly with queue depth.

### Edge cases

- **Empty queue** — auditor exits cleanly with a heartbeat-positive signal; no work performed.
- **LLM API outage** — auditor exits non-zero with a structured error signal; queue state is not corrupted; the next tick retries.
- **Multiple commits in flight** — auditor processes the full queue per tick (no artificial throttle).
- **Audit references a file that doesn't exist** — auditor records the discrepancy in the audit comment and closes the audit; no orphaned lock.
- **Stuck `status:in-progress` lock from a prior failed tick** — auditor recovers the lock if the prior tick's signal indicates failure (no manual cleanup required).
- **GitHub API rate limit** — auditor exits non-zero with a structured signal indicating rate-limit class; next tick retries.

---

## Functional Requirements

| ID | Status | Requirement |
|---|---|---|
| FR-001 | required | The auditor MUST process documentation-drift audit issues using a deterministic workflow that does not depend on LLM interpretation of a multi-step prose procedure. |
| FR-002 | required | The auditor MUST consult an LLM only at narrow, named judgment moments. Each LLM consultation MUST receive only the context required for that specific question — not the auditor's full procedural definition or unrelated state. |
| FR-003 | required | The auditor MUST be stateless between ticks. No persistent conversation history, no growing session artifact, no implicit dependency on prior-tick state outside the GitHub issue surface and the activity log. |
| FR-004 | required | The auditor MUST process the FULL queue of pending-approval decisions and unlocked new audits per tick. Pending-approval decisions MUST be processed before new audits within a tick. |
| FR-005 | required | The auditor MUST file docs-debt issues for judgment-required gaps using the canonical template-compliant issue-filing surface — not ad-hoc GitHub issue creation. |
| FR-006 | required | The auditor MUST apply Tier-A frontmatter-only edits autonomously, per the existing classification policy. The classification thresholds documented in current SKILL.md §7 are inherited as-is by this mission. |
| FR-007 | required | The auditor MUST emit a structured success/failure signal on every tick, observable from outside the auditor process. The signal MUST NOT require parsing LLM-generated prose. |
| FR-008 | required | The auditor MUST update each processed audit issue's labels and add a summary comment on completion, releasing any lock state acquired during processing. |
| FR-009 | required | The auditor MUST preserve the existing activity log format and append one log entry per tick. |
| FR-010 | required | At cutover, the previous openclaw-agent definition for felix-doc-auditor (workspace files and openclaw registration) MUST be fully retired — workspace files removed, agent deregistered from openclaw. No parallel path is maintained for rollback. |
| FR-011 | required | Each LLM judgment prompt MUST be checked into the repo as a named, reviewable artifact. A reviewer MUST be able to determine, without running the auditor, exactly what context the LLM receives at each judgment moment. No runtime-only prompt construction. |
| FR-012 | required | The mission MUST update the architecture documentation (`service-inventory.json`, `data-flows.json`, `credential-manifest.json` as applicable) to reflect the new invocation surface. `updated_by` MUST be set to issue #343 on all modified JSON files; markdown views MUST match JSON sources. |
| FR-013 | required | The mission MUST update the operator quick-reference for felix-doc-auditor operations to reflect: the new architecture, where prompt artifacts live, how to inspect a recent judgment call, and how to read the structured tick signal. |
| FR-014 | required | The auditor MUST recover from a stuck `status:in-progress` lock left behind by a prior failed tick, without requiring manual operator intervention. Lock recovery semantics are documented as part of the mission deliverables. |

---

## Non-Functional Requirements

| ID | Status | Requirement |
|---|---|---|
| NFR-001 | required | Per-tick token consumption MUST be reduced by ≥80% relative to the current openclaw-agent invocation baseline, measured across a representative mix of tick outcomes (empty, debt-only, Tier-A apply, pending-approval apply). Baseline and post-rework measurements MUST be recorded with a methodology repeatable in 6 months. |
| NFR-002 | required | Over a 7-day post-cutover observation window, ≥95% of hourly ticks MUST complete with a successful structured signal. The auditor MUST NOT go >2 consecutive ticks without emitting some signal — silent multi-tick gaps are themselves a failure. |
| NFR-003 | required | The auditor's persistent state artifacts on disk MUST NOT exceed a documented per-tick footprint. After 24 hours of operation, no auditor-owned state artifact may exceed 100 KB. |
| NFR-004 | required | The structured success/failure signal MUST be consumable by a separate process (e.g., the future #327 alerting substrate) without parsing LLM-generated prose. The signal contract MUST be a known artifact location and/or a process exit code paired with a journal-readable line. |
| NFR-005 | required | All LLM judgment prompts MUST be auditable: a reviewer reading the checked-in prompt artifacts MUST be able to enumerate every category of question the auditor asks an LLM. No hidden or runtime-generated prompt content. |
| NFR-006 | required | The auditor process MUST complete a typical full-queue tick (≤5 audits) within the existing systemd `TimeoutStartSec=30min`. Longer backlogs may exceed this and surface a `tick-too-long` signal for operator visibility. |

---

## Constraints

| ID | Status | Constraint |
|---|---|---|
| C-001 | required | This mission MUST preserve the existing Tier-A vs judgment classification policy thresholds. This mission does NOT re-litigate the policy. |
| C-002 | required | This mission MUST NOT change the upstream signal source (the workflow that files `Doc audit:` issues on commits). |
| C-003 | required | This mission MUST NOT alter the canonical issue-filing surface used for docs-debt filing. The auditor consumes it as-is. |
| C-004 | required | The cutover plan MUST require a queue-drained or near-drained state at deploy time to minimize in-flight pending-approval orphaning. |
| C-005 | required | Activity log location and format MUST remain unchanged from the current operational definition. |
| C-006 | required | The auditor MUST operate under the existing service-account identity (`kg-felix-bot`) for GitHub operations, to preserve audit-trail attribution. |
| C-007 | required | This mission operates under a fail-forward posture. No automatic rollback is built into the cutover. Issues surfacing post-cutover are tracked as follow-on missions, not as automatic revert triggers. |
| C-008 | required | All architecture documentation updates (service-inventory.json, data-flows.json, credential-manifest.json) are part of THIS mission, not a separate follow-on. |
| C-009 | required | Constitutional autonomy level: Observed (Level 2). Tier-A frontmatter edits are applied autonomously per existing policy; judgment edits remain pending-approval gated on operator decision label. Unchanged from current behavior. |
| C-010 | required | Privacy boundary: the auditor MUST NOT read second-brain notes or any path under `~/second-brain/notes/04-Growth/_private/`. Activity logging under `~/second-brain/agents/logs/` is operational, not private. |

---

## Success Criteria

These outcomes are measurable, technology-agnostic, and verifiable from outside the auditor process:

| ID | Outcome |
|---|---|
| SC-001 | The audit queue does not accumulate beyond steady state: ≤2 open `Doc audit:` issues older than 2 hours during normal operation. |
| SC-002 | An operator can determine the auditor's health (last successful tick, last failure if any, current queue depth) from the structured signal in under 30 seconds, without reading LLM-generated prose. |
| SC-003 | Per-tick LLM cost is reduced by ≥80% relative to the pre-rework baseline, demonstrated across a representative mix of tick outcomes. |
| SC-004 | The auditor surfaces failures within one tick window of when they occur. Silent multi-day failures (the #342 pattern) are no longer possible without violating NFR-002. |
| SC-005 | A reviewer can audit every LLM judgment moment by reading checked-in artifacts, with no runtime-only prompt construction. |
| SC-006 | The auditor's resource footprint is bounded — no growing state artifacts, no accumulating session content. |
| SC-007 | Post-cutover, the openclaw-agent definition for felix-doc-auditor no longer exists; only the new driver path is active. |
| SC-008 | A backlog of N queued audits drains in one tick (subject to NFR-006 timeout for very large N). |

---

## Key Entities

- **`Doc audit:` issue** — a GitHub issue auto-filed on commits, labeled with `area/*` to indicate scope. Holds lock state via `status:in-progress` label. Resolved via summary comment + closure.
- **Pending-approval issue** — a GitHub issue surfaced by the auditor proposing one or more edits requiring operator review. Resolved via `audit-approve`, `audit-reject`, or `audit-skip` label, then auditor processes on next tick.
- **Docs-debt issue** — a GitHub issue filed by the auditor for judgment-required gaps it cannot resolve autonomously. Filed via the canonical issue-filing surface.
- **Judgment-prompt artifact** — a checked-in repo file containing the exact context-template and question shape sent to an LLM for one named judgment moment.
- **Structured tick signal** — a deterministic, machine-readable record of each tick's outcome (artifact location and/or process exit code + journal line). Consumed by the future alerting substrate (#327).
- **Activity log entry** — a daily append-only record of auditor activity, preserved in its existing location and format.
- **Tier-A edit** — a high-confidence frontmatter-only edit eligible for autonomous application per the existing classification policy.
- **Judgment edit** — a proposed edit requiring operator review, surfaced as a pending-approval issue.

---

## Assumptions

The plan phase MUST validate these before implementation begins:

1. LLM API access for direct (non-openclaw) consumption is available from the auditor's host with credentials accessible to the auditor process under the existing service-account identity. If not, the plan must surface a credential-provisioning sub-task.
2. The service-account credentials (`kg-felix-bot`) currently used by the openclaw-agent for GitHub operations are available to the new auditor process through the same mechanism.
3. The canonical issue-filing surface (`felix-file-issue.py`) is stable enough to call as-is, as validated by recent end-to-end usage (verified 2026-05-19).
4. The activity log location (`/home/kgale/second-brain/agents/logs/`) and write surface remain available to the auditor process under the existing identity.
5. The upstream workflow that files `Doc audit:` issues on commits continues to function unchanged.
6. The existing `handle_audit_routing.py` implementation contains usable deterministic kernels that can be lifted and refactored, reducing the implementation effort. Plan phase confirms the extent.
7. The existing systemd timer cadence (hourly) and `TimeoutStartSec=30min` envelope are acceptable for the new driver. No timer-config change is part of this mission.

---

## Out of Scope

The following are explicitly NOT part of this mission:

1. Building or operating the universal alerting substrate (#327). This mission leaves hook sites; #327 is the separate effort that populates them.
2. Migrating other Felix agents (capture, habits, tasker, escalation) to the same architectural pattern.
3. Changing the upstream workflow that files `Doc audit:` issues on commits.
4. Re-litigating the Tier-A vs judgment classification thresholds.
5. Modifying or replacing the canonical issue-filing surface for docs-debt issues.
6. Active alerting or pager integration. The auditor surfaces a signal; alerting consumes it (separate effort).
7. Changing the systemd timer cadence or the activity log location/format.

---

## Cross-References

- **GitHub issue**: [#343](https://github.com/kentonium3/kg-automation/issues/343)
- **Antecedent incident**: [#342](https://github.com/kentonium3/kg-automation/issues/342) (closed — superseded by this mission)
- **Future hook target**: [#327](https://github.com/kentonium3/kg-automation/issues/327) (RFC: universal alerting primitives)
- **Architectural antecedent**: [#278](https://github.com/kentonium3/kg-automation/issues/278) (signal-driven doc-audit pipeline epic)
- **Constitutional anchor**: Felix Constitution Directive 6 (deterministic vs stochastic work split)
- **Operator memory**: `reference_felix_doc_auditor_ops.md` (will be updated per FR-013)

---

## Discovery Record

The following decisions were resolved during specify-phase discovery:

| # | Question | Decision | Encoded in |
|---|---|---|---|
| Q1 | Post-cutover fate of the openclaw-agent definition | **Fully retire** — workspace files removed, agent deregistered, no parallel path | FR-010, C-007 |
| Q2 | Shape of the reliability requirement | **NFR** with lightweight observation hook for future #327 consumption | NFR-002, NFR-004, FR-007 |
| Q3 | Audit-queue processing cadence per tick | **Full queue per tick** — backlog drains in one pass; doc accuracy prioritized over per-tick predictability | FR-004, SC-008 |
