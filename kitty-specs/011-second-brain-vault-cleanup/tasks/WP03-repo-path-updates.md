---
work_package_id: WP03
title: Repository Path Updates
lane: planned
dependencies: [WP02]
requirement_refs:
- FR-05
- FR-06
- FR-11
- FR-12
- FR-13
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T009, T010, T011, T012, T013, T014, T015]
history:
- date: '2026-04-01T18:30:16Z'
  event: created
  actor: claude
---

# WP03: Repository Path Updates

## Implementation command

```bash
spec-kitty implement WP03 --base WP02
```

## Objective

Update all actionable files in the kg-automation repo that reference the old
`second-brain/vault` path to use `second-brain/notes`. Historical docs
(completed feature specs, archived specs, audit reports) are NOT updated.

## Context

- **Old path patterns to find**: `second-brain/vault`, `vault/Notes/`,
  `vault/00-Inbox/`, `vault/02-Growth/_private/`
- **New path patterns**: `second-brain/notes`, `notes/00-Inbox/`,
  `notes/02-Growth/_private/`
- **All subtasks are parallel-safe** [P] — each touches a different file
- **Do NOT update** files in: `docs/func-spec/`, `docs/archive/`,
  `docs/design/personal-ai-system-spec-*`, `docs/design/adversarial-analysis.md`,
  `docs/reports/`, or completed `kitty-specs/` directories

## Subtask guidance

### T009: Update validate-obsidian-sync.sh [P]

**File**: `scripts/office2/validate-obsidian-sync.sh`

**Purpose**: Update vault path references in the sync validation script.

**Steps**:
1. Read the file and identify all references to `second-brain/vault`
2. Replace each with `second-brain/notes`
3. Also check for `vault/Notes/` patterns and replace with `notes/`

**Validation**:
- [ ] `grep 'vault' scripts/office2/validate-obsidian-sync.sh` returns no matches
- [ ] Script syntax is valid (`bash -n scripts/office2/validate-obsidian-sync.sh`)

### T010: Update felix-admin-capture TOOLS.md [P]

**File**: `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`

**Purpose**: Update vault root path, inbox path, and privacy boundary path.

**Expected changes**:
- `/home/kgale/second-brain/vault/` → `/home/kgale/second-brain/notes/`
- `/home/kgale/second-brain/vault/00-Inbox/` → `/home/kgale/second-brain/notes/00-Inbox/`
- `/home/kgale/second-brain/vault/02-Growth/_private/` → `/home/kgale/second-brain/notes/02-Growth/_private/`

**Validation**:
- [ ] `grep 'vault' scripts/openclaw/agents/felix-admin-capture/TOOLS.md` returns no matches
- [ ] Privacy boundary path correctly references `notes/02-Growth/_private/`

### T011: Update felix-admin-capture AGENTS.md [P]

**File**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Purpose**: Update vault path references in the agent description file.

**Steps**:
1. Read the file and find all `second-brain/vault` references
2. Replace with `second-brain/notes`
3. Check for `vault/Notes/` patterns and replace

**Validation**:
- [ ] `grep 'vault' scripts/openclaw/agents/felix-admin-capture/AGENTS.md` returns no matches

### T012: Update felix-admin-habits TOOLS.md [P]

**File**: `scripts/openclaw/agents/felix-admin-habits/TOOLS.md`

**Purpose**: Update the privacy boundary path.

**Expected change**:
- `/home/kgale/second-brain/vault/02-Growth/_private/` → `/home/kgale/second-brain/notes/02-Growth/_private/`

**Validation**:
- [ ] `grep 'vault' scripts/openclaw/agents/felix-admin-habits/TOOLS.md` returns no matches

### T013: Update CLAUDE.md [P]

**File**: `CLAUDE.md` (repository root)

**Purpose**: Update the privacy boundary path in the absolute rule.

**Expected change**:
- `~/second-brain/vault/Notes/02-Growth/_private/` → `~/second-brain/notes/02-Growth/_private/`

**Validation**:
- [ ] Privacy rule references `notes/02-Growth/_private/`
- [ ] No `vault` references remain in CLAUDE.md (related to second-brain paths)

### T014: Update claude-code-instructions.md [P]

**File**: `ai-agents/claude-code-instructions.md`

**Purpose**: Update the privacy boundary path.

**Expected change**:
- `second-brain/vault/Notes/02-Growth/_private/` → `second-brain/notes/02-Growth/_private/`

**Validation**:
- [ ] `grep 'vault' ai-agents/claude-code-instructions.md` returns no second-brain-related matches

### T015: Update claude-instructions.md [P]

**File**: `ai-agents/claude-instructions.md`

**Purpose**: Update the privacy boundary path.

**Expected change**:
- `second-brain/vault/Notes/02-Growth/_private/` → `second-brain/notes/02-Growth/_private/`

**Validation**:
- [ ] `grep 'vault' ai-agents/claude-instructions.md` returns no second-brain-related matches

## Post-completion verification

After all subtasks, run a comprehensive grep to verify no actionable files
still reference the old path:

```bash
grep -r 'second-brain/vault' scripts/ ai-agents/ CLAUDE.md --include='*.md' --include='*.sh' --include='*.service'
```

Expected: no output (zero matches in actionable files).

## Branch Strategy

- Planning base branch: `main`
- Merge target branch: `main`

## Definition of Done

- All 7 files updated with new path references
- Zero `second-brain/vault` references in actionable files
- Privacy boundary paths correctly reference `notes/02-Growth/_private/`

## Risks

- **Partial replacement**: Some files may have multiple path patterns
  (`vault/`, `vault/Notes/`, `vault/00-Inbox/`). Each must be found and
  updated. Read each file fully before editing.
- **CLAUDE.md format sensitivity**: CLAUDE.md is read by Claude Code at
  session start. Ensure edits preserve the existing markdown structure.
