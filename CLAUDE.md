---
title: Claude Code Context — kg-automation
doc_type: reference
status: approved
---

# kg-automation — Claude Code Context

This file is read automatically by Claude Code at session start.
Read this first. Read nothing else until this is complete.

## Issue-First Habit

When the user asks for a bug fix, feature, investigation, or any change
that touches deployed services, agent config, or multiple files — ask
*"Want me to create an issue for this first?"* before starting work.
This applies during casual conversation, not just during planned
workflow execution. The issue takes 30 seconds and gives us audit
trail, doc-audit triggers, and cross-session context. Exempt: typo
fixes, single-line doc edits, CLAUDE.md updates, and pure research
questions.

## What This System Is

kg-automation is Kent Gale's personal AI operating system — an always-on
accountability and automation infrastructure built on office2 (Ubuntu 24.04 LTS,
Tailscale-accessible) with OpenClaw as the orchestration engine and Vikunja as
the task store and UI layer.

This is not a general-purpose automation repo. It is a personal system with a
specific architecture. Read `docs/design/felix-capability-roadmap.md` for design
intent, capability status, and open decisions. The GitHub issue queue is the
authoritative work backlog.

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
**Developer Portal**: [`docs/DEVELOPER_PORTAL.md`](docs/DEVELOPER_PORTAL.md) — guided onboarding sitemap (start here for orientation; complements [`docs/INDEX.md`](docs/INDEX.md)).

**Documentation map**: [`docs/INDEX.md`](docs/INDEX.md) — master index of all active documentation, grouped by directory with Divio type annotations. Start here to discover docs by topic or type.

**Governance**: [`docs/constitution/FELIX-CONSTITUTION.md`](docs/constitution/FELIX-CONSTITUTION.md) — top-level governance, autonomy levels, principles. See also [`docs/constitution/AGENT-REGISTRY.md`](docs/constitution/AGENT-REGISTRY.md).

**Machine-readable operational state**: `docs/design/architecture/data/` is the canonical home for JSON artifacts (service inventory, topology, credentials, data-flows, schemas). Exempt from moves.

`docs/design/architecture/` — current-state system documentation:
- Hardware, network, and service inventory (with machine-readable JSON in `data/`)
- Data flows, credentials, identity model, backup, security posture
- **Updated after every feature** — see `change-control.md` for the protocol

`docs/design/felix-capability-roadmap.md` — design intent and roadmap:
- Capability area status and feature sequence
- Open decisions and design principles
- Feature cluster progress (GitHub issues are the authoritative backlog)

**Standing requirement**: Any feature that changes deployed services, credentials,
data flows, or network topology must update the relevant files in
`docs/design/architecture/` and `docs/design/architecture/data/`.

**Discovery aid for spec/plan agents**: When authoring or updating a spec's
Architecture Impact section (during `/spec-kitty.specify` and `/spec-kitty.plan`),
consult `docs/design/architecture/data/signal-to-doc-map.json` for the canonical
list of affected docs per change class. Filter entries by
`match.source == "mission-architecture-impact"` and pick the `change_class`
values that fit the mission (e.g., `service-added-or-modified`,
`credential-added-or-modified`, `data-flow-added-or-modified`,
`network-topology-changed`, `runbook-added`, `runbook-modified`,
`architecture-doc-added`, `systemd-unit-added-or-modified`). Each entry's
`doc_targets` array enumerates the docs that must be reviewed and updated in
the mission's merge. Without this lookup, navigation docs like `docs/INDEX.md`
and `docs/DEVELOPER_PORTAL.md` are routinely missed — see #492 for the
precedent that motivated formalizing this. The map is the source of truth;
keep it current as new doc surfaces are added.

**Standing requirement**: Any work that deploys, modifies, or registers an
OpenClaw agent must read `docs/runbooks/openclaw-agent-setup.md` first.
That runbook defines the required workspace files (IDENTITY.md, SOUL.md,
AGENTS.md), the openclaw.json registration, and the verification steps.
An agent is not deployed until both the governance registry and OpenClaw
config are updated.

## Repository Structure

```
ai-agents/          ← agent instruction files (this file's siblings)
docs/
  archive/          ← frozen historical artifacts (contains legacy func-spec/ archive)
  constitution/     ← governance — Felix constitution, agent registry
  design/           ← architecture specs, standards, research
  diagnostics/      ← active troubleshooting (spec-kitty workflow journal)
  runbooks/         ← operational runbooks (how-to guides)
scripts/            ← automation scripts
kitty-specs/        ← spec-kitty managed (DO NOT EDIT — see below)
.kittify/           ← spec-kitty managed (DO NOT EDIT — see below)
.github/
  ISSUE_TEMPLATE/   ← issue templates (feature, bug, rfc, infra, docs-debt)
```

