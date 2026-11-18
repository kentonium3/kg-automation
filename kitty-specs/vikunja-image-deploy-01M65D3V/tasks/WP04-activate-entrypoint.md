---
work_package_id: WP04
title: ACTIVATE entrypoint
dependencies:
- WP01
- WP02
- WP05
requirement_refs:
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
- FR-017
- FR-018
- FR-020
- NFR-001
- NFR-002
- SC-002
planning_base_branch: feat/vikunja-image-deploy
merge_target_branch: feat/vikunja-image-deploy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-image-deploy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-image-deploy unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-image-deploy-01M65D3V
base_commit: b82cfc9f5096e8f3eab060765808a8fb1f324183
created_at: '2026-10-30T04:59:21.100647+00:00'
subtasks:
- T017
- T018
- T019
- T020
- T021
- T022
phase: Phase 3 - Activate
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/deploy-vikunja-release-activate.py
create_intent:
- scripts/deploy/deploy-vikunja-release-activate.py
- tests/deploy/test_deploy_vikunja_release_activate.py
execution_mode: code_change
owned_files:
- scripts/deploy/deploy-vikunja-release-activate.py
- tests/deploy/test_deploy_vikunja_release_activate.py
role: implementer
tags: []
tracker_refs: []
---
# Work Package Prompt: WP04 — ACTIVATE entrypoint

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via the `/spk-charter-profile-load` skill
(profile named in this file's `agent_profile` frontmatter: `python-pedro`). Adopt its identity, governance scope
and boundaries for the whole work package.

## Branch Strategy

Planning branch and final merge target: `feat/vikunja-image-deploy`. Execution worktrees are allocated per computed lane from
`lanes.json`; do not pick a base branch by hand. Implement with:

```bash
spec-kitty agent action implement WP04 --agent claude --mission vikunja-image-deploy-01M65D3V
```

Requirements covered: FR-008, FR-009, FR-010, FR-011, FR-012, FR-017, FR-018, FR-020, NFR-001, NFR-002.

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

The cutover (User Story 2), implemented exactly per the contract Amendments and R-9 to R-24. It depends on WP05's engine evidence: if WP05 records that Compose does not fail closed, STOP and escalate.

## Subtasks

### T017 — Preconditions and `--dry-run` (FR-008, R-10, R-19)
Report each precondition separately, then exit 1 if any is unmet. The preconditions:
- classic store;
- the release tag resolves to the config digest, with facts verified;
- `active` resolves to `60fe1ee8…`;
- the running container's `.Image` is `60fe1ee8…`, whether the configured reference is `vikunja/vikunja:2.4.0` or `active`;
- the live Compose file (read-only) has `image: office2.local/vikunja:active` and `pull_policy: never`;
- the data files are readable;
- free space on `/data` is at least 3× the DB plus WAL;
- the marker is absent.

Make zero mutating calls (assert the verb set). A test shows the expected unmet set before the ACTIVATE merge is exactly {compose not on `active`}.

### T018 — Marker and replay (FR-012, FR-020, R-12, R-24)
- With the marker absent, create it durably with phase `started`.
- Replay with `success` re-checks read-only that the running image is the config digest and `/api/v1/info` reports the version; that is exit 0, otherwise `ACTIVATE_SUCCESS_NOT_RECONCILED`.
- `rolled_back` exits 1 with `ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST`.
- `failed` or in-progress exits 1 with `ACTIVATE_PRIOR_ATTEMPT_<phase>`.
- A malformed marker exits 1 with `MARKER_UNREADABLE`.
- None of the replay paths make any Docker or Compose call, except the read-only reconcile on `success`. Assert the verbs.

### T019 — Stop, lock and snapshot (FR-009, INV-2)
1. Start the 300 s outage deadline.
2. `docker compose -f <file> -p vikunja down` (120 s), using the unit's arguments exactly.
3. `docker image rm office2.local/vikunja:active` (tag only; assert the image ID still exists).
4. Assert no `vikunja` container exists.
5. `snapshot(...)`.
6. Update the marker to `snapshotted` with the snapshot dir and sha.

If the snapshot fails, exit with the lock **held** and nothing started (`SNAPSHOT_*`). INV-1 is safe here because the DB is unmigrated, but the code must not re-tag `active`.

### T020 — Select, start and verify (FR-010, INV-1)
1. `docker tag <config digest> office2.local/vikunja:active`, then marker `retagged`. From this point no code path may tag `active` to `60fe1ee8…`; assert this in a test by scanning every fake-runner call after `retagged`.
2. `compose up -d` (120 s), then marker `started_new`.
3. Verify: the container's `.Image` is the config digest; `wait_ready` with the version within the remaining deadline; `capture_logs` and `migration_ok`.
4. Marker `verified` with outcome `success`. Print the summary: IDs, snapshot sha, task count before and after (aggregate).

### T021 — Failure handling (FR-011, R-14, R-21)
On any failure after `down`, run the cleanup with its own 120 s budget:
1. `capture_logs` (if a container exists);
2. `compose down`;
3. untag `active`;
4. marker outcome `failed` with `failed_phase` and a stable code;
5. exit 1.

It never starts 2.4.0. Inject a failure at each step (timeout, non-zero exit, wrong version, migration-log missing). For each, assert the final state: the lock is held, there is no container, the marker is `failed`, and there is **no** call tagging `active` to `60fe1ee8…`. The happy path is the positive control.

### T022 — Outage deadline and privacy (NFR-001, FR-018, FR-019)
- The fake clock crosses 300 s mid-readiness, giving failure handling with `ACTIVATE_OUTAGE_DEADLINE`.
- Seeded secrets and titles in fake Docker stderr and logs never appear in stdout, stderr or the marker.
- The exec-bit test.

## Definition of Done
The test file is green, saved to a file and read. Every phase-failure test asserts the INV-1 call-scan and the lock-held end state. Zero-mutation dry-run and replay tests pass.
