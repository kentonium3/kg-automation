---
work_package_id: WP08
title: Architecture Doc Updates + Markdown Views
dependencies:
- WP01
- WP02
- WP03
- WP07
requirement_refs:
- FR-011
- FR-012
- FR-013
- FR-014
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 016-change-control-governance-WP08-merge-base
base_commit: 8779a194b2a9839eb56461b7f88c3f1692504564
created_at: '2026-04-05T23:48:04.302698+00:00'
subtasks:
- T035
- T036
- T037
- T038
- T039
phase: Phase 3 - Documentation
assignee: ''
agent: "claude"
shell_pid: "64025"
history:
- at: '2026-04-05T23:00:03Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/architecture/
execution_mode: code_change
owned_files:
- docs/design/architecture/README.md
- docs/design/architecture/change-control.md
- docs/design/architecture/security-posture.md
- docs/design/architecture/service-inventory.md
- docs/design/architecture/physical-topology.md
---

# Work Package Prompt: WP08 — Architecture Doc Updates + Markdown Views

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or stacked on WP01, WP02, WP03, WP07.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Update 5 architecture documentation files to reflect the new governance framework, enriched JSON data, and new artifacts created by earlier work packages.

**Success criteria**:

- [ ] `README.md` updated with governance runbook files, change-risk-taxonomy.json, service-dependencies.view.md, and postmortems directory reference.
- [ ] `change-control.md` updated with risk taxonomy reference, pre-flight checklist, and post-change verification protocol.
- [ ] `security-posture.md` updated with change control governance framework reference.
- [ ] `service-inventory.md` updated to match enriched JSON (11 services x 4 new field groups).
- [ ] `physical-topology.md` updated with service dependency diagram reference and Tailscale serve proxy details.

## Context & Constraints

This is the narrative documentation companion to the machine-readable enrichment done in WP01-WP03 and the diagram created in WP07. The architecture docs must stay synchronized with their JSON counterparts per the documentation standards principle.

**T038 (service-inventory.md) is the largest subtask**: 11 services each need descriptions of dependencies, health checks, config files, and risk tiers added to the narrative.

**Constraints**:

- Narrative must match JSON source data — no contradictions.
- Existing content should be enhanced, not replaced, unless it conflicts with new data.
- Cross-references to new governance artifacts must use correct relative paths.

**Reference documents**:

- `docs/design/architecture/data/service-inventory.json` (enriched by WP02)
- `docs/design/architecture/data/network-topology.json` (enriched by WP03)
- `docs/design/architecture/data/change-risk-taxonomy.json` (created by WP01)
- `docs/design/architecture/service-dependencies.view.md` (created by WP07)
- `docs/runbooks/governance/` (created by WP05)
- `kitty-specs/016-change-control-governance/plan.md`
- `kitty-specs/016-change-control-governance/data-model.md`

## Subtasks & Detailed Guidance

### Subtask T035 — Update README.md

- **Purpose**: Add new F016 artifacts to the architecture documentation suite index.
- **Steps**:
  1. Open `docs/design/architecture/README.md`.
  2. Add governance runbook files to the Documents table:
     - `docs/runbooks/governance/pre-flight-checklist.md`
     - `docs/runbooks/governance/post-change-verification.md`
     - `docs/runbooks/governance/incident-postmortem-template.md`
  3. Add `change-risk-taxonomy.json` to the Data Files table.
  4. Add `service-dependencies.view.md` to the diagrams/views section.
  5. Add postmortems directory reference (`docs/issues/postmortems/`).
- **Files**: `docs/design/architecture/README.md`
- **Parallel?**: Yes — independent of T036-T039.
- **Notes**: Follow existing table formatting. New entries should include brief descriptions.

### Subtask T036 — Update change-control.md

- **Purpose**: Cross-reference new governance artifacts from the existing change control protocol.
- **Steps**:
  1. Open `docs/design/architecture/change-control.md`.
  2. Add a reference to the risk taxonomy file (`change-risk-taxonomy.json`) — explain that changes are classified by the five-tier taxonomy.
  3. Add a reference to the pre-flight checklist runbook — this is the operational companion to the protocol.
  4. Add a reference to the post-change verification protocol runbook.
  5. These are NEW cross-references from existing protocol text to new governance artifacts. Do not rewrite the existing protocol.
- **Files**: `docs/design/architecture/change-control.md`
- **Parallel?**: Yes — independent of T035, T037-T039.
- **Notes**: Keep additions concise. The change-control.md file defines the protocol; the runbooks provide the operational steps.

### Subtask T037 — Update security-posture.md

- **Purpose**: Reference the new change control governance framework from the security posture document.
- **Steps**:
  1. Open `docs/design/architecture/security-posture.md`.
  2. Add a section or paragraph referencing the change control governance framework.
  3. Content should be brief:

     > Change control is governed by a five-tier risk taxonomy. See `change-risk-taxonomy.json` and `docs/runbooks/governance/` for the pre-flight checklist, post-change verification protocol, and incident postmortem template.

  4. Place this in the appropriate location within the existing document structure (near operational security or change management content).
