# Feature Specification: Vikunja API Skill

**Feature Branch**: `007-vikunja-api-skill`
**Created**: 2026-03-30
**Status**: Draft
**Input**: F007 func-spec — OpenClaw skill wrapping Vikunja REST API

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Create and Manage Tasks via OpenClaw (Priority: P1)

An OpenClaw agent needs to create a task in Vikunja with a title, description,
due date, priority, and identity label, then later read it back, update its
fields, and mark it complete. This is the core operation that every subsequent
feature (inbox processing, habit tracking, briefings, escalation) depends on.

**Why this priority**: Without task CRUD, no downstream feature can interact
with the task store. This is the foundation skill.

**Independent Test**: Use the skill from an OpenClaw agent context to create
a task in the Goals project with the `metalcasework` label, read it back by ID,
update its description, mark it complete, then delete it. Verify each step
returns the expected result.

**Acceptance Scenarios**:

1. **Given** the skill is installed in OpenClaw, **When** an agent calls
   create-task with title, project name "Goals", label "metalcasework", and
   a due date, **Then** a task is created in Vikunja and the skill returns
   the task ID and confirmation.
2. **Given** an existing task, **When** an agent calls read-task with its ID,
   **Then** the skill returns all task fields including title, description,
   due date, priority, labels, and done status.
3. **Given** an existing task, **When** an agent calls update-task to change
   the description, **Then** the task is updated in Vikunja and the skill
   confirms the change.
4. **Given** an existing task, **When** an agent calls complete-task,
   **Then** the task's done status is set to true in Vikunja.
5. **Given** a task creation request missing the identity label, **When** the
   agent calls create-task, **Then** the skill rejects the request with a
   validation error before making any API call.

---

### User Story 2 — Resolve Projects and Labels by Name (Priority: P1)

An agent needs to find the Goals project and identity labels by name rather
than by numeric ID, so that agent code remains readable and resilient to
Vikunja re-provisioning.

**Why this priority**: Hardcoding IDs makes agents fragile. Name resolution
is required before any task operation can work reliably.

**Independent Test**: Call list-projects and get-project-by-name "Goals".
Call list-labels and get-label-by-name for each identity label (personal,
intentional, metalcasework). Verify all return correct IDs.

**Acceptance Scenarios**:

1. **Given** the Vikunja instance has a Goals project, **When** an agent
   calls get-project-by-name "Goals", **Then** the skill returns the
   project's ID and metadata.
2. **Given** the Vikunja instance has identity labels, **When** an agent
   calls get-label-by-name "metalcasework", **Then** the skill returns the
   label's ID.
3. **Given** a non-existent project name, **When** an agent calls
   get-project-by-name "Nonexistent", **Then** the skill returns a specific
   not-found error.

---

### User Story 3 — Execute Saved Filters and Ad-Hoc Queries (Priority: P1)

An agent needs to execute Vikunja's saved filters (Today, Upcoming, Overdue,
Goals) to get task lists for briefings and escalation, and run ad-hoc queries
to find tasks by project, label, or due date range.

**Why this priority**: The briefing and escalation features depend on
filter execution to summarize task state.

**Independent Test**: Execute the Goals saved filter and verify it returns
active goal declarations sorted by target date. Execute an ad-hoc query for
tasks in a specific project with a specific label.

**Acceptance Scenarios**:

1. **Given** saved filters exist in Vikunja, **When** an agent calls
   execute-saved-filter "Goals", **Then** the skill returns active
   (incomplete) goal declarations sorted by target date.
2. **Given** tasks exist in various projects, **When** an agent calls
   filter-tasks with a project name and label, **Then** the skill returns
   only matching tasks with full metadata (title, due date, priority,
   project, labels, done status).

---

### User Story 4 — Add and Read Task Comments (Priority: P2)

An agent needs to annotate tasks with comments for escalation history and
status updates. Agent comments must be distinguishable from human comments.

**Why this priority**: Comment operations are needed by escalation and
briefing features but are not blocking for basic task operations.

**Independent Test**: Add a comment to an existing task with the agent
identifier prefix. Read comments back and verify the agent comment appears
with the prefix.

**Acceptance Scenarios**:

1. **Given** an existing task, **When** an agent calls add-comment with
   text, **Then** a comment is added with the "[Felix]" agent prefix.
2. **Given** a task with comments, **When** an agent calls read-comments,
   **Then** all comments are returned including agent and human comments.

---

### User Story 5 — Deploy Skill to OpenClaw on office2 (Priority: P1)

The skill must be installed into OpenClaw's skill system on office2 and
verified as callable by agents. This is the first (or second) live skill
deployment and serves as process discovery for the deployment workflow.

**Why this priority**: A skill that exists only in the repo is not usable.
Deployment is a success criterion, not a follow-up task.

**Independent Test**: SSH to office2 and verify the skill appears in
`openclaw skills list`. Invoke the skill from an OpenClaw agent context
and verify it can reach Vikunja and return data.

**Acceptance Scenarios**:

1. **Given** the skill code is written, **When** it is installed into
   OpenClaw on office2, **Then** `openclaw skills list` shows the
   vikunja-api skill.
2. **Given** the skill is installed, **When** an agent invokes it,
   **Then** it authenticates with the stored API token and returns data
   from Vikunja.

---

## Functional Requirements

