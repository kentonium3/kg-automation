# Agent Workspace Reconciliation

## Overview

OpenClaw agent workspace files have drifted between the kg-automation repo (`scripts/openclaw/agents/`) and their deployed counterparts on office2. A drift audit during mission 026 found 8 drifted files, 3 repo-missing files, and 14 matching files across 5 agent workspaces. The drift is bidirectional — some files have production content the repo lost (specify-phase commit `8c1054c` stripped content; mission 025 edits were never committed back), while others have repo updates that were never deployed to office2 (tasker agent identity/scope updates from mission 023).

Additionally, the main OpenClaw agent's core workspace files (`AGENTS.md`, `TOOLS.md`, `IDENTITY.md`) have never been tracked in the repo. A patch-overlay pattern exists (`main-patches/`) but has no apply mechanism and is effectively documentation, not tooling.

This mission reconciles all agent workspaces bidirectionally, establishes the repo as the single source of truth, retires the patch-overlay pattern in favor of single merged files, and implements a lightweight enforcement mechanism to detect future drift before it becomes a problem.

## Actors

- **Kent (system owner)** — approves reconciliation direction decisions, executes any Tier 0 commands if needed
- **Claude Code agent** — performs the reconciliation, writes the enforcement mechanism, deploys reconciled files
- **Felix agents (OpenClaw)** — consumers of workspace files; their behavior changes when files are updated
- **Enforcement mechanism** — automated process that periodically compares deployed state to repo and sends notifications on drift

## User Scenarios & Testing

### Scenario 1: Full baseline and reconciliation

Kent initiates reconciliation. The system probes all agent workspaces on office2, diffs every file against the repo, produces a reconciliation report showing direction-aware actions per file, executes the reconciliation (capture or deploy per file), and verifies zero drift post-reconciliation via SHA256 hash comparison.

**Acceptance test:** After reconciliation, running `sha256sum` on every workspace file on office2 and its repo counterpart produces identical hashes for all tracked files.

### Scenario 2: Factory-default file crosses customization threshold

An OpenClaw agent's factory-default `IDENTITY.md` (currently unmodified boilerplate) gets customized — either by a mission, by Kent manually, or by the agent itself through an OpenClaw mechanism. The enforcement mechanism detects that the deployed file no longer matches the known factory baseline hash and sends a notification indicating the file should be committed to the repo.

**Acceptance test:** Modifying a factory-default file on office2 triggers a notification within one enforcement cycle.

### Scenario 3: Future drift detection

A future mission or manual edit changes an agent workspace file on office2 without committing the change to the repo. The enforcement mechanism detects the mismatch between deployed and repo state and sends a notification with the agent name, file name, and drift direction.

**Acceptance test:** After deliberately introducing a 1-line change to a deployed file without committing, the enforcement mechanism flags the drift on its next run.

### Scenario 4: New agent onboarding

A new OpenClaw agent is registered. Its workspace starts with factory-default files. The enforcement mechanism recognizes these as factory defaults (matching known baseline hashes) and does not flag them. Once any file is customized, it begins tracking that file for drift.

**Acceptance test:** Registering a new agent with factory defaults produces no drift notifications. Customizing one file triggers a notification for that file only.

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Probe all agent workspaces on office2 and produce a complete inventory of every workspace file across all registered agents | Proposed |
| FR-002 | Diff every inventoried file against its repo counterpart under `scripts/openclaw/agents/` and classify each as: matching, office2-authoritative (capture), repo-authoritative (deploy), or repo-missing (new capture) | Proposed |
| FR-003 | Capture office2-authoritative files into the repo, preserving content exactly as deployed | Proposed |
| FR-004 | Deploy repo-authoritative files to office2 via SCP, replacing outdated deployed content | Proposed |
| FR-005 | Commit the 3 missing main-agent files (`AGENTS.md`, `TOOLS.md`, `IDENTITY.md`) to `scripts/openclaw/agents/main/` as single merged files | Proposed |
| FR-006 | Retire the `main-patches/` directory and pattern, replacing it with the single-file approach used by all other agents | Proposed |
| FR-007 | Record a baseline hash manifest of all agent workspace files (repo and office2) after reconciliation, stored in a machine-readable format | Proposed |
| FR-008 | Implement a periodic enforcement script that compares deployed workspace files on office2 against the repo baseline and detects drift | Proposed |
| FR-009 | The enforcement script must distinguish between factory-default files (no alert) and customized files (alert on drift) using known factory baseline hashes | Proposed |
| FR-010 | The enforcement script sends a notification (email, WhatsApp, or other lightweight channel) when drift or a new customization is detected, including agent name, file name, and drift direction | Proposed |
| FR-011 | Produce a post-reconciliation verification report showing SHA256 hash comparison of all tracked workspace files between repo and office2 | Proposed |
| FR-012 | Document the reconciliation process and factory-default lifecycle policy in a runbook | Proposed |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | Enforcement script completes a full sweep of all agent workspaces within a reasonable time | Under 60 seconds for current agent count (5 agents, ~25 files) | Proposed |
| NFR-002 | Enforcement mechanism runs on a schedule without manual intervention | Cron-based, at least daily | Proposed |
| NFR-003 | Notification delivery latency from detection to alert | Within 5 minutes of enforcement run completing | Proposed |
| NFR-004 | Enforcement script must run as the `claude` user on office2 | No sudo required | Proposed |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | All SSH operations to office2 must use `ssh office2-claude` (never `office2-kgale`) except for Tier 0 commands requiring sudo | Active |
| C-002 | Deploy operations (SCP to office2) require a recent Restic backup confirmation before execution (Tier 2 protocol) | Active |
| C-003 | Runtime files (`HEARTBEAT.md`, `.openclaw/workspace-state.json`) are excluded from reconciliation and tracking | Active |
| C-004 | `BOOTSTRAP.md` files are transient by design and excluded from repo tracking | Active |
| C-005 | The `claude` user does not have sudo access; any permission changes on system paths require Kent to execute manually | Active |
| C-006 | The enforcement mechanism must use a notification channel already available to the `claude` user on office2 (no new service provisioning) | Active |

