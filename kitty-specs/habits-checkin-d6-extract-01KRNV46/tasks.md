# Tasks: Habits morning check-in — extract Steps 1-4 to helper scripts (D6)

**Mission**: `habits-checkin-d6-extract-01KRNV46` | **Generated**: 2026-05-15
**Spec**: [`spec.md`](./spec.md) | **Plan**: [`plan.md`](./plan.md)
**Branch contract**: current `main` → planning base `main` → merge target `main` (matches ✓)

5 work packages, 19 subtasks total. All WP prompts sized in the 200-500 line spec-kitty sweet spot.

---

## Subtask Index

Reference table only — for tracking, use the per-WP checkbox rows below each Work Package heading. The `Parallel` column indicates intra-WP parallelism, not task status.

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Capture pre-refactor reference check-in message from production cron | WP01 |  | [D] |
| T002 | Create `scripts/habits/` directory + tests/habits/__init__.py | WP01 |  | [D] |
| T003 | Implement `scripts/habits/compute_today.py` per contract | WP01 |  | [D] |
| T004 | Write `tests/habits/test_compute_today.py` covering 6 scenarios | WP01 |  | [D] |
| T005 | Local validation: run helper + pytest, confirm green | WP01 |  | [D] |
| T006 | Implement `scripts/habits/query_active_habits.py` per contract | WP02 |  | [D] |
| T007 | Write `tests/habits/test_query_active_habits.py` covering 9 scenarios | WP02 |  | [D] |
| T008 | Local validation: run helper against office2 Vikunja + pytest | WP02 |  | [D] |
| T009 | Implement `scripts/habits/set_due_dates.py` per contract (Z-suffix rejection mandatory) | WP03 |  | [D] |
| T010 | Write `tests/habits/test_set_due_dates.py` covering 8 scenarios | WP03 |  | [D] |
| T011 | Local validation: `--dry-run` helper + pytest | WP03 |  | [D] |
| T012 | Implement `scripts/habits/exclude_completed.py` per contract | WP04 |  | [D] |
| T013 | Write `tests/habits/test_exclude_completed.py` covering 10 scenarios | WP04 |  | [D] |
| T014 | Local validation: helper + pytest | WP04 |  | [D] |
| T015 | Refactor `felix-admin-habits/AGENTS.md` Steps 1-4 → helper invocations | WP05 |  |
| T016 | Add "Failure handling" subsection to AGENTS.md per conventions § 6 | WP05 |  |
| T017 | Update `service-inventory.json` habit-checkin entry | WP05 |  |
| T018 | Deploy 4 helpers + AGENTS.md to office2 via scp | WP05 |  |
| T019 | Smoke test: manual cron run on office2; diff WhatsApp output vs reference | WP05 |  |

---

## Work Packages

### WP01 — Reference capture + compute_today.py + scripts/habits foundation

**Goal**: Establish behavior-preservation baseline (capture pre-refactor reference message) and ship the first helper (`compute_today.py`) along with its tests and the `scripts/habits/` + `tests/habits/` directory infrastructure that subsequent WPs build on.

**Priority**: P0 (blocker for WP02-WP05 — no parallel start possible).

**Independent test**: `pytest tests/habits/test_compute_today.py` passes; running `python3 scripts/habits/compute_today.py` produces well-formed JSON output with correct ET offset for today's date; the captured reference message exists at `kitty-specs/.../artifacts/reference-checkin-output.txt`.

**Estimated prompt size**: ~310 lines.

**Subtasks** (tracking — `mark-status` reads these checkboxes):

- [x] T001 Capture pre-refactor reference check-in message from production cron (WP01)
- [x] T002 Create `scripts/habits/` directory + `tests/habits/__init__.py` (WP01)
- [x] T003 Implement `scripts/habits/compute_today.py` per contract (WP01)
- [x] T004 Write `tests/habits/test_compute_today.py` covering 6 scenarios (WP01)
- [x] T005 Local validation: run helper + pytest, confirm green (WP01)

**Implementation sketch**:
1. T001 first — operator step on office2 (manual cron trigger, capture WhatsApp output to artifacts/). MUST happen before any code change.
2. Directory scaffolding (T002).
3. Implement compute_today.py per `contracts/compute_today.md` (T003).
4. Write 6 tests per the contract's test coverage table (T004).
5. Local validation pass (T005).

**Parallel opportunities**: None within this WP — all subtasks are sequential.

**Dependencies**: None (root of the dependency graph).

**Risks**:
- T001 reference capture requires office2 access. Operator-step risk: capture must be done on the same day-class as eventual smoke test (in WP05) to be a fair diff baseline.
- compute_today.py is small but #112 regression-prevention is critical — tests for after-8-PM-ET and DST/EST transitions are mandatory.

**FRs covered**: FR-001.

**Prompt**: [`tasks/WP01-reference-capture-and-compute-today.md`](./tasks/WP01-reference-capture-and-compute-today.md)

---

### WP02 — query_active_habits.py + tests

