---
id: GOV-AI-EXCHANGE
title: Governance: AI↔AI Exchange via GitHub
doc_type: governance
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-10-12
revision: 1.0
---

# Scope
Defines the protocol and directory layout for AI-to-AI collaboration mediated by GitHub.

# Rules
- Always pull before work; push small, reviewable commits.
- Use the handoff schema in `ai-agents/shared/contracts/ai-handoff.schema.json`.
- Handoff files live under `ai-agents/shared/handoffs/` with canonical filenames.
- Responses must reference outputs and (when applicable) PR URLs.
- No secrets in this repo; use references (e.g., `secrets:<alias>`).

# Operational Notes
- When either worker is degraded, set a pause flag and document next steps.
- ADRs record any protocol changes; update this doc’s revision when changed.
