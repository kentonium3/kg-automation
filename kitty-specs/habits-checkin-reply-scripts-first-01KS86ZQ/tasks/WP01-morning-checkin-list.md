---
work_package_id: WP01
title: morning_checkin_list helper
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-007
- NFR-003
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-habits-checkin-reply-scripts-first-01KS86ZQ
base_commit: a846b5836c1f09b4c471f6c3f9adfe063fd4dd4d
created_at: '2026-05-22T16:24:19.030557+00:00'
subtasks:
- T001
- T002
- T003
- T004
shell_pid: "65168"
agent: "claude:opus:python-implementer:implementer"
history:
- at: '2026-05-22T16:30:00+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/habits/
execution_mode: code_change
mission_id: 01KS86ZQE8GSZ77ZSGSSQMN08K
mission_slug: habits-checkin-reply-scripts-first-01KS86ZQ
owned_files:
- scripts/habits/morning_checkin_list.py
- tests/habits/test_morning_checkin_list.py
tags: []
---

# WP01 — morning_checkin_list helper

## Objective

Implement the helper that produces today's ordered habit list as both (a) the formatted WhatsApp message text on stdout AND (b) a persisted JSON artifact. This is the single source of truth that bug #371 traces back to — both the morning send and the reply parsing read from the same artifact.

## Context

- **Spec**: FR-001 (artifact + message), FR-002 (identical ordering), FR-007 (sole source), NFR-003 (≤10s), NFR-005 (≤1KB per file)
- **Plan**: Phase 0 D1 (path), D2 (atomic write), D10 (cut targets — informational)
- **Data model**: Entity 1 (artifact schema), Entity 6 (test fixture)
- **API contract**: `contracts/api.md` — `build_morning_list`, `persist_morning_list`, `render_morning_message`, `MorningList` + `MorningListHabit`
- **CLI contract**: `contracts/cli.md` — flags, exit codes
- **Existing helpers consumed**: `scripts/habits/query_active_habits_v2.py`, `scripts/habits/exclude_completed_v2.py`. Read these first to understand the data shape they produce.
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T001 — Module skeleton + dataclasses + module constants

**Purpose**: Establish the module structure per contracts/api.md.

**Steps**:

1. Create `scripts/habits/morning_checkin_list.py` with module docstring referencing the spec + plan.
2. Imports: stdlib only — `argparse`, `dataclasses`, `datetime`, `json`, `os`, `pathlib`, `sys`, `typing`, `urllib.request`, `urllib.error`, `zoneinfo`.
3. Module constants per contracts/api.md:
   ```python
   DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"
   DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
   DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/habits")
   HTTP_TIMEOUT_SECONDS = 30
   LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")
   SCHEMA_VERSION = 1
   ```
4. Define `MorningListHabit` frozen dataclass: `position: int`, `vikunja_task_id: int`, `title: str`.
5. Define `MorningList` frozen dataclass: `schema_version: int`, `date: str`, `generated_at: str`, `habits: list[MorningListHabit]`.

**Files**: `scripts/habits/morning_checkin_list.py` (~80 lines so far).

**Validation**:
- [ ] No third-party imports.
- [ ] `python3 -c "from scripts.habits.morning_checkin_list import MorningList, MorningListHabit; print('ok')"` prints `ok`.

---

### T002 — Core functions: build, persist, render

**Purpose**: The three primary functions per contracts/api.md.

**Steps**:

1. `_today_local() -> str` — helper returning today's date in America/New_York as ISO `YYYY-MM-DD`. Wrap so tests can monkeypatch.
2. `_now_utc_iso() -> str` — helper returning current UTC instant as ISO-8601 with `Z` suffix. Same pattern.
3. `_read_token(token_path: Path) -> str` — file read + strip, raises FileNotFoundError on missing.
4. `_http_get(url: str, token: str) -> dict` — urllib wrapper. Returns parsed JSON. Raises `URLError` on failure.
5. `_query_habits(base_url, token) -> list[dict]` — fetch active habit tasks. Call the existing `scripts.habits.query_active_habits_v2.query_active_habits` function (or whatever its exact function name is — verify by reading that module first).
6. `_exclude_already_addressed(habits, date) -> list[dict]` — call the existing `scripts.habits.exclude_completed_v2` filter. Same: verify function name by reading.
7. `build_morning_list(*, date=None, base_url=..., token_path=...) -> MorningList`:
   - If `date` is None, use `_today_local()`.
   - Fetch + filter habits.
   - Sort by `vikunja_task_id ASC` (stable, immutable per memory `reference_vikunja_id_vs_identifier.md`).
   - Assign 1-indexed positions.
   - Build and return `MorningList`.
8. `persist_morning_list(morning_list, *, state_dir=...) -> Path`:
   - Compute path: `state_dir / f"morning-checkin-{morning_list.date}.json"`.
   - Ensure `state_dir` exists (`mkdir parents=True, exist_ok=True`).
   - Serialize to JSON using `dataclasses.asdict` (custom handling for nested dataclasses).
   - Atomic write: `open(<path>.tmp, "w") as f: f.write(json); f.flush(); os.fsync(f.fileno())`. Then `os.replace(<path>.tmp, <path>)`.
   - Return path.
