---
work_package_id: WP03
title: Filters, Comments, and Error Handling
lane: "doing"
dependencies: [WP01]
requirement_refs:
- FR-012
- FR-013
- FR-014
- FR-015
- FR-016
- FR-017
- FR-019
- FR-020
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 007-vikunja-api-skill-WP01
base_commit: 5d97124cb3320d5f3662e83777019c28f7481c0a
created_at: '2026-03-30T23:24:36.620124+00:00'
subtasks: [T011, T012, T013, T014]
agent: "claude-opus"
shell_pid: "33222"
history:
- date: '2026-03-30T22:03:15Z'
  event: created
  actor: claude
---

# WP03: Filters, Comments, and Error Handling

## Implementation Command

```bash
spec-kitty implement WP03 --base WP01
```

## Objective

Add filter execution, comment operations, comprehensive error handling, and
usage examples to the SKILL.md. This covers FR-012 through FR-020 — the
query, annotation, and reliability features.

## Context

- **SKILL.md**: `scripts/openclaw/skills/vikunja-api/SKILL.md` (created in WP01)
- **API contract**: `kitty-specs/007-vikunja-api-skill/contracts/vikunja-api-contract.md`
- **Key design decision**: Today/Upcoming/Overdue are pseudo-projects (negative
  IDs), not saved filters. Access via `/projects/{id}/tasks`.
- **Key design decision**: Goals is a real project (id=11), not a pseudo-project.
- **Parallel**: This WP can be implemented in parallel with WP02.

## Subtask Guidance

### T011: Write Filter Execution Instructions

**Purpose**: Teach the agent how to execute built-in filters and ad-hoc queries.

**Steps**:
1. Add a "Filters and Queries" section to SKILL.md
2. Document pseudo-project access:
   ```bash
   # Today's tasks
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/projects/-2/tasks

   # Upcoming tasks
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/projects/-3/tasks

   # Overdue tasks
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/projects/-4/tasks
   ```

3. Document Goals project access (real project, not pseudo):
   ```bash
   # Active goals (incomplete tasks in Goals project)
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=done%20%3D%20false%20%26%26%20project_id%20%3D%2011&sort_by=due_date&order_by=asc"
   ```

4. Document ad-hoc filtering via `/tasks/all`:
   - Filter by project: `filter=project_id = 11`
   - Filter by done status: `filter=done = false`
   - Filter by due date: `filter=due_date < 2026-04-01T00:00:00Z`
   - Combine filters: `filter=done = false && project_id = 11`
   - Sort: `sort_by=due_date&order_by=asc`
   - Pagination: `page=1&per_page=50`

5. Document the response fields that matter for briefings (FR-014):
   title, due_date, priority, project_id, labels, done

**Validation**:
- [ ] All three pseudo-projects documented with correct negative IDs
- [ ] Goals project query uses real project ID (resolve by name)
- [ ] Ad-hoc filter syntax documented with examples
- [ ] Sort and pagination documented
- [ ] Response fields for briefings listed

### T012: Write Comment Operations Instructions

**Purpose**: Teach the agent how to add and read task comments.

**Steps**:
1. Add a "Comments" section to SKILL.md
2. Document add comment:
   ```bash
   curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d '{"comment": "[Felix] Agent observation: task updated based on inbox processing"}' \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID/comments
   ```
3. State the business rule: all agent comments MUST be prefixed with `[Felix]`
   to distinguish from human comments
4. Document read comments:
   ```bash
   curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/TASK_ID/comments
   ```
5. Note: comments include author info — agent comments will show the
   API token owner's user

**Validation**:
- [ ] PUT method for creating comments (Vikunja convention)
- [ ] [Felix] prefix required and documented
- [ ] Read comments endpoint documented

### T013: Write Comprehensive Error Handling Section

**Purpose**: Teach the agent how to handle every error category from FR-017
through FR-020.

