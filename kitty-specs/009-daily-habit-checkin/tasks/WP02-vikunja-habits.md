---
work_package_id: WP02
title: Vikunja Habits Project and Initial Habits
lane: "for_review"
dependencies: [WP01]
requirement_refs:
- C-006
- FR-001
- FR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 009-daily-habit-checkin-WP01
base_commit: 9268f58f9c8dcd1d7996eb78e18d9fa4f5c760fd
created_at: '2026-04-01T03:14:40.863076+00:00'
subtasks: [T006, T007, T008, T009]
agent: claude-code
shell_pid: '92134'
history:
- date: '2026-04-01T01:46:04Z'
  event: created
  actor: claude
---

# WP02: Vikunja Habits Project and Initial Habits

## Implementation command

```bash
spec-kitty implement WP02 --base WP01
```

## Objective

Create the Habits project in Vikunja, populate it with Kent's 7 recurring
commitments as tasks with identity labels and frequency descriptions, and
validate that the comment-based completion storage approach works.

## Context

- **Vikunja API**: vikunja_api skill on office2, token at `/data/services/openclaw/secrets/vikunja-api`
- **Vikunja URL**: `https://office2.tail0f5f56.ts.net/api/v1`
- **Data model**: `kitty-specs/009-daily-habit-checkin/data-model.md`
- **Existing projects**: Inbox (id=1), Goals (id=11), Research (id=12) — Habits does not exist yet
- **Identity labels**: personal (id=1), intentional (id=2), metalcasework (id=3)

## Subtask guidance

### T006: Create Habits project in Vikunja

**Purpose**: Establish a dedicated project for habit tracking.

**Steps**:
1. Check if Habits project already exists:
   ```bash
   ssh office2-claude 'curl -s \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/projects' \
     | python3 -c "import json,sys; [print(f'id={p[\"id\"]} title={p[\"title\"]}') for p in json.load(sys.stdin) if p['title']=='Habits']"
   ```
2. If not found, create it:
   ```bash
   ssh office2-claude 'curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"title\": \"Habits\"}" \
     https://office2.tail0f5f56.ts.net/api/v1/projects'
   ```
3. Note the project ID for reference

**Validation**:
- [ ] Habits project exists in Vikunja
- [ ] Accessible via API

### T007: Create 7 habit tasks with labels and frequency descriptions

**Purpose**: Populate the Habits project with Kent's recurring commitments.

**Steps**:
1. For each habit, create a task in the Habits project. Use the project ID
   from T006. Example for the first habit:
   ```bash
   ssh office2-claude 'curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"title\": \"Wake at 5:00 AM\", \"description\": \"Mon-Sat\"}" \
     https://office2.tail0f5f56.ts.net/api/v1/projects/<PROJECT_ID>/tasks'
   ```
2. After creating each task, add the personal label (id=1):
   ```bash
   ssh office2-claude 'curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"label_id\": 1}" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/<TASK_ID>/labels'
   ```

**Habit list** (all personal label):

| # | Title | Description (frequency) |
|---|-------|------------------------|
| 1 | Wake at 5:00 AM | Mon-Sat |
| 2 | Meditate 45 min | Daily |
| 3 | Morning shoulder PT | Daily |
| 4 | Functional strength training 45 min | Mon/Wed/Fri |
| 5 | 10K steps (monthly average) | Daily |
| 6 | Read 30 min minimum | Daily (evening) |
| 7 | Evening shoulder PT | Daily |

**Validation**:
- [ ] All 7 tasks created in Habits project
- [ ] Each task has the personal label
- [ ] Each task has the correct frequency in description

### T008: Verify habit tasks via API query

**Purpose**: Confirm all habits are correctly set up.

**Steps**:
1. Query all tasks in the Habits project:
   ```bash
   ssh office2-claude 'curl -s \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/projects/<PROJECT_ID>/tasks' \
     | python3 -c "import json,sys; [print(f'id={t[\"id\"]} title={t[\"title\"]} desc={t[\"description\"]}') for t in json.load(sys.stdin)]"
   ```
2. Verify 7 tasks, each with correct title, description, and label

### T009: Test comment CRUD on a habit task

**Purpose**: Validate the completion storage approach before WP03 relies on it.

**Steps**:
1. Create a test comment on one habit task:
   ```bash
   ssh office2-claude 'curl -s -X PUT \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"comment\": \"[Felix] 2026-03-31 | complete | test entry\"}" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/<TASK_ID>/comments'
   ```
2. Search for the comment by date:
   ```bash
   ssh office2-claude 'curl -s \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/<TASK_ID>/comments?s=2026-03-31"'
   ```
3. Update the comment (test idempotency):
   ```bash
   ssh office2-claude 'curl -s -X POST \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     -H "Content-Type: application/json" \
     -d "{\"comment\": \"[Felix] 2026-03-31 | rescheduled | updated test\"}" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/<TASK_ID>/comments/<COMMENT_ID>'
   ```
4. Delete the test comment to clean up:
   ```bash
   ssh office2-claude 'curl -s -X DELETE \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     https://office2.tail0f5f56.ts.net/api/v1/tasks/<TASK_ID>/comments/<COMMENT_ID>'
   ```

**Validation**:
- [ ] Comment created successfully
- [ ] Comment searchable by date string
- [ ] Comment updateable (idempotency works)
- [ ] Comment deleteable (cleanup works)

## Definition of done

- [ ] Habits project exists in Vikunja
- [ ] 7 habit tasks created with correct labels and frequencies
- [ ] Comment CRUD validated on at least one habit task
- [ ] Test data cleaned up

## Risks

- **Comment search may not support ILIKE on all Vikunja versions**: If
  search returns empty, fall back to fetching all comments and filtering
  client-side. Document the finding.

## Activity Log

- 2026-04-01T03:14:41Z – claude-code – shell_pid=92134 – lane=doing – Assigned agent via workflow command
- 2026-04-01T03:19:32Z – claude-code – shell_pid=92134 – lane=for_review – Ready for review: Habits project (id=13), 7 tasks with personal labels, comment CRUD validated
