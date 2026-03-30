# Research: Goal and Outcome Structure

**Feature**: 006-goal-and-outcome-structure
**Date**: 2026-03-30
**Status**: Complete

## R-01: Vikunja API Pattern for Goals Project

**Decision**: Use the same Python + Vikunja REST API pattern established in
`scripts/vikunja/setup_vikunja.py` (F001).

**Rationale**: The F001 script already handles authentication (JWT via
`POST /login`), idempotent project creation (`PUT /projects` with title
dedup), label creation (`PUT /labels`), and saved filter creation
(`PUT /filters`). Extending this script (or creating a companion) for goals
is the lowest-risk approach.

**Alternatives considered**:
- Manual UI configuration: rejected because not reproducible or verifiable
- Direct SQLite manipulation: rejected because it bypasses Vikunja's API
  contract and could break on upgrades

**Key API details**:
- Base URL: `http://100.92.197.90:3456/api/v1`
- Auth: `POST /login` → JWT token → `Authorization: Bearer {token}`
- Create project: `PUT /projects` with `{"title": "...", "parent_project_id": <id>}`
- Create task: `PUT /projects/{id}/tasks` with `{"title": "...", "description": "...", "due_date": "...", "labels": [...]}`
- Create filter: `PUT /filters` with filter expression syntax
- Idempotency: check by title before creating (established F001 pattern)

## R-02: Existing Vikunja Structure (F001 Baseline)

**Finding**: F001 created 7 top-level projects, 3 child projects, 2 labels
(personal, intentional), and 3 saved filters (Today, Upcoming, Overdue).

**Implication for F006**: The Goals project must be a new top-level project,
not a child of an existing project. This maintains the distinction between
goals (outcome declarations) and tasks (actions). A new label
`metalcasework` is needed to complete the identity label set (personal and
intentional already exist).

## R-03: Current Goals-MOC.md State

**Finding**: `01-Constitution/Goals-MOC.md` on office2 contains legacy
free-text goals across 8 domains (Personal Growth, Health, Intentional LLC,
Acquisition, Metal Casework, Finance, AI/Tech, Creative). These are
informal checkbox items, not formatted declarations. Last reviewed
2026-03-21.

**Decision**: F006 replaces the legacy content with properly formatted goal
declarations. The func-spec states Goals-MOC.md was "reset to clean slate
(2026-03-29)" with legacy content backed up. The new structure will use
the canonical "On [date], I have [outcome] as evidenced by [proof]" format
organized by identity context.

**Seed goal candidates** (from inbox notes):
- Intentional consulting: $5,000/month income (date TBD — Kent must provide)
- 5K race: Against the Tide, Brewster, June 27, 2026

## R-04: Goals-MOC Structure Design

**Decision**: Organize Goals-MOC.md by identity context (matching Vikunja
labels) with an archive section at the bottom.

**Structure**:
```
# Goals — Active Declarations

## Format
[canonical format reference]

## Personal
[declarations with personal identity context]

## Intentional
[declarations with intentional identity context]

## Metal Casework
[declarations with metalcasework identity context]

## Archive
### Achieved
### Retired
```

**Rationale**: Organizing by identity context mirrors the Vikunja label
taxonomy and makes it natural to scan goals by life domain. The archive
section preserves history without cluttering the active view.

## R-05: Vikunja Task Structure for Goal Declarations

**Decision**: Each goal declaration becomes a Vikunja task in the Goals
project with:
- **Title**: Short summary (e.g., "Intentional: $5K/month consulting income")
- **Description**: Full declaration in canonical format, plus evidence
  criteria as a separate paragraph
- **Due date**: Target date from the declaration
- **Label**: Identity label (personal, intentional, or metalcasework)

**Rationale**: The title provides scannable context in list views. The
description carries the full declaration for agent consumption. The due
date enables the saved filter to sort by target date. The label enables
filtering by identity context.

## R-06: Saved Filter Design

**Decision**: Create a saved filter named "Goals" with expression:
`project = <goals_project_id> && done = false` sorted by due date ascending.

**Rationale**: This shows all active (incomplete) goal declarations sorted
by nearest target date. The filter follows the same expression syntax as
F001's Today/Upcoming/Overdue filters.

## R-07: Missing Label — metalcasework

**Decision**: Create the `metalcasework` label during F006 setup. F001
created `personal` and `intentional` but the spec requires all three
identity labels.

**Color**: #ff9800 (orange) — distinct from personal (#2196f3 blue) and
intentional (#4caf50 green).
