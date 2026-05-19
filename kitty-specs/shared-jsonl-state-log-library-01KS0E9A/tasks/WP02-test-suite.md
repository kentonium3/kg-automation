---
work_package_id: WP02
title: Test suite — append, read, concurrency, CLI, coverage
dependencies:
- WP01
requirement_refs:
- NFR-001
- NFR-002
- NFR-003
- NFR-004
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
- T011
agent: "claude:opus:python-implementer:implementer"
shell_pid: "27847"
history:
- at: '2026-05-19T15:51:00Z'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: tests/common/
execution_mode: code_change
mission_id: 01KS0E9A6TZBA9AWT97DR1XMQB
mission_slug: shared-jsonl-state-log-library-01KS0E9A
owned_files:
- tests/common/**
tags: []
---

# WP02 — Test suite (happy path, validation, idempotency, concurrency, CLI)

## Objective

Establish exhaustive automated test coverage for the library shipped in WP01. Verify happy paths, every validation failure mode, idempotency dedup, multiprocess concurrent-append correctness (NFR-003), and the CLI surface. Achieve ≥ 90% line + branch coverage (NFR-005).

## Context

- **WP01 must be merged first.** This WP imports `scripts.common.state_log` and assumes the module-level `STATE_DIR` constant is monkey-patchable.
- **Source issue**: [#305](https://github.com/kentonium3/kg-automation/issues/305)
- **Spec**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/spec.md` — NFR-001..NFR-005 and SC-001..SC-007 are the targets.
- **API contract**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/api.md`
- **CLI contract**: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/cli.md`
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree allocated per the computed lane from `lanes.json`. The lane's branch is created off `main` (with WP01 already merged) and merges back to `main` on approval.

## Subtasks

### T007 — Create `tests/common/__init__.py`

**Purpose**: Make `tests/common/` an importable package for pytest discovery.

**Steps**:
1. Create directory `tests/common/`.
2. Create empty file `tests/common/__init__.py`.

**Validation**:
- [ ] `pytest tests/common/ --collect-only` lists the test modules created in T008-T011 without ImportError.

---

### T008 — `tests/common/test_state_log_append.py`

**Purpose**: Cover every behavior of `append()` — happy path, every validation rejection, idempotency dedup, and the bootstrap-on-first-call directory/file creation.

**Steps**:

1. **Fixtures**:
   ```python
   @pytest.fixture
   def state_dir(tmp_path, monkeypatch):
       d = tmp_path / "state"
       monkeypatch.setattr("scripts.common.state_log.STATE_DIR", d)
       return d

   @pytest.fixture
   def good_habits_record():
       return {
           "domain": "habits",
           "task_id": 14,
           "title": "Wake at 5:00 AM",
           "date": "2026-05-19",
           "state": "complete",
           "source": "whatsapp",
           "note": None,
           "timestamp": "2026-05-19T11:05:11+00:00",
       }
   ```

2. **Happy path** (`test_append_happy_path_creates_file`):
   - Call `append("habits", good_habits_record)`.
   - Assert state_dir exists, mode 0o775.
   - Assert habits-history.jsonl exists, mode 0o664.
   - Assert file has exactly one line, parses as the same record.

3. **Idempotency** (`test_append_is_idempotent_on_dedup_tuple`):
   - Call append twice with the same record.
   - Assert file has exactly one line (no duplicate written, no exception).

4. **Different state for same task+date IS a separate record** (`test_append_different_state_creates_new_record`):
   - Append with state="incomplete", then state="complete" (same task_id + date).
   - Assert file has two lines.

5. **Validation: missing required field** (parametrized over each REQUIRED_FIELDS):
   - Remove one field at a time; expect `ValueError` mentioning that field name.

6. **Validation: state not in domain enum** (parametrized over 3 domains):
   - For each domain, supply an invalid state value (e.g., habits with `state="Complete"` — note capitalization).
   - Expect `ValueError` quoting the invalid state and the allowed set.

7. **Validation: wrong field type** (parametrized):
   - `task_id` as string, as 0, as negative — expect ValueError each.
   - `title` empty / whitespace-only — expect ValueError.
   - `date` wrong format (`2026/05/19`, `5-19-2026`, `2026-05-32`) — expect ValueError.
   - `timestamp` without timezone (`2026-05-19T11:00:00`) — expect ValueError.
   - `note` as int or list (when present) — expect ValueError.

8. **Validation: unknown domain** (`test_append_unknown_domain_raises`):
   - `append("unknown_domain", record)` — expect ValueError mentioning the allowed domains.

9. **Validation: record domain ≠ argument domain** (`test_append_mismatched_domain_raises`):
   - Record has `domain="habits"` but called with `domain="escalation"` — expect ValueError.

**Files**:
- `tests/common/test_state_log_append.py` (new, ~250 lines including fixtures + parametrized cases)

**Validation**:
- [ ] `pytest tests/common/test_state_log_append.py -v` — all tests pass.
- [ ] Tests use `tmp_path` exclusively; production `/data/services/openclaw/state/` is NOT touched.

---

### T009 — `tests/common/test_state_log_read.py`

**Purpose**: Cover every filter combination of `read()`, including the empty-file path, the unknown-kwarg path, and ordering preservation.

**Steps**:

1. **Fixtures** (reuse `state_dir` and `good_habits_record` patterns from T008 — extract to a shared `conftest.py` in `tests/common/`).

2. **Empty result on missing file** (`test_read_returns_empty_list_when_file_missing`):
   - Without any append, call `read("habits")`. Assert returns `[]`.

3. **All-records on no-filter call** (`test_read_returns_all_records_in_append_order`):
   - Append 3 records (different task_id + date). Call `read("habits")`. Assert returns the 3 in append order.

4. **Filter by task_id**:
   - Append records for tasks 14, 15, 17. `read("habits", task_id=14)` returns only the 14-record(s).

5. **Filter by date exact**:
   - Append records for 2026-05-17, 2026-05-18, 2026-05-19. `read("habits", date="2026-05-18")` returns only the 05-18 record(s).

6. **Filter by date range**:
   - `read("habits", date_from="2026-05-18", date_to="2026-05-19")` — inclusive, both ends included.
   - Single-day range: `date_from = date_to` returns matches for that day.
   - Empty range (`date_from > date_to`): returns `[]`.

7. **Filter by state**:
   - `read("habits", state="skipped")` returns only skipped records.

8. **Filter by source**:
   - `read("habits", source="vikunja-ui")` returns only backfilled records.

9. **Combined filters (AND)**:
   - `read("habits", task_id=14, state="complete")` returns matches on BOTH.

10. **Unknown kwarg raises TypeError**:
    - `read("habits", task=14)` (typo) raises `TypeError` mentioning the unknown kwarg.

11. **Unknown domain raises ValueError**:
    - `read("unknown_domain")` raises `ValueError`.

12. **Forward-compatibility**:
    - Manually write a line with an unknown extra field (e.g., `"extra_field": "future"`). `read()` returns the record with the extra field preserved (or dropped — match the implementation, but assert behavior).

**Files**:
- `tests/common/test_state_log_read.py` (new, ~220 lines)

**Validation**:
- [ ] `pytest tests/common/test_state_log_read.py -v` — all tests pass.

---

### T010 — `tests/common/test_state_log_concurrent.py`

**Purpose**: Verify NFR-003 — multiprocess concurrent-append correctness. 100 trials per test run, no race-condition failures.

**Steps**:

1. **Force spawn start method** at module top:
   ```python
   import multiprocessing
   multiprocessing.set_start_method("spawn", force=True)
   ```
   This ensures the test behaves identically on macOS (default spawn) and Linux (default fork).

2. **Helper for worker subprocesses** (must be module-level for pickling):
   ```python
   def _append_worker(state_dir_path: str, worker_id: int, records_per_worker: int) -> None:
       from scripts.common import state_log
       state_log.STATE_DIR = pathlib.Path(state_dir_path)
       for i in range(records_per_worker):
           state_log.append("habits", {
               "domain": "habits",
               "task_id": worker_id * 100 + i,  # unique per (worker, iter)
               "title": f"task {worker_id}-{i}",
               "date": "2026-05-19",
               "state": "complete",
               "source": "test",
               "note": None,
               "timestamp": f"2026-05-19T11:00:{i:02d}+00:00",
           })
   ```

3. **Main test** (`test_concurrent_append_100_trials_no_corruption`):
   - Use `multiprocessing.Pool(10)` with each worker doing 10 appends → 100 records total.
   - After pool completes:
     a. Assert file has exactly 100 lines.
     b. Each line parses as valid JSON.
     c. Set of `(task_id,)` covers exactly the expected 100 values (no duplicates, no losses).
     d. No line has truncated / interleaved content (already implied by valid JSON parse, but assert explicitly via length sanity check).

4. **Idempotency-under-concurrency test** (`test_concurrent_append_same_record_dedups`):
   - Spawn 10 workers all attempting to append the SAME `(task_id, date, state)` tuple.
   - After completion: file MUST contain exactly 1 line.

**Files**:
- `tests/common/test_state_log_concurrent.py` (new, ~140 lines)

**Validation**:
- [ ] `pytest tests/common/test_state_log_concurrent.py -v` — all tests pass.
- [ ] Test runtime < 10 seconds (concurrent test should be fast).

**Note**: If this test ever fails flakily, that IS the NFR-003 failure surfacing — DO NOT mark as flaky and skip. The library has a real bug.

---

### T011 — `tests/common/test_state_log_cli.py`

**Purpose**: Cover the CLI surface (`python3 -m scripts.common.state_log ...`) via `subprocess.run`. Verify exit codes 0/1/2/3 and stdout/stderr contents per `contracts/cli.md`.

**Steps**:

1. **Fixtures**:
   ```python
   @pytest.fixture
   def isolated_state_dir(tmp_path, monkeypatch):
       d = tmp_path / "state"
       monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
       return d
   ```
   For subprocess tests, monkey-patching `STATE_DIR` doesn't reach the child process. Approach: **add an env-var override** in `state_log.py` (`STATE_DIR = Path(os.environ.get("FELIX_STATE_LOG_DIR", "/data/services/openclaw/state"))`) so subprocess tests can set the env var.
   - **Coordination back to WP01**: this env-var override is a small addition to T003. Document this as a follow-up note when implementing WP02; if WP01 didn't include it, file a small patch.

2. **CLI append happy path** (`test_cli_append_writes_record`):
   ```python
   result = subprocess.run(
       ["python3", "-m", "scripts.common.state_log", "append", "--domain", "habits"],
       input=json.dumps(good_habits_record),
       capture_output=True, text=True,
       env={"FELIX_STATE_LOG_DIR": str(isolated_state_dir), **os.environ},
   )
   assert result.returncode == 0
   assert result.stdout == ""
   ```
   Then assert the file contains the record.

3. **CLI append validation failure** (`test_cli_append_validation_failure_exits_1`):
   - Pipe a record missing `task_id`.
   - Assert returncode == 1, stderr contains "task_id".

4. **CLI append malformed JSON on stdin** (`test_cli_append_bad_json_exits_3`):
   - Pipe `not valid json`.
   - Assert returncode == 3, stderr mentions JSON.

5. **CLI append empty stdin** (`test_cli_append_empty_stdin_exits_3`):
   - Pipe empty string.
   - Assert returncode == 3.

6. **CLI read happy path** (`test_cli_read_returns_records`):
   - Pre-populate the file with 2 records (using the library directly).
   - Run `python3 -m scripts.common.state_log read --domain habits`.
   - Assert returncode == 0, stdout has 2 newline-separated JSON lines.

7. **CLI read with filters** (`test_cli_read_with_task_id_filter`):
   - Pre-populate 3 records (task_ids 14, 15, 17).
   - Run with `--task-id 15`.
   - Assert stdout has 1 record, the 15-record.

8. **CLI read unknown domain** (`test_cli_read_unknown_domain_exits_3`):
   - Run `--domain bogus`.
   - Assert returncode == 3 (argparse choice validation).

9. **CLI --help** (`test_cli_help_exits_0`):
   - Each of `--help`, `append --help`, `read --help` exits 0 with non-empty stdout.

**Files**:
- `tests/common/test_state_log_cli.py` (new, ~180 lines)

**Validation**:
- [ ] `pytest tests/common/test_state_log_cli.py -v` — all tests pass.

---

## Coverage target (NFR-005)

After all subtasks complete, run:

```bash
coverage run -m pytest tests/common/
coverage report --include='scripts/common/*'
```

Target: line + branch coverage ≥ 90% on `scripts/common/state_log.py` and `scripts/common/state_log_schema.py`.

If coverage falls short:
- Add a dedicated coverage-gap test, OR
- Document the uncovered code path with a `# pragma: no cover` comment IF it's a defensive branch that cannot be reached in practice (e.g., a `pass` after an unreachable `raise`).

## Definition of Done

- [ ] All 5 subtasks T007-T011 complete and individually validated.
- [ ] `pytest tests/common/ -v` passes with all tests green.
- [ ] `coverage run -m pytest tests/common/ && coverage report --include='scripts/common/*'` shows ≥ 90% line + branch coverage.
- [ ] The concurrent test runs deterministically across 5 consecutive invocations (no flake).
- [ ] No production state at `/data/services/openclaw/state/` is touched during test runs (verified by spot-checking on dev machine after `pytest tests/common/`).
- [ ] All files committed by the spec-kitty workflow; no uncommitted artifacts.

## Risks & mitigations

- **Tempdir leakage**: Use `tmp_path` everywhere. Never reference the production state dir in tests except to assert it's NOT touched.
- **macOS vs Linux fork/spawn**: Force `spawn` in T010 module init for portability.
- **Coverage misses on CLI defensive paths**: Some argparse error paths exit before our code runs. Acceptable; mark with `# pragma: no cover` if truly unreachable.
- **Test runtime budget**: Concurrent test should complete < 10s. If slow, investigate — should NOT be slow.
- **`FELIX_STATE_LOG_DIR` env var coordination**: This env override needs to exist in WP01's `state_log.py`. If it's missing, the CLI tests can't isolate. Document this as a small patch back to WP01 or include in your implementation handover note.

## Reviewer guidance

- Confirm every test uses `tmp_path` / temp dirs — `grep '/data/services/openclaw/state' tests/common/` should return only assertions about NON-touching that path.
- Verify the concurrent test actually uses `multiprocessing.Pool` (not threads) — threads don't exercise the cross-process fcntl lock.
- Spot-check the parametrized validation tests — each REQUIRED_FIELDS entry should have its own missing-field test case.
- Run the coverage measurement yourself; confirm ≥ 90% line + branch.
- Run the concurrent test multiple times — if it ever fails, that's an NFR-003 bug, not a flaky test.

## Implementation command

```bash
spec-kitty agent action implement WP02 --agent <agent-name>
```

Note: WP02 depends on WP01. Ensure WP01 is in the `approved` or `done` lane before claiming WP02 — `spec-kitty next` enforces this.

## Activity Log

- 2026-05-19T16:15:21Z – claude:opus:python-implementer:implementer – shell_pid=27847 – Started implementation via action command
