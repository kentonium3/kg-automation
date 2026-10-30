---
work_package_id: WP09
title: Runbooks and the go packet
dependencies:
- WP03
- WP04
- WP05
- WP06
- WP07
- WP08
requirement_refs:
- FR-015
- FR-016
- SC-004
- NFR-004
- C-001
- C-005
planning_base_branch: feat/vikunja-image-deploy
merge_target_branch: feat/vikunja-image-deploy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-image-deploy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-image-deploy unless the human explicitly redirects the landing branch.
subtasks:
- T037
- T038
- T039
- T040
phase: Phase 5 - Docs
history: []
agent_profile: curator-carla
authoritative_surface: docs/runbooks/
create_intent:
- docs/runbooks/vikunja-release-cutover.md
execution_mode: planning_artifact
owned_files:
- docs/runbooks/vikunja-ops.md
- docs/runbooks/deploy/discipline.md
- docs/runbooks/vikunja-release-cutover.md
role: implementer
tags: []
tracker_refs: []
---
# Work Package Prompt: WP09 — Runbooks and the go packet

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via the `/spk-charter-profile-load` skill
(profile named in this file's `agent_profile` frontmatter: `curator-carla`). Adopt its identity, governance scope
and boundaries for the whole work package.

## Branch Strategy

Planning branch and final merge target: `feat/vikunja-image-deploy`. Execution worktrees are allocated per computed lane from
`lanes.json`; do not pick a base branch by hand. Implement with:

```bash
spec-kitty agent action implement WP09 --agent claude --mission vikunja-image-deploy-01M65D3V
```

Requirements covered: FR-015, FR-016, SC-004, NFR-004.

## Mission-wide rules (read before coding)

- Authoritative design: `kitty-specs/vikunja-image-deploy-01M65D3V/research.md`. **R-9 to R-24 take precedence over R-1 to R-8** where they conflict (post-plan and confirmation reviews). Contracts: `contracts/entrypoints.md`, including its Amendments section. Entities: `data-model.md`.
- Entrypoints accept exactly `--dry-run` or `--apply`; anything else exits 2 with usage on stderr (`docs/runbooks/deploy/discipline.md:254-257`). Python entrypoints need the `parents[2]` `sys.path` shim (`discipline.md:355-359`) and git mode 100755 (assert it in a test, as in `tests/deploy/test_deploy_health_check_coverage.py:212`).
- **Output allowlist (R-16, FR-019):** stdout and stderr carry only fixed summary lines and stable error codes, image IDs, hashes, timestamps, counts and paths. Never echo raw Docker or Compose stderr or container logs; write them to the private 0700 folder. Seeded secrets, names and titles must not leak (privacy test).
- **Deadlines (R-15, FR-018):** every subprocess call passes `timeout=`; every HTTP request has a 5 s timeout; there is a monotonic overall deadline where specified. Inject the clock and runner, never sleep in tests.
- **No sudo, no other account, no registry pull, no edit of the live Compose file** (C-002, C-003, C-006). Do not run anything against office2 from tests: `tests/deploy/conftest.py` blocks `/data` writes. Use `tmp_path` roots injected through module parameters.
- **Tests:** pytest under `tests/deploy/`. Load entrypoints with `importlib.util.spec_from_file_location` and inject the runner, clock, roots and opener. Every refusal or absence assertion has a **same-fixture positive control** (tactic acceptance-criteria-non-vacuity). Fixtures mirror real inputs: use the captured shapes in research R-13 and the real archive's `index.json`, `manifest.json` and config JSON (no production data in them).
- Run tests with `make test` or `python -m pytest tests/deploy/<file> -q`. Save the output to a file and read the file.
- Conventional commits ending with `(#1087)`. Use a scoped `git add`.

## Objective

Correct the stale runbooks and write the operator go packet as a durable runbook (SC-004).

## Subtasks

### T037 — `docs/runbooks/vikunja-ops.md` (FR-016)
Replace the stale upgrade section at `:87-132` (version in `vikunja.service`/`deploy.sh`, `0.24.6`) with the Compose-plus-indirection route: STAGE, ACTIVATE and rollback, linking the new runbook. Note that `scripts/vikunja/deploy.sh` is legacy and cannot select an archive.

### T038 — `docs/runbooks/deploy/discipline.md` (R-20)
Correct `:470-475` (failure records do not block retries; a manifest re-runs every tick) and `:612-614` (the applier rebaselines, deferred-confirm). Add the ACTIVATE-style one-shot marker and the cancel and retry pattern (R-17, R-24) as guidance for any non-idempotent manifest.

### T039 — `docs/runbooks/vikunja-release-cutover.md` (the go packet; FR-015, SC-004)
YAML frontmatter, then:
- preconditions;
- **candidate validation** (R-19: copy to `/data/services/vikunja/candidate-<sha12>/`, run both dry-runs, with the expected unmet set);
- ingress (WP07 commands);
- **STAGE merge assembly** (the branch built from `feat/vikunja-image-deploy` minus the WP08 path set, and the exact `git` commands to create it, for Kent to merge);
- post-STAGE host readiness;
- **ACTIVATE merge** (the WP08 set; Kent's explicit go);
- acceptance (agent checks, then Kent's UI login and a recurring-task editor check);
- the R-21 residual risk;
- rollback (WP06 `--prepare`, then Kent's printed `sudo install`, then `--finish`, then the manual rebaseline);
- cancel and retry (R-17, R-24);
- STAGE partial-failure recovery (R-18).

Every Kent step is marked **Kent** with the exact command. Note the contract amendment: both helpers are Python.

### T040 — Doc validation
Run the repo doc validation, save the output to a file, read it, and fix any findings.

## Definition of Done
Doc validation is green. Every operator step has an exact command. There are no `@mentions`.
