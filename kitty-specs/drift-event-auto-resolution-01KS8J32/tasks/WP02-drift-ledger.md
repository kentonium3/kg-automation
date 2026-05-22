---
work_package_id: WP02
title: drift_ledger module
dependencies: []
requirement_refs:
- FR-010
- NFR-001
- NFR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T19:45:00+00:00'
subtasks:
- T008
- T009
- T010
- T011
- T012
- T013
history: []
authoritative_surface: scripts/doc_audit/output/
execution_mode: code_change
mission_id: 01KS8J321F8KE7369R3DA02329
mission_slug: drift-event-auto-resolution-01KS8J32
owned_files:
- scripts/doc_audit/output/drift_ledger.py
- tests/doc_audit/output/test_drift_ledger.py
tags: []
---

# WP02 — drift_ledger module

## Objective

Implement the append-only JSONL ledger that captures verdict + outcome per drift event. Powers the NFR-001 triage rate metric and operator observability. Co-located with the existing drift-events file at `/data/services/security-monitor/logs/drift-events-ledger.jsonl`.

## Context

- **Spec**: FR-010, NFR-001 (triage rate ≤30%), NFR-005 (reliability ≥98%)
- **Plan**: D4 (ledger schema)
- **Data model**: E3 (AuditLedgerEntry)
- **Schema contract**: [contracts/ledger-schema.md](../contracts/ledger-schema.md)
- **CLI contract**: [contracts/cli.md](../contracts/cli.md) — drift_ledger CLI
- **Branching**: planning_base=`main`, merge_target=`main`.

## Subtasks

### T008 — Module skeleton + AuditLedgerEntry dataclass

**Purpose**: Establish module surface + entity.

**Steps**:

1. Create `scripts/doc_audit/output/drift_ledger.py` with module docstring.
2. Imports: stdlib `json`, `os`, `tempfile`, `dataclasses`, `pathlib`, `typing`, `datetime`, `argparse`, `sys`.
3. Module constants:
   ```python
   DEFAULT_LEDGER_PATH = Path("/data/services/security-monitor/logs/drift-events-ledger.jsonl")
   SCHEMA_VERSION = 1
   VALID_VERDICTS = frozenset({"PROPOSED_EDIT", "JUDGMENT_REQUIRED", "NO_CHANGE_NEEDED", "RETRY_EXHAUSTED"})
   VALID_OUTCOMES = frozenset({"auto_committed", "pr_filed", "issue_filed", "auto_closed", "retry_exhausted"})
   VALID_TIER_OUTCOMES = frozenset({"tier_a", "tier_b", "judgment"})  # plus None
   ```
4. Define `AuditLedgerEntry` frozen dataclass per E3. Field order MUST match the contracts/ledger-schema.md table for deterministic serialization.

**Files**: `scripts/doc_audit/output/drift_ledger.py` (~80 lines so far).

**Validation**:
- [ ] `python3 -c "from scripts.doc_audit.output.drift_ledger import AuditLedgerEntry, append, read_window, compute_triage_rate; print('ok')"` prints `ok`
- [ ] Dataclass is `frozen=True`

---

### T009 — append() function

**Purpose**: Atomic, single-line JSONL append.

**Steps**:

1. `_entry_to_json(entry: AuditLedgerEntry) -> str`:
   - Build dict in field order (per contracts/ledger-schema.md table)
   - Serialize via `json.dumps(d, sort_keys=False, ensure_ascii=True, separators=(",", ":"))` — compact form, deterministic
   - No trailing whitespace
2. `append(entry: AuditLedgerEntry, *, ledger_path: Path = DEFAULT_LEDGER_PATH) -> None`:
   - Validate entry (assert verdict ∈ VALID_VERDICTS, outcome ∈ VALID_OUTCOMES, confidence in [0,1] or None, etc.)
   - Ensure parent dir exists (create if not)
   - Open ledger_path in "a" mode (append)
   - Write `json_line + "\n"`
   - `flush()` + `os.fsync(f.fileno())` for durability
3. The "tempfile + rename" pattern is NOT used for steady-state appends (single-writer; appends are O(1) and OS-atomic for small lines). It IS used in T010 below for any read-then-rewrite operations (none in v1, but documented).

**Files**: same module, +~60 lines.

**Validation**:
- [ ] Test: round-trip serialize → file → parse produces identical entry
- [ ] Test: malformed entry (verdict not in set) raises ValueError BEFORE write
- [ ] Manual: tail the file after several appends; entries are on separate lines

---

### T010 — read_window() function

**Purpose**: Efficient tail-from-end read for query CLIs.

**Steps**:

1. `read_window(*, ledger_path: Path = DEFAULT_LEDGER_PATH, days: int = 7) -> list[AuditLedgerEntry]`:
   - If file doesn't exist: return `[]`
   - Compute cutoff: `datetime.now(timezone.utc) - timedelta(days=days)`
   - Tail-scan strategy: seek to end, read in 64KB chunks backwards, splitting on `\n`, parsing each complete line
   - Stop when finding an entry with `timestamp_utc` older than cutoff (lines are ordered by write time)
   - Reverse the accumulated list before return so order is chronological
