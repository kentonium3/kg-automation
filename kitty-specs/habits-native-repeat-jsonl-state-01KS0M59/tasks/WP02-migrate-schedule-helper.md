---
work_package_id: WP02
title: 'Migration helper: load, validate, snapshot, apply, rollback'
dependencies:
- WP01
requirement_refs:
- C-002
- C-003
- C-004
- C-007
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-012
- FR-014
- NFR-001
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T004
- T005
- T006
- T007
- T008
history:
- at: '2026-05-19T17:30:00Z'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/habits/
execution_mode: code_change
mission_id: 01KS0M59313RF0WVJZTXYDJC6C
mission_slug: habits-native-repeat-jsonl-state-01KS0M59
owned_files:
- scripts/habits/migrate_schedule.py
- tests/habits/test_migrate_schedule.py
- kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml
tags: []
---

# WP02 — Migration helper: load, validate, snapshot, apply, rollback

## Objective

Build the config-driven migration helper that applies Phase 3's production-state changes: 7 daily PATCHes, 1 retire (workout task), 3 creates (Mon/Wed/Fri strength training). Includes a rollback substrate written before any mutation, and a `--rollback` flag to reverse. Plus author the mission's `habits-schedule.yaml` itself.

This is the **Tier 2 production-state mutation tool**. Pre-flight protocol (Restic snapshot + service health checks) is operator-driven; the helper enforces an env-var confirmation gate.

## Context

- **Mission spec**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/spec.md` — esp. FR-001..FR-005, FR-012, FR-014, NFR-001, NFR-004, C-002, C-003, C-004, C-007
- **Plan**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/plan.md`
- **Research**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/research.md` — esp. D1 (HTTP pattern), D3 (transaction model), D6 (idempotency), D8 (validation), D9 (due-date computation), D10 (gotchas)
- **Data model**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/data-model.md` — schedule.yaml + snapshot schemas
- **API contract**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/api.md` — `load_schedule`, `capture_snapshot`, `apply_schedule`, `rollback` signatures
- **CLI contract**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/cli.md` — `migrate_schedule` CLI surface
- **Config contract**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/config.md` — schedule.yaml schema in detail
- **Existing pattern reference**: `scripts/vikunja/provision_felix_bot.py` — canonical urllib + token-file pattern
- **Test fixtures**: from WP01's `tests/habits/conftest.py`
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`. WP02 starts only after WP01 is approved.

## Subtasks

### T004 — Implement `migrate_schedule.py` — `load_schedule()` + YAML schema validation

**Purpose**: Read and validate the habits-schedule.yaml file. Refuse to proceed if the schema is bad.

**Steps**:

1. **Module setup**:
   ```python
   #!/usr/bin/env python3
   """ADR-0002 Phase 3 habits schedule migration helper.

   Reads habits-schedule.yaml describing per-task schedule changes; captures
   a BEFORE-state snapshot to /data/services/openclaw/state/habits-pre-phase3-snapshot.json;
   then applies the changes via Vikunja API calls authenticated as felix-bot.

   Tier 2 protocol: operator must set FELIX_TIER2_PREFLIGHT_OK=yes (or use
   --dry-run) before any destructive HTTP call is issued.

   See kitty-specs/<mission>/spec.md and contracts/cli.md for the full
   contract.
   """
   from __future__ import annotations
   import argparse, hashlib, json, os, sys, urllib.request, urllib.error
   from datetime import datetime, timezone, timedelta
   from pathlib import Path
   from typing import Any, Optional

   try:
       import yaml
   except ImportError:
       print("ERROR: PyYAML required. Install via repo requirements.txt.", file=sys.stderr)
       sys.exit(2)
   ```

2. **Module constants** (per data-model.md):
   ```python
   DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"
   DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"
   DEFAULT_SNAPSHOT_PATH = "/data/services/openclaw/state/habits-pre-phase3-snapshot.json"
   PREFLIGHT_ENV_VAR = "FELIX_TIER2_PREFLIGHT_OK"
   VALID_OPS = {"patch", "retire", "create"}
   VALID_REPEAT_MODES = {0, 1, 2}
   HTTP_TIMEOUT_SECONDS = 30
   ```

