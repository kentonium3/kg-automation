---
work_package_id: WP01
title: 'Foundation: state I/O + HTTP wrapper'
dependencies: []
requirement_refs:
- FR-003
- FR-008
- FR-009
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-vikunja-sync-reconciliation-driver-01KTA1J3
base_commit: 094ac32f15b5022eb9c005574ac13c8dcb93866b
created_at: '2026-06-04T20:08:39.170458+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: "76162"
agent: "claude"
history:
- at: '2026-06-04T19:53:57Z'
  by: spec-kitty.tasks
  note: Created WP01 from plan.md + data-model.md + contracts/state-directory.md
authoritative_surface: scripts/sync/
execution_mode: code_change
owned_files:
- scripts/sync/__init__.py
- scripts/sync/state.py
- scripts/sync/http.py
- tests/sync/__init__.py
- tests/sync/test_state.py
- tests/sync/test_http.py
tags: []
---

# WP01 — Foundation: state I/O + HTTP wrapper

## Objective

Lay down the storage and HTTP primitives every downstream module in this mission imports. Two pure-Python modules — `state.py` for atomic JSON read/write of the driver's persistent state, and `http.py` for the `urllib.request`-based Vikunja HTTP wrapper — plus their unit tests. No business logic; no Vikunja-specific data shapes beyond what's needed to validate I/O contracts.

After this WP, downstream WPs can:
- Import `from scripts.sync.state import atomic_write_json, FreshnessPointer, TaskCacheRecord, ...` and read/write the on-disk JSON files defined in `contracts/state-directory.md`.
- Import `from scripts.sync.http import get_json, http_post_returning_json` and make timeout-bounded, error-typed HTTP calls.

## Context

This mission introduces a new top-level package `scripts/sync/` for the Felix-Vikunja reconciliation driver. The driver is a one-shot Python script invoked by a systemd user timer at 5-minute cadence (operator decision Q1: operational reliability priority). The driver's on-disk state lives under `/data/services/openclaw/state/sync/` per `contracts/state-directory.md`.

This WP is the foundation layer. WP02 (fetch + diff), WP03 (classify + guards), WP04 (emit + send), and WP05 (cycle + driver) all depend on the modules built here. The structure mirrors the established precedent at `scripts/habits/` (record_completion.py / sweeper.py) — read those for the atomic-write pattern and the urllib wrapper conventions.

**Discovery decisions inherited from planning**:
- Standard library only (no third-party deps)
- One-shot timer-fired script (not daemon)
- Mock-based unit tests (no live integration tests per memory `feedback_no_live_integration_tests`)
- Atomic-replace state writes (write `.tmp` → fsync → `os.replace`)

**Branch Strategy**: planning_base_branch = `main`; merge_target_branch = `main`. Each work package executes in its own worktree under `.worktrees/<slug>-<mid8>-lane-X/` (lane allocated by `spec-kitty agent mission finalize-tasks`). Implementer commits are made inside that worktree, never in the main repo checkout.

## Implementation command

```bash
spec-kitty agent action implement WP01 --agent <name>
```

No dependencies. WP01 may start as soon as the mission is ready for implementation.

---

## Subtask T001 — `scripts/sync/__init__.py` package marker

**Purpose**: Make `scripts.sync` a proper Python package so downstream modules can import via `from scripts.sync.* import ...`.

**Steps**:
1. Create the file `scripts/sync/__init__.py` with a module docstring describing the package:

   ```python
   """Felix-Vikunja reconciliation driver.

   See kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/
   for the canonical specification, plan, and contracts.
   """
   ```

That's the entire file. No code, no exports.

**Files**: `scripts/sync/__init__.py` (~5 lines).

**Validation**: `python3 -c "import scripts.sync"` from the repo root must succeed without error.

---

## Subtask T002 — `scripts/sync/state.py`: atomic JSON I/O + state schemas

**Purpose**: Provide the canonical reader/writer functions for every persistent state file the driver maintains, plus the atomic-write helper used by all of them.

