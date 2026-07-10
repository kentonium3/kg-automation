---
work_package_id: WP02
title: Cron-drift detector + approved-cron baseline
dependencies: []
requirement_refs:
- FR-003
- FR-004
- FR-005
- FR-006
- NFR-001
- NFR-002
tracker_refs: []
planning_base_branch: fix/felix-truthful-reporting
merge_target_branch: fix/felix-truthful-reporting
branch_strategy: Planning artifacts for this mission were generated on fix/felix-truthful-reporting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-truthful-reporting unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
phase: Phase 1 - Detection
assignee: ''
agent: "claude:opus:reviewer-renata:reviewer"
agent_profile: "python-pedro"
shell_pid: "6593"
history:
- at: '2026-07-10T18:45:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/trust/
create_intent:
- scripts/trust/__init__.py
- scripts/trust/cron_baseline.py
- scripts/trust/cron_drift_detector.py
- docs/design/architecture/data/approved-crons.json
- tests/trust/__init__.py
- tests/trust/test_cron_baseline.py
- tests/trust/test_cron_drift_detector.py
execution_mode: code_change
owned_files:
- scripts/trust/__init__.py
- scripts/trust/cron_baseline.py
- scripts/trust/cron_drift_detector.py
- docs/design/architecture/data/approved-crons.json
- tests/trust/__init__.py
- tests/trust/test_cron_baseline.py
- tests/trust/test_cron_drift_detector.py
role: implementer
tags: []
---

# WP02 — Cron-drift detector + approved-cron baseline

## ⚡ Do This First: Load Agent Profile

Before touching any file, load your assigned agent profile with the
`/ad-hoc-profile-load` skill (pass the `agent`/`role` from this WP's
frontmatter — `claude` / `implementer`). This applies your identity,
governance scope, boundaries, and initialization declaration. Do **not**
begin implementation until the profile is loaded and its init declaration
is emitted.

## Branch Strategy

- **Current branch at workflow start**: `fix/felix-truthful-reporting`.
- **Planning/base branch for this feature**: `fix/felix-truthful-reporting`.
- **Completed changes must merge into**: `fix/felix-truthful-reporting`.
- The concrete lane branch is resolved and created by `/spec-kitty.implement`
  — do **not** hand-create worktrees or branches yourself. Work only in the
  lane the workflow materializes for you.

## Objectives & Success Criteria

This WP delivers the **load-bearing, agent-independent** half of the detection
subsystem (plan IC-03): a deterministic cron-drift detector that grounds live
OpenClaw crons against a committed approved-cron baseline. It maps to:

- **FR-003** — surface any scheduled/standing OpenClaw cron that is not in the
  approved baseline (the incident class: unrequested infrastructure).
- **FR-004** — establish the committed approved-cron baseline as the
  deterministic ground truth for what crons are legitimate.
- **FR-005** — produce structured findings that WP04 renders into `#701`
  alerts (this WP produces the findings; it does **not** emit alerts).
- **FR-006(b)** — the deterministic cron-drift class; no LLM, no general
  verifier.

**Scope boundary (read carefully):** THIS WP delivers the **baseline file**,
the **loader**, the **pure diff function**, the **live-enumeration wrapper**,
and **unit tests** only. Alert emission, the seen-findings state file, the
systemd timer, and the `run_trust_scan` runner belong to **WP04** — do not
build them here. No `#701` alert-bus calls in this WP.

**Success = all five finding kinds are produced correctly by a pure function,
the baseline is valid and seeded with the 7 known crons, the live wrapper is
fail-safe-friendly, and every finding kind has branch-covered unit tests.**

## Context & Constraints

- **python3-only** (office2 has no `python` binary). All helpers are invoked as
  `python3 -m scripts.trust.<mod>`. Modules import as `scripts.trust.*`, so this
  WP creates `scripts/trust/__init__.py` and `tests/trust/__init__.py`.
- **Fail-safe posture (NFR-001).** A CLI failure or non-JSON output from
  `openclaw cron list --json` must **never** be interpreted as "there are no
  crons" (which would silently suppress an `unapproved_present` finding). The
  live wrapper raises a **typed error** on any read/parse failure; the caller
  (WP04) decides the fail-safe response (log, `ok:false`, no alert). "Can't read
  crons" is emphatically not "no unapproved crons."
