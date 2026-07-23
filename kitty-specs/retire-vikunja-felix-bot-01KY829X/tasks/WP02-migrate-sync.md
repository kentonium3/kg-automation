---
work_package_id: WP02
title: Migrate sync (cycle + fetch + http)
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-003
- NFR-001
tracker_refs: []
planning_base_branch: fix/860-retire-vikunja-felix-bot
merge_target_branch: fix/860-retire-vikunja-felix-bot
branch_strategy: Planning artifacts for this mission were generated on fix/860-retire-vikunja-felix-bot. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/860-retire-vikunja-felix-bot unless the human explicitly redirects the landing branch.
base_branch: fix/860-retire-vikunja-felix-bot
base_commit: 99db76c0f6102a6b0d86972b5b3ffccafba79626
created_at: '2026-07-23T21:04:52Z'
subtasks:
- T006
- T007
- T008
- T009
phase: Phase 1 - Migration
assignee: ''
agent: claude
history:
- at: '2026-07-23T21:04:52Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/sync/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/sync/cycle.py
- scripts/sync/fetch.py
- scripts/sync/http.py
- tests/sync/test_cycle.py
- tests/sync/test_fetch.py
- tests/sync/test_http.py
tags: []
---

# Work Package Prompt: WP02 — Migrate sync (cycle + fetch + http)

## ⚡ Do This First: Load Agent Profile

Load your assigned agent profile via `/ad-hoc-profile-load` before anything else, and adopt its
identity/governance/boundaries for this work package.

## Branch Strategy

- **Planning/base branch**: `fix/860-retire-vikunja-felix-bot`
- **Final merge target**: `fix/860-retire-vikunja-felix-bot`
- **Base may differ later**: `/spec-kitty.implement` populates `base_branch` on worktree creation.
- **If human instructions contradict these fields**: stop and resolve the landing branch.

**Depends on WP01** (the extended `VikunjaClient`). Implement command:
`spec-kitty agent action implement WP02 --agent <name>`.

---

## Objectives & Success Criteria

Route sync's raw urllib access through the shared `VikunjaClient`, **behavior-preserving**. Sync is
**bidirectional and highest-stakes** — the raw path is factored across three files:
- `scripts/sync/http.py` — the authenticated `urllib` request wrapper.
- `scripts/sync/fetch.py` — the read algorithm (one unpaged `GET /projects`, paged
  `GET /projects/{id}/tasks`, best-effort `GET /info`, empty-response **cache-abort guards**, dedup,
  structured `cycle_error` tokens).
- `scripts/sync/cycle.py` — the driver.

**Success criteria**:

- [ ] No `urllib`/raw-token access remains in `sync/http.py`, `fetch.py`, `cycle.py`; all Vikunja
      I/O flows through `VikunjaClient`.
- [ ] `pytest tests/sync/` passes.
- [ ] Parity is proven at the request level **and** the domain boundary: identical call order,
      `/info` best-effort suppression, empty-response cache-abort behavior, dedup, `cycle_error`
      classification, and exit codes are unchanged vs. the raw path.
- [ ] No identity/token change (still felix-bot).

## Context & Constraints

`sync/http.py:54` builds `urllib.request.Request(url, data, headers, method)` and returns
parsed-JSON-or-`None`, raising structured errors on HTTPError/URLError. `fetch.py` composes the read
algorithm on top and has **exact** observable behavior the migration must preserve:
- one **unpaged** `GET /projects` (note: `VikunjaClient.list_all_tasks()` pages
  `GET /projects?page=…&per_page=50` — a **different** request profile; see Risks),
