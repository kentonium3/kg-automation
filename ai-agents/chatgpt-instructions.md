---
id: chatgpt-instructions
title: ChatGPT Instructions
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2025-11-01'
revision: v1.0
audience: agents_and_humans
---
# ChatGPT Instructions — kg-automation

These instructions provide ChatGPT-specific guidance for working in the kg-automation repository.

## Core Responsibilities
- Generate and review code changes
- Assist with documentation and task planning
- Help with system architecture and problem-solving
- Process AI handoffs via established protocols

## Workflow Rules
1. **Always read first:**
   - `ai-agents/ai-context-bootstrap.md` at the start of each session
   - Review latest changes in relevant directories before modifications

2. **File Operations:**
   - Create/edit files only through Git operations
   - Follow `docs/standards/doc-standards.md` for all documentation
   - Use established templates from `docs/_templates/`

3. **Coordination:**
   - Use handoff protocol from `ai-exchange-bootstrap/docs/governance/ai-exchange.md`
   - Respect file locks and coordination mechanisms
   - Clear communication about state changes and actions taken

4. **Quality Standards:**
   - Validate documentation against Canon v2 standards
   - Run local validation before commits
   - Ensure PR readiness with complete context and explanations

## Handoff Specifics
- Follow filename convention: `YYYYMMDD-HHMMSS-<id>-chatgpt-to-<target>-<type>.json`
- Always include complete context and next actions
- Reference source files and planned modifications

## Safety & Validation
- No direct edits to `.github/workflows/`
- Run local validators before pushing changes
- Clear documentation of all automated actions
- Respect repository governance and access controls