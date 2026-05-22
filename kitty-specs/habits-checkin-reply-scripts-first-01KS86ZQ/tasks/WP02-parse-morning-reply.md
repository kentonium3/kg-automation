---
work_package_id: WP02
title: parse_morning_reply helper
dependencies:
- WP01
requirement_refs:
- FR-003
- FR-004
- FR-005
- FR-008
- FR-009
- FR-010
- NFR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T16:30:00+00:00'
subtasks:
- T005
- T006
- T007
- T008
agent: "claude:opus:python-implementer:implementer"
shell_pid: "72115"
history:
- at: '2026-05-22T16:30:00+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/habits/
execution_mode: code_change
mission_id: 01KS86ZQE8GSZ77ZSGSSQMN08K
mission_slug: habits-checkin-reply-scripts-first-01KS86ZQ
owned_files:
- scripts/habits/parse_morning_reply.py
- tests/habits/test_parse_morning_reply.py
- tests/habits/fixtures/morning-checkin-2026-05-22.json
tags: []
---

# WP02 — parse_morning_reply helper

## Objective

Implement the deterministic reply parser. Single most important guarantee: byte-determinism (same inputs → same outputs every time). SC-002 is the load-bearing acceptance test — the 2026-05-22 fixture from #371 must produce exactly the intent Kent expressed.

## Context

- **Spec**: FR-003 (parser output), FR-004 (3-tier matching), FR-005 (special tokens), FR-008 (no live Vikunja), FR-009 (hard-fail on missing list), FR-010 (record_completion contract untouched), NFR-001 (byte-determinism)
- **Plan**: Phase 0 D3 (match rules), D7 (special tokens), D8 (range out of scope), D9 (idempotency)
- **Data model**: Entity 2 (parser output schema), Entity 6 (test fixture)
- **API contract**: `contracts/api.md` — `parse_reply`, `load_morning_list`, `ParseResult` + dataclasses
- **CLI contract**: `contracts/cli.md` — flags, exit codes 0/1/3/4/5
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T005 — Module skeleton + dataclasses

**Purpose**: Establish the module + the ParseResult shape per data-model Entity 2.

**Steps**:

1. Create `scripts/habits/parse_morning_reply.py` with module docstring.
2. Imports: stdlib only (`argparse`, `dataclasses`, `json`, `pathlib`, `re`, `sys`, `typing`, `datetime`, `zoneinfo`).
3. Module constants (mirror WP01):
   ```python
   DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/habits")
   LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")
   SCHEMA_VERSION = 1
   ```
4. Define dataclasses per contracts/api.md:
   - `ParseTuple` (frozen): `task_id`, `state` Literal, `matched_via` Literal, `position: Optional[int] = None`
   - `JudgmentItem` (frozen): `token`, `candidate_task_ids: list[int]`, `candidate_titles: list[str]`, `inferred_state` Literal
   - `ParseError` (frozen): `type` Literal, `detail: str`
   - `ParseResult` (frozen): `schema_version`, `reply_text`, `morning_list_path`, `tuples: list[ParseTuple]`, `judgment_required: list[JudgmentItem]`, `errors: list[ParseError]`
5. Import `MorningList` + `MorningListHabit` from `scripts.habits.morning_checkin_list` so the parser shares the shape (but parser does NOT call the build/persist functions).

**Files**: `scripts/habits/parse_morning_reply.py` (~100 lines so far).

**Validation**:
- [ ] No third-party imports.
- [ ] Dataclasses match Entity 2 verbatim.
- [ ] Import smoke: `python3 -c "from scripts.habits.parse_morning_reply import ParseResult, ParseTuple, JudgmentItem, ParseError; print('ok')"` → `ok`.

---

### T006 — parse_reply core logic

**Purpose**: The deterministic parser per research D3 + D7.

**Steps**:

1. Special-token detection (FIRST pass, before tokenization):
   - All-done family: `r"\b(all\s+done|done\s+with\s+everything|everything\s+done|all\s+complete)\b"` (case-insensitive)
   - All-skipped family: `r"\b(skipping\s+everything|skipped\s+all|none\s+done|nothing\s+done)\b"`
   - On match: emit tuples for every position in the morning list with the matched state. Return ParseResult; skip per-token parsing.
