---
work_package_id: WP02
title: Companion Consistency and Validation
dependencies:
- WP01
requirement_refs:
- FR-006
- NFR-003
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T005
- T006
- T007
- T008
agent: "codex:gpt-5:docs-implementer:implementer"
shell_pid: "73650"
history:
- at: '2026-06-06T00:37:37Z'
  by: spec-kitty.tasks
  note: 'Created WP02 from #528 spec and plan artifacts.'
authoritative_surface: CLAUDE.md
execution_mode: code_change
owned_files:
- CLAUDE.md
- .kittify/charter/charter.md
- docs/design/architecture/change-control.md
tags: []
---

# WP02 — Companion Consistency and Validation

## Objective

Check the companion governance documents named in the spec for consistency with
the amended Felix Constitution, make only concrete consistency fixes if needed,
and run documentation validation.

## Context

WP01 adds the constitutional rule. This WP proves the surrounding context
setting surfaces do not contradict that rule. Initial planning found the named
documents already include risk-tier guidance, so edits may not be necessary.

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch =
`main`. Work only in the Spec Kitty worktree assigned to WP02 after WP01 is
complete.

## Subtask T005 — Inspect `CLAUDE.md`

Compare the `Change Control Guardrails` section in `CLAUDE.md` to the amended
constitution.

Leave it unchanged if it remains consistent. If a concrete inconsistency exists,
make the smallest wording change needed to align it with the constitution.

## Subtask T006 — Inspect `.kittify/charter/charter.md`

Compare the `Change-Risk Taxonomy (Tier Protocol)` section in
`.kittify/charter/charter.md` to the amended constitution.

Leave it unchanged if it remains consistent. If a concrete inconsistency exists,
make the smallest wording change needed to align it with the constitution.

## Subtask T007 — Inspect `docs/design/architecture/change-control.md`

Compare the `Risk-Tiered Change Control` section in
`docs/design/architecture/change-control.md` to the amended constitution.

Leave it unchanged if it remains consistent. If a concrete inconsistency exists,
make the smallest wording change needed to align it with the constitution while
preserving `change-risk-taxonomy.json` as canonical.

## Subtask T008 — Run validation and targeted checks

Run:

```bash
python tooling/scripts/validate_docs.py
rg -n "autonomy|risk-tier|change-risk-taxonomy|Tier 0|Tier 1|Tier 2" docs/constitution/FELIX-CONSTITUTION.md
```

If companion docs are changed, run targeted inspection over those files too.

## Definition of Done

- Companion docs are either unchanged by explicit decision or minimally updated
  for concrete consistency.
- `python tooling/scripts/validate_docs.py` passes.
- Targeted constitution inspection confirms the taxonomy reference and Tier 0,
  Tier 1, and Tier 2 wording.
- Implementation notes identify which companion docs were checked.

## Reviewer Guidance

Reject broad rewording or cosmetic churn. This WP is a consistency and
validation pass, not a governance rewrite.

## Activity Log

- 2026-06-06T00:46:13Z – codex:gpt-5:docs-implementer:implementer – shell_pid=73650 – Started implementation via action command
- 2026-06-06T00:47:46Z – codex:gpt-5:docs-implementer:implementer – shell_pid=73650 – Ready for review
