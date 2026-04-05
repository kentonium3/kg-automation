---
work_package_id: WP05
title: Postmortem Template + Origin Incident + Walkthrough
dependencies:
- WP02
- WP03
requirement_refs:
- FR-007
- FR-008
- FR-016
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 016-change-control-governance-WP05-merge-base
base_commit: f758ab83480cad22de0facb7565ec4298e890500
created_at: '2026-04-05T23:41:36.249286+00:00'
subtasks:
- T023
- T024
- T025
- T026
- T027
- T028
phase: Phase 2 - Incident Management
assignee: ''
agent: ''
shell_pid: '61151'
history:
- at: '2026-04-05T23:00:03Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/runbooks/governance/
execution_mode: code_change
owned_files:
- docs/runbooks/governance/incident-postmortem-template.md
- docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md
---

# Work Package Prompt: WP05 — Postmortem Template + Origin Incident + Walkthrough

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates frontmatter `base_branch` when the worktree is created. For this WP, base = main.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Create a reusable postmortem template, complete the origin incident postmortem (Vikunja UFW outage), and validate the pre-flight checklist by walking through the origin scenario.

**Success criteria**:

- [ ] `docs/runbooks/governance/incident-postmortem-template.md` exists with all required sections.
- [ ] Template is completable in under 30 minutes (NFR-003).
- [ ] `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md` exists as a complete, real postmortem.
- [ ] Origin postmortem uses blameless tone throughout.
- [ ] Pre-flight checklist walkthrough proves the checklist would have caught the port 443 gap.
- [ ] Walkthrough result documented in the postmortem.

## Context & Constraints

The Vikunja UFW outage on 2026-04-03 is the origin incident that motivated F016. This WP creates the postmortem infrastructure and uses the real incident to validate the governance framework created by WP01-WP03.

**Constraints**:

- NFR-003: Template must be completable in under 30 minutes. Keep sections focused.
- Postmortem must be blameless — no finger-pointing, focus on system gaps.
- Walkthrough must use the actual pre-flight checklist from WP03 and the enriched inventory from WP02.

**Reference documents**:

- `kitty-specs/016-change-control-governance/research.md` (section 6 — origin incident details)
- `docs/runbooks/governance/pre-flight-checklist.md` (WP03)
- `docs/design/architecture/data/service-inventory.json` (WP02)
- `kitty-specs/016-change-control-governance/plan.md`

## Subtasks & Detailed Guidance

### Subtask T023 — Create incident postmortem template

- **Purpose**: Establish a reusable postmortem template for future incidents.
- **Steps**:
  1. Create `docs/runbooks/governance/incident-postmortem-template.md`.
  2. Add frontmatter:
     ```yaml
     ---
     title: Incident Postmortem Template
     doc_type: runbook
     audience: both
     status: approved
     owners: [kgale]
     version: "1.0"
     last_validated: 2026-04-05
     ---
     ```
  3. Define these sections:
     - **Incident Summary**: title, date, duration, severity (critical/high/medium/low)
     - **Timeline**: chronological list of events with timestamps
     - **Root Cause Chain**: ordered list tracing from trigger to impact
     - **Impact**: what was affected, for how long, who was impacted
     - **What Went Well**: things that helped during response
     - **What Failed**: systemic gaps, not individual blame
     - **Follow-On Actions**: table with columns: ID, Action, Type (one of: `immediate-fix`, `process-change`, `tooling-improvement`, `documentation`), Owner, Vikunja Task (placeholder), Status
- **Files**: `docs/runbooks/governance/incident-postmortem-template.md` (new)
- **Parallel?**: Yes — independent of T025.

### Subtask T024 — Verify template brevity

- **Purpose**: Ensure the template meets NFR-003 (completable in under 30 minutes).
- **Steps**:
  1. Review the template created in T023.
  2. Confirm each section has clear, focused prompts — no essay requirements.
  3. The Follow-On Actions table should use short entries, not paragraphs.
  4. If any section is bloated, trim it.
- **Files**: `docs/runbooks/governance/incident-postmortem-template.md`
- **Parallel?**: After T023.

### Subtask T025 — Create origin incident postmortem file

- **Purpose**: Create the real postmortem document for the Vikunja UFW outage.
- **Steps**:
  1. Create `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md`.
  2. Add frontmatter:
     ```yaml
     ---
     title: "Postmortem: Vikunja UFW Outage (2026-04-03)"
     doc_type: postmortem
     status: approved
     owners: [kgale]
     version: "1.0"
     last_validated: 2026-04-05
     ---
     ```
  3. This is a REAL postmortem, not a template. It documents an actual incident.
- **Files**: `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md` (new)
- **Parallel?**: Yes — independent of T023.

### Subtask T026 — Complete the origin postmortem

