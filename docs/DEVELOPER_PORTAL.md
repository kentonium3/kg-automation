---
title: kg-automation Developer Portal
doc_type: index
status: approved
owners: [kgale]
audience: agents_and_humans
last_validated: 2026-05-26
version: "1.0"
---

# kg-automation Developer Portal

This is the guided sitemap for the `kg-automation` (Felix) documentation suite.
It exists so that AI agents and human contributors can pick the right starting
point in under thirty seconds without scrolling the full flat catalog. For the
complete directory listing — every active markdown file grouped by directory —
see [`./INDEX.md`](<./INDEX.md>); this portal complements that index rather than
replacing it.

---

## Quick-Start Onboarding

Pick the path that matches what you're about to do. Each path lists files to
read in order; the goal is to reach your first task-relevant decision in as
few hops as possible.

### Feature Development

1. [Felix System Overview](<./design/README.md>) — **start here if you're new.**
   What Felix is, what it does for Kent, how the pieces fit. Day-1 orientation.
2. [CLAUDE.md](../CLAUDE.md) § "Feature Development Workflow" — issue-first
   habit, the `spec: ready` gate, and the spec-kitty arc
3. [Felix Constitution](<./constitution/FELIX-CONSTITUTION.md>) — governance,
   autonomy levels, design principles
4. [Felix Capability Roadmap](<./design/felix-capability-roadmap.md>) — current
   capability status and where new work fits
5. [Architecture README](<./design/architecture/README.md>) — current-state
   system reference (detailed; use after the overview above)
5. [GitHub Issues Workflow](<./runbooks/github-issues-workflow.md>) — labels,
   milestones, project board, and the spec lifecycle

### Runbook Execution

1. [CLAUDE.md](../CLAUDE.md) § "Server Access (office2)" — SSH aliases,
   sudo policy, and the `claude` vs `kgale` user split
2. [Agent Workspace Reconciliation](<./runbooks/agent-workspace-reconciliation.md>)
   — how the office2 daemon syncs from GitHub before any agent runs