**Goal**: Ship the Vikunja habit-query helper with frequency-table filtering, PAUSED/done exclusion, and per-day filtering.

**Priority**: P1 (parallelizable with WP03, WP04 after WP01 ships).

**Independent test**: `pytest tests/habits/test_query_active_habits.py` passes; running `python3 scripts/habits/query_active_habits.py --day <today>` against office2 Vikunja returns the expected scheduled-today habit list.

**Estimated prompt size**: ~270 lines.

**Subtasks**:

- [x] T006 Implement `scripts/habits/query_active_habits.py` per contract (WP02)
- [x] T007 Write `tests/habits/test_query_active_habits.py` covering 9 scenarios (WP02)
- [x] T008 Local validation: run helper against office2 Vikunja + pytest (WP02)

**Implementation sketch**:
1. Implement helper per `contracts/query_active_habits.md` — Vikunja GET `/projects/{habits_id}/tasks`, parse frequency-descriptor lexicon (Daily, Daily (evening), Mon-Sat, Mon/Wed/Fri), exclude PAUSED/done, filter by `--day`.
2. Write 9 tests per contract (each frequency case, exclusions, edge cases, errors).
3. Validate against real Vikunja on office2 for one day; verify result matches what AGENTS.md Step 2 currently produces.

**Parallel opportunities**: Implementation and test-writing can interleave but sequential per subtask makes review cleaner.

