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
specific architecture. Read `docs/design/personal-ai-system-spec-v1.0.md` before
making any architectural decisions. That document is the source of truth.

## Platform

| Component | Role |
|---|---|
| MacBook Pro | Primary authoring and interaction |
| office2 (Ubuntu 24.04 LTS) | Always-on hub — OpenClaw, Vikunja, inbox processor |
| iPhone | Mobile capture (Wispr Flow) and task monitoring (Vikunja web UI) |
| GitHub | Version control, CI validation on push |
| Obsidian Sync | Vault sync across all devices including office2 |

## Server Access (office2)

| Connection | Command |
|---|---|
| SSH as claude | `ssh office2-claude` |

- **Local IP**: 192.168.1.158
- **Tailscale IP**: 100.92.197.90
- **Data drive**: `/data` (2.7TB)
- SSH host aliases are defined in `~/.ssh/config` on the Mac

**Agents must always use `ssh office2-claude` — never `ssh office2-kgale`.
The kgale account is for human use only. Agent actions must be traceable
to the claude user.**

**The claude user does not have sudo access. If a command requires sudo,
stop and present the command to Kent to run manually via `ssh office2-kgale`.**

**Windows is not a supported platform. Ignore any references to it.**
**Dropbox is not used for coordination. Ignore any references to it.**
**ChatGPT handoff JSON protocols are deprecated. Do not use them.**

## Architecture Documentation

**Documentation map**: [`docs/INDEX.md`](docs/INDEX.md) — master index of all active documentation, grouped by directory with Divio type annotations. Start here to discover docs by topic or type.

**Governance**: [`docs/constitution/FELIX-CONSTITUTION.md`](docs/constitution/FELIX-CONSTITUTION.md) — top-level governance, autonomy levels, principles. See also [`docs/constitution/AGENT-REGISTRY.md`](docs/constitution/AGENT-REGISTRY.md).

**Machine-readable operational state**: `docs/design/architecture/data/` is the canonical home for JSON artifacts (service inventory, topology, credentials, data-flows, schemas). Exempt from moves.

`docs/design/architecture/` — current-state system documentation:
- Hardware, network, and service inventory (with machine-readable JSON in `data/`)
- Data flows, credentials, identity model, backup, security posture
- **Updated after every feature** — see `change-control.md` for the protocol

`docs/design/personal-ai-system-spec-v1.0.md` — design intent (what we're building toward):
- Full system architecture and topology
- Implementation phases and feature sequence
- Operating principles

**Standing requirement**: Any feature that changes deployed services, credentials,
data flows, or network topology must update the relevant files in
`docs/design/architecture/` and `docs/design/architecture/data/`.

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

## Feature Development Workflow

All features are implemented through spec-kitty. Always follow this sequence:

```
/spec-kitty.specify → /spec-kitty.plan → /spec-kitty.tasks → /spec-kitty.implement → /spec-kitty.review → /spec-kitty.merge
```

Do not skip steps. Do not perform research, write code, or make design decisions
outside of the spec-kitty workflow. If a spec-kitty command fails, stop and report
the error — do not work around it manually.

See `docs/func-spec/claude-pre-implementation-prompt.md` for the standing
orchestration directive.

## Git Workflow

- Push directly to main for routine changes
- Use feature branches when useful (complex multi-step work, experiments)
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`
- CI validates on every push to main

## Permissions

**Write allowed**: `docs/`, `ai-agents/`, `systems/`, `scripts/`, `workflows/`
**Never**: edit `.env` files, commit secrets, force push, `rm -rf`
**CI**: never modify `.github/workflows/` without explicit instruction

## Architecture Documentation

The system maintains a live architecture documentation store at
`docs/design/architecture/`. JSON files are the authoritative record;
markdown files are narrative views.

**Standing directive**: Any implementation that deploys, modifies, or removes
a service, credential, port, or data flow MUST update the relevant files in
`docs/design/architecture/data/` and their markdown counterparts as part of
the same PR. This is not optional and not a separate task.

See `docs/design/architecture/change-control.md` for the full update protocol.

## Second Brain Boundary

The second brain lives at `~/second-brain/` (separate repo: kentonium3/second-brain).
This repo (kg-automation) contains the system that acts on the second brain.
Do not conflate them. Do not write to second-brain paths from kg-automation tasks
unless explicitly instructed.

**Absolute rule**: `~/second-brain/notes/02-Growth/_private/` is never
read, written, referenced, or logged by any agent or script under any circumstance.
