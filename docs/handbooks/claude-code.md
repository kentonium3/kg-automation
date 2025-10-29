---
id: claude-code
title: Claude Code — Execution Agent
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: "2025-10-18"
revision: v1.0
audience: agents_and_humans
---

Claude Code acts as an autonomous **execution agent** for kg-automation: it reads handoffs, performs multi-step git/docs tasks, runs scripts, validates locally, and pushes PRs—always under repo governance.

## When to use
- Self-healing docs (front-matter, links)
- Multi-file structured edits, refactors
- Running local scripts/tests before committing

## Guardrails
- Never edits `.github/workflows/**`
- Works only on feature branches; opens PRs to `main`
- Respects `.claude/config.json` permissions

## Standard Plays
- **/process-handoff**: apply a request, validate, commit, push, respond
- **/docs-self-heal**: parse CI failure, fix front-matter/links, validate, push

See also: `docs/handbooks/agent-execution-roles.md`.