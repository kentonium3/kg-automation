---
work_package_id: WP03
title: Documentation and Architecture Updates
lane: "doing"
dependencies: [WP01, WP02]
requirement_refs:
- FR-008
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 006-goal-and-outcome-structure-WP03-merge-base
base_commit: f737713aee0cd52c95e6a381e219675988d7aab7
created_at: '2026-03-30T15:04:02.352614+00:00'
subtasks:
- T010
- T011
- T012
- T013
phase: Phase 2 - Documentation
assignee: ''
agent: "claude"
shell_pid: "57617"
review_status: ''
reviewed_by: ''
history:
- timestamp: '2026-03-30T14:32:29Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP03 – Documentation and Architecture Updates

## Review Feedback

*[This section is empty initially. Reviewers will populate it if the work is returned from review.]*

---

## Objectives & Success Criteria

Create the goals operations runbook, update the Vikunja ops runbook with the
new Goals project structure, and update architecture documentation to reflect
F006 changes.

**Success criteria:**
- `docs/handbooks/goals-ops.md` exists and covers: format reference, manual
  goal creation (Vikunja + Obsidian two-step), goal closure, goal retirement,
  and valid vs invalid declaration examples
- `docs/handbooks/vikunja-ops.md` updated with Goals project, metalcasework
  label, and Goals saved filter
- `docs/design/architecture/data/service-inventory.json` updated with F006 note
- `docs/design/architecture/service-inventory.md` updated with narrative note
- All documentation is actionable without external context

## Context & Constraints

**Reference documents:**
- `kitty-specs/006-goal-and-outcome-structure/spec.md` — FR-008, FR-009
- `kitty-specs/006-goal-and-outcome-structure/plan.md` — Phase C details
- `kitty-specs/006-goal-and-outcome-structure/data-model.md` — entity definitions and lifecycle
- `docs/handbooks/vikunja-ops.md` — existing Vikunja documentation (read before updating)
- `docs/design/architecture/data/service-inventory.json` — existing service inventory
- `docs/design/architecture/service-inventory.md` — existing narrative

**Standing requirement from CLAUDE.md:**
> Any feature that changes deployed services, credentials, data flows, or
> network topology must update the relevant files in `docs/design/architecture/`
> and `docs/design/architecture/data/`.

F006 doesn't change services or credentials, but it adds a new data structure
(Goals project) to Vikunja, which must be documented.

## Subtasks & Detailed Guidance

### Subtask T010 – Create goals-ops.md Runbook

- **Purpose**: Provide an operational reference for the goal declaration system
  so Kent can manage goals without re-reading the spec or asking for help.
