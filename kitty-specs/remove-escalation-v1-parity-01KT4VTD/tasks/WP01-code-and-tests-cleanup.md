---
work_package_id: WP01
title: Code + tests cleanup
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- NFR-001
- NFR-003
- NFR-005
- C-001
- C-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
history:
- timestamp: '2026-06-02T19:30:00Z'
  actor: claude:opus-4-7:planner
  action: created
authoritative_surface: scripts/escalation/
execution_mode: code_change
owned_files:
- scripts/escalation/record_completion.py
- scripts/escalation/reconcile_completions.py
- scripts/escalation/hard_fail.py
- scripts/escalation/backfill_jsonl_from_comments.py
- tests/escalation/test_backfill.py
- tests/escalation/test_record_completion.py
- tests/escalation/test_reconcile_completions.py
- tests/escalation/test_hard_fail.py
tags: []
---

# WP01 — Code + tests cleanup

**Mission**: `remove-escalation-v1-parity-01KT4VTD` — [spec.md](../spec.md), [plan.md](../plan.md), [data-model.md](../data-model.md), [contracts/escalation-side-effects.contract.md](../contracts/escalation-side-effects.contract.md)
**Source issue**: [#376](https://github.com/kentonium3/kg-automation/issues/376)

## Objective

Delete every active code path that writes, reads, or templates the `[Felix-Escalation]` substrate from the escalation domain. Preserve the JSONL substrate as the sole canonical record. Update the existing test suite to assert the new behavior. Run `pytest tests/escalation tests/enrichment` and confirm all green.

## Context

Mission #309 migrated the escalation domain to a JSONL state model but kept the v1 Vikunja-comment substrate alive as soak-window parity. The soak window was declared complete retroactively on 2026-06-02; this WP is the cleanup that should have shipped at the end of the soak.

The phantom-subscription detector in `reconcile_completions.py` reads `[Felix-Escalation]` comments and files `phantom_subscription` Q10 hard-fails. Spec discovery on 2026-06-02 confirmed it has fired zero times in 12 days post-cutover (no GitHub issues, no runtime occurrences). #507 will be the proper general bi-directional sync; the detector is removed in this WP per the no-vestiges principle being codified at #514.

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Execution worktree: allocated automatically by `spec-kitty next` per `lanes.json`.

---

## Subtask T001 — Remove v1 comment-write path + helpers + docstrings from `record_completion.py`

**Purpose**: Delete the comment-PUT step from the per-state side-effect dispatcher, the `_format_v1_comment` helper, the `_COMMENT_PREFIX` constant, and every docstring reference to v1 parity / C-001 / soak language. Preserve the Vikunja PATCH for `done` and `rescheduled` (these are real Vikunja state mutations, not v1 artifacts) and the JSONL append (the canonical substrate).

**Steps**:

1. Open `scripts/escalation/record_completion.py`.
2. Read the file end-to-end to understand the module's current shape. Pay attention to:
   - The module docstring (lines 1–70 currently) that describes the three-write contract
   - The `_format_v1_comment` helper (line ~340) and `_COMMENT_PREFIX` constant (line ~336)
   - The `_vikunja_side_effects` function (line ~493) where the comment PUT is dispatched
   - The `_http_request("PUT", comment_url, …)` call (line ~537)
3. Delete the comment PUT step from `_vikunja_side_effects`:
   - The block that constructs `comment_url`, calls `_http_request("PUT", comment_url, …)`, and appends `"comment_PUT"` to actions.
   - The block-level docstring comment "Comment write (C-001 parity)…"
4. Delete the `_format_v1_comment` function entirely (~50 lines including docstring).
5. Delete the `_COMMENT_PREFIX = "[Felix-Escalation]"` constant.
6. Delete the section header comment block "v1 [Felix-Escalation] comment formatter (data-model Entity 3 reverse)" (~6 lines above the helper).
7. Update the module docstring:
   - Remove the per-state lines that mention "PUT a v1 comment" or "PUT a v1 [Felix-Escalation] comment".
   - Remove the entire "C-001 parity (soak): …" paragraph (the one starting "for every event_type that historically wrote a `[Felix-Escalation]` comment in v1, we continue writing that comment as part of Step 1.").
   - Update the surviving prose to describe the new "two-write" contract: validate → (Vikunja PATCH for `done`/`rescheduled` only) → JSONL append.
   - Remove the `D11 (comment-write parity during soak)` line from the "Design references" section.
8. Update the docstring of `_vikunja_side_effects` to reflect the new contract: PATCH for `done`/`rescheduled`; nothing for `level_sent`/`snoozed`/`dismissed`. Remove "The comment write is always last…" and similar language.
9. Update the docstring of `record_event` if it references v1 comment behavior.
10. Verify no other references to `_format_v1_comment`, `_COMMENT_PREFIX`, `[Felix-Escalation]`, or "C-001 parity" remain in the file via grep within the file.

**Files**:
- `scripts/escalation/record_completion.py` (significant edits + deletions; ~80 lines removed)

**Validation**:
- [ ] `grep -nE "_format_v1_comment|_COMMENT_PREFIX|\[Felix-Escalation\]|C-001 parity" scripts/escalation/record_completion.py` returns zero matches.
- [ ] `_vikunja_side_effects` no longer issues any PUT-comment call.
- [ ] `done` state still produces a PATCH `{"done": true}`; `rescheduled` state still produces a PATCH `{"due_date": …}`.
- [ ] JSONL append step is structurally unchanged.

---

## Subtask T002 — Remove phantom-subscription detector from `reconcile_completions.py`

**Purpose**: Delete the v1-comment reader entry points and the phantom-subscription detection walk. Preserve the subscribed-sweep path (which works against JSONL as canonical) unchanged.

**Steps**:

1. Open `scripts/escalation/reconcile_completions.py`.
2. Read the file end-to-end. Identify the surfaces to delete (verified during spec-time research):
   - `_COMMENT_MARKER = "[Felix-Escalation]"` constant (~line 135)
   - `_count_escalation_comments(task)` helper function (~line 610-629)
   - The phantom-subscription detection block at the end of `reconcile_project` (~lines 1154-1226), specifically the `if jsonl_path.exists():` block that enumerates project tasks via `GET /projects/{id}/tasks`, calls `_count_escalation_comments`, and files `phantom_subscription` hard-fails
   - The module-level docstring lines that describe phantom-subscription detection (~lines 16-18, plus any narrative within the function docstrings of `reconcile_project` that mention phantoms)
3. Delete each of the above surfaces. Re-read the file after each deletion to ensure no syntactic dangling.
4. Update the module docstring to remove references to phantom-subscription / D8 (the research decision that introduced it).
5. Update the `reconcile_project` docstring to drop the "Phantom-subscription detection:" paragraph and any mention of the `GET /projects/{id}/tasks` walk that supported it.
6. Confirm the subscribed-sweep path is structurally unchanged (the loop that reads JSONL records, calls `derive_state`, compares against Vikunja task state, files state_drift / malformed_jsonl_record / derive_state_error hard-fails).
7. Grep within the file to confirm no surviving references to `_COMMENT_MARKER`, `_count_escalation_comments`, `[Felix-Escalation]`, `phantom_subscription`, `phantom subscription`, or `phantom-subscription`.

**Files**:
- `scripts/escalation/reconcile_completions.py` (~80 lines removed)

**Validation**:
- [ ] `grep -nE "_COMMENT_MARKER|_count_escalation_comments|phantom_subscription|\[Felix-Escalation\]" scripts/escalation/reconcile_completions.py` returns zero matches.
- [ ] The subscribed-sweep logic is structurally unchanged.
- [ ] Python imports compile cleanly (no orphan references to deleted names).

---

## Subtask T003 — Remove `phantom_subscription` reason code from `hard_fail.py`

**Purpose**: With the producer in `reconcile_completions.py` deleted (T002), the `phantom_subscription` reason code path in `hard_fail.py` becomes unreachable. Delete the reason-code branch, its bug-body templating that references `[Felix-Escalation]` comment_count, and any related constants or helpers.

**Steps**:

1. Open `scripts/escalation/hard_fail.py`.
2. Read the file to understand the reason-code dispatch pattern.
3. Identify the `phantom_subscription` branch — it's part of the bug-body templating that uses `comment_count` (line ~394 currently formats `- \`[Felix-Escalation]\` comment count: {comment_count}`).
4. Delete the reason-code branch and its templating. Preserve the remaining reason codes (`state_drift`, `malformed_jsonl_record`, `derive_state_error`).
5. Update any docstring or comment in the file that enumerates reason codes to drop `phantom_subscription` from the list.
6. Grep within the file to confirm no surviving references.

**Files**:
- `scripts/escalation/hard_fail.py` (~30 lines removed)

**Validation**:
- [ ] `grep -nE "phantom_subscription|\[Felix-Escalation\]" scripts/escalation/hard_fail.py` returns zero matches.
- [ ] Other reason codes still produce their expected bug bodies.

---

## Subtask T004 — Delete `backfill_jsonl_from_comments.py` and `test_backfill.py`

**Purpose**: The one-time migration script and its test are no longer useful — once the comment-write path is removed (T001), no new comments accumulate to backfill from. Delete both files.

**Steps**:

1. `git rm scripts/escalation/backfill_jsonl_from_comments.py`
2. `git rm tests/escalation/test_backfill.py`
3. Confirm `git status` shows the deletions staged.
4. Search the repo for any remaining imports of `backfill_jsonl_from_comments`:
   ```
   grep -rn "backfill_jsonl_from_comments" .
   ```
   Expected: zero matches outside `.git/` and `kitty-specs/`.

**Files**:
- DELETE `scripts/escalation/backfill_jsonl_from_comments.py`
- DELETE `tests/escalation/test_backfill.py`

**Validation**:
- [ ] Both files no longer exist in the working tree.
- [ ] No remaining imports or references to the deleted module from any other code.

---

## Subtask T005 — Update test suites

**Purpose**: Update test files that pin the v1 parity behavior or the phantom-subscription detection. Add or modify assertions to verify the new behavior.

**Steps**:

1. Open `tests/escalation/test_record_completion.py`. Search for assertions that mention `comment_PUT`, `_format_v1_comment`, `[Felix-Escalation]`, or any expectation of a PUT-comment HTTP call. Update each:
   - Tests that asserted the comment write happened → assert it does NOT happen. The action list returned by `_vikunja_side_effects` should be empty for `level_sent`/`snoozed`/`dismissed`, and `["task_PATCH_done"]` / `["task_PATCH_due_date"]` for `done`/`rescheduled`.
   - Tests that asserted comment body content → delete (no body to test).
   - Add new test cases per the named cases in `contracts/escalation-side-effects.contract.md` § "Test obligations" if not already covered: `level_sent_no_comment`, `snoozed_no_comment`, `dismissed_no_comment`, `done_patch_then_jsonl`, `rescheduled_patch_then_jsonl`, `patch_failure_blocks_jsonl`.
2. Open `tests/escalation/test_reconcile_completions.py`. Drop test cases that exercise the phantom-subscription path (any test that constructs a Vikunja task with `[Felix-Escalation]` comments and asserts a `phantom_subscription` hard-fail is filed). Preserve all subscribed-sweep test cases unchanged. Add a new test case `reconcile_no_phantom_path`: assert that when reconcile runs against a project with unsubscribed Vikunja tasks, no `phantom_subscription` hard-fail is filed and no `GET /projects/{id}/tasks` enumeration occurs for phantom-detection purposes.
3. Open `tests/escalation/test_hard_fail.py`. Drop test cases that exercise the `phantom_subscription` reason code path. Preserve test cases for other reason codes unchanged.
4. Open `tests/enrichment/test_record_completion.py`. AUDIT only — read the file to confirm whether any cross-references to escalation v1 parity exist. If so, update them (the habits domain has its own parity story — this WP doesn't touch habits-domain logic, only edits cross-references). If no escalation-domain references exist, no changes.
5. Re-read each modified test file end-to-end to confirm coherence.

**Files**:
- `tests/escalation/test_record_completion.py` (edit)
- `tests/escalation/test_reconcile_completions.py` (edit)
- `tests/escalation/test_hard_fail.py` (edit)
- `tests/enrichment/test_record_completion.py` (audit only; edit only if needed)

**Validation**:
- [ ] Each modified test file's tests can be collected by pytest without import or syntax errors.
- [ ] No test asserts the production of a `comment_PUT` action.
- [ ] No test asserts a `phantom_subscription` reason code.
- [ ] All `escalation-side-effects.contract.md` § "Test obligations" cases are covered.

---

## Subtask T006 — Run full test suite

**Purpose**: Confirm green across the entire escalation and enrichment domains, plus a broader sanity check.

**Steps**:

1. Run the focused test sweep:
   ```
   pytest tests/escalation tests/enrichment -v
   ```
2. Run the broader sweep to catch any unrelated regression:
   ```
   pytest tests/ -v
   ```
3. Run a final grep validation:
   ```
   grep -rnE "_format_v1_comment|_COMMENT_PREFIX|_COMMENT_MARKER|_count_escalation_comments|phantom_subscription" scripts/ tests/
   ```
   Expected: zero matches.
4. If any test fails or any grep match remains in active surfaces, return to the appropriate subtask and address. Do not mark this WP complete with a failing test.

**Validation**:
- [ ] `pytest tests/escalation tests/enrichment -v` exit code 0.
- [ ] `pytest tests/ -v` exit code 0 (or the same failure baseline as on main pre-WP — document any pre-existing failures).
- [ ] Final grep returns zero matches.

---

## Definition of Done

- [ ] All six subtasks marked done.
- [ ] `pytest tests/escalation tests/enrichment -v` is green end-to-end.
- [ ] No active code references `_format_v1_comment`, `_COMMENT_PREFIX`, `_COMMENT_MARKER`, `_count_escalation_comments`, or `phantom_subscription` per FR-001/002/006/007 and NFR-002.
- [ ] `backfill_jsonl_from_comments.py` and `test_backfill.py` are deleted.
- [ ] No unrelated edits to other files (agent prompts, runbooks, arch docs are WP02's domain).

## Reviewer guidance

A reviewer should verify, in order:

1. **The diff to `record_completion.py` is purely deletion of the comment-write surface** (`_format_v1_comment`, `_COMMENT_PREFIX`, the comment-PUT block in `_vikunja_side_effects`, related docstrings). Any non-deletion edit in this file is a red flag.
2. **The diff to `reconcile_completions.py` preserves the subscribed-sweep path exactly** while deleting `_COMMENT_MARKER`, `_count_escalation_comments`, and the phantom-detection walk. If subscribed-sweep behavior changes, the WP overreached.
3. **`hard_fail.py` retains all reason codes except `phantom_subscription`**. The other branches should not be touched.
4. **The two deleted files (`backfill_jsonl_from_comments.py` and `test_backfill.py`) are gone**, no other deletions in scripts/escalation/ or tests/escalation/.
5. **Test coverage at the new behavior is present**, especially the `reconcile_no_phantom_path` regression guard.
6. **`pytest tests/ -v` is green** end-to-end.

## Risks

- **Test-suite fragility**: many existing tests pin the v1 parity behavior. The edits in T005 must be surgical — only the assertions that reference parity behavior change, the test scaffolding stays.
- **Reconcile docstring drift**: long docstrings reference phantom detection at multiple levels (module, function, inline comments). Grep-driven validation in T006 catches the survivors.
- **Cross-mission contract drift**: mission #309's `contracts/api.md` describes the old three-write contract; this WP does NOT edit #309's contract (cross-mission edits trigger the implementation-lane guard — per #512's lesson). The current mission's `contracts/escalation-side-effects.contract.md` is the new authoritative spec; a future `[doc-audit]` commit on main can sync the #309 contract if needed.
