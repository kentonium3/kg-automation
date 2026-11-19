---
work_package_id: WP03
title: Checker records and verifier requires the host endpoints
dependencies: []
requirement_refs:
- FR-004
- FR-005
- NFR-002
- SC-002
- SC-003
planning_base_branch: feat/849-preconditions
merge_target_branch: feat/849-preconditions
branch_strategy: Planning artifacts for this mission were generated on feat/849-preconditions. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-preconditions unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-arms849-live-runtime-host-endpoints-01M7Q8F3
base_commit: 97a50e78e63e424b3b5a82d395ca5a1391378395
created_at: '2026-11-18T18:49:31.689201+00:00'
subtasks:
- T010
- T011
- T012
- T013
- T014
phase: Phase 1 - Foundation
history:
- at: '2026-11-18T18:39:14Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/research/check_849_premerge.py
create_intent: []
execution_mode: code_change
model: ''
owned_files:
- scripts/research/check_849_premerge.py
- tests/research/test_check_849_premerge.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 - Checker records and verifier requires the host endpoints

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

`scripts/research/check_849_premerge.py` produces the commit-bound arms-preconditions-01M3FVRY#FR-015 record, and `--verify` checks it. Today its `live-required-nodes` step runs the two required live nodes with only `ARMS849_LIVE=1` and `ARMS849_CACHE`. The nodes then try the in-network names and can never pass from the host (#1083). This WP makes the checker point the live nodes at the **published ports**, record that it did, and makes `--verify` refuse any record that does not show it.

Done when:

1. One shared mapping, `HOST_LIVE_ENDPOINT_ENV`, holds exactly the four overrides: `ARMS849_FALKOR_HOST=127.0.0.1`, `ARMS849_FALKOR_PORT=str(substrate.FALKOR_PORT)`, `ARMS849_LLAMA_HOST=127.0.0.1`, `ARMS849_LLAMA_PORT=str(substrate.LLAMA_PORT)`. The ports come from the substrate's constants, never repeated literals (FR-004).
2. The `live-required-nodes` step passes those four to the runner **and** its recorded `environment` contains them (FR-004).
3. `--verify` accepts a record only when `live-required-nodes.environment` has `ARMS849_LIVE == "1"` **and** all four keys present and equal to `HOST_LIVE_ENDPOINT_ENV`. Otherwise it rejects with a reason naming the live step's endpoint environment (FR-005, SC-003).
4. Tests T-f and T-g pass, against an **independent oracle** (P-5).
5. Every existing test in `tests/research/test_check_849_premerge.py` still passes, and so does the full `tests/research` suite (NFR-001).

**Out of scope**: hardening `--verify` against self-contradictory records (non-zero counts, non-executing pytest flags). That is post-plan finding P-4, which Kent ruled a separate issue: kentonium3/kg-automation#1106. Do not change `valid_step`'s count rules or `command_has` semantics here.

## Context & Constraints

Read before starting:

- `kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/plan.md`: **D5, D6**, and the test-plan rows **T-f, T-g**. Also the P-5 disposition.
- `kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/data-model.md`: "Checker record: `live-required-nodes` step".
- `kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/quickstart.md`: how the real run is read and verified.

Code anchors in `scripts/research/check_849_premerge.py` (as of `cab71a10`):

| Symbol | Where | Today |
|---|---|---|
| `LIVE_NODES` | `:67-70` | `REQUIRED_NODES[0]` (integration live node) and `REQUIRED_NODES[10]` (`test_arms849_arm_g.py::test_live_hybrid_search_returns_an_item_the_question_names`) |
| `_step` evidence allowlist | `:274-277` | `("PYTHONHASHSEED", "ARMS849_CACHE", "ARMS849_LIVE", "PYTHONPATH")`. A key not listed here is **silently dropped** from the record |
| `verify_record` semantics | `:603-680` | `required_live = by_name["live-required-nodes"]`; requires the pytest tokens, `--junitxml=`, and `environment.get("ARMS849_LIVE") == "1"` (`:669-674`) |
| Office seed env | `:412`, `:733` | `env.pop("ARMS849_LIVE", None)` |
| Live step | `:798-804` | `env = {**os.environ, "ARMS849_LIVE": "1", "ARMS849_CACHE": cache}` |
| Substrate CLI use | `:755` | runs `python -m scripts.research.arms849.substrate` as a subprocess; the module is **not imported** today |

Test anchors in `tests/research/test_check_849_premerge.py`:

| Symbol | Where | Note |
|---|---|---|
| `_FullRunner` | `:333-414` | whole-checker fake; records `(command, cwd, env, timeout)` in `self.calls`; synthesizes JUnit. **Today the live JUnit passes whenever `ARMS849_LIVE == "1"`** (`:391-392`) |
| Whole-checker pass | `:416-439` | `run_premerge(...)` then `verify_record(output, runner.commit) == (True, [])` |
| Mutation pattern | `:479-503` | write a passing record, mutate the JSON, `verify_record`, assert a reason. Reuse this pattern for T-g |

