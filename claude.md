---
id: claude
title: Claude Code Repository Guide
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_validated: 2025-10-18
last_updated: '2025-10-29'
revision: v1.0
audience: agents_and_humans
---


# kg-automation Project Context

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

## Handoff Processing Rules
When processing AI handoffs:
1. Validate handoff JSON schema before starting
2. Checkout target branch before making edits
3. Run validation scripts after creating/updating files
4. Create response JSON with complete status information
5. Use conventional commit format (docs:, ci:, feat:, fix:, handoff:)

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
