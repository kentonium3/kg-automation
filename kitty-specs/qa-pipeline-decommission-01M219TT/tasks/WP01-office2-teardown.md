---
work_package_id: WP01
title: Office2 teardown artifacts
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-008
- FR-010
planning_base_branch: feat/970-qa-decommission
merge_target_branch: feat/970-qa-decommission
branch_strategy: Planning artifacts for this mission were generated on feat/970-qa-decommission. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/970-qa-decommission unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-qa-pipeline-decommission-01M219TT
base_commit: 69bc1268db278003c308e9272fad352e42b905fd
created_at: '2026-09-08T20:19:29.977547+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Teardown artifacts
history:
- timestamp: '2026-09-08T20:30:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/decommission/office2/
create_intent:
- scripts/decommission/office2/teardown.sh
- scripts/decommission/office2/operator-root-steps.sh
- scripts/decommission/office2/verify.sh
- deploys/queued/0xxx-qa-pipeline-decommission.yaml
execution_mode: code_change
lane: planned
owned_files:
- scripts/decommission/office2/**
- deploys/queued/**
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP01 – Office2 teardown artifacts

Read first: `../plan.md` (§Approach ordering steps 1–8), `../data-model.md`
(archive bundle), `../contracts/teardown-verification.md`,
`docs/runbooks/deploy/discipline.md`, an existing applied manifest under
`deploys/applied/` for format, and `scripts/deploy/lib/` for vetted primitives.

- **T001 `teardown.sh`** (runs on office2 as claude, invoked by the manifest):
  step order exactly as plan §Approach: `docker stop` qa-register → build the
  claude archive bundle at
  `/data/services/host-state/decommission/qa-pipeline-2026-09-08/` (register
  db sextet, service.env, start-webhook.sh, qa-webhook.log, code-copy tarball,
  `docker save` image export, `docker inspect` metadata, sha256
  `CLAUDE-MANIFEST.txt`) → verify the manifest before ANY removal → SIGTERM
  webhook pid + confirm exit → remove launcher trio → remove container, all
  `qa-register`-repo images, `/data/services/qa-register/`,
  `/home/claude/spec-kitty-qa/`. Idempotent: each step no-ops cleanly when its
  surface is already absent. `--dry-run` prints the action list. Never print
  env file contents. Docker via `sg docker -c` if needed.
- **T002 `operator-root-steps.sh`** (Kent runs via ssh office2-kgale + sudo):
  archive `/etc/qa-webhook.env` into the bundle (0600 root), append
  `ROOT-MANIFEST.txt`, remove the file, capture current funnel config to the
  bundle, turn Funnel off for :8443 — verify the off-syntax against
  `tailscale funnel --help` ON office2 and cite it in a comment — then write
  `operator-complete.txt`. Refuse to run as non-root. Idempotent.
- **T003 `verify.sh`**: implement contract checks V-01..V-13, V-15 (office2)
  with tri-state output lines and exit semantics per the contract. V-14 (the
  external funnel probe) belongs to the Mac-side runner in WP03's directory?
  NO — keep V-14 in this script behind `--external` flag runnable from the
  Mac (it only needs curl). UNCHECKABLE ≠ ABSENT everywhere (Principle 14).
- **T004 manifest** `deploys/queued/` (next free number,
  `qa-pipeline-decommission.yaml`): copies scripts, runs teardown.sh, then a
  final gate action that FAILS until `operator-complete.txt` exists and
  `verify.sh` exits 0 (deployer retries each tick until Kent runs T002);
  declares `expected_baselines: [listening-ports.txt, docker-images.txt]`.
  Follow discipline.md format exactly; use lib primitives where they fit.
- **T005 validation**: `bash -n` all scripts; run `--dry-run` locally;
  a small test (under `tests/`) asserting verify.sh's tri-state classifier
  distinguishes ABSENT/PRESENT/UNCHECKABLE on stubbed probe outputs (the
  Principle-14 property: a probe error must never classify as ABSENT).

Definition of done: all files created, tests/dry-runs green, `git status`
clean after commit, no secrets in any committed file.
