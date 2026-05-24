---
title: "F007: Vikunja API Skill"
doc_type: func-spec
status: draft
feature: F007
---

# F007: Vikunja API Skill

**Version**: 1.0
**Priority**: HIGH
**Type**: Infrastructure

---

## Executive Summary

OpenClaw can communicate via WhatsApp and transcribe voice notes, but it
cannot read or write tasks in Vikunja. Every subsequent feature that touches
tasks, goals, habits, escalation, or briefings depends on this capability.
F007 creates the OpenClaw skill that wraps the Vikunja REST API, giving all
future agents a single, consistent interface for task store operations.

Current gaps:
- ❌ OpenClaw has no way to create, read, update, or query Vikunja tasks
- ❌ No programmatic access to goal declarations, labels, or saved filters
- ❌ No foundation for habit tracking, escalation, or briefings

This spec delivers a Vikunja API skill installed in OpenClaw that covers
the full task CRUD needed by Phase 1 features, plus project and label
queries, filter execution, and comment operations.

---

## Problem Statement

**Current State:**
```
OpenClaw
└── ✅ WhatsApp channel (F004)
└── ✅ Whisper transcription skill (F003)
└── ❌ No Vikunja API skill
└── ❌ Cannot read or write tasks

Vikunja
└── ✅ Running at https://office2.tail0f5f56.ts.net (F001, ops fix)
└── ✅ Goals project (id=11), identity labels, saved filters (F006)
└── ✅ API token for OpenClaw agent stored in credential store (F002)
└── ❌ Not connected to OpenClaw
```

**Target State:**
```
OpenClaw
└── ✅ Vikunja API skill installed and tested
└── ✅ Can create, read, update, complete tasks
└── ✅ Can query projects, labels, and saved filters
└── ✅ Can add comments to tasks
└── ✅ Uses stored API token — no credentials in skill code

Vikunja
└── ✅ Reachable by OpenClaw via Tailscale
└── ✅ All task operations available to agents
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **What Vikunja currently has — post-F006 state**
   - `docs/runbooks/vikunja-ops.md` — current project structure, saved
     filters, identity labels, Goals project (id=11), API token location
   - `docs/design/architecture/data/service-inventory.json` — Vikunja's
     current URL (`https://office2.tail0f5f56.ts.net`), bind config, and
     TLS termination via Tailscale Serve
   - `docs/design/architecture/data/credential-manifest.json` — `vikunja-api`
     token location at `/data/services/openclaw/secrets/vikunja-api`

2. **OpenClaw skill system**
   - `docs/runbooks/openclaw-ops.md` — skill directory, how skills are
     installed, credential store location
   - F003 func-spec and its artifacts — the Whisper skill is the closest
     existing pattern for an OpenClaw skill that calls an external service.
     Study it before writing this skill.
   - OpenClaw documentation at https://docs.openclaw.ai — skill format,
     how skills declare their dependencies and tool requirements

3. **What F008 and beyond will need**
   - `docs/research/005-system-architecture-development/roadmap.md` — F008
     (inbox migration) and F009 (habit tracking) are the immediate consumers.
     Understand what operations they will need so the skill is built to
     the right scope, not too narrow or too broad.
   - `docs/research/005-system-architecture-development/user-story-catalog.md`
     — B-H01 through B-H06 (habit tracking) and B-G01 through B-G06 (goal
     management) define the task operations that must be supported

4. **Vikunja API documentation**
   - Planning phase must research the Vikunja REST API for version 0.24.6
     to confirm the exact endpoint signatures, authentication headers,
     filter syntax, and response shapes before writing the skill
   - Base URL is `https://office2.tail0f5f56.ts.net/api/v1`
   - Authentication is Bearer token from the credential store

---

## Functional Requirements

### FR-1: Core Task Operations

**What it must do:**
- Create a task in a specified project with: title, description, due date,
  priority, and identity label
- Read a task by ID
- Update a task's fields (title, description, due date, priority, done
  status, labels)
- Mark a task complete
- Delete a task (soft delete / archive — not hard delete)

**Business rules:**
- Every task created by an agent must carry an identity label
  (personal, intentional, or metalcasework)
- Due dates must be stored in a format Vikunja accepts and that can be
  queried in saved filters
- Task creation must be idempotent where possible — if a task with
  the same title exists in the same project, surface it rather than
  creating a duplicate

**Success criteria:**
- [ ] Agent can create a task in any Vikunja project via the skill
- [ ] Agent can read a task by ID
- [ ] Agent can update any task field
- [ ] Agent can mark a task complete
- [ ] Task creation fails gracefully with a clear error if the project
  does not exist or the label is invalid

