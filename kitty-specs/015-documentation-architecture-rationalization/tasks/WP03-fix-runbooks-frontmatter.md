---
work_package_id: WP03
title: Fix docs/runbooks/ Frontmatter + Audience + Link Updates
dependencies:
- WP01
- WP02
requirement_refs:
- FR-003
- FR-004
- FR-005
- FR-013
- NFR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 015-documentation-architecture-rationalization-WP03-merge-base
base_commit: f2b57c53d3aef43f0c1d0d7b4580f8ccba1afb38
created_at: '2026-04-05T04:03:24.636514+00:00'
subtasks:
- T008
- T009
- T010
- T011
- T012
- T013
phase: Phase 1 - Frontmatter Corrections
assignee: ''
agent: ''
shell_pid: '99090'
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/runbooks/
execution_mode: code_change
owned_files:
- docs/runbooks/agent-execution-roles.md
- docs/runbooks/agent-handbook.md
- docs/runbooks/ci-handbook.md
- docs/runbooks/claude-code.md
- docs/runbooks/deployment.md
- docs/runbooks/f001-acceptance-results.md
- docs/runbooks/f002-acceptance-results.md
- docs/runbooks/felix-governance.md
- docs/runbooks/goals-ops.md
- docs/runbooks/habits-ops.md
- docs/runbooks/inbox-ops.md
- docs/runbooks/maintenance.md
- docs/runbooks/observation-ops.md
- docs/runbooks/obsidian-setup.md
- docs/runbooks/obsidian-sync-ops.md
- docs/runbooks/obsidian.md
- docs/runbooks/openclaw-ops.md
- docs/runbooks/repo-governance.md
- docs/runbooks/spec-kitty-init-in-existing-repo.md
- docs/runbooks/task-intelligence-ops.md
- docs/runbooks/templater-commands.md
- docs/runbooks/transcribe-ops.md
- docs/runbooks/vikunja-ops.md
- docs/runbooks/whatsapp-ops.md
---

# Work Package Prompt: WP03 — Fix docs/runbooks/ Frontmatter + Audience + Link Updates

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or may stack on WP01/WP02 branches for stacked execution.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Apply frontmatter corrections to all 24 files remaining in `docs/runbooks/` after WP02's moves:

- 20 files: `handbook` → `runbook` + add `audience` declaration.
- 2 files with misclassifications: `templater-commands.md` (handbook → reference), `repo-governance.md` (policy → standard).
- 2 files already correct (`f001-acceptance-results.md`, `f002-acceptance-results.md`): no changes.
- Update inbound links in `deployment.md` pointing to moved `office2-backup-and-security.md`.

**Success criteria**:

- [ ] Every file in `docs/runbooks/**` has `doc_type ∈ {runbook, reference, standard}`.
- [ ] Every file with `doc_type: runbook` has an `audience` field (`human-only` | `agent-executable` | `both`).
- [ ] `deployment.md` links to `office2-backup-and-security.md` now point to `docs/design/office2-backup-and-security.md` (3 occurrences).
- [ ] No file in `docs/runbooks/` retains the legacy `handbook` or `policy` values.

## Context & Constraints

**Reference documents**:

- `kitty-specs/015-documentation-architecture-rationalization/research.md` §1, §7 (misclassification table + agent-executable candidates)
- `docs/design/standards/divio-classification.md` (created in WP01 — cite this as authority)
- `kitty-specs/015-documentation-architecture-rationalization/data-model.md` §5 (audience rules)

**Audience assignments per research.md §7**:

- `agent-executable` (8 files): vikunja-ops, openclaw-ops, obsidian-sync-ops, transcribe-ops, inbox-ops, goals-ops, habits-ops, task-intelligence-ops
- `human-only` (high-judgement): felix-governance, spec-kitty-init-in-existing-repo, ci-handbook (PR-review sections), agent-handbook, agent-execution-roles, claude-code, repo-governance
- `both` (operational but with judgement): deployment, observation-ops, obsidian-setup, obsidian, maintenance

**Constraints**:

- Do not modify file bodies; only frontmatter + deployment.md's 3 link lines.
- Preserve existing frontmatter fields (title, owners, last_validated, version) — add `audience`, update `doc_type` only.

## Subtasks & Detailed Guidance

### Subtask T008 — Fix handbook → runbook on service-ops runbooks [P]

- **Purpose**: 10 operational runbooks for running services. Most are agent-executable candidates.
- **Files** (10): `vikunja-ops.md`, `goals-ops.md`, `habits-ops.md`, `inbox-ops.md`, `observation-ops.md`, `openclaw-ops.md`, `transcribe-ops.md`, `whatsapp-ops.md`, `obsidian-sync-ops.md`, `task-intelligence-ops.md`.
- **Steps**:
  1. For each file, change `doc_type: handbook` → `doc_type: runbook`.
  2. Add `audience:` field with values per assignments above:
     - `agent-executable`: vikunja-ops, openclaw-ops, obsidian-sync-ops, transcribe-ops, inbox-ops, goals-ops, habits-ops, task-intelligence-ops.
     - `both`: observation-ops, whatsapp-ops (operational but policy-sensitive).
  3. Keep all other frontmatter fields intact.
- **Parallel?**: Yes — 10 independent files.
- **Notes**: whatsapp-ops is `both` because dmPolicy transitions (per memory) require human judgement; day-to-day message handling is mechanical.

### Subtask T009 — Fix handbook → runbook on setup/deployment runbooks [P]