Constraints:

- **One mapping** defines what the checker writes and what the verifier requires (D6). The tests must **not** use that mapping as their oracle (P-5).
- **C-001 is about production harness code**, not the checker. The checker *writing* these keys into a child pytest environment is the design.
- Do not change the record's schema beyond the four added `environment` keys. Do not bump any record version field unless one exists and the verifier keys on it.
- Importing `scripts.research.arms849.substrate` is acceptable: stdlib-only, about 50 ms, though it hashes the runner Dockerfile inputs at import. If you import it at module top, confirm `.venv/bin/python -c "import scripts.research.check_849_premerge"` still works in a fresh worktree (`git worktree add --detach`), because the checker's own CI step imports it there. If that is a problem, derive the mapping in a small function called at use, and note why.

## Branch Strategy

- **Strategy**: Planning artifacts were generated on feat/849-preconditions; completed changes must merge back into feat/849-preconditions.
- **Planning base branch**: feat/849-preconditions
- **Merge target branch**: feat/849-preconditions

> These fields are populated automatically by `spec-kitty agent mission finalize-tasks`.
> Do NOT change them manually unless you are certain the branch topology has changed.

Execution worktrees are allocated per computed lane from `lanes.json`. WP03 has no dependency and can run alongside WP01. Start with:

```bash
spec-kitty agent action implement WP03 --agent claude --mission arms849-live-runtime-host-endpoints-01M7Q8F3
```

## Subtasks & Detailed Guidance

### Subtask T010 - `HOST_LIVE_ENDPOINT_ENV` [P]

- **Purpose**: the single definition of "the live nodes ran at the published ports".
- **Steps**:
  1. Near `LIVE_NODES`, add:

     ```python
     #: #1083: the required live nodes run on the host, so they reach the stack through the ports
     #: the substrate publishes on loopback. The checker writes exactly these into the live step's
     #: environment, and --verify requires exactly these.
     HOST_LIVE_ENDPOINT_ENV: Mapping[str, str] = MappingProxyType({
         "ARMS849_FALKOR_HOST": "127.0.0.1",
         "ARMS849_FALKOR_PORT": str(substrate.FALKOR_PORT),
         "ARMS849_LLAMA_HOST": "127.0.0.1",
         "ARMS849_LLAMA_PORT": str(substrate.LLAMA_PORT),
     })
     ```

     Use `types.MappingProxyType` so it cannot be mutated by accident.
  2. Import `substrate` per the constraint above.
- **Files**: `scripts/research/check_849_premerge.py`.

### Subtask T011 - The live step passes and records the overrides

- **Purpose**: FR-004.
- **Steps**:
  1. In the live phase (`:798`), build `env = {**os.environ, "ARMS849_LIVE": "1", "ARMS849_CACHE": cache, **HOST_LIVE_ENDPOINT_ENV}`. The mapping goes **last**, so an operator's stray exported override cannot redirect the checker's live step.
  2. Extend the `_step` evidence allowlist with the four keys. Derive them from `HOST_LIVE_ENDPOINT_ENV`'s keys, e.g. `("PYTHONHASHSEED", "ARMS849_CACHE", "ARMS849_LIVE", "PYTHONPATH", *HOST_LIVE_ENDPOINT_ENV)`, so the two lists cannot drift.
  3. **Strip** the four keys from the office-seed and fresh-worktree CI environments, in the same places `ARMS849_LIVE` is popped (`:412`, `:733`), so an operator's exported override never leaks into those suites. Assert it in T-f. *(Made definite 2026-11-18 from analysis finding A1.)*
- **Files**: `scripts/research/check_849_premerge.py`.
- **Notes**: the second required live node (`test_arms849_arm_g.py::falkor_endpoint`) already honours `ARMS849_FALKOR_HOST`/`PORT`. With them set, it uses the running stack and no longer runs `substrate up`/`down` itself inside the live step. That is the intended effect. Mention it in your history note so the reviewer sees it.

### Subtask T012 - `--verify` requires the overrides

- **Purpose**: FR-005, SC-003. A record whose live step silently fell back to the in-network names must not verify.
- **Steps**:
  1. In `verify_record`, extend the `required_live` clause (`:669-674`):

     ```python
     live_env = required_live["environment"]
     semantics_ok &= (
         command_has("live-required-nodes", "pytest", "junit_family=xunit1", *LIVE_NODES) and
         any(str(arg).startswith("--junitxml=") for arg in required_live["command"]) and
         live_env.get("ARMS849_LIVE") == "1" and
         all(live_env.get(key) == value for key, value in HOST_LIVE_ENDPOINT_ENV.items())
     )
     ```

  2. The rejection must surface in `reasons` the way other semantics failures do. Today a failed `semantics_ok` yields a "command semantics" reason. Add a **specific** reason when the live endpoint environment is the cause, e.g. `"live-required-nodes did not run at the published host endpoints"`, so a reader knows which check failed. Keep the existing generic reason behaviour for everything else.
