# Data Model: Vikunja API Skill

This skill does not introduce new data models. It operates on existing Vikunja
entities via the REST API. The key entities and their relationships are
documented here for skill implementation reference.

## Entities

### Task

The primary entity. Created in a project, can have labels, comments, and dates.

| Field | Type | Required for Create | Mutable | Notes |
| --- | --- | --- | --- | --- |
| id | integer | No (assigned) | No | Unique task ID |
| title | string | Yes | Yes | Task text |
| description | string | No | Yes | Markdown description |
| due_date | string (ISO 8601) | No | Yes | When the task is due |
| done | boolean | No | Yes | Completion status |
| priority | integer | No | Yes | Numeric priority (user-defined) |
| project_id | integer | Via URL | No | Set by the project in the create URL |
| labels | array | No | Read-only | Must use separate label endpoint |

### Project

Container for tasks. Includes user-created and pseudo-projects.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Negative IDs are pseudo-projects |
| title | string | Project name |
| is_archived | boolean | Whether project is archived |

### Label

Identity tags applied to tasks.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Unique label ID |
| title | string | Label name (personal, intentional, metalcasework) |
| hex_color | string | Display color |

### Comment

Text annotation on a task.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Unique comment ID |
| comment | string | Comment text (agent comments prefixed with "[Felix]") |
| author | object | User who created the comment |

## Relationships

```
Project 1:N Task
Task N:M Label (via /tasks/{id}/labels endpoint)
Task 1:N Comment (via /tasks/{id}/comments endpoint)
```

## State Transitions

### Task Lifecycle

```
Created (done=false) → Updated (fields changed) → Completed (done=true) → Deleted
```

The skill supports all transitions. "Delete" in Vikunja v0.24.6 is a hard
delete (no archive/soft-delete endpoint exists). The spec's FR-005 references
soft delete, but the API only supports `DELETE /tasks/{id}` which is permanent.
The skill should warn the agent before deletion.