| ID | Requirement | Status |
| --- | --- | --- |
| FR-001 | Create a task in a specified project with title, description, due date, priority, and identity label | Proposed |
| FR-002 | Read a task by ID, returning all fields | Proposed |
| FR-003 | Update a task's fields (title, description, due date, priority, done status, labels) | Proposed |
| FR-004 | Mark a task complete (set done status) | Proposed |
| FR-005 | Delete a task (soft delete/archive, not hard delete) | Proposed |
| FR-006 | Task creation must require an identity label (personal, intentional, or metalcasework) | Proposed |
| FR-007 | Task creation must be idempotent — surface existing task with same title in same project rather than creating a duplicate | Proposed |
| FR-008 | List all projects available to the agent | Proposed |
| FR-009 | Get a project by name, returning its ID and metadata | Proposed |
| FR-010 | List all labels | Proposed |
| FR-011 | Get a label by name, returning its ID | Proposed |
| FR-012 | Execute saved filters by name (Today, Upcoming, Overdue, Goals) and return resulting task list | Proposed |
| FR-013 | Execute ad-hoc filter queries (by project, label, due date range) | Proposed |
| FR-014 | Filter results must include title, due date, priority, project, labels, and done status | Proposed |
| FR-015 | Add a comment to a task with agent identifier prefix "[Felix]" | Proposed |
| FR-016 | Read all comments on a task | Proposed |
| FR-017 | Handle all error categories explicitly: network timeout, auth failure, not-found, missing fields, invalid values, permission errors | Proposed |
| FR-018 | Reject invalid or incomplete input before making any API call | Proposed |
| FR-019 | Distinguish transient errors (retry candidates) from permanent errors (surface immediately) | Proposed |
| FR-020 | Never fail silently — every failure produces a structured error response | Proposed |
| FR-021 | Skill installed in OpenClaw skill system on office2 | Proposed |
| FR-022 | Full CRUD round-trip verified against live Vikunja instance | Proposed |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
| --- | --- | --- | --- |
| NFR-001 | Skill follows OpenClaw SKILL.md format with name/description/version frontmatter | Matches Whisper skill structure | Proposed |
| NFR-002 | API token read from credential store at runtime, never in code or logs | Zero credential appearances in source or output | Proposed |
| NFR-003 | Projects and labels resolved by name at runtime, not hardcoded IDs | Zero hardcoded Vikunja IDs in skill source | Proposed |
| NFR-004 | Skill responds to API calls within reasonable time | Operations complete within 5 seconds under normal conditions | Proposed |

## Constraints

| ID | Constraint | Status |
| --- | --- | --- |
| C-001 | API token lives at `/data/services/openclaw/secrets/vikunja-api` — must not be moved or duplicated | Active |
| C-002 | Vikunja base URL is `https://office2.tail0f5f56.ts.net/api/v1` — use Tailscale Serve HTTPS endpoint | Active |
| C-003 | Skill targets Vikunja 0.24.6 — version must be noted in skill source | Active |
| C-004 | No webhooks (Tailscale-only constraint) — polling is the current pattern | Active |
| C-005 | Single-user system — no user/team management operations needed | Active |

## Success Criteria

1. Vikunja API skill appears in `openclaw skills list` on office2
2. An agent can create, read, update, complete, and delete a task via the skill against live Vikunja
3. Project and label resolution by name works for Goals project and all identity labels
4. Goals saved filter returns active goal declarations sorted by target date
5. All error paths return structured error responses — no silent failures
6. Skill source committed to repo with no credentials in code
7. Ops runbook updated with skill usage and token rotation procedure

## Key Entities

| Entity | Description |
| --- | --- |
| Task | Vikunja task with title, description, due date, priority, labels, done status, project |
| Project | Vikunja project container (e.g., Goals id=11) |
| Label | Identity label (personal, intentional, metalcasework) applied to tasks |
| Saved Filter | Named Vikunja filter (Today, Upcoming, Overdue, Goals) |
| Comment | Text annotation on a task, prefixed with agent identifier |
| API Token | Bearer token at `/data/services/openclaw/secrets/vikunja-api` |

## Assumptions

- The Whisper skill SKILL.md at `scripts/openclaw/skills/whisper/SKILL.md` is a valid format reference for the skill structure
- Whether the Whisper skill is currently deployed on office2 is a planning-phase discovery task
- The Vikunja API token in the credential store is valid and has sufficient permissions for all operations
- OpenClaw skill installation procedure will be discovered during implementation — this may be the first live deployment

## Dependencies

- F001: Vikunja deployed and running on office2
- F002: OpenClaw installed, credential store with Vikunja API token
- F006: Goals project, identity labels, and saved filters exist in Vikunja

## Scope Boundaries

**In scope**: Skill code, deployment to OpenClaw on office2, end-to-end verification against live Vikunja, ops runbook update

**Out of scope**: Agents that consume this skill (F008+), habit tracking patterns (F009), escalation logic (F011), briefing generation (F013), webhook integration, CalDAV, user/team management

## Risk Considerations

- **Vikunja API changes**: Skill written against v0.24.6; version upgrade requires re-verification
- **Token expiry**: Auth errors must surface clearly; rotation procedure in runbook
- **Service unavailability**: Skill returns clear errors; graceful degradation is the consuming feature's responsibility
- **First deployment**: OpenClaw skill deployment process may have undiscovered steps or requirements