- paged `GET /projects/{id}/tasks`,
- best-effort `GET /info` (failure is swallowed),
- empty-response **cache-nonempty abort** guards (don't overwrite a good cache with an empty read),
- dedup, and emitted `cycle_error` tokens that downstream classification depends on.

**Reference**: `plan.md` (IC-02 sync scope), `research.md` (R1c, R1e), `reference_vikunja_240_tasks_all_broken`
memory (v1 `GET /tasks/all` → 400; use project-scoped reads — `list_all_tasks` already does this).

## Subtasks & Detailed Guidance

### Subtask T006 — Migrate `sync/http.py`

- **Purpose**: replace the urllib wrapper with `VikunjaClient` calls.
- **Steps**:
  1. Inventory every call site of the `http.py` wrapper across sync.
  2. Replace the wrapper's internals with `VikunjaClient` verb methods (get/post/put/patch), or
     retire the wrapper and update callers to use the client directly — whichever keeps `fetch.py`
     and `cycle.py` diffs smallest.
  3. Preserve the wrapper's return/error contract (parsed-JSON-or-`None`, structured errors) via the
     WP01 adapter option so callers see unchanged values.
- **Files**: `scripts/sync/http.py` (+ `tests/sync/test_http.py`).
- **Parallel?**: No — foundation for T007/T008.

### Subtask T007 — Migrate `sync/fetch.py` read algorithm

- **Purpose**: move the read algorithm onto the client without changing observable behavior.
- **Steps**:
  1. Map each read (`GET /projects`, `GET /projects/{id}/tasks`, `GET /info`) onto client calls.
  2. **Preserve the request profile** — see Risks re: `list_all_tasks()` pagination vs the current
     unpaged `GET /projects`. Either preserve the exact algorithm (client `get()` calls in the same
     order) or consciously adopt `list_all_tasks()` and update the parity test to accept the changed
     profile — decide and document.
  3. Preserve `/info` best-effort suppression, empty-response cache-abort guards, and dedup exactly.
- **Files**: `scripts/sync/fetch.py` (+ `tests/sync/test_fetch.py`).
- **Parallel?**: No — depends on T006.

### Subtask T008 — Migrate `sync/cycle.py` driver

- **Purpose**: drive the migrated fetch/write paths; preserve `cycle_error` classification.
- **Steps**:
  1. Route any direct Vikunja I/O in `cycle.py` through the client.
  2. Preserve the emitted `cycle_error` tokens and their classification (downstream WhatsApp/alerting
     depends on them).
- **Files**: `scripts/sync/cycle.py` (+ `tests/sync/test_cycle.py`).
- **Parallel?**: No — depends on T006/T007.

### Subtask T009 — Sync parity + golden tests

- **Purpose**: prove behavior preservation at the domain boundary, not just request bodies.
- **Steps**:
  1. Extend `tests/sync/test_{http,fetch,cycle}.py` with parity assertions covering: request method/
     path/body **and** call order, `/info` best-effort suppression, empty-response cache-abort,
     dedup, `cycle_error` classification, and process exit codes.
  2. Add a golden test for a full cycle (mock the client) asserting the emitted records/tokens match
     the pre-migration behavior.
- **Files**: `tests/sync/test_{http,fetch,cycle}.py`.
- **Parallel?**: No — validates T006–T008.

## Definition of Done

- All four subtasks complete; `pytest tests/sync/` green.
- SC-001 grep shows no raw urllib/hand-loaded token in `sync/http.py`, `fetch.py`, `cycle.py`.
- Behavior preserved (requests + ordering + `/info`/cache guards + error tokens + exit codes).
- No identity/token change.

## Risks

- **Enumeration profile drift**: `list_all_tasks()` pages `GET /projects?page=…` whereas `fetch.py`
  does one unpaged `GET /projects` — using it silently changes the request profile and possibly
  project ordering/coverage. Preserve the raw algorithm or consciously accept + test the change.
- **Cache corruption**: the empty-response cache-abort guard prevents overwriting a good cache with
  an empty read — do not lose it in the migration.
- Bidirectional sync is highest-stakes — over-test rather than under-test.

## Reviewer Guidance

- Confirm no urllib remains in the three files; confirm the enumeration decision is explicit and
  tested; confirm `/info` suppression, cache-abort, dedup, and `cycle_error` classification are
  preserved with tests. Confirm exit codes unchanged.