3. **`load_schedule(path: Path) -> dict`**:
   - Read file via `path.read_text(encoding="utf-8")`.
   - Parse with `yaml.safe_load`. On parse error: raise `ValueError(f"YAML parse error in {path}: {e}")`.
   - Validate top-level:
     - `data["mission_id"]` is a non-empty string.
     - `data["operations"]` is a list.
   - For each operation (index i):
     - `op["op"]` in `VALID_OPS` (else `ValueError(f"Operation {i}: unknown op '{op['op']}'")`).
     - For `patch`/`retire`: `op["task_id"]` is positive int.
     - For `patch`: `op["target"]["repeat_after"]` positive int; `op["target"]["repeat_mode"]` in VALID_REPEAT_MODES.
     - For `create`: `op["schedule"]["repeat_after"]` positive int; `op["schedule"]["repeat_mode"]` valid; `op["attributes"]["title"]` non-empty after strip.
     - If `due_date` present: parses via `datetime.fromisoformat()`, has tzinfo.
   - No duplicate `task_id` in patch/retire ops.
   - Return the validated dict unchanged.

**Files (T004 contribution)**:
- `scripts/habits/migrate_schedule.py` (new, ~120 lines added in T004)

**Validation**:
- [ ] `load_schedule` raises ValueError with specific field/index on each defined invalid case (missing key, wrong type, invalid op, duplicate task_id, etc.).
- [ ] Valid YAML matching contracts/config.md passes without raising.

---

### T005 — Implement `migrate_schedule.py` — `capture_snapshot()` + `apply_schedule()`

**Purpose**: GET current state of every touched task; persist BEFORE state to disk; iterate operations applying each via HTTP.

**Steps**:

1. **`_http_request(method, url, token, body=None)` helper**:
   - Build `urllib.request.Request` with `Authorization: Bearer <token>` and `Content-Type: application/json` if body.
   - Serialize body to JSON bytes if dict.
   - Call `urlopen` with HTTP_TIMEOUT_SECONDS. Return (status, body_text).
   - On URLError/HTTPError: raise `OSError(f"{method} {url} failed: {e}")`.

2. **`_fetch_task(api_base_url, token, task_id) -> dict`**:
   - `_http_request("GET", f"{api_base_url}tasks/{task_id}", token)` → parse JSON → return relevant fields (id, title, repeat_after, repeat_mode, done, due_date, is_archived, done_at, project_id, labels).

3. **`capture_snapshot(api_base_url, token, schedule) -> dict`**:
   - Compute set of `task_id`s touched (from patch + retire ops + any explicit create task_ids).
   - For each id: call `_fetch_task` → record under `before_states`.
   - For retire ops: assert BEFORE state has `repeat_after == 0` (else raise ValueError "Cannot retire task {id} with repeat_after={X}; auto-advance would un-retire").
   - Compute SHA-256 of the schedule YAML's serialized form: `config_file_sha256`.
   - Return snapshot dict per data-model.md Entity 3 schema, with empty `applied_changes` and `created_tasks`.

4. **`_persist_snapshot(snapshot, path)` helper**:
   - Write JSON to path atomically: write to `path.with_suffix(".json.tmp")`, fsync, rename.
   - Mode 0644.

5. **`_apply_patch(api_base_url, token, op) -> dict`**:
   - PATCH `{api_base_url}tasks/{op["task_id"]}` with body `{"repeat_after": ..., "repeat_mode": ...}`.
   - Returns response (the updated task).

6. **`_apply_retire(api_base_url, token, op) -> dict`**:
   - PATCH `{api_base_url}tasks/{op["task_id"]}` with body `{"done": True}`.
   - Returns response.

