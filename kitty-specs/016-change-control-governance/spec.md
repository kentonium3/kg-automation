---
title: "F016: Change Control Governance & Incident Management"
doc_type: spec
status: draft
feature: 016-change-control-governance
mission: software-dev
---

# Feature Specification: Change Control Governance & Incident Management

## Overview

On 2026-04-03, a UFW firewall hardening change blocked port 443, taking down Vikunja for approximately 8 hours. The change was correct in scope but failed to account for Tailscale serve's dependency on that port. No risk-tiered assessment, pre-flight dependency check, or post-change verification caught the problem. No incident postmortem process existed to capture lessons.

This feature establishes a five-tier change control framework (Tier 0 Hard Lock → Tier 4 Auto-Commit) that classifies changes by blast radius and assigns guardrail protocols governing AI autonomy per tier. It enriches the service inventory with dependency, health-check, and risk-tier data. It adds pre-flight checklists, post-change verification, CLAUDE.md enforcement rules, an incident postmortem template, and formalizes the documentation standards principle.

**Prerequisite (completed)**: F015 (Documentation Architecture Rationalization) resolved path dependencies for this feature — governance files → `docs/runbooks/governance/`, postmortems → `docs/issues/postmortems/`, change risk taxonomy → `docs/design/architecture/data/`.

## User Scenarios & Testing

### Primary Scenario: Agent Executes a Tier 0 Change Request

**Actor**: Claude Code agent asked to modify UFW rules on office2.

**Flow**:
1. Agent receives request: "Add a UFW rule to allow port 8080."
2. Agent consults the change-risk taxonomy (`docs/design/architecture/data/change-risk-taxonomy.json`) and identifies UFW as **Tier 0** (Host/Foundational).
3. Agent applies the Tier 0 **Hard Lock** protocol per CLAUDE.md rules: generates the shell script but does NOT execute it. Presents the script to Kent for manual execution via `ssh office2-kgale`.
4. Kent reviews and executes manually.
5. Agent runs the post-change verification protocol: checks health endpoints of all services dependent on affected ports (from enriched service inventory).

**Success**: Agent never directly executes Tier 0 commands. Post-change verification confirms all dependent services are healthy.

### Secondary Scenario: Agent Modifies a Tier 2 Service Configuration

**Actor**: Claude Code agent updating Vikunja Docker Compose environment variables.

**Flow**:
1. Agent identifies the change as **Tier 2** (Application/State) from the risk taxonomy.
2. Agent applies the Tier 2 **Snapshot Required** protocol: confirms a recent Restic backup exists before modifying.
3. Agent makes the change and runs the post-change verification: checks Vikunja's health endpoint.
4. If verification fails, agent triggers rollback using the defined rollback procedure.

**Success**: Backup confirmed before modification. Post-change health check passes or rollback is triggered.

### Tertiary Scenario: Incident Postmortem After Service Outage

**Actor**: Kent + Claude Code after a service outage is resolved.

**Flow**:
1. After resolving the incident, Kent initiates a postmortem using the template at `docs/runbooks/governance/incident-postmortem-template.md`.
2. The template captures: incident summary, timeline, root cause chain, impact, what went well, what failed, and follow-on actions.
3. Follow-on actions are structured as trackable items and linked to Vikunja tasks.
4. Completed postmortem is stored at `docs/issues/postmortems/YYYY-MM-DD_incident-slug.md`.

**Success**: Postmortem completed in under 30 minutes. Follow-on actions are tracked and linked.

### Validation Scenario: F016 Origin Incident Walkthrough

**Actor**: The feature itself validates its deliverables against the 2026-04-03 Vikunja UFW outage.

**Flow**:
1. Walk the pre-flight checklist (FR-004) through the origin incident scenario: does it catch the port 443 dependency gap?
2. Walk the post-change verification (FR-005): would it have detected the Vikunja outage?
3. Complete the origin incident postmortem (FR-008) using the new template as the first real postmortem.

**Success**: Pre-flight checklist demonstrably catches the port 443 gap. Postmortem is complete and actionable.

### Edge Cases

