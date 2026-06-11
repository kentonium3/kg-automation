---
work_package_id: WP07
title: Smoke runbook + navigation entries
dependencies:
- WP02
requirement_refs:
- FR-011
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T034
- T035
- T036
phase: Phase 3 - Acceptance Substrate
history:
- at: '2026-06-11T03:26:12Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/
execution_mode: code_change
owned_files:
- docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
tags: []
---

# Work Package Prompt: WP07 – Smoke runbook + navigation entries

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, run `/ad-hoc-profile-load <agent_profile>` using the `agent_profile` value in this WP's frontmatter. The profile establishes your identity, governance scope, boundaries, and initialization — it is required for this work package. Do not proceed to the Objective section without loading the profile.

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual execution workspace is resolved later**: `/spec-kitty.implement` selects the lane worktree.

## Objectives & Success Criteria

Author the operator smoke runbook (the canonical behavioral verification surface for this mission) and register it in the documentation navigation. After this WP:

- `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md` exists, follows the structure contract in `contracts/smoke-runbook-shape.md`, and covers all 8 SCs from spec.md.
- `docs/INDEX.md` lists the new smoke runbook in the runbooks section.
- `docs/DEVELOPER_PORTAL.md` references the runbook in the appropriate sitemap section.

**Requirements covered**: FR-011 (smoke surface + nav), NFR-003 (smoke verifies relay latency).

## Context & Constraints

- Structure contract: `kitty-specs/felix-calendar-subagent-extraction-01KTTA33/contracts/smoke-runbook-shape.md`. This contract is the spec — follow it line for line.
- The smoke runbook is the behavioral verification surface for SC-001 (habit DM), SC-002 (calendar DM), SC-005 (other-subagent regression), SC-006 (scheduled outbound).
- felix-doc-auditor verification path: `last-tick.json` freshness check (per `reference_felix_doc_auditor_ops` and research.md F-05), NOT a DM round-trip. Distinguish this in the runbook.
- Per `feedback_live_integration_tests`: NO synthetic-message test substrate. The runbook is operator-driven.
- Voice: Felix's runbooks use Kent's voice (first person, direct). Match it.

## Subtasks & Detailed Guidance

### Subtask T034 – Author the smoke runbook

- **Purpose**: The canonical post-deploy checklist Kent walks through.
- **Steps**:
  1. Create `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md`.
  2. Use the shape contract `contracts/smoke-runbook-shape.md` as the literal structure. All 6 required sections present.
  3. Standard runbook frontmatter (consult an existing runbook for the precise field set; expect `title`, `doc_type: runbook`, `status`, `audience`, `last_updated`, `last_validated`, `updated_by`, `revision`).
  4. Section content guidance:
     - **Pre-conditions**: deploy script completed without errors; journal watch zero hits; observation start timestamp recorded.
     - **DMs to send**: 6 rows per the DM coverage matrix in `contracts/smoke-runbook-shape.md`. Provide example DM text per subagent (use real-feeling examples that match Kent's normal usage patterns; for confidentiality, no actual data needed).
     - **Non-DM checks**: doc-auditor `last-tick.json` freshness command (with `jq` parsing); scheduled-outbound observation window; journal absence-of-warning command.
     - **24h observation window**: explicit timeframe for SC-006 satisfaction.
     - **Decision criteria**: when to mark complete vs file regression bug vs roll back.
     - **Verification record**: blank checkboxes the operator initials + timestamps.
  5. Reference the spec's SC-001 through SC-008 explicitly (each row should note which SC it covers).
- **Files**: `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md`
- **Parallel?**: No — blocks T035/T036 (which need this file's path).

### Subtask T035 – INDEX.md entry

- **Purpose**: Make the new runbook discoverable in the master doc index.
- **Steps**:
  1. Read `docs/INDEX.md`.
  2. Find the runbooks section (likely organized by topic).
  3. Add the new smoke runbook with the standard one-line description per the existing pattern: `- [Smoke checklist for felix-admin-calendar extraction (#579)](runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md) — operator-driven post-deploy verification for the mission`.
- **Files**: `docs/INDEX.md`
- **Parallel?**: [P] with T036 after T034.

### Subtask T036 – DEVELOPER_PORTAL.md entry

- **Purpose**: Add the runbook to the developer onboarding sitemap.
- **Steps**:
  1. Read `docs/DEVELOPER_PORTAL.md`.
  2. Find the section that lists active runbooks (likely a "Runbooks & operational guides" subsection).
  3. Add the new runbook entry following the established pattern (probably a short bullet with link + one-sentence description).
- **Files**: `docs/DEVELOPER_PORTAL.md`
- **Parallel?**: [P] with T035 after T034.

## Test Strategy

- Manual review of the runbook against the contract's required sections.
- Link validity: every internal link in the runbook (to spec, to deploy script, to commands) resolves.
- INDEX.md and DEVELOPER_PORTAL.md additions follow the existing visual pattern (consistent indentation, link format).

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Runbook drifts from contract shape | T034 step 2 anchors to the contract literally; reviewer checks section-by-section |
| Operator runs the runbook without the deploy completing → false negatives | Pre-conditions section makes deploy-complete a gate |
| Subagent DM examples too specific (sensitive content) or too generic (not exercising the path) | Use realistic but generic phrasing; doc-auditor and escalation rows specifically NOT a DM test |
| INDEX.md insertion in wrong section | Read the section organization first; group with runbooks not specs or research |

## Review Guidance

- All 6 contract sections present in the runbook (pre-conditions, DM round-trips, non-DM checks, observation window, decision criteria, verification record)?
- Each DM row references a specific SC?
- felix-doc-auditor row uses `last-tick.json` check, NOT a DM?
- INDEX.md and DEVELOPER_PORTAL.md entries are correctly placed and formatted?
- No synthetic-message test substrate proposed?

## Activity Log

> **CRITICAL**: Activity log entries MUST be in chronological order (oldest first, newest last).

- 2026-06-11T03:26:12Z -- system -- Prompt created.