- **Files**: `docs/design/architecture/security-posture.md`
- **Parallel?**: Yes — independent of T035-T036, T038-T039.
- **Notes**: Brief addition only. The security posture document references the framework; it does not duplicate it.

### Subtask T038 — Update service-inventory.md

- **Purpose**: Synchronize the narrative service inventory with the enriched JSON. This is the largest subtask.
- **Steps**:
  1. Open `docs/design/architecture/service-inventory.md`.
  2. Read enriched `docs/design/architecture/data/service-inventory.json` for the 4 new field groups per service.
  3. For each of the 11 services, add or update the narrative to describe:
     - **Dependencies**: what each service depends on (other services, ports, paths).
     - **Health checks**: how to verify the service is running correctly (command, expected output).
     - **Config files**: where service configuration lives (paths only, per constitution principle).
     - **Risk tier**: the service's tier from the risk taxonomy and what that implies.
  4. Ensure the narrative is consistent with the JSON data — no contradictions.
  5. Maintain the existing document structure; add new subsections or fields as appropriate.
- **Files**: `docs/design/architecture/service-inventory.md`
- **Parallel?**: Yes — independent of T035-T037, T039. However, this is the largest subtask and may benefit from focused attention.
- **Notes**: 11 services x 4 field groups = significant additions. Prioritize accuracy over prose quality. The JSON is truth.

### Subtask T039 — Update physical-topology.md

- **Purpose**: Add service dependency diagram reference and Tailscale serve proxy details.
- **Steps**:
  1. Open `docs/design/architecture/physical-topology.md`.
  2. Add a reference to the new `service-dependencies.view.md` diagram in an appropriate location.
  3. Add Tailscale serve proxy configuration details from enriched `network-topology.json`:
     - How port 443 is routed through tailscale-serve to vikunja.
     - Any other proxy or routing details from the enriched data.
  4. Ensure the narrative is consistent with `network-topology.json`.
- **Files**: `docs/design/architecture/physical-topology.md`
- **Parallel?**: Yes — independent of T035-T038.
- **Notes**: The physical topology already covers hardware and network layout. The additions extend it with service-level routing and a diagram cross-reference.

## Test Strategy

N/A — governance feature, no automated tests. Manual validation per quickstart.md.

**Manual validation**:

- All 5 files updated with correct cross-references.
- README tables complete with new entries.
- service-inventory.md matches enriched JSON for all 11 services.
- No broken relative paths in cross-references.

## Risks & Mitigations

- **Risk**: T038 (service-inventory.md) is large and error-prone. **Mitigation**: Work service-by-service, cross-checking each against the JSON. Use a checklist of all 11 services.
- **Risk**: Cross-reference paths incorrect. **Mitigation**: Verify all referenced files exist before committing.
- **Risk**: Narrative contradicts JSON data. **Mitigation**: JSON is authoritative; narrative must conform to it.
- **Risk**: Dependencies not yet merged (WP01-03, WP07). **Mitigation**: These are hard dependencies; do not start until all are complete.

## Integration Verification

- [ ] `docs/design/architecture/README.md` lists governance runbooks, change-risk-taxonomy.json, service-dependencies.view.md, and postmortems directory.
- [ ] `docs/design/architecture/change-control.md` references risk taxonomy, pre-flight checklist, and post-change verification.
- [ ] `docs/design/architecture/security-posture.md` references change control governance framework.
- [ ] `docs/design/architecture/service-inventory.md` describes dependencies, health checks, config files, and risk tiers for all 11 services.
- [ ] `docs/design/architecture/physical-topology.md` references service dependency diagram and Tailscale serve proxy details.
- [ ] All cross-reference paths resolve to existing files.
- [ ] service-inventory.md narrative matches service-inventory.json data.

## Review Guidance

- **Key checkpoints**: All 5 files updated. README tables complete. change-control.md references correct files. service-inventory.md matches JSON for all 11 services.
- **Before approving**: Spot-check 3 services in service-inventory.md against the JSON to verify consistency. Verify all cross-reference paths resolve.

## Definition of Done

- All 5 architecture documentation files updated and committed.
- README tables include all new F016 artifacts.
- service-inventory.md fully synchronized with enriched JSON.
- All cross-references resolve to existing files.

## Activity Log

- 2026-04-05T23:50:12Z – unknown – shell_pid=63332 – 5 architecture docs updated with governance references
- 2026-04-05T23:50:14Z – claude – shell_pid=64025 – Started review via workflow command
- 2026-04-05T23:50:16Z – claude – shell_pid=64025 – Review passed: surgical additions to 5 files, no content removed