- **Purpose**: Fill in the postmortem with real incident data from research.md section 6.
- **Steps**:
  1. **Incident Summary**: Vikunja HTTPS unavailable for approximately 8 hours on 2026-04-03. Severity: high.
  2. **Timeline**: Agent ran `configure-ufw.sh` -> UFW rules applied without port 443 -> Tailscale serve on port 443 blocked -> Vikunja unreachable via HTTPS.
  3. **Root Cause Chain**:
     1. `configure-ufw.sh` did not include a rule for port 443.
     2. UFW blocked traffic on port 443 (Tailscale interface).
     3. Tailscale serve could not terminate TLS for Vikunja.
     4. Vikunja HTTPS access unavailable.
  4. **Impact**: Vikunja web UI and API inaccessible via HTTPS for ~8 hours. Mobile task management unavailable.
  5. **What Went Well**: Issue was identified and fixed. Port 443 rule added to UFW.
  6. **What Failed**: No pre-change dependency check. No inventory of which services depend on which ports. No automated health check after UFW changes.
  7. **Follow-On Actions**:
     - FA-001: Add dependency data to service inventory (Type: tooling-improvement, Status: done — F016 WP02)
     - FA-002: Create pre-flight checklist for infrastructure changes (Type: process-change, Status: done — F016 WP03)
     - FA-003: Document the fix in vikunja-ops.md (Type: documentation, Status: done — already completed)
  8. Use blameless tone throughout — focus on system gaps, not agent or human errors.
- **Files**: `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md`
- **Parallel?**: After T025.

### Subtask T027 — Walk pre-flight checklist through origin scenario

- **Purpose**: Validate that the pre-flight checklist (WP03) would have prevented the origin incident.
- **Steps**:
  1. Simulate the scenario: "Agent is about to run `configure-ufw.sh`."
  2. Walk through the Tier 0/1 pre-flight checklist:
     - **Step 1 — Identify affected ports/interfaces**: All ports affected (UFW is resetting firewall rules). Port 443 is among them.
     - **Step 2 — Query service inventory for dependent services**: Query `service-inventory.json` for services with dependencies referencing port 443. Result: Vikunja depends on `tailscale-serve:443`.
     - **Step 3 — Note health-check endpoints**: Vikunja health check at `http://100.92.197.90:3456` (or equivalent from inventory).
     - **Step 4 — Document rollback procedure**: Restore previous UFW rules from backup or re-run with corrected script.
     - **Step 5 — Confirm operator availability**: Human available to execute Tier 0 change.
     - **Step 6 — Define post-change verification plan**: After UFW changes, check Vikunja health endpoint.
  3. **RESULT**: The checklist surfaces the Vikunja dependency on port 443 at Step 2 — BEFORE the change executes. The gap that caused the outage is caught.
- **Files**: `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md` (add walkthrough section)
- **Parallel?**: After T026.

### Subtask T028 — Document walkthrough result

- **Purpose**: Record the validation result in the postmortem.
- **Steps**:
  1. Add a "Governance Validation" or "Pre-Flight Checklist Walkthrough" section to the postmortem.
  2. Summarize the walkthrough from T027.
  3. State the conclusion: "The pre-flight checklist, combined with the enriched service inventory, would have surfaced the Vikunja dependency on `tailscale-serve:443` before the UFW change was executed, preventing the outage."
  4. Optionally note this in the Follow-On Actions as a validation entry.
- **Files**: `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md`
- **Parallel?**: After T027.

## Test Strategy

N/A — documentation feature, no automated tests.

**Manual validation**:

- Template has all required sections.
- Postmortem is complete and uses blameless tone.
- Walkthrough correctly traces through all 6 checklist steps.
- Walkthrough conclusion is clear: checklist would have caught the gap.

## Integration Verification

- [ ] `docs/runbooks/governance/incident-postmortem-template.md` exists with all sections.
- [ ] Template is focused and concise (NFR-003).
- [ ] `docs/issues/postmortems/2026-04-03-vikunja-ufw-outage.md` exists as a complete postmortem.
- [ ] Root cause chain traces from `configure-ufw.sh` to Vikunja HTTPS unavailable.
- [ ] Follow-on actions reference F016 WPs.
- [ ] Pre-flight checklist walkthrough proves the checklist catches the port 443 gap.
- [ ] Blameless tone throughout.

## Review Guidance

- **Key checkpoints**: Postmortem is blameless in tone (no "the agent should have..." or "Kent forgot to..."). Walkthrough proves checklist effectiveness — Step 2 must surface the Vikunja dependency. Follow-on actions correctly reference F016 WPs as the resolution.
- **Before approving**: Read the root cause chain — does it make technical sense? Read the walkthrough — does Step 2 actually query the inventory and find the dependency? Is the conclusion justified?

## Risks & Mitigations

- **Risk**: Postmortem tone drifts to blame. **Mitigation**: Focus on "the system lacked X" not "person/agent failed to Y."
- **Risk**: Walkthrough is hand-wavy and doesn't actually prove the checklist works. **Mitigation**: Walk through each step with specific data from the enriched inventory.

## Definition of Done

- Template and postmortem committed to main.
- Postmortem complete with real incident data.
- Walkthrough validates checklist effectiveness.
- Blameless tone throughout.

## Activity Log
- 2026-04-05T23:44:20Z – unknown – shell_pid=61151 – Template + origin postmortem + checklist walkthrough complete. Walkthrough validates FR-016: checklist catches port 443 gap at Step 2.
