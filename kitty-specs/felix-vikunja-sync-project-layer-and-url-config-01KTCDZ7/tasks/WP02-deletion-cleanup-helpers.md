---
work_package_id: WP02
title: Deletion-Cleanup Helpers
dependencies: []
requirement_refs:
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7
base_commit: 166c9c647fd5ae2d6a58a51555c9b78e05999df6
created_at: '2026-06-05T19:12:50.168387+00:00'
subtasks:
- T004
- T005
- T006
shell_pid: "78402"
history: []
authoritative_surface: scripts/sync/cleanup.py
execution_mode: code_change
owned_files:
- scripts/sync/cleanup.py
- tests/sync/test_cleanup.py
tags: []
agent: "claude:sonnet:implementer:implementer"
---

# WP02 — Deletion-Cleanup Helpers

## Objective

Add a new module `scripts/sync/cleanup.py` providing two helper functions used by WP04's Phase 5b deletion-cleanup orchestration:

- `prune_schedule_yaml(task_id: int, path: Path) -> bool`
- `append_task_deleted_event(task_id: int, title: str, detected_at_utc: str, path: Path) -> None`

These are pure side-effect helpers — no orchestration logic, no cycle integration. WP04 imports both and wires them into the cycle.

## Context

Per spec FR-003 and `contracts/cycle-pipeline.md` § Phase 5b, the cycle's deletion-cleanup performs three actions per confirmed-deleted task:

1. **Append `task_deleted` event** to `scripts/habits/state/habits-history.jsonl` (single-line JSON append; atomic).
2. **Prune the entry** for that `task_id` from `scripts/habits/migrations/phase3-schedule.yaml` (YAML round-trip preserving comments + ordering).
3. **Remove the task** from the sync cache (handled in WP04's Phase 6 atomic write — not this WP).

WP02 provides the first two as standalone helpers. WP04 imports and orchestrates them.

Per research R-006, the YAML library is `ruamel.yaml` if available (preserves comments + ordering), with a PyYAML fallback for test environments.

## Implementation guidance

### Subtask T004: Create `scripts/sync/cleanup.py`

**Purpose**: provide both helper functions.

**Steps**:

1. Create the module at `scripts/sync/cleanup.py`. Top-level docstring references mission #520 and FR-003.

2. Define `append_task_deleted_event`:

   ```python
   import json
   from pathlib import Path

   _SCHEMA_VERSION = 1


   def append_task_deleted_event(
       task_id: int,
       title: str,
       detected_at_utc: str,
       path: Path,
   ) -> None:
       """Append a task_deleted event to a JSONL audit log.

       Atomic at small write sizes via stdlib's append-mode open. Idempotent
       in the sense that re-running produces a duplicate event (acceptable;
       the audit trail is append-only).

       Args:
           task_id: positive integer task identifier (Vikunja task.id)
           title: last-known task title before deletion (from cache)
           detected_at_utc: ISO-8601 UTC timestamp ("YYYY-MM-DDTHH:MM:SSZ")
           path: target JSONL file (e.g., scripts/habits/state/habits-history.jsonl)

       Raises:
           OSError: on filesystem failure. Caller decides whether to abort
               the cycle or skip this task_id and continue.
       """
       if not isinstance(task_id, int) or task_id <= 0:
           raise ValueError(f"task_id must be a positive integer; got {task_id!r}")
       event = {
           "event_type": "task_deleted",
           "task_id": task_id,
           "title": title,
           "detected_at_utc": detected_at_utc,
           "schema_version": _SCHEMA_VERSION,
       }
       line = json.dumps(event, separators=(",", ":")) + "\n"
       path.parent.mkdir(parents=True, exist_ok=True)
       with open(path, "a", encoding="utf-8") as f:
           f.write(line)
   ```

3. Define `prune_schedule_yaml`:

   ```python
   from pathlib import Path
   from typing import Any

   try:
       from ruamel.yaml import YAML

       def _round_trip_yaml() -> Any:
           return YAML(typ="rt")
       _USING_RUAMEL = True
   except ImportError:
       import yaml as _pyyaml

       def _round_trip_yaml() -> Any:
           return _pyyaml
       _USING_RUAMEL = False


   def prune_schedule_yaml(task_id: int, path: Path) -> bool:
       """Remove the entry for ``task_id`` from a habits schedule YAML.

       Round-trips the YAML preserving comments + ordering when ruamel.yaml
       is available; falls back to PyYAML (comments lost) for test
       environments without ruamel.

       Args:
           task_id: positive integer; the entry with this id is pruned
           path: path to phase3-schedule.yaml

       Returns:
           True if an entry was removed; False if no matching entry was found
               (idempotent — repeat calls return False).

       Raises:
           OSError: on filesystem failure
           ValueError: on a malformed YAML body that isn't a list of dicts
       """
       if not path.exists():
           return False
       if _USING_RUAMEL:
           yaml = _round_trip_yaml()
           with open(path, "r", encoding="utf-8") as f:
               data = yaml.load(f)
       else:
           import yaml as _pyyaml  # type: ignore[no-redef]
           with open(path, "r", encoding="utf-8") as f:
               data = _pyyaml.safe_load(f)
       if not isinstance(data, list):
           raise ValueError(
               f"Expected schedule.yaml at {path} to be a list of entries; "
               f"got {type(data).__name__}"
           )
       new_data = [entry for entry in data if entry.get("task_id") != task_id]
       if len(new_data) == len(data):
           return False
       if _USING_RUAMEL:
           with open(path, "w", encoding="utf-8") as f:
               yaml.dump(new_data, f)
       else:
           with open(path, "w", encoding="utf-8") as f:
               _pyyaml.safe_dump(new_data, f, default_flow_style=False)
       return True
   ```

4. The exact `task_id` lookup logic (e.g., is it `entry["task_id"]` or `entry["attributes"]["task_id"]`?) MUST be verified against the actual `phase3-schedule.yaml` structure on the codebase. Read a sample of the existing file first, document the assumption in the module docstring, then implement accordingly. **Read the file before writing code.**

**Files**: `scripts/sync/cleanup.py` (new, ~110 lines)

**Validation**:
- [ ] Module imports cleanly
- [ ] Both functions have docstrings with full signature documentation
- [ ] YAML structure assumption is documented in the module docstring (referencing the actual `phase3-schedule.yaml` shape after inspection)
- [ ] `append_task_deleted_event` validates `task_id` is a positive integer

### Subtask T005: Tests in `tests/sync/test_cleanup.py`

**Purpose**: cover happy paths + idempotency for both helpers.

**Steps**:

Create `tests/sync/test_cleanup.py` with pytest. Use `tmp_path` for file paths.

Scenarios:

1. **append_task_deleted_event — happy path**: append one event to a fresh `tmp_path / "test.jsonl"`; read back; assert JSON shape (event_type, task_id, title, detected_at_utc, schema_version=1).

2. **append_task_deleted_event — multiple events**: append 3 events; verify the file has 3 lines, each parseable as JSON, in order.

3. **append_task_deleted_event — creates parent dirs**: target path is `tmp_path / "nested/dir/test.jsonl"`; parents don't exist; expect they're created.

4. **append_task_deleted_event — invalid task_id**: `task_id=-1` or `task_id=0` or `task_id="not-an-int"`; expect `ValueError`.

5. **prune_schedule_yaml — happy path**: write `tmp_path / "schedule.yaml"` with 3 entries (task_ids 1, 2, 3); call `prune_schedule_yaml(2, path)`; assert returns `True`; assert file now has 2 entries (1, 3).

6. **prune_schedule_yaml — idempotent**: same setup; call `prune_schedule_yaml(2, path)` twice in a row; first returns True, second returns False.

7. **prune_schedule_yaml — missing entry**: schedule has entries (1, 3); call `prune_schedule_yaml(2, path)`; expect returns False, file unchanged.

8. **prune_schedule_yaml — missing file**: target path does not exist; call `prune_schedule_yaml(1, path)`; expect returns False (no exception).

9. **prune_schedule_yaml — malformed YAML**: write a YAML that's a dict instead of a list; expect `ValueError`.

10. **prune_schedule_yaml — preserves comments** (only if ruamel.yaml is available): write YAML with leading comment + entries; prune one; verify the comment is still present in the output. If running without ruamel.yaml, mark this test as `pytest.mark.skipif`.

**Files**: `tests/sync/test_cleanup.py` (new, ~150 lines)

**Validation**:
- [ ] `pytest tests/sync/test_cleanup.py -v` passes all 10 scenarios (case 10 may skip if ruamel unavailable)
- [ ] No live HTTP, no live filesystem outside `tmp_path`
- [ ] No live network calls

### Subtask T006: Document atomicity + idempotency + event schema

**Purpose**: capture the cross-cutting contract guarantees in the module docstring so WP04's reviewer can verify orchestration assumptions.

**Steps**:

Add a module-level docstring to `scripts/sync/cleanup.py` covering:

1. **Atomicity guarantees**:
   - `append_task_deleted_event`: append-mode open is atomic for small writes (< PIPE_BUF, ~4KB on Linux). Single line < 200 bytes. Safe.
   - `prune_schedule_yaml`: read-modify-write is NOT atomic. Failure between read and write leaves the file in its old state (acceptable — idempotent retry recovers).

2. **Idempotency guarantees**:
   - `append_task_deleted_event` is NOT idempotent (re-running produces a duplicate event in the audit log; this is acceptable — the audit log is append-only and shows the cleanup was attempted twice).
   - `prune_schedule_yaml` IS idempotent (returns False if the task_id is already absent).

3. **Event schema** (mirrored from `data-model.md` § TaskDeletedEvent):

   ```jsonc
   {
     "event_type": "task_deleted",            // discriminator
     "task_id": 42,
     "title": "Wake at 5:00 AM",              // last-known title
     "detected_at_utc": "2026-06-05T20:00:00Z",
     "schema_version": 1
   }
   ```

4. **YAML library trade-off**: ruamel.yaml preserves comments and ordering; PyYAML fallback drops both. Production assumes ruamel; tests skip ruamel-specific assertions when only PyYAML is present.

5. **Verified assumption about phase3-schedule.yaml shape**: document what the file looks like (list of dicts; each dict has a `task_id` key) based on the verification done in T004.

**Files**: amend `scripts/sync/cleanup.py` (module docstring only)

**Validation**:
- [ ] Module docstring is the first statement after the future-import in the file
- [ ] All 4 sections are present and clear
- [ ] Schema example matches the JSON written by `append_task_deleted_event`

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per computed lane from `lanes.json` (no deps; can run in parallel with WP01 and WP03).

## Test Strategy

Unit tests only. The orchestration test (Phase 5b end-to-end with the helpers) lives in WP04's `test_cycle_*.py` updates, where the cleanup helpers are called by the cycle.

## Definition of Done

- [ ] `scripts/sync/cleanup.py` exists with both helper functions, module docstring covering atomicity/idempotency/schema/YAML trade-off
- [ ] `tests/sync/test_cleanup.py` exists with all 10 scenarios; passes `pytest`
- [ ] phase3-schedule.yaml structure verified by reading the actual file before authoring `prune_schedule_yaml`
- [ ] No changes to files outside `owned_files`
- [ ] No live HTTP, no live filesystem outside `tmp_path`

## Risks

- **YAML library availability**: ruamel.yaml is expected in production but may not be in the test environment. The fallback logic must work cleanly, and tests must skip ruamel-specific assertions appropriately.
- **phase3-schedule.yaml structure assumption**: if the file's actual shape is not "list of dicts each with a `task_id` key" (e.g., it's a dict-of-dicts keyed by task_id), the code needs to change. ALWAYS read the actual file before authoring.
- **Concurrent writers**: not a concern — only the driver writes to `habits-history.jsonl` from this path. Tests don't need to cover concurrency.

