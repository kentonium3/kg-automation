---
work_package_id: WP02
title: Arms, refusals, G routing and loop bridge, before_send hook
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-003
- FR-008
- FR-016
- NFR-003
planning_base_branch: feat/849-preconditions
merge_target_branch: feat/849-preconditions
branch_strategy: Planning artifacts for this mission were generated on feat/849-preconditions. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/849-preconditions unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
- T011
- T012
phase: Phase 2 - Arms
history: []
agent_profile: python-pedro
authoritative_surface: scripts/research/arms849/arm_g.py
create_intent:
- scripts/research/arms849/errors.py
execution_mode: code_change
owned_files:
- scripts/research/arms849/arm_g.py
- scripts/research/arms849/arm_d.py
- scripts/research/arms849/arm_r.py
- scripts/research/arms849/serving.py
- scripts/research/arms849/embed.py
- scripts/research/arms849/errors.py
- tests/research/test_arms849_arm_g.py
- tests/research/test_arms849_arm_d.py
- tests/research/test_arms849_arm_r.py
- tests/research/test_arms849_serving.py
- tests/research/test_arms849_embed.py
- scripts/research/arms849/gates.py
role: implementer
tracker_refs: []
tags: []
---

# Work Package Prompt: WP02 — Arms, refusals, G routing and loop bridge, before_send hook

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load` (the profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch**: `feat/849-preconditions`
- **Final merge target**: `feat/849-preconditions`
- `/spec-kitty.implement` populates the actual worktree `base_branch` from `lanes.json`.
- If human instructions contradict these fields, stop and resolve the landing branch.

## Objective

Make the three arms ready for registration (WP04 wires them):
- one shared refusal class;
- G's refusals, split from its run-halting premise violations;
- **the FR-016 defect fix**: G wrote to `default_db` and hybrid-searched `arms_<Q>`, so hybrid retrieval always returned nothing;
- G's persistent-loop bridge with acknowledged cancellation;
- serving's send-time hook.

**Read first:**
- `contracts/arm-registration.md` (all items) and `contracts/before-send.md` items 1–4;
- `research.md` D-1, D-2, **D-2b**, D-3, D-4, D-9;
- the arms-run-01M3APTA `contracts/arm-interface.md` @`42056e57`;
- the existing `arm_g.py` (driver ~L315–348, `_indices_built` ~L320/332, `hybrid_search` ~L461, `answer` ~L491–534), `arm_d.py` L171–199 and `arm_r.py` L293–318 (the duplicated limit check);
- the installed graphiti `decorators.py` (~L59–68) and `driver/falkordb_driver.py` (`__init__`/`_init_task`, `clone`).

## Subtasks

### T007 — One refusal class and shared errors (FR-003)
- New module `arms849/errors.py`:
  - `ArmRefusal(RuntimeError)`;
  - `PremiseViolated(Exception)` (NOT an `ArmRefusal`), carrying `reason` (`tripwire`|`cross_group_leak`);
  - `CeilingBreached(Exception)` carrying `measured_gib`, `ceiling_gib`;
  - `CeilingUnreadable(Exception)`;
  - `GCancellationUnacknowledged(BaseException)`, carrying `grace_s` (deliberately NOT an `Exception`, so no ordinary handler absorbs it).
  - `CeilingBreached`/`CeilingUnreadable` subclass neither `ContextExceeded` nor `ArmRefusal`.
- The shared `_check_limit` (today duplicated in D and R) moves here or beside it. It reads ONLY `ctx.config`.
- `arm_d.ArmRefusal` and `arm_r.ArmRefusal` become aliases of the shared class, so the tests' `D.ArmRefusal`/`R.ArmRefusal` stay valid.
- Remove the `ctx.serving.config` fallbacks, and give the affected test ctxs a `config`.
- **Correction A (coupled edit declared in `owned_files`, mandated):** add `errors` to `gates.REQUIRED_MODULES` in the SAME commit that creates the file. WP01's two-way test enforces it.

### T008 — G refusals and premise violations (FR-002)
- These raise the shared `ArmRefusal` (terminal for the cell on the first attempt):
  - foreign items in G's view;
  - a graph not built;
  - an incoherent context limit (the SAME check as D/R, via `ctx.config`).
- These raise `PremiseViolated` (the run halts; WP04 records it):
  - the no-LLM tripwire firing;
  - retrieval crossing the per-question graph boundary.
- G does NOT refuse `cache_prompt` (C-008: served identically to D and R).

### T009 — FR-016: per-question database routing (DEFECT FIX, research D-2b)
- EVERY G operation runs through ONE per-question database, `self.driver.clone(database=group)`: node/edge/episode writes, the index build, typed pulls, anchored expansion, hybrid search and drop.
- Create the clone ONCE per question, cache it, and AWAIT its `_init_task` before first use.
- `_indices_built` becomes per-database.
- Build ONE `Graphiti` instance PER QUESTION bound to that cached clone, so `@handle_multiple_group_ids` takes its `gid == driver._database` branch and creates no further clone.
- Tests assert:
  - the clone count per question;
  - that writes and hybrid search hit the same database, with a transport-level fake recording the database of every query;
  - task quiescence: no pending tasks started by the bridge after a question's work or its cancellation.

### T010 — G loop bridge (research D-2; NFR-003)
- G's registration-facing object (for example `arm_g.Bridge`, constructed by a module-level factory that WP04's `ARM_FACTORIES` imports lazily) owns:
  - one asyncio loop on a dedicated thread;
  - one `FalkorDriver(host="falkordb", port=6379)` bound to it (the host/port must be injectable for tests).
- Split `answer`:
  - the retrieval coroutine (`plan_and_assemble`) is submitted to the loop via `run_coroutine_threadsafe`;
  - render, serialize, count and `ctx.serving.complete` run on the ATTEMPT thread through a new synchronous `respond(block, plan, question, ctx)`, exactly as D and R serve.
- `build_graph`, `drop_graph` and retrieval each honour the attempt's `deadline` and `cancelled` flag. WP04 adds `CellContext.deadline`; accept it via ctx, or via an explicit parameter with a clear seam.
- **Cancellation is acknowledged by the coroutine's own cleanup, or the bridge raises.**
  - On timeout or cancel, cancel the loop-side task, then wait up to the named constant `G_CANCEL_GRACE_S = 10` for an acknowledgement flag set in the coroutine's `finally`.
  - The acknowledgement counts only when every task the bridge started for that question is done, including a clone's `_init_task`.
  - `future.done()` is NOT an acknowledgement.
  - No acknowledgement means raise `GCancellationUnacknowledged(grace_s)`.
- `close()` applies the same bounded grace, then abandons the loop thread. There is no driver replacement.
- Expose a read-only graph listing (`list_graphs()`, or equivalent) for WP04's `graph_store_first_build`.

### T011 — `serving.complete(..., before_send)` (FR-008, serving side)
- `before_send()` is invoked after `count_tokens` and the permitted-limit check, and IMMEDIATELY before the HTTP send. Nothing wraps it: its exception propagates unaltered, and zero bytes are sent.
- The parameter's default leaves existing callers working until WP04 makes the facade require it. State this in the docstring.
- No arm catches `CeilingBreached` or `CeilingUnreadable`. Test that each arm's `answer` path lets both through unaltered, with a fake serving that raises them from `before_send`.

### T012 — Live FR-016 test and sweep
- Add a `live`-guarded test that builds the real graph for at least one question on a real FalkorDB. Assert the hybrid step RETURNS ≥ 1 hit, and that the expected item is identified from the FROZEN CORPUS, never from the oracle. It fails on the pre-change code.
- Give it a stable node ID and name it in the review artifact, because WP05's pre-merge checker lists it as REQUIRED.
- **Sweep:** list every G test assertion that checks a step RAN rather than that it PRODUCED, with its disposition (fixed, or justified). Report the count; never fix silently.

## Tests (red-first, NFR-002)

- FR-002, FR-003, FR-008 (serving side) and FR-016 each have a test shown failing on the pre-change code; record it.
- The bridge tests use a fake graph store with injected hangs. They cover:
  - an acknowledged cancellation;
  - an unacknowledged one, raising `GCancellationUnacknowledged` after the grace (patch the constant small in the test; assert the production value is 10);
  - cancellation during a clone's `_init_task`;
  - rebuild and drop across two databases.

## Definition of Done

- T007–T012 are done, and red-first evidence is recorded.
- The full suite passes on office4 under both seeds, and CI collection survives without `graphiti_core`. `arm_g` still imports graphiti at module top, so the harness must never import it eagerly; WP04 relies on this.
- `REQUIRED_MODULES` includes `errors`.
- The sweep list is in the review artifact.
- **No dead code (charter, mandatory before `for_review`):** grep for the live callers of every new or changed public symbol, and list each symbol's production caller in the review artifact. Symbols whose caller lands in a later WP name that WP. This WP: `errors.*` (raised on production paths), the G bridge factory (wired by WP04 T017's `ARM_FACTORIES`), `respond`, the graph listing (WP04 T020), the `before_send` parameter (WP04 T021).

## Risks / reviewer guidance

- **Properties to verify:**
  - one database per question across every G operation;
  - no bridge-started task outlives an acknowledged cancellation;
  - no ordinary `except Exception` can absorb `GCancellationUnacknowledged`;
  - `before_send` runs strictly before any byte is sent, and its exception is unaltered;
  - one refusal class, with terminality decided by identity.
