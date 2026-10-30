---
work_package_id: WP06
title: Rollback helper
dependencies:
- WP02
requirement_refs:
- FR-013
- FR-014
- FR-015
- FR-017
- NFR-004
- SC-003
planning_base_branch: feat/vikunja-image-deploy
merge_target_branch: feat/vikunja-image-deploy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-image-deploy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-image-deploy unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-image-deploy-01M65D3V
base_commit: a6f58aaa676338af7781c7d47ec9089ecb519ea5
created_at: '2026-10-30T04:59:27.954369+00:00'
subtasks:
- T026
- T027
- T028
- T029
phase: Phase 3 - Activate
history: []
agent_profile: python-pedro
authoritative_surface: scripts/vikunja/rollback_release.py
create_intent:
- scripts/vikunja/rollback_release.py
- tests/deploy/test_vikunja_rollback.py
execution_mode: code_change
owned_files:
- scripts/vikunja/rollback_release.py
- tests/deploy/test_vikunja_rollback.py
role: implementer
tags: []
tracker_refs: []
---
# Work Package Prompt: WP06 — Rollback helper

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via the `/spk-charter-profile-load` skill
(profile named in this file's `agent_profile` frontmatter: `python-pedro`). Adopt its identity, governance scope
and boundaries for the whole work package.

## Branch Strategy

Planning branch and final merge target: `feat/vikunja-image-deploy`. Execution worktrees are allocated per computed lane from
`lanes.json`; do not pick a base branch by hand. Implement with:

```bash
spec-kitty agent action implement WP06 --agent claude --mission vikunja-image-deploy-01M65D3V
```

Requirements covered: FR-013, FR-014, FR-015, FR-017, NFR-004.

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

The operator rollback helper (User Story 3). It runs **on office2** as `claude`; the agent invokes it through `ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py ...'`. It is Python, not the contract's `.sh`, for testability; the contract amendment note is in WP09.

## Subtasks

### T026 — CLI and phases
The CLI is `rollback_release.py --snapshot <dir> (--dry-run | --prepare | --finish)`.
- `--prepare`: capture logs privately → `compose down` → untag `active` → copy the failed DB files into `failures/<UTC>/`. Then print **Kent's exact restore command**:
  ```
  sudo install -o kgale -g root -m 644 <snapshot>/vikunja.db /data/services/vikunja/data/vikunja.db && sudo rm -f /data/services/vikunja/data/vikunja.db-wal /data/services/vikunja/data/vikunja.db-shm
  ```
  It is run by Kent through `ssh office2-kgale`. Then exit 0. The helper types nothing on Kent's behalf.
- `--finish`: `rollback_guard` (WP02) → `docker tag 60fe1ee8… office2.local/vikunja:active` → `compose up -d` → `wait_ready(expect 2.4.0 version string, read from the running 2.4.0 /api/v1/info before cutover and recorded in snapshot.json; if unavailable, require the major.minor 2.4)` → marker outcome `rolled_back`.
- `--dry-run` reports the state only.

### T027 — Guard enforcement (FR-014)
`--finish` refuses on any guard code with no tag and no up. Tests: each guard refusal leaves `active` untagged and no container, with the clean restored DB as the positive control.

### T028 — Post-cutover writes (spec edge case)
`--prepare` prints the count of tasks changed after the snapshot timestamp: `updated > snapshot time`, aggregate only. It refuses `--finish` unless `--ack-post-cutover-writes <count>` matches. That makes Kent's disposition explicit.

### T029 — Out-of-band follow-ups
On completion, print the manual-rebaseline command from `docs/runbooks/security-baseline-ops.md` and the queue-cancel step (R-17). Tests check the printed allowlisted lines.

## Definition of Done
The test file is green, saved to a file and read. Every refusal has a positive control. The helper never calls sudo (assert no `sudo` in any argv).
