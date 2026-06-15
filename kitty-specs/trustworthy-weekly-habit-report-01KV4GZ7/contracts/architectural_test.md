# Contract: `tests/architectural/test_habits_history_canonical_read.py`

**Purpose**: Ratchet the canonical-read rule. Fail the build if any `scripts/habits/*.py` script imports `VikunjaClient` for completion-history purposes. Allow current-state queries via an explicit file-level allowlist.

## Test surface

### 1. Main scan

For each Python file matching `scripts/habits/*.py`:

1. Read the file as text.
2. AST-parse it.
3. Walk all `Import` and `ImportFrom` nodes.
4. Detect imports of `VikunjaClient`:
   - `from scripts.common.vikunja_client import VikunjaClient` (canonical)
   - `from scripts.common.vikunja_client import VikunjaError, VikunjaClient` (multi-name)
   - `import scripts.common.vikunja_client` followed by `VikunjaClient` symbol access
   - Aliases (`as ...`)
5. If the file's basename is in `VIKUNJA_CURRENT_STATE_ALLOWLIST`, skip.
6. Otherwise fail the test with `<file_path>:<lineno>: <import line> — VikunjaClient import not allowlisted; completion history must read habits-history.jsonl via scripts/habits/history.py`.

### 2. Negative-control test

Verify the scanner DOES fire by constructing an in-memory or temp-file fixture with `from scripts.common.vikunja_client import VikunjaClient` and asserting the scanner produces a violation containing the fixture path and the import line.

### 3. Allowlist sanity test

Verify every entry in `VIKUNJA_CURRENT_STATE_ALLOWLIST` corresponds to an actually-existing file under `scripts/habits/`. (Stale allowlist entries from removed files should be caught at this layer.)

## Determinism + performance

- NFR-002: test completes ≤5 seconds standalone. AST-parsing 10 small Python files is sub-second.
- NFR-003: failure messages name the specific file and line of the offending import.

## Allowlist contents at mission completion

After IC-02 lands:

```python
VIKUNJA_CURRENT_STATE_ALLOWLIST: frozenset[str] = frozenset({
    "query_active_habits_v2.py",
    "exclude_completed_v2.py",
    "morning_checkin_list.py",
    "record_completion.py",
    "sweeper.py",
    "set_due_dates.py",
    "identify_workout_task.py",
    "backfill_jsonl_from_comments.py",
    "query_active_habits_weekly.py",
    # query_active_habits_weekly.py STAYS because it still uses VikunjaClient
    # for current-state habit list and classification (titles + repeat_after).
    # It does NOT read done_at for completion history — that path was removed.
})
```

(Concrete allowlist is whatever set of habits scripts currently exist and legitimately need current-state Vikunja access at IC-03 implementation time. WP authoring will enumerate the actual set.)

## Discovery / scope

- Test file location: `tests/architectural/test_habits_history_canonical_read.py`.
- Runs as part of default pytest collection. No special markers needed.
- Test class name: `TestHabitsHistoryCanonicalRead` (or function-based — implementer's choice).

## What this test does NOT do

- It does NOT scan for runtime calls to `VikunjaClient` methods (only imports). A file that imports the class and never calls `done_at`-related methods is still flagged if not allowlisted. Rationale: imports are static and grep-able; the rule is simpler to enforce, and the allowlist forces a code-review conversation when someone wants to add a new current-state caller.
- It does NOT enforce anything about `scripts/common/vikunja_client.py` itself. That file stays as the single canonical Vikunja client.
- It does NOT enforce import rules for any other directory (e.g. `scripts/inbox/`, `scripts/openclaw/agents/`). The rule is scoped to habits because that's where the bug class lived.
