---
work_package_id: WP01
title: Schema foundation + escalation package skeleton
dependencies: []
requirement_refs:
- C-003
- FR-003
- NFR-003
- NFR-004
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-migrate-escalation-to-jsonl-state-model-01KS5R4D
base_commit: 7e73197665540941ac21b6fc6073d05b20e659f6
created_at: '2026-05-21T19:18:25.300159+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: "83009"
agent: "codex:gpt-5:spec-kitty-review:reviewer"
history:
- at: '2026-05-21T17:45:30+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/escalation/
execution_mode: code_change
mission_id: 01KS5R4D79WQQWY2MCHZVCT85G
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
owned_files:
- scripts/common/state_log_schema.py
- scripts/escalation/__init__.py
- scripts/escalation/schema.py
- tests/escalation/__init__.py
- tests/escalation/conftest.py
- tests/escalation/test_schema.py
tags: []
---

# WP01 — Schema foundation + escalation package skeleton

## Objective

Lay down the package structure, update `DOMAIN_STATES["escalation"]` with the Phase 6 flat-enum vocabulary, implement the per-event_type schema validator (`scripts/escalation/schema.py`), and scaffold `tests/escalation/` with shared fixtures consumed by WP02–WP06. Unblocks every downstream code WP.

## Context

- **Mission spec**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/spec.md` — FR-003 (flat-enum schema), NFR-005 (schema reviewability), C-003 (amended — DOMAIN_STATES updates permitted)
- **Plan**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/plan.md`
- **Research**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/research.md` — D1 (DOMAIN_STATES update rationale)
- **Data model**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/data-model.md` — Entity 1 (JSONL record), Entity 2 (DOMAIN_STATES enum)
- **API contract**: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md` — `EVENT_TYPE_PARAMETERS`, `validate_event_params`, `EscalationSchemaError`
- **Phase 2 library**: `scripts/common/state_log.py` + `scripts/common/state_log_schema.py` — owns the shared `state_log` substrate
- **Habits Phase 3 precedent**: `scripts/habits/` for module-style + `tests/habits/conftest.py` for fixture patterns
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree allocated per `lanes.json`.

## Subtasks

### T001 — Extend DOMAIN_STATES["escalation"] in `scripts/common/state_log_schema.py`

**Purpose**: Replace the placeholder Phase 2 escalation enum with the Q1=A flat-enum vocabulary per research D1.

**Steps**:

1. Open `scripts/common/state_log_schema.py`.
2. Locate the `DOMAIN_STATES` dict (currently around line 31).
3. Replace the `"escalation"` value:
   ```python
   # BEFORE
   "escalation": frozenset(
       {"triggered", "level-1", "level-2", "resolved", "dismissed"}
   ),

   # AFTER
   "escalation": frozenset({
       "level_sent",
       "snoozed",
       "dismissed",
       "done",
       "rescheduled",
   }),
   ```
4. Keep formatting consistent with neighboring entries. Trailing comma on each member; one-per-line for readability per NFR-005.
5. Do NOT change any other code in this file. No new imports. No edits to `validate_record` or `StateLogRecord`.

**Files**:
- `scripts/common/state_log_schema.py` (modified — 5-line vocabulary diff)

**Validation**:
- [ ] `python3 -c "from scripts.common.state_log_schema import DOMAIN_STATES; print(sorted(DOMAIN_STATES['escalation']))"` prints `['dismissed', 'done', 'level_sent', 'rescheduled', 'snoozed']`.
- [ ] No other lines in `state_log_schema.py` changed. Verify via `git diff scripts/common/state_log_schema.py`.
- [ ] Existing habits tests still pass: `pytest tests/habits/ -q`.

---

### T002 — Create `scripts/escalation/` package skeleton

**Purpose**: Establish the new package directory.

**Steps**:

1. Create empty `scripts/escalation/__init__.py`.
2. Verify the package is importable: `python3 -c "import scripts.escalation"` exits 0.

**Files**:
- `scripts/escalation/__init__.py` (new, empty)

**Validation**:
- [ ] `python3 -c "import scripts.escalation; print(scripts.escalation.__name__)"` prints `scripts.escalation`.

---

### T003 — Implement `scripts/escalation/schema.py`

**Purpose**: Implement the per-event_type parameter-validator surface per contracts/api.md + data-model Entity 1.

**Steps**:

1. Module docstring describing the surface (per contracts/api.md, data-model Entity 1).
2. Imports: stdlib only (`re`, `datetime`).
3. Define `EVENT_TYPE_PARAMETERS` exactly:
   ```python
   EVENT_TYPE_PARAMETERS: dict[str, frozenset[str]] = {
       "level_sent":   frozenset({"level"}),
       "snoozed":      frozenset({"snooze_days", "snooze_until"}),
       "dismissed":    frozenset(),  # no required params; optional `reason`
       "done":         frozenset(),  # no required params; optional `reason`
       "rescheduled":  frozenset({"reschedule_to"}),
   }
   ```
4. Define `class EscalationSchemaError(Exception)` with one-line docstring. Use plain `Exception` subclass; no chained-cause complexity.
5. Define `_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")` matching the Phase 2 pattern.
6. Implement `validate_event_params(record: dict) -> None`:
   - Short-circuit on first violation. Raise `EscalationSchemaError` with field-named, value-quoted message.
   - Step (a): `state = record.get("state")`. If missing or not in `EVENT_TYPE_PARAMETERS`, raise.
   - Step (b): For each `field` in `EVENT_TYPE_PARAMETERS[state]`, ensure `field in record`.
   - Step (c): Type checks per parameter:
     - `level`: int in `{1, 2}`
     - `snooze_days`: int > 0
     - `snooze_until`: str matching `_DATE_RE`, and `datetime.date.fromisoformat(value)` parses
     - `reschedule_to`: str matching `_DATE_RE`, parses via `date.fromisoformat`
   - Step (d): `project_id` is required across all event_types (per data-model Entity 1): int > 0.
   - Optional fields: `reason` (str if present), `note` (str or None per Phase 2 library — passed through; the Phase 2 `validate_record` will catch type errors).