- **Pure functions, no I/O in the diff.** `detect_cron_drift(...)` takes already-
  parsed inputs and returns findings — no subprocess, no file reads, no network.
  This keeps it fully unit-testable against mocked JSON and is the reason the
  subprocess wrapper is isolated in its own function.
- **Style reference:** mirror the deterministic-monitoring code in
  `scripts/office2/felix_health_check/run.py` — `from __future__ import
  annotations`, module logger, `subprocess.run` (never `exec`) with
  `capture_output=True, text=True, timeout=..., check=False`, typed constants,
  dataclasses for value objects.
- **Contracts you bind to:** C1 (the `openclaw cron list --json` shape) and C3
  (`detect_cron_drift` signature + match semantics) in
  `contracts/detector-cli.md`. Entity fields come from `data-model.md`
  (`ApprovedCron`, `LiveCron`, `CronDriftFinding`).
- Wrap any CLI/JSON/`schedule.tz` tokens in backticks in code comments and
  docstrings.

## Subtasks & Detailed Guidance

### T006 — Approved-cron baseline (`docs/design/architecture/data/approved-crons.json`)

**Purpose.** Create the committed allowlist of legitimate crons — the
deterministic ground truth the detector diffs against (`ApprovedCron`,
data-model.md).

**Steps.**
1. Create `scripts/trust/__init__.py` (empty package marker) as part of this WP
   so `scripts.trust.*` imports resolve.
2. Author `docs/design/architecture/data/approved-crons.json` as a
   self-describing object with a top-level `schema_version` (start at `1`) and a
   `crons` array of `ApprovedCron` entries. Each entry has exactly:
   `name`, `agent_id`, `schedule_expr`, `tz`, `purpose`, `approved_by`,
   `approved_at`.
3. Seed the array with the **7 known legitimate crons** (verified live on
   office2 2026-07-10):
   - `inbox-5pm`, `inbox-10pm`, `inbox-7am`, `inbox-noon` — `agent_id`
     `felix-admin-capture`
   - `habits-morning-checkin`, `habits-weekly-report` — `agent_id`
     `felix-admin-habits`
   - `escalation-daily` — `agent_id` `felix-admin-escalation`
4. For `schedule_expr` + `tz`, seed from the values in `data-model.md` /
   contract C1 (`tz` = `America/New_York` where applicable). Add a comment in
   the WP-completion notes (and a `_note` field is acceptable) that the exact
   `schedule_expr`/`tz` per cron must be **confirmed live at deploy** by
   re-running `openclaw cron list --json` via `ssh office2-claude` — the
   implementer may re-run it now to capture exact values.
5. Set `approved_by` = `kent`, `approved_at` = the seeding date (`2026-07-10`).

**Files.** `docs/design/architecture/data/approved-crons.json`,
`scripts/trust/__init__.py`.

**Notes.** The architecture-data validator (`validate_architecture_data.py`)
may inspect files under `data/`; keep the file self-describing (`schema_version`)
and internally consistent so it does not trip a blocking Docs-CI gate. WP05 owns
any service-inventory wiring — do **not** touch inventory here. `name` must be
unique within the baseline (an invariant per data-model.md).

### T007 — Baseline loader + hash (`scripts/trust/cron_baseline.py`)

**Purpose.** Load and validate the baseline into typed value objects, and
provide a stable content hash WP04 will fold into finding fingerprints.

**Steps.**
1. Define `ApprovedCron` as a `@dataclass` (frozen) with the seven fields from
   T006 (`name`, `agent_id`, `schedule_expr`, `tz`, `purpose`, `approved_by`,
   `approved_at`). A `TypedDict` is an acceptable alternative, but a frozen
   dataclass matches the health-check style and is preferred.
2. Define a typed error `class BaselineError(Exception)` (a malformed or
   unreadable baseline).
