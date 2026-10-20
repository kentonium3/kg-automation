---
work_package_id: WP02
title: Architecture record and runbook
dependencies:
- WP01
requirement_refs:
- FR-007
- FR-008
planning_base_branch: feat/970-qa-decommission
merge_target_branch: feat/970-qa-decommission
branch_strategy: Planning artifacts for this mission were generated on feat/970-qa-decommission. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/970-qa-decommission unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-qa-pipeline-decommission-01M219TT
base_commit: 69bc1268db278003c308e9272fad352e42b905fd
created_at: '2026-09-08T21:07:20.746176+00:00'
subtasks:
- T006
- T007
- T008
- T009
phase: Phase 2 - Record
history:
- timestamp: '2026-09-08T20:30:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/
create_intent:
- docs/runbooks/qa-pipeline-decommission.md
execution_mode: code_change
lane: planned
owned_files:
- docs/design/architecture/**
- docs/runbooks/**
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP02 – Architecture record and runbook

Read first: `../plan.md`, `../data-model.md` (§Inventory retirement shape),
WP01's produced manifest + scripts (dependency), and
`docs/design/architecture/data/signal-to-doc-map.json` (filter
`mission-architecture-impact`, change classes `service-added-or-modified`,
`credential-added-or-modified`, `data-flow-added-or-modified`,
`network-topology-changed`, `runbook-added`).

- **T006** `service-inventory.json`: both QA entries → `status: retired`,
  `health_check` → none (#712 status-gate precedent), retirement note naming
  this mission, #970, and the archive bundle path. Keep JSON valid against
  `validate_architecture_data.py`.
- **T007** listening-ports data drops `:8443`/`:3457`/`:8788`; credentials
  data retires the `/etc/qa-webhook.env` entry (archived-then-removed, note
  where); data-flow records drop the Linear→office2 ingress; update the
  markdown counterparts (`security-posture.md` public-ingress claim — office2
  now has ZERO public ingress — and any narrative naming the QA components).
- **T008** signal-to-doc-map sweep: touch every `doc_targets` entry for the
  engaged change classes (`docs/INDEX.md`, `docs/DEVELOPER_PORTAL.md`,
  topology/network docs as the map dictates). #492 precedent: navigation docs
  are routinely missed — do not skip.
- **T009** `docs/runbooks/qa-pipeline-decommission.md`: short operator note —
  when the deployer applies the manifest, how Kent runs
  `operator-root-steps.sh`, what the verify output means, the rebaseline gate,
  the archive location + restore sketch (NFR-002), retention expectations
  (B-03).

Definition of done: `python3 tooling/scripts/validate_docs.py` and the
architecture-data validator pass; every signal-to-doc-map target for the
engaged classes reviewed (updated or explicitly noted why unchanged).
