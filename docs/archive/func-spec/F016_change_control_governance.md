---
title: "F016: Change Control Governance & Incident Management"
doc_type: func-spec
status: draft
---

# F016: Change Control Governance & Incident Management

**Version**: 1.3
**Priority**: HIGH
**Type**: Governance & Infrastructure

---

## Executive Summary

On 2026-04-03, a UFW firewall hardening change blocked port 443, taking down Vikunja
for approximately 8 hours. The change was correct in its stated scope but failed to
account for Tailscale serve's dependency on that port. No pre-flight dependency analysis
was performed, no post-change verification covered all services, and no incident
postmortem process existed to capture lessons and drive remediation.

Current gaps:
- ❌ No risk-tiered change control framework — all changes treated equally regardless of blast radius
- ❌ Service inventory exists but lacks dependency and health check data needed for pre-flight analysis
- ❌ No pre-flight checklist enforced before high-risk changes
- ❌ No post-change verification protocol requiring all dependent services be confirmed
- ❌ CLAUDE.md contains no change control enforcement rules
- ❌ No incident postmortem template or process
- ❌ Documentation standards (machine-readable vs human-readable vs diagrams) not formally defined

This spec establishes a lightweight five-tier change control framework, enriches the
existing architecture documentation with dependency and health data, adds CLAUDE.md
enforcement rules, and creates an incident postmortem process.

---

## Problem Statement

**Current State (INCOMPLETE):**
```
Architecture Documentation
├─ ✅ service-inventory.json — services, versions, ports, paths
├─ ✅ network-topology.json — Tailscale IPs, port assignments
├─ ✅ change-control.md — update protocol after each feature
├─ ❌ No service dependency mapping (what depends on what port/service)
└─ ❌ No health check endpoints captured

Change Control
├─ ❌ No risk taxonomy — all changes treated identically
├─ ❌ No pre-flight checklist for high-blast-radius changes
└─ ❌ No post-change verification protocol

CLAUDE.md Enforcement
└─ ❌ No rules applying tiered guardrail protocols before changes

Incident Management
└─ ❌ DOESN'T EXIST — no postmortem template or process

Documentation Standards
└─ ❌ No formal policy on machine-readable vs human-readable vs diagrams
```

**Target State (COMPLETE):**
```
Architecture Documentation
├─ ✅ service-inventory.json — enriched with dependencies, health checks, risk_tier labels
├─ ✅ network-topology.json — enriched with Tailscale serve configuration
├─ ✅ README.md — updated with governance docs, new data file, postmortems reference
└─ ✅ All markdown views match enriched JSON sources

Change Control
├─ ✅ Five-tier risk taxonomy (Tier 0–4) defined, machine-readable
├─ ✅ Per-tier guardrail protocols defined and enforced
└─ ✅ Post-change verification protocol — confirms all dependent services

CLAUDE.md Enforcement
└─ ✅ Guardrail protocol rules per tier — Hard Lock through Auto-Commit

Incident Management
├─ ✅ Postmortem template capturing root cause, timeline, impact, actions
└─ ✅ F015 origin incident documented using new template

Documentation Standards
└─ ✅ Formal policy on when to use machine-readable, narrative, and diagrams
```

---

## CRITICAL: Study These Files FIRST

**Before implementation, spec-kitty planning phase MUST read and understand:**

1. **Existing Architecture Documentation System**
   - Find `docs/design/architecture/README.md`
   - Understand the existing JSON-as-authoritative-record pattern
   - Note the existing `data/service-inventory.json` schema — enrichment must extend it, not replace it
   - Note `data/network-topology.json` — Tailscale serve config belongs here

2. **Existing Change Control Protocol**
   - Find `docs/design/architecture/change-control.md`
   - Understand what update steps are already required
   - Note what gaps exist — risk tiers and per-tier guardrail protocols are absent

3. **CLAUDE.md**
   - Find `CLAUDE.md` in repo root
   - Understand current Claude Code behavioral rules
   - Note where change control enforcement rules should be inserted
   - Study the pattern used for existing rules to match style

