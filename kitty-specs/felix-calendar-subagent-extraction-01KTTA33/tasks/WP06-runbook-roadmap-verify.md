---
work_package_id: WP06
title: Runbook + roadmap + audited-surfaces verifications
dependencies: []
requirement_refs:
- FR-011
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T030
- T031
- T032
- T033
phase: Phase 1 - Documentation Verification
shell_pid: "34479"
history:
- at: '2026-06-11T03:26:12Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/
execution_mode: code_change
owned_files:
- docs/runbooks/openclaw-agent-setup.md
- docs/runbooks/agent-prompt-sync-ops.md
- docs/design/felix-capability-roadmap.md
- docs/design/architecture/data/audited-surfaces.json
tags: []
agent_profile: curator-carla
role: curator
agent: "claude::reviewer-renata:reviewer"
---

# Work Package Prompt: WP06 – Runbook + roadmap + audited-surfaces verifications

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, run `/ad-hoc-profile-load <agent_profile>` using the `agent_profile` value in this WP's frontmatter. The profile establishes your identity, governance scope, boundaries, and initialization — it is required for this work package. Do not proceed to the Objective section without loading the profile.

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual execution workspace is resolved later**: `/spec-kitty.implement` selects the lane worktree.

## Objectives & Success Criteria

Verify (and update only if drift is found) the existing runbooks and capability roadmap to confirm the new agent fits the established patterns. Check that `audited-surfaces.json` patterns already glob-match the new agent directory without modification.

This WP is mostly READ work with a high bar for "no edit needed unless I can articulate why." Doc hygiene without scope creep.

**Requirements covered**: FR-011 (partial — JSON + narrative architecture surfaces are in WP05; smoke runbook + nav in WP07).

## Context & Constraints

- Per DIR-014: every mission updates the relevant doc surfaces. Verifying is the active form of that obligation — confirmation that the docs DON'T need updating is itself an act of doc maintenance.
- `audited-surfaces.json` patterns of interest:
  - `scripts/openclaw/agents/*/AGENTS.md` → already glob-matches `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md`. No pattern change needed.
  - `scripts/openclaw/agents/*/IDENTITY.md`, `SOUL.md`, `USER.md`, `GOVERNANCE.md`, `AGENTS.md.tmpl` — same. Verify.
