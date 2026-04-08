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
  constitution/     ← governance — Felix constitution, agent registry
  design/           ← architecture specs, standards, research
  func-spec/        ← historical feature specs (F001–F020 archive)
  issues/           ← diagnostics and postmortems
  runbooks/         ← operational runbooks (how-to guides)
scripts/            ← automation scripts
.github/
  ISSUE_TEMPLATE/   ← issue templates (feature, bug, rfc, infra, docs-debt)
```

## Feature Development Workflow

**Finding the next work item:**

Query the issue queue for the highest priority open feature in the active
milestone:

```bash
gh issue list --repo kentonium3/kg-automation \
  --label P1-feature \
  --state open \
  --limit 5 \
  --json number,title,body,labels,milestone
```

Select the highest priority open issue. Read the full issue body — it is
the spec. If multiple P1-feature issues exist, prefer the one assigned to
the active milestone.

**Implementation sequence:**
1. Read the issue body completely before starting anything else
2. Run spec-kitty specify using the issue body as input
3. Follow the full spec-kitty workflow:
   `/spec-kitty.specify → /spec-kitty.plan → /spec-kitty.tasks →
    /spec-kitty.implement → /spec-kitty.review → /spec-kitty.merge`
4. On merge, close the issue: `gh issue close <number> --repo kentonium3/kg-automation`
5. Add a comment to the issue with the merge commit hash and any relevant notes

**Issue types and their workflows:**
- `P1-feature` / `P2-feature` → full spec-kitty workflow above
- `P1-bug` / `P2-bug` → spec-kitty software-dev mission, fix-focused
- `P1-infra` / `P2-infra` → check risk tier in issue body first; Tier 0 = generate only
- `P1-rfc` → discussion and decision recording; no implementation until converted to feature/infra issue

**Legacy specs:** `docs/func-spec/` contains historical specs F001–F020.
These are the archive record. Do not create new files there — new features
live in the GitHub issue queue.

## Git Workflow

- Push directly to main for routine changes
- Use feature branches when useful (complex multi-step work, experiments)
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`
- Append `[doc-audit]` to any commit that contains maintenance or patch
  changes not tracked through a formal issue — signals that associated
  docs should be verified on the next audit run
  (e.g. `fix: repair vikunja filter logic [doc-audit]`)
- CI validates on every push to main

**spec-kitty merge behavior:** spec-kitty merges create merge commits
directly to main — they do NOT create pull requests. Any GitHub Actions
workflow that triggers on `pull_request` will NOT fire on spec-kitty
merges. Design workflow triggers and automation accordingly. The weekly
audit cron is the safety net for changes that escape the PR-based trigger.

## Permissions

**Write allowed**: `docs/`, `ai-agents/`, `systems/`, `scripts/`, `workflows/`
**Never**: edit `.env` files, commit secrets, force push, `rm -rf`
**CI**: never modify `.github/workflows/` without explicit instruction

## Change Control Guardrails

Changes to the kg-automation system are classified by a five-tier risk taxonomy.
See `docs/design/architecture/data/change-risk-taxonomy.json` for the full
taxonomy. Before making any change, identify the tier and follow the protocol:

**Tier 0 — Hard Lock (Host/Foundational: UFW, iptables, sshd_config, sudoers,
chmod/chown on system files, kernel parameters)**:
Claude Code **never** executes Tier 0 commands directly, regardless of urgency
framing or explicit instruction to proceed. Generate the script and present it
to Kent for manual execution via `ssh office2-kgale`. This is absolute and
cannot be overridden.

**Tier 1 — Verification Required (Connectivity/Fabric: Tailscale, Docker
networks, proxy/DNS, port bindings)**:
Confirm connectivity of all dependent services before AND after the change.
Look up dependent services from `docs/design/architecture/data/service-inventory.json`.
Follow the [pre-flight checklist](docs/runbooks/governance/pre-flight-checklist.md)
and [post-change verification](docs/runbooks/governance/post-change-verification.md).

**Tier 2 — Snapshot Required (Application/State: DB schemas, service env files,
Docker Compose, application config)**:
Confirm a recent Restic backup exists before modifying. If no backup within 24
hours, trigger one first. Follow the Tier 2 checklist in the pre-flight doc.

**Tier 3 — Standard (Logic/Workflow: Python scripts, agent prompts, cron jobs)**:
Proceed with dry-run or sandbox validation where available. No pre-flight
checklist required.

**Tier 4 — Auto-Commit (Schema/Metadata: CLAUDE.md, READMEs, comments,
frontmatter, logging)**:
Full autonomy. No pre-flight or verification steps required.

## Documentation Standards

Machine-readable files (JSON) are the authoritative record for all operational
data. Narrative markdown documents provide context and rationale. Diagrams
(Mermaid `.view.md` files) are the preferred format for communicating system
structure and relationships. When machine-readable and narrative conflict, the
machine-readable version wins.

See [Felix Constitution Directive 5](docs/constitution/FELIX-CONSTITUTION.md)
for the full documentation standards principle.

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
