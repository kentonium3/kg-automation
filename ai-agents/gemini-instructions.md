---
id: gemini-instructions
title: Gemini Instructions
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2025-11-01'
revision: v1.0
audience: agents_and_humans
---
# Gemini Instructions — kg-automation

These instructions provide Gemini-specific guidance for working in the kg-automation repository.

## Core Responsibilities
- Code generation and review
- Documentation assistance
- System architecture and analysis
- AI handoff processing

## Workflow Rules
1. **Initial Context:**
   - Start with `ai-agents/ai-context-bootstrap.md` in every session
   - Review relevant directory contents before making changes

2. **File Operations:**
   - Only modify files through Git operations
   - Follow Canon v2 standards (`docs/standards/doc-standards.md`)
   - Use provided templates from `docs/_templates/`

3. **Coordination:**
   - Follow handoff protocols from `ai-exchange-bootstrap/docs/governance/ai-exchange.md`
   - Honor file locks and coordination mechanisms
   - Maintain clear communication about actions and state changes

4. **Quality Assurance:**
   - Validate against Canon v2 documentation standards
   - Run local validation scripts before committing
   - Ensure complete context in pull requests

## Handoff Protocol
- Use filename format: `YYYYMMDD-HHMMSS-<id>-gemini-to-<target>-<type>.json`
- Include comprehensive context and next steps
- List affected files and planned changes

## Safety Guidelines
- No modifications to `.github/workflows/`
- Execute local validation before pushes
- Document all automated operations
- Follow repository governance rules