4. **Felix Constitution**
   - Find constitution document in `.agents/` or `docs/`
   - Understand existing governance principles
   - Note how new documentation standards principle should align

5. **Incident Origin**
   - Find `docs/runbooks/vikunja-ops.md` — updated post-incident with Tailscale serve fix
   - Find `scripts/office2/security-monitor/configure-ufw.sh` — the change that caused the incident
   - Understand what pre-flight analysis would have caught the port 443 gap

---

## Functional Requirements

### FR-1: Five-Tier Risk Taxonomy

**What it must do:**
- Define five risk tiers (Tier 0 through Tier 4) based on blast radius, reversibility,
  and lockout potential
- Assign a specific guardrail protocol to each tier governing what AI may do autonomously
- Be stored in a machine-readable file consumable by tooling and referenced by CLAUDE.md
- Include a `risk_tier` label convention so individual services and components can
  self-declare their tier

**Tier definitions:**

| Tier | Name | Scope | AI Guardrail Protocol |
|------|------|-------|----------------------|
| 0 | Foundational / Host | SSH, sudoers, UFW, kernel, root OS | **Hard Lock** — AI generates script only; human executes manually |
| 1 | Connectivity / Fabric | Tailscale, Docker networks, proxy/DNS, API gateways | **Verification Required** — AI must confirm connectivity before and after |
| 2 | Application / State | DB schemas, service env files, Docker Compose volumes | **Snapshot Required** — AI must trigger backup before modifying |
| 3 | Logic / Workflow | Python scripts, agent prompts, cron jobs, logic flows | **Standard** — AI may modify and test via dry-run or sandbox |
| 4 | Schema / Metadata | CLAUDE.md, READMEs, comments, logging verbosity | **Auto-Commit** — AI has full autonomy to update and sync |

**Business rules:**
- The Tier 0 Hard Lock is absolute — Claude Code never executes Tier 0 commands directly,
  regardless of user urgency or explicit instruction to proceed
- Tier 0 includes but is not limited to: `ufw`, `iptables`, `sshd_config`, `sudoers`,
  `chmod`/`chown` on system files, kernel parameters
- `risk_tier` labels in service inventory and Docker Compose files are the machine-readable
  expression of this taxonomy

**Success criteria:**
- [ ] Risk taxonomy defined in a machine-readable file in the architecture data directory
- [ ] Each tier has a clear name, scope definition, and guardrail protocol
- [ ] `risk_tier` label convention documented for use in service inventory and Docker Compose
- [ ] UFW and SSH config correctly classified as Tier 0
- [ ] Tailscale serve correctly classified as Tier 1
- [ ] Vikunja application config correctly classified as Tier 2

---

### FR-2: Service Inventory Enrichment

**What it must do:**
- Extend the existing `data/service-inventory.json` schema with dependency, health check,
  config file pointer, and `risk_tier` label fields
- Every service record must declare what ports/interfaces it depends on
- Every service record must include a health check endpoint where one exists
- Config file locations captured as pointers (paths only — not duplicated content)
- Tailscale serve configuration captured as declared infrastructure state in network-topology.json

**Business rules:**
- Enrichment must extend the existing schema — do not replace or restructure existing fields
- Config file pointers are paths to where the application stores its own config, not copies
- Dependencies must be specific enough to support pre-flight impact analysis
  (e.g., "tailscale-serve:443" not just "tailscale")
- `risk_tier` value on a service record reflects the tier of that service's configuration —
  not the tier of the host it runs on

**Success criteria:**
- [ ] All current services have dependency fields populated
- [ ] All current services have health check endpoints where applicable
- [ ] Config file pointers present for all services with configuration files
- [ ] `risk_tier` label present on all service records
- [ ] Tailscale serve proxy configuration captured in network-topology.json
- [ ] Vikunja record specifically captures its dependency on tailscale-serve port 443
- [ ] All markdown views updated to reflect enriched data

---

### FR-3: Pre-Flight Checklist

