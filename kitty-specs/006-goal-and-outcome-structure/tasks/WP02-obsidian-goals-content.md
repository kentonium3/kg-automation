---
work_package_id: WP02
title: Obsidian Goals Format and Content
lane: "doing"
dependencies: [WP01]
requirement_refs:
- FR-001
- FR-002
- FR-006
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 006-goal-and-outcome-structure-WP01
base_commit: e0a1e2ae87ad52c5ce972c47c21a7da6f7ac761c
created_at: '2026-03-30T14:55:23.981194+00:00'
subtasks:
- T007
- T008
- T009
phase: Phase 1 - Core Implementation
assignee: ''
agent: "claude"
shell_pid: "55849"
review_status: ''
reviewed_by: ''
history:
- timestamp: '2026-03-30T14:32:29Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP02 – Obsidian Goals Format and Content

## Review Feedback

*[This section is empty initially. Reviewers will populate it if the work is returned from review.]*

---

## Objectives & Success Criteria

Write the canonical goal declaration format, template, and real declarations to
`01-Constitution/Goals-MOC.md` on office2 via SSH. The file must be readable
standalone as a complete picture of Kent's active declared outcomes.

**Success criteria:**
- Goals-MOC.md contains the canonical format definition with all three required
  elements (date, present-tense outcome, observable evidence)
- Template section makes it easy to write valid declarations and obvious when
  elements are missing
- At least one real goal declaration in the standard format
- Declarations organized by identity context (Personal, Intentional, Metal Casework)
- Archive section for achieved/retired goals (initially empty)
- File is readable standalone — no external cross-references needed
- Content matches what was seeded in Vikunja (WP01)
- Obsidian Sync delivers content to all devices

## Context & Constraints

**Reference documents:**
- `kitty-specs/006-goal-and-outcome-structure/spec.md` — FR-001, FR-002, FR-006, FR-007
- `kitty-specs/006-goal-and-outcome-structure/plan.md` — Phase B details
- `kitty-specs/006-goal-and-outcome-structure/research.md` — R-03, R-04
- `kitty-specs/006-goal-and-outcome-structure/data-model.md` — Goal Declaration entity

**Remote access:**
- SSH command: `ssh office2-claude`
- Vault path: `~/second-brain/vault/Notes/01-Constitution/Goals-MOC.md`
- Legacy content backed up to `Goals-MOC-pre-Felix-backup-2026-03-29.md`

**Privacy boundary:**
- `02-Growth/_private/` is **never** accessed under any circumstance
- Goals that arise from private work may be captured in the standard format
  without referencing their origin context

**Canonical format:**
```
On [specific date], I have [present-tense outcome statement]
as evidenced by [observable, concrete proof].
```

**Format rules:**
- Date is specific — a concrete calendar date, not a range or quarter
- Outcome is present-tense — "I have", not "I will" or "I want to"
- Evidence is observable — verifiable without interpretation
- One outcome per declaration — compound goals must be split

## Subtasks & Detailed Guidance

### Subtask T007 – Write Goals-MOC.md Format and Template

- **Purpose**: Define the canonical goal declaration format in the Obsidian
  constitution so it serves as the authoritative reference for Kent and all
  future agents.
- **Steps**:
  1. SSH to office2: `ssh office2-claude`
  2. Read current state: `cat ~/second-brain/vault/Notes/01-Constitution/Goals-MOC.md`
     to confirm it was reset to clean slate
  3. Write the new Goals-MOC.md with the following structure:

     ```markdown
     # Goals — Active Declarations

     > This file is the human-readable canonical reference for all active goal
     > declarations. Future agents read this file for goal context. Vikunja is
     > the machine-readable store; this file is the narrative layer.
     >
     > **Source of truth rules:**
     > - Vikunja is authoritative for **state** (active/achieved/retired, target date)
     > - This file is authoritative for **narrative context** (full declaration text)
     > - Both must be updated together (see goals-ops.md for procedures)

     ## Declaration Format

     Every goal declaration must follow this exact structure:

     > On [specific date], I have [present-tense outcome statement]
     > as evidenced by [observable, concrete proof].

     **Rules for a valid declaration:**
     - **Date is specific** — a concrete calendar date, not "Q2" or "sometime"
     - **Outcome is present-tense** — "I have", not "I will" or "I want to"
     - **Evidence is observable** — something that can be verified without
       interpretation (bank deposits, a completed document, a measurable metric)
     - **One outcome per declaration** — compound goals must be split

     **Example:**
     > On June 30th, 2026, I have established an income of $5,000/month through
     > Intentional consulting as evidenced by deposits totaling $5,000 or more in
     > my Intentional LLC business checking account.

     ---

     ## Personal

     [declarations go here]

     ## Intentional

     [declarations go here]

     ## Metal Casework

     [declarations go here]

     ---

     ## Archive

     ### Achieved

     *None yet.*

     ### Retired

     *None yet.*

     ---

     *Last updated: [date]*
     ```

  4. Verify the file is syntactically correct Markdown and renders cleanly
     in Obsidian