- **Files**: `scripts/research/check_849_premerge.py`.

### Subtask T013 - T-f: checker env, independent oracle

- **Purpose**: prove the overrides reach both the runner **and** the record (the allowlist could drop them silently).
- **Steps**:
  1. Make `_FullRunner`'s live JUnit synthesis **depend on the overrides**. The live cases pass only when `ARMS849_LIVE == "1"` **and** the env carries `ARMS849_FALKOR_HOST == "127.0.0.1"`, `ARMS849_FALKOR_PORT == "16379"`, `ARMS849_LLAMA_HOST == "127.0.0.1"`, `ARMS849_LLAMA_PORT == "18080"`. Otherwise they come out `failure`, modelling the real-world result. Write these as **literals** in the test module (a small `_EXPECTED_HOST_ENV` dict), never `HOST_LIVE_ENDPOINT_ENV`. The existing whole-checker pass test then also proves the checker sends them.
  2. New test `test_live_step_runs_and_records_the_published_host_endpoints`:
     - run the whole checker with `_FullRunner`;
     - find the live call (the pytest call containing `LIVE_NODES[0]`) and assert its env carries the four literal values;
     - assert the recorded `live-required-nodes` step's `environment` carries the same four, plus `ARMS849_LIVE == "1"`;
     - assert the literals agree with `substrate.FALKOR_PORT`/`LLAMA_PORT` (one line), so a port change shows up as a deliberate test edit;
     - assert no office or CI call env contains any of the four (T011 step 3), **even with** `monkeypatch.setenv("ARMS849_FALKOR_PORT", "1")` set beforehand.
  3. Also with an operator override exported (`monkeypatch.setenv("ARMS849_LLAMA_PORT", "9")`), assert the live call still carries `18080` (the checker's mapping wins).
- **Files**: `tests/research/test_check_849_premerge.py`.

### Subtask T014 - T-g: verifier rejects missing or wrong endpoints

- **Purpose**: SC-003, per-key coverage (P-5).
- **Steps**, all from one passing record produced by `_FullRunner` (the mutation pattern at `:479`):
  1. The unmodified record verifies: `(True, [])`.
  2. `ARMS849_LIVE` removed from `live-required-nodes.environment` → rejected.
  3. Parametrize over the four keys:
     - the key **absent** → rejected;
     - the key with a **wrong value** (`"falkordb"`/`"llama"` for hosts, `"6379"`/`"8080"` for ports, i.e. the in-network values) → rejected.
     Each rejection's `reasons` includes the specific endpoint reason from T012.
  4. **Legacy-shaped record**: all four keys removed (what a pre-#1083 checker wrote) → rejected.
  5. Values written by the test are literals, not `HOST_LIVE_ENDPOINT_ENV` (P-5).
- **Files**: `tests/research/test_check_849_premerge.py`.

## Test Strategy

```bash
.venv/bin/python -m pytest tests/research/test_check_849_premerge.py -q
.venv/bin/python -m pytest tests/research -q
.venv/bin/python -c "import scripts.research.check_849_premerge"
```

- Record the before and after totals in the WP history note.
- Non-vacuity, checked by you and the reviewer: remove the `**HOST_LIVE_ENDPOINT_ENV` from the live env → T-f and the whole-checker pass test go red. Remove the four keys from the evidence allowlist → T-f goes red on the recorded environment (and `--verify` rejects). Drop the new `all(...)` clause from the verifier → T-g goes red. Record the three results.
- Do **not** run the real checker here (it needs the live stack and runs over an hour). The orchestrator runs it after the merge (quickstart.md).

## Risks & Mitigations

- **The allowlist drops the keys silently.** T-f asserts on the recorded environment.
- **Shared mapping as its own oracle.** Tests use literals.
- **Old records stop verifying** (run 3 at a5550894). Intended: records are commit-bound, and that record was a FAIL anyway.
- **The import of substrate breaks in the fresh worktree.** Checked by the import command in a detached worktree. Fall back to lazy derivation if needed.

## Review Guidance

- Exactly four keys, ports from `substrate`, a single mapping used by the writer, the allowlist and the verifier.
- The mapping is applied last in the live env, so an operator export cannot override it.
- T-f and T-g use literals; per-key absent and wrong-value parametrization exists; the legacy record is rejected.
- `_FullRunner`'s live JUnit now depends on the overrides.
- `valid_step` and `command_has` semantics are otherwise untouched (P-4 is #1106).
- The three non-vacuity reverts were recorded red.

## Progress & Status

Progress, history, and status all live in the status event log
(`status.events.jsonl`), never in this prompt file. Do **not** hand-edit a
history section here.

- **Record a progress note**: `spec-kitty agent tasks add-history WP03 --note "<what you did>"`
- **Change WP status**: `spec-kitty agent tasks move-task WP03 --to <status>`
- **View history and status**: `spec-kitty agent tasks status`