**Steps**:

1. **Atomic write helper**: implement `atomic_write_json(path: Path, data: dict) -> None`. Mirror the pattern at `scripts/habits/sweeper.py` (search for `_atomic_write_json` for the exact reference). The implementation must:
   - Write to `path.with_suffix(path.suffix + ".tmp")` first
   - Call `f.flush()` then `os.fsync(f.fileno())` before close
   - Call `os.replace(tmp_path, path)` to atomically swap
   - Use `json.dump(data, f, sort_keys=True, indent=2)` for canonical formatting

2. **Append-only writer**: implement `append_jsonl(path: Path, record: dict) -> None`. Each call writes `json.dumps(record, sort_keys=True) + "\n"` followed by `flush()`. No atomic-replace semantics needed; POSIX guarantees per-line atomicity for short writes.

3. **State entity readers/writers**: implement one read + one write function per entity from `data-model.md`:
   - `read_freshness(state_dir: Path) → FreshnessPointer` / `write_freshness(state_dir: Path, fp: FreshnessPointer)`
   - `read_task_cache(state_dir: Path) → TaskCacheRecord` / `write_task_cache(state_dir: Path, tc: TaskCacheRecord)`
   - `read_project_cache(state_dir: Path) → ProjectCacheRecord` / `write_project_cache(state_dir: Path, pc: ProjectCacheRecord)`
   - `read_guard_state(state_dir: Path) → GuardState` / `write_guard_state(state_dir: Path, gs: GuardState)`
   - `write_per_tick_health(state_dir: Path, record: PerTickHealthRecord)` (no read; the driver writes-only)
   - `append_per_tick_error(state_dir: Path, record: PerTickErrorRecord)`

4. **Schema definitions**: use `dataclasses.dataclass(frozen=True)` for each entity. Field set per `contracts/state-directory.md` and `data-model.md`. Include a `schema_version: int` field on every entity. Validate the schema_version on read; raise `OSError` with a clear message on mismatch.

5. **Missing-file semantics**: each `read_*` function must handle the file-missing case explicitly:
   - `read_freshness`: missing file is an error (driver requires bootstrap first). Raise `OSError("freshness.json not found — run `python3 -m scripts.sync.driver --bootstrap` first")`.
   - `read_task_cache`, `read_project_cache`, `read_guard_state`: missing file returns the empty-state default for that entity.

6. **Path constants**: export `STATE_DIR_DEFAULT = Path("/data/services/openclaw/state/sync")` and `SECRETS_DIR_DEFAULT = Path("/data/services/openclaw/secrets")` as module-level constants. The driver's CLI accepts these as `--state-dir` and `--secrets-dir` overrides.

**Files**:
- `scripts/sync/state.py` (~250 lines)

**Reference precedent**: `scripts/habits/sweeper.py` — search for `_atomic_write_json`. Same pattern, generalized.

**Files this WP must NOT touch**: `scripts/common/state_log.py` (used by other modules), `scripts/habits/sweeper.py`, anything outside `scripts/sync/`.

**Validation**:
- [ ] All 5 read functions handle missing file per their documented semantics
- [ ] `atomic_write_json` does not leave a `.tmp` file behind on success or on a crash mid-write
- [ ] `schema_version` field is validated on every read; mismatch raises `OSError`
- [ ] Module imports cleanly with no side effects (no I/O at import time)

---

## Subtask T003 — `scripts/sync/http.py`: urllib wrapper [P]

**Purpose**: Provide a single typed entry point for all Vikunja HTTP calls in this mission. Wraps `urllib.request` to add a default timeout, structured error reporting, and JSON parsing.

**Steps**:

