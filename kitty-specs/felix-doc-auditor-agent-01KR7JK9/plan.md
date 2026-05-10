# Implementation Plan: Felix Doc Auditor Agent

**Branch**: `main` (no worktree until `/spec-kitty.implement`) | **Date**: 2026-05-09 | **Spec**: [spec.md](./spec.md)
**Mission**: `felix-doc-auditor-agent-01KR7JK9` (mission_id `01KR7JK9QTHM5F4PD3YC43KDQW`)
**Source issue**: kentonium3/kg-automation#105

## Summary

Build `felix-doc-auditor`, a new OpenClaw cron-driven agent that processes the documentation audit issues created by the existing `doc-audit-trigger.yml` (per-merge) and `doc-audit-weekly.yml` (weekly) GitHub Actions workflows. The agent classifies each in-scope doc as either a high-confidence direct edit (committed atomically with audit-issue reference) or a judgment-required gap (converted to a structured `docs-debt` issue with a draft outline). It also detects missing artifacts (deployed agents/services without docs).

The agent runs at Assisted (Level 1) for an initial ~1 week, gating every edit through a WhatsApp summary + reply parser modeled on the existing `felix-admin-habits` pattern. Promotion to Supervised (Level 2) is a separate governance decision.

The mission also folds in a small fix to `doc-audit-weekly.yml`: scope the "skip if exists" duplicate check to the *current week's* issue title rather than any open weekly audit. Without this, a stale older weekly issue blocks all future weeklies (the bug currently masking three weeks of missed weekly audits).

## Technical Context

**Language/Runtime**: Bash + JSON for OpenClaw agent workspace files (IDENTITY.md, SOUL.md, AGENTS.md, TOOLS.md per `docs/runbooks/openclaw-agent-setup.md`). Agent execution itself is a Claude (Sonnet) prompt-driven loop orchestrated by OpenClaw on office2.
**Primary Dependencies**: OpenClaw (cron scheduler + agent runtime, already deployed); `gh` CLI (already installed and authenticated on office2); standard git for commits; existing WhatsApp send pipeline.
**Storage**: Repository files (this repo, cloned at `/home/claude/kg-automation/` on office2). Agent activity logs at `/home/kgale/second-brain/agents/logs/` (consistent with other felix-admin-* agents). State lock via GitHub `status:in-progress` label on the in-flight audit issue (no on-disk state file).
**Testing**: Manual canary first — single-issue dry run against #186 at Level 1, end-to-end (read scope → propose edits → WhatsApp → approve → commit → debt issues → summary → close). After canary success, enable cron and observe backlog drain. No unit-test framework for OpenClaw agents exists; validation is operational.
**Target Platform**: office2 (Ubuntu 24.04 LTS server, OpenClaw agent runtime).
**Project Type**: Single addition to existing kg-automation infrastructure (new agent + new skill + ops runbook + agent registry entry + GitHub Actions YAML fix). No new top-level project.
**Performance Goals**: NFR-002 — typical post-merge audit ≤10 min wall-clock (≤5 docs); weekly full-scope audit ≤30 min. NFR-006 — 6-issue backlog drained within 6 cron ticks (≤6 hours).
**Constraints**: NFR-001 60-minute polling interval; NFR-004 2-hour Level-1 approval timeout; constitutional guardrails C-001 through C-007 (no Felix-Constitution edits, no CLAUDE.md edits, no second-brain access, reversible-only operations).
**Scale/Scope**: ~25 documents currently in `doc-domain-map.json` scope; 6-issue current backlog; ~2-5 audit issues created per week steady-state (per-merge triggers + weekly); ~Sonnet model cost expected to be modest (each audit is bounded by domain map size).

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: Skipped — `spec-kitty charter context --action plan --json` returned compact-mode governance with an unresolved warning ("Charter selected unavailable tool(s): pytest, python — Update charter available_tools or register those tools in the runtime tool registry"). The charter exists but its tool registry is out of date. The warning is non-blocking per the workflow command's guidance.

**Substantive constitutional alignment** (from spec § Constitutional Compliance):

- ✅ Autonomy level: deploys at Assisted (Level 1) per Felix Constitution autonomy framework
- ✅ Scope: documentation files only — no agent configs (other than self-registration), no deployed services, no credential files
- ✅ Failure behavior: never fails silently (per-doc failures logged + reported in summary)
- ✅ Privacy: `~/second-brain/notes/04-Growth/_private/` exclusion preserved
- ✅ Reversibility: all operations reversible (git-tracked edits, gh-CLI issue mutations)
- ✅ Tool use: `gh` CLI only for GitHub (per repo convention; MCP GitHub auth unreliable per memory)

**Recommended follow-up** (out of scope for this mission): file a small infra issue to update the charter's `available_tools` list so future spec-kitty runs return resolved governance.

## Project Structure

### Documentation (this feature)

```
kitty-specs/felix-doc-auditor-agent-01KR7JK9/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
├── spec.md              # /spec-kitty.specify output
├── meta.json            # mission identity
├── checklists/
│   └── requirements.md  # spec quality checklist (passed)
├── status.events.jsonl  # workflow event log
└── tasks/               # populated by /spec-kitty.tasks
```

### Source Code (repository root, additions only)

```
kg-automation/
├── scripts/openclaw/
│   ├── agents/
│   │   └── felix-doc-auditor/         # NEW — agent workspace
│   │       ├── IDENTITY.md            # who the agent is
│   │       ├── SOUL.md                # values / character
│   │       ├── AGENTS.md              # standing orders
│   │       └── TOOLS.md               # tool boundary contract
│   └── skills/
│       └── doc-audit/                 # NEW — agent skill (FR-006)
│           └── SKILL.md
├── docs/
│   ├── runbooks/
│   │   └── doc-auditor-ops.md         # NEW — ops runbook (FR-007)
│   ├── constitution/
│   │   └── AGENT-REGISTRY.md          # MODIFY — add felix-doc-auditor at Level 1
│   └── design/architecture/
│       ├── data/
│       │   ├── service-inventory.json # MODIFY — add agent entry
│       │   └── doc-domain-map.json    # MODIFY — add doc-auditor-ops.md reference
│       └── service-inventory.md       # MODIFY — narrative reference for new agent
├── .github/
│   └── workflows/
│       └── doc-audit-weekly.yml       # MODIFY — FR-008 fix
└── (office2-only, not in repo)
    ├── /home/claude/.openclaw/openclaw.json   # MODIFY — register new agent + cron entry
    └── (existing OpenClaw deployment)
```

**Structure Decision**: This mission adds files to the existing kg-automation layout. No new top-level project. Workspace pattern follows the existing `scripts/openclaw/agents/felix-admin-*/` convention. Skill pattern follows the existing `scripts/openclaw/skills/*/SKILL.md` convention (verified during research phase that this directory exists and the convention is established).

## Complexity Tracking

*Fill ONLY if Charter Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |

No charter violations. Charter Check was skipped due to unresolved tool registry (non-blocking per workflow); substantive alignment confirmed inline above.

## Phase Outputs

- **Phase 0** (Outline & Research): see [research.md](./research.md)
- **Phase 1** (Design & Contracts): see [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
- **Phase 2** (Tasks): produced by `/spec-kitty.tasks` (NOT this command)