**What it must do:**
- Define a mandatory checklist for Tier 0 and Tier 1 changes, and a lighter checklist
  for Tier 2 changes
- Tier 0/1 checklist must include: port/interface impact, dependent service lookup
  (via service inventory), rollback procedure, post-change verification plan
- Tier 0 checklist must confirm the operator is present and available to respond
  to issues before the change is applied — not a maintenance window constraint,
  but an availability check appropriate for a solo operator
- Applied to the F015 origin incident, this checklist must have caught the port 443 gap

**Business rules:**
- Deployment timing for this system reflects solo-operator reality: changes are
  best applied when the operator is present and available to respond, which is
  typically during working hours. Evening deployment may be appropriate when
  daytime commitments preclude availability. Enterprise "maintenance window"
  conventions do not apply.

**Success criteria:**
- [ ] Pre-flight checklist documented and stored in the governance directory
- [ ] Separate checklist variants for Tier 0/1 and Tier 2
- [ ] Checklist is referenced from CLAUDE.md and change-control.md
- [ ] Checklist walkthrough for the F015 origin incident demonstrates it would have
      caught the missing port 443 rule

---

### FR-4: Post-Change Verification Protocol

**What it must do:**
- Define verification steps required after Tier 0, 1, and 2 changes
- Verification must check all services listed as dependent on affected ports/interfaces
  using health check endpoints from the enriched service inventory
- Tier 1 verification must include a connectivity confirmation before and after
  (consistent with the Tier 1 guardrail protocol)
- Protocol must define the rollback trigger condition if verification fails

**Success criteria:**
- [ ] Post-change verification protocol documented per tier
- [ ] Protocol references service inventory health check endpoints
- [ ] Rollback trigger condition defined
- [ ] Protocol referenced from change-control.md

---

### FR-5: CLAUDE.md Enforcement Rules

**What it must do:**
- Add rules to CLAUDE.md requiring Claude Code to identify the risk tier of any
  requested change before proceeding
- Implement per-tier guardrail protocols:
  - **Tier 0**: Generate script only, present to operator for manual execution — never execute directly
  - **Tier 1**: Confirm connectivity before and after; surface dependent services from inventory
  - **Tier 2**: Confirm backup/snapshot exists before modifying
  - **Tier 3**: Proceed with dry-run or sandbox validation where available
  - **Tier 4**: Proceed autonomously
- Rules must reference the risk taxonomy file, not duplicate it inline
- Rules must not cause excessive friction on Tier 3 or Tier 4 changes

**Business rules:**
- The Tier 0 Hard Lock cannot be overridden by urgency framing or explicit user instruction
  to execute directly — the protocol is to generate and present, not execute
- Rules should be additive to existing CLAUDE.md content, matching its style

**Success criteria:**
- [ ] CLAUDE.md updated with per-tier guardrail rules
- [ ] Tier 0 Hard Lock rule explicit and unambiguous
- [ ] Rules reference taxonomy and checklist by file location
- [ ] Rules match style and format of existing CLAUDE.md content
- [ ] Test scenario (e.g., "add UFW rule") causes Claude Code to apply Tier 0 protocol

---

### FR-6: Incident Postmortem Template

**What it must do:**
- Define a standard postmortem format capturing: incident summary, timeline, root cause
  chain, impact, what went well, what failed, and required follow-on actions
- Follow-on actions structured as trackable items linkable to Vikunja tasks
- Blameless in tone — focus on system and process gaps
- Required follow-on actions must distinguish: immediate fixes, process changes,
  tooling improvements, documentation updates
- The F015 origin incident (Vikunja outage 2026-04-03) must be documented using
  the template as the first real postmortem

**Success criteria:**
- [ ] Postmortem template created and stored in the repo
- [ ] Template location documented in architecture README
- [ ] F015 origin incident postmortem completed using the template
- [ ] Postmortem includes all root causes identified in this spec
- [ ] Follow-on actions from origin incident captured with Vikunja task references

---

### FR-7: Documentation Standards Principle

