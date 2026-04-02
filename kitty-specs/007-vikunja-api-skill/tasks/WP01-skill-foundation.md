---
work_package_id: WP01
title: SKILL.md Foundation — Frontmatter and Resolution
dependencies: []
requirement_refs:
- C-001
- C-002
- C-003
- FR-008
- FR-009
- FR-010
- FR-011
- NFR-001
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 12ea7bbccfd30d5eec8abd0beb854ba386e6eca3
created_at: '2026-03-30T23:16:06.555173+00:00'
subtasks: [T001, T002, T003, T004]
history:
- date: '2026-03-30T22:03:15Z'
  event: created
  actor: claude
authoritative_surface: kitty-specs/007-vikunja-api-skill/contracts/vikunja-api-contract.md/
execution_mode: code_change
mission_id: 01KN5QX3WHZRDC03C5G6MQ2Y75
owned_files:
- kitty-specs/007-vikunja-api-skill/contracts/vikunja-api-contract.md
wp_code: WP01
---

# WP01: SKILL.md Foundation — Frontmatter and Resolution

## Implementation Command

```bash
spec-kitty implement WP01
```

## Objective

Create the SKILL.md file for the Vikunja API skill with OpenClaw-compatible
frontmatter, API overview, authentication pattern, health check instructions,
and project/label resolution instructions.

This establishes the skill document that all subsequent WPs will extend.

## Context

- **Skill location in repo**: `scripts/openclaw/skills/vikunja-api/SKILL.md`
- **Format reference**: `scripts/openclaw/skills/whisper/SKILL.md`
- **API base URL**: `https://office2.tail0f5f56.ts.net/api/v1`
- **Auth**: Bearer token from `/data/services/openclaw/secrets/vikunja-api`
- **Vikunja version**: 0.24.6
- **API contract reference**: `kitty-specs/007-vikunja-api-skill/contracts/vikunja-api-contract.md`

## Subtask Guidance

### T001: Write SKILL.md Frontmatter and Overview

**Purpose**: Create the skill file with valid OpenClaw frontmatter and an
overview section that explains what the skill does.

**Steps**:
1. Create `scripts/openclaw/skills/vikunja-api/SKILL.md`
2. Add YAML frontmatter:
   ```yaml
   ---
   name: vikunja_api
   description: Create, read, update, and query tasks in Vikunja via its REST API. Use when an agent needs to manage tasks, goals, labels, or projects in the Vikunja task store.
   version: 1.0.0
   ---
   ```
3. Add a top-level heading and overview paragraph explaining:
   - What Vikunja is (task management system on office2)
   - What operations the skill supports (task CRUD, project/label queries, filters, comments)
   - The API base URL
   - That all commands use the `exec` tool to run curl

**Files**: `scripts/openclaw/skills/vikunja-api/SKILL.md` (new file)

**Validation**:
- [ ] Frontmatter has name, description, version
- [ ] name is snake_case (OpenClaw convention)
- [ ] Description is a single line that helps the agent decide when to use the skill

### T002: Write Health Check Instructions

**Purpose**: Teach the agent how to verify Vikunja is running before attempting
any operations.

**Steps**:
1. Add a "Health Check" section after the overview
2. Document the curl command (no auth required):
   ```bash
   curl -s https://office2.tail0f5f56.ts.net/api/v1/info
   ```
3. Explain expected response: JSON with `version`, `frontend_url`, etc.
4. Instruct the agent to check health before any other operation
5. Document what to do if health check fails: report that Vikunja is unreachable

**Validation**:
- [ ] Health check curl command is correct
- [ ] No auth header (this endpoint is public)
- [ ] Error handling instructions included

### T003: Write Project Resolution Instructions

**Purpose**: Teach the agent how to find projects by name and understand
pseudo-projects.

**Steps**:
1. Add an "Authentication" section documenting the auth header pattern:
   ```bash
   -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)"
   ```
   Explain that this reads the token from the credential store at runtime.

2. Add a "Projects" section with:
   - List all projects: `GET /projects`
   - Document pseudo-projects: Today (id=-2), Upcoming (id=-3), Overdue (id=-4)
   - Explain that the agent should search by title to find a project ID:
     ```bash
     curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
       https://office2.tail0f5f56.ts.net/api/v1/projects
     ```
   - Instruct: parse JSON, find project where `title` matches, use its `id`
   - Document current projects for reference (Inbox, Everyday, Goals id=11, etc.)
   - Instruct: NEVER hardcode project IDs — always resolve by name

**Validation**:
- [ ] Auth header reads from credential store file
- [ ] Token value never appears in SKILL.md
- [ ] Pseudo-projects documented with negative IDs
- [ ] Agent instructed to resolve by name, not hardcode IDs

### T004: Write Label Resolution Instructions

**Purpose**: Teach the agent how to find identity labels by name.

**Steps**:
1. Add a "Labels" section with:
   - List all labels: `GET /labels`
   - Document the three identity labels: personal (id=1), intentional (id=2), metalcasework (id=3)
   - Instruct: search by `title` field to get label `id`
   - Instruct: NEVER hardcode label IDs — always resolve by name
   - Note: every task created by an agent MUST have an identity label

**Validation**:
- [ ] Label list curl command is correct
- [ ] Identity labels documented with names and colors
- [ ] Agent instructed to resolve by name
- [ ] Requirement that agent tasks must have identity labels is stated

## Definition of Done

- [ ] SKILL.md exists at `scripts/openclaw/skills/vikunja-api/SKILL.md`
- [ ] Frontmatter follows OpenClaw format (name, description, version)
- [ ] Health check section with curl command and error handling
- [ ] Authentication section with credential store pattern
- [ ] Project resolution section with pseudo-project documentation
- [ ] Label resolution section with identity label requirement
- [ ] No credentials appear in the file — only the `$(cat ...)` pattern
- [ ] File follows the Whisper skill structure as a pattern reference

## Risks

- **Credential leak**: Ensure the SKILL.md never contains the actual token value.
  Use `$(cat /data/services/openclaw/secrets/vikunja-api)` in all curl examples.

## Activity Log

- 2026-03-30T23:16:06Z – claude-opus – shell_pid=30524 – lane=doing – Assigned agent via workflow command
- 2026-03-30T23:17:22Z – claude-opus – shell_pid=30524 – lane=for_review – Ready for review: SKILL.md foundation with frontmatter, health check, auth pattern, project/label resolution
- 2026-03-30T23:18:30Z – claude-opus – shell_pid=31159 – lane=doing – Started review via workflow command
- 2026-03-30T23:19:43Z – claude-opus – shell_pid=31159 – lane=approved – Review passed: SKILL.md foundation with correct frontmatter, health check, auth pattern, project/label resolution. No credentials in source. All subtasks addressed.
- 2026-03-31T00:41:32Z – claude-opus – shell_pid=31159 – lane=done – Done override: Merged to main via manual step-by-step merge (crash diagnostic protocol)
