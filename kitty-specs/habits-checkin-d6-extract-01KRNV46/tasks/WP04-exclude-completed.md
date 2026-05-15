---
work_package_id: WP04
title: exclude_completed.py + tests
dependencies:
- WP01
requirement_refs:
- FR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T012
- T013
- T014
history:
- event: created
  at: '2026-05-15T17:15:12Z'
  by: spec-kitty.tasks
  note: WP04 prompt generated
authoritative_surface: scripts/habits/exclude_completed.py
execution_mode: code_change
mission_slug: habits-checkin-d6-extract-01KRNV46
owned_files:
- scripts/habits/exclude_completed.py
- tests/habits/test_exclude_completed.py
tags: []
---

# WP04 — exclude_completed.py + tests

## Objective

Ship the completion-state filter helper that determines which habits are already addressed today (state = `complete`, `rescheduled`, or `will-not-do`) and returns the subset ready for inclusion in the check-in message. Format-sensitive parsing of `[Felix] YYYY-MM-DD | state | optional note` comments is the high-criticality concern.

## Context

- **Spec**: [`spec.md`](../spec.md) — FR-004 + NFR-005 (test coverage)
- **Contract**: [`contracts/exclude_completed.md`](../contracts/exclude_completed.md) — full CLI + I/O + comment-parsing rules + 10 test scenarios
- **Data model**: [`data-model.md`](../data-model.md) — Completion comment entity
- **Auth source**: same as WP02 (token at `/data/services/openclaw/secrets/vikunja-api`, base URL on Tailscale)

## Subtask details

### T012 — Implement `scripts/habits/exclude_completed.py`

**Purpose**: For each habit ID, fetch Vikunja comments, parse `[Felix]` format, identify habits addressed today, return the ready-for-checkin subset.

**Steps**:

1. Create `scripts/habits/exclude_completed.py` per [`contracts/exclude_completed.md`](../contracts/exclude_completed.md).
2. CLI: `--habit-ids` (comma-separated), `--today` (`YYYY-MM-DD`), `--vikunja-token-path`, `--vikunja-base-url`.
3. Helper internals (in-line, mirroring WP02/WP03's pattern):
   - `_load_token(path)` — read mode-600 token file
   - `_vikunja_get(base_url, token, path)` — GET with bearer auth
4. Comment parser:
   ```python
   import re
   FELIX_COMMENT = re.compile(
       r"^\[Felix\]\s+(\d{4}-\d{2}-\d{2})\s+\|\s+([\w-]+)(?:\s+\|\s+(.*))?$",
       re.MULTILINE
   )

   def parse_felix_comment(comment_text: str) -> Optional[tuple[str, str, Optional[str]]]:
       """Returns (date, state, note) if comment matches, else None."""
       m = FELIX_COMMENT.search(comment_text.strip())
       if not m:
           return None
       return m.group(1), m.group(2).lower(), m.group(3)
   ```
5. Main loop:
   - Parse `--today` (validate `YYYY-MM-DD` shape; exit 2 if malformed).
   - For each habit ID:
     - GET `/api/v1/tasks/{habit_id}/comments`
     - For each comment in response (typically sorted newest-first by Vikunja):
       - Try to parse `[Felix]` format. If non-Felix, skip silently. If malformed Felix (starts with `[Felix]` but doesn't parse), WARN to stderr and skip.
       - If parsed AND date == `--today` AND state ∈ {`complete`, `rescheduled`, `will-not-do`}: record this habit as addressed with the comment_id (use the HIGHEST comment_id when multiple match — "most recent wins").
     - If no matching comment: habit goes into `ready_for_checkin`.
   - Output JSON + SUMMARY.
6. State lexicon (case-insensitive on match, lowercase in output):
   - `complete`
   - `rescheduled`
   - `will-not-do`
7. Exit codes: 0 / 1 / 2 per contract.

**Files**:
- `scripts/habits/exclude_completed.py` (NEW, ~160 lines)

**Validation**:
- [ ] Helper accepts `--today 2026-05-15` and rejects `--today garbage`
- [ ] Comment parser correctly extracts (date, state, note) tuples
- [ ] Malformed `[Felix]` comment produces stderr WARN but doesn't halt
- [ ] Multiple-addressed-comments case picks the highest `comment_id`
- [ ] Output `ready_for_checkin` sorted by habit ID ascending

---

### T013 — Write `tests/habits/test_exclude_completed.py`

**Purpose**: 10 tests covering all the comment-parsing edge cases from the contract.

**Steps**:

1. Create `tests/habits/test_exclude_completed.py` following the contract's test table.
2. Same mocking pattern as WP02/WP03 — helper importable + CLI; patch `urllib.request.urlopen`.
3. Implement these 10 tests:
   - `test_no_comments_all_ready` — habits with empty comments array; all in `ready_for_checkin`
   - `test_complete_today_addressed` — habit has `[Felix] 2026-05-15 | complete`; in `already_addressed` with `state: "complete"`
   - `test_rescheduled_today_addressed` — `[Felix] 2026-05-15 | rescheduled | this afternoon`; addressed
   - `test_will_not_do_today_addressed` — `[Felix] 2026-05-15 | will-not-do | rest day`; addressed
   - `test_yesterday_comment_ignored` — `[Felix] 2026-05-14 | complete`; habit is ready_for_checkin (yesterday doesn't count)
   - `test_non_felix_comment_ignored` — comment `"Random user note"`; doesn't match; habit ready
   - `test_multiple_addressed_uses_most_recent` — 2 matching comments; output uses higher `comment_id`
   - `test_malformed_felix_prefix_warned` — comment `[Felix YYYY-MM-DD]` (missing pipe); stderr WARN; habit treated as ready
   - `test_empty_habit_ids` — `--habit-ids ""`; exit 0 with all-empty arrays
   - `test_vikunja_unreachable` — `URLError` raised; exit 1

**Files**:
- `tests/habits/test_exclude_completed.py` (NEW, ~280 lines)

**Validation**:
- [ ] All 10 tests pass
- [ ] Mock fixtures cover representative Vikunja comment response shapes
- [ ] State lexicon (`complete`, `rescheduled`, `will-not-do`) all tested
- [ ] Most-recent-wins case has explicit assertion on `comment_id`

---

### T014 — Local validation

**Purpose**: Confirm the helper correctly identifies real today-addressed habits in production Vikunja.

**Steps**:

1. Get today's day-of-week and date via `compute_today.py`.
2. Get today's scheduled habit IDs via `query_active_habits.py`.
3. Run `exclude_completed.py` with those inputs:
   ```bash
   python3 scripts/habits/exclude_completed.py \
       --habit-ids "$IDS" \
       --today "$(python3 scripts/habits/compute_today.py | head -1 | jq -r .date)" \
       --vikunja-token-path /tmp/vikunja-token-readonly
   ```
4. Cross-check the output against your own knowledge of which habits Kent has marked complete today (look at Vikunja UI comments on each habit). Should match.
5. Run pytest:
   ```bash
   pytest tests/habits/test_exclude_completed.py -v
   ```

**Files**: No new files.

**Validation**:
- [ ] Helper output matches independent inspection of Vikunja state
- [ ] Tests pass (10/10)
- [ ] No real mutations occurred (helper is read-only)

---

## Branch Strategy

- **Planning base**: `main`
- **Merge target**: `main`
- **Execution workspace**: Per-lane worktree from `lanes.json`, branched from WP01.

## Test strategy

Tests REQUIRED (NFR-005; conventions § 8). Comment-parsing is format-sensitive — fits the "multiple code paths" and "format-sensitive" criteria.

## Definition of Done

- [ ] T012: helper implemented per contract; comment parser handles all lexicon cases
- [ ] T013: 10 tests passing
- [ ] T014: local validation confirms behavior against real Vikunja
- [ ] Module docstring references FR-004 and the comment format spec
- [ ] All owned_files committed
- [ ] Mark subtasks done: `spec-kitty agent tasks mark-status T012 T013 T014 --status done`
- [ ] Move to for_review: `spec-kitty agent tasks move-task WP04 --to for_review --note "exclude_completed.py ready — 10 tests passing"`

## Risks

- **Felix prefix sensitivity**: `[Felix]` is literal. A malformed variant (e.g., `[Felix ]` with trailing space) is treated as non-Felix and skipped silently — that's defensible but worth a test case. The malformed-Felix-prefix case (starts with `[Felix]` but doesn't match the full regex) is the WARN path.
- **Comment ordering assumption**: Vikunja typically returns comments newest-first, but the helper shouldn't rely on this — explicit "most recent wins" via comparing `comment_id` values is the right approach.
- **State lexicon**: only `complete`, `rescheduled`, `will-not-do` count as addressed. Any other state in a `[Felix]` comment (e.g., `[Felix] 2026-05-15 | maybe | unsure`) is a malformed-Felix case (WARN, treated as ready).

## Reviewer guidance (for Codex)

Verify:

1. **Comment regex**: matches the full lexicon (`complete`, `rescheduled`, `will-not-do` — case-insensitive in match, lowercase in output).
2. **Non-Felix vs malformed-Felix**: "Random user note" → silent skip; "[Felix] garbled" → stderr WARN + skip. Two different paths.
3. **Most-recent-wins**: explicit assertion in `test_multiple_addressed_uses_most_recent` that comment_id selection works.
4. **Output sort**: `ready_for_checkin` sorted by habit ID for deterministic downstream comparison.
5. **Token handling**: same as WP02 — no logging of token contents.
6. **State lexicon strict**: only three states count; other states (in well-formed Felix comments) trigger WARN.

Reject if:
- Regex matches non-lexicon states without warning
- Comment ordering relies on Vikunja's return order rather than `comment_id` comparison
- Token contents logged anywhere
- Stale-comment (yesterday) is treated as addressed