7. **`_apply_create(api_base_url, token, op, *, inherit_project_id=None, inherit_labels=None) -> dict`**:
   - Resolve `project_id`: explicit from op.attributes OR inherited from most recent retire op (passed by caller).
   - Resolve `due_date`: explicit from op.attributes OR compute via `_default_due_date(op["attributes"]["title"], op["schedule"]["repeat_after"])` (research D9).
   - PUT `{api_base_url}projects/{project_id}/tasks` with body `{title, due_date, repeat_after, repeat_mode, labels}`.
   - Returns response including new task id.

8. **`_default_due_date(title, repeat_after) -> str`** (research D9):
   - If repeat_after == 604800: extract weekday from title (regex "Monday|Tuesday|...|Sunday") → next occurrence of that weekday at 08:00 UTC, today or later.
   - If repeat_after == 86400: tomorrow at 08:00 UTC.
   - Else: today + repeat_after seconds.

9. **`apply_schedule(api_base_url, token, schedule, snapshot_path, dry_run=False) -> dict`**:
   - Call `capture_snapshot` first.
   - Persist initial snapshot (with empty applied_changes).
   - If dry_run: print intended changes per op, return snapshot.
   - Else iterate operations:
     - For each op: print status line, dispatch to `_apply_patch/_apply_retire/_apply_create`.
     - On success: append to `snapshot["applied_changes"]`, persist snapshot (fsync).
     - For create ops: append created task to `snapshot["created_tasks"]`.
     - For patch ops with already-target state: log "skipped (already matches)" and append a `result: "skipped"` entry.
     - On OSError mid-batch: persist final snapshot with the partial state, re-raise so CLI exits non-zero.
   - Return final snapshot.

**Files (T005 contribution)**:
- `scripts/habits/migrate_schedule.py` (extend; T005 adds ~200 lines)

**Validation**:
- [ ] `_fetch_task` returns the documented field set.
- [ ] Snapshot persistence is atomic (rename pattern, fsync called).
- [ ] Default due-date computation correct for Mon/Wed/Fri titles (test with various run dates).

---

### T006 — Implement `migrate_schedule.py` — `rollback()` + `__main__` CLI

**Purpose**: Reverse-apply changes from the snapshot. Wire up the CLI with all flags.

**Steps**:

1. **`rollback(api_base_url, token, snapshot_path) -> dict`**:
   - Load snapshot from path. Validate `schema_version == "1"` and structural integrity.
   - Iterate `applied_changes` in REVERSE order:
     - `op == "patch"`: look up BEFORE state for this task_id; PATCH with the before values (`repeat_after`, `repeat_mode`).
     - `op == "retire"`: look up BEFORE state (which has `done=False` per pre-flight check); PATCH with `done: False`.
     - `op == "create"`: look up the task_id from `created_tasks`; DELETE `{api_base_url}tasks/{task_id}`.
   - For each successful reversal: append to snapshot's `applied_changes` with `op: "rollback_<orig_op>"`.
   - Persist snapshot after each step.
   - On OSError during rollback: persist + re-raise.
   - Return final snapshot.

2. **`main(argv=None) -> int`** (CLI):
   - argparse:
     - `--schedule PATH` (required unless `--rollback`)
     - `--snapshot-out PATH` (required unless `--rollback`, default DEFAULT_SNAPSHOT_PATH)
     - `--dry-run` (flag)
     - `--rollback` (flag)
     - `--snapshot-file PATH` (required if `--rollback`)
     - `--token-file PATH` (default DEFAULT_TOKEN_PATH)
     - `--base-url URL` (default DEFAULT_BASE_URL)
   - Read token from file. Handle FileNotFoundError → exit 3.
   - If `--rollback`:
     - Load snapshot, call `rollback`, print "SUMMARY: rollback complete; N changes reversed", exit 0.
     - On OSError → exit 1, print partial summary.
   - Else:
     - Validate Tier 2 pre-flight: if NOT `--dry-run` AND env `FELIX_TIER2_PREFLIGHT_OK != "yes"`: print message naming the env var and the Restic snapshot expectation, exit 3.
     - Call `load_schedule(args.schedule)`. Catch ValueError → exit 2.
     - Call `apply_schedule(...)`. Catch OSError mid-batch → exit 1 with partial-state summary pointing at the snapshot for rollback.
     - On success: print "SUMMARY: applied N/N operations; snapshot at <path>", exit 0.