9. `render_morning_message(morning_list) -> str`:
   - If `morning_list.habits` is empty: return `"All habits complete for today."`.
   - Format per contracts/cli.md "Stdout" section. Day-of-week + Month DD via `datetime.date.fromisoformat(morning_list.date).strftime("%A, %B %-d")` (Linux %-d; on macOS dev, use `%d` and strip the leading zero in Python).

**Files**: same module, +~180 lines.

**Validation**:
- [ ] Functions are pure (no global state); all I/O happens in well-named helpers.
- [ ] Sort by `vikunja_task_id` is stable and tested.
- [ ] Atomic write idempotent: re-running with the same data produces the same file content.

---

### T003 — CLI surface

**Purpose**: Per contracts/cli.md.

**Steps**:

1. `def main(argv=None) -> int` with argparse:
   - `--date <YYYY-MM-DD>` (default: today-local)
   - `--dry-run` flag
   - `--state-dir <path>` (default DEFAULT_STATE_DIR)
   - `--base-url <URL>` (default DEFAULT_BASE_URL)
   - `--token-path <path>` (default DEFAULT_TOKEN_PATH)
2. Build the list via `build_morning_list`. On URLError: exit 1 with structured stderr.
3. If `--dry-run`: emit message to stdout; do NOT persist.
4. Otherwise: persist + emit message.
5. Exit codes per contracts/cli.md: 0 / 1 / 2 / 3.
6. `if __name__ == "__main__": sys.exit(main())`.

**Files**: same module, +~80 lines.

**Validation**:
- [ ] `python3 -m scripts.habits.morning_checkin_list --help` exits 0 with reasonable help.
- [ ] `--date 2026-13-99` (invalid) exits 3 with clear error.

---

### T004 — Tests

**Purpose**: ≥85% coverage of the new helper.

**Steps**:

1. Create `tests/habits/test_morning_checkin_list.py`.
2. Use existing `tests/habits/conftest.py` fixtures (or extend if needed for Vikunja-task mocks).
3. Test cases:
   - **Happy path**: 3 mocked habits → build_morning_list → assert position 1,2,3 with sorted task_ids.
   - **Empty habit list**: build returns empty habits; render returns `"All habits complete for today."`.
   - **persist_morning_list creates the file**: verify content matches MorningList shape.
   - **persist_morning_list is atomic**: simulate write failure (monkeypatch `os.fsync` to raise); verify NO partial file left behind.
   - **render_morning_message format**: assert one line per habit, numbered 1..N, correct day-of-week from a known date.
   - **TZ correctness**: monkeypatch the clock; verify `_today_local()` returns America/New_York date even when system is UTC.
   - **Sort stability**: habits with task_ids [3, 1, 2] → positions assign to titles in 1,2,3 order respectively.
   - **CLI dry-run**: invoke `main(["--dry-run"])`, verify stdout has formatted message AND no file at the expected path.
   - **CLI real run**: invoke `main([])`, verify stdout + file at the expected path.
   - **CLI exit 1 on Vikunja error**: mock urlopen to raise URLError, verify return 1.
   - **CLI exit 3 on invalid date**: verify return 3 + clear stderr.

**Files**: `tests/habits/test_morning_checkin_list.py` (~280 lines, ~15 tests).

**Validation**:
- [ ] `pytest tests/habits/test_morning_checkin_list.py -v` all green.
- [ ] `pytest tests/habits/test_morning_checkin_list.py --cov=scripts.habits.morning_checkin_list --cov-branch --cov-report=term-missing` ≥85%.
- [ ] `pytest tests/habits/ -v` — no regression in existing Phase 3+5 tests.

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

pytest with mocked `urllib` (via fixture). Per-test atomic write verification uses `tmp_path` to isolate. No live Vikunja calls.

## Definition of Done

- [ ] All 4 subtasks complete with validations green.
- [ ] `pytest tests/habits/test_morning_checkin_list.py -v` passes ≥85% coverage.
- [ ] `pytest tests/habits/ -q` — no regression.
- [ ] No third-party imports.
- [ ] Sort-by-task_id verified stable in tests.
- [ ] Atomic write verified non-partial in tests.

## Risks

- **Sort instability**: any sort key other than `task_id` (which is immutable) introduces drift between morning send and reply parse. Reviewer must verify the sort key.
- **Async Vikunja state**: tests must NOT make live calls; mock urlopen.
- **TZ trap**: must use America/New_York consistently; UTC is wrong.

## Reviewer Guidance

1. Confirm sort key is `vikunja_task_id` ASC.
2. Verify atomic write pattern (tmp + fsync + rename).
3. Verify TZ is America/New_York throughout.
4. Coverage ≥85%.

## Implementation Command

```bash
spec-kitty agent action implement WP01 --mission habits-checkin-reply-scripts-first-01KS86ZQ --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-22T16:24:22Z – claude:opus:python-implementer:implementer – shell_pid=60663 – Assigned agent via action command
- 2026-05-22T16:31:38Z – claude:opus:python-implementer:implementer – shell_pid=60663 – Ready for review — atomic write verified, sort stability verified, ≥85% coverage
- 2026-05-22T16:32:14Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=62638 – Started review via action command
- 2026-05-22T16:36:14Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=62638 – Moved to planned
- 2026-05-22T16:38:06Z – claude:opus:python-implementer:implementer – shell_pid=65168 – Started implementation via action command
- 2026-05-22T16:40:37Z – claude:opus:python-implementer:implementer – shell_pid=65168 – Cycle 1 fix: argparse → exit 3
