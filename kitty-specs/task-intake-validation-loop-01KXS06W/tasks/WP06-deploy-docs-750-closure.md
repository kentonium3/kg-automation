---
work_package_id: WP06
title: Deploy manifest, docs sync,
dependencies:
- WP01
- WP02
- WP03
- WP04
- WP05
requirement_refs:
- FR-015
tracker_refs:
- '750'
planning_base_branch: feat/task-intake-validation-loop
merge_target_branch: feat/task-intake-validation-loop
branch_strategy: Planning artifacts for this mission were generated on feat/task-intake-validation-loop. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/task-intake-validation-loop unless the human explicitly redirects the landing branch.
subtasks:
- T023
- T024
- T025
- T026
phase: Phase 5 - Release
agent: claude
history:
- at: '2026-07-17T21:55:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/runbooks/intake-ops.md
create_intent:
- deploys/queued/task-intake-validation-loop.yaml
- docs/runbooks/intake-ops.md
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- deploys/queued/task-intake-validation-loop.yaml
- docs/runbooks/intake-ops.md
- docs/design/vikunja-configuration-design.md
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data-flows.md
- docs/design/felix-capability-roadmap.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
role: implementer
tags: []
---

# Work Package Prompt: WP06 — Deploy manifest, docs sync, #750 closure

## ⚡ Do This First: Load Agent Profile

Use `/ad-hoc-profile-load` to load the profile and behave per its guidance first.

- **Profile**: `curator-carla` · **Role**: `implementer` · **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch / merge target: `feat/task-intake-validation-loop`. Worktree per `lanes.json`. **Last WP** — runs after WP01–05.

## Objective

Provision the deploy and synchronize every documentation surface, and record the #750
closure. Consult `docs/design/architecture/data/signal-to-doc-map.json` for the exact
`doc_targets` for the change classes this mission touches (`service-added-or-modified`,
`data-flow-added-or-modified`, `runbook-added`) — INDEX/DEVELOPER_PORTAL are routinely
missed (#492); include them.

## Subtasks

### T023 — Deploy manifest (C-002, R7)
`deploys/queued/task-intake-validation-loop.yaml`: create
`/data/services/openclaw/state/intake/` (+ `digests/`) on office2; assert the kent-token
secret `/data/services/openclaw/secrets/vikunja-api-kent` is present (file-presence check, no
secret content). Helpers deploy via office2 checkout self-pull; agent prompts via
`agent-prompt-sync`. Follow `docs/runbooks/deploy/discipline.md`. Record **`Rebaseline: not
required — #621`** (AGENTS.md not hashed; confirmed Codex #13).

### T024 — Design doc
`docs/design/vikunja-configuration-design.md`: mark the §Required Fields validation loop as
**implemented** (link the mission), describe the ride-inbox-crons cadence + compact-shorthand +
content-based correlation + two-token writes.

### T025 — Architecture data + runbook + navigation
Update `docs/design/architecture/data/service-inventory.json` (+ `service-inventory.md`) with the
intake scan/apply as a capability of the `inbox-processing` cron + new state dir + observability
artifacts; `data-flows.json` (+ `data-flows.md`) for the scan→digest→reply→apply flow. Author
`docs/runbooks/intake-ops.md` (health check, state-dir layout, shorthand grammar, 30-second
check à la habits-ops). Add both to `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md`.

### T026 — Roadmap + #750 closure
`docs/design/felix-capability-roadmap.md`: bump the Felix↔Vikunja integration thread status. Add
a #750 closure note (felix-bot-can't-attach gap closed by kent-token writes, SC-008). Ensure the
architecture-data validator (`validate_architecture_data.py`) stays green.

## Definition of Done
- Manifest validates (tier guard + file-presence); `Rebaseline: not required — #621` recorded.
- All doc surfaces per signal-to-doc-map updated (incl. INDEX + DEVELOPER_PORTAL); validators green.
- #750 closure documented.

## Risks / reviewer guidance
- **Reviewer:** confirm signal-to-doc-map coverage (no missed surface — #492); manifest asserts the kent-token secret; JSON-authoritative-then-md ordering; `validate_docs` + `validate_architecture_data` green.

## Implementation command
`spec-kitty agent action implement WP06 --agent claude`
