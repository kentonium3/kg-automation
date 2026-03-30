# Data Model: Goal and Outcome Structure

**Feature**: 006-goal-and-outcome-structure
**Date**: 2026-03-30

## Entities

### Goal Declaration

A declared outcome in the canonical format. Stored in two systems with
different roles.

**Attributes**:

| Attribute | Description | Vikunja Field | Goals-MOC Representation |
| --- | --- | --- | --- |
| outcome_statement | Present-tense outcome ("I have...") | Task description (first paragraph) | Full declaration text |
| target_date | Specific calendar date | Task due_date (ISO 8601) | Inline in declaration ("On [date]") |
| evidence_criteria | Observable proof | Task description (second paragraph) | Inline in declaration ("as evidenced by") |
| identity_context | personal, intentional, or metalcasework | Task label | Section heading in Goals-MOC.md |
| status | active, achieved, or retired | Task done flag + description note | Active section vs Archive section |
| summary | Short scannable title | Task title | Not used (full declaration is shown) |

**Lifecycle**:
```
declared → active → achieved (target met, evidence confirmed)
                  → retired (abandoned or superseded)
```

**Source of truth rules**:
- Vikunja is authoritative for **state** (active/achieved/retired, target date)
- Goals-MOC.md is authoritative for **narrative context** (full declaration text)
- Both must be updated together (manual two-step in F006; automated in later feature)

### Goals Project (Vikunja)

A top-level Vikunja project that holds goal declaration tasks.

| Attribute | Value |
| --- | --- |
| title | Goals |
| parent_project_id | 0 (top-level) |
| purpose | Hold goal declaration tasks distinct from action tasks |

### Identity Labels (Vikunja)

| Label | Color | Created By |
| --- | --- | --- |
| personal | #2196f3 (blue) | F001 |
| intentional | #4caf50 (green) | F001 |
| metalcasework | #ff9800 (orange) | F006 (new) |

### Goals Saved Filter (Vikunja)

| Attribute | Value |
| --- | --- |
| title | Goals |
| expression | `project = <goals_project_id> && done = false` |
| sort | due_date ascending |
| purpose | Show all active goal declarations sorted by target date |

## Relationships

```
Goals Project (1) ──contains──▶ Goal Declaration Tasks (many)
Goal Declaration Task (1) ──has──▶ Identity Label (1)
Goals-MOC.md (1) ──mirrors──▶ Goal Declaration Tasks (many)
```

## Validation Rules

1. Every goal declaration task MUST have exactly one identity label
2. Every goal declaration task MUST have a due date (target date)
3. Every goal declaration task description MUST contain the full canonical
   declaration format
4. Goals-MOC.md MUST contain all active goals that exist in Vikunja
5. No goal declaration may reference `02-Growth/_private/` content