2. `_parse_json_line(line: str) -> AuditLedgerEntry` — strict deserialize; ignore unknown fields for forward-compat.
3. Edge cases: empty file returns `[]`; corrupt line is logged + skipped (don't fail the whole window).

**Files**: same module, +~80 lines.

**Validation**:
- [ ] Test: 1MB ledger with 10K entries; read_window(days=1) returns subset in <100ms
- [ ] Test: corrupt line is skipped without raising
- [ ] Test: empty file returns []
- [ ] Test: window cutoff is honored to the second

---

### T011 — compute_triage_rate() + helpers

**Purpose**: Implement the NFR-001 metric query.

**Steps**:

1. `compute_triage_rate(*, ledger_path: Path = DEFAULT_LEDGER_PATH, days: int = 7) -> float`:
   ```python
   entries = read_window(ledger_path=ledger_path, days=days)
   total = len(entries)
   if total == 0:
       return 0.0
   escalated = sum(1 for e in entries if e.verdict == "JUDGMENT_REQUIRED")
   return escalated / total
   ```
2. `compute_reliability(*, ledger_path=..., days=7) -> float` — NFR-005 metric:
   ```python
   entries = read_window(...)
   total = len(entries)
   if total == 0:
       return 1.0
   exhausted = sum(1 for e in entries if e.verdict == "RETRY_EXHAUSTED")
   return 1.0 - (exhausted / total)
   ```
3. `compute_outcome_breakdown(*, ledger_path=..., days=7) -> dict[str, int]` — counts by outcome.

**Files**: same module, +~50 lines.

**Validation**:
- [ ] Test: fixture ledger with known outcomes produces expected ratios
- [ ] Test: empty ledger returns 0.0 / 1.0 / {} appropriately

---

### T012 — CLI surface

**Purpose**: Per contracts/cli.md drift_ledger CLI section.

**Steps**:

1. `def main(argv=None) -> int` with argparse subparsers:
   - `summary` — print outcome breakdown table for last N days
   - `tail` — pretty-print last 10 ledger entries
   - `triage-rate` — print `count(JUDGMENT_REQUIRED) / count(*)` as percentage
2. Shared flags: `--ledger-path <path>`, `--days <int>` (default 7).
3. Output format: tabular for `summary`, JSON for `tail`, percentage string for `triage-rate`.
4. Exit codes per contracts/cli.md: 0 / 1 (ledger unreadable) / 3 (bad flag/subcommand).
5. `if __name__ == "__main__": sys.exit(main())`.

**Files**: same module, +~60 lines.

**Validation**:
- [ ] `python3 -m scripts.doc_audit.output.drift_ledger --help` exits 0
- [ ] `python3 -m scripts.doc_audit.output.drift_ledger summary --help` exits 0
- [ ] All 3 subcommands exit 0 against a fixture ledger

---

### T013 — Tests

**Purpose**: ≥85% coverage; verify atomicity, round-trip, window correctness.

**Steps**:

1. Create `tests/doc_audit/output/test_drift_ledger.py`.
2. Test cases:
   - **Round-trip serialization**: build AuditLedgerEntry, append to tmp file, read back via read_window, assert equal.
   - **Field order**: tail the appended line; parse as JSON ordered dict; assert keys appear in the contracted order.
   - **Atomic append (single-writer)**: simulate two consecutive appends; assert both lines present, no truncation.
   - **Schema validation on append**: invalid verdict → ValueError. Invalid outcome → ValueError. Invalid confidence (1.5) → ValueError. RETRY_EXHAUSTED with non-None confidence → ValueError (None required).
   - **read_window cutoff**: build fixture ledger with entries timestamped at -1d, -3d, -10d; assert `days=7` returns only first two.
   - **read_window empty file**: returns [].
   - **read_window with corrupt line**: assert the corrupt line is skipped, valid lines still returned, no exception.
   - **read_window large file**: synthesize 10K entries; assert `days=1` returns subset in reasonable time (<2s).
   - **compute_triage_rate**: fixture with 4 JUDGMENT_REQUIRED out of 10 total → 0.40.
   - **compute_triage_rate empty**: returns 0.0.
   - **compute_reliability**: fixture with 1 RETRY_EXHAUSTED out of 100 → 0.99.
   - **compute_outcome_breakdown**: fixture with mixed outcomes → expected dict.
   - **CLI exit 0 summary**: invoke main with fixture ledger; assert returns 0.
   - **CLI exit 1 missing ledger**: invoke main with non-existent path; assert returns 1.
   - **CLI exit 3 bad subcommand**: invoke main with unknown subcommand; assert returns 3.

**Files**: `tests/doc_audit/output/test_drift_ledger.py` (~280 lines, ~15 tests).

**Validation**:
- [ ] `pytest tests/doc_audit/output/test_drift_ledger.py -v` ≥85% coverage
- [ ] No filesystem state leaks between tests (use tmp_path)

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

pytest with tmp_path-based ledger files. No external dependencies. ≥85% coverage.

## Definition of Done

- [ ] All 6 subtasks complete.
- [ ] `pytest tests/doc_audit/output/test_drift_ledger.py -v` ≥85%.
- [ ] CLI smoke: all 3 subcommands run against a fixture ledger.
- [ ] No regression on existing `scripts/doc_audit/output/activity_log.py`.

## Risks

- **Tail-scan performance**: read_window must handle large files efficiently. Worst-case fallback: linear scan from start (acceptable for first version).
- **Field ordering**: `json.dumps` with `sort_keys=False` preserves dict insertion order in Python 3.7+. Pin Python version expectation in tests.
- **Concurrent writes**: single-writer assumed (one cron job at a time). Document this in module docstring.

## Reviewer Guidance

1. Verify atomic append (flush + fsync) is in place.
2. Verify the JSON output matches contracts/ledger-schema.md field order exactly.
3. Verify read_window doesn't materialize the whole file for large ledgers.
4. Verify validate-on-append catches all the documented schema violations.

## Implementation Command

```bash
spec-kitty agent action implement WP02 --mission drift-event-auto-resolution-01KS8J32 --agent claude:opus:python-implementer:implementer
```