- **Service with no health-check endpoint**: enriched inventory marks the service as having no health check; post-change verification flags it as "unverifiable — manual check required."
- **Tier classification ambiguity**: a change that spans two tiers (e.g., Docker Compose change affecting both application state and network config) uses the HIGHER tier's protocol.
- **Tier 0 urgency framing**: even if the user says "just do it, this is urgent," the Tier 0 Hard Lock cannot be overridden — the protocol is to generate and present, never execute directly.
- **New service not yet in inventory**: pre-flight checklist catches this as "service not found in inventory — cannot verify dependencies; STOP and update inventory first."

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Define a five-tier risk taxonomy (Tier 0 through Tier 4) based on blast radius, reversibility, and lockout potential. Each tier has a named guardrail protocol. Taxonomy stored as machine-readable JSON at `docs/design/architecture/data/change-risk-taxonomy.json`. | Draft |
| FR-002 | Extend the existing `docs/design/architecture/data/service-inventory.json` schema with `dependencies`, `health_check`, `config_files`, and `risk_tier` fields on every service record. Dependencies must be specific enough to support pre-flight impact analysis (e.g., "tailscale-serve:443" not just "tailscale"). | Draft |
| FR-003 | Capture Tailscale serve proxy configuration as declared infrastructure state in `docs/design/architecture/data/network-topology.json`. | Draft |
| FR-004 | Define a mandatory pre-flight checklist for Tier 0/1 changes and a lighter variant for Tier 2 changes. Tier 0/1 checklist includes: port/interface impact, dependent service lookup (via enriched inventory), rollback procedure, operator availability confirmation, and post-change verification plan. | Draft |
| FR-005 | Define a post-change verification protocol for Tier 0/1/2 changes. Verification checks all services listed as dependent on affected ports/interfaces using health-check endpoints from the enriched inventory. Defines rollback trigger condition on verification failure. | Draft |
| FR-006 | Add per-tier guardrail enforcement rules to CLAUDE.md. Tier 0: generate script only, present to operator, never execute. Tier 1: confirm connectivity before and after. Tier 2: confirm backup exists before modifying. Tier 3: dry-run where available. Tier 4: full autonomy. Rules reference the taxonomy file, not duplicate it. | Draft |
| FR-007 | Create an incident postmortem template capturing: incident summary, timeline, root cause chain, impact, what went well, what failed, and follow-on actions (structured as trackable items). Template stored at `docs/runbooks/governance/incident-postmortem-template.md`. | Draft |
| FR-008 | Complete the 2026-04-03 Vikunja UFW outage postmortem using the template as the first real postmortem. Store at `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md`. Include all root causes, follow-on actions with Vikunja task references. | Draft |
| FR-009 | Define a documentation standards principle: machine-readable files are authoritative, narrative docs are views/rationale, diagrams are preferred for system structure and relationships. Canonical definition in the Felix constitution, with a summary + pointer reference from CLAUDE.md. | Draft |
| FR-010 | Produce a service dependency diagram for office2 (Mermaid format) demonstrating the diagram convention. Include in architecture docs. | Draft |
| FR-011 | Update `docs/design/architecture/README.md` to reference the new governance files, change-risk-taxonomy.json, and postmortem directory. | Draft |
| FR-012 | Update `docs/design/architecture/change-control.md` to reference the risk taxonomy, pre-flight checklist, and verification protocol. | Draft |
| FR-013 | Update `docs/design/architecture/security-posture.md` to reference the new change control governance. | Draft |
| FR-014 | Update all markdown views (`service-inventory.md`, `physical-topology.md`) to match enriched JSON sources. | Draft |
| FR-015 | Update `docs/INDEX.md` to reference all new governance files, postmortem directory, and change-risk-taxonomy.json per the F015 change-control INDEX.md maintenance rule. | Draft |
| FR-016 | Walk the pre-flight checklist through the origin incident scenario to validate it would have caught the port 443 dependency gap. Document the walkthrough result. | Draft |

### Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-001 | The Tier 0 Hard Lock rule in CLAUDE.md is unambiguous and cannot be circumvented by urgency framing, explicit user instruction to execute directly, or any other override mechanism. | Draft |
| NFR-002 | CLAUDE.md guardrail rules cause zero added friction for Tier 3 and Tier 4 changes (logic/workflow and schema/metadata). Only Tier 0-2 changes trigger pre-flight or verification steps. | Draft |
| NFR-003 | The postmortem template is completable in under 30 minutes for a typical incident. | Draft |
| NFR-004 | Enrichment extends the existing `service-inventory.json` schema without removing or restructuring existing fields. | Draft |
| NFR-005 | All new governance documents are consistent in style with existing architecture docs and runbooks. | Draft |

### Constraints

| ID | Requirement | Status |
|---|---|---|
| C-001 | No automated drift detection (comparing live system state to documentation automatically) — explicitly deferred. | Draft |
| C-002 | No n8n workflow automation for change approval — deferred. | Draft |
| C-003 | No monitoring or alerting on service health — separate feature. | Draft |
| C-004 | No changes to backup, restic, or audit.sh scope — separate features. | Draft |
| C-005 | Follow the kg-automation standing requirement: features that change deployed services, credentials, or data flows must update `docs/design/architecture/` and `docs/design/architecture/data/` as part of the same work (not a separate task). | Draft |
| C-006 | Follow the F015-established change-control INDEX.md maintenance rule: any doc/directory addition or move must update `docs/INDEX.md` in the same feature branch. | Draft |
| C-007 | The Tier 0 Hard Lock is absolute — cannot be overridden by urgency or explicit user instruction. This is a constitutional-level constraint. | Draft |

