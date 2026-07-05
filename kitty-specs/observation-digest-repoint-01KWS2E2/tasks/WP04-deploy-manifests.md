---
work_package_id: WP04
title: Deploy manifests (two, staged)
dependencies:
- WP02
- WP03
requirement_refs:
- FR-008
- FR-009
tracker_refs: []
planning_base_branch: fix/observation-digest-repoint
merge_target_branch: fix/observation-digest-repoint
branch_strategy: Planning artifacts for this mission were generated on fix/observation-digest-repoint. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/observation-digest-repoint unless the human explicitly redirects the landing branch.
subtasks:
- T012
- T013
agent: "claude"
shell_pid: "58081"
history:
- created by /spec-kitty.tasks 2026-07-05
agent_profile: implementer-ivan
authoritative_surface: deploys/queued/0008-migrate-observation-logs.yaml
create_intent:
- deploys/queued/0008-migrate-observation-logs.yaml
- deploys/staged/0009-decommission-observation-stray-tree.yaml
execution_mode: code_change
owned_files:
- deploys/queued/0008-migrate-observation-logs.yaml
- deploys/staged/0009-decommission-observation-stray-tree.yaml
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile: `/ad-hoc-profile-load implementer-ivan` (role: implementer). Read this WP and
the reference manifest before writing.

## Objective

Author the two staged felix-deployer manifests (FR-009): Phase 1 (migrate, non-destructive) and
Phase 2 (decommission). Both Tier-2, Restic snapshot-gated.

## Context & reference

- Copy the schema/shape from `deploys/queued/0007-migrate-inbox-state-and-logs.yaml` (the #656
  Tier-2 migration manifest). Validate against `tests/deploy/test_manifest_schema.py` and
  `docs/runbooks/deploy/discipline.md`.
- Entrypoints (from WP02/WP03): `scripts/deploy/migrate-observation-logs.py` and
  `scripts/deploy/decommission-observation-stray-tree.py`. `scripts/deploy/lib/apply.py` invokes
  `[entrypoint, "--apply"]` — so each manifest points at ONE entrypoint (no extra args).

### Subtask T012 — Phase-1 manifest `0008-migrate-observation-logs.yaml`

- `tier: 2`; `pre`: Restic snapshot gate (mirror 0007's `verify_restic_recent`).
- `apply`: run `scripts/deploy/migrate-observation-logs.py --apply`.
- `post`: confirm vault log dir writable / present (a check the deployer can run).
- Mark `audited_surface: true` (deploy-pipeline) so felix-deployer auto-rebaselines.
- Notes: non-destructive; verify ≥1 clean digest cycle before Phase 2 is staged.

### Subtask T013 — Phase-2 manifest `0009-decommission-observation-stray-tree.yaml`

- `tier: 2`; `pre`: Restic snapshot gate.
- `apply`: run `scripts/deploy/decommission-observation-stray-tree.py --apply`.
- `post`: `test ! -e /home/claude/second-brain`.
- Notes: **queued but applied only after Phase 1 is verified** — the operator stages this
  deliberately; document that dependency in the manifest notes. `audited_surface: true`.

## Branch Strategy

Base/merge target: `fix/observation-digest-repoint`. Depends on WP02+WP03 (entrypoints exist).
Worktrees per-lane from `lanes.json`.

## Test Strategy

`pytest tests/deploy/test_manifest_schema.py -q` — both new manifests parse and validate.

## Definition of Done

- [ ] Two manifests present, schema-valid, Tier-2, snapshot-gated, `audited_surface: true`.
- [ ] Each points at its single entrypoint via `--apply`.
- [ ] Phase-2 manifest documents the "after Phase 1 verified" staging dependency.

## Risks / Reviewer guidance

- Reviewer verifies the manifest numbers don't collide (0008/0009 are the next free numbers).
- Reviewer confirms Phase-2 `post` includes the `test ! -e` absence check.
- Reviewer confirms neither manifest passes destructive flags implicitly; the gate lives in the
  Phase-2 entrypoint (WP03), not the manifest.

## Activity Log

- 2026-07-05T14:06:33Z – claude – shell_pid=54736 – Assigned agent via action command
- 2026-07-05T14:13:57Z – claude – shell_pid=54736 – Moved to for_review
- 2026-07-05T14:14:14Z – claude – shell_pid=58081 – Started review via action command
- 2026-07-05T14:14:26Z – user – shell_pid=58081 – Review passed: 0008 queued (Phase 1, non-destructive, schema test 7-pass), 0009 staged (Phase 2, felix-deployer scans queued/ only so not auto-applied; operator git-mv to promote after Phase-1 verify), both tier2 snapshot-gated audited_surface:false, entrypoints correct, staged manifest schema-valid