**Steps**:
1. Add an "Error Handling" section to SKILL.md
2. Document each error category with the agent's expected behavior:

   **Network / connectivity errors**:
   - If curl returns a connection error or timeout, report that Vikunja is
     unreachable. Do not retry automatically. Suggest checking the service.
   - These are transient — retry may succeed later.

   **Authentication errors (HTTP 401)**:
   - Response: `{"message": "missing, malformed, expired or otherwise invalid token provided"}`
   - Report as a credential error. The API token may be expired or revoked.
   - Do not retry — this is a permanent error until the token is rotated.
   - Refer to vikunja-ops.md for token rotation procedure.

   **Not found errors (HTTP 404)**:
   - Project not found by name: report which name was searched and that it
     doesn't exist. Do not guess or substitute.
   - Label not found by name: same pattern.
   - Task not found by ID: report the ID and that it doesn't exist.

   **Validation errors (pre-flight)**:
   - Missing title on task creation: reject before making API call.
   - Missing identity label: reject before making API call.
   - Missing project: reject before making API call.
   - Malformed date: reject before making API call.
   - Instruct: validate inputs BEFORE making any curl call.

   **Permission errors (HTTP 403)**:
   - Report the error. The API token may have insufficient scope.

   **Server errors (HTTP 500)**:
   - Report the error. Suggest checking Vikunja logs on office2.
   - This is transient — retry may succeed.

3. State the constitution directive: **NEVER fail silently.** Every error
   must be reported to the caller with a clear description of what happened
   and what to do about it.

4. State: **NEVER invent data.** If a name doesn't resolve, a field is
   missing, or the input is ambiguous — halt and report. Do not substitute
   defaults or make assumptions.

**Validation**:
- [ ] All error categories from FR-017 documented
- [ ] Transient vs permanent errors distinguished
- [ ] Pre-flight validation instructions included
- [ ] "Never fail silently" directive stated
- [ ] "Never invent data" directive stated

### T014: Write Usage Examples Section

**Purpose**: Provide concrete examples of common agent workflows.

**Steps**:
1. Add a "Usage Examples" section at the end of SKILL.md
2. Include these scenarios:

   **"Create a goal declaration"**:
   1. Resolve Goals project ID by name
   2. Resolve metalcasework label ID by name
   3. Create task in Goals project with title, description, due date
   4. Add metalcasework label to the task
   5. Confirm creation to the caller

   **"What are my overdue tasks?"**:
   1. Check health
   2. Get tasks from pseudo-project -4 (Overdue)
   3. Present the list with title, due date, project, labels

   **"Add a note to task #42"**:
   1. Read task 42 to confirm it exists
   2. Add comment with [Felix] prefix
   3. Confirm comment was added

   **"Show active goals sorted by deadline"**:
   1. Query /tasks/all with filter=done = false && project_id = 11
   2. Sort by due_date ascending
   3. Present the list

**Validation**:
- [ ] At least 4 usage examples covering different operations
- [ ] Examples follow the patterns documented in earlier sections
- [ ] Examples demonstrate name resolution (not hardcoded IDs)

## Definition of Done

- [ ] Filter execution section covers pseudo-projects and ad-hoc queries
- [ ] Comment section documents add/read with [Felix] prefix
- [ ] Error handling covers all categories from FR-017 through FR-020
- [ ] "Never fail silently" and "never invent data" directives stated
- [ ] Usage examples cover 4+ common scenarios
- [ ] All curl commands use correct HTTP methods

## Risks

- **Filter syntax may vary**: The `/tasks/all?filter=` syntax was verified
  against the Swagger docs but should be tested end-to-end in WP04.
- **URL encoding**: Filter expressions with spaces and operators need URL
  encoding in curl. Document this clearly.

## Activity Log

- 2026-03-30T23:24:36Z – claude-opus – shell_pid=32349 – lane=doing – Assigned agent via workflow command
- 2026-03-30T23:26:15Z – claude-opus – shell_pid=32349 – lane=for_review – Ready for review: Filters, comments, error handling, usage examples
- 2026-03-30T23:27:56Z – claude-opus – shell_pid=33222 – lane=doing – Started review via workflow command
