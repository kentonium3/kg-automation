---
description: Work packages for F016 Change Control Governance & Incident Management
---

# Work Packages: Change Control Governance & Incident Management

**Inputs**: Design documents from `/kitty-specs/016-change-control-governance/`
**Prerequisites**: plan.md (required), spec.md (16 FRs), research.md (existing patterns), data-model.md (JSON schemas), quickstart.md (validation approach)

**Tests**: Origin incident walkthrough (FR-016) validates framework end-to-end. Manual CLAUDE.md Tier 0 behavior test.

**Organization**: 43 subtasks (`T001`–`T043`) across 9 work packages (`WP01`–`WP09`). Each WP has disjoint `owned_files`.

---

## Work Package WP01: Create Risk Taxonomy (Priority: P0)

**Goal**: Create the five-tier change-risk taxonomy as machine-readable JSON.
**Independent Test**: `change-risk-taxonomy.json` parses as valid JSON with 5 tiers, each having name/scope/guardrail_protocol.
**Prompt**: `tasks/WP01-create-risk-taxonomy.md`
**Requirement Refs**: FR-001

### Included Subtasks

- [x] T001 Create `docs/design/architecture/data/change-risk-taxonomy.json` with schema metadata
- [x] T002 Define all 5 tiers (0-4) with name, scope, guardrail_protocol, guardrail_description, examples
- [x] T003 Set Tier 0 `overridable: false`; Tiers 1-4 `overridable: true`
- [x] T004 Validate JSON parses correctly and all fields populated

### Dependencies

None — this is the foundational WP that everything else references.

### Risks & Mitigations

- Tier scope boundaries are subjective at edges. Mitigated by providing explicit examples per tier.

---

## Work Package WP02: Enrich Service Inventory + Network Topology (Priority: P0)

**Goal**: Extend all 11 service records with dependencies, health checks, config files, and risk_tier fields. Add Tailscale serve proxy configuration to network topology.
**Independent Test**: All 11 services have 4 new field groups populated. Vikunja specifically captures tailscale-serve:443 dependency. Schema version 1.1.
**Prompt**: `tasks/WP02-enrich-service-inventory.md`
**Requirement Refs**: FR-002, FR-003, NFR-004

### Included Subtasks

- [x] T005 Add `risk_tier` field (integer 0-4) to all 11 service records
- [x] T006 [P] Add `dependencies` array to all service records with specific targets
- [x] T007 [P] Add `health_check` object to all service records (method, endpoint, expected, timeout)
- [x] T008 [P] Add `config_files` array to services that have configuration files
- [x] T009 Verify Vikunja captures dependency on `tailscale-serve:443`
- [x] T010 Add `tailscale_serve` config to `network-topology.json` port 443 entry
- [x] T011 Bump `schema_version` to `"1.1"`, set `updated_by: "F016"`

### Dependencies

Depends on WP01 (risk_tier values reference the taxonomy tier numbers).

### Risks & Mitigations

- Some services may have undocumented dependencies. Mitigated by capturing best-known state and flagging gaps.
- Health-check endpoints may not exist for all services. Use `method: "none"` where absent.

---

## Work Package WP03: Governance Runbooks — Checklists + Verification (Priority: P1)

**Goal**: Create the pre-flight checklist and post-change verification protocol governance runbooks.
**Independent Test**: Both files exist with correct doc_type/audience frontmatter. Tier 0/1 checklist includes dependency lookup, rollback, operator availability. Verification protocol references health-check endpoints.
**Prompt**: `tasks/WP03-governance-runbooks.md`
**Requirement Refs**: FR-004, FR-005

### Included Subtasks

- [x] T012 Create `docs/runbooks/governance/pre-flight-checklist.md` with frontmatter
- [x] T013 Define Tier 0/1 checklist: port/interface impact, dependent service lookup, rollback procedure, operator availability, verification plan
- [x] T014 Define Tier 2 checklist (lighter): backup confirm, health check, rollback plan
- [x] T015 Create `docs/runbooks/governance/post-change-verification.md` with frontmatter
- [x] T016 Define per-tier verification steps referencing service inventory health-check endpoints
- [x] T017 Define rollback trigger condition on verification failure

### Dependencies

