---
work_package_id: WP07
title: Ingress helper
dependencies:
- WP01
requirement_refs:
- FR-006
- C-002
planning_base_branch: feat/vikunja-image-deploy
merge_target_branch: feat/vikunja-image-deploy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-image-deploy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-image-deploy unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-image-deploy-01M65D3V
base_commit: 844559e4f127de7e893b975c1161666223fcbaf7
created_at: '2026-10-30T04:30:04.149521+00:00'
subtasks:
- T030
- T031
- T032
phase: Phase 2 - Stage
history: []
agent_profile: python-pedro
authoritative_surface: scripts/vikunja/stage_release_archive.py
create_intent:
- scripts/vikunja/stage_release_archive.py
- tests/deploy/test_vikunja_stage_release_archive.py
execution_mode: code_change
owned_files:
- scripts/vikunja/stage_release_archive.py
- tests/deploy/test_vikunja_stage_release_archive.py
role: implementer
tags: []
tracker_refs: []
---
# Work Package Prompt: WP07 — Ingress helper

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via the `/spk-charter-profile-load` skill
(profile named in this file's `agent_profile` frontmatter: `python-pedro`). Adopt its identity, governance scope
and boundaries for the whole work package.

## Branch Strategy

Planning branch and final merge target: `feat/vikunja-image-deploy`. Execution worktrees are allocated per computed lane from
`lanes.json`; do not pick a base branch by hand. Implement with:

```bash
spec-kitty agent action implement WP07 --agent claude --mission vikunja-image-deploy-01M65D3V
```

Requirements covered: FR-006, C-002.

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

Copy both archives from the PM's office4 custody paths into the create-only, `claude`-owned 0700 folder on office2 through `ssh office2-claude`, re-verifying each sha (R-4). It runs on **office4**.

## Subtasks

### T030 — `--dry-run`
Read `services/vikunja/release.json`. Hash both office4 sources and compare with the record. Over SSH, check that the destination folder does **not** exist (`test ! -e`) and that free space on `/data` is at least 2× the total size. Make no remote change. Refuse any source path under `/home/codex` or any destination outside `/data/services/vikunja/release-artifacts/`.

### T031 — Transfer
1. `ssh office2-claude 'umask 077 && mkdir <dest>'`. This is create-only: an existing folder means `INGRESS_DEST_EXISTS`.
2. For each archive, stream through `ssh office2-claude 'set -o noclobber; cat > <dest>/<name>'`, with a timeout scaled to the size.
3. Remote `sha256sum` must equal the record. On mismatch, `rm -f` that file only and fail `INGRESS_SHA_MISMATCH`.
4. Print both remote shas.

It never overwrites or uses another account. Inject the ssh runner in tests.

### T032 — Tests
Cover a source sha mismatch, an existing destination, the codex-path refusal and a remote sha mismatch, each with the passing run as the positive control. Assert that every remote argv starts with `ssh office2-claude` and never contains `office2-kgale` or `office2-codex`.

## Definition of Done
The test file is green, saved to a file and read. **Do not run the real transfer in this WP.** The transfer is an operator step after the mission's reviews (go packet).
