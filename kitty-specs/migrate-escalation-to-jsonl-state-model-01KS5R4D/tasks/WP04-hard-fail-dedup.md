---
work_package_id: WP04
title: Hard-fail dedup + bug filing helper
dependencies:
- WP02
requirement_refs:
- C-006
- FR-008
- FR-009
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-21T17:45:30+00:00'
subtasks:
- T012
- T013
- T014
agent: "claude:opus:python-implementer:implementer"
shell_pid: "98523"
history:
- at: '2026-05-21T17:45:30+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/escalation/
execution_mode: code_change
mission_id: 01KS5R4D79WQQWY2MCHZVCT85G
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
owned_files:
- scripts/escalation/hard_fail.py
- tests/escalation/test_hard_fail.py
tags: []
---

# WP04 — Hard-fail dedup + bug filing helper

## Objective

Implement the helper module that renders the Q10 hard-fail P2-bug body and queries `gh` for title-prefix dedup before filing. Used by WP05 (reconcile) and indirectly by WP03 (record_completion routes derive_state errors through this when invoked from a tick context). Implements FR-008 (Q10 hard-fail behavior) and FR-009 (title-prefix dedup keyed on Vikunja `id`).

## Context

- **Mission spec**: FR-008 (hard-fail skip + file bug), FR-009 (dedup keyed on immutable Vikunja `id`)
- **Research**: D8 (hard-fail trigger conditions), D9 (dedup query format)
- **Data model**: Entity 5 (hard-fail bug body template)
- **Dependency**: WP02 (the `EscalationStateError` taxonomy from derive_state feeds the `reason` field)
- **Existing issue-filing helper**: `scripts/openclaw/agents/main/felix-file-issue.py` — the canonical issue-filing surface. WP04 invokes it as a subprocess; does NOT reimplement it.
- **Memory reference**: `reference_vikunja_id_vs_identifier.md` — Vikunja `id` is immutable; basis for dedup robustness.
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T012 — Implement `scripts/escalation/hard_fail.py`

**Purpose**: Pure helpers + the `file_hard_fail_bug` function. No CLI (this is library code consumed by WP05).

**Steps**:

1. Module docstring describing the Q10 hard-fail surface + dedup behavior.
2. Imports: stdlib only (`json`, `subprocess`, `dataclasses`, `datetime`, `typing`, `pathlib`).
3. Module constants:
   ```python
   REPO = "kentonium3/kg-automation"
   HARD_FAIL_LABELS = ["P2-bug", "area/escalation"]
   ```
4. Define `HardFailReason` Literal type:
   ```python
   HardFailReason = Literal[
       "malformed_jsonl_record",
       "phantom_subscription",
       "derive_state_inconsistency",
   ]
   ```
5. Implement `dedup_existing_open(task_id: int) -> Optional[str]`:
   - Run `gh issue list --repo {REPO} --state open --search 'in:title "(task #<id>)" "Escalation hard-fail"' --json number,title,url --limit 5` via `subprocess.run(check=True, capture_output=True, text=True)`.
   - Parse JSON. If any result, return the first match's `url`. Else return `None`.
   - On `subprocess.CalledProcessError`: re-raise (caller decides). Don't silently swallow — gh failures must surface.
6. Implement `render_bug_body(*, task_id, project_id, task_title, reason, jsonl_path, detection_snippet, vikunja_state, derive_state_error_message=None) -> tuple[str, str]`:
   - Returns `(title, body)`.
   - Title format per data-model Entity 5: `Escalation hard-fail: <task title> (task #<vikunja_id>) — <short reason>`.
   - `short reason` map:
     - `"malformed_jsonl_record"` → `"malformed JSONL"`
     - `"phantom_subscription"` → `"phantom subscription"`
     - `"derive_state_inconsistency"` → `"derive_state error"`
   - Body uses the Markdown template from data-model Entity 5 (verbatim).
