---
work_package_id: WP09
title: INDEX.md Update
dependencies:
- WP01
- WP02
- WP03
- WP04
- WP05
- WP06
- WP07
- WP08
requirement_refs:
- C-006
- FR-015
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 016-change-control-governance-WP09-merge-base
base_commit: b2d9fb8df3d153752bd943571494effdd5059365
created_at: '2026-04-05T23:48:43.437596+00:00'
subtasks:
- T040
- T041
- T042
- T043
phase: Phase 4 - Cleanup
assignee: ''
agent: ''
shell_pid: '63587'
history:
- at: '2026-04-05T23:00:03Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/INDEX.md
execution_mode: code_change
owned_files:
- docs/INDEX.md
---

# Work Package Prompt: WP09 — INDEX.md Update

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or stacked on WP01-WP08.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Update `docs/INDEX.md` with all new F016 files per the F015 change-control INDEX.md maintenance rule (C-006). Every new file created by F016 must be listed in INDEX.md.

**Success criteria**:

- [ ] 3 governance runbook files added to the runbooks/governance section.
- [ ] `change-risk-taxonomy.json` added to the machine-readable artifacts section.
- [ ] `2026-04-03-vikunja-ufw-outage.md` added as the first entry in the postmortems section.
- [ ] `service-dependencies.view.md` added to the architecture section.
- [ ] No pre-existing entries removed.

## Context & Constraints

F015 established `docs/INDEX.md` as the master documentation map and defined rule C-006: every new file must be added to INDEX.md as part of the same change. This WP is the F016 compliance with that rule.

This WP has the most dependencies in the feature because it must list files created by all other work packages. It runs last in Phase 4.

**Constraints**:

- Entries must have correct `doc_type` annotations matching the files' frontmatter.
- Entries must be placed in the correct INDEX.md sections.
- No pre-existing entries may be removed or modified.
- Follow the exact entry format established by F015 (link + doc_type annotation + brief description).

**Reference documents**:

- `docs/INDEX.md` (current state from F015)
- `kitty-specs/016-change-control-governance/plan.md`
- `kitty-specs/016-change-control-governance/data-model.md`

## Subtasks & Detailed Guidance

### Subtask T040 — Add governance runbook files

- **Purpose**: List the 3 new governance runbooks in INDEX.md.
- **Steps**:
  1. Open `docs/INDEX.md`.
  2. Locate the `runbooks/governance` section (created empty by F015 with note "populated by F016").
  3. Replace the empty/placeholder content with entries for:
     - `pre-flight-checklist.md` — `runbook` `both`
     - `post-change-verification.md` — `runbook` `both`
     - `incident-postmortem-template.md` — `runbook` `both`
  4. Follow the existing entry format: `[Title](relative/path) — doc_type audience`.
- **Files**: `docs/INDEX.md`
- **Parallel?**: No — all T040-T043 modify the same file, so execute sequentially.
- **Notes**: The runbooks/governance section was explicitly reserved for F016 by the F015 INDEX.md. Replace the placeholder, don't just append.

### Subtask T041 — Add change-risk-taxonomy.json

- **Purpose**: List the new machine-readable risk taxonomy in the data files section.
- **Steps**:
  1. Locate the `docs/design/architecture/data/` section in INDEX.md.
  2. Add an entry for `change-risk-taxonomy.json` — `reference` (machine-readable).
  3. Brief description: five-tier change risk taxonomy.
- **Files**: `docs/INDEX.md`
- **Parallel?**: No — sequential with other INDEX.md edits.
- **Notes**: Place the entry in alphabetical or logical order within the data files section.

### Subtask T042 — Add vikunja-ufw-outage postmortem

- **Purpose**: List the first postmortem entry in the postmortems section.
- **Steps**:
  1. Locate the `docs/issues/postmortems/` section in INDEX.md.
  2. Add `2026-04-03-vikunja-ufw-outage.md` as the first entry — `postmortem`.
  3. Brief description: Vikunja outage caused by UFW rule change.
  4. This section was created empty by F015 with note "Populated by F016 onwards."
- **Files**: `docs/INDEX.md`
- **Parallel?**: No — sequential with other INDEX.md edits.
- **Notes**: Replace the placeholder content with the actual entry.

### Subtask T043 — Add service-dependencies.view.md

- **Purpose**: List the new service dependency diagram in the architecture section.
- **Steps**:
  1. Locate the architecture views/diagrams area in INDEX.md (near other `.view.md` entries).
  2. Add `service-dependencies.view.md` — `guide` `reference`.
  3. Brief description: Mermaid service dependency diagram for all 11 office2 services.
- **Files**: `docs/INDEX.md`
- **Parallel?**: No — sequential with other INDEX.md edits.
- **Notes**: Place near existing `.view.md` entries (data-flows.view.md, physical-topology.view.md).

## Test Strategy

N/A — governance feature, no automated tests. Manual validation per quickstart.md.

**Manual validation**:

- Every new F016 file is listed in INDEX.md.
- Entries have correct doc_type annotations.
- No pre-existing entries removed.
- Entry format matches F015 pattern.

## Risks & Mitigations

- **Risk**: Missing a new F016 file. **Mitigation**: Cross-reference against all WP owned_files lists to build a complete checklist.
- **Risk**: INDEX.md structure changed by other work since F015. **Mitigation**: Read current state before editing; adapt to current section structure.
- **Risk**: Incorrect doc_type annotations. **Mitigation**: Check each file's frontmatter for its actual doc_type.

## Integration Verification

- [ ] 3 governance runbook entries present in runbooks/governance section.
- [ ] `change-risk-taxonomy.json` entry present in data files section.
- [ ] `2026-04-03-vikunja-ufw-outage.md` entry present in postmortems section.
- [ ] `service-dependencies.view.md` entry present in architecture section.
- [ ] All entries have correct doc_type annotations.
- [ ] No pre-existing INDEX.md entries removed or modified.
- [ ] Entry format matches F015 pattern (link + annotation + description).

## Review Guidance

- **Key checkpoints**: Every new F016 file is listed. Entries have correct doc_type annotations. No pre-existing entries removed.
- **Before approving**: Compare the list of new entries against all WP owned_files to verify completeness.

## Definition of Done

- `docs/INDEX.md` updated with all new F016 files.
- All entries correctly annotated and placed in appropriate sections.
- No pre-existing entries removed.

## Activity Log

- 2026-04-05T23:51:32Z – unknown – shell_pid=63587 – INDEX.md updated with all F016 files per C-006
