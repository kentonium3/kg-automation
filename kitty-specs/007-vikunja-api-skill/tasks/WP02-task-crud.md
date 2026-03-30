---
work_package_id: WP02
title: Task CRUD Operations
lane: "doing"
dependencies: [WP01]
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-018
- FR-020
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 007-vikunja-api-skill-WP01
base_commit: 5d97124cb3320d5f3662e83777019c28f7481c0a
created_at: '2026-03-30T23:23:23.023871+00:00'
subtasks: [T005, T006, T007, T008, T009, T010]
shell_pid: "31927"
history:
- date: '2026-03-30T22:03:15Z'
  event: created
  actor: claude
---

# WP02: Task CRUD Operations

## Implementation Command

```bash
spec-kitty implement WP02 --base WP01
```

## Objective

Add task create, read, update, complete, and delete instructions to the
SKILL.md. This covers FR-001 through FR-007 — the core task operations that
every downstream feature depends on.

## Context

- **SKILL.md**: `scripts/openclaw/skills/vikunja-api/SKILL.md` (created in WP01)
- **API contract**: `kitty-specs/007-vikunja-api-skill/contracts/vikunja-api-contract.md`
- **Key design decision**: Labels are assigned via a separate endpoint after task
  creation (Task.labels is read-only). Task creation is a two-step process.
- **Key design decision**: Delete is permanent in Vikunja v0.24.6 (no soft-delete).

## Subtask Guidance

### T005: Write Task Creation Instructions

**Purpose**: Teach the agent how to create a task in a project with all
required fields and assign an identity label.

**Steps**:
1. Add a "Create Task" section to SKILL.md
2. Document the two-step process:

   **Step 1 — Create the task**:
   ```bash
   curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00Z", "priority": 1}' \
     https://office2.tail0f5f56.ts.net/api/v1/projects/PROJECT_ID/tasks
   ```
   - Save the returned `id` for label assignment
   - Note: `project_id` is set by the URL path, not the body

   **Step 2 — Add identity label**:
   ```bash
   curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d '{"label_id": LABEL_ID}' \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID/labels
   ```

3. State the business rule: **every agent-created task MUST have an identity label**.
   If the caller doesn't specify one, the agent should ask which label to use.

4. Document required vs optional fields:
   - Required: title, project (by name → resolve to ID), identity label
   - Optional: description, due_date (ISO 8601), priority (integer)

**Validation**:
- [ ] Two-step process clearly documented
- [ ] Project ID resolved by name (not hardcoded)
- [ ] Label ID resolved by name (not hardcoded)
- [ ] Identity label requirement stated as a business rule
- [ ] curl commands are correct with proper HTTP methods (PUT for create)

### T006: Write Task Read Instructions

**Purpose**: Teach the agent how to read a task by ID.

**Steps**:
1. Add a "Read Task" section
2. Document:
   ```bash
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID
   ```
3. List the key response fields: id, title, description, due_date, done,
   priority, project_id, labels, created, updated
4. Note: labels array is populated in the response (read-only but visible)

**Validation**:
- [ ] curl command is correct
- [ ] Key response fields documented

### T007: Write Task Update Instructions

**Purpose**: Teach the agent how to update task fields.

**Steps**:
1. Add an "Update Task" section
2. Document partial update (only send fields to change):
   ```bash
   curl -s -X POST \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d '{"description": "Updated description"}' \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID
   ```
3. List updatable fields: title, description, due_date, priority, done,
   hex_color, percent_done
4. Note: use POST, not PUT (Vikunja convention for updates)

**Validation**:
- [ ] POST method (not PUT) for updates
- [ ] Partial update documented (only changed fields in body)
- [ ] Updatable fields listed

### T008: Write Task Completion Instructions

**Purpose**: Teach the agent how to mark a task as complete.

**Steps**:
1. Add a "Complete Task" section
2. Document:
   ```bash
   curl -s -X POST \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d '{"done": true}' \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID
   ```
3. Note: this is a special case of update — sets `done: true`
4. Mention: `done_at` will be auto-populated by Vikunja

**Validation**:
- [ ] Simple done=true update documented
- [ ] Noted as a convenience alias for the update endpoint

### T009: Write Task Deletion Instructions

**Purpose**: Teach the agent how to delete a task, with appropriate warnings.

**Steps**:
1. Add a "Delete Task" section
2. Document:
   ```bash
   curl -s -X DELETE \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID
   ```
3. Add a prominent warning:
   > **⚠️ DELETE IS PERMANENT.** Vikunja v0.24.6 has no soft-delete or archive.
   > Only use for test cleanup or when explicitly requested by Kent.
   > Prefer marking tasks as complete (done=true) rather than deleting.

**Validation**:
- [ ] DELETE method documented
- [ ] Permanent deletion warning is prominent
- [ ] Agent instructed to prefer completion over deletion

### T010: Write Idempotent Creation Instructions

**Purpose**: Teach the agent to check for existing tasks before creating
duplicates (FR-007).

**Steps**:
1. Add a "Duplicate Check" subsection under Create Task
2. Instruct the agent to search for an existing task with the same title
   in the same project before creating:
   ```bash
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/projects/PROJECT_ID/tasks?s=SEARCH_TERM"
   ```
3. If a task with matching title is found, return it instead of creating new
4. Note: the `s` parameter is a search/filter on task titles
5. Instruct: exact title match is required — partial matches should be
   surfaced to the caller for confirmation

**Validation**:
- [ ] Search-before-create pattern documented
- [ ] Uses project-scoped task search
- [ ] Exact match required for idempotent behavior

## Definition of Done

- [ ] SKILL.md contains complete task CRUD instructions
- [ ] Create task uses two-step process (create + label)
- [ ] Identity label requirement enforced as business rule
- [ ] Delete includes permanent-deletion warning
- [ ] Idempotent creation pattern documented
- [ ] All curl commands use correct HTTP methods
- [ ] No credentials in the file — only `$(cat ...)` pattern

## Risks

- **Wrong HTTP methods**: Vikunja uses PUT for creates, POST for updates,
  which is non-standard REST. Double-check each curl command.
- **Label assignment race**: If the label assignment fails after task creation,
  the agent should report the task was created without a label rather than
  failing silently.