---

### FR-2: Project and Label Queries

**What it must do:**
- List all projects available to the agent
- Get a project by name (returns its ID and metadata)
- List all labels
- Get a label by name (returns its ID)

**Business rules:**
- Project and label IDs must be resolved by name before creating tasks —
  agents should not hardcode IDs, as IDs may change if Vikunja is
  re-provisioned
- The Goals project (currently id=11) must be queryable by name

**Success criteria:**
- [ ] Agent can retrieve the Goals project by name and get its ID
- [ ] Agent can retrieve any identity label (personal, intentional,
  metalcasework) by name and get its ID
- [ ] Label and project resolution works even if IDs change

---

### FR-3: Filter Execution

**What it must do:**
- Execute Vikunja's saved filters by name (Today, Upcoming, Overdue, Goals)
  and return the resulting task list
- Execute an ad-hoc filter query against tasks (e.g., tasks in a specific
  project, tasks with a specific label, tasks due within a date range)

**Business rules:**
- Filter results must include enough task metadata for the briefing feature
  (F013) to construct a useful summary: title, due date, priority, project,
  labels, done status
- The Goals filter must return active (incomplete) declarations sorted by
  target date

**Success criteria:**
- [ ] Agent can execute the Today saved filter and get current tasks
- [ ] Agent can execute the Goals saved filter and get active declarations
- [ ] Agent can filter tasks by project, label, or due date range

---

### FR-4: Comment Operations

**What it must do:**
- Add a comment to a task (used by escalation engine to record escalation
  history and by agents to annotate task state)
- Read comments on a task

**Business rules:**
- Agent comments must be distinguishable from user comments — include an
  agent identifier in the comment body (e.g., "[Felix]" prefix)

**Success criteria:**
- [ ] Agent can add a comment to any task
- [ ] Agent can read existing comments on a task

---

### FR-5: Error Handling, Guardrails, and Graceful Degradation

**What it must do:**
- Handle Vikunja API errors gracefully — network timeouts, authentication
  failures, and resource-not-found errors must surface as clear, actionable
  messages rather than raw stack traces
- If the Vikunja service is unreachable, the skill must halt the operation
  and return a clear error to the calling agent — never silently drop the
  operation or partially complete it
- Reject invalid or incomplete input parameters before making any API call —
  if a required field is missing or invalid (e.g., no identity label on task
  creation, unrecognized project name, malformed due date), the skill must
  return a specific validation error immediately
- If the skill cannot determine how to fulfill a request with the parameters
  given, it must stop and return a descriptive error explaining what is
  missing or ambiguous — it must never guess, invent values, or proceed with
  partial data
- Authentication errors must surface as a specific credential error, not a
  generic failure

**Business rules:**
- **Never fail silently** — this is a constitution directive. Every failure
  must produce a structured error response that the calling agent can act on
- **Never invent data** — if a project name doesn't resolve, a label doesn't
  exist, or a required field is absent, stop and report. Do not substitute
  defaults or make assumptions.
- **Halt on ambiguity** — the skill operates on explicit structured inputs.
  If the input is ambiguous or incomplete, the correct behavior is to halt
  and return an error, not to attempt partial execution
- The skill must distinguish between transient errors (network issues —
  retry candidates) and permanent errors (bad input, auth failure — surface
  to calling agent immediately)

**Error categories the skill must handle explicitly:**
- Vikunja service unreachable (network/timeout)
- Authentication failure (token invalid or expired)
- Project not found by name
- Label not found by name
- Task not found by ID
- Missing required field on task creation (title, project, identity label)
- Invalid field value (malformed date, unrecognized priority)
- Operation not permitted (scope or permission issue)

**Success criteria:**
- [ ] Network timeout halts the operation and returns a clear error
- [ ] Authentication failure returns a specific credential error
- [ ] Project or label not found by name returns a specific not-found error
- [ ] Task creation with a missing identity label is rejected before the
  API call is made
- [ ] Task creation with a missing required field returns a validation error
- [ ] No operation fails silently under any error condition
- [ ] Error responses are structured so the calling agent can distinguish
  error type and decide whether to retry, escalate, or report to Kent

---

### FR-6: End-to-End Verification

**What it must do:**
- Verify the skill works against the live Vikunja instance on office2 as
  part of the acceptance criteria
- Create a test task, read it back, update it, add a comment, and delete it
  as a complete round-trip test

**Success criteria:**
- [ ] Full CRUD round-trip verified against live Vikunja
- [ ] Goals filter returns the goal declarations created in F006
- [ ] Skill is installed in OpenClaw and accessible to agents

---

## Architecture Documentation Updates

