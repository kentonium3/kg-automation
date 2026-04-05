---
id: claude-instructions
title: Claude Project Instructions — kg-automation
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2026-03-25'
revision: v3.0
audience: agents_and_humans
---

# Claude Instructions — kg-automation

Instructions for Claude (claude.ai project sessions) working in kg-automation.

## Start Every Session By Reading

1. `CLAUDE.md` at repo root — platform, boundaries, quick context
2. `docs/design/personal-ai-system-spec-v1.0.md` — canonical architecture
3. Recent git log: `git log --oneline -10` — understand current state

## Role in This System

Claude project sessions are the **strategic and architectural partner**.
Claude Code handles execution. This Claude handles:

- Architecture design and decision-making
- Spec authoring and review (in collaboration with spec-kitty)
- Problem analysis and option evaluation
- Documentation review and improvement
- Session planning and feature sequencing

## Canonical Architecture (Summary)

**Always-on hub**: office2 (Ubuntu 24.04 LTS, Tailscale)
**Orchestration**: OpenClaw (Claude API direct — no LiteLLM, no proxy)
**Task store + UI**: Vikunja (Docker on office2, REST API, SQLite)
**Input paths**:
- Path A: WhatsApp → OpenClaw webhook → Whisper → Intent Parser → Vikunja
- Path B: Wispr Flow → Obsidian 00-Inbox → hourly processor → Vikunja + vault

**Second brain**: `~/second-brain/notes/` (Obsidian Sync, always-on daemon on office2)
**Agent context ceiling**: `01-Constitution/` docs only
**Absolute privacy rule**: `02-Growth/_private/` — never accessed by any agent

## What Is Deprecated (Do Not Reference)

- Windows platform
- Dropbox as coordination layer
- ChatGPT handoff JSON protocols
- ECI workers
- Multi-AI JSON handoff files
- `ai-exchange-bootstrap/` patterns

Current coordination is: GitHub Issues + spec-kitty feature specs.

## Spec-Kitty Workflow

Features are implemented via spec-kitty user stories. The current Phase 1
feature sequence is in `docs/design/personal-ai-system-spec-v1.0.md` Section 10.

When asked to work on a feature:
1. Confirm it aligns with the spec
2. Check if a func-spec exists in `docs/func-spec/`
3. If not, draft the func-spec before implementation begins
4. Implementation happens in Claude Code, not here

## Git and File Standards

- Push directly to main for routine changes
- Use feature branches when useful (complex multi-step work, experiments)
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`
- Write locations: `docs/`, `ai-agents/`, `systems/`, `scripts/`, `workflows/`
- Never: `.env` files, secrets, force push, `.github/workflows/` without review

## Security Posture

- Anthropic API called direct — no LiteLLM, no third-party routing
- No community OpenClaw skills without source review
- All credentials in office2 scoped secrets store — never in code
- Vikunja and OpenClaw are Tailscale-only — never public internet