**What it must do:**
- Define a formal project-wide standard for when to use machine-readable files,
  human-readable narrative, and diagrams
- Be added to the Felix constitution or CLAUDE.md as a standing principle
- Address: config/inventory data (machine-readable), architecture decisions and
  runbooks (narrative), system structure and relationships (diagrams preferred)
- Diagrams are the preferred format for conveying system structure, data flows,
  service dependencies, and network topology

**Business rules:**
- Machine-readable files are the authoritative record; narrative documents reference them
- Config file pointers in inventory are paths only — content is never duplicated
- Diagrams must be consistent with machine-readable sources; when they conflict,
  machine-readable wins
- Proportionality applies — not every config detail requires a prose document

**Success criteria:**
- [ ] Documentation standards principle formally documented
- [ ] Principle added to Felix constitution or CLAUDE.md
- [ ] Architecture README updated to reference the principle
- [ ] A service dependency diagram for office2 produced as demonstration

---

## Architecture Documentation Updates

F015 changes the architecture documentation system itself. Update the following as
part of implementation — not as a separate task.

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Add `dependencies`, `health_check`, `config_files`, `risk_tier` fields to all service records |
| `data/network-topology.json` | Add Tailscale serve configuration as declared state |
| `data/hardware-inventory.json` | N/A |
| `data/credential-manifest.json` | N/A |
| `data/data-flows.json` | N/A |

### Markdown Updates Required

| File | Change |
|---|---|
| `docs/design/architecture/README.md` | Add governance docs to Documents table; add change-risk-taxonomy.json to Data Files table; add postmortems/ directory reference |
| `service-inventory.md` | Update to reflect enriched JSON |
| `change-control.md` | Add risk taxonomy reference, pre-flight checklist reference, verification protocol |
| `security-posture.md` | Reference new change control governance |
| `physical-topology.md` | Add service dependency diagram |

### New Files Required

| File | Purpose |
|---|---|
| `docs/design/architecture/data/change-risk-taxonomy.json` | Machine-readable five-tier taxonomy with guardrail protocol definitions |
| `docs/runbooks/governance/pre-flight-checklist.md` | Pre-flight checklists for Tier 0/1 and Tier 2 |
| `docs/runbooks/governance/post-change-verification.md` | Per-tier verification protocol |
| `docs/runbooks/governance/incident-postmortem-template.md` | Reusable postmortem template |
| `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md` | First postmortem — F015 origin incident |

**Success criteria for this section:**
- [ ] All affected JSON files updated with `updated_by: "F015"`
- [ ] Markdown views match JSON sources
- [ ] Mermaid diagram added showing office2 service dependencies

---

## Out of Scope

**Explicitly NOT included in this feature:**
- ❌ Automated drift detection — comparing live system state to documentation automatically
  (future agent feature; noted as on-horizon in project planning)
- ❌ n8n workflow automation for change approval — deferred
- ❌ Full ITIL-style change management — too heavy for this scale
- ❌ Monitoring or alerting on service health — separate feature
- ❌ Changes to backup, restic, or audit.sh scope — separate features

---

## Success Criteria

**Complete when:**

### Change Control Framework
- [ ] Five-tier taxonomy defined, machine-readable, referenced from CLAUDE.md
- [ ] Pre-flight checklists documented for Tier 0/1 and Tier 2
- [ ] Post-change verification protocol documented per tier
- [ ] CLAUDE.md updated with per-tier guardrail rules matching existing style
- [ ] Tier 0 Hard Lock rule explicit and unambiguous

### Service Inventory
- [ ] All services enriched with dependency, health check, config pointer, and risk_tier fields
- [ ] Tailscale serve captured as declared infrastructure state
- [ ] Markdown views match enriched JSON

### Incident Management
- [ ] Postmortem template created
- [ ] Origin incident postmortem completed using template
- [ ] Follow-on actions captured with Vikunja task references

### Documentation Standards
- [ ] Standards principle formally documented
- [ ] Architecture README updated
- [ ] office2 service dependency diagram produced

