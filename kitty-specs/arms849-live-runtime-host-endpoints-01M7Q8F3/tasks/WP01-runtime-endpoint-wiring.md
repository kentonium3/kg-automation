---
work_package_id: WP01
title: Runtime endpoint wiring
dependencies: []
requirement_refs:
- FR-001
- FR-002
- C-001
- C-002
- C-004
- NFR-001
planning_base_branch: feat/849-preconditions
merge_target_branch: feat/849-preconditions
branch_strategy: Planning artifacts for this mission were generated on feat/849-preconditions. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-preconditions unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Foundation
history:
- at: '2026-11-18T18:39:14Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/research/run_849_harness.py
create_intent:
- tests/research/test_arms849_endpoints.py
execution_mode: code_change
model: ''
owned_files:
- scripts/research/run_849_harness.py
- tests/research/test_arms849_endpoints.py
- tests/research/test_arms849_resume.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 - Runtime endpoint wiring

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

The #849 live runtime reaches FalkorDB and llama.cpp only through two module constants in `scripts/research/run_849_harness.py`:

```python
LLAMA_URL = "http://llama:8080"          # :170
FALKORDB_ADDR = ("falkordb", 6379)       # :171
```

Those names resolve only inside the `arms849` compose network, so the FR-015 pre-merge checker's required live node can never pass from the host (kentonium3/kg-automation#1083). This WP makes the endpoints **a value, not a constant**. The defaults stay exactly today's in-network pair, so the decisive in-container run is unchanged.

Done when:

1. A runtime built with no `endpoints` argument targets `falkordb:6379` and `http://llama:8080` at **all four** consumers: arm G's bridge, the serving facade, the health check, and the secondary gate's `/props` probe (FR-002, ratchet).
2. A runtime built with `endpoints=Endpoints(("127.0.0.1", 16379), "http://127.0.0.1:18080")` targets the host pair at all four consumers (FR-001, build). This is the positive control for item 1 and uses the same fixture.
3. Production code reads **none** of `ARMS849_FALKOR_HOST`, `ARMS849_FALKOR_PORT`, `ARMS849_LLAMA_HOST`, `ARMS849_LLAMA_PORT`, at import or at construction (C-001). This is proven in a fresh process with read recording.
4. `serving.ALLOWED_HOSTS` and the `ARMS849_LLAMA_HOSTS` prohibition are unchanged (C-002).
5. The full `tests/research` suite has 0 failures, with no previously passing test newly skipped (NFR-001).

## Context & Constraints

Read before starting:

