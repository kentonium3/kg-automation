---
work_package_id: WP02
title: Substrate lifecycle and the run boundary
dependencies: []
requirement_refs:
- C-004
- C-005
- C-009
- FR-013
- FR-016
- FR-018
- NFR-004
planning_base_branch: feat/849-arms-run
merge_target_branch: feat/849-arms-run
branch_strategy: Planning artifacts for this mission were generated on feat/849-arms-run. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-arms-run unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-arms-run-01M3APTA
base_commit: 1b9271f9762845d1c0536cd9289cf5e48d59d225
created_at: '2026-09-25T00:45:34.370606+00:00'
subtasks:
- T006
- T007
- T008
- T009
- T010
phase: Phase 0 - Foundation
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/substrate.py
create_intent:
- scripts/research/arms849/substrate.py
- scripts/research/arms849/compose/compose.yaml
- scripts/research/arms849/compose/runner.Dockerfile
- tests/research/test_arms849_substrate.py
- tests/research/test_arms849_isolation.py
execution_mode: code_change
owned_files:
- scripts/research/arms849/substrate.py
- scripts/research/arms849/compose/compose.yaml
- scripts/research/arms849/compose/runner.Dockerfile
- tests/research/test_arms849_substrate.py
- tests/research/test_arms849_isolation.py
role: implementer
tags: []
tracker_refs: []
---

# Work Package Prompt: WP02 — Substrate lifecycle and the run boundary

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/849-arms-run`
- **Final merge target**: `feat/849-arms-run`
- `/spec-kitty.implement` populates the actual worktree `base_branch` from `lanes.json`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Everything that touches the machine: pinned installs, the two services, the oracle-free export,
and the **runner container whose only mounts are the export, the corpus and the ledger directory**
— the boundary that makes FR-013 true rather than hoped. Read first: `research.md` D-8 and D-9
(the sandbox note — this WP implements exactly that envelope, no more), D-11 (tokenizer cache),
§Supply chain (pins and the no-torch rule); `contracts/gates.md` `boundary` and `env_clean`;
`docs/design/research/849-synthesis/gate-b-context-window.md` (the known-good serving flags);
`~/models/gguf/unsloth/Qwen3-Next-80B-A3B-Instruct-GGUF/SOURCE.md`.

**Nothing here deploys to office2** (C-005). All ports bind to `127.0.0.1`. The GGUF is mounted
read-only and never copied.

## Subtasks

### T006 — `substrate.py setup`: pinned installs and caches

**Steps**:
1. `python3 -m scripts.research.arms849.substrate setup` installs, via
   `uv pip install --python .venv/bin/python`, exactly: `graphiti-core==0.30.2 falkordb==1.7.1
   fastembed==0.8.1 openai==3.19.2`, then `--no-deps transformers tokenizers huggingface-hub`
   (adversarial A2). Afterwards assert `torch` is **not** importable; fail loudly if it is.
2. Pull images by digest: FalkorDB — resolve the full digest from the record on
   kentonium3/kg-automation#976 (SOURCE prefix `sha256:9042fdc4…`; verify with
   `docker manifest inspect` and record the full value in `build/849-runs/setup.json`); llama.cpp
   `ghcr.io/ggml-org/llama.cpp@sha256:063e88aef1c168cf4a0a4b3a7983604561f96870a3c4953bd1fad908b4e41716`.
3. Fetch and cache `BAAI/bge-small-en-v1.5` via fastembed and the Qwen tokenizer files via
   `huggingface_hub` into `build/849-cache/`; record sha256 of every cached file in `setup.json`.
   This is the **only** step that may reach the network; write that in the docstring.
4. Verify the GGUF sha256 against `SHA256SUMS` (streaming; 46 GB) and record it.

**Validation**: `setup.json` lists every pin, digest and sha; a second run is idempotent.

### T007 — `substrate.py up | down | health` and `compose/compose.yaml`

**Steps**:
1. `compose/compose.yaml`, project name `arms849`: services `falkordb` (image by digest,
   `127.0.0.1:16379:6379`, volume `arms849-falkor`), `llama` (image by digest, `127.0.0.1:18080:8080`,
   `--device /dev/dri`, `group_add: ["992"]`, GGUF dir mounted `:ro`, command from gate (b):
   `-m /models/<file> --parallel 1 --n-gpu-layers 999 --jinja --host 0.0.0.0 --port 8080
   --ctx-size ${N_CTX}` plus, when `${ROPE}` is `yarn`: `--rope-scaling yarn --rope-scale 2
   --yarn-orig-ctx 262144`); network `arms849-net` (bridge, `internal: true` for the runner, with
   the two services also on it). Health checks: `redis-cli -p 6379 PING` for FalkorDB;
   `curl -sf localhost:8080/health` for llama.
2. `up [--yarn]` sets `N_CTX=262144`/`393216` and `ROPE`, runs `docker compose -p arms849 up -d`,
   waits for both health checks (bounded, prints progress), then `health()` verifies FalkorDB
   answers `GRAPH.LIST` and llama `/props` reports the expected model file, `n_ctx` and rope
   settings. Return a `SubstrateState` the harness records.
3. `down`: `docker compose -p arms849 down -v --rmi all`; then **verify** no container, volume,
   network or image matching `arms849|falkor|llama` remains and GTT (`mem_info_gtt_used`) is under
   2 GiB; print the SC-008 check; the GGUF is untouched.
4. `health` as a standalone command used by the harness's retry policy (FR-007).

**Validation**: `live` test: up → health ok → down → nothing remains.

### T008 — `substrate.py export`: the oracle-free export

**Steps**:
1. `export [--commit HEAD]`: `git archive <commit>` extracted into `build/849-run-env/` with
   these paths **excluded**: `docs/design/research/849-synthesis/oracle/`,
   `docs/design/research/849-synthesis/seed/`, `docs/design/research/849-synthesis/00-context-chains.md`,
   `docs/design/research/849-synthesis/01-cast.md`, `docs/design/research/849-lattice-scenario-arcs.md`,
   `docs/design/research/849-traceability.md`, and `kitty-specs/` entirely (planning docs quote
   oracle material). Keep `scripts/`, `tests/`, `pyproject`/venv metadata, the rubric.
2. Write `build/849-run-env/.export-manifest.json`: source commit, the exclusion list, and
   `content_sha` = sha256 over (path + sha256(content)) for every exported file in sorted path
   order (D-16, adversarial A3 — content, not names).
3. Refuse to export if the working tree at `<commit>` is dirty (the export must equal a commit).

**Validation**: the excluded paths do not exist under the export; `content_sha` changes when any
exported file changes; a dirty tree refuses.

### T009 — `substrate.py run` + `compose/runner.Dockerfile`: the boundary

**Steps**:
1. `runner.Dockerfile`: `python:3.12-slim`, copy nothing from the repo; install the same pins as
   T006 from a `requirements-arms849.txt` you generate in the export at build time; no `torch`.
2. `run -- <harness args>`: `docker run --rm --network arms849-net` with mounts **only**:
   `build/849-run-env:/work:ro`, `build/849-corpus:/corpus:ro`, `build/849-cache:/cache:ro`,
   `build/849-runs:/runs:rw`; env `ARMS849_CORPUS=/corpus`, `ARMS849_CACHE=/cache`,
   `HF_HUB_OFFLINE=1`, no `OPENAI_API_KEY`; working dir `/work`; command
   `python3 -m scripts.research.run_849_harness <args>` with service URLs `http://llama:8080` and
   `falkordb:6379` (compose DNS on the network).