2. Tokenization (if no special-token match):
   - Split the reply into CLAUSES on connectives (`","`, `";"`, `" and "`, `" but "`). Each clause has a verb (done/skipped/incomplete/not done) and a set of identifier tokens.
   - For each clause:
     - Determine the inferred state from the verb. Default: `complete` if "done"; `skipped` if "skip"/"skipped"/"skipping"; `incomplete` if "didn't"/"did not"/"incomplete".
     - Extract identifier-tokens: digits, words.
3. For each identifier-token:
   - **Number reference**: digit → look up in morning_list by position. If found, emit `ParseTuple(task_id, state, matched_via="position", position=N)`. If position out of range, emit `ParseError("invalid_token", "position N not in list")`.
   - **Exact title match (case-insensitive)**: compare token against `[h.title.lower() for h in morning_list.habits]`. Single match: emit `ParseTuple(matched_via="exact_title")`. No match: try substring next.
   - **Substring match (case-insensitive)**: collect all habits whose lowercased title contains the lowercased token. Single match: emit `ParseTuple(matched_via="substring")`. Multiple matches: emit `JudgmentItem(token, candidate_task_ids, candidate_titles, inferred_state=clause_state)`. Zero matches: emit `ParseError("unparseable_reply", f"token '{token}' didn't match any habit")`.
4. Return populated `ParseResult`.

**Files**: same module, +~250 lines.

**Validation**:
- [ ] All match paths covered by tests in T008.
- [ ] Function is pure (no I/O — caller passes the MorningList).
- [ ] Determinism: same inputs → same outputs (tested in T008).

---

### T007 — load_morning_list + CLI

**Purpose**: File I/O + CLI wrapper per contracts/cli.md.

**Steps**:

1. `load_morning_list(*, date: str, state_dir: Path) -> MorningList`:
   - Path: `state_dir / f"morning-checkin-{date}.json"`.
   - `open(path).read()` → `json.loads()`.
   - Validate schema: `schema_version`, `date`, `habits` present; each habit has `position`, `vikunja_task_id`, `title`.
   - Reconstruct `MorningList` dataclass from dict.
   - On FileNotFoundError: re-raise (caller maps to exit 4).
   - On JSON parse error or schema mismatch: raise ValueError (caller maps to exit 5).

2. `def main(argv=None) -> int` with argparse:
   - `--reply <text>` OR `--reply-file <path>` (exactly one required).
   - `--date <YYYY-MM-DD>` (default today-local).
   - `--state-dir <path>`.
3. Compute reply_text from `--reply` or by reading `--reply-file`.
4. Compute date (default `_today_local()` — share helper with WP01 or duplicate).
5. Load morning_list. Catch FileNotFoundError → exit 4. Catch ValueError → exit 5.
6. Call `parse_reply(reply_text=..., morning_list=...)`.
7. Emit ParseResult as JSON to stdout via `dataclasses.asdict` + json.dumps.
8. Exit 0 unless caught above.
9. `if __name__ == "__main__": sys.exit(main())`.

**Files**: same module, +~120 lines.

**Validation**:
- [ ] `python3 -m scripts.habits.parse_morning_reply --help` exits 0.
- [ ] Missing morning-list file → exit 4 with structured stderr.

---

### T008 — Tests including SC-002 fixture

**Purpose**: ≥85% coverage; SC-002 acceptance.

**Steps**:

1. Create `tests/habits/fixtures/morning-checkin-2026-05-22.json` with the 8-habit list from data-model Entity 6 (placeholder task_ids OK).
2. Create `tests/habits/test_parse_morning_reply.py`.
3. Test cases:
   - **SC-002 — the 2026-05-22 reply**: `parse_reply("Skipped 3,7,8 done", morning_list)` → assert tuples match exactly: positions 3, 7, 8 → `skipped`; positions 1, 2, 4, 5, 6 → `complete`.
   - **All-done special token**: `"all done"` → all positions → complete.
   - **Skipping-everything**: `"nothing done"` → all positions → incomplete.
   - **Number references**:
     - `"1 done"` → position 1 → complete.
     - `"skipped 3"` → position 3 → skipped.
     - `"1, 3, 5 done"` → 3 tuples.
   - **Exact title match**:
     - Reply mentioning a full habit title (case-insensitive) → matched_via="exact_title".
   - **Unique substring**:
     - `"meditation done"` against a list with "Meditate" → matched_via="substring", task_id matches.
   - **Ambiguous substring**:
     - `"PT done"` against list with 3 PT habits → judgment_required emitted with 3 candidates; no tuple.
   - **Out-of-range position**:
     - `"99 done"` against 8-habit list → error type "invalid_token".
   - **Unparseable token**:
     - `"xyzzy done"` → error type "unparseable_reply".
   - **Mixed clauses**:
     - `"1 done, skipped 3, meditation done"` → 3 tuples (positions 1, 3 + substring match for meditation), each with correct state.
   - **load_morning_list missing file**:
     - Call with non-existent date → FileNotFoundError.
   - **Determinism**:
     - Call `parse_reply` twice on the same inputs → assert results are byte-identical (via `json.dumps(asdict(r1)) == json.dumps(asdict(r2))`).
   - **CLI exit codes**:
     - `main(["--reply", "1 done"])` with mocked load → exit 0.
     - `main(["--reply", "1 done", "--date", "1999-01-01"])` (no fixture) → exit 4.
     - `main([])` (no --reply or --reply-file) → exit 3.

**Files**:
- `tests/habits/fixtures/morning-checkin-2026-05-22.json` (~30 lines)
- `tests/habits/test_parse_morning_reply.py` (~360 lines, ~20 tests)

**Validation**:
- [ ] All tests green.
- [ ] Coverage ≥85% line + branch.
- [ ] SC-002 explicitly named test exists and passes.
- [ ] At least one test verifies byte-determinism (NFR-001).

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

pytest. No I/O except the fixture file load (in tmp_path or via the conftest fixture directory). Pure-function tests for `parse_reply`; minimal mocking.

## Definition of Done

- [ ] All 4 subtasks complete.
- [ ] `pytest tests/habits/test_parse_morning_reply.py -v` ≥85% coverage.
- [ ] SC-002 fixture passes.
- [ ] Byte-determinism test passes (NFR-001).
- [ ] No regression on existing habits tests.

## Risks

- **Tokenization quirks**: handling of commas, "and", multi-word verbs. Tests cover the common shapes; reviewer should add cases for any new pattern Kent uses.
- **State inference per clause**: "1 done, skipped 3" — the parser must associate "done" with "1" and "skipped" with "3". Naive splits could mis-associate.
- **Substring matching false positives**: a short substring like `"PT"` matches multiple habits; must route to judgment_required, NOT pick one.

## Reviewer Guidance

1. Verify SC-002 fixture is byte-correct vs. the journalctl evidence in #371.
2. Walk the parser logic against `"1 done, skipped 3"` — verify state inference handles per-clause.
3. Verify substring uniqueness gate produces judgment_required, not silent picks.
4. Verify byte-determinism test exists and passes.
5. Coverage ≥85%.

## Implementation Command

```bash
spec-kitty agent action implement WP02 --mission habits-checkin-reply-scripts-first-01KS86ZQ --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-22T16:44:11Z – claude:opus:python-implementer:implementer – shell_pid=67556 – Started implementation via action command
- 2026-05-22T17:00:02Z – claude:opus:python-implementer:implementer – shell_pid=67556 – Ready for review — SC-002 + determinism + ambiguity-routing all tested
- 2026-05-22T17:00:40Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=70677 – Started review via action command
- 2026-05-22T17:04:19Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=70677 – Moved to planned
- 2026-05-22T17:05:22Z – claude:opus:python-implementer:implementer – shell_pid=72115 – Started implementation via action command
- 2026-05-22T17:12:19Z – claude:opus:python-implementer:implementer – shell_pid=72115 – Cycle 1 fix: multi-word title parsing via whole-phrase match