7. Implement `file_hard_fail_bug(*, task_id, project_id, task_title, reason, jsonl_path, detection_snippet, vikunja_state, derive_state_error_message=None) -> dict`:
   - Call `dedup_existing_open(task_id)`. If hit, return `{"filed": False, "deduped": True, "existing_url": <url>}`.
   - Render `(title, body)`.
   - Invoke `felix-file-issue.py` via subprocess:
     ```python
     subprocess.run([
         "python3", "-m", "scripts.openclaw.agents.main.felix-file-issue",
         "--title", title,
         "--body-stdin",
         "--labels", ",".join(HARD_FAIL_LABELS),
     ], input=body, text=True, check=True, capture_output=True)
     ```
   - Parse stdout for the issue number/URL (or use `gh issue list` immediately after to confirm).
   - Return `{"filed": True, "deduped": False, "issue_url": <url>}`.
   - On any subprocess failure: return `{"filed": False, "deduped": False, "error": <str>}`.

**Files**:
- `scripts/escalation/hard_fail.py` (new, ~180 lines)

**Validation**:
- [ ] No third-party imports.
- [ ] `python3 -c "from scripts.escalation.hard_fail import render_bug_body, file_hard_fail_bug, dedup_existing_open; print('ok')"` prints `ok`.

---

### T013 — Integration with `felix-file-issue.py`

**Purpose**: Verify the issue-filing interface matches what `felix-file-issue.py` actually accepts. Adjust T012's invocation as needed.

**Steps**:

1. Read `scripts/openclaw/agents/main/felix-file-issue.py` end-to-end (or `scripts/openclaw/agents/main/felix_file_issue.py` — check exact filename via `ls`).
2. Identify the exact CLI surface: required flags, body-via-stdin support, label format (`,`-separated vs repeated `--label`).
3. Verify the helper handles classification labels (P2-bug, area/escalation). If not, T012's invocation may need to use `--p2 --area escalation` or similar.
4. Adjust T012's `subprocess.run` call to match.
5. Document the actual CLI in T012's docstring as a comment.
6. If `felix-file-issue.py` does NOT support body-via-stdin: write the body to a temp file under `tmp_path` (or `/tmp` at runtime) and pass `--body-file <path>`.

**Files**:
- `scripts/escalation/hard_fail.py` (updated invocation, no API surface change)

**Validation**:
- [ ] T012's `file_hard_fail_bug` calls `felix-file-issue.py` with flags it actually accepts.
- [ ] At least one integration-style test (mocked subprocess) verifies the exact argv passed to felix-file-issue.

---

### T014 — Tests for `hard_fail.py`

**Purpose**: Coverage of dedup + filing across the three operational lifecycles per research D9.

**Steps**:

1. Create `tests/escalation/test_hard_fail.py`.
2. Use `monkeypatch` to mock `subprocess.run` calls. Build a `_mock_subprocess` fixture in conftest if missing.
3. Test cases:
   - **render_bug_body**:
     - `test_render_title_format` — title matches `Escalation hard-fail: <title> (task #<id>) — <reason>`.
     - `test_render_title_for_each_reason` — three test cases covering all `HardFailReason` values.
     - `test_render_body_includes_jsonl_path` — body contains the absolute jsonl_path.
     - `test_render_body_includes_detection_snippet` — body contains the raw snippet.
     - `test_render_body_omits_derive_state_error_when_not_provided` — `derive_state_error_message=None` → body section is absent (or shows "n/a").
     - `test_render_body_no_second_brain_paths` — body never contains any `~/second-brain` substring (C-006).
   - **dedup_existing_open**:
     - `test_dedup_returns_url_on_match` — mock `gh issue list` returns one issue → returns the URL.
     - `test_dedup_returns_none_on_empty` — mock returns `[]` → returns `None`.
     - `test_dedup_uses_correct_search_query` — verify the `--search` argv contains `"(task #<id>)"` AND `"Escalation hard-fail"`.
     - `test_dedup_uses_state_open_filter` — verify `--state open` in argv (per D9).
   - **file_hard_fail_bug — dedup behavior**:
     - `test_file_skips_when_dedup_hit` — pre-mock `gh issue list` to return a match. Assert `felix-file-issue.py` is NOT invoked.
     - `test_file_invokes_when_no_dedup_match` — pre-mock `gh issue list` returns empty. Assert `felix-file-issue.py` IS invoked.
   - **Double-fire prevention (D9)**:
     - `test_two_consecutive_ticks_file_only_once` — first tick: empty dedup → fired. Second tick: mock dedup to now return the just-filed issue → no second filing.
   - **Re-fire on close**:
     - `test_refire_after_issue_closed` — mock dedup returns empty (the open-state filter excludes closed) → fired again.
   - **Subprocess failure**:
     - `test_file_returns_error_on_subprocess_failure` — mock `subprocess.run` raises `CalledProcessError`. Assert return dict has `filed=False, error="..."`.
