---
work_package_id: WP02
title: DB snapshot, rollback guard and readiness primitives
dependencies:
- WP01
requirement_refs:
- FR-009
- FR-010
- FR-011
- FR-014
- FR-017
- FR-018
- FR-019
planning_base_branch: feat/vikunja-image-deploy
merge_target_branch: feat/vikunja-image-deploy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-image-deploy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-image-deploy unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-image-deploy-01M65D3V
base_commit: ca3012e5dab8af19e93338ef95066ba944f765bb
created_at: '2026-10-30T04:29:51.028174+00:00'
subtasks:
- T007
- T008
- T009
- T010
- T011
phase: Phase 1 - Foundation
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/vikunja_release/
create_intent:
- scripts/deploy/vikunja_release/dbsafety.py
- scripts/deploy/vikunja_release/readiness.py
- tests/deploy/test_vikunja_release_db.py
- tests/deploy/test_vikunja_release_readiness.py
execution_mode: code_change
owned_files:
- scripts/deploy/vikunja_release/dbsafety.py
- scripts/deploy/vikunja_release/readiness.py
- tests/deploy/test_vikunja_release_db.py
- tests/deploy/test_vikunja_release_readiness.py
role: implementer
tags: []
tracker_refs: []
---
# Work Package Prompt: WP02 — DB snapshot, rollback guard and readiness primitives

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via the `/spk-charter-profile-load` skill
(profile named in this file's `agent_profile` frontmatter: `python-pedro`). Adopt its identity, governance scope
and boundaries for the whole work package.

## Branch Strategy

Planning branch and final merge target: `feat/vikunja-image-deploy`. Execution worktrees are allocated per computed lane from
`lanes.json`; do not pick a base branch by hand. Implement with:

```bash
spec-kitty agent action implement WP02 --agent claude --mission vikunja-image-deploy-01M65D3V
```

Requirements covered: FR-009, FR-010, FR-011, FR-014, FR-017, FR-018, FR-019.

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

The database-safety and readiness primitives: the write-boundary snapshot (R-6 and INV-2 in R-21), the rollback guard (R-11), `/api/v1/info` readiness (R-8, R-15) and bounded private log capture (R-14).

## Subtasks

### T007 — Snapshot (R-6)
`snapshot(data_dir, snap_root, clock)`:
1. Create `snap_root/<UTC>/` and `raw/` with mode 0700.
2. Copy `vikunja.db` plus any `-wal`/`-shm` into `raw/`, hashing each.
3. Open `raw/vikunja.db` read-write (in the writable snapshot folder), run `PRAGMA wal_checkpoint(TRUNCATE)`, then `VACUUM INTO '<snap>/vikunja.db'`.
4. Run `PRAGMA integrity_check` on the result, which must equal `ok`.
5. Record the sha256, `SELECT count(*) FROM tasks` (an aggregate) and the source hashes.
6. Write `snapshot.json` through WP01's durable writer pattern.

Report each written file through `scripts.deploy.lib.installed_report.record_installed`, which satisfies `tests/deploy/test_host_copies_report.py`.

Tests:
- **WAL test:** a fixture DB with committed rows only in the WAL must have them in the snapshot. As the positive control, a main-file-only copy misses them.
- A corrupted source fails `integrity_check` with `SNAPSHOT_INTEGRITY_FAILED`.
- Busy timeout and a 120 s budget (R-15).

### T008 — Migration detector
`is_migrated(db_path_copy)` returns True if the table `task_repeat_legacy_backup` exists **or** `tasks` has a `repeats` column. It opens the private copy with `mode=ro`.

Fixtures: build a v2.4.0-shaped schema (`repeat_after`/`repeat_mode`, no `repeats`) and a migrated shape. Do not invent other columns; copy the column names from the real migration in the Vikunja harness notes, or use just these two signals.

### T009 — Rollback guard (R-11)
`rollback_guard(runner, data_dir, snapshot_json)` runs in this order, refusing at the first failure with a stable code:
1. No `vikunja` container exists: `docker ps -a --filter name=^vikunja$ -q` is empty (`GUARD_CONTAINER_PRESENT`).
2. `active` is untagged (`GUARD_LOCK_NOT_HELD`).
3. `vikunja.db-wal` and `vikunja.db-shm` are both absent (`GUARD_SIDECAR_PRESENT`).
4. The data DB's sha256 equals the snapshot's `vikunja.db` sha (`GUARD_SHA_MISMATCH`).
5. Copy it privately, then `is_migrated(copy)` is False (`GUARD_DB_MIGRATED`).

Any exception refuses (`GUARD_INSPECTION_ERROR`). Tests:
- each refusal, plus a fully passing case on the same fixture;
- a residual migrated WAL;
- a non-writable data folder (`chmod 0555` on `tmp_path`) still passes when clean, proving no write is attempted.

### T010 — Readiness (R-8, R-15)
`wait_ready(url, expect_version, deadline, opener=urllib.request.urlopen, sleep=...)` polls every 5 s with a 5 s per-request timeout, inside the deadline. It returns only on HTTP 200 with JSON `version == expect_version`, otherwise `READY_TIMEOUT` or `READY_WRONG_VERSION`. The body is never echoed (`version` only).

Tests: a fake opener with a 503 then a 200; the wrong version; a hang (`socket.timeout`); and deadline expiry with an injected clock.

### T011 — Private log capture (R-14)
`capture_logs(runner, container, dest_dir)` runs `docker logs --timestamps <c>` with a 30 s timeout and writes at most 10 MB into a 0600 file. It returns the path or `None`; capture failure never raises past the caller. `migration_ok(log_path)` checks for the line `Ran all migrations successfully`. It returns only a bool plus the RRULE summary line's counts (digits only).

Test: seeded titles and secrets in a fake log never reach stdout, and the bool is correct.

## Definition of Done
Both test files are green, saved to a file and read. Every refusal is paired with a positive control. Nothing writes outside injected roots.
