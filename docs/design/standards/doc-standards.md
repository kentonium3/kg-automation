---
title: "kg-automation Documentation Standards (Canon v3)"
doc_type: standard
status: approved
---

# kg-automation Documentation Standards (Canon v3)

> Supersedes Canon v2. Simplified to reduce friction while keeping docs organized.

## Required Frontmatter

All markdown files in `docs/` must include YAML frontmatter with these three fields:

```yaml
---
title: My Document Title
doc_type: handbook
status: draft
---
```

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Human-readable title |
| `doc_type` | enum | Document classification |
| `status` | enum | Lifecycle status |

## Optional Fields

These fields are validated if present but not required:

| Field | Type | Format |
|-------|------|--------|
| `id` | string | kebab-case |
| `level` | enum | overview, concept, howto, reference, policy |
| `audience` | enum | agents, humans, agents_and_humans |
| `owners` | array | Non-empty list of @handles or names |
| `last_updated` | string | YYYY-MM-DD |
| `revision` | string | vMAJOR.MINOR |
| `tags` | array | Free-form categorization |
| `aliases` | array | Alternative names |
| `links` | array | Related document links |

Additional properties are allowed — Obsidian plugins and other tools can add their own fields without breaking validation.

## Allowed Values

### doc_type

`strategy`, `charter`, `decision`, `policy`, `handbook`, `runbook`, `guide`, `reference`, `readme`, `index`, `project`, `note`

### status

`draft`, `in_review`, `approved`, `deprecated`, `archived`

### level (optional)

`overview`, `concept`, `howto`, `reference`, `policy`

### audience (optional)

`agents`, `humans`, `agents_and_humans`

## Validation

Run locally before committing:

```bash
python tooling/scripts/validate_docs.py
```

Or via Make:

```bash
make docs-check
```

The validator checks:
- Required fields present (`title`, `doc_type`, `status`)
- Enum values match allowed-values.json (for any enum field that is present)
- Secret pattern scanning (AWS keys, GitHub tokens, etc.)

## What Changed from Canon v2

| Change | v2 | v3 |
|--------|----|----|
| Required fields | 9 (id, title, doc_type, level, status, owners, last_updated, revision, audience) | 3 (title, doc_type, status) |
| Additional properties | Rejected | Allowed |
| id-filename matching | Blocking | Advisory |
| Format checks | Blocking | Advisory |
| Mermaid sync, registries, docgraph | Enforced in CI | Removed |
