---
work_package_id: WP05
title: Cutover script for backlog replay
dependencies:
- WP04
requirement_refs:
- C-008
- FR-014
- FR-015
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T19:45:00+00:00'
subtasks:
- T024
- T025
- T026
- T027
- T028
history: []
authoritative_surface: scripts/doc_audit/helpers/cutover_362.py
execution_mode: code_change
mission_id: 01KS8J321F8KE7369R3DA02329
mission_slug: drift-event-auto-resolution-01KS8J32
owned_files:
- scripts/doc_audit/helpers/cutover_362.py
- tests/doc_audit/helpers/test_cutover_362.py
tags: []
agent: "agy:gemini-2.5-pro:spec-kitty-review:reviewer"
shell_pid: "24424"
---

# WP05 — Cutover script for backlog replay

## Objective

Implement the one-shot cutover script that closes the 13 known pre-#362 `[doc-audit]` P3 issues + resets the drift-events cursor + writes the idempotency marker. Operator runs this once during deploy; the next cron tick reprocesses originating drift events via the new Moment 0 pipeline.

## Context

- **Spec**: FR-014 (cursor reset), FR-015 (close pre-existing issues), C-008 (backlog replay)
- **Plan**: D5 (cutover script design)
- **Data model**: E6 (CutoverState marker)
- **CLI contract**: [contracts/cli.md](../contracts/cli.md) — cutover_362 section
- **API contract**: [contracts/api.md](../contracts/api.md) — `cutover_362.run()` signature
- **Dependencies**: WP04 (`--reset-cursor` flag must exist on handle_drift_events)
- **Branching**: planning_base=`main`, merge_target=`main`.

## Subtasks

### T024 — Module skeleton + CutoverResult dataclass

**Purpose**: Establish module surface.

**Steps**:

1. Create `scripts/doc_audit/helpers/cutover_362.py` with module docstring explaining the one-shot purpose.
2. Imports: stdlib `argparse`, `json`, `os`, `subprocess`, `sys`, `tempfile`, `dataclasses`, `pathlib`, `datetime`, `logging`, `time`.
3. Module constants:
   ```python
   MARKER_PATH = Path.home() / ".config" / "doc-audit" / "cutover-362.done"
   MISSION_SLUG = "drift-event-auto-resolution-01KS8J32"
   MISSION_ID = "01KS8J321F8KE7369R3DA02329"
   REPO = "kentonium3/kg-automation"
   GH_QUERY = 'is:issue is:open label:P3-candidate "[doc-audit]" in:title'
   COMMENT_BODY = (
       "Closing as part of mission {mission_slug} (#362). "
       "The new drift-interpretation pipeline will reprocess this drift event "
       "on the next cron tick. See quickstart.md in the mission folder for details."
   )
   GH_RATE_DELAY_SECONDS = 0.5  # polite spacing between gh calls
   ```
4. `@dataclass(frozen=True) class CutoverResult`:
   - `issues_closed: list[int]`
   - `cursor_reset: bool`
   - `marker_written: bool`
   - `dry_run: bool`
   - `already_done: bool`  # True when marker existed and --force not set

**Files**: `scripts/doc_audit/helpers/cutover_362.py` (~80 lines so far).

**Validation**:
- [ ] `python3 -c "from scripts.doc_audit.helpers.cutover_362 import run, CutoverResult; print('ok')"` prints `ok`

---

### T025 — GitHub close-with-comment

**Purpose**: Query open P3 `[doc-audit]` issues, post a comment, close.

**Steps**:

1. `_list_open_issues() -> list[int]`:
   - `subprocess.run(["gh", "issue", "list", "--repo", REPO, "--state", "open", "--search", GH_QUERY, "--json", "number", "--limit", "30"], capture_output=True, text=True, check=True)`
   - Parse JSON output, return list of issue numbers
2. `_close_issue(issue_number: int, comment: str) -> None`:
   - Post comment: `subprocess.run(["gh", "issue", "comment", str(issue_number), "--repo", REPO, "--body", comment], check=True)`
   - Close issue: `subprocess.run(["gh", "issue", "close", str(issue_number), "--repo", REPO], check=True)`
   - Sleep `GH_RATE_DELAY_SECONDS` between calls
