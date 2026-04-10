---
work_package_id: WP02
title: Fix Habits Midnight Anchor
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-003
- FR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
history:
- date: '2026-04-10T17:15:00Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-habits/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
tags: []
---

# WP02: Fix Habits Midnight Anchor

## Objective

Change the habits agent's due_date convention from midnight ET (`00:00:00`) to end-of-day ET (`23:59:59`) so daily habit tasks remain "on time" throughout the day instead of appearing overdue from the moment they're created. This addresses Bug A from `research.md`.

## Context

The habits agent currently uses this template at around line 85 of AGENTS.md:
```
{"due_date": "<YYYY-MM-DD>T00:00:00<ET_OFFSET>"}
```

Morning cron fires at 7:05 AM ET. By then, the task (due at midnight ET) has already been "due" for 7 hours. As the day progresses, the "hours overdue" grows, producing Kent's reported symptom of "seemingly random hours overdue."

**Fix:** Change the template to use `23:59:59` (end of day), so the task remains "on time" until end-of-day and only flips to overdue after midnight ET.

**Files:**
- Office2: `/data/services/openclaw/habits-agent/AGENTS.md`
- Repo copy: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (must stay in sync)

**Change control:** Tier 3 (agent prompts). No backup required.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP02 --agent claude`

---

## Subtask T006: Update Habits Template to End-of-Day

**Purpose**: Change the due_date template from midnight to end-of-day.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Read the current AGENTS.md at lines 79-95 to confirm the exact template location
3. Find the template line (around line 85):
   ```
   {"due_date": "<YYYY-MM-DD>T00:00:00<ET_OFFSET>"}
   ```
4. Replace with:
   ```
   {"due_date": "<YYYY-MM-DD>T23:59:59<ET_OFFSET>"}
   ```
5. Also update any instances in the surrounding example text that show the same pattern

**Validation**:
- [ ] Line 85 (or wherever the template is) uses `23:59:59`
- [ ] No instance of `T00:00:00<ET_OFFSET>` remains in the habits AGENTS.md
- [ ] No instances of `T23:59:59` pattern are introduced elsewhere by mistake

---

## Subtask T007: Add Explanation About End-of-Day Convention

**Purpose**: Document WHY the template uses end-of-day so future contributors don't "fix" it back to midnight.

**Steps**:
1. Immediately before or after the template line (T006), add:
   ```
   **Why end-of-day (23:59:59) instead of midnight (00:00:00)?**

   A midnight anchor makes the task appear overdue from the moment the
   morning cron fires at 7:05 AM ET, because the deadline is already in
   the past. End-of-day anchoring means the task stays "on time"
   throughout the day and only flips to overdue after midnight ET.

   This is the correct convention for daily tasks that should be
   completed "sometime today." Do NOT change this back to 00:00:00
   without understanding issue #112 and the research in mission 025.
   ```

**Validation**:
- [ ] Explanation block is present
- [ ] References issue #112 and mission 025 for future maintainers

---

## Subtask T008: Sync to Repo Copy

**Purpose**: Keep the repo-side copy in sync with what's deployed on office2.

**Steps**:
1. From the worktree, copy the updated AGENTS.md from office2:
   ```bash
   scp office2-claude:/data/services/openclaw/habits-agent/AGENTS.md \
       scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   ```
2. Verify the sync:
   ```bash
   # md5 should match
   md5 -q scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   ssh office2-claude "md5sum /data/services/openclaw/habits-agent/AGENTS.md | awk '{print \$1}'"
   ```

**Validation**:
- [ ] Repo copy matches office2 copy (md5 match)
- [ ] Both files contain the updated template and explanation

---

## Subtask T009: Verify Fix with Real Habits Run

**Purpose**: Confirm the fix works end-to-end by triggering the habits cron and checking the resulting task.

**Steps**:
1. Trigger the habits morning check-in cron:
   ```bash
   ssh office2-claude "openclaw cron run 3082343c-bc7f-47ee-916b-ee070b1e50dc"
   ```
   (That's the `habits-morning-checkin` cron ID — verify with `openclaw cron list | grep habits` if unsure)
2. Wait 30-60 seconds for the run to complete
3. Query a habit task via Vikunja API to see the stored due_date:
   ```bash
   ssh office2-claude 'curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" "https://office2.tail0f5f56.ts.net/api/v1/tasks/16" | python3 -m json.tool | grep -E "title|due_date|done"'
   ```
   (Task ID 16 is "Morning shoulder PT" as observed in research. If it's not a habit task anymore, grab any habit task ID from `/tasks/all?filter=project_id=13`.)
4. Verify the due_date stored in Vikunja is now the end-of-day moment, not midnight. Expected stored form: `2026-04-10T03:59:59Z` (which is 23:59:59 on April 10 EDT = 03:59:59 on April 11 UTC).
5. Also check the session log to confirm the agent sent the new format:
   ```bash
   ssh office2-claude 'ls -t /home/claude/.openclaw/agents/felix-admin-habits/sessions/*.jsonl | head -1 | xargs grep -o "due_date[^,}]*" | head -5'
   ```
   Expected: values containing `23:59:59-04:00` (or `-05:00` in winter).

**Validation**:
- [ ] Agent sent due_date with `23:59:59` and ET offset (not `Z` and not `00:00:00`)
- [ ] Vikunja stored the task with a due_date corresponding to end-of-day ET
- [ ] Kent can confirm (or the planner can confirm later) that the task appears in Vikunja's Today view, not Overdue

---

## Definition of Done

- [ ] Habits AGENTS.md on office2 uses end-of-day template (23:59:59)
- [ ] Explanation block present with #112/mission 025 references
- [ ] Repo copy synced and md5-verified
- [ ] Real habits cron run produces the new format
- [ ] Vikunja stored value corresponds to end-of-day ET
- [ ] No regression in other habits agent behavior

## Risks

- **Cron may not run immediately on trigger**: The `cron run` command enqueues the job; it may take 10-30 seconds to actually execute. Allow enough wait time.
- **Vikunja's "Today" filter logic may behave unexpectedly**: The assumption is that tasks with due_date = end-of-day today appear in the Today view. If that's not true, the fix may need to go to noon ET or another convention instead. Verify empirically.
- **Test task may overlap with real habits data**: The cron runs against real habit tasks. The fix updates them in place; there's no separate test flow. This is acceptable because the change is backward-compatible (Vikunja will just show the updated due time).

## Reviewer Guidance

- Confirm the template change is in the right location
- Verify the explanation text references the relevant issue and mission
- Check the md5 match between office2 and repo copies
- Confirm the real-run verification was done (not just planned)
