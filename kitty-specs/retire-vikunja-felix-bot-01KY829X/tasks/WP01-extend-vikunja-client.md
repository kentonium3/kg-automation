---
work_package_id: WP01
title: Extend VikunjaClient (shared surface)
dependencies: []
requirement_refs:
- FR-002
- FR-003
- FR-004
tracker_refs: []
planning_base_branch: fix/860-retire-vikunja-felix-bot
merge_target_branch: fix/860-retire-vikunja-felix-bot
branch_strategy: Planning artifacts for this mission were generated on fix/860-retire-vikunja-felix-bot. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/860-retire-vikunja-felix-bot unless the human explicitly redirects the landing branch.
base_branch: fix/860-retire-vikunja-felix-bot
base_commit: 99db76c0f6102a6b0d86972b5b3ffccafba79626
created_at: '2026-07-23T21:04:52Z'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 0 - Foundation
assignee: ''
agent: "claude:opus:reviewer-renata:reviewer"
agent_profile: python-pedro
role: implementer
shell_pid: "42194"
shell_pid_created_at: "1784844563.858698"
history:
- at: '2026-07-23T21:04:52Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/common/vikunja_client.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/common/vikunja_client.py
- tests/common/test_vikunja_client.py
tags: []
---

# Work Package Prompt: WP01 — Extend VikunjaClient (shared surface)

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile via `/ad-hoc-profile-load`
(profile named in this file's `agent_profile` frontmatter). Adopt its identity, governance scope,
and boundaries for the whole work package.

## Branch Strategy

- **Planning/base branch at prompt creation**: `fix/860-retire-vikunja-felix-bot`
- **Final merge target**: `fix/860-retire-vikunja-felix-bot`
- **Actual worktree base may differ later**: `/spec-kitty.implement` populates `base_branch` when
  the worktree is created.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch.

---

## Objectives & Success Criteria

Extend `scripts/common/vikunja_client.py` so it covers **every** operation the raw-HTTP consumers
(sync, escalation, enrichment, habits, credential-health) require, on the existing client contract +
error model. This is the foundation WP — the domain migration WPs (WP02–WP06) depend on it.

**This is Phase 1: behavior-preserving. Do NOT change `DEFAULT_TOKEN_PATH` (still felix-bot
`vikunja-api`). Do NOT introduce an abstract `TaskService` port / adapter layer (FR-004).**

**Success criteria**:

- [ ] `VikunjaClient` exposes a `patch()` method; `_request` sets a JSON content-type for PATCH
      (as it already does for POST/PUT).
- [ ] Two distinct update methods exist: a **raw POST-replace** and a **safe read-modify-write**
      (GET-then-POST that preserves unspecified fields like `repeat_after`/`repeat_mode`).
- [ ] Shared read/comment/label operations the consumers need are present + unit-tested.
- [ ] A documented per-consumer decision exists for return/error semantics (raw `None`-on-empty /
      error-body-in-message vs. the client's `{}`-on-empty / redacted-exception), with an
      adapter-friendly option where a consumer must preserve raw behavior.
- [ ] `DEFAULT_TOKEN_PATH` is unchanged and points at the felix-bot `vikunja-api` file (SC-004).
- [ ] `pytest tests/common/test_vikunja_client.py` passes; every new method has a unit test.

## Context & Constraints

`VikunjaClient` today (`scripts/common/vikunja_client.py`) exposes `get/post/put/delete`,
`list_all_tasks`, and an internal `_request(method, …)` that only advertises a JSON content-type for
POST/PUT (see the `if method in ("POST", "PUT")` branch). It loads the token at **construction**
(`self.token = token`) from `DEFAULT_TOKEN_PATH` = `/data/services/openclaw/secrets/vikunja-api`.

**Before adding methods, inventory the actual consumer operations** — grep the raw modules to see
exactly which endpoints/verbs/bodies they issue, so you add the *right* methods (inventory-driven,
not speculative):

```
grep -rnE "urllib.request.Request|method=|/tasks|/comments|/labels|/projects|repeat_after" \
  scripts/sync scripts/escalation scripts/enrichment scripts/habits \
  scripts/security/credential_health_check
```

Known operations the consumers use (confirm by grep):
- **PATCH** `/tasks/{id}` — escalation `record_completion.py` (done / reschedule due_date).
- **POST** `/tasks/{id}` partial update — Vikunja v0.24.6 uses POST (not PATCH) for task field
  updates and **zeroes unspecified fields** (the known POST-partial-replace quirk). Habits
  `record_completion.py` handles this with GET-before-POST; `migrate_schedule.py` deliberately POSTs
  narrow bodies for patch/retire/rollback.
- **PUT** `/tasks/{id}/comments` — comment creation (habits uses PUT, not POST — the G4 quirk).
- Label attach/detach, filtered/bulk reads (`list_all_tasks` already pages projects+tasks).

**Reference docs**: `plan.md` (IC-01), `research.md` (R1d — client method gaps), `data-model.md`
(the `VikunjaClient` entity + INV-3 zero-identity-change), and the memory-documented Vikunja gotchas
(POST-partial-replace read-modify-write; id-vs-identifier; server-side `?filter=` rejection).

## Subtasks & Detailed Guidance

### Subtask T001 — Add `patch()` + PATCH content-type

- **Purpose**: escalation issues `PATCH /tasks/{id}`; the client has no `patch()`.
- **Steps**:
  1. Add a `patch(self, path, *, json=None, params=None, timeout=None)` method mirroring `put()`,
     delegating to `self._request("PATCH", …)`.
  2. In `_request`, include `PATCH` in the content-type branch so PATCH bodies advertise
     `application/json` (currently only POST/PUT do).
  3. Unit-test: PATCH sends the JSON body + header; empty/204 handled per the existing contract.
- **Files**: `scripts/common/vikunja_client.py`, `tests/common/test_vikunja_client.py`.
- **Parallel?**: No — establishes the verb other subtasks build on.

### Subtask T002 — Raw POST-replace update method

- **Purpose**: some consumers (`habits/migrate_schedule.py`) intentionally POST a narrow body to
  replace fields; expose this explicitly so callers opt into replace semantics.
- **Steps**:
  1. Add e.g. `replace_task_fields(self, task_id, body)` → `POST /tasks/{id}` with `body` verbatim.
  2. Document in the docstring that this **replaces** and that Vikunja v0.24.6 zeroes unspecified
     fields — callers wanting to preserve fields must use the read-modify-write method (T003).
  3. Unit-test the exact request shape.
- **Files**: same two.
- **Parallel?**: [P] with T003/T004.

### Subtask T003 — Safe read-modify-write update method

- **Purpose**: `habits/record_completion.py` GETs the task first, then POSTs the merged body so
  `repeat_after`/`repeat_mode` survive. Encapsulate this so the quirk lives in one place.
- **Steps**:
  1. Add e.g. `update_task_fields(self, task_id, changes)` that GETs `/tasks/{id}`, merges `changes`
     over the current fields, and POSTs the merged body (read-modify-write).
  2. Preserve `repeat_after`, `repeat_mode`, and other unspecified fields exactly.
  3. Unit-test: given a task with `repeat_after` set, `update_task_fields(id, {"done": True})` POSTs
     a body that still carries `repeat_after` (proves the zeroing quirk is defeated).
- **Files**: same two.
- **Parallel?**: [P].

### Subtask T004 — Shared read/comment/label ops

- **Purpose**: cover the remaining consumer operations that ≥2 domains share.
- **Steps**:
  1. From the T001 inventory, add the shared operations not already present — e.g. create-comment
     (PUT `/tasks/{id}/comments`, the G4 PUT-not-POST quirk), list-comments, label attach/detach,
     and any filtered/single-task read consumers need beyond `list_all_tasks`.
  2. Keep each on the existing error model (`VikunjaHttpError` mapping via `_map_http_error`).
  3. Unit-test each. Preserve id-vs-identifier handling and avoid server-side `?filter=` (rejected by
     the server — filter client-side).
- **Files**: same two.
- **Parallel?**: [P].

### Subtask T005 — Return/error-semantics adapter option + default-token assertion

- **Purpose**: raw consumers return `None` on empty/non-JSON and surface server error bodies in
  messages; the client returns `{}` on empty success and redacts bodies. Migrations must not silently
  change a consumer's observable error/return behavior.
- **Steps**:
  1. Decide, per operation, whether the client method returns raw-compatible values or whether the
     consumer adapts at the call site. Document the decision (a short table in the module docstring
     or a `docs`-comment) so WP02–WP06 apply it consistently.
  2. Where a consumer must preserve raw `None`/error-body behavior, provide an adapter-friendly path
     (e.g. an option to return the parsed body-or-`None`, or expose the status/body on the exception).
  3. Add an explicit unit test asserting `DEFAULT_TOKEN_PATH` still equals the felix-bot
     `vikunja-api` path (guards SC-004 — zero identity change this phase).
- **Files**: same two.
- **Parallel?**: No — depends on T001–T004 being defined.

## Definition of Done

- All five subtasks complete; `pytest tests/common/test_vikunja_client.py` green.
- No `TaskService` port/adapter introduced (FR-004). No default-token change (SC-004).
- New methods follow the existing contract + `VikunjaHttpError` model.
- No migration of any consumer in this WP (that's WP02–WP06) — this WP only extends the client.

## Risks

- **Over-abstraction**: resist building a generic "partial update" that hides the replace-vs-merge
  distinction — that reintroduces the v0.24.6 zeroing bug. Keep T002 and T003 separate.
- **Scope creep into Phase 2**: do not touch the token path, credential manifest, or validator.

## Reviewer Guidance

- Verify `patch()` + PATCH content-type; the two distinct update methods; a read-modify-write test
  proving `repeat_after` survives; the default-token assertion.
- Confirm no abstract port and no default-token change. Confirm every new method is unit-tested.

## Activity Log

- 2026-07-23T21:53:26Z – claude:sonnet-5:python-pedro:implementer – shell_pid=37000 – Assigned agent via action command
- 2026-07-23T22:03:18Z – claude:sonnet-5:python-pedro:implementer – shell_pid=37000 – Blocked: move-task WP01 --to for_review fails with 'Illegal transition: planned -> for_review'. Implementation is complete and committed (3fb9d9b4); 'spec-kitty agent tasks status' and the kanban both show WP01 in Doing/in_progress, but move-task's internal resolution read status as 'planned' — command printed 'Using planning repo's kitty-specs/ on fix/860-retire-vikunja-felix-bot (worktree copy ignored)', i.e. it resolved status from the primary/target-branch checkout instead of the mission coordination branch/worktree, a stale-state/authority-confusion mismatch. Also saw a secondary anomaly on the same call: 'Pre-review regression gate: no_coverage — gate authorities unavailable — unverified: tests.architectural._gate_coverage is not importable'. Not working around either — surfacing to the orchestrating session per standing rules.
- 2026-07-23T22:08:21Z – claude:sonnet-5:python-pedro:implementer – shell_pid=37000 – Ready for review — patch()+PATCH content-type, replace_task_fields (raw POST) + update_task_fields (read-modify-write preserving repeat_after), get_task, create_task_in_project, create_comment(PUT)/list_task_comments, VikunjaError.body captured but never in str/verbose_message; DEFAULT_TOKEN_PATH unchanged assertion. 73 client tests + 440 common suite pass; flake8 exit 0. Commit 3fb9d9b4 on lane-a.
- 2026-07-23T22:09:39Z – claude:opus:reviewer-renata:reviewer – shell_pid=42194 – Started review via action command
- 2026-07-23T22:17:01Z – user – shell_pid=42194 – Review passed (opus/reviewer-renata): all criteria verified; repeat_after-survives + token-unchanged tests present; scope clean; 73 tests pass. WP04 caveat: update_task_fields full-echo vs habits narrow-POST — verify or add field-allowlist.
