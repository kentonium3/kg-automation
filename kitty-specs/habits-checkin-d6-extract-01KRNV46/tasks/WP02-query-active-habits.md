---
work_package_id: WP02
title: query_active_habits.py + tests
dependencies:
- WP01
requirement_refs:
- FR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
agent: "claude:opus-4-7:implementer:implementer"
shell_pid: "3211"
history:
- event: created
  at: '2026-05-15T17:15:12Z'
  by: spec-kitty.tasks
  note: WP02 prompt generated
authoritative_surface: scripts/habits/query_active_habits.py
execution_mode: code_change
mission_slug: habits-checkin-d6-extract-01KRNV46
owned_files:
- scripts/habits/query_active_habits.py
- tests/habits/test_query_active_habits.py
tags: []
---

# WP02 — query_active_habits.py + tests

## Objective

Ship the Vikunja habit-query helper that fetches all tasks in the Habits project, parses each task's frequency descriptor from its `description` field, applies the project's frequency lexicon (Daily, Daily (evening), Mon-Sat, Mon/Wed/Fri), excludes PAUSED/done tasks, and returns the subset scheduled for the input day.

This helper is the highest-criticality piece of the morning check-in pipeline — it determines WHICH habits appear in Kent's WhatsApp message. A bug here yields the wrong habits being delivered.

## Context

- **Spec**: [`spec.md`](../spec.md) — FR-002 + NFR-005 (test coverage)
- **Contract**: [`contracts/query_active_habits.md`](../contracts/query_active_habits.md) — full CLI + I/O + frequency lexicon + 9 test scenarios
- **Data model**: [`data-model.md`](../data-model.md) — Habit entity + frequency descriptor lexicon (canonical)
- **Auth source**: per Phase 0 R1, read Vikunja token from `/data/services/openclaw/secrets/vikunja-api` (mode 600 file). Base URL: `https://office2.tail0f5f56.ts.net/api/v1`.
- **HTTP library**: `urllib.request` stdlib only (per Phase 0 R2). See `scripts/security/credential_health_check/vikunja_writer.py` for the canonical pattern.

## Subtask details

### T006 — Implement `scripts/habits/query_active_habits.py`

**Purpose**: Vikunja query + frequency-table filter + PAUSED/done exclusion + per-day filter, returning structured JSON to stdout.

**Steps**:

1. Create `scripts/habits/query_active_habits.py` following the contract at [`contracts/query_active_habits.md`](../contracts/query_active_habits.md).
2. Required imports: `argparse`, `json`, `re`, `sys`, `urllib.request`, `urllib.error`, `pathlib.Path`.
3. CLI: `--day`, `--vikunja-token-path` (default `/data/services/openclaw/secrets/vikunja-api`), `--vikunja-base-url` (default the tailscale URL).
4. Internal helpers (in-line, not extracted per C-003):
   ```python
   def _load_token(path: Path) -> str:
       """Read Vikunja API token from a mode-600 file. Returns the token string."""
       return path.read_text(encoding="utf-8").strip()

   def _vikunja_get(base_url: str, token: str, path: str) -> dict:
       """GET request to Vikunja with bearer-style auth. Returns parsed JSON."""
       req = urllib.request.Request(f"{base_url}{path}", headers={"Authorization": f"Bearer {token}"})
       with urllib.request.urlopen(req, timeout=15) as resp:
           return json.loads(resp.read().decode("utf-8"))
   ```
5. Frequency parsing logic:
   - Resolve the Habits project: GET `/projects` → find project with title "Habits" → get its ID.
   - Fetch tasks: GET `/projects/{habits_id}/tasks?per_page=200` (or use `/tasks/all?filter=project_id={id}`).
   - For each task:
     - Skip if `done` is true.
     - Read `description` field. Strip `(PAUSED)` (case-insensitive) — if it WAS present, skip the task entirely.
     - Match remaining description against the frequency lexicon (case-insensitive contains):
       - `daily (evening)` → all 7 days
       - `daily` → all 7 days
       - `mon-sat` or `mon–sat` (en-dash) → Mon-Sat
       - `mon/wed/fri` → Mon, Wed, Fri
       - else → stderr WARN, skip
     - If `--day` is in the matched scheduled-days set: include the task in output.
