---
work_package_id: WP06
title: Design/architecture/runbook docs — reframe to physical exclusion
dependencies: []
requirement_refs:
- FR-005
tracker_refs: []
planning_base_branch: feat/retire-private-folder-guards
merge_target_branch: feat/retire-private-folder-guards
branch_strategy: Planning artifacts for this mission were generated on feat/retire-private-folder-guards. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/retire-private-folder-guards unless the human explicitly redirects the landing branch.
subtasks:
- T020
- T021
- T022
agent: "claude:sonnet:reviewer-renata:reviewer"
history: []
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/
create_intent: []
execution_mode: code_change
owned_files:
- docs/design/architecture/glossary.md
- docs/design/architecture/security-posture.md
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data/service-inventory.json
- docs/design/coherence/doctrine.md
- docs/design/felix-capability-roadmap.md
- docs/design/process-flows/inbox-routing.md
- docs/design/process-flows/journal.md
- docs/runbooks/escalation-ops.md
- docs/runbooks/habits-ops.md
- docs/runbooks/inbox-ops.md
- docs/runbooks/openclaw-agent-setup.md
- docs/runbooks/tasker-ops.md
role: implementer
tags: []
shell_pid: "40719"
shell_pid_created_at: "1784652217.539403"
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load curator-carla` before anything else.

## Objective

Reframe docs that present the `_private` folder rule as a *current enforced guard* to the
physical-exclusion model (the boundary is now the folder's absence, not an in-repo rule).
Authoritative detail: `data-model.md` IC-05 rows; FR-005; SC-001.

## Subtasks

- **T020** — Architecture docs: `glossary.md` (redefine the boundary term to physical exclusion),
  `security-posture.md` (the `_private` guard is now "content physically excluded from office2"),
  `service-inventory.md` + `data/service-inventory.json` (drop stale "enforces `_private`" claims;
  keep the JSON well-formed — the arch-data validator is a blocking gate). Bump the JSON metadata
  (`last_updated`, prepend a `#848` note to `updated_by`).
- **T021** — `coherence/doctrine.md` (reframe any decision/doctrine citing the absolute rule),
  `felix-capability-roadmap.md` ("privacy is absolute" entries → physical-exclusion model),
  `process-flows/{inbox-routing,journal}.md` (reframe any "never route/write `_private`" step to the
  general vault-path guard from WP03; do not describe removed behavior as still present).
- **T022** — Runbooks `{escalation-ops,habits-ops,inbox-ops,openclaw-agent-setup,tasker-ops}.md`:
  remove the operational notes that say an agent must carry / enforce the `_private` rule; reframe to
  physical exclusion where context needs it.

## Definition of Done

- No doc in the owned set states the `_private` folder rule as a current enforced guard.
- `python3 tooling/scripts/validate_architecture_data.py` passes (service-inventory.json well-formed).
- `python3 tooling/scripts/validate_docs.py` passes.
- `grep -rn "_private" <owned docs>` returns only intentional physical-exclusion narrative.

## Risks & reviewer guidance

- `service-inventory.json` is a blocking arch-data gate — keep it valid.
- Reviewer: confirm no doc now *describes removed behavior as still present* (e.g. an inbox-routing
  step claiming classify_content refuses `_private`, which WP03 deleted).

## Activity Log

- 2026-07-21T16:26:56Z – claude:sonnet:implementer:implementer – shell_pid=22263 – Assigned agent via action command
- 2026-07-21T16:40:06Z – claude:sonnet:implementer:implementer – shell_pid=22263 – WP06 in lane (e35efa29); 13 docs reframed to physical exclusion, validators green, no stale deleted-behavior claims. From primary per #710.
- 2026-07-21T16:44:09Z – claude:sonnet:reviewer-renata:reviewer – shell_pid=40719 – Started review via action command
