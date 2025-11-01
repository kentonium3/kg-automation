---
id: copilot-instructions
title: GitHub Copilot Instructions
doc_type: handbook
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-10-17
last_updated: '2025-10-29'
revision: v1.1
audience: agents_and_humans
---
# GitHub Copilot instructions — kg-automation

These instructions are a concise, actionable guide for AI coding agents working in this repository. Read the short "PRIMERS" below before making edits.

## Must-read context (start here)
- `ai-agents/ai-context-bootstrap.md` — READ FIRST in every session. Contains canonical platform paths and read-vs-edit rules.
- `ai-agents/README.md` and `ai-exchange-bootstrap/docs/governance/ai-exchange.md` — protocol for AI↔AI handoffs.
- **Visual navigation:** Start with `docs/README.md` and `docs/diagrams/` for system overview.

## Repository & Branch Rules
- Primary branch: `main` (protected)
- Work branches: Use `feature/`, `fix/`, `docs/`, `ci/`, or `handoff/` prefix
- All changes require PR review
- CI/CD: GitHub Actions validates PRs and docs

## Handoff & Processing Rules
1. **Format:** `YYYYMMDD-HHMMSS-<handoff-id>-<from>-to-<to>-<type>.json`
   - Example: `20251012-123501-0001-chatgpt-to-claude-request.json`
2. **Schema Validation:** Always validate handoff JSON before processing
3. **Branch Strategy:** Checkout target branch before making edits
4. **Commit Messages:**
   - Request: `handoff: request <id> <from>→<to> – <purpose>`
   - Response: `handoff: response <id> <status> – <summary>`

## Development & Deployment Flow
1. Create feature branch from main
2. Make changes (use VS Code tasks where possible)
3. Run validation: `python tooling/scripts/validate_docs.py`
4. Push and create PR
5. After merge, deploy to Dropbox:
   ```powershell
   ./deploy-to-dropbox.ps1
   ```

## File & Documentation Standards
- **Documentation:** Follow Canon v2 standards defined in `docs/standards/doc-standards.md`
- **Validation:** Run `python tooling/scripts/validate_docs.py` before commits
- **Contracts:** Version controlled in `contracts/` directory
- **Runtime State:** Managed in Dropbox Automation roots (NEVER edit directly)

## Safety & Permissions
### Allowed:
- Read any repository file
- Write to `docs/`, `ai-agents/`, `systems/`, `runbooks/`, `workflows/`
- Execute scripts in `tooling/scripts/`
- Create/update markdown and JSON files

### Never:
- Edit files directly in Dropbox
- Commit secrets (use `secrets:<alias>` references)
- Modify CI configuration without review
- Edit generated files (`*_registry.yaml`, `.docgraph/*`)

## Quick References
- **Visual Index:** `docs/README.md`
- **Handoffs:** `ai-agents/shared/handoffs/`
- **Templates:** `scripts/templates/`
- **Deploy Scripts:** `deploy-to-dropbox.ps1`, `deploy_eci_framework.ps1`

Need more examples or clarification? Let me know which section to expand.