1. Implement `_http_request(method: str, url: str, token: str, body: dict | None = None, timeout: int = 10) -> tuple[int, Any]`. Mirror exactly the implementation at `scripts/habits/record_completion.py:_http_request` (lines 98-156 — read it first for the exact pattern). Key semantics:
   - Headers: `Accept: application/json`, `Authorization: Bearer {token}`, plus `Content-Type: application/json` if body is set.
   - Body: `json.dumps(body).encode("utf-8")` if non-None.
   - Raises `OSError` on: network failure (URLError), non-2xx HTTP status, or HTTPError (with error body included in the message for triage).
   - Returns `(status, parsed_json_or_none)` on success.

2. Export a convenience wrapper `def get_json(url: str, token: str, timeout: int = 10) → Any` that returns the parsed JSON or raises OSError. Same wrapper pattern for `post_json`.

3. Export `HTTP_TIMEOUT_SECONDS = 10` as a module-level constant. The driver's cycle pipeline can override via parameter but the default lives here.

**Files**:
- `scripts/sync/http.py` (~100 lines)

**Reference precedent**: `scripts/habits/record_completion.py:_http_request` — copy the structure verbatim and adapt the export surface.

**Validation**:
- [ ] HTTP 200 with JSON body returns `(200, parsed_dict)`
- [ ] HTTP 404 raises OSError with the 404 body included in the message
- [ ] Network timeout raises OSError with `timeout` in the message
- [ ] Non-JSON body returns `(status, None)` — does NOT raise

---

## Subtask T004 — `tests/sync/test_state.py`: state I/O tests [P]

**Purpose**: Cover atomic-write semantics, schema validation, missing-file handling, and roundtrip correctness for every entity reader/writer.

**Steps**:

1. Create `tests/sync/__init__.py` (empty package marker).

2. Create `tests/sync/test_state.py`. Test classes (one per concern):

   - `TestAtomicWriteJson`:
     - `test_roundtrip`: write a dict, read it back, equal.
     - `test_no_tmp_file_left_behind`: after `atomic_write_json`, `path.with_suffix(".tmp")` does NOT exist.
     - `test_overwrite`: write twice with different content; final read shows the second write.

   - `TestEntityReaders`:
     - One test class per entity (Freshness, TaskCache, ProjectCache, GuardState).
     - For each: write an entity → read it back → equal.
     - For each: missing-file behavior matches docstring (raises OSError for freshness, returns empty default for the others).

   - `TestSchemaVersionValidation`:
     - Write a state file with `"schema_version": 999` directly → read function raises OSError with version mismatch in the message.

3. Use `tmp_path` fixture (pytest built-in) for all I/O. Never touch `/data/services/openclaw/state/`.

4. Match the test style of `tests/habits/test_record_completion.py` — class-based grouping, descriptive test names, terse assertions.