7. Module structure: matches `scripts/common/state_log_schema.py` convention — module-level constants, helper(s), then the validator function.
8. Total length target: ~120-150 lines including docstring + spaced sections.

**Files**:
- `scripts/escalation/schema.py` (new, ~150 lines)

**Validation**:
- [ ] `python3 -c "from scripts.escalation.schema import EVENT_TYPE_PARAMETERS, validate_event_params, EscalationSchemaError; print(sorted(EVENT_TYPE_PARAMETERS.keys()))"` prints `['dismissed', 'done', 'level_sent', 'rescheduled', 'snoozed']`.
- [ ] No third-party imports: `grep -E '^(import|from)\s+(?!re|datetime|__future__)' scripts/escalation/schema.py` returns nothing.
- [ ] A reviewer reading the file alone can enumerate every event_type's required parameters (NFR-005 review check).

---

### T004 — Create `tests/escalation/__init__.py` + `tests/escalation/conftest.py`

**Purpose**: Establish the `tests/escalation/` package and shared fixtures used by WP02–WP06.

**Steps**:

1. Create empty `tests/escalation/__init__.py`.
2. Create `tests/escalation/conftest.py` with these pytest fixtures:

   **`fake_vikunja_token`**: returns `"test-token-xxx"`.

   **`tmp_token_file(tmp_path, fake_vikunja_token)`**: writes the token to `tmp_path / "token"` (mode 0600) and returns its path.

   **`sample_vikunja_task`**: callable factory:
   ```python
   def _make(task_id, title="Task", done=False, project_id=4, priority=3,
             due_date="2026-05-15T00:00:00Z", comments=None):
       return {
           "id": task_id, "title": title, "done": done,
           "project_id": project_id, "priority": priority,
           "due_date": due_date, "comments": comments or [],
       }
   ```

   **`make_felix_comment`**: callable factory returning a Vikunja-API-shaped comment dict:
   ```python
   def _make(comment_text, comment_id=1, created="2026-05-15T08:00:00Z"):
       return {"id": comment_id, "comment": comment_text, "created": created}
   ```

   **`make_jsonl_record`**: callable factory matching data-model Entity 1:
   ```python
   def _make(task_id=1234, project_id=4, state="level_sent", date="2026-05-21",
             source="agent", title="Task", note=None, **params):
       record = {
           "domain": "escalation", "task_id": task_id, "title": title,
           "date": date, "state": state, "source": source,
           "timestamp": f"{date}T12:00:00+00:00", "note": note,
           "project_id": project_id,
       }
       record.update(params)
       return record
   ```

   **`mock_state_log_dir(tmp_path, monkeypatch)`**: monkey-patches the state log path module constant to `tmp_path / "state" / "escalation"` and creates it. Returns the path.

   **`mock_urlopen(monkeypatch)`**: same shape as habits `conftest.py`. Returns a `MagicMock` configurable per-test.

3. Module docstring listing available fixtures.

**Files**:
- `tests/escalation/__init__.py` (new, empty)
- `tests/escalation/conftest.py` (new, ~120 lines)

**Validation**:
- [ ] `pytest tests/escalation/ --collect-only` lists T005's test module without ImportError.
- [ ] All fixtures are session-safe (no per-test global state).

---

### T005 — Tests for `scripts/escalation/schema.py`

**Purpose**: Exhaustive coverage of `validate_event_params` — every event_type, every required parameter, every type-error path.

**Steps**:

