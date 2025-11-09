---
id: claude-code-instructions
title: Claude Code Instructions
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2025-11-01'
revision: v1.0
audience: agents_and_humans
---
# Claude Code Instructions — kg-automation

These instructions provide Claude Code-specific guidance for working in the kg-automation repository.

## Core Responsibilities
- Direct code execution and file modifications
- Repository operations and Git workflows
- Script execution and validation
- Automated testing and deployment
- Command-line operations and tooling

## Workflow Rules
1. **Always read first:**
   - `ai-agents/ai-context-bootstrap.md` at the start of each session
   - `CLAUDE.md` for repository-specific instructions and permissions
   - Check current branch and Git status

2. **File Operations:**
   - Use Read tool before editing any existing file
   - Prefer Edit tool over Write for existing files
   - Follow conventional commit format (docs:, feat:, fix:, chore:, etc.)
   - Never commit directly to main — always use feature branches

3. **Git Workflow:**
   - Create feature branches following pattern: `feature/`, `fix/`, `docs/`, `ci/`
   - Run validation scripts before committing
   - Create PRs with comprehensive descriptions
   - Include CI validation status in PR body

4. **Command Execution:**
   - Use Bash tool for terminal operations (git, npm, python, etc.)
   - Use specialized tools for file operations (Read, Edit, Write, Glob, Grep)
   - Validate command outputs and handle errors appropriately
   - Document all automated actions clearly

## Repository-Specific Guidelines
- **Allowed write locations:** `docs/`, `ai-agents/`, `systems/`, `runbooks/`, `workflows/`
- **Restricted:** Never edit `.env` files or commit secrets
- **Generated files:** Never edit `*_registry.yaml`, `.docgraph/*`
- **CI configuration:** Requires review before modifications

## Handoff Processing
When processing handoff requests:
1. Validate handoff JSON schema
2. Checkout target branch before making edits
3. Run validation scripts after file operations
4. Create response JSON with complete status
5. Use conventional commit format with handoff prefix

## Validation & Testing
- Run `python tooling/scripts/validate_docs.py` after doc changes
- Run `python tooling/scripts/sync_mermaid_views.py --write` for diagrams
- Execute preset workflows via `doc-hygiene` preset
- Verify CI passes before merging PRs

## Tool Usage Patterns
- **Glob:** Find files by pattern (`**/*.md`, `docs/**/*.json`)
- **Grep:** Search code content with regex
- **Read:** Read file contents (always before Edit/Write)
- **Edit:** Exact string replacement in existing files
- **Write:** Create new files or overwrite (requires prior Read)
- **Bash:** Terminal commands (git, validation scripts, npm, etc.)

## Safety & Permissions
- Never run destructive git commands without user confirmation
- Never force push to main/master
- Never skip git hooks (--no-verify) without explicit request
- Always validate before committing
- Clear documentation of all automated actions
- Respect repository governance and access controls

## Preset Commands
- **doc-hygiene:** Sync diagrams, validate docs, commit/push changes
  - Usage in handoff: `{"op": "preset", "name": "doc-hygiene"}`
  - Manual: Run sync, validate, commit, push sequence
