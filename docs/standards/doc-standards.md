---
id: doc-standards
doc_type: reference
owner: kent
status: active
last_updated: 2025-10-25
tags: [documentation, standards, reference]
---

# Documentation Standards

This document defines the enforced standards for all markdown documentation in the `docs/` directory. These standards are validated by CI and should be followed when creating or modifying documentation files.

---

## Table of Contents

1. [Front-Matter Requirements](<#front-matter-requirements>)
2. [YAML Formatting Rules](<#yaml-formatting-rules>)
3. [Markdown Formatting Rules](<#markdown-formatting-rules>)
4. [File Organization](<#file-organization>)
5. [Template Usage](<#template-usage>)
6. [Examples](<#examples>)

---

## Front-Matter Requirements

### Required Fields

Every markdown file in `docs/` **must** include YAML front-matter with these fields:

| Field | Type | Format | Description | Example |
|-------|------|--------|-------------|---------|
| `id` | string | kebab-case | Unique identifier derived from filename | `project-plan` |
| `doc_type` | string | predefined values | Document category | `strategy`, `project`, `note` |
| `owner` | string | lowercase | Document owner/maintainer | `kent` |
| `status` | string | predefined values | Document lifecycle status | `draft`, `active`, `archived` |
| `last_updated` | date | ISO 8601 (YYYY-MM-DD) | Last modification date | `2025-10-25` |

### Optional Fields

| Field | Type | Format | Description | Example |
|-------|------|--------|-------------|---------|
| `tags` | array | single-line | Topic/category tags | `[strategy, planning]` |
| `aliases` | array | single-line | Alternative names | `[alt-name]` |

### Valid Values

**doc_type:**

- `strategy` - Strategic plans and initiatives
- `project` - Project plans and deliverables
- `note` - General notes and documentation
- `reference` - Reference materials and standards

**status:**

- `draft` - Work in progress
- `active` - Current and maintained
- `archived` - Historical/deprecated

---

## YAML Formatting Rules

### Structure Requirements

1. **Delimiters:** Front-matter must start and end with `---`
2. **Position:** Must be at the very beginning of the file (first line)
3. **Blank Line:** Must have one blank line after closing `---`

### Key Ordering

Keys should appear in this priority order:

```yaml
id: document-id
doc_type: note
owner: kent
status: draft
last_updated: 2025-10-25
tags: []
aliases: []
[...other keys in alphabetical order]
```

### Array Formatting

**Use single-line format:**

```yaml
tags: [strategy, planning, intentional]
aliases: [alt-name, other-name]
```

**Not multi-line:**

```yaml
# ❌ Don't use this format
tags:
  - strategy
  - planning
```

### Special Characters

Values with special characters must be quoted:

```yaml
title: "Project: Phase 1"  # ✅ Quoted because of colon
description: "Company's vision"  # ✅ Quoted because of apostrophe
```

### Compact Formatting

**No blank lines between keys:**

```yaml
---
id: my-doc
doc_type: note
owner: kent
status: draft
---
```

**Not:**

```yaml
---
id: my-doc

doc_type: note

owner: kent
---
```

---

## Markdown Formatting Rules

### Headings

**Requirements:**

- Use ATX-style headings (`#`, `##`, etc.)
- Headings must be surrounded by blank lines (one above, one below)
- No trailing punctuation in headings (`.`, `:`, `!`)
- Heading levels should increment by one (no skipping from `#` to `###`)

**Example:**

```markdown
## Section Title

Content goes here.

### Subsection

More content.
```

**Not:**

```markdown
## Section Title
Content immediately after (missing blank line)

### Subsection.
Content with trailing period in heading.
```

### Lists

**Requirements:**

- Lists must be surrounded by blank lines (one before, one after)
- Use consistent markers within the same list
- One space after list marker

**Unordered lists:**

```markdown
Some paragraph before.

- First item
- Second item
- Third item

Next paragraph after.
```

**Ordered lists:**

```markdown
Instructions:

1. First step
2. Second step
3. Third step

Continue with text.
```

### Code Blocks

**Requirements:**

- Fenced code blocks must be surrounded by blank lines
- Specify language for syntax highlighting (when applicable)

**Example:**

```markdown
Here's an example:

\`\`\`yaml
id: example
doc_type: note
\`\`\`

The above shows front-matter.
```

### Tables

**Requirements:**

- Tables must be surrounded by blank lines
- Use proper markdown table syntax

**Example:**

```markdown
Summary of options:

| Option | Description |
|--------|-------------|
| A      | First choice |
| B      | Second choice |

Next section.
```

### Blockquotes

**Requirements:**

- Blockquotes must be surrounded by blank lines
- Use `>` (with space) for blockquote markers

**Example:**

```markdown
As the guide states:

> This is a quoted section
> that spans multiple lines.

Back to regular text.
```

### Line Endings

**Requirements:**

- Files must end with a single newline character
- No trailing spaces at end of lines (unless intentional line break)
- No multiple consecutive blank lines (max 1)

---

## File Organization

### Directory Structure

```text
docs/
├── _templates/          # Templater templates (excluded from validation)
│   ├── frontmatter_template.md
│   ├── strategy_doc_template.md
│   └── project_plan_template.md
├── [category]/          # Organized by topic
│   └── *.md            # Documentation files
└── _index.md           # Directory index/navigation
```

### Naming Conventions

### File Naming Policy

- **Kebab-case only** for files: `brand-identity-brief.md`, `brand-voice-and-tone.md`.
  Directories should also use kebab-case where possible.
- **Do not include version numbers in filenames.** Versioning is handled by:
  1. **Front-matter** (`status`, `last_updated`)
  2. **Git history** (diffs, tags, releases)
- **Avoid dates in filenames.** Use front-matter instead unless the document itself is a dated log.
- **Examples**
  - ✅ `brand-identity-brief.md`, `support-ops-maturity-model.md`
  - ❌ `branding_identity_brief_v1.md`, `support_ops_maturity_model_v2.md`, `2025-10-25-branding.md`

> Migration rule: new/renamed files must follow kebab-case; legacy underscores may be migrated opportunistically.

### Excluded Directories

These directories are excluded from validation:

- `docs/_templates/` - Templater syntax files
- `docs/.obsidian/` - Obsidian configuration

---

## Template Usage

### Available Templates

Located in `docs/_templates/`:

1. **frontmatter_template.md** - Generic note template
2. **strategy_doc_template.md** - Strategy document structure
3. **project_plan_template.md** - Project planning format

### Using Templates

**In Obsidian:**

1. Open command palette (Ctrl+P / Cmd+P)
2. Type: `Templater: Insert Template`
3. Select desired template

**Template variables:**

- `{{tp.file.title}}` - Auto-fills with filename
- `{{tp.date.now("YYYY-MM-DD")}}` - Auto-fills with current date

### Creating New Documents

**Recommended workflow:**

1. Create new `.md` file in appropriate directory
2. Insert template via Templater
3. Fill in content
4. Obsidian Linter will auto-format on save

---

## Examples

### Complete Document Example

```markdown
---
id: website-plan
doc_type: project
owner: kent
status: active
last_updated: 2025-10-25
tags: [web, planning, phase-1]
---

# Website Plan (Phase 1)

## Overview

This document outlines the Phase 1 website development plan.

## Objectives

- Create homepage with clear value proposition
- Establish brand presence
- Enable contact conversions

## Timeline

| Phase | Deliverable | Target Date |
|-------|-------------|-------------|
| 1     | Design mockups | 2025-11-01 |
| 2     | Development | 2025-11-15 |
| 3     | Launch | 2025-12-01 |

## Next Steps

- Finalize design direction
- Select technology stack
- Create content outline

## References

See also:
- [Brand Guidelines](brand/brand-voice-and-tone.md)
- [Copy Overview](copy/overview.md)
```

### Front-Matter Only Example

```markdown
---
id: quick-note
doc_type: note
owner: kent
status: draft
last_updated: 2025-10-25
tags: [meetings, decisions]
---

# Quick Note Title

Content here.
```

---

## Validation

### Automated Checks

**CI validates:**

1. Front-matter presence and required fields
2. `last_updated` is valid ISO date (YYYY-MM-DD)
3. Markdown formatting (via markdownlint-cli2)

**Local validation:**

```bash
# Front-matter validation
python scripts/validate_docs.py

# Markdown linting
npx markdownlint-cli2

# Auto-fix formatting issues
npx markdownlint-cli2 --fix
```

### Obsidian Linter

If using Obsidian, the Linter plugin will automatically:

- Format front-matter with correct key order
- Add blank lines around headings, lists, tables
- Remove trailing spaces
- Ensure single newline at end of file
- Format arrays as single-line

**Trigger:** Automatic on file change

---

## Disabled Rules

These markdownlint rules are **disabled** to allow flexibility:

| Rule | Description | Reason |
|------|-------------|--------|
| MD013 | Line length limit | No strict line length enforced |
| MD033 | No inline HTML | HTML allowed for complex formatting |
| MD041 | First line heading | Front-matter comes first |
| MD003 | Heading style | ATX preferred but not strictly enforced |
| MD036 | No emphasis as heading | Allows emphasized dates/metadata |

---

## Common Mistakes

### ❌ Missing blank lines

```markdown
## Heading
Immediately followed by content (missing blank line).
```

### ✅ Correct

```markdown
## Heading

Content with proper spacing.
```

---

### ❌ Multi-line arrays

```markdown
---
tags:
  - strategy
  - planning
---
```

### ✅ Correct Format

```markdown
---
tags: [strategy, planning]
---
```

---

### ❌ No front-matter

```markdown
# My Document

Content without front-matter.
```

### ✅ With Front-Matter

```markdown
---
id: my-document
doc_type: note
owner: kent
status: draft
last_updated: 2025-10-25
---

# My Document

Content with proper front-matter.
```

---

## Tools Reference

### Scripts

- `scripts/validate_docs.py` - Front-matter validation
- `scripts/test-linters.ps1` - Linter comparison (PowerShell)
- `scripts/test-linters.sh` - Linter comparison (Bash)

### Configuration Files

- `.markdownlint-cli2.yaml` - Markdown linting rules
- `.markdownlintignore` - Excluded paths
- `docs/.obsidian/plugins/obsidian-linter/data.json` - Obsidian Linter config

### CI Workflow

- `.github/workflows/docs-ci.yml` - Automated validation on PR

---

## Quick Checklist

When creating a new markdown document:

- [ ] Add complete front-matter with all required fields
- [ ] Use `last_updated: YYYY-MM-DD` format (today's date)
- [ ] Set appropriate `doc_type` (strategy/project/note/reference)
- [ ] Set `status` (draft/active/archived)
- [ ] Add blank line after front-matter closing `---`
- [ ] Surround headings with blank lines
- [ ] Surround lists with blank lines
- [ ] Surround code blocks/tables with blank lines
- [ ] End file with single newline
- [ ] No trailing spaces on lines
- [ ] Run `npx markdownlint-cli2 --fix` before committing

---

## Getting Help

**Automatic formatting:**

- Use Obsidian Linter (auto-formats on file change)
- Run `npx markdownlint-cli2 --fix` to auto-fix issues

**Documentation:**

- See `LINTER_ALIGNMENT_REPORT.md` for detailed linter setup
- See `LINTER_COMPLETION_REPORT.md` for configuration details

**Testing:**

- Run `scripts/test-linters.ps1` to compare local vs CI checks
- Check `linter-reports/` for detailed violation reports
