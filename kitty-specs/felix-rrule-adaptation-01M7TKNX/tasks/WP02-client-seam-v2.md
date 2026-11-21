---
work_package_id: WP02
title: Client seam — v2 partial update first
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- C-001
- C-006
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: d4da5afa34a2a97cf96345a743c7d833eac20c87
created_at: '2026-11-19T22:24:27.847594+00:00'
subtasks:
- T006
- T007
- T008
- T009
- T010
- T011
phase: Phase 0 - Foundation
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/common/vikunja_client.py
create_intent:
- tests/common/test_vikunja_client_v2.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/common/vikunja_client.py
- tests/common/test_vikunja_client.py
- tests/common/test_vikunja_client_v2.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 – Client seam — v2 partial update first

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `spec-kitty agent tasks status` for a `review_ref`. If this WP came back from review, address every feedback item and record each fix with `spec-kitty agent tasks add-history WP02 --note "..."`.

---

## Objectives & Success Criteria

Implement the client side of `contracts/vikunja-client-v2.md` in `scripts/common/vikunja_client.py`:

- `v2_base_url`
- `patch_task`
- `end_series` (resumable)
- `get_task_v2`, `create_task_v2`, `occurrences`, `preview_occurrences`
- `SeriesEndIncomplete`
- the guarded `update_task_fields`

**Do not remove `replace_task_fields` in this WP.** It still has callers until WP03 and WP08; WP08 removes it.

Done when:
- Every method in the contract exists, and its behaviour matches the contract, including null refusal, 304 → `None`, the 401 messages naming the missing permission, and the end-series recovery table.
- Existing client tests still pass, and the new tests in `tests/common/test_vikunja_client_v2.py` pass.

## Context & Constraints

- Read `contracts/vikunja-client-v2.md` (authoritative), `data-model.md` (Task write operation table, End-series recovery contract, Invariants 1 and 4), `research.md` R-001, R-002 and R-004, and `post-plan-review.md` findings 5 and 10.
- Today's client is described in the WP02-relevant parts of `scripts/common/vikunja_client.py`:
  - constructor at L192-221, with `_BASE_URL_PATTERN` at L112;
  - verbs at L248-299;
  - `_request` at L508-565 (urllib; sets `Content-Type: application/json` for POST, PUT and PATCH; an empty body returns `{}`; non-JSON raises `VikunjaServerError`);
  - `_map_http_error` at L596-608;
  - `replace_task_fields` at L415-432 and `update_task_fields` at L434-463.
- **Server facts** (vikunja-harness `d7e202228` + huma autopatch v2.40.0):
  - PATCH accepts `application/merge-patch+json` and `application/json` as RFC 7396 (AP:345, 366).
  - `null` deletes a key. A no-op returns **304 with an empty body** (AP:408-410).
  - `{"repeat":null,"done":true}` in one call reopens the task, so `end_series` must use two calls.
  - A done task with a rule, PATCHed with `{"repeat": null}` (done unchanged), does not reopen.
  - Token keys: `tasks.update` covers PATCH, `tasks.read_one` covers the GET, `tasks.create` covers create, and `tasks.occurrences` / `tasks.occurrences_preview` are needed for those two endpoints. Felix's current token lacks the last two (401 code 11, seen live).
- Keep the base-URL contract: **do not change `_BASE_URL_PATTERN` or `vikunja_config.py`**. Derive v2 (R-002).
- Stdlib only. No retries (an existing design choice, docstring L186).

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP02 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T006 – v2 root and request plumbing

- **Steps**:
  1. In `__init__`, after validation, set `self.v2_base_url = self.base_url[: -len("/api/v1")] + "/api/v2"`.
  2. Generalise `_request` (or add a private `_request_v2`) so that:
     - (a) the URL is composed against `v2_base_url`;
     - (b) the content type can be given, `application/merge-patch+json` for PATCH;
     - (c) **status 304 returns a sentinel** (`_NOT_MODIFIED`) instead of trying to parse JSON. `urllib` raises `HTTPError` for 304, so catch it before `_map_http_error`.
  3. Map a 401 on v2 to `VikunjaAuthError`, with a message naming the permission when the path is occurrences or preview. Never put the token in any message.
- **Notes**: Reuse `_compose_url` and the existing error classes. Keep v1 behaviour byte-identical; existing tests prove it.

### Subtask T007 – `patch_task`

- **Contract**: `patch_task(task_id, changes) -> dict | None`.
- **Steps**:
  1. Define `WRITABLE_TASK_FIELDS` as in the contract.
  2. Validate before any network call:
     - non-empty;
     - keys ⊆ `WRITABLE_TASK_FIELDS`;
     - no `None` values, unless the key is in the private `_allow_null` frozenset passed by `end_series` or the WP10 restore path. Use a keyword-only private parameter `_allow_null: frozenset[str] = frozenset()`, documented as internal.
  3. PATCH `/tasks/{id}` on v2 with the merge-patch content type. Return the dict on 200, or `None` on 304.
- **Tests**:
  - The body sent is exactly `changes`.
  - The `None` refusal raises `ValueError` and makes no HTTP call.
  - An unknown key is refused.
  - 304 → `None`; 404 → `VikunjaNotFoundError`; 401 → `VikunjaAuthError`.
  - The content-type header is merge-patch.
  - The URL is `/api/v2/tasks/{id}`.

