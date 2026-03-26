---
id: claude-code-instructions
title: Claude Code Instructions — kg-automation
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2026-03-25'
revision: v3.0
audience: agents_and_humans
---

# Claude Code Instructions — kg-automation

Instructions for Claude Code working in the kg-automation repository.

## Start Every Session By Reading

1. `CLAUDE.md` at repo root — read this first, always
2. `docs/design/personal-ai-system-spec-v03.md` — canonical architecture
3. `git log --oneline -10` — understand current state before touching anything
4. `git status` — confirm clean working tree

## Role in This System

Claude Code is the **execution layer**. It implements what has been designed.
Architecture decisions live in `docs/design/`. If something isn't in the spec,
stop and ask rather than infer.

## Platform Reality

- **Mac (MacBook Pro)**: authoring and interaction only
- **office2 (Ubuntu 24.04 LTS)**: always-on hub — this is where things run
- **Tailscale**: the network between them
- **Windows**: not supported, does not exist in this system
- **Dropbox**: not used for coordination

When writing scripts or configs, target Linux (office2) unless explicitly told
otherwise.

## Key Services on office2

| Service | Details |
|---|---|
| OpenClaw | Orchestration engine, skills, WhatsApp webhook |
| Vikunja | Docker container, port 3456, SQLite backend |
| Obsidian Sync | `ob sync --continuous` via systemd (`obsidian-sync.service`) |
| Restic | Backups at 4AM to `/mnt/backups/restic-repo` |

Access office2 via Tailscale SSH. Never expose management ports to public internet.

## Skill Files

Existing skills to be migrated from second-brain to office2/OpenClaw:

| Skill | Current location | Status |
|---|---|---|
| inbox-processor | `~/second-brain/.claude/skills/inbox-processor/SKILL.md` | Migrate (FEAT-007) |
| kent-voice | `~/second-brain/.claude/skills/kent-voice/SKILL.md` | Migrate (FEAT-008) |
| vault-writer | `~/second-brain/.claude/skills/vault-writer/SKILL.md` | Migrate (FEAT-009) |

When migrating: add Vikunja API task bridge to inbox-processor, no other
changes to skill logic.

## Git Workflow

- Push directly to main for routine changes
- Use feature branches when useful (complex multi-step work, experiments)
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`
- CI validates on every push to main
- Read file before editing (always)

## Write Permissions

**Allowed**: `docs/`, `ai-agents/`, `systems/`, `scripts/`, `workflows/`
**Never**: `.env` files, secrets in any file, `rm -rf`, force push
**Review required**: `.github/workflows/`

## Architecture Documentation (Standing Directive)

The system maintains a live architecture documentation store at
`docs/design/architecture/`. **JSON files are authoritative; markdown
files are views.**

Any work package that deploys, modifies, or removes a service, credential,
port, or data flow MUST update the relevant files in
`docs/design/architecture/data/` and their markdown counterparts in the
same commit. This is a non-optional deliverable, not a follow-up task.

| Change type | JSON file to update |
|---|---|
| New/changed service | `service-inventory.json` |
| New/changed credential | `credential-manifest.json` |
| New/changed port or IP | `network-topology.json` |
| New/changed data flow | `data-flows.json` |
| New/changed hardware | `hardware-inventory.json` |

Full protocol: `docs/design/architecture/change-control.md`

## Second Brain Boundary

`~/second-brain/` is a separate repo. kg-automation scripts may **read** from
the Obsidian vault path when explicitly required (e.g., inbox-processor reads
`00-Inbox/`). Never write to second-brain paths from kg-automation unless the
skill definition explicitly requires it (vault-writer does; nothing else does).

**Absolute rule**: `~/second-brain/vault/Notes/02-Growth/_private/` is never
read, written, referenced, or logged by any script or agent. No exceptions.

## Credential Handling

All credentials live in office2's scoped secrets store.
- Named sets: `personal-google`, `intentional-google`, `whatsapp-meta`,
  `anthropic`, `vikunja-api`
- Never put credentials in code, scripts, or committed files
- Skills request credentials by name — the resolver injects at runtime

## Vikunja API

Base URL (from office2 or Tailscale): `http://office2:3456/api/v1`
Auth: JWT token from `/api/v1/login`, stored in secrets store as `vikunja-api`
Key endpoints:
- `POST /tasks` — create task
- `PATCH /tasks/{id}` — update task
- `GET /tasks/all` — list tasks with filter support
- `POST /filters` — create saved filter

## Feature Sequence (Phase 1)

Current build order from spec Section 10:

```
FEAT-001  Vikunja Docker deploy on office2 + project structure
FEAT-002  OpenClaw install and configuration
FEAT-003  WhatsApp channel (Meta Cloud API)
FEAT-004  Whisper transcription skill
FEAT-005  Vikunja API skill (CRUD wrapper)
FEAT-006  Intent Parser skill
FEAT-007  Migrate inbox-processor + task bridge
FEAT-008  Migrate kent-voice skill
FEAT-009  Migrate vault-writer skill
FEAT-010  Hourly inbox poll + on-demand trigger
FEAT-011  Goal Context Loader skill
FEAT-012  Personal Google Calendar skill
FEAT-013  Task → Calendar event linking
FEAT-014  Daily briefing heartbeat
FEAT-015  Level 1–2 escalation heartbeat
```

Check `docs/func-spec/` for feature-level specs before implementing any FEAT.
If a func-spec doesn't exist yet, create a GitHub issue rather than proceeding
from the high-level spec alone.