3. **`if __name__ == "__main__": sys.exit(main())`**.

**Files (T006 contribution)**:
- `scripts/habits/migrate_schedule.py` (extend; T006 adds ~150 lines)

**Validation**:
- [ ] `python3 -m scripts.habits.migrate_schedule --help` exits 0 with reasonable help text.
- [ ] `--rollback` without `--snapshot-file` errors at argparse (exit 2).
- [ ] CLI exit codes match contracts/cli.md (0/1/2/3).

---

### T007 — Create `tests/habits/test_migrate_schedule.py`

**Purpose**: Exhaustive coverage of T004-T006 with mocked Vikunja API.

**Steps**:

1. **Fixtures** (extend conftest.py with WP02-specific ones if needed; otherwise inline):
   - `valid_schedule_yaml(tmp_path)`: writes a minimal valid YAML; returns path.
   - `mock_vikunja(monkeypatch)`: monkey-patches `urllib.request.urlopen` to a configurable mock that returns canned responses keyed by `(method, url)`.

2. **load_schedule tests**:
   - Happy path: valid YAML → returns parsed dict.
   - Missing mission_id → ValueError.
   - Wrong mission_id (mismatch with meta.json) — defer this check to a separate utility called by main (load_schedule itself doesn't read meta.json).
   - Each per-op validation failure: unknown op, missing task_id, negative repeat_after, invalid repeat_mode, missing title for create, duplicate task_id.
   - Each error message names the operation index.

3. **capture_snapshot tests**:
   - Happy path: 8 tasks GET'd, snapshot dict has 8 `before_states`.
   - Pre-flight refuse: retire op targeting a task with `repeat_after > 0` → ValueError mentioning the auto-advance risk.
   - Network failure: mocked urlopen raises HTTPError → capture_snapshot raises OSError.

4. **apply_schedule tests**:
   - Happy path: 7 PATCH + 1 retire + 3 create, all mocked successful. Snapshot's `applied_changes` has 11 entries; `created_tasks` has 3.
   - Dry-run: no urlopen calls issued (assert via mock call_count == 8 for the snapshot GETs only); snapshot has empty applied_changes.
   - Idempotency (patch already matches): mock GET returns task with `repeat_after=86400` already; the PATCH is skipped; snapshot records `result: "skipped"`.
   - Mid-batch failure: 5th PATCH raises HTTPError; OSError propagates; snapshot on disk has 4 applied_changes; created_tasks empty.

5. **rollback tests**:
   - Happy path: snapshot with 11 applied_changes; rollback reverses all (7 PATCH reverts + 1 retire revert + 3 DELETEs); snapshot annotated with rollback entries.
   - Mid-rollback failure: one DELETE fails; OSError propagates; partial annotation persisted.
   - Schema-version check: snapshot with `schema_version: "0"` → ValueError.

6. **CLI tests** (subprocess against `python3 -m scripts.habits.migrate_schedule`):
   - `--help` exits 0.
   - Missing `--schedule` exits 2.
   - Tier 2 pre-flight gate: without `FELIX_TIER2_PREFLIGHT_OK=yes` and without `--dry-run` → exit 3.
   - Dry-run happy path: exit 0; no HTTP issued (mock at module level via env or skip subprocess and call `main()` directly).
   - Rollback CLI: exit 0 with snapshot file.

**Files**:
- `tests/habits/test_migrate_schedule.py` (new, ~350 lines)

**Validation**:
- [ ] `pytest tests/habits/test_migrate_schedule.py -v` — all tests pass.
- [ ] Coverage on `scripts/habits/migrate_schedule.py` ≥ 90%.

---

### T008 — Create `habits-schedule.yaml`

**Purpose**: The mission-scoped config file with all 11 operations. Workout task ID is a TBD placeholder (operator fills via WP01's identify_workout_task.py output before invoking migrate_schedule).

**Steps**:

1. Create `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml`.

2. Content per `contracts/config.md` § Example. The 7 daily PATCHes use task IDs 14, 15, 16, 18, 19, 20, 65. The retire op uses `task_id: 17` as a placeholder with a comment `# placeholder — operator runs identify_workout_task.py and replaces this`. The 3 create ops omit `due_date` (helper computes default) and `project_id`/`labels` (helper inherits from the retired task).

3. Add a top-level comment block explaining the workout-ID-placeholder requirement and pointing at the quickstart.md walkthrough.

**Files**:
- `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml` (new, ~80 lines including comments)

**Validation**:
- [ ] `python3 -c "import yaml; yaml.safe_load(open('kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml'))"` succeeds.
- [ ] `python3 -m scripts.habits.migrate_schedule --schedule <path> --snapshot-out /tmp/test.json --dry-run` (with a mocked Vikunja or live token) accepts the schema.

---

## Branch Strategy

- **Current branch at WP start**: as resolved by `spec-kitty agent action implement WP02 --mission habits-native-repeat-jsonl-state-01KS0M59` — typically the lane-a worktree (shared with WP01 after WP01 merges).
- **Planning base / merge target**: `main`.
- **Execution worktree**: per `lanes.json`. WP02 depends on WP01 being approved.

## Definition of Done

- [ ] All 5 subtasks T004-T008 complete and individually validated.
- [ ] `python3 -m scripts.habits.migrate_schedule --help` exits 0 with the documented flags.
- [ ] `pytest tests/habits/test_migrate_schedule.py -v` passes with all tests green.
- [ ] Coverage on `scripts/habits/migrate_schedule.py` ≥ 90%.
- [ ] `habits-schedule.yaml` parses as valid YAML; passes `load_schedule()` validation.
- [ ] Tier 2 pre-flight gate enforced: invoking without `FELIX_TIER2_PREFLIGHT_OK=yes` (and without `--dry-run`) exits 3.
- [ ] No new third-party dependencies (PyYAML is pre-existing).
- [ ] All files committed; no uncommitted artifacts.

## Risks & mitigations

- **Vikunja API quirk G4** (comment-create is PUT not POST): doesn't directly apply to migrate_schedule (no comment writes), but be aware if any error-recovery path tries to write a comment, use PUT.
- **Snapshot persistence atomicity**: use `tmp + fsync + rename` pattern. If fsync is slow on the office2 disk, accept the latency for safety.
- **Default-due-date weekday parsing**: regex on title to detect "Monday"/"Wednesday"/"Friday" must be case-sensitive (or normalized) to avoid false positives on titles containing those substrings without the canonical capitalization.
- **Operator forgetting to update the workout task ID in YAML**: dry-run output will show a retire op targeting whatever ID is in the file. The operator should sanity-check via the dry-run before live apply.
- **`FELIX_TIER2_PREFLIGHT_OK` env var as the only gate**: this is an honor system. The operator who sets the env var is asserting they did the Restic check. Document this explicitly in stderr help text.

## Reviewer guidance

- Check imports: stdlib only (PyYAML is in requirements.txt — verify).
- Verify the validation order in `load_schedule` matches contracts/config.md exactly.
- Verify the BEFORE-state retire check: `repeat_after == 0` is required before any retire op.
- Verify snapshot persistence is atomic + fsync'd.
- Verify the Tier 2 env-var gate is present and stderr message is clear about what the env var means.
- Spot-check default due-date computation: for a Friday run, "Strength training — Monday" should resolve to next Monday 08:00 UTC.

## Implementation command

```bash
spec-kitty agent action implement WP02 --mission habits-native-repeat-jsonl-state-01KS0M59 --agent <agent-name>
```

Note: WP02 depends on WP01. Ensure WP01 is `approved` before claiming WP02 — `spec-kitty next` enforces this.