3. **Denied-access self-test** (`run --self-test`): from inside the container assert that
   `/home`, the host checkout path, `/work/docs/design/research/849-synthesis/oracle`, `/work/docs/design/research/849-synthesis/seed`, `/work/kitty-specs` do not exist; that `/work` is read-only
   (a write raises `OSError`); that outbound DNS to any non-compose name fails; print each
   assertion. WP04's `boundary` gate calls this.

**Validation**: `live` test: self-test passes; a deliberately added extra mount makes it fail.

### T010 — Tests

**Files**: `tests/research/test_arms849_substrate.py` (compose file renders the expected ports,
digests, flags for both primary and yarn; export exclusion list; content_sha stability; dirty-tree
refusal — all static), `tests/research/test_arms849_isolation.py` (the static half of FR-013: no
module under `scripts/research/arms849/` contains `oracle`, `seed/` or `traceability`; the export
exclusion list covers every path in `research.md` D-8). Mark container tests `@pytest.mark.live`
and skip unless `ARMS849_LIVE=1`.

## Definition of Done

- `setup`, `up`, `health`, `down`, `export`, `run` all work on office4; `down` leaves the machine
  as SC-008 requires; the self-test proves the boundary.
- The sandbox note in `research.md` D-9 matches what the code does — if you must deviate, update
  the note in the same commit and say why in the commit message.
- Tests green (static in CI; `live` locally); `mark-status T006 T007 T008 T009 T010 --status done`.

## Risks / reviewer guidance

- The `internal: true` network must still let the runner reach both services — verify with the
  self-test, not by reading the YAML.
- `--rmi all` also removes the llama image; that is intended (re-pull is cheap; the GGUF is not).
- Reviewer: run `run --self-test` yourself; a boundary nobody has seen fail is not a boundary.