### Subtask T008 – `end_series`

Implement the **End-series recovery contract** table from `data-model.md` exactly.

- **Steps**:
  1. Fresh `get_task_v2(id)`.
  2. Branch on the fresh state:
     - **Open with rule**: `patch_task(id, {"repeat": None}, _allow_null={"repeat"})`, then `get_task_v2`.
       - If the rule is still present, raise `SeriesEndIncomplete(id, "rule_reappeared")`.
       - Then `patch_task(id, {"done": True})` and `get_task_v2`.
     - **Open without rule**: `patch_task(id, {"done": True})`, then `get_task_v2`.
     - **Done with rule**: PATCH `{"repeat": None}` (done unchanged), then `get_task_v2`.
     - **Done without rule**: no-op.
  3. Final check in every branch: `done is True and not has_rule(task)`. Otherwise raise `SeriesEndIncomplete(id, "not_ended")`.
  4. Error and timeout handling:
     - An error after the first write succeeded → `SeriesEndIncomplete(id, "rule_cleared_not_done")`, chained with `from exc`.
     - On a `VikunjaTimeoutError` at either step: re-read once and decide from the fresh state. If that read also fails, raise `SeriesEndIncomplete(id, "unknown")`.
- **`SeriesEndIncomplete(VikunjaError)`**: attributes `task_id` and `state`.
- **Tests**:
  - each branch;
  - failure after step 1;
  - a timeout at step 1, then a re-read showing the rule cleared;
  - a timeout plus a failed re-read;
  - 304 on each step;
  - the rule reappearing;
  - assert that no single request body contains both `repeat` and `done`.

### Subtask T009 – Reads, create, occurrences, preview

- `get_task_v2(id)`: GET `/tasks/{id}` on v2, returning a dict that includes `repeats_rrule`.
- `create_task_v2(project_id, fields, *, rrule=None, initial_due_time=None)`:
  - POST `/projects/{id}/tasks` on v2. Merge in `repeats_rrule` and `initial_due_time` when given.
  - Refuse `None` values.
  - It does **not** verify; WP08's caller does.
- `occurrences(id, *, count=1)`:
  - Validate `1 <= count <= 100` locally.
  - GET `/tasks/{id}/occurrences?count=N` and return `{occurrences, reason?}`.
  - A 401 message names `tasks.occurrences`.
- `preview_occurrences(...)`:
  - Exactly one of `rrule`/`repeat` and one of `due_date`/`initial_due_time`, else `ValueError` before the call.
  - POST `/tasks/occurrences/preview`.
  - 400 → `VikunjaBadRequestError`; expose the server `code` (2002 or 2003) on the exception if the body has one.
  - A 401 message names `tasks.occurrences_preview`.
- **Parallel?**: Yes, after T006.

### Subtask T010 – Guarded `update_task_fields`

- **Steps**:
  1. Stop calling `replace_task_fields`. Call `self.post(f"/tasks/{id}", json=merged)` directly. This is the change that keeps the fallback alive when WP08 deletes `replace_task_fields`.
  2. Add the guard. If the current task has a rule, `repeats_from_current_date=True`, or non-empty reminders, and `merged` would drop or alter any of them, raise `ValueError`. Alter means `same_rule` is false, the flag changed, or the reminders differ. Allow it with keyword `allow_rule_change=True`.
  3. Update its docstring to name `repeat`, `repeats_from_current_date` and `reminders`, replacing `repeat_after`/`repeat_mode` (audit row 24).
  4. Leave `replace_task_fields` in place, but add a docstring line: "Deprecated: removed in WP08 of felix-rrule-adaptation; use patch_task". Also fix its `repeat_after` wording.
- **Tests**:
  - A full echo of a new-shape body keeps the rule.
  - Refusal when `changes={"repeat": None}` on a repeating task without the override.
  - The override works.
  - Convert the existing "preserves repeat_after" test (`tests/common/test_vikunja_client.py:347-385`) to `repeat`, using the WP01 factory.

### Subtask T011 – Tests

- Put the new behaviour in `tests/common/test_vikunja_client_v2.py`, using the existing `mock_vikunja_urlopen` fixture (`tests/common/conftest.py:305-348`) and the WP01 factory.
- Edit `tests/common/test_vikunja_client.py` only to convert the old-shape preservation test (T010).

```bash
python3 -m pytest -q tests/common/test_vikunja_client.py tests/common/test_vikunja_client_v2.py
```

```bash
make test
```

## Risks & Mitigations

- A 304 surfacing as an exception: test it explicitly.
- Message leakage: no token in any exception string. The existing `str()` redaction covers the body; add a test that asserts the token string is absent.
- Scope creep into callers: do not edit habits, escalation, intake or sync files here.

## Review Guidance

- Compare each method with the contract, line by line.
- Confirm that the null refusal cannot be bypassed through the public API.
- Confirm the end-series table is implemented branch for branch, and that the both-keys-in-one-body assertion test exists.
- Confirm v1 behaviour is unchanged: the existing tests pass untouched, apart from the one converted test.

## Progress & Status

Use `spec-kitty agent tasks add-history WP02 --note "..."` and `spec-kitty agent tasks mark-status T00x --status done`.