## Key Entities

- **Agent workspace** — a directory on office2 containing markdown files (`AGENTS.md`, `SOUL.md`, `TOOLS.md`, `USER.md`, `IDENTITY.md`) that define an OpenClaw agent's identity, capabilities, and standing orders
- **Factory baseline hash** — SHA256 hash of an unmodified OpenClaw factory-default template file, used to distinguish "never customized" from "customized and drifted"
- **Baseline manifest** — machine-readable record of all tracked workspace file hashes after reconciliation, used as the reference point for drift detection
- **Drift** — any difference between a deployed workspace file on office2 and its repo counterpart, classified by direction (office2-authoritative or repo-authoritative)

## Assumptions

- The drift audit from #156 (8 drifted, 3 missing, 14 matching) is approximately current; the plan phase will re-probe to confirm before implementation
- The `openclaw.json` on office2 is the authoritative registry of all agents and their workspace paths
- OpenClaw factory-default template files are stable across versions (hash comparison is reliable for detecting customization)
- At least one notification channel (email or WhatsApp) is already configured and reachable from the `claude` user on office2
- The `main-patches/` content is fully represented in the merged `data/AGENTS.md` on office2 (no patch content exists only in the repo)

## Dependencies

- SSH access to office2 as `claude` user (operational)
- `openclaw.json` readable by `claude` user on office2
- Restic backup system operational (for Tier 2 pre-deploy verification)
- Notification channel available from office2 (email relay, WhatsApp API, or equivalent)

## Success Criteria

- Zero drift between `scripts/openclaw/agents/` in the repo and deployed workspace files on office2 for all tracked files
- All 5 agent workspaces (main, capture, escalation, habits, tasker) have complete file sets tracked in the repo
- `main-patches/` pattern retired; main agent uses single-file approach consistent with other agents
- Enforcement mechanism running on office2, detecting drift within one cycle and sending notifications
- Factory-default lifecycle policy documented: trigger for when untracked files become tracked, ownership, and enforcement mechanism
- Runbook documenting the reconciliation process for future use
- #156 and #157 closeable upon mission completion

## Out of Scope

- Fixing the spec-kitty specify-phase commit scope bleed that caused the original drift (that's a spec-kitty upstream bug — appendix in #156)
- Reconciliation of non-OpenClaw config files on office2 (Vikunja, Obsidian Sync, cron — deferred to a separate sweep issue)
- Changes to OpenClaw's own workspace initialization or template mechanisms
- Modifying the `openclaw.json` agent registry
- Full robust enforcement tooling if it requires a dedicated feature cycle (lightweight notification is the minimum viable deliverable)

## Related Issues

- **#166** — parent issue (this mission's input spec)
- **#156** — P1-bug: widespread repo-vs-office2 drift (child of #166)
- **#157** — P2-infra: main agent workspace files partially tracked (child of #166)
- **#152** — mission 026, blocked by drift until reconciliation completes
- **#143, #588** — spec-kitty sparse-checkout staleness (root cause of some drift events)
- **#105** — doc auditor (potential future home for enforcement responsibilities)
- **#106** — state auditor (potential future home for enforcement responsibilities)
