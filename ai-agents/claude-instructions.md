---
id: claude-instructions
title: Claude Instructions
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2025-11-01'
revision: v1.0
audience: agents_and_humans
---
# Claude Instructions — kg-automation

These instructions provide Claude-specific guidance for working in the kg-automation repository.

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

## Handoff Specifics
- **Filename convention:** `YYYYMMDD-HHMMSS-<id>-claude-to-<target>-<type>.json`
- **Required elements:**
  - Complete context about the task
  - Clear next actions for recipient
  - References to source files and documentation
  - Status information and validation results

## Strategic Focus
- System architecture and design patterns
- Multi-AI coordination strategies
- Documentation standards and governance
- Process optimization and automation
- Quality assurance and validation

## Safety & Validation
- No direct edits to `.github/workflows/` without review
- Run local validators before pushing changes
- Clear documentation of all automated actions
- Respect repository governance and access controls
- Preserve existing file structure and conventions
