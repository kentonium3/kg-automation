---
work_package_id: WP01
title: Fix vikunja_api Skill
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
agent: "claude:opus-4.6:reviewer:reviewer"
shell_pid: "35660"
history:
- date: '2026-04-10T17:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: kitty-specs/025-vikunja-date-timezone-bug/artifacts/
execution_mode: planning_artifact
owned_files:
- kitty-specs/025-vikunja-date-timezone-bug/artifacts/skill-update-report.md
tags: []
---

# WP01: Fix vikunja_api Skill

## Objective

Update the canonical `vikunja_api` skill on office2 so its example and description use the ET offset format instead of the UTC `Z` suffix. This addresses Bug B (from `research.md`) at the single layer that all Vikunja-interacting agents reference. After this WP, any agent reading the skill for API syntax will get timezone-aware guidance consistent with USER.md.

## Context

The skill lives at `~/.openclaw/skills/vikunja-api/SKILL.md` on office2. It has no repo-side copy currently (noted as a future improvement in #152's extension plan). For this WP, we modify it directly on office2 and document the change in a report artifact.

**Key line to update (line ~159):**
```bash
-d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00Z", "priority": 1}' \
```

**Key line to update (line ~165):**
```
- `due_date` must be ISO 8601 format (e.g., `2026-04-15T00:00:00Z`)
```

The new format should be explicit about using the ET offset, and should include a pointer to dynamic offset resolution (via `TZ=America/New_York date +%:z`) so the example works across EDT/EST transitions.

**Change control:** Tier 3 (agent skill docs). No backup required by the tier taxonomy, but a manual copy (T001) gives us a safety net.

**Office2 access:** `ssh office2-claude`

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP01 --agent claude`

---

## Subtask T001: Backup Current Skill

**Purpose**: Save a copy of the current skill before editing so we can diff and/or restore if needed.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Copy the skill to a backup path:
   ```bash
   cp ~/.openclaw/skills/vikunja-api/SKILL.md ~/.openclaw/skills/vikunja-api/SKILL.md.backup.2026-04-10
   ```
3. Verify the backup exists and has the same content:
   ```bash
   diff ~/.openclaw/skills/vikunja-api/SKILL.md ~/.openclaw/skills/vikunja-api/SKILL.md.backup.2026-04-10
   ```
   Should produce no output (files identical).

**Validation**:
- [ ] Backup file exists
- [ ] Backup matches current skill content

---

## Subtask T002: Update Skill Example to ET Offset

**Purpose**: Replace the UTC `Z` example with an ET offset example that agents should copy.

**Steps**:
1. Edit `~/.openclaw/skills/vikunja-api/SKILL.md` on office2
2. Find the task creation example (around line 159). Current:
   ```bash
   -d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00Z", "priority": 1}' \
   ```
3. Replace with:
   ```bash
   -d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00-04:00", "priority": 1}' \
   ```
4. Double-check that only the one example was changed — do NOT change filter expressions lower in the file (e.g., `due_date < 2026-04-01T00:00:00Z` on line ~318). Those are QUERY filters and can remain in whatever format is currently there; the fix target is the CREATION example.

**Validation**:
- [ ] Line with task creation example shows the ET offset `-04:00`
- [ ] Other references to `Z` format in the file (filters, queries) are unchanged
- [ ] `grep -c '00:00:00Z' ~/.openclaw/skills/vikunja-api/SKILL.md` returns a lower number than before the change

---

## Subtask T003: Update Skill Description Text

**Purpose**: Make the description text match the new example and explicitly warn against using `Z`.

**Steps**:
1. Find the line (around line 165) that currently says:
   ```
   - `due_date` must be ISO 8601 format (e.g., `2026-04-15T00:00:00Z`)
   ```
2. Replace with:
   ```
   - `due_date` must be ISO 8601 format with an explicit timezone offset
     (e.g., `2026-04-15T00:00:00-04:00` for EDT, `-05:00` for EST).
     Do NOT use the `Z` (UTC) suffix for task creation — it causes
     off-by-one errors for tasks created in the evening ET.
   ```

**Validation**:
- [ ] Description references the ET offset, not `Z`
- [ ] The "off-by-one" warning is present

---

## Subtask T004: Add Dynamic Offset Resolution Note

**Purpose**: Give agents a way to compute the current ET offset dynamically so they don't hardcode `-04:00` and break at DST transition.

**Steps**:
1. Immediately after the updated description text (from T003), add:
   ```
   To determine the current offset dynamically (handles EDT/EST transitions
   automatically):

   ```bash
   TZ=America/New_York date +%:z
   ```

   This returns `-04:00` during EDT and `-05:00` during EST. Use this in
   your due_date computation rather than hardcoding an offset.
   ```
2. Ensure the code block formatting is correct (triple backticks, bash language tag).

**Validation**:
- [ ] The new note includes the `TZ=America/New_York date +%:z` command
- [ ] The note is clearly formatted and readable in context

---

## Subtask T005: Verify and Document the Change

**Purpose**: Confirm the skill is now self-consistent and produce a report artifact documenting the change.

**Steps**:
1. Verify the skill change with targeted greps:
   ```bash
   # Should find the new example line (1 result)
   grep -n '00:00:00-04:00' ~/.openclaw/skills/vikunja-api/SKILL.md

   # Should NOT find the old UTC example (but MAY find filter-side Z usage, which is fine)
   grep -n 'due_date.*00:00:00Z' ~/.openclaw/skills/vikunja-api/SKILL.md

   # Should find the dynamic offset note
   grep -n 'TZ=America/New_York date' ~/.openclaw/skills/vikunja-api/SKILL.md
   ```
2. Create the report artifact at `kitty-specs/025-vikunja-date-timezone-bug/artifacts/skill-update-report.md` with:
   - What was changed (before/after for each edit)
   - Grep verification output
   - Path to the backup file
   - A note that the skill has no repo-side copy, so the backup is the only rollback path

**Validation**:
- [ ] Grep for the new format finds the expected line
- [ ] Report artifact exists and documents the change
- [ ] Backup file path is recorded in the report

---

## Definition of Done

- [ ] Backup of original skill exists on office2
- [ ] Skill example uses ET offset (`-04:00`) instead of `Z`
- [ ] Skill description explicitly warns against `Z` suffix for creation
- [ ] Dynamic offset resolution note added
- [ ] Report artifact documents the change with verification output
- [ ] No unrelated changes to the skill (filter/query examples untouched)

## Risks

- **Skill gets regenerated by OpenClaw**: OpenClaw may re-install the skill from its source if the skill is classified as "openclaw-managed". If that happens, the change could be reverted. Mitigation: verify that editing in place persists; if not, escalate to Kent before proceeding to WP02.
- **Other examples in the skill use different formats**: The filter expressions later in the file (line ~318) use `Z` format for query operators. Those are queries against Vikunja's storage (which IS UTC), so they're semantically different from creation payloads. Do NOT change them.

## Reviewer Guidance

- Verify the edit is in the creation section, not the query section
- Confirm the grep results match the expected outputs in T005
- Check the report artifact is discoverable and accurate

## Activity Log

- 2026-04-10T17:40:31Z – claude:opus-4.6:implementer:implementer – shell_pid=34529 – Started implementation via action command
- 2026-04-10T17:47:05Z – claude:opus-4.6:implementer:implementer – shell_pid=34529 – Skill updated, verified with grep, report artifact created
- 2026-04-10T17:47:33Z – claude:opus-4.6:reviewer:reviewer – shell_pid=35660 – Started review via action command
- 2026-04-10T17:48:43Z – claude:opus-4.6:reviewer:reviewer – shell_pid=35660 – Review passed: backup verified on office2, creation example uses -04:00 offset at line 159, description forbids Z suffix with off-by-one warning at lines 165-168, dynamic offset note with TZ=America/New_York date +%:z at line 174, query filter at line 331 correctly unchanged, report artifact accurate, no scope creep in commit.
