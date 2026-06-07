---
work_package_id: WP01
title: Calendar helper + validator tests + classifier regression set
dependencies: []
requirement_refs:
- FR-003
- FR-004
- FR-011
- FR-012
tracker_refs: []
planning_base_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
merge_target_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
branch_strategy: Planning artifacts for this mission were generated on kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-inbox-calendar-and-aspiration-routing-01KTHHXS
base_commit: 59b4cf4eac92a404df0d00b4a32a1d1899758551
created_at: '2026-06-07T22:49:33.512168+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
agent: "claude:opus-4-7:python-pedro:implementer"
shell_pid: "85788"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/calendar/
execution_mode: code_change
owned_files:
- scripts/calendar/**
- tests/calendar/**
- tests/inbox/test_classifier_regression.py
- tests/inbox/fixtures/classifier_regression.json
role: implementer
tags: []
---

# WP01: Calendar helper + validator tests + classifier regression set

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load the agent profile assigned to this work package by running `/ad-hoc-profile-load` with the profile slug from this file's `agent_profile` frontmatter field. Apply the profile's identity, governance scope, boundaries, and initialization declaration to the rest of this session. If the field is absent, request a profile selection from the operator before proceeding.

## Objective

Deliver the deterministic helper script `scripts/calendar/validate_calendar_event.py`, its full fixture-driven unit test suite, and the broader inbox classifier regression fixture set + runner. This WP is the deterministic surface of mission `inbox-calendar-and-aspiration-routing-01KTHHXS` per Felix Constitution Directive 6 (scripts vs LLM split): the LLM extracts; this helper validates and converts. Later WPs (WP02 capture prompt, WP03 Felix main) consume this helper.

## Context

- **Authority docs**: `spec.md` FR-003 / FR-004 / FR-011 / FR-012; `contracts/validate_calendar_event.md` (full I/O contract); `data-model.md` (ExtractedCalendarBlock + CalendarEventPayload entities).
- **Existing patterns to follow**:
  - `scripts/inbox/` helpers (`prescan.py`, `append_routing_entry.py`, `handle_parse_failures.py`) — established stdin/stdout JSON convention, atomic state writes, exit-code semantics.
  - `tests/inbox/` — established pytest layout including `--cov-branch` usage.
- **The block input the helper receives** comes from the capture LLM. Field shape is spelled out in `contracts/validate_calendar_event.md` § Input schema. The helper does NOT call out to an LLM — it's pure.
- **Recurrence patterns to support**: weekly-on-named-weekday, weekly-on-multiple-weekdays, biweekly, monthly-on-day-of-month, by-weekday-of-month (first/last/etc.). Patterns outside this set return `"missing recurrence"`.
- **Test-first per DIRECTIVE_034**: author the fixture files + test cases BEFORE implementing the helper. Each test should fail first (Red), pass after implementation (Green), then refactor.
- **Coverage target**: ≥90% line, ≥85% branch on `scripts/calendar/validate_calendar_event.py`. Branch coverage is the harder gate — exercise both branches of every condition. Use `# pragma: no branch` only for truly unreachable branches guarded by earlier short-circuit returns (per memory `reference_pytest_branch_coverage_pragma`).

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP01 --agent <name>` (executes on the lane base computed by finalize-tasks)
- No dependencies — this WP starts immediately.

---

## Subtask T001: Scaffold `scripts/calendar/` module

**Purpose**: Create the directory and Python package shell that hosts the validator. Sets up the import boundary so later subtasks can write tests that import from `scripts.calendar.validate_calendar_event`.

**Steps**:
1. Create directory `scripts/calendar/`.
2. Create `scripts/calendar/__init__.py` (empty file; just establishes the package).
3. Verify the layout matches the existing `scripts/inbox/__init__.py` convention (if it exists; otherwise just leave empty).

**Files**:
- `scripts/calendar/__init__.py` (new, empty)

**Validation**:
- [ ] `scripts/calendar/` directory exists
- [ ] `scripts/calendar/__init__.py` exists and is empty
- [ ] `python3 -c "import scripts.calendar"` succeeds when run from repo root

---

## Subtask T002: Implement `validate_calendar_event.py`

**Purpose**: The core deterministic helper. Reads an ExtractedCalendarBlock JSON from stdin, validates completeness, parses natural-language recurrence to RFC 5545 RRULE, parses natural-language datetimes to RFC 3339, and emits either a CalendarEventPayload (complete) or a missing-fields report (incomplete).

**Steps**:
1. Read the full contract at `kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/contracts/validate_calendar_event.md`. The Input schema, Output schema, and Recurrence patterns table are authoritative — implement to that spec exactly.
2. Module structure:
   - Top of file: module docstring, imports (standard library only — `json`, `sys`, `re`, `datetime`, `zoneinfo`, `dataclasses` if helpful).
   - `parse_datetime(natural: str, tick_iso: str) -> Optional[datetime]`: resolve "today"/"tomorrow"/"next Tuesday"/explicit forms against the tick_iso reference time. Default timezone: `America/New_York`.
   - `parse_duration(natural: str) -> Optional[timedelta]`: handle "30 minutes", "1 hour", "2 hours 15 minutes".
   - `parse_recurrence(natural: str) -> Optional[str]`: apply the recurrence pattern table from the contract. Return the full RRULE string or None.
   - `validate(block: dict) -> dict`: orchestrator. Returns the output JSON shape.
   - `main()`: read stdin, validate, write stdout, exit code per contract.
3. Default fields when not provided: `calendar_id="primary"`, `account="kent@intentional.biz"`, `description=f"Source: {basename(source_inbox_path)}"`, `start_timezone="America/New_York"`.
4. Failure modes per contract: exit 2 (malformed JSON), exit 3 (missing required input field), exit 4 (internal error), exit 0 (complete=true or complete=false — both are normal returns).
5. Aim for ~200 lines. If pushing past 300, factor out a `_recurrence.py` helper.

**Files**:
- `scripts/calendar/validate_calendar_event.py` (new)

**Validation**:
- [ ] Module imports cleanly: `python3 -c "import scripts.calendar.validate_calendar_event"`
- [ ] Running with no input returns exit code 2 with `INVALID_INPUT_JSON` on stderr
- [ ] Running with `echo '{}' | python3 scripts/calendar/validate_calendar_event.py` returns exit 3 with `MISSING_INPUT_FIELD` on stderr
- [ ] All 11 fixture inputs produce the expected outputs (covered by T003)

---

## Subtask T003: Validator unit tests + fixtures [P]

**Purpose**: Author the fixture-driven test suite that exercises every branch of `validate_calendar_event.py`. Per DIRECTIVE_034, these tests are written before T002's implementation passes them (Red → Green).

**Steps**:
1. Create `tests/calendar/__init__.py` (empty).
2. Create the 11 fixture files listed in `contracts/validate_calendar_event.md` § Test fixtures:
   - `tests/calendar/fixtures/complete_oneoff.json`
   - `tests/calendar/fixtures/complete_oneoff_duration.json`
   - `tests/calendar/fixtures/complete_weekly.json`
   - `tests/calendar/fixtures/complete_biweekly.json`
   - `tests/calendar/fixtures/complete_monthly_by_dayofmonth.json`
   - `tests/calendar/fixtures/complete_byweekday_of_month.json`
   - `tests/calendar/fixtures/incomplete_no_start.json`
   - `tests/calendar/fixtures/incomplete_no_end.json`
   - `tests/calendar/fixtures/incomplete_recurrence_unrecognized.json`
   - `tests/calendar/fixtures/edge_dst_transition.json`
   - `tests/calendar/fixtures/edge_relative_anchor_resolution.json`
   Each fixture is a pair: `<name>.input.json` (the stdin block) + `<name>.expected.json` (the expected stdout).
3. Create `tests/calendar/test_validate_calendar_event.py`:
   - Parameterized test that walks every `*.input.json` in `fixtures/`, runs the validator via `subprocess.run` (preferred — matches deploy invocation) OR via direct module import (faster — pick one, document the choice), and diffs against the matching `*.expected.json`.
   - Separate tests for failure modes: malformed JSON (exit 2), missing required field (exit 3).
   - Edge-case tests: timezone-aware vs naive inputs, RFC 3339 with explicit offset, leap-year February dates, etc.
4. Run `pytest tests/calendar/ -v` and ensure all tests fail first (because the helper is empty), then pass after T002 is implemented.

**Files**:
- `tests/calendar/__init__.py` (new, empty)
- `tests/calendar/fixtures/*.input.json` and `tests/calendar/fixtures/*.expected.json` (11 pairs)
- `tests/calendar/test_validate_calendar_event.py` (new, ~200 lines)

**Validation**:
- [ ] All 22 fixture files exist with valid JSON
- [ ] `pytest tests/calendar/ -v` discovers and runs at least one parameterized case per fixture pair
- [ ] Tests pass against the T002 implementation
- [ ] No flaky behavior on a repeat run (idempotent assertions)

---

## Subtask T004: Classifier regression fixture set [P]

**Purpose**: Curate a representative set of ~25 inbox blocks tagged with their expected classification destination. Drives WP02's classifier prompt acceptance.

**Steps**:
1. Create `tests/inbox/fixtures/classifier_regression.json`. Schema:
   ```json
   {
     "fixtures": [
       {
         "id": "trivia-night-recurrence",
         "input_block": "Tuesday trivia nights at Tru West Brewery, 525 Massachusetts Ave, Acton, MA 01720, 6:00 PM, starting May 20.",
         "expected_destination": "calendar_event_complete",
         "rationale": "Recurring calendar event with title, weekday, time, location. From #324."
       },
       ...
     ]
   }
   ```
2. Aim for at least 25 fixtures distributed across destinations:
   - Calendar event (complete one-off): 3 cases
   - Calendar event (complete recurring): 3 cases
   - Calendar event (incomplete — missing time/end/recurrence): 4 cases (one per missing-field shape)
   - Aspiration / musing: 3 cases (incl. "get to bed earlier", "wonder about small business loan")
   - Someday item: 3 cases (incl. "get rid of old lawn tractor when I get around to it")
   - Active task: 3 cases (incl. "call dentist to reschedule cleaning")
   - GitHub issue: 2 cases (existing trigger pattern)
   - Goal declaration: 1 case (existing pattern)
   - Reference / resource: 1 case
   - Multi-domain (block contains both calendar AND task): 2 cases
3. Source as many cases as possible from real historical inbox content — read `~/second-brain/agents/state/inbox-routing.jsonl` (if accessible locally; otherwise document the synthetic ones with `source: synthetic`). Include the specific misroutes from #556 ("spend 15 mins on growth practice", household items routed as tasks) so the regression catches those exact shapes.
4. Sanity-check each fixture: re-read the rationale; if the destination is ambiguous (could legitimately go to two places), tag it `expected_destinations` (array) instead of a singular and accept either as a pass.

**Files**:
- `tests/inbox/fixtures/classifier_regression.json` (new, ~150 lines for 25 fixtures with rationale)

**Validation**:
- [ ] ≥25 fixtures present
- [ ] At least 1 fixture per destination type listed above
- [ ] JSON is valid
- [ ] Each fixture has `id`, `input_block`, `expected_destination`, `rationale`
- [ ] Misroutes from #556 are present and clearly tagged with a `source: historical-misroute` field

---

## Subtask T005: Classifier regression test runner [P]

**Purpose**: Build the pytest runner that asserts the classifier prompt produces the expected destination for each fixture. Two-mode design: static (prompt-rule analysis, fast, deterministic) and live (LLM call, slow, requires API access).

**Steps**:
1. Create `tests/inbox/test_classifier_regression.py`.
2. Default mode: static. Loads `tests/inbox/fixtures/classifier_regression.json`, loads the classifier prompt section from `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (the Step 3 routing table + signals — robust parser; do not attempt to execute LLM logic), and asserts that for each fixture the relevant signal patterns match the expected destination. This is a smoke-level assertion — not full LLM fidelity. Useful for catching regressions where the routing table loses a row.
3. Opt-in live mode: gated behind an env var (e.g., `CLASSIFIER_REGRESSION_LIVE=1` and `ANTHROPIC_API_KEY` present). Calls the Claude haiku API with the actual capture prompt + each fixture input; asserts the parsed classification matches expected. Document the cost (each fixture ≈ 1 API call) so the operator can run it deliberately.
4. The static mode is the CI gate; live mode is for pre-deploy verification.

**Files**:
- `tests/inbox/test_classifier_regression.py` (new, ~150 lines)

**Validation**:
- [ ] `pytest tests/inbox/test_classifier_regression.py -v` runs in static mode and asserts ≥25 cases
- [ ] All static-mode assertions pass against the unmodified (pre-WP02) capture prompt for the existing destination types (calendar/aspiration cases are SKIPPED at this point — they exist only post-WP02)
- [ ] Static-mode assertions fail explicitly for calendar/aspiration cases until WP02 adds the rows
- [ ] Live mode is properly gated (does not run without the env var)

---

## Subtask T006: Pytest config + coverage thresholds

**Purpose**: Wire the coverage gate so CI / local pytest enforces ≥90% line and ≥85% branch on `scripts/calendar/`.

**Steps**:
1. Locate the existing pytest configuration — likely `pyproject.toml` (under `[tool.pytest.ini_options]`) or `pytest.ini`. Use `grep -r "cov-branch" .` to find existing patterns.
2. Add a coverage config block targeting `scripts/calendar/`:
   - In `pyproject.toml` under `[tool.coverage.run]`: `source = ["scripts/calendar"]` (extend if it exists).
   - Under `[tool.coverage.report]`: `fail_under = 90`, `show_missing = true`.
3. Document the canonical invocation in the README or in a new `tests/calendar/README.md`: `pytest tests/calendar/ --cov=scripts/calendar --cov-branch --cov-fail-under=90`.
4. Verify the invocation passes against T002+T003's deliverables.

**Files**:
- `pyproject.toml` OR `pytest.ini` (existing — modified)
- `tests/calendar/README.md` (new, optional, ~20 lines)

**Validation**:
- [ ] Coverage config includes `scripts/calendar` in the measured source
- [ ] `pytest tests/calendar/ --cov=scripts/calendar --cov-branch --cov-fail-under=90` succeeds
- [ ] The `--cov-fail-under` threshold actually fires when a branch is removed (smoke-test by commenting out one branch in T002's helper temporarily and verifying coverage drops)

---

## Definition of Done

- [ ] All 6 subtasks complete with their per-subtask validation items checked.
- [ ] `pytest tests/calendar/ tests/inbox/test_classifier_regression.py --cov=scripts/calendar --cov-branch --cov-fail-under=90` passes from a clean checkout.
- [ ] No uncommitted changes outside this WP's `owned_files`.
- [ ] WP frontmatter `subtasks` count matches body subtask count.
- [ ] Helper script has zero external dependencies beyond stdlib.

## Risks

1. **Classifier static analysis impractical**: if the capture prompt is too complex to statically infer "this block → that destination", the static mode of T005 degrades to a syntactic check (table contains the row, header signals match a pattern). Acceptable degradation — live mode is the real gate.
2. **Coverage tool excludes generated code**: ensure any code-generation step (none expected) is not measured.
3. **Fixture set ages**: classifier regression set should be revisited when capture's prompt changes substantively. Document this in `tests/calendar/README.md` or a `MAINTENANCE.md`.

## Reviewer guidance

- Reviewer checks: do the 11 validator fixtures cover BOTH parser-success and parser-failure paths? Are RRULE conversions exactly correct for the four recurrence patterns? Does the classifier regression set carry historical misroute cases from #556 verbatim?
- Reviewer must run the coverage gate command and verify the actual percentage reported. If <90% line or <85% branch, reject.
- Reviewer verifies no `# noqa` / `# pragma: no cover` markers slipped in for production logic (defensive-check pragmas per `reference_pytest_branch_coverage_pragma` memory are allowed for unreachable branches guarded by earlier short-circuit returns; reviewer scrutinizes that they are genuinely unreachable).

## Activity Log

- 2026-06-07T22:50:11Z – claude:opus-4-7:python-pedro:implementer – shell_pid=85788 – Started implementation via action command
