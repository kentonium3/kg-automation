---
title: Codex Context — kg-automation
doc_type: reference
status: approved
audience: agents_and_humans
owners: [kgale]
last_validated: '2026-06-05'
last_updated: '2026-06-05'
---

# Codex Context — kg-automation

This file is the Codex adapter for kg-automation. `CLAUDE.md` remains the
authoritative project context; read it before beginning feature, bug, infra,
deployment, or Spec Kitty work.

## Startup

1. Read `CLAUDE.md` first.
2. Read `AGENTS.md` for cross-agent operating guidance.
3. For large codebase navigation, follow
   `.agents/skills/agent-analyzer-token-hygiene/SKILL.md`.
4. Treat the GitHub issue queue as the authoritative backlog.

## Spec Kitty Workflow

- Before starting a mission, verify the issue has `spec: ready` and read the
  full issue body.
- Drive the workflow in this order unless the current Spec Kitty command file
  says otherwise: specify -> plan -> tasks -> implement/review -> merge.
- Before each step, read the matching command file from
  `~/.claude/commands/` fresh. These files are the canonical workflow
  runbooks and may change between sessions.
- When available and appropriate, prefer the optional implement-review command
  path that combines implementation and review orchestration.
- Do not manually edit `kitty-specs/` or `.kittify/`; those paths are owned by
  Spec Kitty. Reading them for context is allowed.
- After merge, close the GitHub issue and comment with the merge commit hash
  and relevant notes.

## Change Control

- Classify system changes by the Tier 0-4 taxonomy before acting. Canonical
  source: `docs/design/architecture/data/change-risk-taxonomy.json`.
- Tier 0 is operator-only. Generate commands for Kent to run; do not execute.
- Tier 1 requires connectivity/dependency verification before and after.
- Tier 2 requires recent backup/snapshot confirmation and the defined approval
  and verification gates.
- Tier 3 uses normal implementation discipline: dry-run, tests, and smoke
  checks where available.
- Tier 4 docs/metadata changes may proceed with normal validation.

## Codex Mechanics

- Use `rg`/bounded reads for exploration and avoid noisy shell output.
- Use `apply_patch` for manual file edits.
- Preserve unrelated worktree changes; never revert user or generated changes
  unless Kent explicitly asks.
- Do not use destructive git or filesystem commands without explicit approval.
- If a command needs sudo, Tier 0 authority, or `ssh office2-kgale`, stop and
  give Kent the command to run.
- Use `ssh office2-claude` for approved office2 agent access.

## Documentation And Architecture

- Architecture JSON in `docs/design/architecture/data/` is authoritative.
- When work changes deployed services, credentials, data flows, network
  topology, runbooks, or systemd units, consult
  `docs/design/architecture/data/signal-to-doc-map.json` and update the
  relevant docs in the same mission.
- If work deploys, modifies, or registers an OpenClaw agent, read
  `docs/runbooks/openclaw-agent-setup.md` before planning deployment.
- Never read, write, reference, or log
  `~/second-brain/notes/04-Growth/_private/`.

## Validation

- Run focused tests for changed code.
- Run `python tooling/scripts/validate_docs.py` after documentation changes.
- Report any tests or validations that could not be run.
