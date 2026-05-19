---
work_package_id: WP03
title: Completion + reconcile helpers
dependencies:
- WP01
requirement_refs:
- C-005
- FR-006
- FR-007
- FR-008
- FR-009
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
- T011
- T012
agent: "claude:opus:python-implementer:implementer"
shell_pid: "58292"
history:
- at: '2026-05-19T17:30:00Z'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/habits/
execution_mode: code_change
mission_id: 01KS0M59313RF0WVJZTXYDJC6C
mission_slug: habits-native-repeat-jsonl-state-01KS0M59
owned_files:
- scripts/habits/record_completion.py
- scripts/habits/reconcile_completions.py
- tests/habits/test_record_completion.py
- tests/habits/test_reconcile_completions.py
tags: []
---

# WP03 — Completion + reconcile helpers

## Objective

Build the two Phase 5-consumed helpers — `record_completion.py` (three-write atomic completion) and `reconcile_completions.py` (Vikunja-UI backfill + drift detection). Both are testable standalone but won't be invoked by the cron until Phase 5 cutover (#308).

## Context

- **Mission spec**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/spec.md` — esp. FR-006..FR-009, NFR-002, NFR-003, C-005
- **Plan**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/plan.md`
- **Research**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/research.md` — esp. D4 (three-write ordering), D6 (idempotency), D7 (drift handling), D10 (gotchas G3 + G4)
- **API contract**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/api.md` — `record()` and `reconcile()` signatures
- **CLI contract**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/cli.md` — `record_completion` and `reconcile_completions` CLI
- **Phase 2 library**: `scripts/common/state_log.py` — both helpers import from this
- **Vikunja gotchas**: `docs/design/research/vikunja-task-model-research.md` § Verified API gotchas (G3, G4)
- **Test fixtures**: from WP01's `tests/habits/conftest.py`
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T009 — Implement `scripts/habits/record_completion.py` — `record()` + CLI

**Purpose**: Three-write atomic completion helper per ADR Q3-D. Order: idempotency check via state_log first, then Vikunja `done=true`, then Vikunja comment, then state_log.append.

**Steps**:

1. **Module setup**:
   ```python
   #!/usr/bin/env python3
   """ADR-0002 Phase 3 record_completion helper.

   Three-write atomic completion record per ADR Q3-D:
       (a) POST /tasks/<id> with done=true  -- Vikunja auto-advance trigger
       (b) PUT /tasks/<id>/comments  -- UI-visible mirror
       (c) state_log.append("habits", record)  -- canonical history

   Idempotency: pre-flight read of state_log; if (task_id, date, state)
   tuple already present, exit 0 immediately (no writes).

   See contracts/api.md + contracts/cli.md for the full contract.
   """
   from __future__ import annotations
   import argparse, json, os, sys, urllib.request, urllib.error
   from datetime import datetime, timezone
   from pathlib import Path
   from typing import Optional

   from scripts.common import state_log
   from scripts.common.state_log_schema import DOMAIN_STATES
   ```

2. **Module constants**:
   ```python
   DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"
   DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"
   HTTP_TIMEOUT_SECONDS = 30
   COMMENT_TEMPLATE = "[Felix] {date} | {state}"
   COMMENT_TEMPLATE_WITH_NOTE = "[Felix] {date} | {state} | {note}"
   ```

3. **`_http_request(method, url, token, body=None) -> tuple[int, str]`**: same pattern as WP02.

4. **`_format_comment(date, state, note) -> str`**: returns the formatted comment body (with or without note).

5. **`record(task_id, title, date, state, source, note=None, *, api_base_url, token) -> None`**:
   - Build a candidate record dict matching the Phase 2 state_log schema (domain="habits").
   - Validate via `state_log.validate_record(record, "habits")`. Raises ValueError on invalid.
   - **Step 1 — Idempotency check**:
     - `existing = state_log.read("habits", task_id=task_id, date=date, state=state)`.
     - If non-empty: return None immediately (no writes, exit 0 from CLI).
   - **Step 2 — Vikunja done=true**:
     - PATCH `{api_base_url}tasks/{task_id}` with body `{"done": True}`.
     - On OSError: re-raise with prefix "step 2 (Vikunja done=true) failed".
   - **Step 3 — Vikunja comment** (use PUT per G4):
     - `comment_body = _format_comment(date, state, note)`.
     - PUT `{api_base_url}tasks/{task_id}/comments` with body `{"comment": comment_body}`.
     - On OSError: re-raise with prefix "step 3 (Vikunja comment) failed".
   - **Step 4 — state_log.append**:
     - `state_log.append("habits", record)`.
     - On OSError: re-raise with prefix "step 4 (state_log) failed".

6. **`main(argv=None) -> int`** (CLI):
   - argparse: optional positional/keyword args + `--task-id`, `--title`, `--date`, `--state`, `--source`, `--note`, `--token-file`, `--base-url`.
   - If stdin has content: parse as JSON object → use as record args.
   - Else: build args from flags (require all of `--task-id, --title, --date, --state, --source`).
   - Call `record(...)`. Handle:
     - ValueError → stderr message, exit 3 (usage/validation).
     - OSError with "step 4" prefix → exit 2 (state_log failure; Vikunja already committed).
     - OSError otherwise → exit 1 (Vikunja failure).
   - On success: empty stdout, exit 0.

7. **`if __name__ == "__main__": sys.exit(main())`**.

**Files**:
- `scripts/habits/record_completion.py` (new, ~200 lines)

**Validation**:
- [ ] `python3 -m scripts.habits.record_completion --help` exits 0.
- [ ] Imports `from scripts.common import state_log` — Phase 2 library is in use.
- [ ] No third-party imports.

---

### T010 — Implement `scripts/habits/reconcile_completions.py` — `reconcile()` + CLI

**Purpose**: Detect missing JSONL entries (backfill from Vikunja-UI completions); detect drift (JSONL says complete, Vikunja says done=false). Exit 0 even with drift.

**Steps**:

1. **Module setup + constants**: same imports as record_completion.

2. **`_enumerate_active_habits(api_base_url, token) -> list[dict]`**:
   - GET `{api_base_url}tasks?filter_by[]=is_archived&filter_value[]=false&...` — or use the existing project-scoped enumeration. (Reference: existing `scripts/habits/query_active_habits.py` for the filter pattern.)
   - Return list of task dicts.

3. **`_done_at_date(task) -> str | None`**:
   - If `task["done_at"]` is null OR empty OR `"0001-01-01T00:00:00Z"` (Vikunja zero sentinel): return None.
   - Else parse `done_at` as datetime, return the UTC date portion as ISO string `YYYY-MM-DD`.

4. **`reconcile(api_base_url, token, today=None) -> dict`**:
   - `today = today or datetime.now(timezone.utc).date().isoformat()`.
   - Enumerate active habits via `_enumerate_active_habits`.
   - Initialize result: `{tasks_examined: 0, backfilled: [], drift: [], errors: []}`.
   - For each task:
     - Increment `tasks_examined`.
     - **Backfill check**: if `task["done"]` is True:
       - `done_date = _done_at_date(task)`.
       - If `done_date` is None (Vikunja shows done but no done_at — odd; log error): append to `result["errors"]` with description.
       - Else: `existing = state_log.read("habits", task_id=task["id"], date=done_date, state="complete")`.
         - If empty: append a backfill record (state_log.append with `source="vikunja-ui"`), add to `result["backfilled"]`.
     - **Drift check**: query state_log for today's date with `state="complete"`:
       - `today_records = state_log.read("habits", task_id=task["id"], date=today, state="complete")`.
       - If non-empty AND `task["done"]` is False: drift detected. Append to `result["drift"]`.
   - Return result dict.

5. **`main(argv=None) -> int`** (CLI):
   - argparse: `--today YYYY-MM-DD` (optional), `--token-file`, `--base-url`.
   - Read token from file.
   - Call `reconcile(...)`. On unrecoverable OSError → exit 1.
   - Print summary block to stdout: "tasks_examined", "backfilled" (with task_id + date for each), "drift" (with DRIFT: prefix per format), "errors".
   - Exit 0 regardless of drift count (drift is informational).

6. **`if __name__ == "__main__": sys.exit(main())`**.

**Files**:
- `scripts/habits/reconcile_completions.py` (new, ~180 lines)

**Validation**:
- [ ] `python3 -m scripts.habits.reconcile_completions --help` exits 0.
- [ ] Drift detection emits the DRIFT: prefix; exit code is 0.

---

### T011 — Create `tests/habits/test_record_completion.py`

**Purpose**: Exhaustive coverage of record_completion.

**Steps**:

1. **Fixtures** (reuse conftest fixtures from WP01).

2. **Test: happy path — three writes succeed in order**:
   - Mock state_log.read to return empty.
   - Mock urlopen with two canned responses (done=true PATCH + comment PUT).
   - Mock state_log.append.
   - Call `record(...)`. Assert: state_log.read called once, urlopen called twice (in the right order via MagicMock.call_args_list), state_log.append called once.

3. **Test: idempotent no-op**:
   - Mock state_log.read returns a matching record.
   - Call `record(...)`. Assert: NO urlopen calls, NO state_log.append.

4. **Test: validation failure (invalid state)**:
   - Build a record with `state="Complet"` (typo).
   - Expect ValueError from state_log.validate_record before any I/O.

5. **Test: step 2 fail (Vikunja done=true)**:
   - urlopen mock raises HTTPError on first call.
   - Expect OSError with "step 2" in message; state_log.append NOT called.

6. **Test: step 3 fail (Vikunja comment)**:
   - urlopen mock succeeds on done=true, raises on comment PUT.
   - Expect OSError with "step 3"; state_log.append NOT called.

7. **Test: step 4 fail (state_log)**:
   - urlopen mocks succeed.
   - state_log.append raises OSError.
   - Expect OSError with "step 4"; the Vikunja side is already committed.

8. **Test: comment uses PUT method (G4)**:
   - Inspect urlopen.call_args_list[1] — the Request object's `method` attribute is "PUT".

9. **Test: comment body format**:
   - With note: `[Felix] 2026-05-20 | complete | travel — no gym`.
   - Without note: `[Felix] 2026-05-20 | complete`.

10. **Test: CLI happy path** (subprocess or in-process):
    - Stdin = JSON record. Verify exit 0, no stdout.

11. **Test: CLI step-2-fail exit code 1**:
    - Subprocess + mocked HTTP (or in-process main()).
    - Verify exit 1, stderr names step 2.

**Files**:
- `tests/habits/test_record_completion.py` (new, ~250 lines)

**Validation**:
- [ ] `pytest tests/habits/test_record_completion.py -v` — all tests pass.
- [ ] Coverage ≥ 85% (slightly lower than Phase 2's 90% because some CLI exit-code branches are subprocess-only).

---

### T012 — Create `tests/habits/test_reconcile_completions.py`

**Purpose**: Coverage of reconcile_completions.

**Steps**:

1. **Test: backfill from Vikunja UI completion**:
   - Mock urlopen enumerate returns 1 active habit with `done=true, done_at="2026-05-19T11:00:00Z"`.
   - Mock state_log.read returns empty.
   - Call `reconcile(...)`. Assert state_log.append called with `source="vikunja-ui"`, date="2026-05-19".

2. **Test: no backfill needed**:
   - Mock urlopen returns 1 habit done=true.
   - Mock state_log.read returns a matching record.
   - reconcile() returns with `backfilled: []`.

3. **Test: drift detection**:
   - Mock urlopen returns 1 habit done=false.
   - Mock state_log.read for `today` with `state=complete` returns a non-empty record.
   - reconcile() returns with one entry in `drift`.

4. **Test: zero-sentinel done_at**:
   - Mock urlopen returns habit with `done=true, done_at="0001-01-01T00:00:00Z"`.
   - `_done_at_date` returns None; reconcile records an error, no backfill.

5. **Test: today-override**:
   - Call `reconcile(today="2026-05-15")`. Drift detection uses 2026-05-15 instead of system date.

6. **Test: CLI exit 0 even with drift**:
   - Subprocess + mocked HTTP producing drift.
   - Exit 0; stdout contains DRIFT: prefix line.

7. **Test: CLI exit 1 on enumerate failure**:
   - Mock urlopen for enumerate raises HTTPError.
   - Exit 1.

**Files**:
- `tests/habits/test_reconcile_completions.py` (new, ~200 lines)

**Validation**:
- [ ] `pytest tests/habits/test_reconcile_completions.py -v` — all tests pass.
- [ ] Coverage ≥ 85%.

---

## Branch Strategy

- **Execution worktree**: per `lanes.json`. WP03 depends on WP01 approval.
- **Planning base / merge target**: `main`.

## Definition of Done

- [ ] All 4 subtasks T009-T012 complete and individually validated.
- [ ] `python3 -m scripts.habits.record_completion --help` exits 0.
- [ ] `python3 -m scripts.habits.reconcile_completions --help` exits 0.
- [ ] `pytest tests/habits/test_record_completion.py tests/habits/test_reconcile_completions.py -v` passes with all tests green.
- [ ] Coverage on both source modules ≥ 85%.
- [ ] record_completion uses PUT (not POST) for the comment write (G4 honored).
- [ ] No new third-party dependencies.
- [ ] All files committed; no uncommitted artifacts.

## Risks & mitigations

- **G4 enforcement**: PUT-not-POST for comment creation. Easy to get wrong if implementer copies a generic "POST a comment" pattern from elsewhere. Test #8 in T011 is the explicit guard.
- **G3 awareness**: when verifying the comment readback (if a verify step is added), consult `author.username` not `created_by`. Not directly tested in WP03 because verify-readback isn't part of the FR scope, but worth a note for the reviewer.
- **Idempotency must check state on the (task_id, date, state) tuple**: Phase 2's state_log.read with all three filters does this. Verify the call in the implementation includes ALL three kwargs.
- **Drift exits 0**: easy to accidentally make drift exit non-zero. The test #6 in T012 is the explicit guard.
- **Zero-sentinel done_at**: Vikunja returns `0001-01-01T00:00:00Z` for unset done_at. Helper must treat this as "not set", not as a valid 1AD timestamp.

## Reviewer guidance

- Check imports: stdlib + `scripts.common.state_log` only.
- Verify the three-write ordering per research D4 (idempotency check, then Vikunja done=true, then Vikunja comment PUT, then state_log).
- Verify the comment uses PUT method (search for "PUT" in record_completion.py; should appear at the comment write site).
- Verify drift detection uses `today` parameter override (not just `datetime.now()`).
- Verify reconcile exit code is 0 even with drift (the test verifies this; spot-check the main() return).
- Coverage report ≥ 85% on both modules.

## Implementation command

```bash
spec-kitty agent action implement WP03 --mission habits-native-repeat-jsonl-state-01KS0M59 --agent <agent-name>
```

WP03 depends on WP01; can run in parallel with WP02 and WP04 after WP01 approval.

## Activity Log

- 2026-05-19T19:19:55Z – claude:opus:python-implementer:implementer – shell_pid=58292 – Started implementation via action command
