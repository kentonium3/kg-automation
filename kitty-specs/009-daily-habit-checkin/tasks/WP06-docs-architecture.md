---
work_package_id: WP06
title: Documentation and Architecture Updates
lane: "for_review"
dependencies: [WP05]
requirement_refs:
- FR-012
- FR-013
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 009-daily-habit-checkin-WP05
base_commit: f28885767a163d185a9f0b4bc43d1bdd0b2e6523
created_at: '2026-04-01T03:56:54.955362+00:00'
subtasks: [T026, T027, T028]
agent: claude-code
shell_pid: '1991'
history:
- date: '2026-04-01T01:46:04Z'
  event: created
  actor: claude
---

# WP06: Documentation and Architecture Updates

## Implementation command

```bash
spec-kitty implement WP06 --base WP05
```

## Objective

Create the habits operations runbook and update architecture documentation
with the new agent and cron jobs.

## Context

- **Runbook location**: `docs/handbooks/habits-ops.md` (new file)
- **Architecture data**: `docs/design/architecture/data/service-inventory.json`
- **Architecture narrative**: `docs/design/architecture/service-inventory.md`
- **Existing runbook pattern**: `docs/handbooks/inbox-ops.md` (F008) — follow this structure
- **Existing architecture entries**: F008 added felix-admin-capture agent and inbox-processing crons

## Subtask guidance

### T026: Create habits operations runbook

**Purpose**: Document how to operate, monitor, and troubleshoot habit check-ins.

**Steps**:
1. Create `docs/handbooks/habits-ops.md` with standard frontmatter:
   ```yaml
   ---
   title: Habit Check-in Operations Runbook
   doc_type: handbook
   status: draft
   ---
   ```
2. Follow the structure of `docs/handbooks/inbox-ops.md`. Include:

   **Overview**: What felix-admin-habits does, where it runs, how often.

   **Agent management**:
   - Agent name, workspace path, source in repo
   - How to update workspace files
   - How to verify: `openclaw agents list`

   **Schedule**:
   - Morning check-in: 7:05 AM ET daily
   - Weekly report: Sunday 6 PM ET
   - How to view, manually trigger, view run history

   **Vikunja habits project**:
   - How to view habits in Vikunja web UI
   - How to check completion history (comments on habit tasks)
   - How to add/remove habits directly in Vikunja

   **WhatsApp interaction**:
   - Check-in delivery and reply format
   - On-demand queries ("how am I doing on habits?")
   - Habit management via WhatsApp

   **Troubleshooting**:
   | Symptom | Check | Fix |
   |---------|-------|-----|
   | No check-in delivered | `openclaw cron list` | Verify cron exists and is enabled |
   | Completion not recorded | Check Vikunja task comments | Verify vikunja_api skill |
   | Agent not responding | `openclaw agents list` | Restart gateway |
   | Session lock error | Check for stale .lock files | Remove stale locks |

   **Privacy boundary**: Same as all agents — `02-Growth/_private/` never accessed.

**Validation**:
- [ ] Runbook covers all sections
- [ ] Frontmatter passes CI validation
- [ ] Follows inbox-ops.md pattern

### T027: Update service-inventory.json

**Purpose**: Record the new agent and cron jobs.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json`
2. Under the `openclaw-gateway` service entry, add to the `agents` object:
   ```json
   "felix-admin-habits": {
     "workspace": "/data/services/openclaw/habits-agent",
     "model": "anthropic/claude-sonnet-4-6",
     "purpose": "Daily habit check-in, completion tracking, weekly pattern reports",
     "source_in_repo": "scripts/openclaw/agents/felix-admin-habits/",
     "deployed_by": "F009"
   }
   ```
3. Add a new service entry for the habit cron jobs:
   ```json
   {
     "name": "habit-checkin",
     "type": "openclaw-cron",
     "host": "office2",
     "agent": "felix-admin-habits",
     "schedules": [
       {"name": "habits-morning-checkin", "cron": "5 11 * * *", "local_time": "7:05 AM ET"},
       {"name": "habits-weekly-report", "cron": "0 22 * * 0", "local_time": "Sunday 6:00 PM ET"}
     ],
     "timeout_seconds": 120,
     "session_mode": "isolated",
     "deployed_by": "F009",
     "status": "active",
     "purpose": "Daily habit check-in and weekly pattern report",
     "runbook": "docs/handbooks/habits-ops.md"
   }
   ```
4. Update `last_updated` and `updated_by: "F009"`

**Validation**:
- [ ] JSON is valid
- [ ] Agent entry under openclaw-gateway.agents
- [ ] Cron entry as separate service
- [ ] updated_by: "F009"

### T028: Update service-inventory.md narrative

**Purpose**: Add the habits agent and crons to the narrative doc.

**Steps**:
1. Read `docs/design/architecture/service-inventory.md`
2. Add a "Felix Admin Habits Agent (F009)" section after the inbox capture
   agent section, following the same format
3. Add the 2 cron entries to the Scheduled Jobs table

**Validation**:
- [ ] Narrative section added
- [ ] Scheduled Jobs table updated with 2 entries
- [ ] Consistent with service-inventory.json

## Definition of done

- [ ] `docs/handbooks/habits-ops.md` exists with all required sections
- [ ] `service-inventory.json` updated with agent and cron entries
- [ ] `service-inventory.md` updated with narrative and table entries
- [ ] All docs pass CI validation

## Risks

- **Architecture doc conflicts**: If other features have updated
  service-inventory.json since the worktree was created, resolve by
  taking the latest version and adding F009 entries.

## Activity Log

- 2026-04-01T03:56:55Z – claude-code – shell_pid=1991 – lane=doing – Assigned agent via workflow command
- 2026-04-01T03:58:59Z – claude-code – shell_pid=1991 – lane=for_review – Ready for review: habits-ops.md runbook, service-inventory.json with agent and cron entries, service-inventory.md with narrative section and scheduled jobs. Also corrected WhatsApp dm_policy to 'disabled' in both files. CI passes.