**Dependencies**: `WP01` (needs `scripts/habits/` + `tests/habits/__init__.py` from WP01's T002).

**Risks**:
- Vikunja API token must be readable from `/data/services/openclaw/secrets/vikunja-api` during local validation. If running on Mac, scp the token to a local path and use `--vikunja-token-path` override.
- Frequency parsing must handle en-dash (`Mon–Sat`) and ascii dash (`Mon-Sat`) variants.

**FRs covered**: FR-002.

**Prompt**: [`tasks/WP02-query-active-habits.md`](./tasks/WP02-query-active-habits.md)

---

### WP03 — set_due_dates.py + tests (with #112 regression-prevention)

**Goal**: Ship the due_date-setting helper with explicit Z-suffix rejection (NFR-004), partial-failure resilience (NFR-007), and `--dry-run` support.

**Priority**: P1 (parallelizable with WP02, WP04 after WP01).

**Independent test**: `pytest tests/habits/test_set_due_dates.py` passes; helper with `--dry-run` prints the would-be PUT calls without performing them; helper rejects `--iso-eod-et` values ending with `Z`.

**Estimated prompt size**: ~270 lines.

**Subtasks**:

- [x] T009 Implement `scripts/habits/set_due_dates.py` per contract (Z-suffix rejection mandatory) (WP03)
- [x] T010 Write `tests/habits/test_set_due_dates.py` covering 8 scenarios (WP03)
- [x] T011 Local validation: `--dry-run` helper + pytest (WP03)

**Implementation sketch**:
1. Implement helper per `contracts/set_due_dates.md`. Critical: validate `--iso-eod-et` rejects `Z` suffix (regex check at startup; exit 2 on violation).
2. Implement per-habit-failure resilience: continue on individual PUT failure, accumulate in `failed` array, exit 1 if any failed.
3. Write 8 tests covering happy path, partial failure, all-fail, dry-run, Z-suffix rejection, malformed inputs, idempotency, empty input.
4. Validate locally in `--dry-run` mode (never run mutating mode against production Vikunja without explicit intent).

**Parallel opportunities**: Implementation and tests in sequence.

**Dependencies**: `WP01`.

**Risks**:
- **CRITICAL**: This helper is the load-bearing point for #112 regression-prevention. Z-suffix rejection is a hard requirement; tests must explicitly verify the rejection path.
- Partial-failure semantics — exit code 1 with non-empty `succeeded` must communicate partial state correctly; agent's failure-handling depends on this.

**FRs covered**: FR-003.

**Prompt**: [`tasks/WP03-set-due-dates.md`](./tasks/WP03-set-due-dates.md)

---

### WP04 — exclude_completed.py + tests

**Goal**: Ship the completion-state filter helper that parses `[Felix] YYYY-MM-DD | state | note` comments and identifies habits already addressed today.

**Priority**: P1 (parallelizable with WP02, WP03 after WP01).

**Independent test**: `pytest tests/habits/test_exclude_completed.py` passes; helper correctly excludes habits with `complete`, `rescheduled`, or `will-not-do` state comments for today; helper correctly INCLUDES habits with stale (yesterday's) comments.

**Estimated prompt size**: ~270 lines.

**Subtasks**:

- [x] T012 Implement `scripts/habits/exclude_completed.py` per contract (WP04)
- [x] T013 Write `tests/habits/test_exclude_completed.py` covering 10 scenarios (WP04)
- [x] T014 Local validation: helper + pytest (WP04)

**Implementation sketch**:
1. Implement helper per `contracts/exclude_completed.md`. For each habit ID, GET comments, parse `[Felix]` format, match against `--today` date + lexicon (complete/rescheduled/will-not-do).
2. Implement "most recent wins" rule for multiple addressed-comments on the same habit.
3. Write 10 tests covering each state, yesterday's comments (ignored), non-Felix comments, malformed Felix prefix (warn, treat as ready), multiple addressed, empty inputs, errors.
4. Validate locally.

**Parallel opportunities**: Sequential within WP.

**Dependencies**: `WP01`.

**Risks**:
- Comment-format parsing is fragile. Tests must cover the malformed-Felix-prefix case (WARN to stderr, don't halt).
- "Most recent wins" semantics — if a habit has both a `complete` and `rescheduled` comment for today, the one with higher `comment_id` wins.

**FRs covered**: FR-004.

**Prompt**: [`tasks/WP04-exclude-completed.md`](./tasks/WP04-exclude-completed.md)

---

### WP05 — AGENTS.md refactor + service-inventory + deploy + smoke test

**Goal**: Wire the four helpers into `felix-admin-habits/AGENTS.md`, update the architecture inventory, deploy to office2, and verify behavior preservation via the smoke test.

**Priority**: P0 for completion (mission's acceptance verification lives here). Cannot start until WP01-WP04 all approved.

**Independent test**: `diff` between the WP01-captured reference message and the post-deploy smoke-test message is empty (zero lines of difference). `service-inventory.json` validates.

**Estimated prompt size**: ~440 lines.

**Subtasks**:

- [ ] T015 Refactor `felix-admin-habits/AGENTS.md` Steps 1-4 → helper invocations (WP05)
- [ ] T016 Add "Failure handling" subsection to AGENTS.md per conventions § 6 (WP05)
- [ ] T017 Update `service-inventory.json` habit-checkin entry (WP05)
- [ ] T018 Deploy 4 helpers + AGENTS.md to office2 via scp (WP05)
- [ ] T019 Smoke test: manual cron run on office2; diff WhatsApp output vs reference (WP05)

**Implementation sketch**:
1. Edit `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`:
   - Replace Step 1 prose with `python3 scripts/habits/compute_today.py` invocation + JSON parse
   - Replace Step 2 with `query_active_habits.py --day <from-step-1>`
   - Replace Step 3 with `set_due_dates.py --habit-ids <from-step-2> --iso-eod-et <from-step-1>`
   - Replace Step 4 with `exclude_completed.py --habit-ids <from-step-3-succeeded> --today <from-step-1>`
   - Step 5 unchanged but note its input is now Step 4's `ready_for_checkin`
   - Step 6 unchanged
   - Add Failure handling subsection per conventions § 6 (file [doc-audit] issue on helper failure; do NOT send broken check-in)
2. Update `docs/design/architecture/data/service-inventory.json` `habit-checkin` entry: add `config_files` references for the 4 helpers; bump `updated_by` to reference #282.
3. Deploy: `scp` 4 helpers to `/home/claude/kg-automation/scripts/habits/` + AGENTS.md to `/data/services/openclaw/habits-agent/AGENTS.md`.
4. Smoke test: `ssh office2-claude 'openclaw cron run habits-morning-checkin'`; capture WhatsApp output; `diff` against the WP01 reference file.

**Parallel opportunities**: T015-T017 can be done in parallel (different files); T018 sequential after; T019 sequential after T018.

**Dependencies**: `WP01`, `WP02`, `WP03`, `WP04` (must have all helpers approved).

**Risks**:
- AGENTS.md size target: ≤300L (NFR-003). Pre-refactor: 478L. The refactor removes ~120L of Steps 1-4 prose and adds ~30L of helper invocations + Failure handling. Target should be ~390L worst case; tight but achievable.
- Smoke test must run on the SAME day-class as the reference capture (in WP01). If WP01's capture was a Wednesday, smoke test should also run on a Wednesday for a fair diff.
- Operator-step risk: deploy via scp is manual; T018 needs careful sequencing (helpers before AGENTS.md, so the agent's first invocation can find them).

**FRs covered**: FR-005, FR-006, FR-007.

**Prompt**: [`tasks/WP05-agents-md-refactor-deploy-smoke.md`](./tasks/WP05-agents-md-refactor-deploy-smoke.md)

---

## MVP scope

This mission has no MVP/full-scope split — all 5 WPs must complete for behavior preservation to be verifiable. WP01 alone (reference capture + compute_today) doesn't deliver user-visible value; WP05 is the integration that makes the refactor live.

## Parallelization summary

- WP01 ships first (root of dep graph)
- WP02, WP03, WP04 can ship in parallel after WP01 (independent helpers, no shared files)
- WP05 ships last (depends on all four helpers)

Expected lanes (from `finalize-tasks` `lanes.json`): 3 lanes, with WP02-WP04 distributed across lanes after WP01's lane completes.

## Next suggested command

`/spec-kitty.implement` — or invoke the `spec-kitty-implement-review` skill for the orchestrated implement-review loop (Claude implementer + Codex reviewer per Kent's directive).