**`kitty-specs/` and `.kittify/` are owned by spec-kitty.** These directories
contain mission specifications, work packages, status event logs, and workflow
configuration managed exclusively by spec-kitty commands. Agents and humans
must **never** directly create, edit, move, or delete files in these directories.
All changes flow through spec-kitty slash commands (`/spec-kitty.*`). Reading
these files for context is fine; writing to them is not.

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

**Spec readiness gate:**
Before entering the spec-kitty workflow, the issue MUST have the `spec: ready`
label. Issues follow a three-label lifecycle:

- `spec: brief` — default on new feature/infra issues. Low-friction capture.
- `spec: pending` — auto-added by GitHub Actions when a P1/P2 priority label
  is applied. Signals "needs body formalized before spec-kitty." Visible in
  project board for planning/sweep queries.
- `spec: ready` — manually applied after the issue body meets the structured
  template (`.github/ISSUE_TEMPLATE/feature.md` or `infra.md`). Clears the
  issue for `/spec-kitty.specify`.

Do not run `/spec-kitty.specify` on an issue without `spec: ready`.
To find issues needing formalization, query for `spec: pending`.

**Implementation sequence:**
1. Verify the issue has the `spec: ready` label
2. Read the issue body completely before starting anything else
3. Run spec-kitty specify using the issue body as input
4. Follow the full spec-kitty workflow:
   `/spec-kitty.specify → /spec-kitty.plan → /spec-kitty.tasks →
    /spec-kitty.implement → /spec-kitty.review → /spec-kitty.merge`
5. On merge, close the issue: `gh issue close <number> --repo kentonium3/kg-automation`
6. Add a comment to the issue with the merge commit hash and any relevant notes

**Auto-driving the workflow:**
When Kent says to "proceed through the workflow" or equivalent, drive the full
arc (specify → plan → tasks → implement → review → merge) without waiting for
him to type each slash command. For EACH workflow step, read the corresponding
command file from disk before executing:

- `~/.claude/commands/spec-kitty.specify.md`
- `~/.claude/commands/spec-kitty.plan.md`
- `~/.claude/commands/spec-kitty.tasks.md`
- `~/.claude/commands/spec-kitty.implement.md`
- `~/.claude/commands/spec-kitty.review.md`
- `~/.claude/commands/spec-kitty.merge.md`

These files are the canonical runbooks — the same content a slash command
loads. Read the file fresh each step (spec-kitty upgrades may update them).
Follow the instructions in the file as if Kent had invoked the slash command.

**Only stop for:**
1. Mandatory stops marked in the command file (e.g., "MANDATORY STOP POINT")
2. Required input from Kent (discovery questions, scope decisions, approvals)
3. Workflow errors or unexpected state that can't be resolved autonomously

Do not stop to ask "should I proceed to the next step?" — the instruction to
drive the workflow IS the approval for all subsequent steps until a genuine
stop condition is hit.

**Issue types and their workflows:**
- `P1-feature` / `P2-feature` → full spec-kitty workflow above
- `P1-bug` / `P2-bug` → spec-kitty software-dev mission, fix-focused
- `P1-infra` / `P2-infra` → check risk tier in issue body first; Tier 0 = generate only
- `P1-rfc` → discussion and decision recording; no implementation until converted to feature/infra issue

**Legacy specs:** `docs/archive/func-spec/` contains historical specs F001–F020.
These are the archive record. Do not create new files there — new features
live in the GitHub issue queue.

**Design-time discipline (per Constitution Directive 6):** during
spec-kitty specify and plan phases, identify deterministic vs stochastic
work. Route every step that's mechanically verifiable into a helper
script the agent invokes; reserve the agent's prompt for judgment,
classification, and interpretation. Helper scripts live in
`scripts/<domain>/` and are tested independently. Do NOT force-extract
when a one-line agent step is genuinely correct — the rule is to
*recognize the split*, not to mechanize everything.

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

## Engineering Principles

Two governing documents sit between the Felix Constitution (broad governance)
and individual feature specs:

- [`docs/design/engineering-principles.md`](docs/design/engineering-principles.md) — the 10 ratified
  principles covering runtime state, deterministic work, integration boundaries,
  JSON validation, test discipline, privacy enforcement, active-surface hygiene,
  suspension as an operational state, observability per feature, and guardrail
  preference. Read these before designing new features or scoping new
  infrastructure work.
- [`docs/design/helper-script-conventions.md`](docs/design/helper-script-conventions.md) — the
  approved three-tier model (helper / library / skill), invocation-surface
  decision test, CLI interface contract, stdout convention, atomic state
  mutation, idempotency, failure-mode handling, observability, testing
  discipline, deploy story, and migration discipline. Operational source of
  truth referenced from Felix Constitution Directive 6.

When a feature, infrastructure change, or bug fix touches deterministic
verification work, the helper/library/skill decision is part of spec-ready
criteria (per the issue templates).

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

**Absolute rule**: `~/second-brain/notes/04-Growth/_private/` is never
read, written, referenced, or logged by any agent or script under any circumstance.
