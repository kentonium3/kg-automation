---
work_package_id: WP03
title: 'set_due_dates.py + tests with #112 regression-prevention'
dependencies:
- WP01
requirement_refs:
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Per-lane worktree from finalize-tasks lanes.json; branches off WP01's merged base.
subtasks:
- T009
- T010
- T011
history:
- event: created
  at: '2026-05-15T17:15:12Z'
  by: spec-kitty.tasks
  note: WP03 prompt generated
authoritative_surface: scripts/habits/set_due_dates.py
execution_mode: code_change
mission_slug: habits-checkin-d6-extract-01KRNV46
owned_files:
- scripts/habits/set_due_dates.py
- tests/habits/test_set_due_dates.py
tags: []
---

# WP03 — set_due_dates.py + tests with #112 regression-prevention

## Objective

Ship the due_date-setting helper that PUTs `due_date` to end-of-day Eastern Time on a list of habit IDs. This helper is the LOAD-BEARING surface for #112 regression-prevention — the bug that caused habits to appear overdue at 7:05 AM because the due_date was midnight ET (already in the past). The fix is end-of-day ET (`23:59:59` with explicit `-04:00` or `-05:00` offset).

The helper must reject any `--iso-eod-et` value ending with `Z` (UTC) at startup — that would re-introduce the bug.

## Context

- **Spec**: [`spec.md`](../spec.md) — FR-003 + NFR-004 (TZ correctness) + NFR-007 (partial-failure resilience)
- **Contract**: [`contracts/set_due_dates.md`](../contracts/set_due_dates.md) — full CLI + I/O + 8 test scenarios
- **Historical context**: issue #112 (midnight anchor bug). NEVER REGRESS THIS.
- **Reference precedent**: `vikunja_writer.py` has `render_due_date_iso(due: date) -> str` doing the same ET-end-of-day formatting. Per C-003, duplicate the pattern in-line; don't extract a library.

## Subtask details

### T009 — Implement `scripts/habits/set_due_dates.py`

**Purpose**: PUT `due_date` to each habit ID in input list with end-of-day-ET ISO timestamp; continue on per-habit failure; aggregate results.

**Steps**:

1. Create `scripts/habits/set_due_dates.py` per [`contracts/set_due_dates.md`](../contracts/set_due_dates.md).
2. Required imports: `argparse`, `json`, `re`, `sys`, `urllib.request`, `urllib.error`, `pathlib.Path`.
3. CLI: `--habit-ids` (comma-separated ints), `--iso-eod-et` (string), `--vikunja-token-path`, `--vikunja-base-url`, `--dry-run`.
4. **CRITICAL — Z-suffix rejection** (NFR-004; #112 regression-prevention):
   ```python
   ISO_EOD_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T23:59:59[+-]\d{2}:\d{2}$")

   def validate_iso_eod_et(value: str) -> None:
       if value.endswith("Z"):
           print("ERROR: --iso-eod-et ends with 'Z' (UTC). "
                 "Issue #112 forbids UTC due_date — must use explicit ET offset.",
                 file=sys.stderr)
           sys.exit(2)
       if not ISO_EOD_PATTERN.match(value):
           print(f"ERROR: --iso-eod-et '{value}' does not match expected "
                 f"format YYYY-MM-DDT23:59:59<+/-NN:NN>", file=sys.stderr)
           sys.exit(2)
   ```
5. Helper internals (in-line per C-003):
   - `_load_token(path)` — same pattern as WP02
   - `_vikunja_put(base_url, token, path, body)` — PUT request with bearer auth, returns parsed response or raises on non-2xx
6. Main loop:
   - Parse habit IDs from comma-separated string. Empty input → exit 0 with empty result.
   - For each ID:
     - Construct PUT body: `{"due_date": "<iso_eod_et>"}`
     - In `--dry-run`: print intent to stderr, don't call API, add ID to `succeeded`.
     - Otherwise: call `_vikunja_put`. On success, add to `succeeded`. On failure, log to stderr and add `{"id": id, "reason": str(e)}` to `failed`.
   - Output JSON object + SUMMARY line.
   - Exit 0 if `failed` empty, else exit 1.
7. Module docstring references FR-003, NFR-004, NFR-007, and issue #112.

**Files**:
- `scripts/habits/set_due_dates.py` (NEW, ~150 lines)

**Validation**:
- [ ] `--iso-eod-et 2026-05-15T23:59:59Z` exits 2 with regression-prevention message
- [ ] `--iso-eod-et garbage` exits 2 with format-error message
- [ ] `--iso-eod-et 2026-05-15T23:59:59-04:00` accepted
- [ ] `--dry-run` makes no HTTP calls (verify by mocking and asserting call count == 0)
- [ ] Module docstring mentions #112 explicitly

---

### T010 — Write `tests/habits/test_set_due_dates.py`

**Purpose**: 8 tests covering the contract's test table including the all-important Z-suffix rejection.

**Steps**:

1. Create `tests/habits/test_set_due_dates.py` following the contract's test table.
2. Same mocking pattern as WP02: helper structured as both CLI and importable module; patch `urllib.request.urlopen`.
3. Implement these 8 tests:
   - `test_happy_path_all_succeed` — mock PUT 200 for all 3 habit IDs; exit 0; `succeeded` has 3, `failed` empty
   - `test_partial_failure` — mock PUT 200 for 2, PUT 500 for 1; exit 1; `succeeded` has 2, `failed` has 1
   - `test_all_fail` — mock PUT 500 for all; exit 1; `succeeded` empty
   - `test_dry_run_makes_no_calls` — `--dry-run` flag; mock asserts `urlopen.call_count == 0`; exit 0
   - `test_z_suffix_rejected` — `--iso-eod-et 2026-05-15T23:59:59Z`; exit 2 with stderr containing "#112"
   - `test_malformed_iso` — `--iso-eod-et garbage`; exit 2
   - `test_idempotency` — mock PUT 200; run helper twice with same input; result is identical (in real Vikunja, PUT to same value is idempotent; this just verifies the helper doesn't introduce non-determinism)
   - `test_empty_habit_ids` — `--habit-ids ""`; exit 0 with empty arrays

**Files**:
- `tests/habits/test_set_due_dates.py` (NEW, ~220 lines)

**Validation**:
- [ ] All 8 tests written and pass
- [ ] `test_z_suffix_rejected` is EXPLICIT — it's the #112 regression backstop
- [ ] `test_dry_run_makes_no_calls` asserts call count == 0 (not just exit code)
- [ ] No real Vikunja API calls during test run

---

### T011 — Local validation in `--dry-run` mode

**Purpose**: Confirm helper works against the real Vikunja API surface in `--dry-run` only (we don't want to mutate production Vikunja state during development validation).

**Steps**:

1. Use the chain from previous WPs:
   ```bash
   # Resolve today's context
   TODAY=$(python3 scripts/habits/compute_today.py)
   ISO_EOD=$(echo "$TODAY" | head -1 | jq -r .iso_eod_et)

   # Get today's scheduled habit IDs (assumes WP02 is merged)
   HABITS=$(python3 scripts/habits/query_active_habits.py \
       --day "$(echo "$TODAY" | head -1 | jq -r .day)" \
       --vikunja-token-path /tmp/vikunja-token-readonly)
   IDS=$(echo "$HABITS" | head -1 | jq -r '[.habits[].id] | join(",")')

   # DRY-RUN the set_due_dates helper
   python3 scripts/habits/set_due_dates.py \
       --habit-ids "$IDS" \
       --iso-eod-et "$ISO_EOD" \
       --dry-run \
       --vikunja-token-path /tmp/vikunja-token-readonly
   ```
2. Verify the helper reports the would-be PUT calls without making them.
3. Run pytest:
   ```bash
   pytest tests/habits/test_set_due_dates.py -v
   ```
4. (Optional, careful) Run helper WITHOUT `--dry-run` against a single habit ID to verify the real PUT path works. If you do this, only use a habit you control and verify the due_date is the expected end-of-day-ET value afterwards in the Vikunja UI.

**Files**: No new files.

**Validation**:
- [ ] `--dry-run` invocation reports intent for each habit ID and exits 0
- [ ] All 8 tests pass
- [ ] If real PUT was tested: due_date in Vikunja UI matches end-of-day-ET expectation (no `Z` suffix, no off-by-one)

---

## Branch Strategy

- **Planning base**: `main`
- **Merge target**: `main`
- **Execution workspace**: Per-lane worktree from `lanes.json`, branched from WP01's merged state.

## Test strategy

Tests REQUIRED (NFR-005; criticality gate from D6 § 4 — TZ math + state mutation = both required-clauses fire). The Z-suffix rejection test is the #112 regression-prevention backstop and is MANDATORY.

## Definition of Done

- [ ] T009: helper implemented; passes Z-suffix rejection self-test
- [ ] T010: 8 tests passing
- [ ] T011: local validation in `--dry-run` mode green
- [ ] Module docstring mentions #112 issue
- [ ] Validation regex for `--iso-eod-et` is in-line (not deferred to a library — per C-003)
- [ ] All owned_files committed
- [ ] Mark subtasks done: `spec-kitty agent tasks mark-status T009 T010 T011 --status done`
- [ ] Move to for_review: `spec-kitty agent tasks move-task WP03 --to for_review --note "set_due_dates.py ready — Z-suffix rejection in place; 8 tests passing"`

## Risks

- **#112 regression**: If the Z-suffix rejection is somehow bypassed (e.g., implementer adds a "convenience" auto-conversion from UTC to ET), Kent's habits will reappear as overdue. The contract explicitly forbids auto-conversion — the helper REJECTS bad input rather than fixing it. This must be preserved.
- **Partial-failure semantics**: agent's failure-handling depends on exit code 1 with non-empty `succeeded` array. If the helper just exits 0 on per-habit failures (silently dropping them), the agent has no way to detect the partial state. Tests must verify exit code 1 in partial-failure case.
- **Mutating production Vikunja during T011**: avoid this unless using a known-safe habit ID. `--dry-run` is the development default.

## Reviewer guidance (for Codex)

Verify:

1. **Z-suffix rejection**: regex pattern is `r"^\d{4}-\d{2}-\d{2}T23:59:59[+-]\d{2}:\d{2}$"` (or equivalent — must require `[+-]NN:NN` and disallow `Z`).
2. The rejection happens at startup BEFORE any HTTP calls. Test case `test_z_suffix_rejected` must reach exit 2 with zero `urlopen` calls.
3. **Partial-failure exit code**: explicit assertion in `test_partial_failure` that exit code is 1 AND `succeeded` is non-empty AND `failed` is non-empty.
4. **No auto-conversion**: helper does NOT attempt to convert UTC to ET if given a `Z` suffix. It REJECTS.
5. **`--dry-run` is no-op**: verify `urllib.request.urlopen` is never called when `--dry-run` is set.
6. **Issue #112 mentioned in module docstring** so future readers understand the constraint's origin.

Reject if:
- Z-suffix rejection is missing or weakened (e.g., warns instead of exits 2)
- Helper auto-converts UTC to ET (this defeats the regression-prevention)
- Partial-failure case exits 0 (loses the signal to the agent)
- `--dry-run` makes any HTTP calls