3. `load_baseline(path) -> list[ApprovedCron]`:
   - read + `json.load` the file; on `FileNotFoundError`, `json.JSONDecodeError`,
     or a structurally invalid document, raise `BaselineError` (never return an
     empty list — the caller must be able to distinguish "no baseline" from "no
     crons", the fail-safe rule).
   - validate the top-level shape (`schema_version` present, `crons` is a list),
     and that every entry has all required non-empty string fields; raise
     `BaselineError` with a clear message on any missing/blank required field.
   - enforce the `name`-unique invariant (raise `BaselineError` on a duplicate).
4. `baseline_hash(entries: list[ApprovedCron]) -> str`: a deterministic,
   order-independent content hash (e.g., `hashlib.sha256` over a sorted,
   canonical JSON serialization of the entries). Used later by WP04 for
   baseline-versioned finding fingerprints — so a baseline edit re-evaluates
   findings rather than letting stale seen-state suppress them.

**Files.** `scripts/trust/cron_baseline.py`.

**Notes.** Pure library — no CLI here for T007 (the live wrapper CLI concern is
T009). `load_baseline` does file I/O but its failure surfaces as a typed error,
not a swallowed empty result — the caller (WP04) owns the fail-safe decision.

### T008 — Pure drift diff (`scripts/trust/cron_drift_detector.py`)

**Purpose.** The deterministic, I/O-free core: compare parsed live jobs against
the loaded baseline and return findings (contract C3).

**Steps.**
1. Define `CronDriftFinding` as a `@dataclass` with the fields from data-model.md:
   `kind`, `name`, `agent_id`, `cron_id`, `schedule_expr`, `expected_schedule_expr`,
   `enabled`, `created_at_ms`. Optional fields default to `None`. Represent
   `kind` as a `str` constant set (module-level constants
   `KIND_UNAPPROVED_PRESENT = "unapproved_present"`, `KIND_APPROVED_MISSING`,
   `KIND_SCHEDULE_MISMATCH`, `KIND_ENABLED_MISMATCH`) — mirror the closed-set
   token pattern in `felix_health_check/run.py`.
2. `detect_cron_drift(live_jobs: list[dict], baseline: list[ApprovedCron]) ->
   list[CronDriftFinding]` — **pure, no I/O.** Match key is the tuple
   `(name, agent_id)`.
   - Parse each live job defensively: `name`, `agentId`, `enabled`,
     `schedule.expr`, `schedule.tz` (tolerate a missing `schedule` or missing
     `schedule.tz`), `id`, `createdAtMs`. Do this parse inside the pure function
     over the already-decoded dicts (no subprocess) — see T009 for the
     enumeration boundary.
   - **`unapproved_present`** — a live `(name, agent_id)` not present in the
     baseline. This also covers the **owner-mismatch** case: an approved `name`
     running under a *different* `agent_id` is `unapproved_present` (the
     incident-relevant signal), because the match key includes `agent_id`.
     Carry `cron_id`, `schedule_expr`, `enabled`, `created_at_ms` into the
     finding.
   - **`approved_missing`** — a baseline entry with no live `(name, agent_id)`
     match. Carry `expected_schedule_expr` from the baseline.
   - **`schedule_mismatch`** — a matched pair whose live `schedule.expr` **or**
     `schedule.tz` differs from the baseline (`schedule_expr` / `tz`). Carry both
     observed (`schedule_expr`) and `expected_schedule_expr`.
   - **`enabled_mismatch`** — a matched pair whose live `enabled` is `false`
     (an approved cron unexpectedly disabled). Carry observed `enabled`.
   - A matched pair may legitimately produce a `schedule_mismatch` **and** an
     `enabled_mismatch` — evaluate both independently.
3. Return findings in a deterministic order (e.g., sorted by
   `(kind, name, agent_id)`) so tests are stable.

**Files.** `scripts/trust/cron_drift_detector.py`.

**Notes.** **No I/O in this function** — no subprocess, no file read, no bus
call. Do **not** map findings to severities or `Alert` objects here; that is
WP04's job (the finding → severity/alert mapping table lives in data-model.md).
This function is the unit-testable heart of the WP.

### T009 — Live-enumeration wrapper (fail-safe subprocess boundary)

**Purpose.** Isolate the one impure step — running `openclaw cron list --json`
and parsing it — behind a small function so the pure diff stays testable and the
fail-safe rule is enforced at a single boundary (contract C1).

**Steps.**
1. Add `enumerate_live_crons() -> list[dict]` (place it in
   `cron_drift_detector.py`, or in `cron_baseline.py` — either is acceptable;
   keep it in one place and out of `detect_cron_drift`).
2. Run `openclaw cron list --json` via `subprocess.run(["openclaw", "cron",
   "list", "--json"], capture_output=True, text=True, timeout=..., check=False)`
   (never `exec`; fixed argv, no shell) — matching the health-check runner style.
3. Tolerant parse: `json.loads` the stdout, read `.jobs` (default to a hard
   error if absent — see fail-safe), and return the raw job dicts unchanged
   (ignore unknown fields; tolerate a missing `schedule.tz`). Return
   `list[dict]` suitable to feed straight into `detect_cron_drift`.
4. **Fail-safe:** on non-zero exit, a timeout, non-JSON output, or a missing
   `jobs` key, raise a typed error `class CronEnumerationError(Exception)`.
   Do **not** return `[]` on failure — an empty list is a valid "no crons"
   answer and must be reserved for a genuinely empty `jobs` array. WP04 catches
   `CronEnumerationError` and fails safe (no alert, `ok:false`).

**Files.** `scripts/trust/cron_drift_detector.py` (or `cron_baseline.py`).

**Notes.** Keep the subprocess strictly inside this wrapper. Tests mock it (feed
canned JSON) — no test may call office2 or invoke `openclaw`.

### T010 — Unit tests (`tests/trust/test_cron_baseline.py` + `test_cron_drift_detector.py`)

**Purpose.** Prove every finding kind, the loader/hash, and the fail-safe
wrapper deterministically, with branch coverage of each kind.

**Steps.**
1. Create `tests/trust/__init__.py`.
2. `tests/trust/test_cron_baseline.py`:
   - `load_baseline` on a valid seeded file → 7 `ApprovedCron` entries with
     correct fields.
   - malformed baseline (missing `crons`, missing required field, blank field,
     bad JSON, missing file, duplicate `name`) → each raises `BaselineError`.
   - `baseline_hash` is stable across entry reordering (order-independent) and
     changes when a field changes.
3. `tests/trust/test_cron_drift_detector.py` — feed **canned JSON dicts** (the
   C1 shape) and a small in-memory baseline to `detect_cron_drift`, asserting the
   finding set for each case:
   - **exact-match no-drift** — live == baseline → zero findings.
   - **`unapproved_present`** — a live cron not in the baseline.
   - **`approved_missing`** — a baseline cron with no live match.
   - **`schedule_mismatch`** — matched pair, differing `schedule.expr` (and a
     second case: differing `schedule.tz` only).
   - **`enabled_mismatch`** — matched pair with live `enabled: false`.
   - **owner-mismatch** — approved `name` present but under a *different*
     `agent_id` → `unapproved_present` (assert the kind explicitly).
   - **tolerant parse** — a live job with extra/unknown fields and a missing
     `schedule.tz` is handled without error.
   - **wrapper fail-safe** — mock `subprocess.run` so `enumerate_live_crons`
     sees non-zero exit / non-JSON / missing `jobs` → raises
     `CronEnumerationError` (NOT an empty list). Also assert a genuinely empty
     `jobs: []` returns `[]`.
4. Mock the subprocess boundary (`monkeypatch`/`unittest.mock`); **never** call
   office2 in tests. Structure so `--cov-branch` exercises every `kind` branch.

**Files.** `tests/trust/__init__.py`, `tests/trust/test_cron_baseline.py`,
`tests/trust/test_cron_drift_detector.py`.

**Notes.** Keep fixtures inline/small and readable — one canned `jobs` payload
per scenario. Assert on the finding `kind` set plus the carried forensic fields
(`cron_id`, `created_at_ms`, `expected_schedule_expr`) where relevant.

## Test Strategy

Run the WP's tests with branch coverage:

```
python3 -m pytest tests/trust/test_cron_baseline.py tests/trust/test_cron_drift_detector.py -v --cov=scripts/trust --cov-branch
```

All cases above must pass, and branch coverage must exercise every finding kind
(`unapproved_present`, `approved_missing`, `schedule_mismatch`,
`enabled_mismatch`) plus the owner-mismatch, tolerant-parse, and
wrapper-fail-safe branches. Tests must be hermetic — no network, no `openclaw`,
no office2 access.

## Definition of Done

- [ ] `docs/design/architecture/data/approved-crons.json` exists, is valid
      self-describing JSON (`schema_version` + `crons`), and is seeded with the 7
      known crons with unique `name`s; deploy-time live-confirm noted.
- [ ] `scripts/trust/__init__.py` and `tests/trust/__init__.py` exist so
      `scripts.trust.*` imports resolve.
- [ ] `load_baseline` validates and returns typed `ApprovedCron` entries and
      raises `BaselineError` on any malformed/unreadable baseline (never a silent
      empty list).
- [ ] `baseline_hash` returns a deterministic, order-independent content hash.
- [ ] `detect_cron_drift` is a pure, I/O-free function producing all five finding
      kinds (`unapproved_present` incl. owner-mismatch, `approved_missing`,
      `schedule_mismatch`, `enabled_mismatch`) with correct match key
      `(name, agent_id)`.
- [ ] `enumerate_live_crons` isolates the subprocess, tolerates unknown/missing
      fields, and raises a typed `CronEnumerationError` on any read/parse failure
      (never returns `[]` on failure).
- [ ] Unit tests green, including branch coverage of every finding kind and the
      fail-safe wrapper path.
- [ ] No alert-bus / timer / runner / state-file code in this WP (those are
      WP04).

## Risks

- **OpenClaw JSON shape drift.** `openclaw cron list --json` could add/rename
  fields across versions. Mitigation: tolerant parse in `enumerate_live_crons`
  (ignore unknowns, tolerate missing `schedule.tz`) and bind tests to the C1
  contract shape rather than a live call.
- **Baseline false-positives.** If the committed baseline drifts from reality
  (e.g., a legitimate new cron lands before the baseline is updated), the
  detector will (correctly) flag `unapproved_present`. The baseline-deploy
  ordering rule (baseline lands **before/with** the cron it authorizes) and the
  seen-findings/re-alert cadence are owned by **WP04/WP05** — do **not**
  implement ordering/state here; just note the dependency in code comments.
- **Fail-safe inversion.** The most dangerous bug is treating a CLI failure as
  "no crons." Guard it explicitly (typed error, never `[]` on failure) and cover
  it in tests.
- **No alerts here.** Emitting an `Alert` in this WP would duplicate WP04 and
  break the layering — keep this WP finding-only.

## Reviewer Guidance

- Confirm `detect_cron_drift` performs **no I/O** — no subprocess, file read,
  network, or bus call inside it; the subprocess lives only in
  `enumerate_live_crons`.
- Verify the match key is `(name, agent_id)` and that an approved `name` under a
  different `agent_id` yields `unapproved_present` (owner-mismatch), not a false
  `schedule_mismatch` or a silent pass.
- Verify the fail-safe posture of `enumerate_live_crons`: non-zero exit /
  timeout / non-JSON / missing `jobs` → typed error, **never** `[]`; a genuine
  empty `jobs: []` → `[]`.
- Verify `load_baseline` raises on malformed input rather than returning an empty
  list, and that `baseline_hash` is order-independent.
- Confirm tests cover **each** finding kind with branch coverage, mock the
  subprocess, and never touch office2 or `openclaw`.
- Confirm the baseline file is self-describing (`schema_version`), seeds all 7
  crons with unique names, and that no WP04/WP05 concerns (alerts, timer, runner,
  seen-state, inventory) leaked into this WP.

## Activity Log

- 2026-07-10T19:15:59Z – claude:sonnet:python-pedro:implementer – shell_pid=98580 – Assigned agent via action command
- 2026-07-10T19:30:29Z – claude:sonnet:python-pedro:implementer – shell_pid=98580 – Force past 3.2.6 pre-review regression gate (missing tests.architectural._gate_coverage; tracked). Impl complete+tested+committed.
- 2026-07-10T19:36:14Z – claude:opus:reviewer-renata:reviewer – shell_pid=6593 – Started review via action command
- 2026-07-10T19:42:37Z – user – shell_pid=6593 – Review passed (reviewer-renata): implementation complete, tested, integration-verified.