3. The target runbook under `docs/runbooks/` — see the
   [Virtual Runbook Filter](<#virtual-runbook-filter>) below
4. [Pre-Flight Change Checklist](<./runbooks/governance/pre-flight-checklist.md>)
   — mandatory assessment for Tier 0/1/2 changes
5. [Post-Change Verification](<./runbooks/governance/post-change-verification.md>)
   — health-check protocol once the runbook completes

### Bug Fix

1. [CLAUDE.md](../CLAUDE.md) § "Issue-First Habit" — when to file an issue
   before touching anything
2. The affected runbook(s) under `docs/runbooks/` — see the
   [Virtual Runbook Filter](<#virtual-runbook-filter>) below
3. The relevant [architecture](<./design/architecture/README.md>) doc for
   context on the service or data flow being changed
4. [Change Control Protocol](<./design/architecture/change-control.md>) — when
   architecture JSON/markdown must update as part of the fix
5. [Repository Governance](<./runbooks/repo-governance.md>) — git workflow,
   commit conventions, and the `[doc-audit]` marker

---

## The Execution Loop Explained

Local workspace is the authoring surface. Engineers and agents write code,
docs, and spec-kitty mission artifacts on a laptop, run the local validators
listed in the next section, then commit and push to GitHub. The repository on
GitHub is the source of truth for branch state, CI validation, and merge
history; spec-kitty mission merges land as merge commits directly to `main`
and do not open pull requests, so any CI step that depends on `pull_request`
triggers will not fire on a spec-kitty merge. Conventional commits and the
optional `[doc-audit]` suffix on maintenance changes drive downstream signals
that audits and the architecture-docs review process consume.

From GitHub the office2 host pulls the latest `main` on its own cadence and
reconciles its on-disk workspace against the repository. The reconciliation
daemon owns drift detection, last-author-wins resolution, and the
factory-default lifecycle that keeps agent workspaces consistent across
restarts; the full mechanics — directory ownership, conflict policy, and the
hooks the daemon emits — live in
[`agent-workspace-reconciliation.md`](<./runbooks/agent-workspace-reconciliation.md>)
and are not duplicated here.

Once office2 has the reconciled tree, OpenClaw is the runtime that actually
executes agents against it. Each registered agent runs from its deploy
directory with its own IDENTITY.md, SOUL.md, and AGENTS.md files, dispatched
according to the `openclaw.json` registration; the agent setup, registration
contract, and verification steps are documented in
[`openclaw-agent-setup.md`](<./runbooks/openclaw-agent-setup.md>). Treat that
runbook as the authority for any deployment, modification, or removal of an
OpenClaw agent — this section is orientation only.

---

## Verification Command Quick-Reference

Run these locally before pushing. All commands are executed from the
repository root.

| Command | What it checks | Run from |
|---|---|---|
| `python -m pytest` | Repo-wide test suite | repo root |
| `python tooling/scripts/validate_docs.py` | Markdown frontmatter schema, secret scan, portal drift | repo root |
| `python tooling/scripts/build_runbook_filter.py` | Portal runbook-filter block is current (drift check) | repo root |
| `python tooling/scripts/build_runbook_filter.py --write` | Refresh the portal runbook-filter block in place | repo root |

---

## Virtual Runbook Filter

Runbooks under `docs/runbooks/` grouped by their `audience:` frontmatter
value. This section is auto-generated from the runbook frontmatter; do not
hand-edit it. Refresh after adding or changing a runbook's `audience:` with:

```
python tooling/scripts/build_runbook_filter.py --write
```

A drift check runs as part of `validate_docs.py`, so a stale block will fail
local validation and CI.

<!-- begin:runbook-filter (generated; do not edit) -->

### Agent-executable
- [Goals Operations Runbook](<./runbooks/goals-ops.md>)
- [Inbox Processing Operations Runbook](<./runbooks/inbox-ops.md>)
- [Obsidian Sync Operations Runbook](<./runbooks/obsidian-sync-ops.md>)
- [OpenClaw Operations Runbook](<./runbooks/openclaw-ops.md>)
- [Task Intelligence Operations](<./runbooks/task-intelligence-ops.md>)
- [Transcribe API Operations Runbook](<./runbooks/transcribe-ops.md>)
- [Vikunja Operations Runbook](<./runbooks/vikunja-ops.md>)

### Dual-audience
- [Agent Workspace Reconciliation](<./runbooks/agent-workspace-reconciliation.md>)
- [Deployment Runbook](<./runbooks/deployment.md>)
- [Doc Auditor Operations Runbook](<./runbooks/doc-auditor-ops.md>)
- [Doc Maintenance](<./runbooks/doc-maintenance.md>)
- [Escalation Operations](<./runbooks/escalation-ops.md>)
- [felix-doc-auditor driver operations](<./runbooks/doc-auditor-driver-ops.md>)
- [Felix-Vikunja sync driver operations](<./runbooks/sync-driver-ops.md>)
- [GitHub Issues Workflow](<./runbooks/github-issues-workflow.md>)
- [Google Workspace Operations](<./runbooks/google-workspace-ops.md>)
- [Habit Check-in Operations](<./runbooks/habits-ops.md>)
- [Incident Postmortem Template](<./runbooks/governance/incident-postmortem-template.md>)
- [Observation Intelligence Layer — Operations Runbook](<./runbooks/observation-ops.md>)
- [Obsidian Setup Guide](<./runbooks/obsidian-setup.md>)
- [Obsidian Vault (kg-automation/docs)](<./runbooks/obsidian.md>)
- [Ollama Operations Runbook](<./runbooks/ollama-ops.md>)
- [OpenClaw Agent Setup](<./runbooks/openclaw-agent-setup.md>)
- [Post-Change Verification Protocol](<./runbooks/governance/post-change-verification.md>)
- [Pre-Flight Change Checklist](<./runbooks/governance/pre-flight-checklist.md>)
- [Repository Governance](<./runbooks/repo-governance.md>)
- [Restic Backup Operations](<./runbooks/restic-backup-ops.md>)
- [Security Baseline Operations](<./runbooks/security-baseline-ops.md>)
- [Signal-driven monitoring operations (felix-core-digest signal extraction + felix-heartbeat-gate)](<./runbooks/signal-driven-monitoring-ops.md>)
- [Spec-Kitty Bug Reporting](<./runbooks/spec-kitty-bug-reporting.md>)
- [Tasker Operations (Enrichment JSONL Migration)](<./runbooks/tasker-ops.md>)
- [Templater Commands (Canon v2)](<./runbooks/templater-commands.md>)
- [Vault Path Registry Migration Runbook](<./runbooks/vault-path-registry-migration.md>)
- [Vikunja Date Handling](<./runbooks/vikunja-date-handling.md>)
- [WhatsApp Channel Operations Runbook](<./runbooks/whatsapp-ops.md>)

### Human-only
- [Credential Rotation Operations](<./runbooks/credential-rotation-ops.md>)
- [Escalation Phase 6 Soak Window](<./runbooks/escalation-soak-window.md>)
- [Felix Governance Runbook](<./runbooks/felix-governance.md>)
- [felix-bot Vikunja Provisioning](<./runbooks/felix-bot-vikunja-provisioning.md>)
- [Spec-Kitty Installation Guide for Existing Repositories](<./runbooks/spec-kitty-init-in-existing-repo.md>)

### Unclassified
- _(none)_

<!-- end:runbook-filter -->