6. Output: JSON object per contract (`habits`, `total_in_project`, `scheduled_today`). Sort habits by ID ascending. SUMMARY line with counts.
7. Exit codes: 0 / 1 / 2 per contract.

**Files**:
- `scripts/habits/query_active_habits.py` (NEW, ~150 lines)

**Validation**:
- [ ] Helper runs with `--day Wed` and produces well-formed JSON
- [ ] Frequency lexicon matches the data-model table exactly (Daily, Daily (evening), Mon-Sat / Mon–Sat, Mon/Wed/Fri)
- [ ] PAUSED tasks excluded (verified by inspecting a manual run with a known-paused habit)
- [ ] `done: true` tasks excluded
- [ ] Habit list sorted by ID ascending

---

### T007 — Write `tests/habits/test_query_active_habits.py`

**Purpose**: pytest test module covering 9 scenarios from the contract's test table.

**Steps**:

1. Create `tests/habits/test_query_active_habits.py` following the contract's test table.
2. Mocking strategy: patch `urllib.request.urlopen` with `unittest.mock.patch`. Construct mock responses that return JSON via a helper fixture.
3. Implement these 9 tests from the contract:
   - `test_daily_all_seven_days` — 1 daily task in fixture; query each day; always returned
   - `test_mon_sat_excludes_sunday` — 1 Mon-Sat task; query Sun → empty; query Mon-Sat → returned
   - `test_mon_wed_fri_only_three_days` — 1 Mon/Wed/Fri task; query each day; in for Mon/Wed/Fri only
   - `test_paused_excluded` — task with `(PAUSED)` in description; never in result
   - `test_done_excluded` — task with `done: true`; never in result
   - `test_unrecognized_freq_skipped_with_warning` — task with description "Twice weekly"; not in result; stderr contains WARN
   - `test_empty_project` — Habits project has 0 tasks; exit 0; `habits: []`
   - `test_vikunja_unreachable` — `urlopen` raises `URLError`; exit 1
   - `test_invalid_day_arg` — `--day Funday`; exit 2
4. Use `subprocess` invocation pattern (matches T004 convention). For mocking, since the helper is CLI-invoked, the cleanest approach is to mock at the helper's source level — either:
   - Have the helper expose its `urlopen` as a module-level binding that can be patched in import-mode
   - Or use a `--mock-fixture` flag for testing (less clean)
   - **Recommended**: import the helper as a module for unit testing (`from scripts.habits import query_active_habits`) and call its main()/internal functions directly. This requires the helper to be both a CLI AND an importable module.

5. Helper structure to enable both CLI and importable testing:
   ```python
   #!/usr/bin/env python3
   """Module docstring."""
   # ... imports ...

   def main(argv=None) -> int:
       """Entry point. Returns exit code."""
       # parse args, do work, print output, return 0/1/2

   if __name__ == "__main__":
       sys.exit(main())
   ```
   Then tests `import scripts.habits.query_active_habits as qah` and patch `qah.urllib.request.urlopen` with `unittest.mock.patch`.

**Files**:
- `tests/habits/test_query_active_habits.py` (NEW, ~250 lines including fixtures)

**Validation**:
- [ ] All 9 tests written and pass
- [ ] Mock fixtures cover all 4 frequency cases (Daily, Daily (evening), Mon-Sat, Mon/Wed/Fri)
- [ ] No real Vikunja API calls during test run (all `urlopen` patched)
- [ ] Tests run in <5 seconds locally

---

### T008 — Local validation against office2 Vikunja

**Purpose**: Confirm the helper works against the REAL Vikunja API on office2 (not just mocked tests).

**Steps**:

1. Acquire a local copy of the Vikunja token (from office2) for testing:
   ```bash
   # On the Mac:
   ssh office2-claude 'cat /data/services/openclaw/secrets/vikunja-api' > /tmp/vikunja-token-readonly
   chmod 600 /tmp/vikunja-token-readonly
   ```
   (Or run the validation directly on office2 where the token is already accessible.)
2. Run helper with override flag pointing at the local token:
   ```bash
   python3 scripts/habits/query_active_habits.py \
       --day "$(python3 scripts/habits/compute_today.py | jq -r .day)" \
       --vikunja-token-path /tmp/vikunja-token-readonly
   ```
