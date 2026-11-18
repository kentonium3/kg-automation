---
work_package_id: WP05
title: Compose fail-closed sandbox evidence on office2
dependencies: []
requirement_refs:
- FR-017
- C-002
- C-003
planning_base_branch: feat/vikunja-image-deploy
merge_target_branch: feat/vikunja-image-deploy
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-image-deploy. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-image-deploy unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-image-deploy-01M65D3V
base_commit: ff0f01960f72ea2705cc17f16f149bc848fceb24
created_at: '2026-10-30T03:45:58.079719+00:00'
subtasks:
- T023
- T024
- T025
phase: Phase 1 - Foundation
history: []
agent_profile: researcher-robbie
authoritative_surface: docs/design/architecture/evidence/
create_intent:
- docs/design/architecture/evidence/vikunja-lock-sandbox-2026-10.md
execution_mode: code_change
owned_files:
- docs/design/architecture/evidence/vikunja-lock-sandbox-2026-10.md
role: implementer
tags: []
tracker_refs: []
---
# Work Package Prompt: WP05 — Compose fail-closed sandbox evidence on office2

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via the `/spk-charter-profile-load` skill
(profile named in this file's `agent_profile` frontmatter: `researcher-robbie`). Adopt its identity, governance scope
and boundaries for the whole work package.

## Branch Strategy

Planning branch and final merge target: `feat/vikunja-image-deploy`. Execution worktrees are allocated per computed lane from
`lanes.json`; do not pick a base branch by hand. Implement with:

```bash
spec-kitty agent action implement WP05 --agent claude --mission vikunja-image-deploy-01M65D3V
```

Requirements covered: FR-017, C-002, C-003.

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

Produce real-engine evidence (R-22) that, on office2's Docker 29.6.2 and Compose v5.3.1, a service whose image tag is missing, with `pull_policy: never`, fails `up -d` closed: non-zero exit, no running container, no pull. Also show that untagging after `down` keeps the image. The ACTIVATE design (WP04) depends on this result.

## Subtasks

### T023 — Post the sandbox record to #1087 BEFORE running (CLAUDE.md sandbox carve-out)
The comment is Kent-audience, with no @mentions. It names:
- project `vikunja-lock-sandbox`;
- its own default network, no ports, no mounts;
- images `office2.local/sandbox:absent` (missing) and a re-tag of the already-present `vikunja/vikunja:0.24.6` (`cec159e222f5`, unused) as `office2.local/sandbox:present`;
- `mem_limit: 64m`; a `command` that runs `version` and exits;
- the teardown commands;
- the statement that it touches no production state.

### T024 — Run through `ssh office2-claude` only, from `/tmp` on office2 (a compose file written under `/tmp/vikunja-lock-sandbox/`)
Cases:
- (a) `docker events --since <t0> --until <t1> --filter type=image --filter event=pull` captured around (b);
- (b) `up -d` with the absent tag: record the exit code, `docker ps -a` and `docker network ls`, filtered by the label `com.docker.compose.project=vikunja-lock-sandbox`;
- (c) `up -d` with the present tag (positive control), then `down`, then `docker image rm office2.local/sandbox:present`: the image ID `cec159e222f5` still exists under `vikunja/vikunja:0.24.6`;
- (d) `up -d` again after the untag, which fails closed like (b).

Then tear down: `down --remove-orphans`, remove the network if present, and remove the sandbox tags. Verify nothing labelled with the project remains, and that `vikunja` (production) is unchanged: same container ID and same image before and after.

### T025 — Evidence document
Write `docs/design/architecture/evidence/vikunja-lock-sandbox-2026-10.md` with YAML frontmatter (`title`, `doc_type: reference`, `status: approved`), the exact commands, sanitized outputs, and a verdict line `FAIL-CLOSED: CONFIRMED` or `NOT CONFIRMED`.

If NOT CONFIRMED: STOP the mission and report to the operator. WP04 must not proceed on an invalid lock.

## Definition of Done
The document is committed with the verdict. Production is unchanged (before and after recorded). The sandbox is fully removed.
