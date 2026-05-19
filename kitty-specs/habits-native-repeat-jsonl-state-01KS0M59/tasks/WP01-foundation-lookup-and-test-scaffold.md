---
work_package_id: WP01
title: 'Foundation: workout lookup + tests/habits scaffolding'
dependencies: []
requirement_refs:
- C-006
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-habits-native-repeat-jsonl-state-01KS0M59
base_commit: 8eed40a3980c9aab93a6a28d4fe0670bd67f4b5f
created_at: '2026-05-19T18:00:35.554614+00:00'
subtasks:
- T001
- T002
- T003
shell_pid: '45180'
history:
- at: '2026-05-19T17:30:00Z'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/habits/
execution_mode: code_change
mission_id: 01KS0M59313RF0WVJZTXYDJC6C
mission_slug: habits-native-repeat-jsonl-state-01KS0M59
owned_files:
- scripts/habits/identify_workout_task.py
- tests/habits/__init__.py
- tests/habits/conftest.py
- tests/habits/test_identify_workout_task.py
tags: []
---

# WP01 — Foundation: workout lookup + tests/habits scaffolding

## Objective

Establish the `tests/habits/` package with shared fixtures, and deliver the `identify_workout_task.py` lookup helper. This unblocks WP02-WP04 (which all consume the conftest fixtures) and gives the operator the lookup tool needed for WP02 migration.

## Context

