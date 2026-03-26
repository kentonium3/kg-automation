---
id: ai-context-bootstrap
title: AI Context Bootstrap — READ FIRST
doc_type: handbook
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-11-01
last_updated: '2025-11-01'
revision: v1.0
audience: agents_and_humans
---
# AI Context Bootstrap — READ FIRST

> **Canonical guidance for all AIs (ChatGPT, Claude, Claude Code, Gemini, Copilot, etc.) working on _kg-automation_.**

## AI-Specific Instructions
Each AI system should read their specific instruction file after this bootstrap:

- **GitHub Copilot:** `ai-agents/copilot-instructions.md` — Copilot-specific workflow and repository guidance
- **Claude Code:** `ai-agents/claude-code-instructions.md` — Code execution and repository modification procedures
- **Claude:** `ai-agents/claude-instructions.md` — Strategic planning and architecture guidance
- **ChatGPT:** `ai-agents/chatgpt-instructions.md` — Task processing and code generation guidance
- **Gemini:** `ai-agents/gemini-instructions.md` — Repository interaction and workflow procedures

## AI-Specific Instructions
Each AI system should read their specific instruction file after this bootstrap:

- **GitHub Copilot:** `ai-agents/copilot-instructions.md` — Copilot-specific workflow and repository guidance
- **Claude Code:** `ai-agents/claude-code-instructions.md` — Code execution and repository modification procedures
- **Claude:** `ai-agents/claude-instructions.md` — Strategic planning and architecture guidance
- **ChatGPT:** `ai-agents/chatgpt-instructions.md` — Task processing and code generation guidance
- **Gemini:** `ai-agents/gemini-instructions.md` — Repository interaction and workflow procedures

## Operate GitHub-first
- **System of record:** GitHub `kentonium3/kg-automation`.
- **Read context** from Dropbox if available; **never edit** in Dropbox.
- **Edit/generate** only in Git branches or dev container.
- **Use Handoff Runner** for file creation/edits via JSON requests in `ai-agents/shared/handoffs/`.

## Start here (navigation)
- **Visual Docs Index:** `docs/README.md`
- **Diagrams:** `docs/diagrams/`
- **Handbooks:** `docs/handbooks/`

## Handoff Runner — quick start
1) Create a feature branch.
2) Add `*-chatgpt-to-handoff-runner-request.json` under `ai-agents/shared/handoffs/`.
3) Run **Actions → Handoff Runner** on that branch.
4) Open PR → Docs CI (`Docs CI / validate (pull_request)`) must pass → merge.

**Guards:** runner won’t run on `main`; it never edits `.github/workflows/**`.
