---
work_package_id: WP06
title: actor-level concurrency harness + bootstrap deploy record + docs
dependencies:
- WP04
- WP05
requirement_refs:
- C-002
- C-003
- C-005
- FR-003
- NFR-001
tracker_refs: []
planning_base_branch: fix/prompt-sync-ff-race
merge_target_branch: fix/prompt-sync-ff-race
branch_strategy: Planning artifacts for this mission were generated on fix/prompt-sync-ff-race. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/prompt-sync-ff-race unless the human explicitly redirects the landing branch.
subtasks:
- T019
- T020
- T021
agent: "claude"
history: []
agent_profile: python-pedro
authoritative_surface: tests/deploy/
create_intent:
- tests/deploy/test_actor_concurrency.py
- deploys/applied/0012-prompt-sync-ff-race.yaml
execution_mode: code_change
mission_id: 01KX3SZC2YHPWRCYD7WXQSFZQ7
mission_slug: prompt-sync-ff-race-01KX3SZC
owned_files:
- tests/deploy/test_actor_concurrency.py
- deploys/applied/0012-prompt-sync-ff-race.yaml
- docs/runbooks/deployment.md
- docs/runbooks/security-baseline-ops.md
role: implementer
tags: []
shell_pid: "82925"
---

# WP06 — actor-level concurrency harness + bootstrap deploy + docs

## ⚡ Do This First: Load Agent Profile
Load your assigned profile via `/ad-hoc-profile-load python-pedro` (role: implementer) before anything else.

## Objective
Prove NFR-001 at the **actor level** (the load-bearing proof — a primitive-level
test is not sufficient), then land the deploy record and docs for the controlled
bootstrap.

## Context (read first)
- **Research "Test strategy" fold + D6**: [../research.md](../research.md).
- **Spec NFR-001, FR-003, C-002/003/005**: [../spec.md](../spec.md).
- **Quickstart bootstrap**: [../quickstart.md](../quickstart.md) — the exact deploy sequence.
- **Applied-record pattern**: existing `deploys/applied/*.yaml` (e.g. `0011-*`, the felix-deployer bootstrap record) + `deploys/schema/` for shape.
- Both actors' tick bodies from WP04/WP05.

## Subtasks

### T019 — actor-level concurrency integration harness (`tests/deploy/test_actor_concurrency.py`)
Build one shared temp git checkout with a real origin, **seeded with a stale extra
origin branch** (mimicking `kitty/…-lane-a`). Barrier-synchronize the two real
tick bodies — felix-deployer `run_tick` and prompt-sync `run_tick` — so they enter
their critical sections simultaneously, both using the **same** `deploylock` path.
Run ≥100 overlapped pairs. After each pair assert:
- 0 occurrences of "Cannot fast-forward to multiple branches";
- no residual `.git/index.lock`; clean worktree;
- expected final HEAD (checkout advanced to origin);
- prompt-sync copy still lands its files;
- felix `pre_pull_head`/`post_pull_head` correct for the rebaseline range;
- prompt-sync audit records intact.
Use temp lock path + temp state dirs (never real `/data`). Keep runtime reasonable (mock ntfy/network).

### T020 — bootstrap applied record (`deploys/applied/0012-prompt-sync-ff-race.yaml`)
Author an operator-applied record per the existing applied-record schema
documenting the controlled bootstrap (stop timers → manual ff-merge → verify →
delete stale lane branch → manual rebaseline of `scripts/deploy/lib/**` → restart
timers). Reference #667 and the mission. (If `0012` is taken at deploy time, the
operator renames to the next free number — note this in the file header.)

### T021 — docs
- `docs/runbooks/deployment.md`: document the two-actor shared-checkout lock and
  the controlled-bootstrap deploy pattern (why this class of change can't ride the
  self-pull path; why it's an applied record not a queued manifest).
- `docs/runbooks/security-baseline-ops.md`: note that this bootstrap's audited
  surface is the new `scripts/deploy/lib/**` files and the rebaseline is a manual
  out-of-band reset (drift-confirmed first).
- If a new doc surface is implicated, check `docs/design/architecture/data/signal-to-doc-map.json`.

## Definition of Done
- `python3 -m pytest tests/deploy/test_actor_concurrency.py` green; ≥100 overlapped pairs, all assertions hold.
- Bootstrap applied record present and schema-valid.
- Runbook docs updated; Docs CI green.
- Full test suite green.

## Reviewer guidance
The harness is the mission's central proof — verify it truly runs BOTH real tick
bodies concurrently through ONE lock against ONE checkout with a stale extra
branch, and asserts index-lock cleanliness + rebaseline-range correctness, not
just "no error". Confirm the deploy record matches the quickstart bootstrap and
the docs explain the bootstrap rationale.

## Branch Strategy
Planning on `fix/prompt-sync-ff-race`; final merge target `fix/prompt-sync-ff-race`.
Execution worktrees are allocated per computed lane from `lanes.json`.

## Activity Log

- 2026-07-09T17:33:09Z – claude – shell_pid=82925 – Assigned agent via action command