## Reviewer Guidance

The reviewer should validate:

1. **`phase3-schedule.yaml` shape is actually as documented in the module docstring** (read the file to verify the implementer didn't guess).
2. **Append atomicity**: the `open(path, "a")` pattern is correct (not `"w"`). Tests assert append behavior.
3. **ruamel.yaml fallback**: the `try/except ImportError` is at module-import time, not inside the function (correct for one-time check).
4. **Idempotency contract is correct**: prune_schedule_yaml returns False on no-op; append_task_deleted_event is NOT idempotent (duplicate appends are accepted by design).
5. **Tests use `tmp_path`**: no writes to production paths.
6. **No third-party imports** other than ruamel.yaml (with PyYAML fallback) — `urllib`, `json`, `pathlib`, `os` only.

## Implementation command

```bash
spec-kitty agent action implement WP02 --mission felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7 --agent <tool>:<model>:<profile>:<role>
```

## Next steps after WP02 approval

- WP04 can use `prune_schedule_yaml` and `append_task_deleted_event` directly (once WP03 also approves, WP04 can start).
- WP01 and WP03 are independent — they can run in parallel with WP02.

## Activity Log

- 2026-06-05T19:12:52Z – claude:sonnet:implementer:implementer – shell_pid=78402 – Assigned agent via action command
