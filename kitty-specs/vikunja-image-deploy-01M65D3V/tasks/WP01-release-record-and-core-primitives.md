---
work_package_id: WP01
title: Release record and core primitives
dependencies: []
requirement_refs:
- FR-002
- FR-003
- FR-006
- FR-018
- FR-019
- C-006
- C-007
- NFR-002
planning_base_branch: feat/vikunja-image-deploy
merge_target_branch: feat/vikunja-image-deploy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-image-deploy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-image-deploy unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-image-deploy-01M65D3V
base_commit: 338744276f7217fd11aaf3acfe88522386631009
created_at: '2026-10-30T03:48:12.125263+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1 - Foundation
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/vikunja_release/
create_intent:
- services/vikunja/release.json
- scripts/deploy/vikunja_release/__init__.py
- scripts/deploy/vikunja_release/core.py
- tests/deploy/test_vikunja_release_core.py
- tests/deploy/fixtures/vikunja_release/index.json
execution_mode: code_change
owned_files:
- services/vikunja/release.json
- scripts/deploy/vikunja_release/__init__.py
- scripts/deploy/vikunja_release/core.py
- tests/deploy/test_vikunja_release_core.py
- tests/deploy/fixtures/vikunja_release/**
role: implementer
tags: []
tracker_refs: []
---
# Work Package Prompt: WP01 — Release record and core primitives

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via the `/spk-charter-profile-load` skill
(profile named in this file's `agent_profile` frontmatter: `python-pedro`). Adopt its identity, governance scope
and boundaries for the whole work package.

## Branch Strategy

Planning branch and final merge target: `feat/vikunja-image-deploy`. Execution worktrees are allocated per computed lane from
`lanes.json`; do not pick a base branch by hand. Implement with:

```bash
spec-kitty agent action implement WP01 --agent claude --mission vikunja-image-deploy-01M65D3V
```

Requirements covered: FR-002, FR-003, FR-006, FR-018, FR-019, C-006, C-007, NFR-002.

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

Build the pinned release record and the core library that both entrypoints, the ingress helper and the rollback helper use. The library holds only pure or injectable primitives: no entrypoint logic.

## Subtasks

### T001 — `services/vikunja/release.json`
Create the file exactly per `data-model.md` ReleaseRecord. Values:
- `release_version` `v2.7.1-670-420c7bcb75`; `source_revision` `420c7bcb75231be9b6571fdfdf76a1a62f2aebd8`.
- archive: path `/data/services/vikunja/release-artifacts/48008c5067a6/image.tar`, sha256 `48008c5067a6555cb880200d5416a7989df6be06246cc41bc69d1da685581f79`, size `54450688`.
- image: config digest `sha256:35e1bc8790292deedf2addc3f3f196e38d84c2614219a95d6ef711c1f02afba5`, index digest `sha256:2be2b8c20475294c74447414548437eca49b1fcf972f292813737eea6578ffb6`, platform `linux/amd64`, user `1000`.
- tags: release `office2.local/vikunja:v2.7.1-670-420c7bcb75`, active `office2.local/vikunja:active`.
- rollback: image ID `sha256:60fe1ee8f729c17b057ba00a49b968adb4ed1e774cea36b5f4cc81340991a7d2`, ref `vikunja/vikunja:2.4.0`, archive path `/data/services/vikunja/release-artifacts/48008c5067a6/vikunja-2.4.0.image.tar`, sha256 `b63e5529ba35e695aec3b240f835a5ea412a2b0552f2a1b054e5d0d9a9aaa9ad`, size `115518464`.
- service: compose file `/home/claude/kg-automation/services/vikunja/docker-compose.yml`, project `vikunja`, container `vikunja`, info URL `http://100.92.197.90:3456/api/v1/info`, data dir `/data/services/vikunja/data`.
- roots: snapshots `/data/services/vikunja/snapshots`, activation `/data/services/vikunja/activation`, private log root `/data/services/vikunja/failures`, office4 sources (for ingress): `/home/kgale/.local/share/rrule-office2-images/420c7bcb75231be9b6571fdfdf76a1a62f2aebd8/image.tar` and `/home/kgale/.local/share/rrule-office2-images/rollback-v2.4.0-60fe1ee8/vikunja-2.4.0.image.tar`.

Add `load_release(path)`. It validates every key and type and the hex formats, and raises `ReleaseError` with a stable code. Test a malformed record and a missing key, each with a valid-record positive control.

### T002 — Errors and output allowlist (R-16)
- Add a `Fail(code, detail_private=None)` exception and an `emit(summary, **fields)` writer that allows only `str` codes, hex IDs, ints and paths.
- The CLI exit helpers give 0, 1 or 2.
- Add a private-log writer that writes raw text to a 0700 folder with a 0600 file, and returns only the path.
- Privacy test: seed `password=hunter2`, a fake task title and a fake user name into raw text. Assert that `emit` output and stdout contain none of them, while the private file does (positive control).

### T003 — Bounded runner (R-15)
- `run(argv, timeout, runner=subprocess.run)` returns `(rc, stdout, stderr)`. On `TimeoutExpired` it raises `Fail("TIMEOUT_<step>")`. No `shell=True`.
- Add a monotonic `Deadline(seconds, clock=time.monotonic)` with `remaining()` and `check(step)`.
- Tests use a fake runner raising `TimeoutExpired`, and a fake clock.

### T004 — Docker store preflight and identity (R-13)
- `docker_store_ok(runner)` accepts only `Driver == overlay2` with no `io.containerd.snapshotter` entry in `DriverStatus`; anything else raises `DOCKER_STORE_UNSUPPORTED`.
- `image_id(ref)` comes from `docker image inspect --format {{.Id}}` and returns `None` when the image is absent.
- `image_facts(ref)` returns Architecture, Os, Config.User and the revision label.
- `container_image(name)` returns `(.Image, .Config.Image)`, or `None`.
- The fixtures are the captured shapes from R-13; build the fake runner around them.

### T005 — Offline archive chain check (R-13)
- `verify_archive(path, record)`: size, then sha256, streamed in 1 MiB chunks.
- Then read the tar members without extracting to disk: `index.json` must name the index digest; the `manifest.json` `Config` must equal `blobs/sha256/<config hex>`; the config blob's sha256 must equal its name; and the config's architecture, os, `config.User` and revision label must match the record.
- Fixture: build a tiny synthetic OCI tar in `tmp_path` with the same structure. Copy the real `index.json` and `manifest.json` shapes into `tests/deploy/fixtures/vikunja_release/`; the digests in the synthetic tar are computed by the test.
- Mutation tests: a wrong config hash, a wrong label and a wrong arch each fail, with the intact tar as the positive control.

### T006 — Durable marker I/O (R-12)
- `marker_create(path, data)`: `os.open(O_CREAT|O_EXCL|O_WRONLY, 0o600)`, write, `fsync`, then `fsync` the parent folder.
- `marker_update(path, data)`: write a temp file in the same folder, `fsync`, `os.replace`, `fsync` the parent.
- `marker_read(path)` returns `None` when absent, the dict when valid, and raises `MARKER_UNREADABLE` when it is malformed or has an unknown phase or outcome.
- The phase set and outcome set come from `data-model.md`, plus the outcome `rolled_back`.
- Tests: a second exclusive create fails; an interrupted update (simulate a crash before `replace`) leaves the old content readable; a malformed marker refuses.

## Definition of Done
- All six subtasks are covered by tests, with positive controls.
- `python -m pytest tests/deploy/test_vikunja_release_core.py -q` is green, saved to a file and read.
- There is no entrypoint logic in `core.py`, and no dead code: every function has a caller in a later WP or a test, and later WPs are listed as callers in a module docstring.

## Reviewer guidance
Check the identity chain against R-13 exactly, the allowlist against R-16, and that nothing uses `shell=True`.