Depends on WP01 (checklists reference tier definitions) and WP02 (checklists reference service inventory dependencies and health checks).

### Risks & Mitigations

- Checklist must balance thoroughness with usability. Mitigated by NFR-003 spirit (completable quickly).

---

## Work Package WP04: CLAUDE.md Guardrail Rules + Doc Standards Pointer (Priority: P1)

**Goal**: Add per-tier guardrail enforcement rules to CLAUDE.md. Include documentation standards summary with pointer to constitution.
**Independent Test**: CLAUDE.md has "Change Control Guardrails" section. Tier 0 Hard Lock is explicit and unoverridable. Rules reference taxonomy by path. Doc standards pointer present.
**Prompt**: `tasks/WP04-claudemd-guardrails.md`
**Requirement Refs**: FR-006, FR-009, NFR-001, NFR-002

### Included Subtasks

- [ ] T018 Add new "Change Control Guardrails" section to CLAUDE.md after Permissions
- [ ] T019 Write Tier 0 Hard Lock rule — explicit, unambiguous, unoverridable by urgency or instruction
- [ ] T020 Write Tier 1-4 guardrail rules referencing taxonomy file path
- [ ] T021 Add documentation standards summary + pointer to Felix constitution (FR-009)
- [ ] T022 Verify rules cause zero friction for Tier 3/4 changes (NFR-002)

### Dependencies

Depends on WP01 (taxonomy must exist to reference) and WP03 (checklist must exist to reference from rules).

### Risks & Mitigations

- Tier 0 Hard Lock wording is the highest-stakes addition. Must be precise enough to prevent override while still enabling script-generation assistance.

---

## Work Package WP05: Postmortem Template + Origin Incident + Walkthrough (Priority: P1)

**Goal**: Create the postmortem template, complete the origin incident postmortem, and walk the pre-flight checklist through the origin scenario to validate it catches the port 443 gap.
**Independent Test**: Template exists. Origin postmortem completed with all sections. Walkthrough documents that checklist catches the dependency gap.
**Prompt**: `tasks/WP05-postmortem-origin-incident.md`
**Requirement Refs**: FR-007, FR-008, FR-016, NFR-003

### Included Subtasks

- [x] T023 Create `docs/runbooks/governance/incident-postmortem-template.md` with all required sections
- [x] T024 Define template: summary, timeline, root cause chain, impact, what went well, what failed, follow-on actions
- [x] T025 Create `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md`
- [x] T026 Complete origin incident postmortem with all root causes, follow-on actions (Vikunja task placeholders)
- [x] T027 Walk pre-flight checklist through origin incident: UFW port 443 change scenario
- [x] T028 Document walkthrough result proving checklist catches the port 443 dependency gap

### Dependencies

