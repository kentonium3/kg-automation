---
work_package_id: WP05
title: Touchpoint URL Migration
dependencies:
- WP01
requirement_refs:
- FR-008
- FR-010
- FR-011
- NFR-002
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T018
- T019
- T020
- T021
- T022
- T023
- T024
- T025
history: []
authoritative_surface: scripts/habits/
execution_mode: code_change
owned_files:
- scripts/habits/query_active_habits_v2.py
- scripts/habits/morning_checkin_list.py
- scripts/habits/set_due_dates.py
- scripts/habits/reconcile_completions.py
- scripts/escalation/reconcile_completions.py
- scripts/enrichment/reconcile_completions.py
- scripts/sync/driver.py
tags: []
agent: "claude:sonnet:implementer:implementer"
shell_pid: "80769"
---

# WP05 — Touchpoint URL Migration

## Objective

Migrate 7 runtime-path scripts (6 #519-migrated touchpoints + the #518 driver) to read the Vikunja base URL from `get_vikunja_base_url()` (from WP01) instead of hardcoded URL constants. Verify NFR-006 grep contract — zero hardcoded URLs remain in runtime-path scripts.

Each touchpoint migration is a uniform 1-3 line refactor: add an import, replace the URL constant or CLI default with the helper call. The work is repetitive but each file is touched in isolation.

## Context

Per spec FR-008, the following 7 scripts in the runtime path read the Vikunja base URL from a shared source:

- `scripts/habits/query_active_habits_v2.py` (TP-03, cache-only read)
- `scripts/habits/morning_checkin_list.py` (TP-07, cache-only read)
- `scripts/habits/set_due_dates.py` (TP-04, cache-only GET; preserves direct `_http_put` for writes)
- `scripts/habits/reconcile_completions.py` (TP-02, cache reconciliation)
- `scripts/escalation/reconcile_completions.py` (TP-10, escalation reconciliation)
- `scripts/enrichment/reconcile_completions.py` (TP-12, cache reconciliation; preserves `_http_get` for comments)
- `scripts/sync/driver.py` (CLI default for the reconciliation driver)

Each file currently has one of these patterns:
- A module-level constant (`VIKUNJA_BASE_URL = "https://office2.tail0f5f56.ts.net/api/v1"`)
- A CLI argparse default value (e.g., `parser.add_argument("--vikunja-base-url", default="...")`)

The migration: replace the literal URL with `get_vikunja_base_url()` from `scripts/common/vikunja_config.py` (WP01).

**Per memory `feedback_wp_prompts_grep_codebase`**: BEFORE writing the literal import or constant change for any file, READ the actual current state of that file. Different touchpoints may have slightly different module-init patterns (some compute the URL inside a function call, some use a constant, some use a CLI default). Read first; write second.

## Implementation guidance

### General migration pattern

**Pattern A — Module-level constant**:

Before:
```python
VIKUNJA_BASE_URL = "https://office2.tail0f5f56.ts.net/api/v1"
```

After:
```python
from scripts.common.vikunja_config import get_vikunja_base_url
VIKUNJA_BASE_URL = get_vikunja_base_url()
```

Note: `get_vikunja_base_url()` returns the URL with a trailing slash; if the existing code does `f"{VIKUNJA_BASE_URL}/tasks/..."`, the joined URL will have a double slash. Fix the existing code to use `f"{VIKUNJA_BASE_URL}tasks/..."` (no leading slash on the path) — or strip the trailing slash if that's the touchpoint's convention.

**Pattern B — CLI argparse default**:

Before:
```python
parser.add_argument("--vikunja-base-url", default="https://office2.tail0f5f56.ts.net/api/v1")
```

After:
```python
parser.add_argument("--vikunja-base-url", default=get_vikunja_base_url())
```

Or with lazy evaluation (preferred — avoids reading the config when the user provides `--vikunja-base-url` explicitly):

```python
parser.add_argument("--vikunja-base-url", default=None)
args = parser.parse_args()
if args.vikunja_base_url is None:
    args.vikunja_base_url = get_vikunja_base_url()
```

**Pattern C — Function-internal computation**:

Some scripts compute the URL inside a function. Replace the literal with `get_vikunja_base_url()` at the function-internal location. Don't introduce a module-level constant if the existing code doesn't have one.

### Subtask T018: Migrate `scripts/habits/query_active_habits_v2.py`

**Steps**:

1. Read `scripts/habits/query_active_habits_v2.py` — identify the URL constant or argparse default.
2. Add import: `from scripts.common.vikunja_config import get_vikunja_base_url`.
3. Replace the literal URL per Pattern A/B/C above.
4. Run the touchpoint's existing test (`pytest tests/habits/test_query_active_habits_v2.py` — verify the file name; if different, run the appropriate test).
5. Verify NFR-006: `grep -n "office2.tail0f5f56.ts.net\|100.92.197.90:3456" scripts/habits/query_active_habits_v2.py` returns zero hits.

**Files**: `scripts/habits/query_active_habits_v2.py`

**Validation**:
- [ ] Import added
- [ ] URL constant/default replaced
- [ ] Touchpoint test passes
- [ ] NFR-006 grep clean for this file

### Subtask T019: Migrate `scripts/habits/morning_checkin_list.py`

Repeat the same pattern for `scripts/habits/morning_checkin_list.py`.

**Special note**: this touchpoint runs in the morning check-in cron path. The post-WP05 deploy + next 7:05 ET cron is the production regression check.

### Subtask T020: Migrate `scripts/habits/set_due_dates.py`

Repeat. **Special note**: this file has TWO HTTP usages — a cache-only GET via `read_cached_tasks` (from #519) AND a retained `_http_put` for the PUT phase. Both must read the URL from the helper. The `_http_put` function should accept the base URL as a parameter; if it currently hardcodes a constant, that's the migration target.

### Subtask T021: Migrate `scripts/habits/reconcile_completions.py`

Repeat for `scripts/habits/reconcile_completions.py`.

### Subtask T022: Migrate `scripts/escalation/reconcile_completions.py`

Repeat for `scripts/escalation/reconcile_completions.py`.

### Subtask T023: Migrate `scripts/enrichment/reconcile_completions.py`

Repeat for `scripts/enrichment/reconcile_completions.py`.

**Special note**: this file has THREE HTTP usages — a cache-only GET via `read_cached_tasks` (from #519), a retained `_http_get` for `_fetch_comments` (TP-12 scope correction), AND any task-state retrievals that were retained. Verify all three read the URL from the helper.

### Subtask T024: Migrate `scripts/sync/driver.py` CLI default

**Steps**:

1. Read `scripts/sync/driver.py` — identify the `--vikunja-base-url` argparse default.
2. Add import: `from scripts.common.vikunja_config import get_vikunja_base_url`.
3. Replace the literal URL with `get_vikunja_base_url()` (Pattern B preferred — explicit CLI override should bypass the helper).
4. Verify driver tests pass: `pytest tests/sync/test_driver.py` (if it exists; otherwise the integration tests cover this).

**Files**: `scripts/sync/driver.py`

**Validation**:
- [ ] CLI default reads from `get_vikunja_base_url()`
- [ ] Explicit `--vikunja-base-url=<url>` argument still overrides
- [ ] Driver invocation in dry-run mode succeeds

### Subtask T025: NFR-006 grep verification

**Purpose**: confirm the global NFR-006 success criterion.

**Steps**:

Run from the repo root:

```bash
grep -rn "office2.tail0f5f56.ts.net\|100.92.197.90:3456" scripts/ --include="*.py" | grep -v __pycache__
```

**Expected hits**:
1. `scripts/common/vikunja_config.py` — the `_CANONICAL_FILE_PATH` constant or any docstring example (acceptable)
2. The 6 FR-010 exclusions (one-off setup/utility scripts; each line should mention the file is in the exclusion list):
   - `scripts/vikunja/provision_felix_bot.py`
   - `scripts/vikunja/validate_felix_bot.py`
   - `scripts/vikunja/swap_vikunja_secrets.py`
   - `scripts/vikunja/revoke_kent_tokens.py`
   - `scripts/vikunja/setup_goals.py`
   - `scripts/habits/migrate_schedule.py`
   - `scripts/habits/query_active_habits.py` (legacy v1, superseded)
   - `scripts/security/credential_health_check/vikunja_writer.py`

**Expected NO hits** in:
- `scripts/habits/query_active_habits_v2.py`
- `scripts/habits/morning_checkin_list.py`
- `scripts/habits/set_due_dates.py`
- `scripts/habits/reconcile_completions.py`
- `scripts/escalation/reconcile_completions.py`
- `scripts/enrichment/reconcile_completions.py`
- `scripts/sync/` (all driver code)

Document the verification output in the WP's PR description.

**Files**: no file changes — verification step only.

**Validation**:
- [ ] grep output matches expected (only config helper + 6 FR-010 exclusions)
- [ ] Output captured in PR description for reviewer reference

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per computed lane from `lanes.json` (depends on WP01). Can run in parallel with WP02, WP03, WP04 once WP01 approves.

## Test Strategy

Per touchpoint: the existing test suite from #519 (e.g., `tests/habits/test_*.py`) provides regression coverage. If a test mocks the URL constant, update the mock to mock `get_vikunja_base_url()` instead.

No net-new unit tests required for this WP — the touchpoint behavior is unchanged; only the URL source moves.

The NFR-006 grep is the structural success criterion for this WP.

## Definition of Done

- [ ] All 7 files (6 touchpoints + driver.py) read URL from `get_vikunja_base_url()`
- [ ] Each touchpoint's existing test suite passes unchanged
- [ ] NFR-006 grep verification documented; output matches expected
- [ ] No changes to files outside `owned_files`
- [ ] No hardcoded URL strings in runtime-path scripts

## Risks

- **Trailing slash mismatch**: `get_vikunja_base_url()` returns URL with trailing slash; existing code may have `f"{URL}/path"` which becomes `https://...//path`. Fix incrementally per touchpoint.
- **Per memory `feedback_wp_prompts_grep_codebase`**: read each file's actual URL-handling pattern BEFORE writing the migration. Don't assume uniformity.
- **CLI default eager vs lazy evaluation**: argparse defaults are evaluated at parser construction. If `get_vikunja_base_url()` raises `VikunjaConfigError` because the config isn't deployed, the script fails at startup. The lazy pattern (default=None, resolve after parse_args) avoids this for `--vikunja-base-url=<url>` explicit-override paths.
- **Test mocks**: existing tests may patch `urllib.urlopen` directly or mock the URL constant. Updating mocks to mock `get_vikunja_base_url()` requires a small per-test fix.

## Reviewer Guidance

The reviewer should validate:

1. **All 7 files import and call `get_vikunja_base_url()`** — no hardcoded URLs remain.
2. **NFR-006 grep output is documented** in the WP's PR (or here) and matches the expected exclusion pattern.
3. **Each touchpoint test still passes** — no behavioral regression.
4. **Trailing-slash handling is consistent** per touchpoint (verify by tracing the URL concatenation pattern).
5. **CLI default lazy-pattern**: prefer the lazy pattern for `--vikunja-base-url` to allow explicit overrides without requiring the config file.
6. **No changes leaked into files outside `owned_files`** (the 7 listed files + 0 others).
7. **The 6 FR-010 exclusions are NOT modified** in this WP (they continue to use their existing URL handling).

## Implementation command

```bash
spec-kitty agent action implement WP05 --mission felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7 --agent <tool>:<model>:<profile>:<role>
```

## Next steps after WP05 approval

- WP06 (architecture docs) can begin once WP04 also approves.
- All consumer-side work is done; the post-merge deploy step (creating the URL config file on office2) is the operational completion.

## Activity Log

- 2026-06-05T19:18:47Z – claude:sonnet:implementer:implementer – shell_pid=80769 – Started implementation via action command
- 2026-06-05T19:29:22Z – claude:sonnet:implementer:implementer – shell_pid=80769 – Ready for review: 4 files migrated (set_due_dates.py, escalation/reconcile_completions.py, enrichment/reconcile_completions.py, sync/driver.py); 3 files already clean (query_active_habits_v2.py, morning_checkin_list.py, habits/reconcile_completions.py); NFR-006 grep verified clean for all 7 owned files; 209 tests pass; autouse mock fixtures added to 4 test files