F007 makes no changes to deployed services, ports, credentials, or network
topology. The Vikunja API token already exists in the credential store (F002).
The skill is installed inside OpenClaw's skill system.

No architecture documentation updates required — this feature makes no
changes to deployed services, credentials, ports, or data flows.

---

## Out of Scope

- ❌ Any agent that calls this skill — F008, F009, and beyond use it
- ❌ Habit tracking or recurring task patterns — F009
- ❌ Escalation label management — F011
- ❌ Briefing generation — F013
- ❌ Vikunja webhook integration — deferred (Tailscale-only constraint means
  polling is the current pattern; webhooks require Tailscale Funnel)
- ❌ CalDAV integration — not planned for Phase 1
- ❌ Vikunja user or team management — not needed for single-user system

---

## Success Criteria

**Complete when:**

### Skill Installation
- [ ] Vikunja API skill installed in OpenClaw skill system
- [ ] Skill source committed to repo for reproducibility

### Task Operations
- [ ] Create, read, update, complete tasks verified against live Vikunja
- [ ] Project and label resolution by name works
- [ ] Goals filter returns active goal declarations

### Error Handling
- [ ] All error paths surface clear messages
- [ ] No silent failures

### Documentation
- [ ] Ops runbook updated to include Vikunja API skill usage and token
  rotation procedure
- [ ] Architecture docs updated (updated_by: F007) if any JSON files change

---

## Architecture Principles

### Resolve by Name, Not ID

Vikunja project and label IDs are stable under normal operations but can
change if the service is re-provisioned. The skill must resolve names to IDs
at runtime rather than hardcoding numeric IDs. This makes the skill resilient
to re-provisioning and keeps agent code readable.

### Credential from Store, Never in Code

The Vikunja API token lives at `/data/services/openclaw/secrets/vikunja-api`
(mode 600, claude-owned). The skill must read it from the credential store at
runtime. The token must never appear in skill source code, config files, or
logs. This is a constitution directive with no exceptions.

### Foundation Skill

This skill is consumed by every subsequent Phase 1 feature that touches tasks.
It must be reliable, well-tested, and consistent. Future agents will call it
without inspecting its internals — the interface must be stable.

---

## Constitutional Compliance

✅ **No credentials in code**: API token read from credential store at
runtime, never in skill source or logs.

✅ **Agents start at Gate 1**: This is a skill, not an agent — it has no
autonomous behavior. It executes operations when called.

✅ **Safety parameters**: FR-5 requires all errors to surface clearly.
The skill never fails silently.

✅ **Narrow scope**: This skill does one thing — Vikunja API operations.
It does not contain routing logic, business rules, or scheduling.

✅ **Docs adjacent**: Ops runbook updated alongside deployment.

---

## Risk Considerations

**Risk: Vikunja API changes between versions**
- The skill is written against Vikunja 0.24.6. A version upgrade may
  change endpoint signatures or filter syntax.
- Mitigation: Skill is version-pinned in documentation. API version noted
  in skill source as a comment. Any Vikunja version upgrade (future feature)
  must re-verify this skill.

**Risk: Token expiry or revocation**
- The `openclaw-agent` token in Vikunja could be revoked accidentally or
  expire.
- Mitigation: FR-5 requires authentication errors to surface clearly.
  Token rotation procedure documented in vikunja-ops.md runbook.

**Risk: Vikunja service unavailable**
- If office2 is down or Vikunja is stopped, all skill calls fail.
- Mitigation: FR-5 requires clear error surfacing. The heartbeat and
  briefing features (F009, F013) will need graceful degradation when
  Vikunja is unavailable — that is their responsibility, not this skill's.

---

## Notes for Implementation

**Pattern discovery (planning phase):**
- Study the F003 Whisper skill as the closest existing pattern for an
  OpenClaw skill calling an external HTTP service — understand how it
  handles the request/response cycle and error paths
- Read the OpenClaw skill documentation to understand the exact format
  required: SKILL.md structure, tool declarations, how the skill is
  invoked by an agent
- Discover the correct way to read from the credential store within an
  OpenClaw skill context — this is critical and must be researched before
  writing any skill code

**Vikunja API base URL:**
- `https://office2.tail0f5f56.ts.net/api/v1` (post-ops-fix URL with TLS)
- Not `http://100.92.197.90:3456/api/v1` — the Tailscale Serve URL is the
  correct endpoint from inside the Tailscale network

**Scope confirmation:**
- Confirm the exact set of operations F008 (inbox migration) and F009
  (habit tracking) will need before finalizing the skill's interface.
  Build to that scope — not less, not more.

---

**END OF SPECIFICATION**
