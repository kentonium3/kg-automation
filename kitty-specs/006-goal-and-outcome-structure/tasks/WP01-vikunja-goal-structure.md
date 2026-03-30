---
work_package_id: WP01
title: Vikunja Goal Structure
lane: "for_review"
dependencies: []
requirement_refs:
- FR-003
- FR-004
- FR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 9d25354e02d25cd6062b8f217fd731db5dc281dc
created_at: '2026-03-30T14:40:51.296983+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1 - Core Implementation
assignee: ''
agent: claude
shell_pid: '52606'
review_status: ''
reviewed_by: ''
history:
- timestamp: '2026-03-30T14:32:29Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP01 – Vikunja Goal Structure

## Review Feedback

*[This section is empty initially. Reviewers will populate it if the work is returned from review.]*

---

## Objectives & Success Criteria

Create the Vikunja goal infrastructure: a `metalcasework` label, a top-level
`Goals` project, at least one seed goal declaration task with structured fields,
and a "Goals" saved filter showing active goals sorted by target date.

**Success criteria:**
- `metalcasework` label exists in Vikunja (#ff9800 orange)
- Top-level `Goals` project exists
- At least one goal declaration task exists with: outcome statement + evidence
  in description, target date as due date, identity label applied
- "Goals" saved filter shows active goals sorted by target date (nearest first)
- All operations are idempotent (script can be re-run safely)
- Setup verified via API queries

## Context & Constraints

**Reference documents:**
- `kitty-specs/006-goal-and-outcome-structure/spec.md` — FR-003, FR-004, FR-005
- `kitty-specs/006-goal-and-outcome-structure/plan.md` — Phase A details
- `kitty-specs/006-goal-and-outcome-structure/research.md` — R-01 through R-07
- `kitty-specs/006-goal-and-outcome-structure/data-model.md` — entity definitions

**Pattern reference:**
- `scripts/vikunja/setup_vikunja.py` — the F001 setup script. Study this file
  carefully before writing any code. Follow its exact patterns for auth, API
  calls, idempotency checks, and error handling.

**Vikunja API details:**
- Base URL: `http://100.92.197.90:3456/api/v1`
- Auth: `POST /login` with `{"username": "...", "password": "..."}` → JWT token
- Headers: `Authorization: Bearer {token}`, `Content-Type: application/json`
- Create project: `PUT /projects` with `{"title": "Goals"}`
- Create task: `PUT /projects/{id}/tasks` with title, description, due_date, labels
- Create label: `PUT /labels` with `{"title": "metalcasework", "hex_color": "#ff9800"}`
- Create filter: `PUT /filters` with filter expression
- List projects: `GET /projects` (for idempotency check)
- List labels: `GET /labels` (for idempotency check)

**Existing labels (from F001):**
- `personal` — #2196f3 (blue)
- `intentional` — #4caf50 (green)

**Constraints:**
- No credentials stored in code — interactive auth only
- Script must be idempotent (check before create)
- `02-Growth/_private/` never accessed
- Run via `ssh office2-claude` or locally with Tailscale access

## Subtasks & Detailed Guidance

### Subtask T001 – Create setup_goals.py Script

- **Purpose**: Establish the script that will configure Vikunja with goal
  infrastructure. Follows the same pattern as `setup_vikunja.py`.
- **Steps**:
  1. Read `scripts/vikunja/setup_vikunja.py` thoroughly — understand the auth
     flow, API helper functions, idempotency pattern, and error handling
  2. Create `scripts/vikunja/setup_goals.py` with:
     - Same shebang, imports, and argument parsing pattern
     - `BASE_URL` constant: `http://100.92.197.90:3456/api/v1`
     - `authenticate()` function (same as setup_vikunja.py)
     - `get_projects()`, `get_labels()` helper functions
     - `create_project_if_not_exists()`, `create_label_if_not_exists()` helpers
     - `create_task()`, `create_filter()` functions
     - `main()` that orchestrates: auth → label → project → task → filter → verify
  3. Include `--dry-run` flag that prints what would be created without making
     API calls
- **Files**: `scripts/vikunja/setup_goals.py` (new, ~150-200 lines)
- **Parallel?**: No — this is the foundation for all other subtasks

### Subtask T002 – Create metalcasework Label

- **Purpose**: Complete the identity label set. F001 created `personal` and
  `intentional`; the spec requires `metalcasework` as the third identity context.
- **Steps**:
  1. In `setup_goals.py`, add label creation logic:
     - `GET /labels` to check if `metalcasework` already exists
     - If not: `PUT /labels` with `{"title": "metalcasework", "hex_color": "#ff9800"}`
     - Store the label ID for use in task creation
  2. Also retrieve IDs for existing `personal` and `intentional` labels
     (needed for seed goal tasks)
- **Files**: `scripts/vikunja/setup_goals.py`
- **Parallel?**: Yes — can be created alongside T003 (project creation)
- **Notes**: Color #ff9800 (orange) is distinct from personal (blue) and
  intentional (green)

### Subtask T003 – Create Goals Project

- **Purpose**: Create the dedicated top-level project in Vikunja that holds
  goal declarations as tasks, distinct from regular task projects.
- **Steps**:
  1. `GET /projects` to check if a project titled "Goals" already exists
     at the top level (parent_project_id = 0)
  2. If not: `PUT /projects` with `{"title": "Goals"}`
  3. Store the project ID for use in task and filter creation
- **Files**: `scripts/vikunja/setup_goals.py`
- **Parallel?**: Yes — can be created alongside T002 (label creation)
- **Notes**: The Goals project must be top-level, not a child of any existing
  project. This maintains the distinction between goals (outcome declarations)
  and tasks (actions).

### Subtask T004 – Create Seed Goal Declaration Task(s)

- **Purpose**: Seed at least one real goal declaration in the canonical format
  so the system is immediately useful after setup.
- **Steps**:
  1. **STOP AND REQUEST INPUT**: Before creating seed tasks, confirm with Kent
     the exact goal declaration text. Candidates from inbox notes:
     - Intentional consulting: "$5,000/month income" — needs specific target
       date and evidence criteria
     - 5K race: Against the Tide, Brewster, June 27, 2026 — needs outcome
       statement and evidence criteria
  2. For each seed goal, create a task via `PUT /projects/{goals_id}/tasks`:
     ```json
     {
       "title": "Short summary (e.g., Intentional: $5K/month consulting income)",
       "description": "On [date], I have [outcome] as evidenced by [proof].\n\n**Evidence criteria:** [detailed evidence description]",
       "due_date": "2026-06-30T00:00:00Z",
       "labels": [{"id": <label_id>}]
     }
     ```
  3. Verify each task was created with correct fields
- **Files**: `scripts/vikunja/setup_goals.py`
- **Parallel?**: No — depends on T003 (needs project ID) and T002 (needs label IDs)
- **Notes**: The description must contain the full canonical declaration format.
  The title is a short summary for list views. Do not invent dates or evidence
  criteria — these must come from Kent.

### Subtask T005 – Create Goals Saved Filter

- **Purpose**: Provide a single view showing all active goal declarations
  sorted by target date, matching the existing Today/Upcoming/Overdue filter
  pattern from F001.
- **Steps**:
  1. Create filter via `PUT /filters`:
     ```json
     {
       "title": "Goals",
       "filters": {
         "filter_by": ["project_id"],
         "filter_value": ["<goals_project_id>"],
         "filter_comparator": ["equals"],
         "filter_concat": "and",
         "order_by": ["due_date"],
         "order": ["asc"]
       }
     }
     ```
  2. Note: The exact filter expression syntax may differ from F001's saved
     filters. Study the Vikunja 0.24.x API docs or test with a simple filter
     first.
  3. If the filter API doesn't support project-based filtering directly,
     fall back to documenting a manual saved filter setup in the ops runbook.
- **Files**: `scripts/vikunja/setup_goals.py`
- **Parallel?**: No — depends on T003 (needs project ID)
- **Notes**: The filter must show only incomplete (active) goals. Vikunja's
  default behavior excludes done tasks from filters, but verify this.

### Subtask T006 – Verify Vikunja Setup

- **Purpose**: Programmatically verify that all Vikunja goal infrastructure
  was created correctly.
- **Steps**:
  1. Add a `verify()` function to `setup_goals.py` that checks:
     - `metalcasework` label exists with correct color
     - `Goals` project exists at top level
     - At least one task exists in the Goals project
     - Each task has: non-empty description, due_date set, at least one label
     - "Goals" filter exists (or document manual setup if API doesn't support)
  2. Print verification results to stdout
  3. Exit with non-zero code if any check fails
- **Files**: `scripts/vikunja/setup_goals.py`
- **Parallel?**: No — runs after all creation steps
- **Notes**: This verification serves as the test strategy for WP01. The
  script itself is the test — it creates and then verifies.

## Risks & Mitigations

- **Filter expression syntax**: Vikunja 0.24.x filter API may use different
  syntax than expected. Mitigation: test with a simple filter first; fall back
  to documenting manual filter creation if API is limited.
- **Label ID retrieval**: Need existing label IDs (personal, intentional) for
  seed tasks. Mitigation: `GET /labels` returns all labels with IDs.
- **Task label assignment**: Verify the correct API shape for assigning labels
  to tasks (may be `labels` array in task creation or separate endpoint).

## Review Guidance

- Verify script follows `setup_vikunja.py` patterns exactly (auth, idempotency)
- Verify seed goal declaration uses the canonical format
- Verify filter shows goals sorted by due date ascending
- Verify script can be re-run without creating duplicates
- Check that no credentials are hardcoded

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Implementation command: `spec-kitty implement WP01`
- No dependencies — this is the starting work package

## Activity Log

- 2026-03-30T14:32:29Z – system – lane=planned – Prompt created.
- 2026-03-30T14:40:51Z – claude – shell_pid=52606 – lane=doing – Assigned agent via workflow command
- 2026-03-30T14:52:04Z – claude – shell_pid=52606 – lane=for_review – Ready for review: setup_goals.py creates Goals project, metalcasework label, 3 seed goals, and Goals filter. All verification checks pass.