## Success Criteria

- **Risk taxonomy in place**: Five-tier taxonomy defined in machine-readable JSON, each tier has a named guardrail protocol, referenced from CLAUDE.md and change-control.md.
- **Service inventory enriched**: All current services have dependencies, health checks, config pointers, and risk_tier labels. Vikunja specifically captures its dependency on tailscale-serve port 443.
- **Pre-flight checklists documented**: Separate checklist variants for Tier 0/1 and Tier 2. Walkthrough of the origin incident demonstrates the checklist catches the port 443 gap.
- **Post-change verification defined**: Per-tier verification protocol referencing health-check endpoints. Rollback trigger condition defined.
- **CLAUDE.md enforcement active**: Per-tier guardrail rules added matching existing style. Tier 0 Hard Lock is explicit and unambiguous. Tier 3/4 changes have no added friction.
- **Postmortem process operational**: Template created. Origin incident (Vikunja UFW outage 2026-04-03) postmortem completed as the first real entry. Follow-on actions tracked with Vikunja task references.
- **Documentation standards formalized**: Principle canonically recorded in Felix constitution with summary in CLAUDE.md.
- **Architecture docs updated**: README, change-control, security-posture, service-inventory.md, physical-topology.md all reflect the new governance framework. INDEX.md updated per F015 rule.
- **No existing content broken**: All current architecture doc content preserved. Enrichment extends, never replaces.

## Key Entities

- **Risk Tier**: One of 5 tiers (0-4) classifying a change by blast radius, reversibility, and lockout potential. Stored as `risk_tier` label on service records and as the taxonomy definition in `change-risk-taxonomy.json`.
- **Guardrail Protocol**: Named enforcement behavior per tier (Hard Lock, Verification Required, Snapshot Required, Standard, Auto-Commit) governing what AI may do autonomously.
- **Pre-Flight Checklist**: Mandatory assessment before Tier 0/1/2 changes covering dependency impact, rollback planning, and operator availability.
- **Post-Change Verification**: Protocol for confirming all dependent services are healthy after a change, using health-check endpoints from the enriched inventory.
- **Postmortem**: Blameless incident analysis following a defined template, stored at `docs/issues/postmortems/YYYY-MM-DD_incident-slug.md`.
- **Service Dependency**: A specific port/interface/service that another service requires to function (e.g., Vikunja depends on tailscale-serve:443).

## Assumptions

1. **Service inventory is the existing `data/service-inventory.json`** — enrichment adds fields to existing service records, following the JSON-as-authoritative pattern already established.
2. **Health-check endpoints exist for most services** — where they don't, the inventory explicitly marks "no health check" and verification protocol flags these as requiring manual confirmation.
3. **Felix constitution is editable** — documentation standards principle can be added directly; `spec-kitty constitution sync` will propagate to derived artifacts.
4. **Vikunja tasks for follow-on actions are created manually** — the postmortem template includes a placeholder format for task references, but actual Vikunja task creation is out of scope for this feature.
5. **The origin incident facts are well-understood** — the UFW port 443 → Tailscale serve → Vikunja dependency chain has been validated in `docs/runbooks/vikunja-ops.md` and `scripts/office2/security-monitor/configure-ufw.sh`.
6. **Mermaid is the standard diagram format** — per the existing `.view.md` pattern in architecture docs.

## Out of Scope

- Automated drift detection (comparing live system to documentation automatically)
- n8n workflow automation for change approval
- Full ITIL-style change management — too heavy for a solo-operator system
- Monitoring or alerting on service health (separate feature)
- Changes to backup, restic, or audit.sh scope
- Automatic Vikunja task creation from postmortem follow-on actions

## Dependencies

- **Prerequisite (completed)**: F015 (Documentation Architecture Rationalization) — resolved path dependencies, created INDEX.md and the Divio classification standard, corrected frontmatter across docs.
- **Downstream**: Future features that deploy services or modify infrastructure will be governed by this framework.
- **Standing requirement**: Architecture doc updates are part of this feature's implementation, not a separate task (per CLAUDE.md standing directive + F015 change-control INDEX.md rule).

## Notes

- **Service inventory enrichment is the foundational deliverable** — everything else (checklists, verification, CLAUDE.md rules) references it.
- **Tier 0 Hard Lock wording in CLAUDE.md is the highest-stakes enforcement addition** — get the wording precise and unambiguous.
- **The origin incident postmortem validates both the template and the pre-flight checklist** — it's the proof that the framework works.
- **Study existing patterns during planning**: JSON schema extension (extend, don't replace), CLAUDE.md rule style (match existing format), architecture README table conventions.
