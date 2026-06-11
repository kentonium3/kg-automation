---
work_package_id: WP05
title: Architecture + Constitution documentation sync
dependencies:
- WP02
requirement_refs:
- FR-005
- FR-011
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T025
- T026
- T027
- T028
- T029
phase: Phase 3 - Documentation
shell_pid: "47640"
history:
- at: '2026-06-11T03:26:12Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/
execution_mode: code_change
owned_files:
- docs/constitution/agent-registry.json
- docs/constitution/AGENT-REGISTRY.md
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/service-dependencies.view.md
tags: []
agent_profile: curator-carla
role: curator
agent: "claude::reviewer-renata:reviewer"
---

# Work Package Prompt: WP05 – Architecture + Constitution documentation sync

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, run `/ad-hoc-profile-load <agent_profile>` using the `agent_profile` value in this WP's frontmatter. The profile establishes your identity, governance scope, boundaries, and initialization — it is required for this work package. Do not proceed to the Objective section without loading the profile.

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual execution workspace is resolved later**: `/spec-kitty.implement` selects the lane worktree.

## Objectives & Success Criteria

Update the canonical architecture + constitution data and narrative views to reflect the new `felix-admin-calendar` agent. After this WP, the kg-automation governance and architecture documentation accurately represents the post-mission state.

**Requirements covered**: FR-005, FR-011 (partial — runbook verifications live in WP06; smoke runbook + INDEX/Portal live in WP07).

## Context & Constraints

- Authoritative entry shapes are in `kitty-specs/felix-calendar-subagent-extraction-01KTTA33/data-model.md`.
- Per CLAUDE.md: "machine-readable JSON is authoritative; narrative markdown provides context. When they conflict, JSON wins." Update JSON first, then narrative.
- Per DIR-014: doc-sync is a mandatory part of the mission, not optional.
- Reference patterns in the same files: existing `felix-admin-tasker` and `felix-admin-escalation` entries are the canonical templates for shape.
- The `mission-agent-prompt-changed` and `mission-service-added-or-modified` change classes in `signal-to-doc-map.json` enumerate the specific doc targets — those are encoded as this WP's `owned_files`.

## Subtasks & Detailed Guidance

### Subtask T025 – agent-registry.json entry

- **Purpose**: Register felix-admin-calendar under Felix governance.
- **Steps**:
  1. Read `docs/constitution/agent-registry.json`. Locate the `agents` dict.
  2. Add a new key `felix-admin-calendar` with the exact shape from `data-model.md` § agent-registry.json entry.
  3. `registered`: `2026-06-11`.
  4. `deployed_feature`: `"#579"`.
  5. `transition_history`: single entry per the data-model template.
  6. Bump the top-level `updated` field to today's ISO date if convention requires; check the file's existing pattern.
- **Files**: `docs/constitution/agent-registry.json`
- **Parallel?**: [P] with T026/T027/T028.

### Subtask T026 – AGENT-REGISTRY.md narrative view

- **Purpose**: Markdown view of the JSON registry.
- **Steps**:
  1. Read `docs/constitution/AGENT-REGISTRY.md`. Determine: is this file hand-maintained or auto-generated from the JSON? Look for a generator script reference in the file header.
  2. If hand-maintained: add a new row/section for felix-admin-calendar matching the shape used for the other agents.
  3. If auto-generated: find the generator and re-run it. Document in Activity Log which path was taken.
  4. Verify the markdown view's information matches the JSON authoritative source.
- **Files**: `docs/constitution/AGENT-REGISTRY.md`
- **Parallel?**: [P].

### Subtask T027 – service-inventory.json entry

