# Claude Code Mission: Vikunja Configuration Discovery

## Mission type
**Discovery only. Read-only. Make zero changes to Vikunja, the database, or any
file on office2.** The output is a structured report written to the repo. Nothing
else changes.

---

## Background

Vikunja is the task management system running on office2. It was set up by
`scripts/vikunja/setup_vikunja.py` (read this file before starting). The setup
script intended to create a project hierarchy for task grouping and saved filters
for cross-project views (Today, Upcoming, Overdue). It appears projects and filters
may have been mixed up — some things that should be saved filters were created as
projects, and there is a suspected duplicate Inbox situation.

The goal of this mission is to get a complete, accurate picture of what actually
exists in Vikunja right now so that a cleanup plan can be designed.

---

## What you have access to

**Vikunja API:**
- HTTPS URL: `https://office2.tail0f5f56.ts.net/api/v1`
- API token location on office2: `/data/services/openclaw/secrets/vikunja-api`
- Auth header: `Authorization: Bearer <token>`

**SSH access to office2:**
- `ssh -i ~/.ssh/id_ed25519 kgale@100.92.197.90`
- Read the API token via SSH: `ssh -i ~/.ssh/id_ed25519 kgale@100.92.197.90 'cat /data/services/openclaw/secrets/vikunja-api'`
- Then use the token to make API calls from your local machine against
  `https://office2.tail0f5f56.ts.net` (Tailscale must be active)

**Repo files to read before starting:**
- `scripts/vikunja/setup_vikunja.py` — what was intended to be created
- `docs/handbooks/vikunja-ops.md` — documented expected state
- `docs/Vikunja.md` — Kent's notes on known issues with the current setup

**Vikunja API reference (version 0.24.6):**
- Projects: `GET /api/v1/projects`
- Filters: `GET /api/v1/filters`
- Labels: `GET /api/v1/labels`
- Tasks in a project: `GET /api/v1/projects/{id}/tasks`
- All tasks: `GET /api/v1/tasks/all`

---

## What to discover

### 1. Full project inventory
For every project that exists in Vikunja:
- ID, title, parent_project_id, parent project name (if any)
- Is it a top-level project or a child?
- Task count (how many tasks live directly in this project)
- Flag any project whose name matches a filter concept: Today, Upcoming,
  Overdue, Someday — these should be saved filters, not projects

### 2. Full saved filter inventory
For every saved filter that exists:
- ID, title, filter expression
- Compare against the intended filters from `setup_vikunja.py`:
  Today, Upcoming, Overdue
- Note any missing filters or filters with wrong expressions

### 3. Dual Inbox investigation
Vikunja has a native "Inbox" concept: a special built-in project that
automatically receives tasks created without an explicit project assignment.
The setup script also created an "Inbox" project under "Everyday".

Find and distinguish:
- The native Vikunja inbox (if it exists as a separate entity)
- The "Inbox" project created under "Everyday"
- How many tasks are in each
- Whether the tasks in the created Inbox were routed there intentionally
  by Felix agents or ended up there by accident

### 4. Label inventory
- List all labels: ID, title, hex_color
- Verify the three identity labels exist: personal (#2196f3), intentional
  (#4caf50), metalcasework (#ff9800)
- Note any unexpected labels

### 5. Task sample from key projects
For the Inbox project(s) and any project with more than 0 tasks:
- Total task count
- First 10 task titles (to understand what kind of content is there)
- How many tasks have identity labels vs. no label
- How many tasks have due dates vs. no due date

### 6. Discrepancy summary
Explicitly list every discrepancy between what `setup_vikunja.py` intended
to create and what actually exists. Use these categories:
- **Should be filter, is a project**: (list each)
- **Should exist but missing**: (list each)
- **Exists but unexpected**: (list each)
- **Inbox duplication**: describe the situation
- **Data concerns**: any tasks in wrong location, unlabeled tasks, etc.

---

## Output

Write a single markdown report to:
`docs/reports/vikunja-discovery-YYYY-MM-DD.md`

Use this structure:

```markdown
---
title: Vikunja Configuration Discovery Report
date: YYYY-MM-DD
doc_type: report
status: complete
---

# Vikunja Configuration Discovery Report
**Date**: YYYY-MM-DD
**Vikunja version**: (from API /info)
**API base**: https://office2.tail0f5f56.ts.net/api/v1

## Projects
(table: id | title | parent | task_count | notes)

## Saved Filters
(table: id | title | expression | status vs. intended)

## Labels
(table: id | title | color | status)

## Inbox Investigation
(detailed prose + task counts for each inbox)

## Task Sample (Inbox)
(list of first 10 task titles, label coverage, due date coverage)

## Discrepancies
### Should be filter, is a project
### Should exist but missing
### Exists but unexpected
### Inbox duplication
### Data concerns

## Recommended Cleanup Actions
(ordered list — what to do, in what sequence, to reach clean state)
Not a spec — just a clear statement of what needs to happen.
```

---

## Constraints

- **Read only.** Do not create, update, or delete any Vikunja project, filter,
  label, or task. Do not modify any file on office2.
- **No credentials in output.** Do not include the API token or any secret in
  the report or in any file you write.
- **Do not modify the database directly.** Use the REST API only.
- If you hit an API endpoint that returns an error, note it in the report and
  move on — do not retry destructively.
- Write the report and then stop. Do not proceed to implement any fixes.

---

## Definition of done

- [ ] `docs/reports/vikunja-discovery-YYYY-MM-DD.md` exists and is complete
- [ ] All six discovery sections are populated with real data from the API
- [ ] Discrepancy summary is explicit and actionable
- [ ] Recommended cleanup actions are listed in order
- [ ] No changes made to Vikunja or office2