- **Files**: `~/second-brain/vault/Notes/01-Constitution/Goals-MOC.md` (on office2)
- **Parallel?**: No — must be done before T008
- **Notes**: The format definition is the contract. It is not a guideline or
  preference. Do not soften the language.

### Subtask T008 – Populate Goals-MOC.md with Real Declarations

- **Purpose**: Add at least one real goal declaration so the file is immediately
  useful and demonstrates the format in practice.
- **Steps**:
  1. **STOP AND CONFIRM**: The declarations here must exactly match what was
     seeded in Vikunja during WP01 (T004). If WP01 paused for Kent's input
     on seed goals, this subtask must use the same confirmed declarations.
  2. Add each declaration under the appropriate identity context section:
     - Personal goals → under `## Personal`
     - Intentional goals → under `## Intentional`
     - Metal Casework goals → under `## Metal Casework`
  3. Each declaration should be formatted as a blockquote for visual
     distinction:
     ```markdown
     > On June 30th, 2026, I have established an income of $5,000/month through
     > Intentional consulting as evidenced by deposits totaling $5,000 or more in
     > my Intentional LLC business checking account.
     ```
  4. Update the `*Last updated:*` line at the bottom with the current date
  5. Verify the file reads as a complete, standalone picture of Kent's active
     declared outcomes
- **Files**: `~/second-brain/vault/Notes/01-Constitution/Goals-MOC.md` (on office2)
- **Parallel?**: No — depends on T007 (format must be in place first)
- **Notes**: Do not invent declarations. Every declaration must come from Kent
  or be confirmed by Kent. The seed goal(s) from WP01 are the minimum.

### Subtask T009 – Verify Obsidian Sync

- **Purpose**: Confirm that the updated Goals-MOC.md syncs to all devices
  via Obsidian Sync.
- **Steps**:
  1. After writing Goals-MOC.md on office2, wait a reasonable time for
     Obsidian Sync (typically under 60 seconds)
  2. Verify the file exists and has the expected content on office2:
     `cat ~/second-brain/vault/Notes/01-Constitution/Goals-MOC.md`
  3. Ask Kent to confirm the file appears correctly on his Mac and/or iPhone
     via Obsidian
  4. If sync is not working, document the issue and note it as a blocker
     (do not attempt to fix Obsidian Sync)
- **Files**: N/A (verification only)
- **Parallel?**: No — runs after T008
- **Notes**: Obsidian Sync is existing infrastructure, not something F006
  deploys. If sync fails, it's an infrastructure issue, not an F006 bug.

## Risks & Mitigations

- **Goals-MOC.md already has content**: If the clean slate reset didn't happen,
  back up the current content before overwriting. Check for the backup file
  `Goals-MOC-pre-Felix-backup-2026-03-29.md`.
- **Seed goal mismatch**: If WP01 was modified during review, the declarations
  here must be updated to match. Always cross-reference WP01's final state.
- **Obsidian Sync delay**: Allow up to 5 minutes for sync. If still not
  synced, ask Kent to check Obsidian Sync status on his devices.

## Review Guidance

- Verify Goals-MOC.md uses the exact canonical format (no variations)
- Verify at least one real declaration exists (not just the example)
- Verify declarations match what was seeded in Vikunja (WP01)
- Verify the file is readable standalone
- Verify the format rules are clear and unambiguous
- Check that `02-Growth/_private/` is never referenced

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Implementation command: `spec-kitty implement WP02 --base WP01`
- Depends on WP01 (seed goal declarations must align)

## Activity Log

- 2026-03-30T14:32:29Z – system – lane=planned – Prompt created.
- 2026-03-30T14:55:24Z – claude – shell_pid=55849 – lane=doing – Assigned agent via workflow command
