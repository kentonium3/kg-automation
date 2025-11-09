<<<<<<< HEAD
---
id: copilot-instructions
title: GitHub Copilot Instructions
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2025-11-01'
revision: v1.0
audience: agents_and_humans
---
# GitHub Copilot instructions — kg-automation

These instructions are a concise, actionable guide for AI coding agents working in this repository. Read the short "PRIMERS" below before making edits.

## Must-read context (start here)
- `ai-agents/ai-context-bootstrap.md` — READ FIRST in every session. It contains canonical platform paths and the read-vs-edit rules.
- `ai-agents/README.md` and `ai-exchange-bootstrap/docs/governance/ai-exchange.md` — protocol for AI↔AI handoffs and commit conventions.

## Top-level rules (enforced workflow)
- Always pull-before-write: run `git pull --rebase` before any changes. Small, reviewable commits preferred.
- Edit in this Git repo (Vaults-repos/kg-automation). Do NOT edit files directly in Dropbox.
- No secrets in the repo. Use references (e.g., `secrets:<alias>`) and external vaults.
- Attribute authorship: commits should clearly identify the agent (name/email configured per-agent).

## Where runtime state and queues live
- Runtime queues, lock and state files live in Dropbox Automation roots (see `ai-agents/ai-context-bootstrap.md` for exact platform paths). Example runtime folder: `Dropbox\Automation\.queue` and `Dropbox\Automation\.state`.
- Handoff files are versioned under: `ai-agents/shared/handoffs/` (JSON). Follow filename pattern and schemas in `ai-exchange-bootstrap` docs.

## Handoff & commit conventions (examples)
- Handoff filename: `YYYYMMDD-HHMMSS-<handoff-id>-<from>-to-<to>-<type>.json`
  - Example: `20251012-123501-0001-chatgpt-to-claude-request.json`
- Commit messages for handoffs:
  - Request: `handoff: request <id> <from>→<to> – <purpose>`
  - Response: `handoff: response <id> <status> – <summary>`

## Typical dev -> deploy flow (Windows PowerShell example)

```bash
# Pull and commit changes
git pull --rebase
git add .
git commit -m "<concise, conventional message>"
git push origin main

# Deploy to Dropbox (sync runtime files)
bash ./deploy-to-dropbox.sh
```

VS Code has tasks already configured (see workspace Tasks):
- "Complete Deployment Workflow" (commits, pushes, then runs deploy-to-dropbox)
- "Quick Deploy (Skip Git)" (runs `deploy-to-dropbox.ps1` directly)

## ECI worker templates and execution
- Templates: `scripts/templates/eci_mac_claim_and_run.sh` and `scripts/templates/eci_win_Claim-And-Run.ps1`.
- These are templates only — do NOT run them in-place. Copy to the platform-specific location first (see `scripts/templates/README.md`).

## File and documentation conventions
- Filenames: kebab-case (lowercase with hyphens).
- Docs: Markdown with Mermaid diagrams where useful. `.vscode/settings.json` enforces Markdown preferences and line-wrap rules.
- Contracts/schemas: `contracts/` (versioned in repo). Runtime job queues live outside the repo in Dropbox.

## Safety & coordination
- Pull before processing shared/handoffs. If exclusive access is required, create a short-lived `.lock` file in the shared directory and remove it ASAP.
- If you update operational governance, update `ai-exchange-bootstrap/docs/governance/ai-exchange.md` revision and note the change in a small PR.

## Quick references (paths & examples)
- Read-first: `ai-agents/ai-context-bootstrap.md`
- Handoffs: `ai-agents/shared/handoffs/` (example JSON in `ai-agents/shared/handoffs/20251012-0712-0001-claude-to-chatgpt-response.json`)
- Templates: `scripts/templates/` (`eci_*` files)
- Deploy script: `deploy-to-dropbox.ps1` and `deploy_eci_framework.ps1`

