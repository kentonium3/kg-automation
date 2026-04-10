# Tasks: Vikunja Date Timezone Bug Fix

**Feature**: 025-vikunja-date-timezone-bug
**Branch**: main → main
**Date**: 2026-04-10

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Backup current vikunja_api skill (pre-flight) | WP01 | | [D] |
| T002 | Update vikunja_api skill example to use ET offset | WP01 | | [D] |
| T003 | Update skill description to forbid `Z` suffix | WP01 | | [D] |
| T004 | Add dynamic offset resolution note to skill | WP01 | | [D] |
| T005 | Verify skill change: grep for remaining Z examples | WP01 | | [D] |
| T006 | Update habits AGENTS.md template from 00:00:00 to 23:59:59 | WP02 | | [D] |
| T007 | Add explanation block about end-of-day convention | WP02 | | [D] |
| T008 | Sync habits AGENTS.md to repo copy | WP02 | | [D] |
| T009 | Verify habits fix: trigger cron, query task, confirm end-of-day ET | WP02 | | [D] |
| T010 | Create test inbox note with evening "tomorrow" scenario | WP03 | |
| T011 | Trigger felix-admin-capture and observe tasker delegation | WP03 | |
| T012 | Query resulting Vikunja task, verify due_date matches expected ET | WP03 | |
| T013 | If tasker trace fails, extend fix with corrective instruction | WP03 | |
| T014 | Create docs/runbooks/vikunja-date-handling.md | WP03 | |
| T015 | Sanity check: mission 022 and 023 changes still intact | WP03 | |

---

## Work Packages

### WP01: Fix vikunja_api Skill (Bug B — canonical)

**Goal**: Update the vikunja_api skill so its canonical example uses the ET offset format instead of UTC `Z`. This addresses Bug B at the layer that all Vikunja-interacting agents reference.

**Priority**: High — this is the root cause of the tasker inconsistency.

**Dependencies**: None

**Prompt file**: [WP01-fix-vikunja-skill.md](tasks/WP01-fix-vikunja-skill.md)

**Subtasks**:
- [x] T001: Backup current vikunja_api skill (pre-flight)
- [x] T002: Update vikunja_api skill example to use ET offset
- [x] T003: Update skill description to forbid `Z` suffix
- [x] T004: Add dynamic offset resolution note to skill
- [x] T005: Verify skill change: grep for remaining Z examples

**Estimated prompt size**: ~350 lines

---

### WP02: Fix Habits Midnight Anchor (Bug A)

**Goal**: Change the habits agent's due_date convention from midnight ET (start of day) to end-of-day ET (23:59:59), so daily habit tasks don't appear overdue from the moment they're created.

**Priority**: High — fixes the visible habits symptom.

**Dependencies**: WP01 (not strictly required, but WP01 establishes the canonical format which habits references)

**Prompt file**: [WP02-fix-habits-midnight.md](tasks/WP02-fix-habits-midnight.md)

**Subtasks**:
- [x] T006: Update habits AGENTS.md template from 00:00:00 to 23:59:59
- [x] T007: Add explanation block about end-of-day convention
- [x] T008: Sync habits AGENTS.md to repo copy
- [x] T009: Verify habits fix: trigger cron, query task, confirm end-of-day ET

**Estimated prompt size**: ~300 lines

---

### WP03: Tasker Trace, Documentation, and Sanity

**Goal**: Complete the mission with tasker end-to-end verification, durable documentation, and a sanity check against prior mission drift.

**Priority**: High — the tasker verification is a required gate (FR-004) and documentation prevents regression (FR-005).

**Dependencies**: WP02 (tasker trace should run against the fully-fixed state)

**Prompt file**: [WP03-tasker-trace-docs.md](tasks/WP03-tasker-trace-docs.md)

**Subtasks**:
- [ ] T010: Create test inbox note with evening "tomorrow" scenario
- [ ] T011: Trigger felix-admin-capture and observe tasker delegation
- [ ] T012: Query resulting Vikunja task, verify due_date matches expected ET
- [ ] T013: If tasker trace fails, extend fix with corrective instruction
- [ ] T014: Create docs/runbooks/vikunja-date-handling.md
- [ ] T015: Sanity check: mission 022 and 023 changes still intact

**Estimated prompt size**: ~400 lines

---

## Dependency Graph

```
WP01 (skill fix)
    ↓
WP02 (habits fix + verification)
    ↓
WP03 (tasker trace + docs + sanity)
```

Strictly sequential. Each WP builds on the previous.

## Size Validation

| WP | Subtasks | Est. Lines | Status |
|---|---|---|---|
| WP01 | 5 | ~350 | ✓ Ideal range |
| WP02 | 4 | ~300 | ✓ Ideal range |
| WP03 | 6 | ~400 | ✓ Ideal range |

All WPs within ideal sizing. No ownership conflicts.