- **Purpose**: 4 setup/deployment runbooks. These typically involve both procedural steps and judgement calls.
- **Files** (4): `deployment.md`, `obsidian-setup.md`, `obsidian.md`, `spec-kitty-init-in-existing-repo.md`.
- **Steps**:
  1. Change `doc_type: handbook` → `doc_type: runbook` for all 4.
  2. Add `audience:` field:
     - `both`: deployment, obsidian-setup, obsidian (mostly procedural, some judgement).
     - `human-only`: spec-kitty-init-in-existing-repo (requires tool installation and manual setup).
  3. Keep all other frontmatter fields intact.
- **Parallel?**: Yes — 4 independent files.
- **Notes**: `obsidian.md` blends config reference and procedural content; dominant = runbook. Note `divio_ambiguity: "mixed: config reference + setup procedure"` in its frontmatter.

### Subtask T010 — Fix handbook → runbook on process/governance runbooks [P]

- **Purpose**: 6 process/governance runbooks. Most require human judgement.
- **Files** (6): `felix-governance.md`, `ci-handbook.md`, `agent-handbook.md`, `agent-execution-roles.md`, `claude-code.md`, `maintenance.md`.
- **Steps**:
  1. Change `doc_type: handbook` → `doc_type: runbook` for all 6.
  2. Add `audience:` field:
     - `human-only`: felix-governance, ci-handbook, agent-handbook, agent-execution-roles, claude-code.
     - `both`: maintenance (some tasks mechanical, some require judgement).
  3. Keep all other frontmatter fields intact.
- **Parallel?**: Yes — 6 independent files.
- **Notes**: These runbooks contain policy decisions, PR reviews, or identity-sensitive operations — human-only is the safe default.

### Subtask T011 — Fix misclassifications: templater-commands + repo-governance [P]

- **Purpose**: Two files that aren't runbooks at all.
- **Files** (2): `templater-commands.md`, `repo-governance.md`.
- **Steps**:
  1. `templater-commands.md`: change `doc_type: handbook` → `doc_type: reference`. (This is a command list, not a procedure.) Do NOT add `audience` (not a runbook).
  2. `repo-governance.md`: change `doc_type: policy` → `doc_type: standard`. (Cross-cutting git workflow standard.) Do NOT add `audience` (not a runbook).
- **Parallel?**: Yes.
- **Notes**: These are the two files in `docs/runbooks/` whose content type doesn't match the directory name. Since they're not being moved (per conservative approach), their frontmatter should at least be correct.

### Subtask T012 — Update deployment.md links to moved file

- **Purpose**: `deployment.md` contains 3 references to `office2-backup-and-security.md` at its OLD path. These are now broken because WP02 moved the file.
- **Steps**:
  1. Read `docs/runbooks/deployment.md`.
  2. Replace all 3 occurrences of `docs/runbooks/office2-backup-and-security.md` with `docs/design/office2-backup-and-security.md`.
  3. Original lines (approximate):

     - Line ~236: "See `docs/runbooks/office2-backup-and-security.md` for..."
     - Line ~256: "See `docs/runbooks/office2-backup-and-security.md` for what `claude` can sudo..."
     - Line ~273: "- `docs/runbooks/office2-backup-and-security.md` — security baseline reset"
  4. Verify with `grep -n office2-backup-and-security docs/runbooks/deployment.md` — should show 3 lines with new path.
- **Files**: `docs/runbooks/deployment.md`.
- **Parallel?**: No — runs after T009.
- **Notes**: These are inline markdown links in narrative text, not frontmatter.

### Subtask T013 — Validate frontmatter across all runbooks

- **Purpose**: Confirm zero legacy values remain and all runbooks declare audience.
- **Steps**:
  1. Run: `grep -r "doc_type: handbook" docs/runbooks/` — expect zero matches.
  2. Run: `grep -r "doc_type: policy" docs/runbooks/` — expect zero matches.
  3. Run: `grep -rL "audience:" docs/runbooks/*.md` — expect only the 2 non-runbook files (templater-commands, repo-governance) and the 2 acceptance-results files (already reference).
  4. Report any unexpected output.
- **Files**: None modified. Validation only.
- **Parallel?**: No — runs last.
- **Notes**: If validation fails, return to previous subtasks to fix.

## Test Strategy

N/A — documentation feature, no automated tests (per spec constraint C-006).

## Risks & Mitigations

- **Risk**: Wrong audience assignment (agent-executable for a human-only runbook). **Mitigation**: Default to `both` or `human-only` if uncertain; research.md §7 has agent-executable candidates list.
- **Risk**: Missing a file in the 24-file list. **Mitigation**: T013 validation step catches this.
- **Risk**: Breaking YAML frontmatter by misplacing `audience:` field. **Mitigation**: Add after `doc_type:` line consistently.

## Integration Verification

- [ ] All 24 files in `docs/runbooks/` have correct `doc_type` (no legacy values).
- [ ] All files with `doc_type: runbook` have an `audience` field.
- [ ] `deployment.md` has 3 updated links to `docs/design/office2-backup-and-security.md`.
- [ ] grep validations pass.
- [ ] No file bodies were modified except deployment.md's 3 link lines.

## Review Guidance

- **Key checkpoints**: Frontmatter changes are small and surgical. Audience values match research.md §7. Link updates are surgical (3 lines in deployment.md).
- **Before approving**: Spot-check 2-3 files to verify frontmatter is well-formed YAML.

## Definition of Done

- All 24 files have correct frontmatter committed to main.
- deployment.md links updated.
- grep validations return expected results.
