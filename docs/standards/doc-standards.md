---
id: doc-standards
title: kg-automation Documentation Standards (Canon v2)
doc_type: policy
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: "2024-10-29"
revision: v2.0
audience: agents_and_humans
tags:
  - standards
  - documentation
  - canon-v2
aliases:
  - documentation-standards
  - doc-canon
links:
  - docs/standards/frontmatter.schema.json
  - docs/standards/allowed-values.json
---

# kg-automation Documentation Standards (Canon v2)

## Overview

This document defines **Canon v2**, the machine-readable documentation standard for kg-automation. All documentation MUST conform to these standards to pass CI validation.

## Machine Truth Files

Canon v2 is enforced through machine-readable configuration:

- **`allowed-values.json`** - Enumerated values for all classification fields
- **`frontmatter.schema.json`** - JSON Schema (Draft 2020-12) for frontmatter validation
- **Validator** - `tooling/scripts/validate_docs.py` enforces all rules

## Required Frontmatter

All markdown documentation files MUST include YAML frontmatter with these **required** fields:

```yaml
---
id: my-document-id
title: My Document Title
doc_type: handbook
level: reference
status: draft
owners:
  - "@kentonium3"
last_updated: 2024-10-29
revision: v1.0
audience: agents_and_humans
---
```

### Field Specifications

| Field | Type | Format | Description |
|-------|------|--------|-------------|
| `id` | string | kebab-case | Unique identifier, MUST match filename stem |
| `title` | string | any | Human-readable title |
| `doc_type` | enum | see allowed-values.json | Document classification |
| `level` | enum | see allowed-values.json | Documentation depth/type |
| `status` | enum | see allowed-values.json | Lifecycle status |
| `owners` | array | @username or name | Non-empty list of owners |
| `last_updated` | string | YYYY-MM-DD | ISO date of last update |
| `revision` | string | vMAJOR.MINOR | Semantic version |
| `audience` | enum | see allowed-values.json | Target audience |

### Optional Fields

```yaml
tags: []          # Categorization tags
aliases: []       # Alternative names/identifiers
links: []         # Related document links
```

## Allowed Values

All enum fields are validated against `docs/standards/allowed-values.json`:

### doc_type

Valid values: `strategy`, `charter`, `decision`, `policy`, `handbook`, `runbook`, `guide`, `reference`, `readme`, `index`, `project`, `note`

### level

Valid values: `overview`, `concept`, `howto`, `reference`, `policy`

### status

Valid values: `draft`, `in_review`, `approved`, `deprecated`, `archived`

### audience

Valid values: `agents`, `humans`, `agents_and_humans`

## Templates

Templater templates are provided in `docs/_templates/`:

- **`base.md`** - General purpose documentation (doc_type: guide)
- **`handbook.md`** - Handbook/manual documentation (doc_type: handbook)
- **`runbook.md`** - Operational runbooks (doc_type: runbook, level: howto)

### Using Templates

In Obsidian with Templater plugin:
1. Create new file
2. Invoke Templater command
3. Select appropriate template
4. Template auto-generates frontmatter with correct date and kebab-case ID

## Validation

### Local Validation

Run the validator before committing:

```bash
"C:\Program Files\Python312\python.exe" tooling/scripts/validate_docs.py
```

The validator checks:
- All required frontmatter fields present
- Enum values match allowed-values.json
- `id` is kebab-case and matches filename stem
- `owners` is non-empty array
- `last_updated` is ISO date (YYYY-MM-DD)
- `revision` is vMAJOR.MINOR format
- No duplicate IDs across repository

### CI Validation

All pull requests automatically run validation via GitHub Actions. PRs will fail if:
- Any markdown file has invalid/missing frontmatter
- Any enum field contains disallowed value
- Filename and ID don't match
- Format validation fails

## Migration Notes

Canon v2 introduces breaking changes from Canon v1:

### Changed Fields

- `last_validated` → `last_updated`
- `version` → `revision` (format changed to vMAJOR.MINOR)
- `owner` → `owners` (now an array)

### New Required Fields

- `audience` (NEW in v2)
- `title` (NEW in v2)

### Changed Allowed Values

All doc_type, level, and status values updated. See `allowed-values.json` for current canonical list.

## Claude Code Integration

Canon v2 includes Claude Code policy and preset integration:

### Policy: doc-standards

Pre-reads standards files before doc creation:
- `.claude/policies/doc-standards.json`

### Preset: new-doc

Interactive doc creation workflow:
- `.claude/presets/new-doc.json`

Usage: Invoke `new-doc` preset in Claude Code to create standards-compliant documentation with template selection.

## Examples

### Minimal Valid Document

```markdown
---
id: example-doc
title: Example Document
doc_type: guide
level: reference
status: draft
owners:
  - "@kentonium3"
last_updated: 2024-10-29
revision: v1.0
audience: agents_and_humans
---

# Example Document

Document content here.
```

### Full Featured Document

```markdown
---
id: advanced-example
title: Advanced Example with All Fields
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
  - "@agent-chatgpt"
last_updated: 2024-10-29
revision: v2.1
audience: agents_and_humans
tags:
  - examples
  - best-practices
  - canon-v2
aliases:
  - advanced-guide
  - example-full
links:
  - docs/standards/doc-standards.md
  - docs/_templates/handbook.md
---

# Advanced Example

Document content here with full frontmatter.
```

## Enforcement

Non-compliant documentation will:
1. Fail local validation (`validate_docs.py`)
2. Block PR merges via CI
3. Be flagged in automated audits

All new documentation MUST be Canon v2 compliant. Existing Canon v1 documentation will be migrated separately.

## Questions & Support

- **Schema**: See `docs/standards/frontmatter.schema.json`
- **Allowed Values**: See `docs/standards/allowed-values.json`
- **Templates**: See `docs/_templates/`
- **Validator Source**: See `tooling/scripts/validate_docs.py`
- **Issues**: Create GitHub issue with `documentation` label