- **Steps**:
  1. Create `docs/handbooks/goals-ops.md` with the following sections:

     **a. Goal Declaration Format**
     - The canonical format: "On [date], I have [outcome] as evidenced by [proof]"
     - The three required elements explained
     - Rules: specific date, present-tense, observable evidence, one outcome per declaration

     **b. Valid vs Invalid Examples**
     - Valid: "On June 30th, 2026, I have established an income of $5,000/month
       through Intentional consulting as evidenced by deposits totaling $5,000
       or more in my Intentional LLC business checking account."
     - Invalid: "I want to grow my consulting business" (future tense, no date,
       no evidence)
     - Invalid: "By Q2, I will have revenue" (range not date, future tense,
       vague evidence)
     - Invalid: "On June 30th, I have grown as a person" (not observable)

     **c. Adding a New Goal (Two-Step Process)**
     Step 1 — Vikunja:
     1. Open Vikunja web UI (http://100.92.197.90:3456 via Tailscale)
     2. Navigate to the Goals project
     3. Create a new task with:
        - Title: short summary (e.g., "Intentional: $5K/month consulting income")
        - Description: full declaration in canonical format, evidence criteria
          as separate paragraph
        - Due date: target date from the declaration
        - Label: identity label (personal, intentional, or metalcasework)

     Step 2 — Obsidian:
     1. Open `01-Constitution/Goals-MOC.md` in Obsidian
     2. Add the declaration as a blockquote under the appropriate identity
        context section (Personal, Intentional, or Metal Casework)
     3. Update the "Last updated" date at the bottom

     **d. Closing an Achieved Goal**
     1. In Vikunja: mark the goal task as done
     2. In Goals-MOC.md: move the declaration from the active section to
        `Archive > Achieved` with the date achieved
     3. Note: do not delete — achieved goals are historical record

     **e. Retiring an Abandoned Goal**
     1. In Vikunja: mark the goal task as done, add a note in the description
        explaining why it was retired
     2. In Goals-MOC.md: move the declaration from the active section to
        `Archive > Retired` with the date and reason for retirement
     3. Note: do not delete — retired goals inform future goal-setting

     **f. Source of Truth Rules**
     - Vikunja is authoritative for **state** (active/achieved/retired, target date)
     - Goals-MOC.md is authoritative for **narrative context** (full declaration text)
     - Both must be updated together until automated sync is built

     **g. Identity Labels**
     - `personal` — personal life goals
     - `intentional` — Intentional LLC business goals
     - `metalcasework` — Metal Casework project goals
     - Every goal must have exactly one identity label

  2. Add YAML front-matter matching kg-automation doc standards if applicable
  3. Keep the language direct and actionable — this is a reference, not a spec

- **Files**: `docs/handbooks/goals-ops.md` (new, ~150-200 lines)
- **Parallel?**: No — primary deliverable, write first
- **Notes**: The runbook must be usable by Kent without any other context. Test
  by reading it cold — can you follow the instructions?

### Subtask T011 – Update vikunja-ops.md

- **Purpose**: Keep the existing Vikunja documentation current with the new
  Goals project, metalcasework label, and Goals saved filter.
- **Steps**:
  1. Read `docs/handbooks/vikunja-ops.md` to understand the current structure
  2. Add to the project structure section:
     ```
     ├── Goals                    ← F006: goal declarations (not tasks)
     ```
  3. Add to the labels section:
     ```
     - metalcasework (#ff9800 orange) — Metal Casework project goals  ← F006
     ```
  4. Add to the saved filters section:
     ```
     - Goals — active goal declarations sorted by target date  ← F006
     ```
  5. Add a brief note explaining that goals are distinct from tasks — they are
     outcome declarations with target dates, not action items
  6. Do not rewrite the existing content — only add the new sections
- **Files**: `docs/handbooks/vikunja-ops.md` (update existing)
- **Parallel?**: Yes — can proceed alongside T012 and T013
- **Notes**: Preserve the existing document structure. Add, don't rewrite.

### Subtask T012 – Update service-inventory.json

- **Purpose**: Record the F006 change in the architecture documentation's
  machine-readable service inventory.
- **Steps**:
  1. Read `docs/design/architecture/data/service-inventory.json`
  2. Find the Vikunja entry
  3. Add or update the following fields:
     - Add to `notes` or a relevant field: "Goals project added by F006 for
       goal declaration storage"
     - Add `"updated_by": "F006"` (or append to existing list)
  4. Do not change existing fields (image, port, systemd_unit, etc.)
- **Files**: `docs/design/architecture/data/service-inventory.json` (update existing)
- **Parallel?**: Yes — can proceed alongside T011 and T013
- **Notes**: The JSON must remain valid. Verify with `python -m json.tool` after editing.

### Subtask T013 – Update service-inventory.md

- **Purpose**: Update the narrative architecture documentation to note the
  Goals project under Vikunja.
- **Steps**:
  1. Read `docs/design/architecture/service-inventory.md`
  2. Find the Vikunja section
  3. Add a brief paragraph noting that F006 added a Goals project for
     structured goal declaration storage, with a metalcasework label and
     Goals saved filter
  4. Keep it concise — one paragraph maximum
- **Files**: `docs/design/architecture/service-inventory.md` (update existing)
- **Parallel?**: Yes — can proceed alongside T011 and T012
- **Notes**: This is a narrative companion to the JSON file. Keep them consistent.

## Risks & Mitigations

- **Stale documentation**: If Vikunja structure changed since the ops runbook
  was written, the runbook may not match reality. Mitigation: cross-reference
  with WP01's final Vikunja state.
- **JSON syntax error**: Editing service-inventory.json could introduce invalid
  JSON. Mitigation: validate with `python -m json.tool` after editing.

## Review Guidance

- Verify goals-ops.md is actionable without external context
- Verify vikunja-ops.md additions are consistent with WP01's actual setup
- Verify service-inventory.json is valid JSON after update
- Verify service-inventory.md narrative matches JSON changes
- Verify all documents reference the canonical goal declaration format consistently

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Implementation command: `spec-kitty implement WP03 --base WP02`
- Depends on WP01 (Vikunja structure) and WP02 (Goals-MOC structure)

## Activity Log

- 2026-03-30T14:32:29Z – system – lane=planned – Prompt created.
- 2026-03-30T15:04:02Z – claude – shell_pid=57617 – lane=doing – Assigned agent via workflow command
