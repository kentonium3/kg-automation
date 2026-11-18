---
work_package_id: WP02
title: Host overrides, live node and red-first proof
dependencies:
- WP01
requirement_refs:
- FR-003
- FR-006
- C-001
- C-003
- SC-001
planning_base_branch: feat/849-preconditions
merge_target_branch: feat/849-preconditions
branch_strategy: Planning artifacts for this mission were generated on feat/849-preconditions. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-preconditions unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-arms849-live-runtime-host-endpoints-01M7Q8F3
base_commit: a5405108a087a3f51ee11a979decb5a3533dadd8
created_at: '2026-11-18T23:13:48.224770+00:00'
subtasks:
- T006
- T007
- T008
- T009
phase: Phase 2 - Live path
history:
- at: '2026-11-18T18:39:14Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: tests/research/test_arms849_integration.py
create_intent: []
execution_mode: code_change
model: ''
owned_files:
- tests/research/test_arms849_integration.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 - Host overrides, live node and red-first proof

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match for this work package's `task_type` and `authoritative_surface`.

---

## ⚠️ IMPORTANT: Review Feedback

**Read this first if you are implementing this task!**

- **Has review feedback?**: Check the `review_ref` field in the event log (via `spec-kitty agent tasks status`).
- **You must address all feedback** before your work is complete. Feedback items are your implementation TODO list.
- **Report progress**: As you address each feedback item, record what you changed with `spec-kitty agent tasks add-history <WPID> --note "..."` (stored in the status event log).

---

## Review Feedback

*[If this WP was returned from review, the reviewer feedback reference appears in the status event log.]*

---

## Markdown Formatting

Wrap HTML/XML tags in backticks: `` `<div>` ``, `` `<script>` ``
Use language identifiers in code blocks: ````python`,````bash`

---

## Objectives & Success Criteria

WP01 made the runtime's endpoints a value (`h.Endpoints`, `h.IN_NETWORK_ENDPOINTS`, `live_runtime(..., *, endpoints=)`, `Runtime.endpoints`). This WP is the **only place a host pair is built from the environment**. It lives in the test module, never in production (C-001). It wires that pair into the required live node, and proves with a red-first test that the override is what makes a host run pass.

Done when:

1. `_host_endpoints_from_env()` in `tests/research/test_arms849_integration.py` builds `h.Endpoints` from `ARMS849_FALKOR_HOST`/`ARMS849_FALKOR_PORT` and `ARMS849_LLAMA_HOST`/`ARMS849_LLAMA_PORT`, with **host** defaults (`127.0.0.1` and the substrate's published ports), never the in-network names (FR-003, spec edge cases).
2. T-d pins the defaults, a partial override, and a non-integer port that fails loudly naming the variable.
3. The required live node `test_live_runtime_registers_g_d_r_with_one_embedder` builds its runtime with `endpoints=_host_endpoints_from_env()` and **also calls `runtime.health()` for real**, so the llama side is exercised live, not only FalkorDB (SC-001, post-plan P-2). Its node ID is unchanged.
4. T-e (red-first, FR-006) shows that a default runtime built from the host fails on **name resolution of `falkordb`**. It is not live-gated, it runs in both office seed suites on office4, and it is bounded by a hard timeout (P-6).
5. The full `tests/research` suite has 0 failures (NFR-001).

## Context & Constraints

Read before starting:

- `kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/plan.md`: **D4**, and the test-plan rows **T-d, T-e and the live node**. Also the P-2 and P-6 dispositions.
- `kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/spec.md`: FR-003, FR-006, C-001, C-003, and the edge cases (only one override set; non-integer port).
- WP01's merged code in `scripts/research/run_849_harness.py` (`Endpoints`, `live_runtime`, `container_health`).

Code anchors (as of `cab71a10`):

| Symbol | Where | Note |
|---|---|---|
| Required live node | `tests/research/test_arms849_integration.py:1339-1355` | gated `skipif(os.environ.get("ARMS849_LIVE") != "1")`; **its node ID is pinned** in `scripts/research/check_849_premerge.py` `REQUIRED_NODES[0]` and `LIVE_NODES`. Do not rename, move or parametrize it |
| Autouse HTTP guard | `tests/conftest.py` `_block_live_http` | replaces `urllib.request.urlopen` with a raiser for every test |
| Guard opt-out precedent | `tests/research/test_arms849_arm_g.py:40-44` | `_REAL_URLOPEN = urllib.request.urlopen` captured at module import (before the fixture runs), and a `live_http` fixture that sets it back |
| Override convention precedent | `tests/research/test_arms849_arm_g.py` `falkor_endpoint` (~`:2832`) | reads `ARMS849_FALKOR_HOST` (default `127.0.0.1`) and `ARMS849_FALKOR_PORT` |
| Published ports | `scripts/research/arms849/substrate.py:103` | `FALKOR_PORT, LLAMA_PORT = 16379, 18080` |
| Cache location | `scripts/research/arms849/substrate.py` `CACHE_DIR`; `live_runtime` honours `ARMS849_CACHE` | `qwen-tokenizer/` and `fastembed/` beneath it |
| Bridge connects eagerly | `scripts/research/arms849/arm_g.py:1374-1404` | FalkorDB's client sends `INFO` at construction, so a bad host fails inside `live_runtime` |
| Connect timeout | `arm_g.py:1398` | `socket_connect_timeout=None`. **Do not change production transport**: the test carries its own timeout |

Constraints:

- **C-001**: the reader is test code. Do not add it, or any env read for endpoints, under `scripts/`.
- **C-003**: the required nodes stay host pytest. Do not move them into the runner container.
- The checker's office seeds run `tests/research` **without** `ARMS849_LIVE` and with `ARMS849_CACHE` set. The fresh-worktree CI step runs without the model cache and corpus (build absent). T-e must behave correctly in all three: run in the office seeds, skip in CI, and be unaffected by the live step.

## Branch Strategy

- **Strategy**: Planning artifacts were generated on feat/849-preconditions; completed changes must merge back into feat/849-preconditions.
- **Planning base branch**: feat/849-preconditions
- **Merge target branch**: feat/849-preconditions

> These fields are populated automatically by `spec-kitty agent mission finalize-tasks`.
> Do NOT change them manually unless you are certain the branch topology has changed.

Execution worktrees are allocated per computed lane from `lanes.json`. WP02 is claimable only after WP01 is approved or done. Start with:

```bash
spec-kitty agent action implement WP02 --agent claude --mission arms849-live-runtime-host-endpoints-01M7Q8F3
```

## Subtasks & Detailed Guidance

### Subtask T006 - `_host_endpoints_from_env()`

- **Purpose**: the single place a host `Endpoints` is built from the environment (D4).
- **Steps**:
  1. In `tests/research/test_arms849_integration.py`, add a module-level helper:

     ```python
     def _host_endpoints_from_env() -> h.Endpoints:
         """Host endpoints for the required live node: the published substrate ports on loopback,
         overridable by ARMS849_FALKOR_HOST/PORT and ARMS849_LLAMA_HOST/PORT (the falkor_endpoint
         convention). Test-only by design (C-001): production never reads these variables."""
     ```

  2. Defaults: hosts `127.0.0.1`; ports `substrate.FALKOR_PORT` and `substrate.LLAMA_PORT` (import `scripts.research.arms849.substrate` lazily inside the helper or at module top. Either is fine; the harness's C13 import rule concerns `graphiti_core`, not substrate).
  3. Each side resolves **independently**. Setting only the FalkorDB pair leaves llama on `127.0.0.1:<LLAMA_PORT>`, never `llama:8080`, and vice versa.
  4. Port parsing: `int(value)`. On `ValueError`, raise `ValueError(f"{name}={value!r} is not an integer port")`, naming the variable. Reject non-positive or >65535 ports the same way.
  5. Return `h.Endpoints((falkor_host, falkor_port), f"http://{llama_host}:{llama_port}")`.
- **Files**: `tests/research/test_arms849_integration.py`.

### Subtask T007 - T-d: reader tests [P]

- **Purpose**: pin the edge cases the spec names.
- **Steps** (use `monkeypatch.delenv(..., raising=False)` for all four keys first, then `setenv` per case):
  1. **Defaults**: no keys set → `Endpoints(("127.0.0.1", 16379), "http://127.0.0.1:18080")`. Assert against **literals**, and separately that they equal `substrate.FALKOR_PORT`/`LLAMA_PORT`, so a change to the constants is visible.
  2. **Partial, FalkorDB only**: `ARMS849_FALKOR_PORT=26379` → falkordb `("127.0.0.1", 26379)`, llama still `http://127.0.0.1:18080`. Assert `"llama:8080"` does not appear.
  3. **Partial, llama only**: `ARMS849_LLAMA_HOST=localhost`, `ARMS849_LLAMA_PORT=28080` → llama `http://localhost:28080`, FalkorDB `("127.0.0.1", 16379)`. Assert `"falkordb"` does not appear.
  4. **Non-integer port**: `ARMS849_LLAMA_PORT=eighteen` → `pytest.raises(ValueError, match="ARMS849_LLAMA_PORT")`. The same for `ARMS849_FALKOR_PORT`, parametrized.
- **Files**: `tests/research/test_arms849_integration.py`.

### Subtask T008 - Live node: host endpoints and a real health call

- **Purpose**: SC-001. The live node must pass from the host, and must exercise llama live, not only FalkorDB (P-2).
- **Steps**:
  1. Add a module-level `_REAL_URLOPEN = urllib.request.urlopen` near the imports (module import happens before the autouse fixture patches it). Add a local fixture `live_http(monkeypatch)` that restores it, mirroring `test_arms849_arm_g.py:40-44`. Do not import the fixture across test modules.
  2. Give the live node the `live_http` fixture. Keep its name and the `skipif` gate.
  3. Change construction to `endpoints = _host_endpoints_from_env()` and `runtime = h.live_runtime(PRIMARY, CORPUS, PASSING_GATES, endpoints=endpoints)`.
  4. Inside the existing `try`, add:
     - `assert runtime.endpoints == endpoints`;
     - `assert runtime.health() is True, "llama /health, /props n_ctx and FalkorDB PING at the host endpoints"`. This calls `container_health` with the host URL and FalkorDB address: llama `/health`, `/props` `n_ctx == PRIMARY.n_ctx`, and a FalkorDB `PING`.
  5. Keep every existing assertion and the `finally` close loop.
- **Files**: `tests/research/test_arms849_integration.py`.
- **Notes**:
  - `health()` returns `False` (it does not raise) on any `OSError`/`ValueError`/`KeyError`. If it fails live, diagnose by calling the three probes by hand. Do not weaken the assertion.
  - The checker brings the stack up in primary (non-yarn) mode, so `PRIMARY.n_ctx` is the expected value.
  - You cannot run the live node unless the stack is up (`substrate up`, which needs `build/849-runs/setup.json`). If you can bring it up on office4, do, and record the result. If you cannot, say so plainly in the history note. The orchestrator's quickstart run is the binding live proof (SC-001). **Do not** run `substrate up`/`down` if any other session is using the stack. Check `docker ps --filter name=arms849` first.

### Subtask T009 - T-e: red-first proof [P]

- **Purpose**: FR-006. Show that the override is what makes the host run pass: without it, the failure is specifically **name resolution of `falkordb`**.
- **Steps**:
  1. A new test, **not** live-gated, e.g. `test_host_run_without_override_fails_resolving_falkordb`.
  2. Skip conditions, checked in the parent, each with a distinct reason:
     - `socket.getaddrinfo("falkordb", 6379)` **succeeds**: the precondition is false (in the container, or a hosts entry). Skip with "falkordb resolves here; the red-first precondition does not hold".
     - The model cache is absent: `cache = pathlib.Path(os.environ.get("ARMS849_CACHE", str(substrate.CACHE_DIR)))`, and `cache / "qwen-tokenizer"` or `cache / "fastembed"` missing. Skip with the research-environment reason the module already uses (`RESEARCH_ENVIRONMENT_SKIP_REASON`), which matches how the fresh-worktree CI step treats absent build state.
     - The corpus is absent (`CORPUS / "stream.jsonl"` missing): the same reason.
     - `graphiti_core` is not importable (`importlib.util.find_spec("graphiti_core") is None`, or importing it raises, as with the checker's CI stub): the same reason. *(Added 2026-11-18 from analysis finding U1; arm G's factory imports graphiti, so without this the child would report an import error.)*
  3. Run the attempt in a **child process** with a hard bound:

     ```python
     result = subprocess.run([sys.executable, "-c", RED_FIRST_CHILD], cwd=REPO_ROOT, env=child_env,
                             capture_output=True, text=True, timeout=180, check=False)
     ```

     `child_env` is `os.environ` with the four `ARMS849_*` endpoint overrides **removed**, `ARMS849_LIVE` removed, and `PYTHONPATH` including `REPO_ROOT`. The child imports the harness and `tests.research.conftest` (`PRIMARY`, `PASSING_GATES`, `CORPUS`), calls `h.live_runtime(PRIMARY, CORPUS, PASSING_GATES)` with **no** endpoints, and prints one JSON line. If it raised, the line carries every exception in the `__cause__`/`__context__` chain as `{"type": ..., "module": ..., "message": ...}`. If it did not raise, it closes the arms and prints `{"raised": false}`.
  4. On `subprocess.TimeoutExpired`, `pytest.fail("red-first attempt hung past 180 s; production connect timeout is None (arm_g.py:1398), see P-6")`. A hang is a failure, never a pass.
  5. Assertions in the parent:
     - it raised;
     - some exception in the chain is a name-resolution failure: type `gaierror` (module `socket`), or a message containing `Name or service not known`, `nodename nor servname`, `Temporary failure in name resolution` or `getaddrinfo`;
     - `"falkordb"` appears in at least one message in the chain;
     - the chain contains **no** tokenizer, embedder, corpus or import error. That would mean the test failed for a setup reason, not the endpoint (P-6).
     Print the full chain in the assertion message so a reviewer can see why it passed.
- **Files**: `tests/research/test_arms849_integration.py`.
- **Notes**:
  - Measured 2026-11-18 on office4: `socket.getaddrinfo('falkordb', 6379)` raises `gaierror: [Errno -2] Name or service not known`, and `build/849-cache` exists. So T-e runs (not skips) in the checker's office seeds there.
  - `pytest-timeout` is **not** installed. Do not add a dependency. The subprocess timeout is the bound.
  - This is the red half of FR-006. The green half is the live node (T008), which runs with the override. Say so in both docstrings.

## Test Strategy

```bash
.venv/bin/python -m pytest tests/research/test_arms849_integration.py -q -k "host_endpoints or red_first or without_override"
.venv/bin/python -m pytest tests/research -q
ARMS849_LIVE=1 .venv/bin/python -m pytest -q "tests/research/test_arms849_integration.py::test_live_runtime_registers_g_d_r_with_one_embedder"   # only with the stack up
```

- Record the before and after `tests/research` totals in the WP history note.
- Confirm T-e **runs** (not skipped) in a plain `.venv/bin/python -m pytest tests/research` on office4, and paste its outcome line.
- Confirm red-first is real: temporarily make the child pass `endpoints=h.Endpoints(("127.0.0.1", 16379), "http://127.0.0.1:18080")` with the stack **down**. T-e must then fail its name-resolution assertion (connection refused is not name resolution). Revert it and record the result.

## Risks & Mitigations

- **T-e hangs.** Subprocess timeout; a hang fails.
- **T-e passes for a setup reason.** The chain assertions exclude tokenizer, embedder, corpus and import errors, and require `falkordb` plus a resolution error.
- **The live node's ID changes.** The checker's `REQUIRED_NODES` would no longer match. Do not rename.
- **Cross-module fixture coupling.** Define `live_http` locally; do not import it from `test_arms849_arm_g.py`.
- **Known interaction (no action here)**: `test_arms849_arm_g.py::falkor_endpoint` already honours `ARMS849_FALKOR_PORT`. Once WP03 sets it in the checker's live step, the second required live node reuses the running stack instead of running `substrate up`/`down` itself. That is the intended direction. WP03 owns the checker, and the reviewer notes it.

## Review Guidance

- The reader exists only in the test module. `grep -rn "ARMS849_FALKOR_HOST\|ARMS849_LLAMA_HOST" scripts/` shows no production read (WP03 adds the checker's **write** of these keys, which is expected).
- The live node keeps its exact node ID, adds `live_http`, passes `endpoints=`, and asserts `runtime.health() is True`.
- T-e is not live-gated, has the three distinct skip reasons, is bounded, and asserts name resolution of `falkordb` with setup errors excluded. The red-first check (host pair with the stack down fails T-e) was recorded.
- No change under `scripts/`.

## Progress & Status

Progress, history, and status all live in the status event log
(`status.events.jsonl`), never in this prompt file. Do **not** hand-edit a
history section here.

- **Record a progress note**: `spec-kitty agent tasks add-history WP02 --note "<what you did>"`
- **Change WP status**: `spec-kitty agent tasks move-task WP02 --to <status>`
- **View history and status**: `spec-kitty agent tasks status`