**Files**:
- `tests/sync/__init__.py` (~3 lines)
- `tests/sync/test_state.py` (~280 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_state.py -q` passes
- [ ] Every public function in `scripts/sync/state.py` has at least one test exercising it
- [ ] Schema-version mismatch tests cover both reader directions (too-old, too-new)

---

## Subtask T005 — `tests/sync/test_http.py`: HTTP wrapper tests [P]

**Purpose**: Cover the happy path and every error path of the HTTP wrapper using `unittest.mock` patches of `urllib.request.urlopen`.

**Steps**:

1. Mirror the mock pattern at `tests/habits/test_record_completion.py` (see `_resp` helper and `mock_urlopen` fixture at the top of that file). Build a `_resp(payload, *, status=200)` helper and `_http_error(code, body)` helper in `tests/sync/test_http.py`.

2. Test cases:

   - `test_get_json_happy_path`: urlopen returns 200 + JSON body → wrapper returns parsed dict.
   - `test_get_json_with_bearer_header`: verify the request's Authorization header matches `Bearer <token>`.
   - `test_get_json_non_200_raises`: urlopen returns 500 → OSError raised, message includes status code and body.
   - `test_get_json_http_error_raises`: HTTPError exception → OSError raised, message includes the URL and error body.
   - `test_get_json_url_error_raises`: URLError (network failure) → OSError raised, message includes "network failure".
   - `test_get_json_timeout_raises`: simulated timeout (raise URLError with timeout reason) → OSError raised, message mentions timeout.
   - `test_get_json_non_json_body_returns_none`: HTTP 200 with body `<html>...</html>` → returns `(200, None)`, does NOT raise.
   - `test_post_json_includes_content_type_header`: body passed to post → Content-Type: application/json header sent.

3. Use pytest fixture `mock_urlopen` patching `urllib.request.urlopen`. No conftest changes — keep the fixture local to this file.

**Files**:
- `tests/sync/test_http.py` (~180 lines)

**Validation**:
- [ ] `python3 -m pytest tests/sync/test_http.py -q` passes
- [ ] Mock-only — no real network calls

---

## Test strategy

This WP's tests are entirely mock-based unit tests. No live integration tests per memory `feedback_no_live_integration_tests` (operational SC verification happens manually on office2 post-merge). Run the full test suite via:

```bash
python3 -m pytest tests/sync/ -q
```

Both new test files combined target ≥80% line coverage of `scripts/sync/state.py` and `scripts/sync/http.py`.

---

## Definition of Done

- [ ] All 5 subtasks complete; all listed files committed in the WP01 worktree
- [ ] `python3 -c "import scripts.sync"` returns 0 from repo root
- [ ] `python3 -m pytest tests/sync/test_state.py tests/sync/test_http.py -q` passes
- [ ] No edits to files outside the WP's `owned_files` list
- [ ] No lint errors from existing project linters (if any are wired)
- [ ] Schema version validation tests cover both the success and mismatch paths
- [ ] HTTP wrapper's error message format is grep-able for "step N (Vikunja ...)" patterns matching the existing `scripts/habits/record_completion.py:268-270` convention (downstream WPs will follow that pattern for cycle phase prefixing)

---

## Risks and mitigations

- **Risk: pickle of dataclasses across Python versions.** Mitigation: never pickle state. All persistent storage is JSON. Dataclasses are in-memory only.
- **Risk: race between atomic_write_json and a SIGTERM at the rename boundary.** Mitigation: `os.replace` is atomic at the kernel level on Linux ext4; the worst case is the `.tmp` file remains and the original is untouched. Documented in `contracts/state-directory.md`.
- **Risk: HTTP wrapper masks underlying Vikunja errors.** Mitigation: error messages always include the URL, the status code, and the response body (truncated to 200 chars for triage). Tests assert these are present.

---

## Reviewer guidance

When reviewing this WP, verify:
1. **Atomic-write contract**: read `scripts/habits/sweeper.py` for the canonical pattern, then read the new `scripts/sync/state.py` `atomic_write_json` — they should be structurally identical (only the imports / module-scope differ).
2. **HTTP wrapper parity**: read `scripts/habits/record_completion.py:_http_request` and the new `scripts/sync/http.py:_http_request` — same structure, same error semantics.
3. **No I/O at import time**: import `scripts.sync.state` and `scripts.sync.http` should produce no side effects (no logging, no environment reads, no file creation).
4. **Schema version present on every entity**: grep `scripts/sync/state.py` for `schema_version` — every dataclass should have one.
5. **Test coverage** is comprehensive against the public surface — no public function in `state.py` or `http.py` lacks a test.

Reject if any owned-file boundary is violated, any test uses live I/O, or any state file is written outside the atomic-replace pattern.

---

## References

- Mission spec: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md`
- Mission plan: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/plan.md`
- Data model: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/data-model.md`
- State layout contract: `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/state-directory.md`
- Atomic-write precedent: `scripts/habits/sweeper.py:_atomic_write_json`
- HTTP wrapper precedent: `scripts/habits/record_completion.py:_http_request` (lines 98-156)
- Test pattern precedent: `tests/habits/test_record_completion.py`

## Activity Log

- 2026-06-04T20:08:41Z – claude – shell_pid=76162 – Assigned agent via action command