- **Purpose**: Add the new agent to the canonical service inventory.
- **Steps**:
  1. Read `docs/design/architecture/data/service-inventory.json`. Find the existing felix-admin-* entries — they're the template.
  2. Add felix-admin-calendar with fields matching the existing agent-service shape:
     - service id / name (felix-admin-calendar)
     - host (office2)
     - workspace (`/data/services/openclaw/calendar-agent`)
     - agentDir (`/home/claude/.openclaw/agents/felix-admin-calendar/agent`)
     - model (`anthropic/claude-haiku-4-5`)
     - delivery / schedule / dependencies / config_files / runbooks — match the felix-admin-tasker / felix-admin-habits shape; for an event-driven agent (not scheduled), the schedule field is null or empty
     - depends_on: includes gog (for Calendar API) and the openclaw-gateway / openclaw-gateway-env (for OAuth)
  3. Validate JSON parse.
- **Files**: `docs/design/architecture/data/service-inventory.json`
- **Parallel?**: [P].
- **Notes**: If the JSON shape uses an `agents` sub-section or treats agents differently from services, follow the pattern of existing felix-admin-* entries — don't invent a new shape.

### Subtask T028 – service-inventory.md narrative

- **Purpose**: Update the narrative view.
- **Steps**:
  1. Read `docs/design/architecture/service-inventory.md`. Find the section that lists felix-admin-* agents.
  2. Add felix-admin-calendar with the same narrative pattern.
  3. Cross-reference: link to felix-admin-calendar's workspace path; link to the spec/plan/issue.
- **Files**: `docs/design/architecture/service-inventory.md`
- **Parallel?**: [P].

### Subtask T029 – service-dependencies.view.md diagram

- **Purpose**: Update the dependency diagram (likely Mermaid) to include felix-admin-calendar.
- **Steps**:
  1. Read `docs/design/architecture/service-dependencies.view.md`. Locate the Mermaid block(s).
  2. Add a node for felix-admin-calendar.
  3. Add edges:
     - main → felix-admin-calendar (delegation)
     - felix-admin-capture → felix-admin-calendar (delegation, since capture initiates calendar event creation per data-model.md)
     - felix-admin-calendar → gog (uses gog CLI for Google Calendar)
     - felix-admin-calendar → openclaw-gateway-env (credential source)
  4. Verify Mermaid block renders by previewing in Obsidian or by `mermaid` CLI parse.
- **Files**: `docs/design/architecture/service-dependencies.view.md`
- **Parallel?**: No — review the others' shapes first to ensure consistency.

## Test Strategy

- JSON files: `python3 -c "import json; json.load(open('<path>'))"` for each — must parse.
- Markdown narrative: visual review.
- Mermaid diagram: parse via `mermaid` CLI or Obsidian preview.

If the repo has a `tooling/scripts/validate_docs.py` style validator, run it after these changes.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Narrative view diverges from JSON authoritative source | T028 author reads JSON before drafting markdown; reviewer compares |
| Mermaid syntax error breaks the diagram view | T029 parses or previews before committing |
| Auto-generated markdown view manually edited (or vice-versa) | T026 step 1 forces the call before editing |
| Schedule / dependency fields incomplete | Reference existing felix-admin-* entries; don't leave unfilled |

## Review Guidance

- All 5 file changes present?
- JSON files parse cleanly?
- AGENT-REGISTRY.md and agent-registry.json carry the same information for felix-admin-calendar?
- service-inventory.json entry shape matches existing felix-admin-* entries?
- service-dependencies.view.md diagram includes the new node + 4 expected edges?
- All values referenced from data-model.md (model, workspace, agentDir, scope, registered date)?

## Activity Log

> **CRITICAL**: Activity log entries MUST be in chronological order (oldest first, newest last).

- 2026-06-11T03:26:12Z -- system -- Prompt created.
- 2026-06-11T04:23:16Z – claude::curator-carla:curator – shell_pid=43094 – Assigned agent via action command
- 2026-06-11T04:31:08Z – claude::curator-carla:curator – shell_pid=43094 – Ready for review: 5 doc surfaces updated, JSON validates, narrative views consistent with JSON authoritative sources
- 2026-06-11T04:32:04Z – claude::reviewer-renata:reviewer – shell_pid=47640 – Started review via action command