### Quality
- [ ] No existing architecture doc content broken or removed
- [ ] All new governance docs consistent in style with existing docs
- [ ] CLAUDE.md rules proportional — Tier 3/4 changes have no added friction

---

## Architecture Principles

### Five-Tier Guardrail Model

**AI autonomy is inversely proportional to blast radius:**
- Tier 0 (Host/Foundational): Zero autonomy — Hard Lock, human executes
- Tier 1 (Fabric/Connectivity): Constrained autonomy — verify before and after
- Tier 2 (Application/State): Protected autonomy — snapshot before modifying
- Tier 3 (Logic/Workflow): Standard autonomy — dry-run where possible
- Tier 4 (Schema/Metadata): Full autonomy — auto-commit

### Solo Operator Reality

**Change timing reflects operator availability, not enterprise maintenance windows:**
- Changes are best applied when the operator is present and can respond to issues
- For this system, that is typically during working hours
- Evening deployment is appropriate when daytime commitments preclude availability
- The pre-flight checklist confirms operator availability, not a scheduled window

### Machine-Readable as Authoritative Record

**JSON files are the source of truth:**
- All inventory, topology, and taxonomy data lives in structured files
- Markdown documents are views over that data
- When they conflict, JSON wins

### Diagrams as Communication Layer

**Visual representations complement machine-readable data:**
- Preferred for system structure, service dependencies, data flows, network topology
- Generated from or kept consistent with JSON sources

---

## Constitutional Compliance

✅ **Safety-first / halt-and-alert**
- Tier 0 Hard Lock implements the strongest form of this principle —
  AI halts and presents, never executes

✅ **Earned autonomy through gates**
- Per-tier guardrail protocols formalize the autonomy gates already established
  in the Felix constitution

✅ **Document-first / GitOps pattern**
- All governance artifacts version-controlled; machine-readable taxonomy follows
  established JSON-authoritative pattern

✅ **System documentation comprehensive and current**
- Service inventory enrichment and postmortem process directly serve this principle

---

## Risk Considerations

**Risk: Service inventory enrichment is incomplete on first pass**
- Some services may have undocumented dependencies or no health check endpoint
- Mitigation: Capture best-known state; flag gaps explicitly rather than leave blank;
  iterate as gaps are discovered

**Risk: CLAUDE.md Tier 0 Hard Lock causes friction for routine security work**
- Kent may want to make firewall changes with Claude Code assistance
- Mitigation: Hard Lock means Claude generates the script for review and copy-paste;
  this is assistance, not obstruction — the friction is intentional and appropriate

**Risk: Postmortem process becomes bureaucratic overhead**
- Template too heavy = won't be used
- Mitigation: Template should be completable in under 30 minutes; planning phase
  should study lightweight formats (PagerDuty, Atlassian) for calibration

---

## Notes for Implementation

**Pattern Discovery (Planning Phase):**
- Study existing `data/service-inventory.json` schema → extend, do not replace
- Study `docs/design/architecture/change-control.md` → understand what already exists
- Study CLAUDE.md existing rule style → match format for new guardrail rules
- Study Felix constitution → confirm where documentation standards principle belongs
- Study `docs/design/architecture/README.md` → understand Documents and Data Files
  table conventions before adding new entries

**Focus Areas:**
- Service inventory enrichment is the foundational deliverable — everything else references it
- Tier 0 Hard Lock rule in CLAUDE.md is the highest-stakes enforcement addition —
  get the wording precise and unambiguous
- The origin incident postmortem validates both the template and the pre-flight checklist

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-04 | Initial draft — post-incident retrospective on Vikunja UFW outage |
| 1.1 | 2026-04-04 | Adopted five-tier taxonomy (Tier 0–4) with named guardrail protocols; added solo-operator deployment timing principle |
| 1.2 | 2026-04-04 | Added docs/design/architecture/README.md to Markdown Updates Required table; added README study pointer to Notes for Implementation |

---

**END OF SPECIFICATION**
