---
work_package_id: WP04
title: v2 query/exclude variants + architecture documentation
dependencies:
- WP01
requirement_refs:
- C-001
- FR-010
- FR-011
- FR-013
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Lane worktree branches off main; merges back to main on approval. WP04 depends on WP01.
subtasks:
- T013
- T014
- T015
- T016
- T017
- T018
history:
- at: '2026-05-19T17:30:00Z'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/habits/
execution_mode: code_change
mission_id: 01KS0M59313RF0WVJZTXYDJC6C
mission_slug: habits-native-repeat-jsonl-state-01KS0M59
owned_files:
- scripts/habits/query_active_habits_v2.py
- scripts/habits/exclude_completed_v2.py
- tests/habits/test_query_active_habits_v2.py
- tests/habits/test_exclude_completed_v2.py
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/service-inventory.json
tags: []
---

# WP04 — v2 query/exclude variants + architecture documentation

## Objective

Build the two parallel `_v2.py` variants (`query_active_habits_v2`, `exclude_completed_v2`) that Phase 5 cutover (#308) will swap to. Plus update `data-flows.json` and `service-inventory.json` to register the new write/read paths and scripts. This WP closes Phase 3's functional surface.

## Context

- **Mission spec**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/spec.md` — esp. FR-010, FR-011, FR-013, NFR-005, C-001
- **Plan**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/plan.md`
- **API contract**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/api.md` — `query_active_today` and `exclude_completed_for_today` signatures
- **CLI contract**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/cli.md` — both v2 CLI surfaces
- **Existing siblings (do NOT modify)**: `scripts/habits/query_active_habits.py`, `scripts/habits/exclude_completed.py` — these remain live until Phase 5 cutover (C-001).
- **Phase 2 library**: `scripts/common/state_log.py` (used by exclude_completed_v2)
- **Test fixtures**: from WP01's `tests/habits/conftest.py`
- **Arch doc registry**: `docs/design/architecture/change-control.md` for the update protocol
- **Branching**: planning_base=`main`, merge_target=`main`.

## Subtasks

### T013 — Implement `scripts/habits/query_active_habits_v2.py`

**Purpose**: Parallel new variant using Vikunja's native filter `due_date <= now/d AND done = false`. Original `query_active_habits.py` is NOT touched.

**Steps**:

1. **Module setup**:
   ```python
   #!/usr/bin/env python3
   """Phase 5 cutover variant of query_active_habits using Vikunja-native filter.

   Replaces the comment-parsing approach of the v1 sibling
   (scripts/habits/query_active_habits.py) with a single Vikunja filter
   expression. Both files coexist until Phase 5 (#308) cutover.

   See contracts/api.md + contracts/cli.md for the contract.
   """
   from __future__ import annotations
   import argparse, json, os, sys, urllib.parse, urllib.request, urllib.error
   from datetime import datetime, timezone
   from pathlib import Path
   ```

2. **Module constants**: same `DEFAULT_BASE_URL`, `DEFAULT_TOKEN_PATH`, `HTTP_TIMEOUT_SECONDS` as other WP02/WP03 helpers.

3. **`_http_get(url, token) -> tuple[int, str]`**: same pattern as WP02.

4. **`query_active_today(api_base_url, token, today=None) -> list[dict]`**:
   - `today = today or datetime.now(timezone.utc).date().isoformat()`.
   - Build filter expression: `f"due_date <= {today}T23:59:59Z AND done = false"`.
   - URL-encode the filter.
   - GET `{api_base_url}tasks/all?filter={encoded_filter}` — or use the per-project endpoint if necessary (consult Vikunja v0.24.6 docs / canary test which endpoint accepts the filter syntax).
   - Parse JSON response. Return list of task dicts.

5. **`main(argv=None) -> int`** (CLI):
   - argparse: `--today YYYY-MM-DD` (optional), `--token-file`, `--base-url`.
   - Read token from file.
   - Call `query_active_today(...)`. On OSError → exit 1.
   - Print each task as a JSON object, one per line, on stdout. Exit 0.

**Files**:
- `scripts/habits/query_active_habits_v2.py` (new, ~120 lines)

**Validation**:
- [ ] `python3 -m scripts.habits.query_active_habits_v2 --help` exits 0.
- [ ] Filter expression matches the spec (`due_date <= now/d AND done = false`).

---

### T014 — Implement `scripts/habits/exclude_completed_v2.py`

**Purpose**: Parallel new variant that reads state_log instead of LLM-parsing comments.

**Steps**:

1. **Module setup**:
   ```python
   #!/usr/bin/env python3
   """Phase 5 cutover variant of exclude_completed using JSONL state_log.

   Replaces the LLM-parsing approach of the v1 sibling
   (scripts/habits/exclude_completed.py). Both files coexist until
   Phase 5 (#308) cutover.

   See contracts/api.md + contracts/cli.md for the contract.
   """
   from __future__ import annotations
   import argparse, json, sys
   from datetime import datetime, timezone
   from typing import Iterable

   from scripts.common import state_log
   ```

2. **`exclude_completed_for_today(active_tasks, today=None) -> list[dict]`**:
   - `today = today or datetime.now(timezone.utc).date().isoformat()`.
   - Build the result list:
     ```python
     result = []
     for task in active_tasks:
         existing = state_log.read("habits", task_id=task["id"], date=today, state="complete")
         if not existing:
             result.append(task)
     return result
     ```

3. **`main(argv=None) -> int`** (CLI):
   - argparse: `--today YYYY-MM-DD` (optional). No token needed — pure state_log read.
   - Read stdin line-by-line, parse each as JSON. Empty lines skipped. Malformed JSON: print error to stderr, exit 2.
   - Build `active_tasks` list from stdin.
   - Call `exclude_completed_for_today(...)`. On OSError (state_log read fail) → exit 1.
   - Print each result task as JSON on its own line. Exit 0.

**Files**:
- `scripts/habits/exclude_completed_v2.py` (new, ~80 lines)

**Validation**:
- [ ] `python3 -m scripts.habits.exclude_completed_v2 --help` exits 0.
- [ ] Reads stdin correctly; handles empty input (no error, empty stdout).

---

### T015 — Create `tests/habits/test_query_active_habits_v2.py`

**Purpose**: Coverage of query_active_habits_v2.

**Steps**:

1. **Test: happy path**:
   - Mock urlopen returns canned JSON list of 3 active tasks.
   - `query_active_today` returns the 3 tasks in order.

2. **Test: empty result**:
   - Mock urlopen returns `[]`.
   - Returns empty list.

3. **Test: today override**:
   - Call with `today="2026-05-15"`. Inspect mock urlopen call_args — URL must contain `2026-05-15` (URL-encoded if necessary).

4. **Test: filter expression includes `done = false`**:
   - Inspect URL: must contain the literal `done = false` (URL-encoded).

5. **Test: HTTPError → exit 1 via CLI**:
   - Subprocess + mocked failure. Exit 1.

6. **Test: stdout format**:
   - CLI invocation with mocked successful response. stdout has 3 JSON-per-line entries. Each parses.

**Files**:
- `tests/habits/test_query_active_habits_v2.py` (new, ~140 lines)

**Validation**:
- [ ] `pytest tests/habits/test_query_active_habits_v2.py -v` — all tests pass.
- [ ] Coverage ≥ 85%.

---

### T016 — Create `tests/habits/test_exclude_completed_v2.py`

**Purpose**: Coverage of exclude_completed_v2.

**Steps**:

1. **Test: filter out completed**:
   - Pre-populate state_log (using mock_state_log_dir fixture) with a `complete` record for task 14, date 2026-05-20.
   - Pass an active_tasks list with task 14 and task 15.
   - `exclude_completed_for_today([...], today="2026-05-20")` returns only task 15.

2. **Test: no completions → all returned**:
   - Empty state_log.
   - Returns the full active_tasks list.

3. **Test: today override**:
   - state_log has a complete for task 14 on 2026-05-19.
   - Call with `today="2026-05-20"` → task 14 included (no complete for the new date).
   - Call with `today="2026-05-19"` → task 14 excluded.

4. **Test: CLI stdin parsing**:
   - Subprocess with stdin = 3 newline-separated JSON objects. Verify stdout subset is correct.

5. **Test: CLI empty stdin**:
   - Subprocess with empty stdin → exit 0, empty stdout.

6. **Test: CLI malformed JSON line → exit 2**:
   - Subprocess with `"not json"` as stdin → exit 2.

7. **Test: state_log read failure → exit 1**:
   - Monkey-patch state_log.read to raise OSError. CLI exits 1.

**Files**:
- `tests/habits/test_exclude_completed_v2.py` (new, ~150 lines)

**Validation**:
- [ ] `pytest tests/habits/test_exclude_completed_v2.py -v` — all tests pass.
- [ ] Coverage ≥ 85%.

---

### T017 — Update `docs/design/architecture/data/data-flows.json`

**Purpose**: Register the new write path (habits agent → state_log) AND the new read path (exclude_completed_v2 → state_log.read). Per FR-013.

**Steps**:

1. Read the existing `data-flows.json`. Note its shape (probably a list of flow objects with `source`, `target`, `kind`, etc.).

2. Add new entries (don't remove existing ones — old flows remain live until Phase 5):
   - `{source: "felix-admin-habits agent", target: "scripts/common/state_log.py → habits-history.jsonl", kind: "write", purpose: "Phase 3+ canonical habit completion history per ADR-0002 Q3-D", introduced_by: "#306"}`.
   - `{source: "scripts/habits/exclude_completed_v2.py", target: "scripts/common/state_log.py → habits-history.jsonl", kind: "read", purpose: "Filter today's completed habits via JSONL state log instead of LLM comment parsing", introduced_by: "#306"}`.

3. Validate via `python3 tooling/scripts/validate_docs.py` and (if available) `python3 -c "import json; json.load(open('docs/design/architecture/data/data-flows.json'))"`.

**Files**:
- `docs/design/architecture/data/data-flows.json` (modify; ~10-20 lines added depending on existing schema)

**Validation**:
- [ ] JSON parses without error.
- [ ] `validate_docs.py` passes.
- [ ] Grep confirms new entries: `grep -c 'state_log' docs/design/architecture/data/data-flows.json` ≥ 2.

---

### T018 — Update `docs/design/architecture/data/service-inventory.json`

**Purpose**: Register the 6 new `scripts/habits/` files. Per FR-013.

**Steps**:

1. Read the existing `service-inventory.json`. Note shape.

2. Add entries for the 6 new files (identify_workout_task, migrate_schedule, record_completion, reconcile_completions, query_active_habits_v2, exclude_completed_v2) under the appropriate "scripts" or "components" section. Each entry should include:
   - `name`: file basename
   - `path`: absolute path under the repo (e.g., `scripts/habits/record_completion.py`)
   - `purpose`: 1-line description
   - `host`: "office2" (where they're executed)
   - `introduced_by`: "#306"

3. Do NOT modify existing entries.

4. Validate: `python3 tooling/scripts/validate_docs.py`.

**Files**:
- `docs/design/architecture/data/service-inventory.json` (modify; ~30-50 lines added)

**Validation**:
- [ ] JSON parses.
- [ ] `validate_docs.py` passes.

---

## Branch Strategy

- **Execution worktree**: per `lanes.json`. WP04 depends on WP01.
- **Planning base / merge target**: `main`.

## Definition of Done

- [ ] All 6 subtasks T013-T018 complete and individually validated.
- [ ] `python3 -m scripts.habits.query_active_habits_v2 --help` exits 0.
- [ ] `python3 -m scripts.habits.exclude_completed_v2 --help` exits 0.
- [ ] `pytest tests/habits/test_query_active_habits_v2.py tests/habits/test_exclude_completed_v2.py -v` passes.
- [ ] Coverage ≥ 85% on both new source modules.
- [ ] **C-001 verified**: `scripts/habits/query_active_habits.py` and `scripts/habits/exclude_completed.py` are unchanged (`git diff main -- scripts/habits/query_active_habits.py scripts/habits/exclude_completed.py` returns empty).
- [ ] `validate_docs.py` passes (data-flows.json and service-inventory.json updates).
- [ ] All files committed; no uncommitted artifacts.

## Risks & mitigations

- **C-001 violation risk**: WP04 must NOT touch the existing v1 files. The owned_files declaration scopes this; reviewer should verify via git diff.
- **Vikunja filter syntax**: `due_date <= now/d AND done = false` — verify this syntax is accepted by Vikunja v0.24.6 (the research doc says it is, but canary will confirm). If the syntax needs adjustment, document in Verified API gotchas.
- **data-flows.json schema**: the file's current schema is unknown until read; the new entries must conform.
- **Empty stdin in exclude_completed_v2**: must NOT raise; return immediately with exit 0 + empty stdout.

## Reviewer guidance

- Verify `query_active_habits.py` and `exclude_completed.py` are untouched (git diff on main branch).
- Verify the filter expression in `query_active_habits_v2.py` matches the spec exactly.
- Verify `exclude_completed_v2.py` reads stdin line-by-line (not slurping the entire input at once) — though for typical sizes either works; line-by-line is more robust to malformed entries.
- Verify the doc updates parse as valid JSON and `validate_docs.py` passes.
- Coverage report ≥ 85% on both code modules.

## Implementation command

```bash
spec-kitty agent action implement WP04 --mission habits-native-repeat-jsonl-state-01KS0M59 --agent <agent-name>
```

WP04 depends on WP01; can run in parallel with WP02 and WP03 after WP01 approval.
