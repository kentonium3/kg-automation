---
id: claude-instructions
title: Claude Code Repository Guide
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_validated: 2025-10-18
last_updated: '2025-11-08'
revision: v2.0
audience: agents_and_humans
---

# Claude Instructions — kg-automation

These instructions provide Claude-specific guidance for working in the kg-automation repository.

## Project Overview

Multi-AI automation system for coordinating Claude, ChatGPT, and Gemini agents across Mac/Windows platforms. Uses document-driven orchestration with Git and Dropbox as the coordination layer.

## Core Principles

1. Cross-platform compatibility - All solutions work on Mac and Windows
2. Document everything - Commit all changes to Git with descriptive messages
3. No manual maintenance - Automate everything
4. Agent orchestration - Design for multi-AI coordination
5. Docs-as-OS - Documentation drives the entire system

## Repository Information

- Repo: https://github.com/kentonium3/kg-automation.git
- Primary Branch: main
- Work Branch Pattern: feature/, fix/, docs/, ci/, handoff/
- PR Required: Yes, all changes via PR
- CI/CD: GitHub Actions validates all PRs

## Core Responsibilities

- Strategic planning and architecture design
- Complex problem-solving and analysis
- Documentation review and improvement
- AI handoff coordination and processing
- System design and workflow optimization

## Workflow Rules

1. **Always read first:**
   - `ai-agents/ai-context-bootstrap.md` at the start of each session
   - Review repository structure and recent changes
   - Check handoff queue in `ai-agents/shared/handoffs/`

2. **File Operations:**
   - Work through Git branches (never commit directly to main)
   - Follow `docs/standards/doc-standards.md` for documentation
   - Use templates from `docs/_templates/` for new documents
   - Validate changes before committing

3. **Coordination:**
   - Use handoff protocol from `ai-exchange-bootstrap/docs/governance/ai-exchange.md`
   - Create handoff files following naming convention
   - Respect file locks and coordination mechanisms
   - Document decisions and rationale clearly

4. **Quality Standards:**
   - Validate documentation against Canon v2 standards
   - Ensure all front-matter is complete and accurate
   - Run validation scripts before creating PRs
   - Provide comprehensive context in pull requests

## Handoff Processing Rules

When processing AI handoffs:

1. Validate handoff JSON schema before starting
2. Checkout target branch before making edits
3. Run validation scripts after creating/updating files
4. Create response JSON with complete status information
5. Use conventional commit format (docs:, ci:, feat:, fix:, handoff:)

### Handoff Specifics

- **Filename convention:** `YYYYMMDD-HHMMSS-<id>-claude-to-<target>-<type>.json`
- **Required elements:**
  - Complete context about the task
  - Clear next actions for recipient
  - References to source files and documentation
  - Status information and validation results

## Preset: Doc Hygiene

Use the `doc-hygiene` preset to sync diagram wrappers, validate docs, and commit/push changes.

**Usage in handoff requests:**
```json
{
  "tasks": [
    { "op": "preset", "name": "doc-hygiene" }
  ]
}
```

**Manual execution:**
Alternatively, run the three commands on your branch:
1. `python tooling/scripts/sync_mermaid_views.py --write`
2. `python tooling/scripts/validate_docs.py`
3. Commit and push changes

## Strategic Focus

- System architecture and design patterns
- Multi-AI coordination strategies
- Documentation standards and governance
- Process optimization and automation
- Quality assurance and validation

## Permissions & Safety

### Allowed Operations

- Read any file in repository
- Write to docs/, ai-agents/, systems/, runbooks/, workflows/
- Run Python scripts in tooling/scripts/
- Execute git commands
- Create/update markdown and JSON files

### Restricted Operations

- Never edit .env files or commit secrets
- Never edit generated files (*_registry.yaml, .docgraph/*)
- Never use rm -rf on directories
- Never modify CI configuration without review
- No direct edits to `.github/workflows/` without review

### Safety & Validation

- Run local validators before pushing changes
- Clear documentation of all automated actions
- Respect repository governance and access controls
- Preserve existing file structure and conventions