4. Coverage target: ≥85% line + branch.

**Files**:
- `tests/escalation/test_hard_fail.py` (new, ~280 lines, ~14 test cases)

**Validation**:
- [ ] `pytest tests/escalation/test_hard_fail.py -v` all green.
- [ ] Coverage ≥85% line + branch on `scripts.escalation.hard_fail`.
- [ ] At least one test verifies the exact `gh` argv (verbatim per D9).
- [ ] At least one test verifies double-fire prevention across two simulated ticks.

---

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Execution worktree allocated per `lanes.json` after `finalize_tasks`.

## Test Strategy

All subprocess calls (`gh`, `felix-file-issue.py`) mocked via monkeypatched `subprocess.run`. No live GitHub API access in tests. Coverage ≥85% on the module.

## Definition of Done

- [ ] T012-T014 subtasks complete with all validations green.
- [ ] `pytest tests/escalation/test_hard_fail.py -v` passes.
- [ ] Coverage ≥85% line + branch.
- [ ] gh dedup query format verified verbatim against research D9.
- [ ] Body rendering matches data-model Entity 5 template.

## Risks

- **gh query format**: must use `--state open` and the exact `in:title` syntax per D9. A typo in the search string causes silent dedup failure (always filing new bugs).
- **felix-file-issue.py interface drift**: T013 verifies the actual CLI. If felix-file-issue is later refactored, this WP's subprocess call breaks.
- **Vikunja id immutability assumption**: dedup relies on `(task #<id>)` substring matching. If Vikunja ever reissues ids (unlikely per memory ref), dedup fails. Pre-flight verifies this assumption holds.

## Reviewer Guidance

1. Verify the gh search query matches D9 exactly.
2. Verify the bug body template matches data-model Entity 5 verbatim.
3. Read the `_format_v1_comment` produced by WP03 and verify no overlap with hard-fail bug rendering (these are separate surfaces).
4. Verify no second-brain paths can leak into bug bodies (C-006).
5. Coverage report ≥85%.

## Implementation Command

```bash
spec-kitty agent action implement WP04 --mission migrate-escalation-to-jsonl-state-model-01KS5R4D --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-21T20:14:47Z – claude:opus:python-implementer:implementer – shell_pid=94862 – Started implementation via action command
- 2026-05-21T20:22:33Z – claude:opus:python-implementer:implementer – shell_pid=94862 – Ready for review — dedup verified, double-fire prevention tested, 87% coverage. Untracked files in worktree belong to concurrent WP03 (record_completion.py, test_record_completion.py) and a .coverage artifact; not WP04 scope.
- 2026-05-21T20:23:12Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=96577 – Started review via action command
- 2026-05-21T20:26:02Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=96577 – Moved to planned
- 2026-05-21T20:27:59Z – claude:opus:python-implementer:implementer – shell_pid=98523 – Started implementation via action command
