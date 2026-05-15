---
work_package_id: WP01
title: Reference capture + compute_today.py + scripts/habits foundation
dependencies: []
requirement_refs:
- FR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-habits-checkin-d6-extract-01KRNV46
base_commit: afb30d9c8cdf85b48f2c660dcd6d7d11cb3f7685
created_at: '2026-05-15T17:32:30.313075+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: "96693"
agent: "claude:opus-4-7:implementer:implementer"
history:
- event: created
  at: '2026-05-15T17:15:12Z'
  by: spec-kitty.tasks
  note: WP01 prompt generated
authoritative_surface: scripts/habits/compute_today.py
execution_mode: code_change
mission_slug: habits-checkin-d6-extract-01KRNV46
owned_files:
- scripts/habits/compute_today.py
- tests/habits/__init__.py
- tests/habits/test_compute_today.py
- kitty-specs/habits-checkin-d6-extract-01KRNV46/artifacts/reference-checkin-output.txt
tags: []
---

# WP01 — Reference capture + compute_today.py + scripts/habits foundation

## Objective

Establish the behavior-preservation baseline (capture a pre-refactor reference check-in message from the current Sonnet-driven cron) AND ship the first helper (`compute_today.py`) along with its tests and the `scripts/habits/` + `tests/habits/` directory infrastructure that WP02-WP04 build on.

This WP is the foundation of the mission. Subsequent WPs cannot start until WP01 is approved.

## Context

- **Spec**: [`spec.md`](../spec.md) — FR-001 + NFR-002 (reference capture for behavior preservation)
- **Plan**: [`plan.md`](../plan.md) — Technical Context + Charter Check
- **Contract**: [`contracts/compute_today.md`](../contracts/compute_today.md) — full CLI + I/O + test coverage spec for compute_today.py
- **Data model**: [`data-model.md`](../data-model.md) — "Today context" entity (output envelope of compute_today.py)
- **Conventions**: [`docs/design/helper-script-conventions.md`](../../../docs/design/helper-script-conventions.md) — §§ 2 (CLI contract), 3 (stdout SUMMARY: line), 4 (atomic state mutation — not applicable here; no state), 5 (idempotency — pure compute), 8 (testing discipline)
- **Reference precedent**: [`scripts/security/credential_health_check/vikunja_writer.py`](../../../scripts/security/credential_health_check/vikunja_writer.py) — canonical implementation pattern (urllib.request, ET ISO timestamp via zoneinfo)

## Subtask details

### T001 — Capture pre-refactor reference check-in message

**Purpose**: Capture a representative pre-refactor habits-morning-checkin WhatsApp message to serve as the behavior-preservation reference for WP05's smoke test. Without this baseline, NFR-002 ("line-by-line identical post-refactor") is unverifiable.

**Steps**:

1. SSH to office2 as `claude` and trigger the current Sonnet-driven cron:
   ```bash
   ssh office2-claude 'openclaw cron run habits-morning-checkin'
   ```
2. Wait for the WhatsApp message to arrive on Kent's phone (typically <30 seconds).
3. Capture the message text. Two ways:
   - Have Kent forward the WhatsApp message via WhatsApp Web → copy text → paste
   - SSH to office2 and extract from the agent's session JSONL: `tail -50 /home/claude/.openclaw/agents/felix-admin-habits/sessions/<most-recent>.jsonl | jq` and find the assistant message that was the WhatsApp output
4. Save the message text VERBATIM (including the `Sent by felix-admin-habits:sonnet` identity header) to:
   ```
   kitty-specs/habits-checkin-d6-extract-01KRNV46/artifacts/reference-checkin-output.txt
   ```
   Create the `artifacts/` directory if it doesn't exist.
5. Also record metadata in a sibling file `artifacts/reference-checkin-metadata.txt`:
   - Capture date (Eastern time): e.g., `2026-05-15`
   - Day of week: e.g., `Wed`
   - Number of habits scheduled that day
   - Notable Vikunja state at capture (e.g., "1 habit was paused at capture time")

**Files**:
- `kitty-specs/habits-checkin-d6-extract-01KRNV46/artifacts/reference-checkin-output.txt` (NEW)
- `kitty-specs/habits-checkin-d6-extract-01KRNV46/artifacts/reference-checkin-metadata.txt` (NEW)

