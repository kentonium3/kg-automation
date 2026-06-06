# TOOLS.md

## Skills

- **vikunja-api**: Task CRUD, labels, projects, comments, queries
  Path: `~/.openclaw/skills/vikunja-api/SKILL.md`
- **task-intelligence**: Task structuring model, inference rules, confidence thresholds
  Path: `~/.openclaw/skills/task-intelligence/SKILL.md`

## Tools

### WhatsApp

Primary interaction channel for Kent communication.

- Send messages, receive replies
- Used for: clarification questions, task proposals, batch enrichment, alerts

### Vikunja API

REST API for task management.

- **Base URL**: https://office2.tail0f5f56.ts.net/api/v1
- **Auth**: Bearer token from /data/services/openclaw/secrets/vikunja-api
- Use the vikunja_api skill for all Vikunja operations
- Run `openclaw skills info vikunja_api` for details

### Action log

Central logging to `~/second-brain/agents/logs/`.

- **Format**: task-intelligence-YYYY-MM-DD.md
- Required per Felix Constitution Directive 3
- Every action must be logged with: agent name, action type, target, outcome,
  timestamp, and autonomy level

## Restrictions

- NEVER read, write, or reference `~/second-brain/notes/04-Growth/_private/` (path renumbered from `02-Growth/_private/` in mission 026 / #152)
- NEVER log API tokens or credentials
- NEVER create tasks without Kent's confirmation (while at Assisted level)
