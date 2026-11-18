---
work_package_id: WP03
title: STAGE entrypoint and manifest
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- NFR-002
- NFR-003
- SC-001
planning_base_branch: feat/vikunja-image-deploy
merge_target_branch: feat/vikunja-image-deploy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-image-deploy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-image-deploy unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-image-deploy-01M65D3V
base_commit: 2ddedd7b794f60c381abeb315348cf99f7b59732
created_at: '2026-10-30T04:29:57.646780+00:00'
subtasks:
- T012
- T013
- T014
- T015
- T016
phase: Phase 2 - Stage
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/deploy-vikunja-release-stage.py
create_intent:
- scripts/deploy/deploy-vikunja-release-stage.py
- deploys/queued/vikunja-release-stage.yaml
- tests/deploy/test_deploy_vikunja_release_stage.py
execution_mode: code_change
owned_files:
- scripts/deploy/deploy-vikunja-release-stage.py
- deploys/queued/vikunja-release-stage.yaml
- tests/deploy/test_deploy_vikunja_release_stage.py
role: implementer
tags: []
tracker_refs: []
---
# Work Package Prompt: WP03 — STAGE entrypoint and manifest

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via the `/spk-charter-profile-load` skill
(profile named in this file's `agent_profile` frontmatter: `python-pedro`). Adopt its identity, governance scope
and boundaries for the whole work package.

## Branch Strategy

Planning branch and final merge target: `feat/vikunja-image-deploy`. Execution worktrees are allocated per computed lane from
`lanes.json`; do not pick a base branch by hand. Implement with:

```bash
spec-kitty agent action implement WP03 --agent claude --mission vikunja-image-deploy-01M65D3V
```

Requirements covered: FR-001, FR-002, FR-003, FR-004, FR-005, NFR-002, NFR-003.

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

An inert load-and-verify step (User Story 1). It never touches a container or the Compose file.

## Subtasks

### T012 — `--dry-run` (FR-001)
Run the store preflight. Stat the archive and check its size and sha (`verify_archive`). Check whether the release tag exists and its ID; check `active`'s state and whether an activation marker exists; check the rollback image's presence. Print the planned actions. Make **zero** mutating calls: assert in a test that the fake runner saw only `inspect`, `info` and `ps` verbs.

### T013 — `--apply` (FR-002, FR-005; R-18 order)
1. Run the dry-run checks.
2. If the release tag already resolves to the config digest, it is a no-op success.
3. Otherwise `docker load -i <archive>` (timeout 300 s). Parse `Loaded image ID: sha256:...`; on the classic store this must equal the config digest, and anything else is `STAGE_LOADED_ID_UNEXPECTED`.
4. Verify `image_facts` against the record.
5. Only then `docker tag <id> <release tag>`.

### T014 — `active` creation and hold (R-3, R-23)
Create `active` → `60fe1ee8…` only if `active` is absent **and no activation marker exists**. If `active` exists, it must resolve to `60fe1ee8…` or to the config digest; otherwise `STAGE_ACTIVE_UNEXPECTED`. If the marker exists and `active` is absent, exit `STAGE_ACTIVE_HELD_BY_ACTIVATION`. Never retag an existing `active`.

### T015 — Refusals (FR-003, FR-004)
These codes exit 1 with no load and no tag:
- archive missing, size mismatch, sha mismatch;
- release tag pointing elsewhere;
- rollback image absent (`STAGE_ROLLBACK_IMAGE_MISSING`);
- unsupported store.

Test each, with the passing fixture as the positive control. A partial failure after load (verification fails) leaves the image untagged and reports `STAGE_VERIFY_FAILED` with the loaded ID (R-18).

### T016 — Manifest `deploys/queued/vikunja-release-stage.yaml`
- `schema_version v1`, `name vikunja-release-stage`, `issue kentonium3/kg-automation#1087`, `tier 2`, `entrypoint scripts/deploy/deploy-vikunja-release-stage.py`.
- `audited_surface true`, `expected_baselines [docker-images.txt]`.
- `verification.pre: [<entrypoint> --dry-run]`; `verification.post`: `docker image inspect --format '{{.Id}}' office2.local/vikunja:v2.7.1-670-420c7bcb75 | grep -qx sha256:35e1bc87...` and the same for `vikunja/vikunja:2.4.0` → `60fe1ee8…`.
- `created_by claude-code-1087`, plus notes.
- Validate it against `deploys/schema/manifest-v1.schema.json` in a test, and check `expected_baselines` with `scripts/deploy/lib/manifest.py`.
- Add a gate-composition test through `scripts.deploy.lib.apply.dry_run_then_apply_gate` with a fake runner (R-18).
- Add the exec-bit test.

## Definition of Done
The test file is green, saved to a file and read. The dry-run is proven side-effect free. Every refusal is paired with a positive control. The manifest validates.
