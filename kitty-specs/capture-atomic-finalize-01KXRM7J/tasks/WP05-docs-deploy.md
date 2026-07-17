---
work_package_id: WP05
title: Documentation sync + deploy
dependencies:
- WP01
- WP02
- WP03
- WP04
requirement_refs:
- FR-017
tracker_refs: []
planning_base_branch: fix/capture-atomic-finalize
merge_target_branch: fix/capture-atomic-finalize
branch_strategy: Planning artifacts for this mission were generated on fix/capture-atomic-finalize. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/capture-atomic-finalize unless the human explicitly redirects the landing branch.
subtasks:
- T022
- T023
- T024
- T025
phase: Phase 4 - Close-out
agent: claude
history:
- at: '2026-07-17T18:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/runbooks
create_intent:
- deploys/queued/capture-atomic-finalize.yaml
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- docs/runbooks/inbox-ops.md
- docs/design/architecture/data/service-inventory.json
- deploys/queued/capture-atomic-finalize.yaml
- docs/design/felix-capability-roadmap.md
role: implementer
tags: []
---

# Work Package Prompt: WP05 – Documentation sync + deploy

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `curator-carla`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch: `fix/capture-atomic-finalize`. Merge target: `fix/capture-atomic-finalize`. Execution worktree per `lanes.json`.

## Objective

Synchronize documentation to the note-level finalize behavior (DIR-014) and prepare the
office2 deploy. **Read first**: `../plan.md` (Deploy Plan / IC-06), `../research.md` (D7),
`[[reference_office2_agent_deploy_paths]]`, and the actual doc/JSON surfaces before editing.

**Consult** `docs/design/architecture/data/signal-to-doc-map.json` (filter
`match.source == "mission-architecture-impact"`, change classes `runbook-modified`,
`systemd-unit-added-or-modified` is N/A here, `service-added-or-modified` for the new
health-check) for the canonical doc targets so INDEX/DEVELOPER_PORTAL are not missed.

## Subtasks

### T022 — Runbook
- Update the existing inbox/capture runbook `docs/runbooks/inbox-ops.md` to describe the
  note-level finalize flow: agent classifies blocks → assembles routing plan → one
  `route_and_finalize` → the atomic route/verify/log/mark guarantee; the health rail +
  IDLE-gate surfacing; the `needs-review` and `empty` terminals.

### T023 — Architecture data + navigation
- Add the new `processed-without-routing-log` health-check to
  `docs/design/architecture/data/service-inventory.json` (and its markdown view) with a
  freshness/health entry consistent with the existing schema; run
  `python3 tooling/scripts/validate_architecture_data.py` (the blocking Docs-CI gate).
- Update `docs/INDEX.md` / `docs/DEVELOPER_PORTAL.md` if a new doc surface was added.

### T024 — Deploy manifest + deploy story
- Deploy split: helpers (`scripts/inbox/*`, `prescan.py`) land via office2 checkout
  self-pull (felix-deployer); the capture `AGENTS.md`/`TOOLS.md` deploy via `agent-prompt-sync`
  to `/data/services/openclaw/inbox-agent/` (slug ≠ dir). Add a `deploys/queued/` manifest
  ONLY if an office2 apply step beyond the self-pull is required; otherwise document that no
  manifest is needed and why. If added, validate against `deploys/schema/manifest-v1.schema.json`.
- Record the rebaseline decision: expected **not required** (#621 — AGENTS.md not a hashed
  audited surface; `scripts/inbox/` not in `audited-surfaces.json`) — confirm against
  `docs/design/architecture/data/audited-surfaces.json`.

### T025 — Roadmap status
- Update `docs/design/felix-capability-roadmap.md` capture-reliability status to reflect the
  atomic-finalize completion.

## Definition of Done
- `validate_docs`, `validate_privacy_boundary`, and `validate_architecture_data` all green
  (pre-commit will run them).
- Docs describe the shipped note-level behavior; navigation docs updated if surfaces changed.
- Deploy story documented; manifest (if any) schema-valid; rebaseline decision recorded.

## Risks / reviewer guidance
- Do not invent a runbook filename — list `docs/runbooks/` and edit the real one.
- Reviewer: confirm the service-inventory health-check entry validates and the deploy story
  matches the actual felix-deployer + agent-prompt-sync mechanics.
