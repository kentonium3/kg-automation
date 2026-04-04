---
title: Vikunja Configuration Discovery Report
date: 2026-04-03
doc_type: report
status: complete
---

# Vikunja Configuration Discovery Report

**Date**: 2026-04-03
**Vikunja version**: v0.24.6
**API base**: `https://office2.tail0f5f56.ts.net/api/v1`

## Projects

| ID | Title | Parent | Task Count | Notes |
|---|---|---|---|---|
| 1 | Inbox | (top-level) | 11 | Native Vikunja inbox (auto-created at user registration) |
| 2 | Everyday | (top-level) | 0 | Parent container only |
| 3 | Inbox | Everyday (id=2) | 0 | Setup script created this under Everyday |
| 4 | Someday | Everyday (id=2) | 6 | Intended as a project per setup script |
| 5 | Personal Growth & Transformation | (top-level) | 0 | Empty |
| 6 | Business Acquisition | (top-level) | 0 | Empty |
| 7 | CT-90day | Business Acquisition (id=6) | 0 | Empty |
| 8 | Health & Conditioning | (top-level) | 0 | Empty |
| 9 | Intentional LLC | (top-level) | 2 | Felix system tasks |
| 10 | Metal Casework | (top-level) | 0 | Empty |
| 11 | Goals | (top-level) | 4 | Created by F006 (setup_goals.py) |
| 12 | Research | (top-level) | 1 | Not in setup script — created manually or by agent |
| 13 | Habits | (top-level) | 7 | Not in setup script — created by F009 |

**Total projects**: 13 (plus 3 saved filters appearing as virtual projects)

## Saved Filters

| Filter ID | Project ID | Title | Expression | Status vs. Intended |
|---|---|---|---|---|
| 1 | -2 | Today | `due_date >= now/d && due_date < now/d+1d && done = false` | Matches setup_vikunja.py exactly |
| 2 | -3 | Upcoming | `due_date > now/d && due_date <= now+14d && done = false` | Matches setup_vikunja.py exactly |
| 3 | -4 | Overdue | `due_date < now/d && done = false` | Matches setup_vikunja.py exactly |

All three filters have `sort_by: ["due_date"]`, `order_by: ["asc"]` as intended.

**Missing filter**: The Goals filter documented in `vikunja-ops.md` (`project = 11 && done = false`, attributed to F006) does not exist. Only filter IDs 1-3 are present.

**Note**: `GET /api/v1/filters` returns 404 — Vikunja 0.24.x has no list endpoint for filters. Individual filters are accessible via `GET /api/v1/filters/{id}`.

## Labels

| ID | Title | Color | Status |
|---|---|---|---|
| 1 | personal | #2196f3 (blue) | Expected — created by setup_vikunja.py |
| 2 | intentional | #4caf50 (green) | Expected — created by setup_vikunja.py |
| 3 | metalcasework | #ff9800 (orange) | Expected — created by F006 (not in original setup script) |

All three identity labels are present and correct. No unexpected labels.

## Inbox Investigation

There are two "Inbox" entities:

### Native Inbox (id=1, top-level)

- **Type**: Vikunja's built-in inbox project, auto-created at user registration
- **Parent**: None (top-level, `parent_project_id=0`)
- **Task count**: 11 (9 open, 2 done)
- **This is the active inbox.** Felix agents and manual task creation route here.

### Created Inbox (id=3, under Everyday)

- **Type**: Regular project created by `setup_vikunja.py` under the "Everyday" parent
- **Parent**: Everyday (id=2)
- **Task count**: 0
- **This is unused.** The setup script created it, but all task routing targets the native inbox (id=1) because tasks created without an explicit project assignment land in the native inbox automatically.

### Why the duplication happened

The setup script defines `{"name": "Everyday", "children": [{"name": "Inbox"}, ...]}`. When the script ran, the native Inbox (id=1) already existed as a top-level project. The script's `find_project_by_name` function matched it (line 128: `parent_project_id == 0`), so it didn't create a duplicate at the top level. However, it then created a *child* Inbox under Everyday because the child lookup (with `parent_id` scoped to Everyday) found no match.

The result: two Inbox projects, one native (active, has tasks) and one under Everyday (empty, unused).

## Task Sample

### Native Inbox (id=1) — 11 tasks