3. `_close_all_issues(issue_numbers: list[int], dry_run: bool) -> list[int]`:
   - If dry_run: print what would happen; return empty list
   - Otherwise: iterate, call `_close_issue` for each; return list of closed numbers; on subprocess error, log + continue (don't fail the whole cutover; partial-close is recoverable on next run via `--force`)

**Files**: same module, +~80 lines.

**Validation**:
- [ ] Mocked `subprocess.run`: test verifies each issue gets comment + close
- [ ] Dry-run: no subprocess calls made beyond the list query
- [ ] Error tolerance: one failed close doesn't abort the others

---

### T026 — Cursor reset + marker write

**Purpose**: Reset cursor (via WP04's flag) and write idempotency marker.

**Steps**:

1. `_reset_cursor(dry_run: bool) -> bool`:
   - If dry_run: log "Would reset cursor"; return True
   - Otherwise: `subprocess.run(["python3", "-m", "scripts.doc_audit.helpers.handle_drift_events", "--reset-cursor"], check=True)`
   - Return True on success
2. `_write_marker(closed_issues: list[int], dry_run: bool) -> bool`:
   - If dry_run: log "Would write marker"; return True
   - Otherwise:
     - Ensure parent dir exists (`MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)`)
     - Build marker content (YAML or plain key:value):
       ```
       mission: drift-event-auto-resolution-01KS8J32
       mission_id: 01KS8J321F8KE7369R3DA02329
       run_at_utc: <ISO 8601 now>
       closed_issues: [351, 352, ...]
       cursor_reset_to: 0
       ```
     - Atomic write: tempfile in same dir + rename to MARKER_PATH
     - Return True
3. `_marker_exists() -> bool` — `MARKER_PATH.exists()`.

**Files**: same module, +~60 lines.

**Validation**:
- [ ] Marker write is atomic (tempfile + rename, observable via tmp_path)
- [ ] Marker contents include all closed issue numbers
- [ ] Dry-run produces no filesystem state

---

### T027 — CLI flags + main()

**Purpose**: Per contracts/cli.md cutover_362 section.

**Steps**:

1. `run(*, dry_run: bool = False, force: bool = False) -> CutoverResult`:
   - If `_marker_exists()` and not `force`: log + return `CutoverResult(already_done=True, ...)`
   - Otherwise: list issues → close all → reset cursor → write marker → return `CutoverResult(...)`
2. `def main(argv=None) -> int` with argparse:
   - `--dry-run` flag
   - `--force` flag
3. Call `run()`; print summary; exit codes:
   - 0 success or idempotent no-op
   - 1 GitHub API failure
   - 2 filesystem failure
4. `if __name__ == "__main__": sys.exit(main())`.

**Files**: same module, +~50 lines.

**Validation**:
- [ ] `python3 scripts/doc_audit/helpers/cutover_362.py --help` exits 0
- [ ] `--dry-run` flag: no mutations
- [ ] Marker exists + no `--force`: idempotent no-op (exit 0)
- [ ] Marker exists + `--force`: re-runs

---

### T028 — Tests

**Purpose**: ≥85% coverage; mock gh + filesystem.

**Steps**:

1. Create `tests/doc_audit/helpers/test_cutover_362.py`.
2. Mock `subprocess.run` via monkeypatch or `unittest.mock`.
3. Use `tmp_path` for marker location (monkeypatch `MARKER_PATH`).
4. Test cases:
   - **Happy path**: 5 open issues → mocked subprocess succeeds → marker written → CutoverResult.issues_closed has 5 entries.
   - **Dry-run**: no subprocess calls beyond list; no marker write; returns CutoverResult(dry_run=True).
   - **Idempotent no-op**: marker pre-exists → returns CutoverResult(already_done=True); no subprocess calls.
   - **--force overrides marker**: marker pre-exists + force=True → cutover runs anyway.
   - **gh list failure**: subprocess.run raises CalledProcessError → returns exit 1.
   - **gh comment failure on issue 3 of 5**: issues 1-2 succeed, 3 fails, 4-5 succeed; CutoverResult.issues_closed lists 1,2,4,5 (skipping 3); marker still written.
   - **Cursor reset subprocess failure**: handle_drift_events --reset-cursor fails → returns exit 2 (filesystem-class failure).
   - **Marker write failure**: simulate PermissionError on write → returns exit 2.
   - **Marker contents**: read back the marker file after success; assert mission_id, run_at_utc, closed_issues all present.
   - **CLI exit codes**: invoke main with each scenario; assert correct exit code.
   - **Polite rate-limit spacing**: assert `time.sleep` (mocked) called with `GH_RATE_DELAY_SECONDS` between gh calls.

**Files**: `tests/doc_audit/helpers/test_cutover_362.py` (~220 lines, ~11 tests).

**Validation**:
- [ ] `pytest tests/doc_audit/helpers/test_cutover_362.py -v` ≥85% coverage
- [ ] No real GitHub API calls
- [ ] Marker tests use tmp_path

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

pytest with mocked `subprocess.run` and `tmp_path` for marker. No live GitHub calls.

## Definition of Done

- [ ] All 5 subtasks complete.
- [ ] `pytest tests/doc_audit/helpers/test_cutover_362.py -v` ≥85%.
- [ ] CLI smoke: `--help`, `--dry-run`, `--force` all behave per contract.
- [ ] Idempotency verified (marker prevents re-run).

## Risks

- **GitHub rate-limit**: 13 issues × 2 calls (comment + close) = 26 calls. Under the 5000/hr authenticated limit. `GH_RATE_DELAY_SECONDS = 0.5` adds buffer.
- **Partial-close on failure**: documented behavior is "close what you can, log failures". Operator can re-run with `--force` to clean up stragglers.
- **Marker path**: `~/.config/doc-audit/` may not exist on first run. Script must create parent dir.
- **Subprocess invocation of handle_drift_events**: must work as a module call (`python3 -m scripts.doc_audit.helpers.handle_drift_events`). Test verifies the invocation pattern.

## Reviewer Guidance

1. Verify marker is written atomically (tempfile + rename in tmp_path test).
2. Verify dry-run makes no GitHub or filesystem mutations.
3. Verify the GH search query matches contracts/cli.md exactly: `'is:issue is:open label:P3-candidate "[doc-audit]" in:title'`.
4. Verify the comment body references the mission slug + #362 + quickstart.md.
5. Coverage ≥85%.

## Implementation Command

```bash
spec-kitty agent action implement WP05 --mission drift-event-auto-resolution-01KS8J32 --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-22T21:56:21Z – claude:opus:python-implementer:implementer – shell_pid=22906 – Started implementation via action command
- 2026-05-22T22:03:21Z – claude:opus:python-implementer:implementer – shell_pid=22906 – Ready for review: cutover_362 script; 28 tests / 96% coverage; full doc_audit regression clean (532 passed / 2 skipped)
- 2026-05-22T22:04:03Z – agy:gemini-2.5-pro:spec-kitty-review:reviewer – shell_pid=24424 – Started review via action command
