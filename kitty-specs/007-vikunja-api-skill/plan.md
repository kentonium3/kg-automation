# Implementation Plan: Vikunja API Skill

**Branch**: `007-vikunja-api-skill` | **Date**: 2026-03-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/kitty-specs/007-vikunja-api-skill/spec.md`

## Summary

Create an OpenClaw skill (SKILL.md) that wraps the Vikunja REST API v0.24.6,
providing task CRUD, project/label resolution by name, filter execution, and
comment operations. Deploy to `~/.openclaw/skills/vikunja-api/` on office2 and
verify end-to-end against the live Vikunja instance.

## Technical Context

**Language/Version**: Markdown (SKILL.md instruction document) + bash/curl for API calls
**Primary Dependencies**: OpenClaw skill system, Vikunja REST API v0.24.6
**Storage**: N/A (skill is stateless; Vikunja manages all data)
**Testing**: Manual end-to-end via `openclaw agent --message` against live Vikunja
**Target Platform**: office2 (Ubuntu 24.04 LTS) running OpenClaw 2026.3.24
**Project Type**: Single skill directory (SKILL.md + optional reference files)
**Performance Goals**: API calls complete within 5 seconds
**Constraints**: Token from file-based credential store only; no credentials in code/config
**Scale/Scope**: Single-user system, one OpenClaw agent

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Directive | Status | Notes |
| --- | --- | --- |
| TEST_FIRST | Pass | End-to-end verification against live Vikunja is final WP |
| No credentials in code | Pass | Token read from `/data/services/openclaw/secrets/vikunja-api` at runtime via `cat` |
| Never fail silently | Pass | SKILL.md includes explicit error handling instructions for all error categories |
| Narrow scope | Pass | Skill does one thing: Vikunja API operations |
| Docs adjacent | Pass | Ops runbook updated alongside deployment |

## Project Structure

### Documentation (this feature)

```
kitty-specs/007-vikunja-api-skill/
├── plan.md              # This file
├── research.md          # Phase 0 output — API research, architecture decisions
├── data-model.md        # Phase 1 output — Vikunja entity reference
├── contracts/
│   └── vikunja-api-contract.md  # Phase 1 output — API endpoint reference
└── tasks.md             # Phase 2 output (/spec-kitty.tasks)
```

### Source Code (repository root)

```
scripts/openclaw/skills/vikunja-api/
└── SKILL.md             # The skill document — deployed to office2
```

No `src/`, `tests/`, or build system needed. The "source code" is the SKILL.md
instruction document. Testing is end-to-end against the live Vikunja instance.

**Structure Decision**: Single SKILL.md file in a skill directory, following the
Whisper skill pattern at `scripts/openclaw/skills/whisper/SKILL.md`.

## Key Design Decisions

### 1. Skill is an instruction document, not executable code

OpenClaw skills are SKILL.md files that teach the agent how to use tools. The
agent reads the instructions and uses `exec` to run curl commands against the
Vikunja API. This matches the deployed Whisper skill pattern.

### 2. Token read from file at runtime

Every curl command includes `$(cat /data/services/openclaw/secrets/vikunja-api)`
in the Authorization header. This keeps the token out of the SKILL.md source
and out of openclaw.json config.

### 3. Name-based resolution in instructions

The SKILL.md teaches the agent to resolve project and label names to IDs before
using them. The instructions include the curl commands to list projects/labels
and extract IDs by name.

### 4. Labels assigned via separate endpoint

Vikunja's Task model has read-only labels. The skill instructions teach a
two-step process: create task, then add label(s) via `PUT /tasks/{id}/labels`.

### 5. Pseudo-projects for built-in filters

Today (id=-2), Upcoming (id=-3), and Overdue (id=-4) are accessed as
`GET /projects/{id}/tasks`. The Goals project is a real project (id=11).

### 6. Delete is permanent

Vikunja v0.24.6 has no soft-delete/archive for tasks. The skill instructions
warn the agent that `DELETE /tasks/{id}` is permanent and should only be used
for test cleanup or when explicitly requested.

## Deployment Plan

1. Write SKILL.md in `scripts/openclaw/skills/vikunja-api/`
2. Copy to `~/.openclaw/skills/vikunja-api/SKILL.md` on office2 via `scp` or `ssh + cat`
3. Verify with `openclaw skills list` (skill should appear as ready)
4. Test with `openclaw agent --message` for end-to-end verification
5. Update ops runbook with skill usage and troubleshooting

## Risk Mitigations

| Risk | Mitigation |
| --- | --- |
| Vikunja API version change | Skill documents target version (0.24.6); version upgrade requires re-verification |
| Token expiry | Auth errors are documented as a specific error class; rotation procedure in runbook |
| First skill deployment to OpenClaw | Whisper skill is already deployed; deployment procedure is verified |
| Delete is permanent | Skill instructions include explicit warning; agent must confirm before deletion |

## Complexity Tracking

No constitution violations. No complexity justifications needed.