| ID | Title | Labels | Due Date | Done |
|---|---|---|---|---|
| 5 | Diagnose and fix red van interior lights | personal | none | Yes |
| 7 | Get car to shop — coolant leak and oil leak repair | personal | 2026-04-01 | Yes |
| 8 | Upload cardiac lab history to second brain | personal | none | No |
| 9 | Resolve failed OpenClaw skills installs | intentional | none | No |
| 10 | Integrate Google Voice number into KG automation | intentional | none | No |
| 21 | Watch Dries Driesnote DrupalCon address | personal | 2026-04-06 | No |
| 24 | Watch Dries Driesnote Drupalcon address | personal | 2026-04-06 | No |
| 25 | Replace indoor garage door switch | personal | 2026-04-16 | No |
| 26 | Fix plastic covering for greenhouse | personal | 2026-05-15 | No |
| 27 | Respond to Arcadia Financial email | personal | none | No |
| 28 | Call Arcadia Financial to arrange a phone call | personal | 2026-04-03 | No |

**Label coverage**: 11/11 (100%) have identity labels
**Due date coverage**: 6/11 (55%) have due dates
**Duplicate**: Tasks 21 and 24 appear to be the same item (Dries Driesnote)

### Someday (id=4) — 6 tasks

All 6 tasks are labeled `personal`, none have due dates. Content is home improvement/decluttering items. This is appropriate use of a Someday project.

### Goals (id=11) — 4 tasks

All 4 tasks have identity labels and due dates. Content is goal declarations — correct placement.

### Habits (id=13) — 7 tasks

All 7 tasks are labeled `personal`, none have due dates. Content is daily habit check-in items — correct placement.

### Intentional LLC (id=9) — 2 tasks

Both labeled `intentional`, no due dates. Content is Felix system development tasks.

### Research (id=12) — 1 task

One completed task (`intentional` label). This project is not in the setup script.

## Discrepancies

### Should be filter, is a project

None. Kent's notes in `docs/Vikunja.md` suspected this, but the investigation confirms Today, Upcoming, and Overdue are correctly implemented as saved filters (negative IDs: -2, -3, -4), not projects.

### Should exist but missing

- **Goals saved filter**: `vikunja-ops.md` documents a "Goals" saved filter (`project = 11 && done = false`, sort by due_date, attributed to F006). This filter does not exist — only filter IDs 1-3 are present. The Goals *project* (id=11) exists and works, but there is no cross-project saved filter view for goals.

### Exists but unexpected

- **Research project (id=12)**: Not in `setup_vikunja.py`. Contains 1 completed task. Likely created manually or by an agent.
- **Habits project (id=13)**: Not in `setup_vikunja.py`. Contains 7 habit tasks. Created by F009 (daily habit check-in feature). This is expected post-F009 but is not in the original setup script.

### Inbox duplication

Two Inbox entities exist:

| Inbox | ID | Parent | Tasks | Active? |
|---|---|---|---|---|
| Native (built-in) | 1 | top-level | 11 | Yes — all routing targets this |
| Created (setup script) | 3 | Everyday | 0 | No — unused, empty |

The created Inbox (id=3) under Everyday serves no purpose and should be removed.

### Data concerns

1. **Duplicate task**: Tasks 21 and 24 in the native Inbox are both "Watch Dries Driesnote DrupalCon address" with the same due date (2026-04-06). One should be deleted.
2. **Empty projects**: Personal Growth & Transformation, Business Acquisition, CT-90day, Health & Conditioning, and Metal Casework all have 0 tasks. These are legitimate category projects that may receive tasks over time — not a problem, but worth noting.
3. **No tasks in non-Inbox projects**: Most tasks (11/31) are in the Inbox. Only Someday (6), Habits (7), Goals (4), Intentional LLC (2), and Research (1) have tasks. The project hierarchy is underutilized — tasks that could be categorized (e.g., health tasks, home tasks) remain in Inbox.

## Recommended Cleanup Actions

1. **Delete the duplicate Inbox project (id=3)** under Everyday. It has 0 tasks and is unused. This eliminates confusion about which Inbox is active.

2. **Delete duplicate task**: Remove either task 21 or 24 (Dries Driesnote) from the native Inbox.

3. **Create the Goals saved filter** documented in vikunja-ops.md:

   ```
   PUT /api/v1/filters
   {
     "title": "Goals",
     "filters": {
       "filter": "project = 11 && done = false",
       "sort_by": ["due_date"],
       "order_by": ["asc"]
     }
   }
   ```

4. **Consider categorizing Inbox tasks**: 9 open tasks in the Inbox could be moved to appropriate projects (e.g., health-related tasks to Health & Conditioning, home improvement to Everyday). This is a prioritization decision, not urgent.

5. **Update `setup_vikunja.py`** to account for the native Inbox — either skip creating a child Inbox under Everyday, or rename the child to something else (e.g., "Quick Tasks").

6. **Add Research and Habits projects** to `setup_vikunja.py` if they should be part of the standard project hierarchy going forward.
