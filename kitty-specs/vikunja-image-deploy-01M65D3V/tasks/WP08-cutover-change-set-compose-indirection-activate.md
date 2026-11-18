---
work_package_id: WP08
title: 'Cutover change set: Compose indirection, ACTIVATE manifest, inventory'
dependencies:
- WP04
requirement_refs:
- FR-007
- FR-016
- C-003
- C-004
planning_base_branch: feat/vikunja-image-deploy
merge_target_branch: feat/vikunja-image-deploy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-image-deploy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-image-deploy unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-image-deploy-01M65D3V
base_commit: 9daa0e9586a22213e8a76a9240b0ee053b93a6b5
created_at: '2026-10-30T05:32:14.082932+00:00'
subtasks:
- T033
- T034
- T035
- T036
phase: Phase 4 - Cutover set
history: []
agent_profile: python-pedro
authoritative_surface: services/vikunja/docker-compose.yml
create_intent:
- deploys/queued/vikunja-release-activate.yaml
- tests/deploy/test_vikunja_cutover_change_set.py
execution_mode: code_change
owned_files:
- services/vikunja/docker-compose.yml
- deploys/queued/vikunja-release-activate.yaml
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- tests/deploy/test_vikunja_cutover_change_set.py
role: implementer
tags: []
tracker_refs: []
---
# Work Package Prompt: WP08 — Cutover change set: Compose indirection, ACTIVATE manifest, inventory

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via the `/spk-charter-profile-load` skill
(profile named in this file's `agent_profile` frontmatter: `python-pedro`). Adopt its identity, governance scope
and boundaries for the whole work package.

## Branch Strategy

Planning branch and final merge target: `feat/vikunja-image-deploy`. Execution worktrees are allocated per computed lane from
`lanes.json`; do not pick a base branch by hand. Implement with:

```bash
spec-kitty agent action implement WP08 --agent claude --mission vikunja-image-deploy-01M65D3V
```

Requirements covered: FR-007, FR-016, C-003, C-004.

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

The files that make up the ACTIVATE merge. They are kept as a separately mergeable set: the go packet assembles the STAGE merge without these files (WP09).

## Subtasks

### T033 — Compose (FR-007)
Change `image: vikunja/vikunja:2.4.0` to `image: office2.local/vikunja:active` and add `pull_policy: never` directly under it. Nothing else changes. Test: compare against `git show <base>:services/vikunja/docker-compose.yml`. The diff is exactly those two lines; the mounts, ports, environment (including `VIKUNJA_DATABASE_PATH`), restart policy and container name are byte-identical. Update the header comment only if a test allows it, otherwise leave it.

### T034 — ACTIVATE manifest
- `name vikunja-release-activate`, `tier 2`, `entrypoint scripts/deploy/deploy-vikunja-release-activate.py`.
- `audited_surface true`, `expected_baselines [docker-images.txt]`.
- `verification.pre [<entrypoint> --dry-run]`.
- `verification.post`: the release-exact reconcile `docker inspect vikunja --format '{{.Image}}' | grep -qx sha256:35e1bc87...` plus `curl -fsS --max-time 5 http://100.92.197.90:3456/api/v1/info | jq -e '.version == "v2.7.1-670-420c7bcb75"'`.
- The notes reference R-21's residual risk and the cancel and retry paths.
- Schema-validation test.

### T035 — Service inventory (FR-016)
In `service-inventory.json`, set the vikunja `image` to `office2.local/vikunja:active` and add a version note (`v2.7.1-670-420c7bcb75`, built from `420c7bcb75…`, archive sha). Set `updated_by` to `#1087`. Update the markdown view to match. Run the repo's doc validation (`python scripts/validate_docs.py` or the Makefile target), save the output to a file and read it.

### T036 — Change-set test
A test enumerating the exact path set of this WP. The go packet's STAGE assembly uses the complement; WP09 documents it.

## Definition of Done
Tests and doc validation are green. The two-line Compose diff is proven.
