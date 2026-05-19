---
work_package_id: WP01
title: Backfill helper + tests + architecture documentation
dependencies: []
requirement_refs:
- C-001
- C-002
- C-003
- C-004
- C-005
- C-006
- C-007
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
- NFR-001
- NFR-002
- NFR-003
- NFR-004
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-backfill-habits-jsonl-from-comments-01KS0Y4F
base_commit: 359644f1c48b8c53953c0c67509554157f0179e7
created_at: '2026-05-19T20:32:38.387332+00:00'
subtasks:
- T001
- T002
- T003
- T004
shell_pid: "78143"
agent: "codex:gpt-5:python-reviewer:reviewer"
history:
- at: '2026-05-19T20:35:00Z'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/habits/
execution_mode: code_change
mission_id: 01KS0Y4F60A30H8CT28Z3VMVT6
mission_slug: backfill-habits-jsonl-from-comments-01KS0Y4F
owned_files:
- scripts/habits/backfill_jsonl_from_comments.py
- tests/habits/test_backfill_jsonl_from_comments.py
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/service-inventory.json
tags: []
---

# WP01 — Backfill helper + tests + architecture documentation

## Objective

Build the one-shot operator-driven backfill helper at `scripts/habits/backfill_jsonl_from_comments.py` that reads existing `[Felix]` completion comments from Vikunja habit tasks and replays them as JSONL entries via the Phase 2 `state_log.append` library. Plus its exhaustive test suite and architecture-doc updates. This is the entire Phase 4 scope — after this WP merges and the operator runs the helper, historical completion data is preserved in the canonical JSONL log before Phase 5 cutover (#308) wires the cron to consume it.

## Context

- **Mission spec**: `kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/spec.md` — FR-001..FR-012, NFR-001..NFR-005, C-001..C-007
- **Plan**: `kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/plan.md`
- **Research**: `kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/research.md` — esp. D1 (regex reuse), D2 (state map), D3 (idempotency), D4 (snapshot), D5 (timestamp), D6 (title denorm), D7 (project scoping), D8 (report format), D9 (test layers)
- **Data model**: `kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/data-model.md` — HISTORICAL_STATE_MAP, JSONL record provenance, summary report format
- **API contract**: `kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/contracts/api.md` — `backfill()` signature + exceptions
- **CLI contract**: `kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/contracts/cli.md` — flags + exit codes 0/1/2/3/4
- **Existing pattern references**:
  - `scripts/habits/exclude_completed.py` — source of `FELIX_COMMENT_PATTERN` (import, don't duplicate)
  - `scripts/habits/reconcile_completions.py` — project-scoped enumeration pattern (`_resolve_habits_project_id`)
  - `scripts/habits/record_completion.py` — Vikunja urllib pattern; state_log.append usage
- **Phase 2 library**: `scripts/common/state_log.py` — `append()`, `read()`, `validate_record()`, `DOMAIN_STATES`
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree allocated per `lanes.json`. No prior WPs to wait on.

## Subtasks

### T001 — Implement `scripts/habits/backfill_jsonl_from_comments.py`

**Purpose**: The one-shot backfill helper. Idempotent, dry-run-capable, with summary reporting.

**Steps**:

1. **Module setup**:
   ```python
   #!/usr/bin/env python3
   """Phase 4 (ADR-0002) one-shot historical backfill helper.

   Reads existing [Felix] completion comments from Vikunja habit tasks
   and replays them as JSONL entries via scripts.common.state_log so
   historical completion data is preserved before Phase 5 cutover.

   One-shot tool: not invoked by cron. Re-runs are idempotent (Phase 2's
   (task_id, date, state) dedup short-circuits subsequent attempts).

   See contracts/api.md + contracts/cli.md for the contract.
   """
   from __future__ import annotations
   import argparse, json, os, shutil, sys, urllib.parse, urllib.request, urllib.error
   from datetime import datetime, timezone
   from pathlib import Path
   from typing import Optional

   from scripts.common import state_log
   from scripts.habits.exclude_completed import FELIX_COMMENT_PATTERN
   ```

2. **Module constants**:
   ```python
   DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"
   DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"
   SNAPSHOT_SUFFIX = ".pre-phase4-backfill.bak"
   HABITS_PROJECT_TITLE = "Habits"
   HTTP_TIMEOUT_SECONDS = 30

   HISTORICAL_STATE_MAP: dict[str, str] = {
       "complete": "complete",
       "will-not-do": "skipped",
   }
   ```

3. **HTTP helpers** (mirror `scripts/habits/reconcile_completions.py` pattern):
   - `_http_get(url, token) -> tuple[int, str]`: returns (status, body_text). Raises OSError on URLError/HTTPError.
   - Use `urllib.request.Request` with `Authorization: Bearer <token>` header.

4. **`_resolve_habits_project_id(api_base_url, token) -> int`**:
   - GET `/projects`. Parse JSON.
   - Filter for entries where `title == HABITS_PROJECT_TITLE` (exact match).
   - If exactly 1: return its `id`.
   - If 0 or >1: raise `ValueError("Habits project not uniquely resolvable: found N matches")`.
   - This mirrors `scripts/habits/reconcile_completions.py::_resolve_habits_project_id` — copy and adapt.

5. **`_enumerate_habit_tasks(api_base_url, token, project_id) -> list[dict]`**:
   - GET `/projects/<project_id>/tasks?filter=is_archived = false`.
   - Return list of task dicts (each with at least `id`, `title`).

6. **`_fetch_comments(api_base_url, token, task_id) -> list[dict]`**:
   - GET `/tasks/<task_id>/comments`.
   - Return list of comment dicts (with `id`, `comment` text, `created` ISO-8601 string).
   - On HTTPError: raise OSError (caller catches and logs as anomaly).

7. **`_build_record(task: dict, comment: dict, parsed: re.Match) -> dict`**:
   - Extract `date`, `state`, `note` (optional) from `parsed.groupdict()`.
   - Lowercase the state value to match HISTORICAL_STATE_MAP keys.
   - Build record dict per Phase 2 schema:
     ```python
     {
         "domain": "habits",
         "task_id": task["id"],
         "title": task["title"],
         "date": parsed_date,
         "state": HISTORICAL_STATE_MAP[parsed_state],  # caller already verified mapping exists
         "source": "historical-backfill",
         "note": parsed.group("note") or None,
         "timestamp": comment["created"],
     }
     ```

8. **`_snapshot_jsonl(state_dir: Path) -> Optional[Path]`**:
   - Path: `state_dir / "habits-history.jsonl"`.
   - If file doesn't exist: return None (skip snapshot).
   - Else: `shutil.copy2(source, source.with_suffix(source.suffix + SNAPSHOT_SUFFIX))`.
   - Return the `.bak` Path.
   - Raise OSError on copy failure (caller catches → exit 3).

9. **`backfill(api_base_url: str, token: str, *, dry_run: bool = False, today: str | None = None) -> dict`**:
   - Initialize summary dict with all counter fields = 0, anomalies = [], unmapped_state_values = [], by_task = {}, by_state = {}.
   - Resolve Habits project → `project_id` (raise ValueError on resolution failure).
   - Enumerate habit tasks → `tasks`. Log progress.
   - On live (not dry_run): call `_snapshot_jsonl(state_log.STATE_DIR)`. On OSError: re-raise; caller maps to exit 3.
   - For each task:
     - Fetch comments via `_fetch_comments`. On OSError: append to anomalies, continue to next task.
     - For each comment:
       - Increment total comments fetched.
       - If no `comment.created`: append to anomalies, skip.
       - Match `FELIX_COMMENT_PATTERN.search(comment["comment"])`.
       - If no match: increment skipped_malformed counter, continue.
       - Extract groups. Lowercase state. Check `HISTORICAL_STATE_MAP`.
       - If state unmapped: append to `unmapped_state_values` (include task_id, date, state, comment snippet), increment counter, continue.
       - Build record. Call `state_log.validate_record(record, "habits")`. On ValueError: append to anomalies, skip.
       - If dry_run: increment `records_planned`, update `by_task` + `by_state`, do NOT call `state_log.append`.
       - Else (live):
         - Pre-flight dedup check: `state_log.read("habits", task_id=task_id, date=date, state=mapped_state)`. If non-empty: increment `records_skipped_dedup`, skip the append. (Phase 2's append also handles this but pre-flight avoids racing on the lock.)
         - Else: call `state_log.append("habits", record)`. On success: increment `records_appended`, update `by_task` + `by_state`.
   - Return summary dict.

10. **`_format_summary(summary: dict) -> str`**:
    - Build the operator-facing report per data-model.md Entity 4. Plain text, section headers, bullet entries.

11. **`main(argv: list[str] | None = None) -> int`** (CLI):
    - argparse: `--dry-run` (flag), `--token-file PATH` (default DEFAULT_TOKEN_PATH), `--base-url URL` (default DEFAULT_BASE_URL).
    - Read token from file. On FileNotFoundError: print error to stderr → exit 2.
    - Print progress lines to stdout as the run proceeds (e.g., "Resolved Habits project: id=<N>").
    - Call `backfill(api_base_url, token, dry_run=args.dry_run)`. Catch:
      - `ValueError` → stderr → exit 2.
      - `OSError` (snapshot copy specifically — detect by exception args or wrap in a sub-exception class): stderr → exit 3.
      - Other `OSError` (Vikunja project enumeration failure pre-snapshot) → exit 1.
      - state_log internal failure mid-run (rare): catch in the loop above, append to anomalies, continue → exit 0 with anomalies surfaced. But if state_log fails on initialization (e.g., STATE_DIR uncreatable): exit 4 with stderr.
    - Print summary via `_format_summary(summary)` → stdout. Exit 0.

12. **Module-level docstring**: 8-12 lines summarizing the contract + pointing at `kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/contracts/api.md`.

**Files**:
- `scripts/habits/backfill_jsonl_from_comments.py` (new, ~220 lines)

**Validation**:
- [ ] `python3 -c "from scripts.habits.backfill_jsonl_from_comments import backfill, HISTORICAL_STATE_MAP; print('ok')"` prints ok.
- [ ] `python3 -m scripts.habits.backfill_jsonl_from_comments --help` exits 0.
- [ ] No third-party imports (`grep -E '^(import|from)' scripts/habits/backfill_jsonl_from_comments.py` shows only stdlib + scripts.common + scripts.habits.exclude_completed).
- [ ] No PATCH/POST/PUT/DELETE in the source: `grep -E "(PATCH|POST|PUT|DELETE)" scripts/habits/backfill_jsonl_from_comments.py` shows only documentation references, not Request method calls. (The helper is read-only on Vikunja.)

---

### T002 — Create `tests/habits/test_backfill_jsonl_from_comments.py`

**Purpose**: Exhaustive coverage of T001's behavior.

**Steps**:

1. **Reuse fixtures** from `tests/habits/conftest.py`: `mock_urlopen`, `sample_habit_task_response`, `mock_state_log_dir`. Add new fixtures as needed:
   - `sample_felix_comment`: callable factory `(task_id, date, state, note=None, created="2026-05-19T11:00:00Z")` → returns a dict in Vikunja's comments response shape.

2. **TestProjectResolution** group:
   - Happy path: 1 project named "Habits" → returns id.
   - Zero matches → ValueError.
   - Multiple matches → ValueError.

3. **TestSnapshot** group:
   - File exists → snapshot created, mtime preserved.
   - File missing → snapshot skipped, returns None.
   - Snapshot copy permission denied → OSError raised.

4. **TestBackfillDryRun** group:
   - Happy path: 3 tasks each with 2 [Felix] comments, all `complete`. Dry-run returns summary with `records_planned=6`, `records_appended=0`. No state_log.append calls. No snapshot file created.
   - Unmapped state values: 1 task with a "partial" state comment. Summary records `records_skipped_unmapped=1` and `unmapped_state_values` lists the entry.
   - Malformed comment: 1 task with a comment that doesn't match `FELIX_COMMENT_PATTERN`. Summary records `records_skipped_malformed=1`.

5. **TestBackfillLive** group:
   - Happy path: 2 tasks with 3 + 2 comments. Live run appends 5 records to JSONL. Snapshot created. Summary correct.
   - State mapping verified: `complete` → `complete`, `will-not-do` → `skipped`. Spot-check JSONL line content.
   - Source attribution: all records have `source="historical-backfill"`.
   - Timestamp pass-through: JSONL `timestamp` matches `comment.created` byte-for-byte.

6. **TestIdempotency** group:
   - Live run, then second live run. First: records_appended=N. Second: records_appended=0, records_skipped_dedup=N.
   - Spot-check JSONL line count unchanged after second run.

7. **TestErrorHandling** group:
   - Vikunja project enumerate raises HTTPError → OSError propagates, exit 1.
   - Per-task comment fetch raises HTTPError → anomaly logged, OTHER tasks still processed (exit 0).
   - Comment with missing `created` field → anomaly logged, skipped.
   - state_log.validate_record raises ValueError on a record (e.g., timestamp without timezone, shouldn't happen with proper input but defensive) → anomaly logged, skipped.

8. **TestCLI** group (subprocess tests, fixture-driven):
   - `--help` exits 0.
   - `--dry-run` with mocked Vikunja exits 0, stdout contains "Run mode: dry-run".
   - Live run with mocked Vikunja exits 0, JSONL log gains records.
   - Missing token file exits 2.
   - Project resolution failure exits 2.
   - Snapshot failure (simulate via tmp_path with read-only state dir): exits 3.

**Files**:
- `tests/habits/test_backfill_jsonl_from_comments.py` (new, ~300 lines)

**Validation**:
- [ ] `pytest tests/habits/test_backfill_jsonl_from_comments.py -v` — all tests pass.
- [ ] Coverage on `scripts/habits/backfill_jsonl_from_comments.py` ≥ 85%.
- [ ] No regressions: `pytest tests/habits/ -v` — all 269+ tests still pass.

---

### T003 — Update `docs/design/architecture/data/data-flows.json`

**Purpose**: Register the one-shot backfill flow in the architecture data-flows registry per FR-012.

**Steps**:

1. Read the current `data-flows.json` to understand its schema (it was updated by Phase 3's WP04; flows look like `{name, source, target, kind, purpose, introduced_by}`).

2. Add a new entry:
   ```json
   {
       "name": "habits-historical-backfill",
       "source": "scripts/habits/backfill_jsonl_from_comments.py",
       "target": "scripts/common/state_log.py → habits-history.jsonl",
       "kind": "write",
       "purpose": "One-time backfill of historical Felix completion comments as JSONL records (source=historical-backfill). Operator-driven, not part of cron.",
       "introduced_by": "#307"
   }
   ```

3. Do NOT remove or modify existing entries.

4. Validate: `python3 -c "import json; json.load(open('docs/design/architecture/data/data-flows.json'))"` succeeds.

5. Validate: `python3 tooling/scripts/validate_docs.py` passes (other than pre-existing warnings unrelated to this change).

**Files**:
- `docs/design/architecture/data/data-flows.json` (modify; ~8 lines added)

**Validation**:
- [ ] JSON parses cleanly.
- [ ] `grep "habits-historical-backfill" docs/design/architecture/data/data-flows.json` finds the entry.

---

### T004 — Update `docs/design/architecture/data/service-inventory.json`

**Purpose**: Register the new script in the service inventory per FR-012.

**Steps**:

1. Read the current `service-inventory.json` schema. Phase 3's WP04 registered the 6 Phase 3 scripts under `habit-checkin` service. Find the same section.

2. Add a new entry for the backfill helper within the existing `habit-checkin` service's relevant section (likely `config_files` or `scripts`):
   ```json
   {
       "name": "backfill_jsonl_from_comments.py",
       "path": "scripts/habits/backfill_jsonl_from_comments.py",
       "purpose": "One-shot historical backfill of Felix completion comments to JSONL log",
       "host": "office2",
       "introduced_by": "#307"
   }
   ```

3. Do NOT modify existing entries.

4. Validate: `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` succeeds.

5. Validate: `python3 tooling/scripts/validate_docs.py` passes (other than pre-existing warnings).

**Files**:
- `docs/design/architecture/data/service-inventory.json` (modify; ~7 lines added)

**Validation**:
- [ ] JSON parses cleanly.
- [ ] `grep "backfill_jsonl_from_comments" docs/design/architecture/data/service-inventory.json` finds the entry.

---

## Branch Strategy

- **Current branch at WP start**: as resolved by `spec-kitty agent action implement WP01 --mission backfill-habits-jsonl-from-comments-01KS0Y4F` — typically the lane-a worktree.
- **Planning base / merge target**: `main`.
- **Execution worktree**: allocated per `lanes.json`. WP01 has no dependencies.

## Definition of Done

- [ ] All 4 subtasks T001-T004 complete and individually validated.
- [ ] `python3 -m scripts.habits.backfill_jsonl_from_comments --help` exits 0.
- [ ] `pytest tests/habits/test_backfill_jsonl_from_comments.py -v` passes.
- [ ] Coverage ≥ 85% on `scripts/habits/backfill_jsonl_from_comments.py`.
- [ ] No regressions on the existing 269+ habits tests.
- [ ] data-flows.json and service-inventory.json parse as valid JSON.
- [ ] `python3 tooling/scripts/validate_docs.py` doesn't introduce NEW failures (the pre-existing `.spec-kitty/reviews/` failure from Phase 3 is unrelated and can remain).
- [ ] No new third-party Python dependencies introduced.
- [ ] All files committed; no uncommitted artifacts.

## Risks & mitigations

- **Importing `FELIX_COMMENT_PATTERN` from `scripts.habits.exclude_completed`**: this is a one-directional READ that does NOT violate C-001's "don't modify v1 siblings" rule. Reviewer should verify the import is read-only.
- **HISTORICAL_STATE_MAP locked content**: based on 2026-05-19 probe. If new state values surface during the operator run, summary report names them; operator extends the map + re-runs. No code-side change needed by this WP.
- **State_log.append OSError mid-batch**: per-record failure → anomaly logged, loop continues. Don't abort the whole run on transient failures.
- **`.bak` snapshot atomicity**: `shutil.copy2` is sufficient for single-writer + operator-driven; no concurrency to worry about.
- **Vikunja API quirks**: comment-create is PUT (G4) and comment-readback is `author.username` (G3) — neither affects the backfill (we only GET comments, never write them).

## Reviewer guidance

- Check imports: stdlib + `scripts.common.state_log` + `scripts.habits.exclude_completed.FELIX_COMMENT_PATTERN`. Nothing else.
- Confirm NO modifications to `scripts/habits/exclude_completed.py` (C-001 enforcement).
- Verify `HISTORICAL_STATE_MAP` content matches the spec exactly: `{"complete": "complete", "will-not-do": "skipped"}`.
- Verify project-scoped enumeration: helper resolves "Habits" by exact title, uses `/projects/<id>/tasks`. No `/tasks/all` calls.
- Spot-check the summary report format against `data-model.md` Entity 4.
- Idempotency: re-run test should show 0 appends + N dedup-skipped.
- Coverage report ≥ 85%.
- JSON docs parse + validate_docs passes (modulo pre-existing unrelated failures).

## Implementation command

```bash
spec-kitty agent action implement WP01 --mission backfill-habits-jsonl-from-comments-01KS0Y4F --agent <agent-name>
```

## Activity Log

- 2026-05-19T20:32:40Z – claude:opus:python-implementer:implementer – shell_pid=72034 – Assigned agent via action command
- 2026-05-19T20:53:10Z – claude:opus:python-implementer:implementer – shell_pid=72034 – Ready for review — 4 subtasks complete; backfill helper + tests + arch docs
- 2026-05-19T20:54:30Z – codex:gpt-5:python-reviewer:reviewer – shell_pid=75614 – Started review via action command
- 2026-05-19T20:58:54Z – codex:gpt-5:python-reviewer:reviewer – shell_pid=75614 – Moved to planned
- 2026-05-19T20:59:03Z – claude:opus:python-implementer:implementer – shell_pid=76713 – Started implementation via action command
- 2026-05-19T21:06:00Z – claude:opus:python-implementer:implementer – shell_pid=76713 – Cycle 2: .bak preservation + malformed snippets in report
- 2026-05-19T21:06:38Z – codex:gpt-5:python-reviewer:reviewer – shell_pid=78143 – Started review via action command
