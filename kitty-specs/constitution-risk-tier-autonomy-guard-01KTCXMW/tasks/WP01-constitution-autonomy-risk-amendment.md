---
work_package_id: WP01
title: Constitution Autonomy/Risk Amendment
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-constitution-risk-tier-autonomy-guard-01KTCXMW
base_commit: ba54c27612daf41a12253f90102d0d36f6354b90
created_at: '2026-06-06T00:40:23.302105+00:00'
subtasks:
- T001
- T002
- T003
- T004
shell_pid: '73650'
history:
- at: '2026-06-06T00:37:37Z'
  by: spec-kitty.tasks
  note: 'Created WP01 from #528 spec and plan artifacts.'
authoritative_surface: docs/constitution/
execution_mode: code_change
owned_files:
- docs/constitution/FELIX-CONSTITUTION.md
tags: []
---

# WP01 — Constitution Autonomy/Risk Amendment

## Objective

Amend `docs/constitution/FELIX-CONSTITUTION.md` so Directive 2 explicitly
states that agent autonomy level never grants permission to bypass deployed-
change risk-tier gates.

## Context

The Felix Constitution currently defines Assisted, Observed, and Autonomous
levels as the model for how agent activity is surfaced to Kent. The deployed
change-risk taxonomy is already canonical in
`docs/design/architecture/data/change-risk-taxonomy.json`, but the constitution
does not yet connect autonomy level to those gates.

This WP closes that interpretive gap without changing the autonomy model,
promotion rules, demotion rules, or the Tier 0-4 taxonomy.

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch =
`main`. Work only in the Spec Kitty worktree assigned to WP01.

## Subtask T001 — Locate the Directive 2 insertion point

Read Directive 2 in `docs/constitution/FELIX-CONSTITUTION.md`. The preferred
placement is after the three autonomy level definitions and before
`**Promotion rules:**`.

Preserve all existing Assisted, Observed, Autonomous, promotion, and demotion
wording unless an adjacent sentence needs minor transition wording.

## Subtask T002 — Add autonomy/risk-tier binding wording

Add a concise paragraph or subsection stating that autonomy level determines
activity surfacing and routine execution posture, while deployed-change risk
tier determines required change-control gates.

The wording must clearly satisfy FR-001:

- Autonomy level does not grant permission to bypass risk-tier protocols.
- Autonomous Level 3 is not production-mutation authority.

Keep it principle-level and reviewable in under five minutes.

## Subtask T003 — Reference the canonical taxonomy

Reference `docs/design/architecture/data/change-risk-taxonomy.json` as the
canonical Tier 0-4 taxonomy.

Do not copy the full tier table into the constitution. The constitution should
point readers to the canonical source and summarize only the autonomy effect.

## Subtask T004 — Verify Tier 0 and Tier 1/2 obligations

Ensure the amendment states:

- Tier 0 remains operator-only regardless of autonomy level, urgency framing,
  or user phrasing.
- Tier 1 and Tier 2 changes remain subject to their defined gates, including
  pre-flight, approval, backup/snapshot, and verification obligations where
  applicable.

## Validation

Run targeted inspection:

```bash
rg -n "autonomy|risk-tier|change-risk-taxonomy|Tier 0|Tier 1|Tier 2" docs/constitution/FELIX-CONSTITUTION.md
```

## Definition of Done

- `docs/constitution/FELIX-CONSTITUTION.md` contains the new Directive 2
  clarification.
- The canonical taxonomy JSON path is present in the new wording.
- Tier 0 and Tier 1/Tier 2 obligations are named at principle level.
- Existing autonomy levels and promotion/demotion rules are not weakened.

## Reviewer Guidance

Review for interpretive clarity, not breadth. Reject if the WP duplicates the
taxonomy table, changes promotion/demotion semantics, or makes companion-doc
edits outside the WP ownership boundary.