Depends on WP02 (origin incident references Vikunja's dependency data from enriched inventory) and WP03 (walkthrough validates the pre-flight checklist).

### Risks & Mitigations

- Template must be lightweight enough for 30-min completion (NFR-003). Mitigated by studying PagerDuty/Atlassian lightweight formats during implementation.

---

## Work Package WP06: Documentation Standards — Constitution (Priority: P2)

**Goal**: Add the documentation standards principle to the Felix constitution as Directive 5.
**Independent Test**: FELIX-CONSTITUTION.md has Directive 5. .kittify/constitution/constitution.md has matching content. spec-kitty constitution sync completes without error.
**Prompt**: `tasks/WP06-constitution-doc-standards.md`
**Requirement Refs**: FR-009

### Included Subtasks

- [x] T029 Add "Directive 5: Documentation Standards" to `docs/constitution/FELIX-CONSTITUTION.md`
- [x] T030 Add matching content to `.kittify/constitution/constitution.md`
- [x] T031 Run `spec-kitty constitution sync` and verify derived artifacts update cleanly

### Dependencies

None — constitution edit is independent of other F016 deliverables.

### Risks & Mitigations

- Constitution sync may produce unexpected changes. Mitigated by reviewing diff before committing.

---

## Work Package WP07: Service Dependency Diagram (Priority: P2)

**Goal**: Produce a Mermaid service dependency diagram for office2 showing all services with dependency edges and risk tier labels.
**Independent Test**: `.view.md` file exists with valid Mermaid graph. All 11 services shown. Port 443 → Tailscale serve → Vikunja chain visible.
**Prompt**: `tasks/WP07-service-dependency-diagram.md`
**Requirement Refs**: FR-010

### Included Subtasks

- [x] T032 Create `docs/design/architecture/service-dependencies.view.md` with frontmatter
- [x] T033 Write Mermaid `graph LR` showing all 11 services with dependency edges from enriched inventory
- [x] T034 Include risk_tier labels on nodes; ensure port 443 Tailscale→Vikunja chain is visible

### Dependencies

Depends on WP02 (diagram uses enriched dependency data from service inventory).

### Risks & Mitigations

- Complex graph with 11 services may be hard to read. Mitigated by using subgraphs to group by tier.

---

## Work Package WP08: Architecture Doc Updates + Markdown Views (Priority: P2)

**Goal**: Update README, change-control, security-posture, service-inventory.md, and physical-topology.md to reflect the new governance framework and enriched JSON sources.
**Independent Test**: All 5 files updated. README references new governance files + taxonomy in Data Files table. change-control references checklist/verification. Markdown views match enriched JSON.
**Prompt**: `tasks/WP08-architecture-doc-updates.md`
**Requirement Refs**: FR-011, FR-012, FR-013, FR-014

### Included Subtasks

- [ ] T035 Update `docs/design/architecture/README.md` (governance refs, taxonomy in Data Files, diagram ref)
- [ ] T036 Update `docs/design/architecture/change-control.md` (risk taxonomy, checklist, verification protocol refs)
- [ ] T037 Update `docs/design/architecture/security-posture.md` (reference change control governance)
- [ ] T038 Update `docs/design/architecture/service-inventory.md` to match enriched JSON
- [ ] T039 Update `docs/design/architecture/physical-topology.md` (Tailscale serve, diagram ref)

### Dependencies

Depends on WP01 (taxonomy), WP02 (enriched inventory), WP03 (checklist/verification), WP07 (diagram).

### Risks & Mitigations

- service-inventory.md update is large (11 services with new fields). Mitigated by using the JSON as source of truth and rendering systematically.

---

## Work Package WP09: INDEX.md Update (Priority: P2)

**Goal**: Update docs/INDEX.md with all new governance files, machine-readable artifacts, and postmortem entries per the F015 change-control INDEX.md maintenance rule.
**Independent Test**: INDEX.md lists all new files from F016. Governance runbooks section expanded. Postmortem entry present.
**Prompt**: `tasks/WP09-index-md-update.md`
**Requirement Refs**: FR-015, C-006

### Included Subtasks

- [ ] T040 Add governance runbook files (pre-flight-checklist, post-change-verification, incident-postmortem-template) to INDEX.md runbooks section
- [ ] T041 Add `change-risk-taxonomy.json` to machine-readable artifacts section
- [ ] T042 Add `2026-04-03-vikunja-ufw-outage.md` entry to postmortems section
- [ ] T043 Add `service-dependencies.view.md` entry to architecture section

### Dependencies

Depends on WP01, WP02, WP03, WP05, WP06, WP07, WP08 (needs complete file list to be accurate).

### Risks & Mitigations

- INDEX.md must be last WP to ensure all new files are captured.

---

## Execution Order

**Phase 0 (parallel starters)**: WP01, WP06

**Phase 1 (after WP01)**: WP02 (depends on WP01)

**Phase 2 (after WP02)**: WP03 (depends on WP01 + WP02), WP05 (depends on WP02 + WP03), WP07 (depends on WP02)

**Phase 3 (after WP03)**: WP04 (depends on WP01 + WP03)

**Phase 4 (after all content WPs)**: WP08 (depends on WP01-03, WP07), WP09 (depends on all)

## Size Validation

| WP | Subtasks | Est. Lines |
|---|---|---|
| WP01 | 4 | ~200 |
| WP02 | 7 | ~450 |
| WP03 | 6 | ~350 |
| WP04 | 5 | ~300 |
| WP05 | 6 | ~450 |
| WP06 | 3 | ~200 |
| WP07 | 3 | ~250 |
| WP08 | 5 | ~350 |
| WP09 | 4 | ~200 |

Total: 43 subtasks across 9 WPs. All within 200-500 line range.
