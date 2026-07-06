---
work_package_id: WP04
title: Model doc updates (architecture data + agent registry)
dependencies: []
requirement_refs:
- FR-004
tracker_refs: []
planning_base_branch: feat/harden-inbox-capture
merge_target_branch: feat/harden-inbox-capture
branch_strategy: Planning artifacts for this mission were generated on feat/harden-inbox-capture. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/harden-inbox-capture unless the human explicitly redirects the landing branch.
subtasks:
- T030
- T031
agent: claude
history:
- 2026-07-06 authored from plan IC-03 (docs) + Codex MED-5 (agent-registry.json)
agent_profile: curator-carla
authoritative_surface: docs/constitution/
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/constitution/AGENT-REGISTRY.md
- docs/constitution/agent-registry.json
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, run `/ad-hoc-profile-load curator-carla` (role: implementer).
Then read this WP and `../data-model.md` (AgentModelConfig doc-mirrors).

## Objective

Keep the docs consistent with the capture haiku→sonnet move so nothing split-brains after merge.
Independent doc edits (no dependency on the other WPs). The authoritative JSONs win over
narrative per the repo's documentation standard, so update BOTH the JSON and the md view.

## Subtasks

### T030 — Architecture data + view

- `docs/design/architecture/data/service-inventory.json`: set the `felix-admin-capture` agent
  `model` field `anthropic/claude-haiku-4-5` → `anthropic/claude-sonnet-4-6`. Update the entry's
  `updated_by` per repo convention. **Also correct the openclaw-gateway PYTHONPATH-drop-in claim**
  if present (the drop-in sets the gateway *process* env, but OpenClaw's exec tool strips
  PYTHONPATH from subshells — so agents must invoke helpers with the checkout-cd form; the
  drop-in does NOT make bare `-m scripts` work in exec). Search the JSON for `PYTHONPATH` /
  `pythonpath` / the agent-prompt-sync `exec_start_note` and reconcile the narrative to reality.
- `docs/design/architecture/service-inventory.md`: mirror the capture model change in the md view.
- Run the architecture-data validator (`validate_architecture_data.py`) — it is a blocking
  Docs-CI gate; keep it green.

### T031 — Agent registry (both surfaces, Codex MED-5)

- `docs/constitution/agent-registry.json` (**authoritative**): set `felix-admin-capture.model`
  `anthropic/claude-haiku-4-5` → `anthropic/claude-sonnet-4-6` (line ~10).
- `docs/constitution/AGENT-REGISTRY.md` (narrative): update the capture agent's model/behavior
  note to reflect sonnet + the reliability fix (self-contained invocations; corrects #658).

## Definition of Done

- [ ] `service-inventory.json` + `.md` show capture on `anthropic/claude-sonnet-4-6`.
- [ ] The PYTHONPATH-drop-in narrative reflects exec sanitization reality.
- [ ] `agent-registry.json` + `AGENT-REGISTRY.md` show capture on sonnet.
- [ ] Architecture-data validator + Docs-CI green.

## Reviewer guidance

- Confirm BOTH the authoritative JSON and its md view changed (no split-brain).
- Confirm no OTHER agent's model was altered (only capture).
- Confirm the drop-in claim now matches the exec-sanitization finding.

## Branch Strategy

Planning base `feat/harden-inbox-capture`; final merge target `feat/harden-inbox-capture`.
Independent; parallel with WP02/WP03. Command: `spec-kitty agent action implement WP04 --agent claude`.
