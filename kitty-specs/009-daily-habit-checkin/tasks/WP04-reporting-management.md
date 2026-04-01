---
work_package_id: WP04
title: Standing Orders — Reporting and Habit Management
lane: planned
dependencies: [WP03]
requirement_refs:
- FR-008
- FR-009
- FR-010
- FR-011
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T015, T016, T017, T018]
history:
- date: '2026-04-01T01:46:04Z'
  event: created
  actor: claude
---

# WP04: Standing Orders — Reporting and Habit Management

## Implementation command

```bash
spec-kitty implement WP04 --base WP03
```

## Objective

Add the weekly pattern report, on-demand track record query, and habit
management (add/pause/remove) sections to AGENTS.md. These complete the
agent's standing orders.

## Context

- **AGENTS.md**: Created in WP03 with check-in and completion. This WP adds reporting and management.
- **Data model**: `kitty-specs/009-daily-habit-checkin/data-model.md` — pattern report computation, completion rate formula
- **Completion rate formula**: (complete + rescheduled) / (complete + rescheduled + will-not-do + no-response) for scheduled days
- **"This week"**: Monday–Sunday of current week. **"Last week"**: prior Monday–Sunday.

## Subtask guidance

### T015: Weekly pattern report section

**Purpose**: Teach the agent to generate a concise weekly pattern report.

**Steps**:
1. Add a "Weekly pattern report" section to AGENTS.md:
   ```markdown
   ## Weekly pattern report

   When triggered by the Sunday evening cron job, generate a pattern report.

   ### Step 1: Determine date ranges

   - This week: Monday to Sunday of the current week
   - Last week: Monday to Sunday of the prior week

   ### Step 2: Query completion history

   For each active habit:
   1. Fetch comments: `GET /tasks/{habit_id}/comments?per_page=50&order_by=desc`
   2. Parse each comment for date and state
   3. Filter to this week and last week date ranges
   4. For days with no comment on a scheduled day, count as "no-response"

   ### Step 3: Calculate rates

   For each habit:
   - scheduled_days = days in the week where the habit's frequency applies
   - positive = count of "complete" + "rescheduled" comments
   - rate = positive / scheduled_days (as percentage)

   Overall rate = sum(all positive) / sum(all scheduled_days)

   ### Step 4: Format the report

   ```
   Weekly habits — Mar 24–30 vs Mar 17–23:

   Wake 5AM:     ████░░ 67% (was 83%) ↓
   Meditate:     ██████ 100% (was 86%) ↑
   Morning PT:   █████░ 86% (was 71%) ↑
   Training:     ███░░░ 67% (was 100%) ↓
   10K steps:    ████░░ 57% (was 57%) →
   Reading:      ██████ 86% (was 100%) ↓
   Evening PT:   █████░ 86% (was 86%) →

   Overall: 78% (was 83%) ↓
   ```

   Rules:
   - Use simple bar indicators (█ and ░), 6 characters wide
   - Show percentage and trend arrow (↑ ↓ →)
   - Keep to 20 lines or fewer
   - No motivational commentary — just the numbers
   ```

**Validation**:
- [ ] Date range logic documented (Mon–Sun)
- [ ] Completion rate formula matches spec (C-007)
- [ ] Report format is concise (<=20 lines)
- [ ] Trend indicators (up/down/same) included

### T016: On-demand track record query

**Purpose**: Let Kent ask about his habits at any time.

**Steps**:
1. Add a "Track record query" section:
   ```markdown
   ## Track record query

   When Kent asks "how am I doing on my habits?", "show my track record",
   "habit status", or any natural variation:

   1. Query the last 4 weeks of completion history (same method as weekly report)
   2. Calculate per-habit and overall rates for each of the 4 weeks
   3. Format as a 4-week summary:

   ```
   Habit track record — last 4 weeks:

   Wake 5AM:     83% → 67% → 83% → 67%
   Meditate:     71% → 86% → 100% → 86%
   [... one line per habit ...]

   Overall:      75% → 78% → 85% → 78%
                 ← oldest        newest →
   ```

   Keep the same concise format. No walls of text.
   ```

### T017: Habit add/pause/remove section

**Purpose**: Let Kent manage habits via WhatsApp.

**Steps**:
1. Add a "Habit management" section:
   ```markdown
   ## Habit management

   ### Adding a habit

   When Kent says "add [habit name]" or "new habit: [description]":

   1. Parse the habit name and frequency (default: Daily if not specified)
   2. Parse identity label (default: personal if not specified)
   3. Confirm before creating:
      "I'll add [name] as a [label] habit, [frequency]. Correct?"
   4. Wait for confirmation
   5. Create the task in the Habits project via vikunja_api skill
   6. Add the identity label
   7. Confirm: "Added [name] to your habits. It will appear in tomorrow's check-in."

   ### Pausing a habit

   When Kent says "pause [habit]" or "stop tracking [habit]":

   1. Match the habit by name (fuzzy matching)
   2. Confirm: "I'll pause [name]. It won't appear in check-ins but history is preserved. Resume anytime."
   3. Mark the task description with "(PAUSED)" prefix
   4. Paused habits are excluded from check-ins and reports

   ### Removing a habit

   When Kent says "remove [habit]" or "delete [habit]":

   1. Match by name
   2. Confirm: "I'll archive [name]. History is preserved but it won't appear in check-ins or reports."
   3. Mark the Vikunja task as done (archived state) — do NOT delete it

   ### Resuming a paused habit

   When Kent says "resume [habit]" or "unpause [habit]":

   1. Match by name (check for "(PAUSED)" prefix)
   2. Remove the "(PAUSED)" prefix from description
   3. Confirm: "Resumed [name]. It will appear in tomorrow's check-in."
   ```

**Validation**:
- [ ] Add flow includes confirmation step
- [ ] Pause preserves history
- [ ] Remove archives (done=true) rather than deletes
- [ ] Resume flow documented

### T018: Deploy updated AGENTS.md and verify

**Purpose**: Deploy the complete standing orders and verify.

**Steps**:
1. Deploy:
   ```bash
   ssh office2-claude "cat > /data/services/openclaw/habits-agent/AGENTS.md" \
     < scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   ```
2. Verify file size:
   ```bash
   ssh office2-claude "wc -c /data/services/openclaw/habits-agent/AGENTS.md"
   ```
3. Test the agent understands reporting:
   ```bash
   ssh office2-claude "openclaw agent --agent felix-admin-habits \
     --message 'Summarize your reporting capabilities.' --json --timeout 30"
   ```

**Validation**:
- [ ] Updated AGENTS.md deployed
- [ ] Within 20K bootstrap limit
- [ ] Agent describes weekly report and track record query

## Definition of done

- [ ] Weekly pattern report section added to AGENTS.md
- [ ] On-demand track record query section added
- [ ] Habit management (add/pause/remove/resume) section added
- [ ] Deployed to office2 and verified

## Risks

- **AGENTS.md approaching size limit**: Check file size after adding these
  sections. If over 18K chars, consider moving the track record and management
  sections to a separate reference file.