1. Create `tests/escalation/test_schema.py`.
2. Test cases per event_type happy-path (use `make_jsonl_record` fixture):
   - `test_validate_level_sent_happy_path` — record with `state="level_sent"`, `level=1`, `project_id=4`. Asserts no exception.
   - `test_validate_snoozed_happy_path` — `state="snoozed"`, `snooze_days=3`, `snooze_until="2026-05-24"`.
   - `test_validate_dismissed_happy_path` — `state="dismissed"`, optional `reason="Not relevant"`.
   - `test_validate_done_happy_path` — `state="done"`.
   - `test_validate_rescheduled_happy_path` — `state="rescheduled"`, `reschedule_to="2026-06-15"`.
3. Test cases for unknown state:
   - `test_validate_unknown_state_raises` — `state="acknowledged"` raises `EscalationSchemaError` with "state" in message.
4. Test cases for missing required parameter (per event_type):
   - `test_validate_level_sent_missing_level_raises`
   - `test_validate_snoozed_missing_snooze_days_raises`
   - `test_validate_snoozed_missing_snooze_until_raises`
   - `test_validate_rescheduled_missing_reschedule_to_raises`
5. Test cases for bad type / bad value:
   - `test_validate_level_sent_bad_level_value` — `level=3` raises (must be 1 or 2)
   - `test_validate_snoozed_bad_snooze_until_date` — `snooze_until="not-a-date"` raises
   - `test_validate_rescheduled_bad_reschedule_to` — `reschedule_to="2026-13-99"` raises (invalid date)
   - `test_validate_snoozed_negative_snooze_days` — `snooze_days=-1` raises
6. Test cases for the shared `project_id` field:
   - `test_validate_missing_project_id_raises`
   - `test_validate_bad_project_id_type_raises` — `project_id="4"` (str instead of int) raises
7. Test case for short-circuit behavior:
   - `test_validate_short_circuits_on_first_error` — record with multiple errors raises ONCE with the first-encountered field named.
8. Use `pytest.raises(EscalationSchemaError) as excinfo:` and assert the field name appears in `str(excinfo.value)` for each error path.

**Files**:
- `tests/escalation/test_schema.py` (new, ~220 lines covering ~14 test cases)

**Validation**:
- [ ] `pytest tests/escalation/test_schema.py -v` all green.
- [ ] `pytest tests/escalation/test_schema.py --cov=scripts.escalation.schema --cov-report=term-missing` shows ≥85% line + branch coverage.
- [ ] No test mocks the schema module itself — schema.py is the SUT.

---

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Execution worktree allocated per `lanes.json` after `finalize_tasks`.

## Test Strategy

pytest-based unit tests under `tests/escalation/test_schema.py`. NFR-004 requires ≥85% line + branch coverage on the helper. The schema module is pure (no I/O), so all tests are fast and deterministic.

## Definition of Done

- [ ] T001-T005 subtasks complete with all validations green.
- [ ] `pytest tests/escalation/ -v` passes.
- [ ] `pytest tests/habits/ -q` still passes (no Phase 2 regression).
- [ ] `git diff --stat scripts/common/state_log_schema.py` shows only the 5-line vocabulary change.
- [ ] WP frontmatter `owned_files` matches all files modified.

## Risks

- **Touching scripts/common/state_log_schema.py**: amended C-003 permits the vocabulary update only. Reviewer must verify the diff scope is the DOMAIN_STATES["escalation"] frozenset and nothing else.
- **Existing escalation records under the old enum**: pre-flight should verify none exist on office2 (`find /data/services/openclaw/state -name '*escalation*history*' | xargs cat 2>/dev/null | wc -l` should print 0). If any are found, halt this WP and triage.

## Reviewer Guidance

1. Verify the DOMAIN_STATES diff is exactly 5 lines + braces. No other library changes.
2. Verify `EVENT_TYPE_PARAMETERS` matches data-model Entity 1 (5 event_types, exactly these required params).
3. Read `scripts/escalation/schema.py` end-to-end and confirm a reader can enumerate every event_type's required parameters without running tests (NFR-005 review).
4. Coverage: `pytest tests/escalation/test_schema.py --cov=scripts.escalation.schema --cov-report=term-missing` ≥85%.
5. No third-party imports anywhere in scripts/escalation/*.

## Implementation Command

```bash
spec-kitty agent action implement WP01 --mission migrate-escalation-to-jsonl-state-model-01KS5R4D --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-21T19:18:27Z – claude:opus:python-implementer:implementer – shell_pid=78836 – Assigned agent via action command
- 2026-05-21T19:26:37Z – claude:opus:python-implementer:implementer – shell_pid=78836 – Ready for review — all subtasks complete, coverage ≥85%, regression-free
- 2026-05-21T19:39:56Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=83009 – Started review via action command
- 2026-05-21T19:43:17Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=83009 – Moved to planned