3. Verify the returned habits list matches what the CURRENT agent's AGENTS.md Step 2 would have produced for the same day. If you have a recent reference (from T001's metadata file), cross-check the count and titles.
4. Run pytest:
   ```bash
   pytest tests/habits/test_query_active_habits.py -v
   ```
5. Clean up: `rm /tmp/vikunja-token-readonly` after validation.

**Files**: No new files; validation only.

**Validation**:
- [ ] Helper returns sensible habit list when run against real Vikunja
- [ ] Habit count matches independent inspection of the Habits project for today's day-of-week
- [ ] Test suite passes (9/9)
- [ ] No real Vikunja state mutations occurred (helper is read-only)

---

## Branch Strategy

- **Planning base**: `main`
- **Merge target**: `main`
- **Execution workspace**: Per-lane worktree allocated by `finalize-tasks` `lanes.json`. Worktree branches from WP01's merged state (since dependencies: ["WP01"]).

## Test strategy

Tests REQUIRED for this WP (NFR-005). The helper makes Vikunja API calls (mutates external state contract); has multiple code paths (each frequency case); handles state-format-sensitive parsing — qualifies under conventions § 8 "REQUIRED when" three different criteria.

- pytest + `unittest.mock` for HTTP mocking.
- Test file at `tests/habits/test_query_active_habits.py`.
- 9 test cases from contract.
- Helper structured as both CLI and importable module so tests can patch `urllib.request.urlopen` at module level.

## Definition of Done

- [ ] T006: `scripts/habits/query_active_habits.py` implemented per contract; runs cleanly
- [ ] T007: `tests/habits/test_query_active_habits.py` has 9 tests, all passing
- [ ] T008: local validation against real Vikunja confirms behavior
- [ ] Module docstring references FR-002 and contract path
- [ ] Helper structure supports both `python3 scripts/habits/query_active_habits.py` and `import scripts.habits.query_active_habits` for testability
- [ ] All owned_files committed
- [ ] Mark all subtasks done: `spec-kitty agent tasks mark-status T006 T007 T008 --status done`
- [ ] Move to for_review: `spec-kitty agent tasks move-task WP02 --to for_review --note "Ready for review — query_active_habits.py complete with 9 tests passing"`

## Risks

- **Frequency lexicon strictness**: the existing AGENTS.md table is the source of truth. Don't add or modify cases; out-of-vocabulary descriptions go to stderr WARN per contract.
- **En-dash vs ascii dash**: the AGENTS.md table lists `Mon–Sat` (en-dash, U+2013). The current Vikunja habit descriptions may use either. Implementation must accept both — explicit test case (`test_mon_sat_excludes_sunday`) should verify with the en-dash variant.
- **Habits project ID resolution**: never hardcode the project ID. Resolve by title at runtime so the helper survives Vikunja project renames or rebuilds.
- **Token file permissions**: helper assumes the token file is readable. Document behavior on permission error in the exit-1 code path (stderr message must mention "permission denied" so operator can diagnose).

## Reviewer guidance (for Codex)

Verify:

1. **Frequency lexicon**: every case in [`data-model.md`](../data-model.md#habit) is handled in code AND covered by a test case. Out-of-vocab cases produce a WARN, not an exception.
2. **PAUSED handling**: matched case-insensitively; the matcher strips `(PAUSED)` from the description before checking frequency (a "(PAUSED) Daily" task that gets unpaused later would still parse correctly).
3. **HTTP**: uses `urllib.request`, NOT `requests`. Mocks at `urllib.request.urlopen`, not at module-level helper functions.
4. **Token loading**: reads from `/data/services/openclaw/secrets/vikunja-api` by default; overridable via `--vikunja-token-path`. Doesn't log token contents to stderr or stdout.
5. **Output stability**: habits sorted by ID ascending so downstream comparisons (in WP05's smoke test) are deterministic.
6. **Project resolution**: Habits project found by title lookup, not hardcoded ID.

Reject if:
- HTTP uses `requests` or any third-party library
- Token contents logged anywhere
- Frequency lexicon adds cases not in the data-model table (scope creep)
- Project ID hardcoded
- Tests don't cover the en-dash `Mon–Sat` variant

## Activity Log

- 2026-05-15T18:08:12Z – claude:opus-4-7:implementer:implementer – shell_pid=3211 – Started implementation via action command