- `docs/runbooks/openclaw-agent-setup.md` describes the standard agent setup pattern. felix-admin-calendar IS an instance of that pattern. Check whether the runbook references a "current agent count" or "list of registered agents" that drifts after adding a new agent.
- `docs/runbooks/agent-prompt-sync-ops.md` describes the sync mechanism (per #567). Verify nothing in the runbook is invalidated by the new agent (e.g., timing, file list, edge cases).
- `docs/design/felix-capability-roadmap.md` tracks capability area status. Calendar work may or may not be tracked there as a discrete capability area — check.

## Subtasks & Detailed Guidance

### Subtask T030 – openclaw-agent-setup.md verification

- **Purpose**: Confirm the runbook's guidance is still accurate after adding felix-admin-calendar.
- **Steps**:
  1. Read `docs/runbooks/openclaw-agent-setup.md` top to bottom.
  2. Check sections that could drift:
     - "Two registrations, not one" — still accurate (agent-registry.json + openclaw.json) ✓
     - "Per-agent workspace files" — IDENTITY/SOUL/AGENTS pattern still valid ✓
     - Any explicit list of current agents → if present, add felix-admin-calendar.
     - Reference to which agent is the "canonical example" — if it's felix-admin-habits, mention felix-admin-calendar as a recent additional example.
  3. Decision: pass with no edits, OR update specific sections.
  4. Document the decision in Activity Log: what was checked, what (if anything) was updated.
- **Files**: `docs/runbooks/openclaw-agent-setup.md` (modify only if drift found)
- **Parallel?**: [P].

### Subtask T031 – agent-prompt-sync-ops.md verification

- **Purpose**: Confirm the sync runbook still describes correct behavior.
- **Steps**:
  1. Read `docs/runbooks/agent-prompt-sync-ops.md` top to bottom.
  2. Check: any explicit list of synced agents that now needs felix-admin-calendar? Any references to file count or watched directories that change?
  3. Most likely: no edit needed (the sync globs `scripts/openclaw/agents/*/` so new agents are auto-included).
  4. Document decision.
- **Files**: `docs/runbooks/agent-prompt-sync-ops.md` (modify only if drift)
- **Parallel?**: [P].

### Subtask T032 – felix-capability-roadmap.md verification

- **Purpose**: If calendar is tracked as a capability area, note the architectural change.
- **Steps**:
  1. Read `docs/design/felix-capability-roadmap.md`.
  2. Find any section that mentions calendar work (likely under "Capture & Calendar" or similar).
  3. If a "current state" or "status" field references the architectural shape (e.g., "calendar handled inline by main agent"), update to reflect felix-admin-calendar.
  4. Add #579 to the capability area's recent-issues or changelog if convention supports it.
- **Files**: `docs/design/felix-capability-roadmap.md` (modify if drift)
- **Parallel?**: [P].

### Subtask T033 – audited-surfaces.json pattern verification

- **Purpose**: Confirm the existing patterns cover the new agent dir (no edit expected).
- **Steps**:
  1. Read `docs/design/architecture/data/audited-surfaces.json`.
  2. Find the `openclaw-agent-prompts` entry. Its `patterns` array includes `scripts/openclaw/agents/*/AGENTS.md`, `scripts/openclaw/agents/*/IDENTITY.md`, etc.
  3. Verify (e.g., `python3 -c "import glob; print(glob.glob('scripts/openclaw/agents/*/AGENTS.md'))"`) that the glob matches felix-admin-calendar.
  4. If matches: no edit needed. Document in Activity Log.
  5. If NOT matches (unexpected): update patterns. Most likely: no change needed.
- **Files**: `docs/design/architecture/data/audited-surfaces.json` (modify only if pattern coverage gap)
- **Parallel?**: [P].

## Test Strategy

No automated tests; this WP is verification + minimal-touch edits. Reviewer should re-read each doc with the same lens and confirm.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Reviewer doesn't catch subtle drift the author missed | Each subtask requires an explicit Activity Log entry stating what was checked and what (if anything) was updated, with rationale |
| Premature edit that creates churn without value | "Pass with no edits" is a valid outcome; the WP doesn't require any file change to be accepted |
| audited-surfaces.json pattern doesn't actually glob-match (edge case in path matching) | T033 step 3 EXECUTES the glob to verify, doesn't just inspect the regex |

## Review Guidance

- For each of the 4 subtasks, is there a clear "checked / no change needed" OR "checked / changed X because Y" rationale in the Activity Log?
- If any subtask resulted in a doc edit, does the diff stay minimal (no scope creep)?
- The audited-surfaces.json glob actually matches the new agent dir?

## Activity Log

> **CRITICAL**: Activity log entries MUST be in chronological order (oldest first, newest last).

- 2026-06-11T03:26:12Z -- system -- Prompt created.
- 2026-06-11T03:52:14Z – claude::curator-carla:curator – shell_pid=31884 – Assigned agent via action command
- 2026-06-11T03:56:55Z – claude::curator-carla:curator – shell_pid=31884 – T030 (openclaw-agent-setup.md): Read full runbook (345 lines). Drift articulable in 'Current agent layout' tree (lines 222-264) — explicitly enumerates each deployed agent dir; missing felix-admin-calendar / calendar-agent entries after WP02+WP05 land. EDIT: appended calendar-agent/ branch to /data/services/openclaw/ tree (AGENTS.md, IDENTITY.md, SOUL.md, TOOLS.md, USER.md) and felix-admin-calendar/agent/ to the ~/.openclaw/agents/ tree. Bumped frontmatter last_updated → 2026-06-11, revision → v1.3, added mission attribution. Other sections checked but not drifted: 'Two registrations', 'Per-agent workspace files', 'Output Discipline', deploy-pipeline section, checklist, cutover sequence.
- 2026-06-11T03:57:04Z – claude::curator-carla:curator – shell_pid=31884 – T031 (agent-prompt-sync-ops.md): Read full runbook (226 lines). Sync mechanism is JSON-driven (reads service-inventory.json, globs scripts/openclaw/agents/<slug>/) so new agents auto-included — no behavioral drift. Drift articulable in operator troubleshooting block (lines 147-150): explicit per-agent next-tick schedule list omitted felix-admin-calendar. Per WP02 spec, calendar is event-driven (delegation-triggered, same as tasker). EDIT: added one line for felix-admin-calendar matching tasker's pattern. Bumped frontmatter last_validated → 2026-06-11, version → 1.1. No other sections required edits.
- 2026-06-11T03:57:15Z – claude::curator-carla:curator – shell_pid=31884 – T032 (felix-capability-roadmap.md): Read full roadmap (422 lines). Calendar Integration tracked as a feature cluster (line 162) with status 'Planned'; planned features include F020 OAuth (#100), F021 task-event linking (#117), calendar-aware briefing (#164). This mission (#579) is architectural extraction — moving calendar handlers from main/AGENTS.md into a dedicated subagent. NOT a new F-series feature; does NOT change Calendar Integration cluster status (still Planned — F020 OAuth foundation still upstream); does NOT match 'Self-documenting system epic' table scope (cross-cutting doc/auditor infra missions, not subagent topology). The roadmap operates at capability cluster / F-series abstraction level, not agent topology level. No 'calendar handled inline by main agent' statement appears in the doc. PASS WITH NO EDITS — adding a subagent-extraction line would be churn at the wrong abstraction layer.
- 2026-06-11T03:57:25Z – claude::curator-carla:curator – shell_pid=31884 – T033 (audited-surfaces.json): Read full JSON. openclaw-agent-prompts entry's patterns array uses six scripts/openclaw/agents/*/<FILE>.md globs (AGENTS.md, AGENTS.md.tmpl, SOUL.md, IDENTITY.md, USER.md, GOVERNANCE.md). EXECUTED the glob per WP step 3: (a) in-tree run from worktree root showed all six globs match every existing felix-admin-* dir (felix-admin-capture, felix-admin-escalation, felix-admin-habits, felix-admin-tasker, felix-doc-auditor, main); (b) positive-proof simulation with a temp scripts/openclaw/agents/felix-admin-calendar/ dir confirmed the * wildcard auto-includes the new dir for AGENTS.md, IDENTITY.md, SOUL.md, USER.md. CI consumer tooling/scripts/check_audited_surface_drift.py exists. PASS WITH NO EDITS — pattern coverage already in place; the glob is the contract, specific agent enumeration not required (per WP guidance: 'don't treat absence of explicit felix-admin-calendar mention as drift').
- 2026-06-11T03:58:38Z – claude::curator-carla:curator – shell_pid=31884 – Verifications complete (see WP file Activity Log for per-doc rationale). T030+T031: minimal-touch edits to runbook trees / schedule list. T032+T033: pass with articulated rationale.
- 2026-06-11T03:59:17Z – claude::reviewer-renata:reviewer – shell_pid=34479 – Started review via action command