- `kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/spec.md`: FR-001, FR-002, C-001, C-002, and the edge cases.
- `kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/plan.md`: **Design D1, D1a, D2, D3, D7** and the **test plan rows T-a, T-b, T-c and half-by-half**. The design is settled (Kent's decision `01M7Q8RGRANSNEQX84JP7JEAEB`, option A: the pair is carried on `Resources`). Do not re-open option B (per-call keyword arguments).
- `kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/data-model.md`: the `Endpoints` invariants I-1 and I-2.
- `.kittify/charter/charter.md`: testing standards (no dead code; fixtures mirror real inputs).

Code anchors (line numbers as of `cab71a10`; re-locate by name if they drift):

| Symbol | Where | Today |
|---|---|---|
| `LLAMA_URL`, `FALKORDB_ADDR` | `run_849_harness.py:170-171` | module constants |
| `Resources` | `:352-359` | frozen dataclass: `corpus_dir`, `config`, `tokenizer`, `embedder` |
| `_factory_g` | `:368-382` | `arm_g.make_bridge(resources.embedder, _corpus_text(resources))`, no host/port |
| `Runtime` | `:495-512` | dataclass; no endpoints |
| `container_health` | `:1206-1222` | `(config, base_url=LLAMA_URL, falkordb=FALKORDB_ADDR)`: `/health`, `/props`, then a FalkorDB PING over `socket.create_connection` |
| `live_runtime` | `:1534-1545` | facade built with `LLAMA_URL`; `health=lambda: container_health(config)` |
| `_props_n_ctx` | `:1548-1550` | `urlopen(f"{LLAMA_URL}/props")` |
| `live_secondary_gate` | `:1677` | `props_n_ctx: Callable[[], int] = _props_n_ctx` |
| CLI caller | `:1934-1936` | `live_runtime(config, args.corpus, gates_outcome)`, then `live_secondary_gate(runtime)`. **Must keep working unchanged**: it is the production path, and it gets the default |

Read only, do not modify: `scripts/research/arms849/arm_g.py` (`make_bridge(embedder, text, *, host=FALKOR_HOST, port=FALKOR_PORT, driver=None)` at `:1374` already accepts the endpoint), `scripts/research/arms849/serving.py` (`ALLOWED_HOSTS` at `:75` already contains `127.0.0.1`; `complete()` at `:400` sends through `urllib.request.urlopen` at `:426`), `scripts/research/arms849/substrate.py` (`FALKOR_PORT, LLAMA_PORT = 16379, 18080` at `:103`).

Constraints:

- **C-001**: no production code path reads an endpoint override from the environment. `live_runtime` already reads `ARMS849_CACHE`. That read is pre-existing, out of scope, and stays.
- **C-002**: no allowlist change. If a test needs one, the design is wrong. Stop and report.
- Keep the new dataclass fields **last, with defaults**, so every existing positional or keyword construction of `Resources` and `Runtime` (tests, fakes, `tests/research/conftest.py:300`) stays valid.
- Python 3.12, the repo `.venv`. Run tests as `.venv/bin/python -m pytest` (the bare console script fails at plugin import).

## Branch Strategy

- **Strategy**: Planning artifacts were generated on feat/849-preconditions; completed changes must merge back into feat/849-preconditions.
- **Planning base branch**: feat/849-preconditions
- **Merge target branch**: feat/849-preconditions

> These fields are populated automatically by `spec-kitty agent mission finalize-tasks`.
> Do NOT change them manually unless you are certain the branch topology has changed.

Execution worktrees are allocated per computed lane from `lanes.json`. Start with:

```bash
spec-kitty agent action implement WP01 --agent claude --mission arms849-live-runtime-host-endpoints-01M7Q8F3
```

## Subtasks & Detailed Guidance

### Subtask T001 - `Endpoints` value object and `IN_NETWORK_ENDPOINTS`

- **Purpose**: one immutable value naming both targets, so the three call sites cannot drift apart (the reason option B was rejected).
- **Steps**:
  1. Directly after `LLAMA_URL`/`FALKORDB_ADDR` (they must be defined first), add:

     ```python
     @dataclass(frozen=True)
     class Endpoints:
         """Where a live runtime connects. Production uses IN_NETWORK_ENDPOINTS only (C-001);
         host pairs are built by the required live test and the FR-015 checker, never from the
         environment here."""

         falkordb: tuple[str, int]
         llama_url: str


     IN_NETWORK_ENDPOINTS = Endpoints(FALKORDB_ADDR, LLAMA_URL)
     ```

  2. Keep `LLAMA_URL` and `FALKORDB_ADDR`. They remain the single source of the default, and other users (`container_health`'s signature defaults, the host-phase gates near `:1283`) keep using them.
  3. Do **not** add any parsing, env-reading or `from_env` constructor here (C-001, data-model invariant I-1).
- **Files**: `scripts/research/run_849_harness.py`.
- **Notes**: `dataclass` is already imported. A frozen dataclass with `eq=True` is hashable, so it is a legal dataclass field default.

### Subtask T002 - `Resources.endpoints`; `_factory_g` passes host/port

- **Purpose**: arm G's bridge is the FalkorDB consumer. It must read the runtime's pair.
- **Steps**:
  1. Add `endpoints: Endpoints = IN_NETWORK_ENDPOINTS` as the **last** field of `Resources`.
  2. In `_factory_g`, change the bridge construction to:

     ```python
     host, port = resources.endpoints.falkordb
     bridge = arm_g.make_bridge(resources.embedder, _corpus_text(resources), host=host, port=port)
     ```

  3. Leave `_factory_d` and `_factory_r` untouched. They make no network connection.
  4. Keep the lazy `from scripts.research.arms849 import arm_g` inside the factory (C13: importing the harness must not import `graphiti_core`; `test_importing_the_harness_never_imports_graphiti_core` pins it).
- **Files**: `scripts/research/run_849_harness.py`.
- **Notes**: `make_bridge` probes the server once, synchronously, at construction (FalkorDB's client runs `INFO`; see its docstring). So a wrong host fails at `live_runtime` time, not at first query. WP02's red-first test relies on that.

### Subtask T003 - `Runtime.endpoints`; `live_runtime(..., *, endpoints=)`

- **Purpose**: the facade and health callbacks read the same pair as the bridge (invariant I-2), and the runtime remembers it for T004.
- **Steps**:
  1. Add `endpoints: Endpoints = IN_NETWORK_ENDPOINTS` as the **last** field of `Runtime` (after `out`).
  2. Change the signature to a keyword-only parameter:

     ```python
     def live_runtime(config: serving.ServingConfiguration, corpus: pathlib.Path, gates_outcome: SessionGates,
                      *, endpoints: Endpoints = IN_NETWORK_ENDPOINTS) -> Runtime:
     ```

  3. Inside it:
     - `Resources(corpus_dir=corpus, config=config, tokenizer=tokenizer, embedder=embedder, endpoints=endpoints)`;
     - `facade=lambda deadline, cancelled, before_send: ServingFacade(config, tokenizer, endpoints.llama_url, deadline, cancelled, before_send)`;
     - `health=lambda: container_health(config, endpoints.llama_url, endpoints.falkordb)`;
     - `Runtime(..., endpoints=endpoints)`.
  4. Read no environment variable for endpoints. Update the docstring (there is none today; add a short one) to say the default is the in-network pair and that only tests and the checker pass a host pair.
- **Files**: `scripts/research/run_849_harness.py`.
- **Notes**: the CLI caller at `:1934` stays `live_runtime(config, args.corpus, gates_outcome)`, so production gets the default. Do not touch it.

### Subtask T004 - The `/props` probe follows the runtime (P-1)

- **Purpose**: without this, a host runtime sends its completion to the host endpoint but probes `/props` in-network. Codex's post-plan review found this gap (P-1).
- **Steps**:
  1. `def _props_n_ctx(base_url: str = LLAMA_URL) -> int:` and use `f"{base_url}/props"`.
  2. Change `live_secondary_gate`'s signature to `props_n_ctx: Callable[[], int] | None = None`. At the top of the function body (before `def probe`), resolve it:

     ```python
     if props_n_ctx is None:
         llama_url = runtime.endpoints.llama_url
         props_n_ctx = lambda: _props_n_ctx(llama_url)
     ```

  3. Existing callers that inject `props_n_ctx=lambda: 393_216` (`tests/research/test_arms849_integration.py:625, :654`) must keep working unchanged.
- **Files**: `scripts/research/run_849_harness.py`.
- **Notes**: resolve the URL from `runtime.endpoints`, never from the module constant. A `Runtime` built directly by test fakes (`tests/research/conftest.py:300`) gets `IN_NETWORK_ENDPOINTS` by default, so no fake changes.

### Subtask T005 - Tests: T-a, T-b, T-c; adapt the resume fake

- **Purpose**: prove the wiring through the **real** code paths. Faking the factories or only constructing the callbacks would bypass what changed (P-2), and a check on an already-imported module misses import-time reads (P-3).
- **Files**: create `tests/research/test_arms849_endpoints.py`; edit `tests/research/test_arms849_resume.py`.

**Shared fixture `_wired_runtime(monkeypatch, endpoints)`** (one helper used by T-a and T-b, so the positive control runs on the same fixture):

1. Patch `serving.Tokenizer` and `scripts.research.arms849.embed.Embedder` (imported inside `live_runtime`, so patch the **attribute on the module** `live_runtime` imports from) with trivial fakes. The tokenizer fake needs whatever `serving.complete`/`count_tokens` touch on the path you exercise; keep it minimal.
2. Patch `h._corpus_text` to return a sentinel, so no corpus files are needed (the suite must pass where `build/849-corpus` is absent).
3. Patch **only** `scripts.research.arms849.arm_g.make_bridge` with a recorder that captures `host`/`port` and returns a stub with `answer`, `build_graph`, `drop_graph`, `list_graphs` and `close`. Do **not** patch `ARM_FACTORIES` or `_factory_g`: the real factory must run. If `_factory_d`/`_factory_r` need more than the sentinel text to bind, patch `arm_d.bind`/`arm_r.bind` at their module boundary, not the factories.
4. Patch `urllib.request.urlopen` with a recorder that captures each request URL (`req.full_url` for a `Request`, or the string) and returns a context manager whose `read()` gives a plausible body. `/health` gives `{"status": "ok"}`. `/props` gives `{"default_generation_settings": {"n_ctx": <config.n_ctx>}}`. The completion endpoint gives whatever `serving.complete` parses. Your patch overrides the autouse `_block_live_http` guard (`tests/conftest.py`) for the test's duration, which is the documented way.
5. Patch `socket.create_connection` (as `run_849_harness` sees it) with a recorder that captures the address and returns a fake socket answering `+PONG`.
6. Build `h.live_runtime(PRIMARY, CORPUS_OR_TMP, PASSING_GATES, **({} if endpoints is None else {"endpoints": endpoints}))` and **invoke** the callbacks:
   - `runtime.health()`, which must return `True`;
   - `runtime.facade(time.monotonic() + 60, threading.Event(), lambda: None).complete(body)` with a small serialized body, so the request goes through `serving.complete` and the allowlist check, to the patched `urlopen`;
   - the props probe through `h.live_secondary_gate(runtime)`'s **default** resolution. Either run the probe end to end with fakes, or (simpler and sufficient) assert on a probe built by the same resolution path. Do not inject `props_n_ctx`: the default is what is under test.

**T-a (FR-002, ratchet)**: `endpoints=None` (omitted). Assert the bridge saw `("falkordb", 6379)`; every captured URL starts with `http://llama:8080`; `create_connection` saw `("falkordb", 6379)`; the `/props` probe URL is `http://llama:8080/props`; and `runtime.endpoints is h.IN_NETWORK_ENDPOINTS`. Use literals here, not the module constants, so the test is an independent oracle.

**T-b (FR-001, build; the positive control for T-a)**: the same helper with `h.Endpoints(("127.0.0.1", 16379), "http://127.0.0.1:18080")`. Assert all four consumers saw the host pair. This also proves C-002: the host URL passes `serving`'s allowlist with no change.

**T-c (C-001, fresh process)**: a test that runs a child Python via `subprocess.run([sys.executable, "-c", CHILD], env=..., cwd=REPO_ROOT, timeout=120, check=False, capture_output=True, text=True)`:

- The env sets all four `ARMS849_*` overrides to values distinct from every default (for example `ARMS849_FALKOR_HOST=203.0.113.7`, `ARMS849_FALKOR_PORT=1`, `ARMS849_LLAMA_HOST=203.0.113.8`, `ARMS849_LLAMA_PORT=2`), and `PYTHONPATH` includes `REPO_ROOT`.
- **Before** importing the harness, the child replaces `os.environ` with a mapping subclass that records every key read through `__getitem__`, `get`, `__contains__` and `getenv`. Patch `os.getenv` too, since it reads `os.environ`.
- It then imports `scripts.research.run_849_harness`, applies the same boundary patches as the shared fixture (inline in the child; keep the child script readable, as a module-level string constant in the test file), and builds the **default** runtime, including invoking `health()`.
- It prints JSON: the recorded reads of the four keys, and the four captured targets.
- The parent asserts (i) the in-network pair at all four consumers and (ii) **zero** reads of the four keys.
- Note in a comment, and confirm once locally, that planting `os.environ.get("ARMS849_FALKOR_HOST")` in a fake makes (ii) fail. That proves the recorder can fail. Do not commit the planted read.

**Resume fake**: `tests/research/test_arms849_resume.py:147` patches `h.container_health` with `lambda config: True`. After T003 the health callback calls it with three arguments. Change it to `lambda config, *args, **kwargs: True` (or `lambda *a, **k: True`). Check the rest of that file and `tests/research/conftest.py` for any other fake whose signature T001-T004 changed, and fix only what breaks.

## Test Strategy

Required:

```bash
.venv/bin/python -m pytest tests/research/test_arms849_endpoints.py -q
.venv/bin/python -m pytest tests/research -q
```

- Record the before and after totals for `tests/research` (passed, skipped, failed) in the WP history note. NFR-001: 0 failures, and no test that passed before now skips.
- Run `git diff --check` and the repo's pre-commit doc validation (it runs on commit).
- **Half-by-half (for the reviewer, and do it yourself first)**: revert each of the four wirings alone (bridge host/port, facade URL, health URL+falkordb, props probe URL). T-b must go red each time. Record the four results in the history note.

## Risks & Mitigations

- **A consumer missed.** Half-by-half catches it.
- **Positional construction breaks.** New fields go last, with defaults.
- **`graphiti_core` import at harness import.** Keep the factory's lazy import (C13 test).
- **The fake tokenizer drifts from the real interface.** Keep it to what `serving.complete` touches on the exercised path. If `serving.complete` needs more than a few methods, capture the URL at the `urlopen` boundary with a body small enough to stay under limits, rather than reimplementing tokenization.

## Review Guidance

- T-a/T-b must exercise the **real** `_factory_g` and **invoke** `facade`, `health` and the default props probe. Reject a version that patches `ARM_FACTORIES`, only constructs the lambdas, or injects `props_n_ctx`.
- T-c must set the overrides **before import**, in a child process, and assert zero reads. Reject a version that only checks the resulting targets.
- `serving.py`, `arm_g.py` and `substrate.py` are unchanged. `ALLOWED_HOSTS` is unchanged.
- No new `os.environ` read for endpoints anywhere under `scripts/`.
- Half-by-half recorded, four reds.

## Progress & Status

Progress, history, and status all live in the status event log
(`status.events.jsonl`), never in this prompt file. Do **not** hand-edit a
history section here.

- **Record a progress note**: `spec-kitty agent tasks add-history WP01 --note "<what you did>"`
- **Change WP status**: `spec-kitty agent tasks move-task WP01 --to <status>`
- **View history and status**: `spec-kitty agent tasks status`