- **Mission spec**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/spec.md`
- **Plan**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/plan.md`
- **Research**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/research.md` (D1, D2)
- **API contract**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/api.md` — see `find_workout_task` signature
- **CLI contract**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/cli.md` — see `identify_workout_task`
- **Phase 2 library**: `scripts/common/state_log.py` (commit 231e880) — used by downstream WPs but not directly by WP01
- **Existing scripts/vikunja/* helpers**: read `provision_felix_bot.py` as the canonical urllib HTTP pattern for this codebase
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree allocated per `lanes.json`.

## Subtasks

### T001 — Create `scripts/habits/identify_workout_task.py`

**Purpose**: One-shot lookup helper that finds the current "workout" habit task among the 8 known production habit IDs (14, 15, 16, 17, 18, 19, 20, 65). Operator runs this once during Phase 3 pre-flight to identify the workout task ID for the `retire` op in `habits-schedule.yaml`.

**Steps**:

1. **Imports**: stdlib only — `argparse`, `json`, `os`, `re`, `sys`, `urllib.request`, `urllib.error`, `pathlib`.

2. **Module constants**:
   ```python
   DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"  # office2 Vikunja over Tailscale loopback
   DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"
   DEFAULT_CANDIDATE_IDS = [14, 15, 16, 17, 18, 19, 20, 65]
   HTTP_TIMEOUT_SECONDS = 30
   WORKOUT_TITLE_REGEX = re.compile(r"workout", re.IGNORECASE)
   ```

3. **`_http_get(url, token)` helper**:
   - Build `urllib.request.Request` with `Authorization: Bearer <token>` header.
   - Call `urlopen` with `HTTP_TIMEOUT_SECONDS`. Return `(status, body_text)`.
   - On `URLError`/`HTTPError`: raise `OSError` with a clear message including the URL.

4. **`find_workout_task(api_base_url, token, candidate_ids=None) -> dict | None`**:
   - For each candidate id: `_http_get(api_base_url + f"tasks/{id}", token)` → parse JSON.
   - Match `title` against `WORKOUT_TITLE_REGEX`. Collect matches.
   - If exactly one match: return a dict `{task_id, title, project_id, labels, repeat_after, due_date}`.
   - If zero matches: return `None`.
   - If multiple matches: raise `ValueError(f"Multiple workout-like tasks found: {[ids]}")`.

5. **`main(argv=None) -> int`** (CLI):
   - argparse with `--token-file` (default DEFAULT_TOKEN_PATH), `--base-url` (default DEFAULT_BASE_URL), `--candidate-ids` (comma-separated, default DEFAULT_CANDIDATE_IDS).
   - Read token from file (handle FileNotFoundError, exit 2).
   - Call `find_workout_task`. On `None`: print `null` to stdout, exit 0.
   - On `ValueError` (multiple): print error to stderr listing the IDs found, exit 1.
   - On `OSError`: print to stderr, exit 2.
   - On match: print JSON object to stdout, exit 0.

6. **Module structure**: matches the `scripts/vikunja/*.py` convention — module-level constants, helper functions, `def main()`, `if __name__ == "__main__": sys.exit(main())`.

**Files**:
- `scripts/habits/identify_workout_task.py` (new, ~160 lines)

**Validation**:
- [ ] `python3 -m scripts.habits.identify_workout_task --help` exits 0 with reasonable help text.
- [ ] Manual test with a mocked token file pointing at a sandbox Vikunja instance (or skip if no live access from dev machine; rely on unit tests in T003).
- [ ] No third-party imports (`grep -E '^(import|from)\s+(?!urllib|json|os|re|sys|argparse|pathlib|__future__)' scripts/habits/identify_workout_task.py` returns nothing).

---

### T002 — Create `tests/habits/__init__.py` + `tests/habits/conftest.py`

**Purpose**: Establish the `tests/habits/` package and shared fixtures consumed by WP02-WP04 test files.

**Steps**:

1. Create empty `tests/habits/__init__.py`.

2. Create `tests/habits/conftest.py` with these pytest fixtures:

   **`fake_vikunja_token`**: trivial fixture returning a placeholder string `"test-token-xxx"`.

   **`tmp_token_file(tmp_path, fake_vikunja_token)`**: writes the placeholder token to `tmp_path / "token"` mode 0600 and returns its path.

   **`sample_habit_task_response`**: returns a callable factory:
   ```python
   def _make(task_id, title="Habit", repeat_after=0, repeat_mode=0, done=False,
             due_date="2026-05-20T08:00:00Z", project_id=1, labels=None,
             is_archived=False, done_at=None):
       return {
           "id": task_id, "title": title, "repeat_after": repeat_after,
           "repeat_mode": repeat_mode, "done": done, "due_date": due_date,
           "project_id": project_id, "labels": labels or [],
           "is_archived": is_archived, "done_at": done_at,
       }
   ```

   **`mock_urlopen(monkeypatch)`**: monkey-patches `urllib.request.urlopen` to a `MagicMock`. Returns the mock so tests can configure `.return_value.read.return_value` per-call.

   **`mock_state_log_dir(tmp_path, monkeypatch)`**: monkey-patches `scripts.common.state_log.STATE_DIR` to `tmp_path / "state"` and creates the dir. Returns the path. Also sets `FELIX_STATE_LOG_DIR` env var via `monkeypatch.setenv` for subprocess tests.

3. **Module docstring**: brief description of available fixtures.

**Files**:
- `tests/habits/__init__.py` (new, empty)
- `tests/habits/conftest.py` (new, ~80 lines)

**Validation**:
- [ ] `pytest tests/habits/ --collect-only` lists T003's test module without ImportError.
- [ ] Fixtures importable: `from tests.habits.conftest import *` works (or via pytest's automatic conftest discovery).

---

### T003 — Create `tests/habits/test_identify_workout_task.py`

**Purpose**: Exhaustive coverage of `identify_workout_task.py` (T001).

**Steps**:

1. **Test: single workout match found**:
   - `mock_urlopen` returns canned responses for tasks 14-20 + 65, with task 17 having title "Workout — strength training" and others with non-workout titles.
   - Call `find_workout_task(api_base_url, token)`. Assert returns dict with `task_id=17` and the title/project_id/labels.

2. **Test: zero matches**:
   - Mock all 8 candidate responses with non-workout titles.
   - `find_workout_task` returns `None`.

3. **Test: multiple matches**:
   - Mock 2 candidates with workout-matching titles.
   - `find_workout_task` raises `ValueError` mentioning both IDs.

4. **Test: case-insensitive match**:
   - Mock title "WORKOUT" or "Workout" or "workout" — all should match.

5. **Test: HTTPError on one candidate**:
   - One urlopen call raises `urllib.error.HTTPError(404)`. Helper should raise `OSError` (per contract), NOT silently skip the candidate. (Rationale: missing a candidate task means the candidate-ID list is wrong, which the operator must know about.)

6. **Test: CLI happy path** (subprocess):
   - Use `subprocess.run` against `python3 -m scripts.habits.identify_workout_task --token-file tmp_token_file --base-url <mock server URL>` — OR mock urlopen at the in-process level and call `main()` directly with `argv=[...]`.
   - Verify exit 0 + JSON on stdout.

7. **Test: CLI multiple matches** (exit 1):
   - Subprocess invocation with mocked Vikunja producing 2 matches. Verify exit 1, stderr mentions IDs.

8. **Test: CLI no match** (exit 0, stdout = `null`):
   - All non-workout titles. Verify exit 0, stdout = `"null\n"`.

**Files**:
- `tests/habits/test_identify_workout_task.py` (new, ~180 lines)

**Validation**:
- [ ] `pytest tests/habits/test_identify_workout_task.py -v` — all tests pass.
- [ ] Coverage ≥ 90% on `scripts/habits/identify_workout_task.py`.

---

## Branch Strategy

- **Current branch at WP start**: as resolved by `spec-kitty agent action implement WP01 --mission habits-native-repeat-jsonl-state-01KS0M59` — typically the lane-a worktree.
- **Planning base / merge target**: `main`.
- **Execution worktree**: allocated per `lanes.json`. WP01 has no dependencies, so it can start immediately.
- All file edits + commits happen in the worktree, not the main repo.

## Definition of Done

- [ ] All 3 subtasks T001-T003 complete and individually validated.
- [ ] `python3 -m scripts.habits.identify_workout_task --help` exits 0 with reasonable help text.
- [ ] `pytest tests/habits/ -v` passes with all tests green (just T003 at this point; other test files will land in WP02-WP04).
- [ ] Coverage on `scripts/habits/identify_workout_task.py` ≥ 90% line + branch.
- [ ] No new third-party dependencies introduced.
- [ ] All files committed by the spec-kitty workflow; no uncommitted artifacts.

## Risks & mitigations

- **fcntl in `mock_state_log_dir` fixture**: the Phase 2 state_log uses fcntl locking. Tests that touch the state_log must use the monkey-patched STATE_DIR. WP01 doesn't yet exercise state_log directly (only WP02-WP04 do), but the fixture is in place ready for them.
- **Token file 0600 mode in fixture**: macOS umask may strip group bits — use explicit `os.chmod(0o600)` after creating the temp file.

## Reviewer guidance

- Check imports: stdlib only.
- Verify `find_workout_task` matches the contract in `contracts/api.md`. Exit codes for the CLI must match `contracts/cli.md`.
- Verify the conftest.py fixtures are pytest-discoverable (no module-level state outside fixtures).
- Check the regex `re.IGNORECASE` flag is on for the workout title match.
- Coverage report: confirm ≥90% on the lookup helper.

## Implementation command

```bash
spec-kitty agent action implement WP01 --mission habits-native-repeat-jsonl-state-01KS0M59 --agent <agent-name>
```
