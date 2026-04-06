# Implementation Plan: F018 Habit Today Filter Visibility

**Branch**: `main` | **Date**: 2026-04-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/018-habit-today-filter-visibility/spec.md`
**Mission**: software-dev

---

## Summary

Add one step to the felix-admin-habits morning check-in workflow: set
`due_date = today` on each scheduled habit before delivering the WhatsApp
message. Update the agent standing orders (AGENTS.md) and the habits
operations runbook. No new services, no code, no data model changes.

## Technical Context

**Language/Version**: N/A — this feature edits agent instruction files
(markdown) and deploys them to office2
**Primary Dependencies**: Vikunja REST API (task update endpoint), OpenClaw
agent system (felix-admin-habits)
**Storage**: Vikunja (existing — due_date field on existing tasks)
**Testing**: Manual verification — trigger morning check-in cron, confirm
habits appear in Vikunja Today filter
**Target Platform**: office2 (Ubuntu 24.04 LTS) — agent runtime
**Constraints**: Must complete within existing 120-second cron timeout;
read/write access to Vikunja API via existing token

## Constitution Check

*GATE: Passed.*

- **Tier 3 (Standard)**: Agent prompt changes are logic/workflow tier —
  proceed with dry-run or sandbox validation where available
- **Privacy**: No change to privacy handling; habits from private context
  appear as names only (unchanged from F009)
- **Narrow scope**: One new behavior added within existing agent scope
- **Never fail silently**: Failed due_date updates must be reported

No constitution violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```
kitty-specs/018-habit-today-filter-visibility/
├── plan.md              # This file
├── spec.md              # Feature specification
├── meta.json            # Feature identity metadata
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks/               # Work package files (created by /spec-kitty.tasks)
```

### Files Modified (repository)

```
scripts/openclaw/agents/felix-admin-habits/
└── AGENTS.md            # Add due_date step to morning check-in workflow

docs/runbooks/
└── habits-ops.md        # Add due_date documentation and troubleshooting
```

### Deployed Files (office2)

```
/data/services/openclaw/habits-agent/
└── AGENTS.md            # Deployed copy — must match repo after update
```

## Implementation Approach

### What changes

1. **AGENTS.md** — insert a new "Step 3: Set due_date for Today visibility"
   between the existing Step 2 (query active habits) and Step 4 (format
   check-in message). The new step instructs the agent to call
   `PUT /api/v1/tasks/{id}` with `{"due_date": "<today>T00:00:00Z"}`
   for each habit scheduled for today.

2. **habits-ops.md** — add a section explaining that habits appear in the
   Today filter after the morning check-in runs. Add a troubleshooting
   entry: "Habits not appearing in Today → verify morning cron ran
   successfully; check `openclaw cron runs --id <uuid>` for errors."

3. **Deploy to office2** — copy the updated AGENTS.md to the deployed
   agent workspace using the existing deployment pattern from habits-ops.md.

### What does NOT change

- Completion recording (comment model unchanged)
- Weekly reporting (queries comments by date — unaffected)
- Cron configuration (same schedule, same timeout)
- WhatsApp message format and reply handling
- Task structure in Vikunja (no new tasks, no recurrence)

### Error handling approach

The new step must be non-blocking: if the API call fails for one habit,
log the error and continue with the remaining habits. The WhatsApp
check-in must still be delivered even if all due_date updates fail.
This matches the agent's existing error handling pattern for API calls.

## Verification Plan

After deployment:

1. Manually trigger the morning check-in cron
2. Confirm habits appear in Vikunja Today filter
3. Confirm habits not scheduled today do NOT appear
4. Confirm WhatsApp message was delivered
5. Check cron run output for any API errors

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Vikunja API rejects due_date update | Very Low | Medium | F017 confirmed the call works on v0.24.6 |
| Agent misinterprets new step | Low | Medium | Clear, specific instructions in AGENTS.md |
| Deployment drift (office2 copy out of sync) | Low | Low | Deployment step is part of the WP |

---

**Branch contract (confirmed)**:
- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: **yes**

---

**END OF PLAN**
