# Data Model: Inbox Processing Migration

This feature operates on existing data structures. No new databases or
schemas are introduced.

## Entities

### Inbox Note

Markdown file in `00-Inbox/` with YAML frontmatter.

| Field | Type | Source | Notes |
| --- | --- | --- | --- |
| status | string | frontmatter | `unprocessed`, `processed`, or `needs-review` |
| domain | string | frontmatter | Optional — may be absent in raw captures |
| type | string | frontmatter | Optional — `capture` for inbox files |
| source | string | frontmatter | e.g., "WisprFlow", "typed" |
| updated | date | frontmatter | Last modification date |

**State transitions**:
```
unprocessed → processed    (all content blocks classified and routed)
unprocessed → needs-review (one or more blocks unclassifiable)
```

### Content Block

Extracted topic from parsing an inbox note. Not persisted as a separate
entity — exists only during processing.

| Field | Derived from | Notes |
| --- | --- | --- |
| content_type | Classification | See routing table in inbox-processor SKILL.md |
| destination | Routing table | Vault path for routed content |
| text | Extraction | Raw content from the inbox note |

### Processing Log

Markdown file at `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`.

| Section | Content |
| --- | --- |
| Files processed | Each file with brief content description |
| Actions taken | What was created/updated, with wikilinks |
| Tasks created | Vikunja tasks with project, label, and source |
| Research requests | Vikunja tasks in Research project |
| Goals routed | Declarations added to Goals-MOC.md and Vikunja |
| Items flagged | needs-review items, potential-goals, errors |
| Summary | Counts: files processed, notes created, updated, tasks, flags |

### Vikunja Task (created by task bridge)

Created via F007 vikunja_api skill.

| Field | Source | Notes |
| --- | --- | --- |
| title | Action item text from inbox note | |
| project | Inbox (action items), Research (research requests), Goals (declarations) | Resolved by name |
| identity label | Inferred from context | personal, intentional, or metalcasework |
| description | Source reference | "Source: Inbox YYYY-MM-DD HHmm.md" |
| due_date | Goal declarations only | Target date from Felix format |

## Relationships

```
Inbox Note 1:N Content Block (during processing)
Content Block → Vault File (routed destination)
Content Block → Vikunja Task (if type: task or research-request)
Content Block → Goals-MOC.md (if valid goal declaration)
Content Block → Vikunja Goals Task (if valid goal declaration)
Processing Log ← all actions from one processing run
```

## Agent Workspace Files

### felix-admin-capture workspace

| File | Purpose | Auto-injected |
| --- | --- | --- |
| SOUL.md | Kent-voice authoring identity | Yes |
| AGENTS.md | Standing orders: routing table, task bridge, goal handling | Yes |
| USER.md | Kent's context (name, timezone, projects) | Yes |
| IDENTITY.md | Agent identity (name, emoji) | Yes |
| TOOLS.md | Tool-specific notes | Yes |
| HEARTBEAT.md | Not used (cron-driven, not heartbeat-driven) | Yes |

### Shared skills (available to all agents)

| Skill | Location | Used for |
| --- | --- | --- |
| vikunja_api | `~/.openclaw/skills/vikunja-api/SKILL.md` | Task creation, goal tasks |
| whisper | `~/.openclaw/skills/whisper/SKILL.md` | Not used by this agent |