If anything here is unclear or you need more examples (more commit/PR examples, schema references, or task-run samples), tell me which section to expand and I will iterate.
=======
---
id: copilot-instructions
title: GitHub Copilot Instructions
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2025-11-01'
revision: v1.0
audience: agents_and_humans
---
# GitHub Copilot instructions — kg-automation

These instructions are a concise, actionable guide for AI coding agents working in this repository. Read the short "PRIMERS" below before making edits.

## Must-read context (start here)
- `ai-agents/ai-context-bootstrap.md` — READ FIRST in every session. It contains canonical platform paths and the read-vs-edit rules.
- `ai-agents/README.md` and `ai-exchange-bootstrap/docs/governance/ai-exchange.md` — protocol for AI↔AI handoffs and commit conventions.

## Top-level rules (enforced workflow)
- Always pull-before-write: run `git pull --rebase` before any changes. Small, reviewable commits preferred.
- Edit in this Git repo (Vaults-repos/kg-automation). Do NOT edit files directly in Dropbox.
- No secrets in the repo. Use references (e.g., `secrets:<alias>`) and external vaults.
- Attribute authorship: commits should clearly identify the agent (name/email configured per-agent).

## Where runtime state and queues live
- Runtime queues, lock and state files live in Dropbox Automation roots (see `ai-agents/ai-context-bootstrap.md` for exact platform paths). Example runtime folder: `Dropbox\Automation\.queue` and `Dropbox\Automation\.state`.
- Handoff files are versioned under: `ai-agents/shared/handoffs/` (JSON). Follow filename pattern and schemas in `ai-exchange-bootstrap` docs.

## Handoff & commit conventions (examples)
- Handoff filename: `YYYYMMDD-HHMMSS-<handoff-id>-<from>-to-<to>-<type>.json`
  - Example: `20251012-123501-0001-chatgpt-to-claude-request.json`
- Commit messages for handoffs:
  - Request: `handoff: request <id> <from>→<to> – <purpose>`
  - Response: `handoff: response <id> <status> – <summary>`

## Typical dev -> deploy flow (Windows PowerShell example)

```bash
# Pull and commit changes
git pull --rebase
git add .
git commit -m "<concise, conventional message>"
git push origin main

# Deploy to Dropbox (sync runtime files)
bash ./deploy-to-dropbox.sh
```

VS Code has tasks already configured (see workspace Tasks):
- "Complete Deployment Workflow" (commits, pushes, then runs deploy-to-dropbox)
- "Quick Deploy (Skip Git)" (runs `deploy-to-dropbox.ps1` directly)

## ECI worker templates and execution
- Templates: `scripts/templates/eci_mac_claim_and_run.sh` and `scripts/templates/eci_win_Claim-And-Run.ps1`.
- These are templates only — do NOT run them in-place. Copy to the platform-specific location first (see `scripts/templates/README.md`).

## File and documentation conventions
- Filenames: kebab-case (lowercase with hyphens).
- Docs: Markdown with Mermaid diagrams where useful. `.vscode/settings.json` enforces Markdown preferences and line-wrap rules.
- Contracts/schemas: `contracts/` (versioned in repo). Runtime job queues live outside the repo in Dropbox.

## Safety & coordination
- Pull before processing shared/handoffs. If exclusive access is required, create a short-lived `.lock` file in the shared directory and remove it ASAP.
- If you update operational governance, update `ai-exchange-bootstrap/docs/governance/ai-exchange.md` revision and note the change in a small PR.

## Quick references (paths & examples)
- Read-first: `ai-agents/ai-context-bootstrap.md`
- Handoffs: `ai-agents/shared/handoffs/` (example JSON in `ai-agents/shared/handoffs/20251012-0712-0001-claude-to-chatgpt-response.json`)
- Templates: `scripts/templates/` (`eci_*` files)
- Deploy script: `deploy-to-dropbox.ps1` and `deploy_eci_framework.ps1`

If anything here is unclear or you need more examples (more commit/PR examples, schema references, or task-run samples), tell me which section to expand and I will iterate.
>>>>>>> feat/reorganize-ai-instructions
