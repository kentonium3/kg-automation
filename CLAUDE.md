---
title: Claude Code Context — kg-automation
doc_type: reference
status: approved
---

# kg-automation — Claude Code Context

This file is read automatically by Claude Code at session start.
Read this first. Read nothing else until this is complete.

## What This System Is

kg-automation is Kent Gale's personal AI operating system — an always-on
accountability and automation infrastructure built on office2 (Ubuntu 24.04 LTS,
Tailscale-accessible) with OpenClaw as the orchestration engine and Vikunja as
the task store and UI layer.

This is not a general-purpose automation repo. It is a personal system with a
specific architecture. Read `docs/design/personal-ai-system-spec-v03.md` before
making any architectural decisions. That document is the source of truth.

## Platform

| Component | Role |
|---|---|
| MacBook Pro | Primary authoring and interaction |
| office2 (Ubuntu 24.04 LTS) | Always-on hub — OpenClaw, Vikunja, inbox processor |
| iPhone | Mobile capture (Wispr Flow) and task monitoring (Vikunja web UI) |
| GitHub | Version control, all agent changes via PR |
| Obsidian Sync | Vault sync across all devices including office2 |

## Server Access (office2)

| Connection | Command |
|---|---|
| SSH as kgale | `ssh office2-kgale` |
| SSH as claude | `ssh office2-claude` |

- **Local IP**: 192.168.1.158
- **Tailscale IP**: 100.92.197.90
- **Data drive**: `/data` (2.7TB)
- SSH host aliases are defined in `~/.ssh/config` on the Mac

**Windows is not a supported platform. Ignore any references to it.**
**Dropbox is not used for coordination. Ignore any references to it.**
**ChatGPT handoff JSON protocols are deprecated. Do not use them.**

## Canonical Design Document

`docs/design/personal-ai-system-spec-v03.md` — read this for:
- Full system architecture and topology
- Two input paths (WhatsApp and Obsidian inbox)
- Vikunja as task store and UI layer
- OpenClaw as orchestration engine
- Skill inventory and migration status
- Implementation phases and feature sequence
- Security requirements
- Operating principles

## Repository Structure

```
ai-agents/          ← agent instruction files (this file's siblings)
docs/
  design/           ← architecture specs (start here)
  func-spec/        ← feature specs (spec-kitty output)
  handbooks/        ← operational runbooks
  standards/        ← doc standards
scripts/            ← automation scripts
systems/            ← capability definitions
workflows/          ← defined workflows
```

## Git Workflow

- Never commit directly to main
- Branch pattern: `feature/`, `fix/`, `docs/`, `ci/`
- PR required for all changes
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`

## Permissions

**Write allowed**: `docs/`, `ai-agents/`, `systems/`, `scripts/`, `workflows/`
**Never**: edit `.env` files, commit secrets, force push, `rm -rf`
**CI**: never modify `.github/workflows/` without explicit instruction

## Second Brain Boundary

The second brain lives at `~/second-brain/` (separate repo: kentonium3/second-brain).
This repo (kg-automation) contains the system that acts on the second brain.
Do not conflate them. Do not write to second-brain paths from kg-automation tasks
unless explicitly instructed.

**Absolute rule**: `~/second-brain/vault/Notes/02-Growth/_private/` is never
read, written, referenced, or logged by any agent or script under any circumstance.