**Validation**:
- [ ] `reference-checkin-output.txt` exists and contains the verbatim WhatsApp message
- [ ] First line of `reference-checkin-output.txt` is `Sent by felix-admin-habits:sonnet`
- [ ] Metadata file records capture date + day-of-week
- [ ] No leading/trailing whitespace in the reference file (so `diff` in WP05 won't false-positive)

**Edge case**: if all habits happen to already be complete at capture time, the reference message is `All habits complete for today.` — that's still a valid reference (validates the "empty case" path).

---

### T002 — Create `scripts/habits/` and `tests/habits/__init__.py`

**Purpose**: Establish the directory structure WP02-WP04 will use. No `__init__.py` in `scripts/habits/` (helpers are standalone executables, not a Python package).

**Steps**:

1. Create directory: `mkdir -p scripts/habits/`
2. Create directory: `mkdir -p tests/habits/`
3. Create `tests/habits/__init__.py` with the docstring:
   ```python
   """Tests for scripts/habits/ helpers (felix-admin-habits refactor — mission 282)."""
   ```
4. Stage the empty directories with a `.gitkeep` if needed (probably not — scripts/habits/ will have compute_today.py from T003, tests/habits/ will have __init__.py + test_compute_today.py from T004).

**Files**:
- `tests/habits/__init__.py` (NEW)

**Validation**:
- [ ] `scripts/habits/` directory exists
- [ ] `tests/habits/` directory exists
- [ ] `tests/habits/__init__.py` exists and is importable

---

### T003 — Implement `scripts/habits/compute_today.py`

**Purpose**: TZ-aware helper that returns today's day-of-week, date, ET UTC offset, and end-of-day-ET ISO timestamp. Pure compute; no Vikunja calls. Critical for the #112 regression-prevention property.

**Steps**:

1. Create `scripts/habits/compute_today.py` following the contract at [`contracts/compute_today.md`](../contracts/compute_today.md).
2. Required imports (stdlib only): `argparse`, `json`, `sys`, `datetime`, `zoneinfo`.
3. CLI: argparse with `--now-utc` flag (optional, defaults to `datetime.now(timezone.utc)`). Used in tests to fix the time.
4. Logic:
   - Parse `--now-utc` as an ISO-8601 timestamp (or use current UTC if not provided).
   - Convert to `America/New_York` via `zoneinfo.ZoneInfo`.
   - Extract: day-of-week (`%a` → `Mon`/`Tue`/.../`Sun`), date (`%Y-%m-%d`), UTC offset (`%z` → `-0400` or `-0500`; reformat to `-04:00` / `-05:00`).
   - Build `iso_eod_et` = `YYYY-MM-DDT23:59:59<ET_OFFSET>`. **MUST NOT** use `Z` suffix.
5. Output: single JSON line to stdout with fields `day`, `date`, `et_offset`, `iso_eod_et`. Then a `SUMMARY:` line.
6. Exit codes per contract: 0 / 1 / 2.
7. Add module docstring and brief inline comments where the #112 prevention logic is.

**Files**:
- `scripts/habits/compute_today.py` (NEW, ~80 lines)

**Validation**:
- [ ] Helper runs with no arguments: `python3 scripts/habits/compute_today.py` produces valid JSON + SUMMARY
- [ ] Helper runs with `--now-utc 2026-05-15T11:00:00Z` produces deterministic output
- [ ] `iso_eod_et` field NEVER ends with `Z`
- [ ] `et_offset` is one of `-04:00` or `-05:00`
- [ ] Module has docstring referencing FR-001 and contract path

---

### T004 — Write `tests/habits/test_compute_today.py`

**Purpose**: pytest test module covering 6 scenarios from the contract's test coverage table.

**Steps**:

1. Create `tests/habits/test_compute_today.py` following the test coverage table in [`contracts/compute_today.md`](../contracts/compute_today.md).
2. Import the helper via subprocess invocation (since it's a CLI tool, not an importable module):
   ```python
   import subprocess
   import json
   from pathlib import Path

   HELPER = Path(__file__).parent.parent.parent / "scripts" / "habits" / "compute_today.py"

   def run_helper(*args):
       result = subprocess.run(
           ["python3", str(HELPER), *args],
           capture_output=True, text=True
       )
       return result
   ```
3. Implement 6 tests from the contract:
   - `test_typical_weekday` — `--now-utc 2026-05-15T11:00:00Z` → day=Wed, date=2026-05-15, et_offset=-04:00
   - `test_after_8pm_et` — `--now-utc 2026-05-16T01:00:00Z` (9 PM ET prev day) → date=2026-05-15
   - `test_dst_transition` — `--now-utc 2026-03-09T07:00:00Z` (3 AM ET DST starts) → et_offset is the post-DST value
   - `test_est_transition` — `--now-utc 2026-11-02T07:00:00Z` (3 AM ET DST ends) → et_offset is the post-DST-end value (`-05:00`)
   - `test_iso_eod_no_z_suffix` — assert `not output["iso_eod_et"].endswith("Z")`
   - `test_malformed_now_utc` — `--now-utc not-a-date` → exit code 2

**Files**:
- `tests/habits/test_compute_today.py` (NEW, ~80 lines)

**Validation**:
- [ ] All 6 tests written
- [ ] `pytest tests/habits/test_compute_today.py -v` passes locally (6 passed)
- [ ] Tests use subprocess invocation (no direct import — helper is a CLI tool)

---

### T005 — Local validation

**Purpose**: Confirm the helper works end-to-end before declaring WP01 ready for review.

**Steps**:

1. Run helper manually:
   ```bash
   python3 scripts/habits/compute_today.py
   ```
   Visually inspect the JSON output and SUMMARY line. Compare day/date against your wall clock in Eastern time.
2. Run the test suite:
   ```bash
   pytest tests/habits/test_compute_today.py -v
   ```
   All 6 tests must pass.
3. (Optional but recommended) Run helper with a few `--now-utc` overrides spanning DST/EST transition days; verify offsets flip correctly.

**Files**: No new files; validation only.

**Validation**:
- [ ] Manual helper run produces sensible output for current moment
- [ ] All 6 tests pass
- [ ] No deprecation warnings or errors in pytest output

---

## Branch Strategy

- **Planning base**: `main`
- **Merge target**: `main`
- **Execution workspace**: Per-lane worktree allocated by `finalize-tasks` `lanes.json`. The implementer enters the workspace (`spec-kitty agent action implement WP01 --agent <name>` outputs the path) and works there. Commits land on the lane branch; review and merge are handled by spec-kitty workflow.

## Test strategy

Tests are REQUIRED for this WP (NFR-005; conventions § 8 — helpers that touch state OR have multiple code paths OR handle dates with TZ math all qualify).

- pytest + `unittest.mock` (stdlib).
- Test file at `tests/habits/test_compute_today.py`.
- 6 test cases from the contract's coverage table.
- All tests use `subprocess` invocation (helper is a CLI, not a Python module).
- No mocking needed for compute_today.py since it's pure compute.

## Definition of Done

- [ ] T001: reference message captured to `artifacts/reference-checkin-output.txt` with metadata file
- [ ] T002: `scripts/habits/` and `tests/habits/__init__.py` exist
- [ ] T003: `scripts/habits/compute_today.py` implemented per contract; runs cleanly
- [ ] T004: `tests/habits/test_compute_today.py` has 6 tests, all passing
- [ ] T005: local validation green
- [ ] Module docstring on compute_today.py references FR-001
- [ ] No `Z` suffix in any `iso_eod_et` output (verified by `test_iso_eod_no_z_suffix`)
- [ ] All owned_files are committed and pass `python3 -m py_compile`
- [ ] Mark all subtasks done via `spec-kitty agent tasks mark-status T001 T002 T003 T004 T005 --status done`
- [ ] Move WP to for_review: `spec-kitty agent tasks move-task WP01 --to for_review --note "Ready for review — reference captured, compute_today.py complete"`

## Risks

- **Reference-capture timing**: T001 must run on a day with at least one habit scheduled (else the reference is `All habits complete for today.` which is a valid but less-informative baseline). If the capture day is unrepresentative (e.g., a Sunday with no habits), consider capturing a second reference on a busier day.
- **Pure compute is forgiving**: compute_today.py has no Vikunja side effects, so worst-case bug is "wrong day" — caught immediately by manual inspection in T005.
- **zoneinfo availability**: relies on system `tzdata` being present on office2. Ubuntu 24.04 LTS ships with it; not expected to be missing.

## Reviewer guidance (for Codex)

When reviewing this WP, verify:

1. `reference-checkin-output.txt` is present and looks like a real WhatsApp habits check-in (starts with `Sent by felix-admin-habits:sonnet`, contains numbered habit lines).
2. `compute_today.py`'s `iso_eod_et` field NEVER produces a `Z` suffix — grep the source for `'Z'` or `"Z"` and confirm it's only in an error-message context, not the output formatting.
3. DST transition test cases are concrete (use actual 2026 DST/EST transition dates: 2026-03-08 for DST start, 2026-11-01 for DST end — adjust the `--now-utc` test inputs accordingly if helper has issues with those specific dates).
4. Module docstring is present and informative.
5. Test invocation pattern uses subprocess (helper is a CLI; tests should match that contract).
6. All exit codes match the contract (0 success, 1 op error, 2 usage error).

Approve if Definition of Done is satisfied. Reject if any of:
- `Z` suffix appears in `iso_eod_et` output
- Tests use direct import instead of subprocess (drifts from CLI contract)
- Reference capture is missing or malformed
- DST/EST transition tests are missing

## Activity Log

- 2026-05-15T17:32:32Z – claude:opus-4-7:implementer:implementer – shell_pid=96693 – Assigned agent via action command
- 2026-05-15T18:01:19Z – claude:opus-4-7:implementer:implementer – shell_pid=96693 – Ready for review — T001 reference captured (from production session log e05c7c2e on 2026-05-15 11:05 UTC; no extra cron triggered), T002-T005 compute_today.py + 6 tests passing locally (1.05s); --force used because the artifacts/ files are legitimate WP01 deliverables (committed to lane, planning docs explicitly specify this path)
