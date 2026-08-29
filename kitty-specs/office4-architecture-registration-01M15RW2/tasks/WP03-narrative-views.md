---
work_package_id: WP03
title: Narrative views — four-device topology and security posture
dependencies:
- WP01
requirement_refs:
- FR-009
planning_base_branch: feat/office4-architecture-registration
merge_target_branch: feat/office4-architecture-registration
branch_strategy: Planning artifacts for this mission were generated on feat/office4-architecture-registration. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/office4-architecture-registration unless the human explicitly redirects the landing branch.
subtasks:
- T012
- T013
- T014
phase: Phase 2 - Narrative
history:
- at: '2026-08-29T04:12:16Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/physical-topology.md
create_intent: []
execution_mode: code_change
model: ''
owned_files:
- docs/design/architecture/physical-topology.md
- docs/design/architecture/security-posture.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 – Narrative views

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `curator-carla`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objectives & Success Criteria

Bring the human-readable narratives into agreement with the authoritative JSON WP01 landed.

Done when neither file asserts a three-device tailnet, both agree with
`network-topology.json`, and `validate_docs.py` exits 0.

## Context & Constraints

- **Depends on WP01.** JSON is authoritative; these views follow it (charter policy). Read
  the merged `network-topology.json` and `hardware-inventory.json` first and let them drive
  the prose.
- office4 is an **unmanaged peer** — attended, not a deploy target. Nothing you write may
  imply it hosts services or is a felix-deployer target.
- Tier 4. No host or service change.

## Branch Strategy

- **Strategy**: single_branch
- **Planning base branch**: `feat/office4-architecture-registration`
- **Merge target branch**: `feat/office4-architecture-registration`

## Subtasks & Detailed Guidance

### Subtask T012 – Add office4 to `physical-topology.md`

- **Purpose**: this is the narrative counterpart of `hardware-inventory.json`, and
  `change-control.md:20` names it as the view that follows new hardware.
- **Steps**: read the file whole. Add office4 wherever devices are enumerated, matching the
  existing treatment of the Mac and iPhone — peers get lighter treatment than office2.
  Include: Tailscale name `office4`, IP `100.112.83.28`, Linux Mint 22.3 (noble base),
  Framework Desktop (AMD Ryzen AI Max 300 Series), role = attended primary development
  machine.
- **Notes**: if the file contains a diagram or device count, update it too. Do not
  restructure the document; add office4 into its existing shape.

### Subtask T013 – Correct three-device assumptions in `security-posture.md`

- **Purpose**: the access model text was written when the tailnet had three devices. Some of
  it may be true for three and subtly wrong for four.
- **Steps**: **read the whole file** — do not grep for "three" and stop. Look for: device
  enumerations, statements about which machines can reach what, any claim that all tailnet
  devices are X, and any statement about SSH exposure.
- **Facts you may rely on** (research.md R-12): office4 has **Tailscale SSH off**
  (`RunSSH: false`); it exposes **no port**; it runs **no service**. So the security posture
  genuinely does not change in substance — but the *text* must still stop implying three
  devices.
- **If you conclude no change is needed**, say so explicitly in your Activity Log entry with
  the reasoning. Silence is indistinguishable from not having looked.

### Subtask T014 – Confirm narrative matches the authoritative JSON

- **Steps**: re-read both edited files against `network-topology.json` and
  `hardware-inventory.json`. Every device name, IP, and OS string in prose must match the
  JSON exactly.
- Run `python3 tooling/scripts/validate_docs.py` — must exit 0.
- **Validation**: no contradiction between prose and JSON; no device present in one and
  absent from the other.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Prose drifts from JSON | T014 is an explicit reconciliation pass, not an afterthought |
| Implying office4 hosts services | It runs none; describe it as an attended peer |
| Grepping instead of reading `security-posture.md` | T013 requires a whole-file read |
| "Reviewed, no change" being indistinguishable from "not opened" | Record the conclusion and reasoning in the Activity Log |

## Review Guidance

- Confirm both files name four tailnet devices consistently.
- Confirm every IP and OS string in prose matches the JSON byte for byte.
- Confirm nothing describes office4 as a host, server, or deploy target.
- If `security-posture.md` is unchanged, confirm the Activity Log explains why.

## Activity Log

- 2026-08-29T04:12:16Z – system – Prompt created.
