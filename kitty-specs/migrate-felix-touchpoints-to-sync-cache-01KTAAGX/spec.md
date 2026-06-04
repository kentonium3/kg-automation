# Specification: Migrate Felix Touchpoints to Sync Cache

**Mission ID**: `01KTAAGXA149W5F6GVW5N8N5XW`
**Mission slug**: `migrate-felix-touchpoints-to-sync-cache-01KTAAGX`
**Source issue**: [#519](https://github.com/kentonium3/kg-automation/issues/519) (sub-issue of Epic [#507](https://github.com/kentonium3/kg-automation/issues/507))
**Builds on**: [#518 — Sync reconciliation driver foundation](https://github.com/kentonium3/kg-automation/issues/518) (merged `cf74f33e`; deployed to office2 2026-06-04 21:48 UTC)

---

## Overview

Mission #518 delivered the centralized sync reconciliation driver — a deterministic Python module on a 5-minute systemd cadence that polls Vikunja, detects divergences from a local cache, and routes unsafe-class conflicts to the operator's WhatsApp. The driver is now running on office2 and producing `task-cache.json` + `freshness.json` on every successful tick.

But the cache exists in isolation. Felix's 18 existing Vikunja-touching read callsites — enumerated exhaustively as TP-01 through TP-18 in #518's RQ-2 research — continue to issue direct Vikunja HTTP reads. The cache is a write-only artifact from their perspective. Until those callsites migrate, the cache provides no operator-facing value and the driver's overhead is unjustified.

This mission migrates all 18 read callsites to consume the cache. Each migration is a **clean cutover**: the old direct-Vikunja-read code is deleted in the same change that introduces the cache read. There is no fallback path, no runtime config flag, no coexistence period. When a touchpoint cannot serve its read from the cache (cache file missing, freshness pointer stale beyond per-touchpoint SLA, specific task absent from cache), the touchpoint surfaces a structured error to stderr and exits non-zero — never silently falls back to direct Vikunja.

Write callsites are **not** migrated by this mission. Felix's existing sub-agents continue to POST/PUT/DELETE against Vikunja directly; the driver remains read-only. Read-after-write within a single script run will see the previous cycle's snapshot until the next driver tick captures the new write — an acceptable lag at #518's locked 5-minute cadence.

The migration adds one new shared helper: `scripts/common/sync_cache.py` — the canonical entry point for cache reads. All 18 touchpoints route through it; no touchpoint imports `scripts.sync.state` directly.

---

## User Scenarios & Testing

The actors are the **operator** (Kent — affected indirectly through changed touchpoint behavior) and the **touchpoint scripts themselves** (the consumers of the cache). Acceptance scenarios describe how the system behaves after migration; edge cases describe correctness boundaries the implementation must respect.

### Acceptance scenarios

**AS-1 — Steady-state read serves from cache**
The sync driver is running on office2 with cycles completing successfully. A touchpoint (e.g., `scripts/habits/query_active_habits_v2.py`) is invoked. It loads the cache from `/data/services/openclaw/state/sync/task-cache.json`, filters the tasks per its existing semantics, and returns the same result it would have returned with the old direct-Vikunja-read path. Zero Vikunja HTTP calls.

**AS-2 — Cache missing surfaces structured error**
A touchpoint is invoked before the driver has been bootstrapped (or after the state directory was manually cleared). The touchpoint detects the missing cache file, writes a structured error to stderr identifying the touchpoint, the expected cache path, and the recovery action (`python3 -m scripts.sync.driver --bootstrap`), and exits with a non-zero status code. The operator sees a clear actionable message.

**AS-3 — Stale freshness pointer surfaces structured error**
The driver has not ticked successfully for longer than the touchpoint's freshness SLA (e.g., 15 minutes for a habits check-in callsite). The touchpoint reads the freshness pointer first, compares against its SLA, and surfaces a structured error naming the SLA threshold and the actual pointer age. Exit non-zero.

**AS-4 — Task not in cache (Vikunja added a task after the last driver tick)**
A touchpoint that addresses a task by ID (e.g., `record_completion.py` reading task 14 to verify its state) finds the cache populated and fresh, but the specific task ID is not present. The touchpoint surfaces a structured error naming the missing task ID and the cache's `last_polled_utc`. Exit non-zero. The touchpoint does NOT fall back to a direct Vikunja read.

**AS-5 — Field-set match**
A touchpoint reads only fields in #518's `TRACKED_TASK_FIELDS` (`title`, `done`, `due_date`, `project_id`, `repeat_after`, `repeat_mode`, `labels`). The cache returns those fields verbatim; the touchpoint's downstream logic produces identical output to the pre-migration direct-read path.

**AS-6 — Field-set expansion (plan-phase decision)**
A touchpoint reads a field NOT in `TRACKED_TASK_FIELDS` (e.g., `description`, `percent_done`). Plan phase enumerates these cases and produces a plan-phase decision: either extend `TRACKED_TASK_FIELDS` (with the downstream consequence of widening the conflict-event surface) OR redesign the touchpoint to not require that field. No silent widening of the field set during implement.

**AS-7 — Private-project task in cache (privacy boundary)**
A touchpoint reads a task that belongs to a `02-Growth/_private/` project. The cache entry exists but its `fields` dict is empty (privacy redaction applied at the driver's diff phase). The touchpoint detects the empty-fields case and treats it identically to "task data unavailable" — surfaces a structured error to stderr. The touchpoint does NOT fall back to a direct Vikunja read for private tasks.

### Edge cases

**EC-1 — Cache file present but corrupted (malformed JSON)**
`sync_cache.read_cached_tasks()` raises `OSError` with a clear "cache file unreadable" message. Touchpoint propagates. Operator recovery: re-bootstrap.

**EC-2 — Cache schema version mismatch**
`scripts/sync/state.py`'s schema-version guard raises `OSError` on read. Touchpoint propagates. Operator recovery: re-bootstrap or coordinate with a future schema migration mission.

**EC-3 — Multiple touchpoints invoked concurrently**
The cache file is read-only from touchpoints' perspective; the driver is the sole writer. POSIX read semantics handle concurrent reads safely; touchpoints do NOT need to coordinate with each other.

**EC-4 — Touchpoint invoked during a driver tick (read during atomic-replace window)**
The driver writes state files via the atomic-replace pattern (`.tmp` → `os.replace`). At any instant the touchpoint sees either the pre-tick state or the post-tick state; never a partial-write. Verified by #518's existing tests.

**EC-5 — Cache freshness pointer is from a previous driver process generation**
The driver was restarted (e.g., systemd unit reloaded). The new process reads the prior freshness pointer and continues from there. Touchpoints see no special case; the freshness pointer's UTC timestamp is the source of truth.

**EC-6 — Touchpoint's SLA threshold is reached during the same invocation**
A touchpoint that runs longer than its own SLA threshold (rare; touchpoints are typically sub-second) does NOT re-check freshness mid-invocation. The single freshness check at the top of the touchpoint is the contract; SLA is checked once per invocation.

---

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | A new shared helper module is introduced at the canonical Felix shared-script location. The module exposes the three primary cache-read entry points used by all touchpoints: a full-cache read returning all tracked tasks, a single-task lookup by integer task_id, and a freshness-check function returning the current pointer value. Touchpoints do not import driver-internal modules directly; they route every cache read through this helper. | Locked |
| FR-002 | The helper performs the freshness check per the caller-supplied SLA threshold. If the pointer is older than the threshold, the helper raises an OSError with a structured message identifying the SLA, the pointer age, and the recovery action. | Locked |
| FR-003 | The helper detects missing cache files, schema-version mismatches, and malformed JSON. Each failure mode raises an OSError with a structured message identifying the failure class and the recovery action. The helper NEVER returns silent defaults (e.g., empty dict, None) for unrecoverable errors. | Locked |
| FR-004 | All 18 touchpoints enumerated in #518's RQ-2 research (TP-01 through TP-18) migrate to use the helper in this mission. No subset, no batched rollout. Each migration is a clean cutover — the old direct-Vikunja-read code is removed in the same change that introduces the cache read. | Locked |
| FR-005 | Each migrated touchpoint operates identically to its pre-migration self when the cache is healthy, fresh, and contains the required task(s). Output is byte-for-byte unchanged for the steady-state path. | Locked |
| FR-006 | Each migrated touchpoint surfaces a structured stderr error and exits non-zero when the cache is missing, stale, the requested task is absent, or the task's fields are empty (privacy redaction). No touchpoint silently falls back to direct Vikunja under any condition. | Locked |
| FR-007 | Each touchpoint has a per-callsite freshness SLA assigned during plan phase. The SLA reflects the touchpoint's time-sensitivity (e.g., a habit check-in invoked at a specific clock minute has a tighter SLA than a daily sweeper). SLAs are documented in plan.md, surfaced as named constants in the touchpoint, and tested. | Locked |
| FR-008 | Plan phase enumerates every field each touchpoint reads from the cache. Any field outside `TRACKED_TASK_FIELDS` triggers an explicit plan-phase decision recorded in plan.md: either expand `TRACKED_TASK_FIELDS` in `scripts/sync/diff.py` (with the documented downstream consequence on the conflict-event surface and #516 forward-compatibility) OR redesign the touchpoint to not require that field. No silent widening during implement. | Locked |
| FR-009 | Each migrated touchpoint has unit-test coverage via a shared cache-state mock fixture provided in a new `tests/common/conftest.py`. The fixture supports parameterizing the cache contents, the freshness pointer, and the private-project list. Touchpoint tests reuse this fixture instead of re-implementing per-touchpoint mocks. | Locked |
| FR-010 | Write callsites (POST/PUT/DELETE against Vikunja) are NOT migrated by this mission. The driver remains read-only against Vikunja per #518's C-003. Touchpoints that read-after-write within a single script run continue to observe the 5-minute lag inherent in the driver's cadence. | Locked |

---

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Per-touchpoint invocation latency post-migration is no worse than pre-migration latency. | Pre-migration latency measured for each touchpoint in plan phase; post-migration latency MUST NOT regress by more than 10% (95th percentile) | Locked |
| NFR-002 | Cumulative Vikunja HTTP read volume across all 18 touchpoints, measured over 24 hours of steady-state operation. | Reduces by ≥ 95% versus pre-migration baseline (Vikunja's only remaining HTTP-read source from Felix is the sync driver itself) | Locked |
| NFR-003 | Helper module file-read overhead per invocation. | Single file read per touchpoint invocation; ≤ 50 ms at current cache size (≤ 100 tasks) | Locked |
| NFR-004 | The shared mock fixture in `tests/common/conftest.py` enables a touchpoint test suite to run without any live state directory, urlopen call, or subprocess. | 100% of new and updated touchpoint tests pass under fully mocked I/O. No live-state test mode added. | Locked |
| NFR-005 | Operator-visible error messages from any failure path (missing cache, stale, missing task, schema mismatch, malformed JSON) include the touchpoint name, the expected cache path, the failure class, and the recovery action. | All five enumerated failure paths verified by tests | Locked |
| NFR-006 | Post-migration code search confirms zero remaining direct-Vikunja-read patterns in the migrated touchpoints (no `urlopen` against Vikunja, no `requests.get` against the Vikunja base URL). | `grep` audit of the migrated files returns zero hits for the pre-migration patterns | Locked |

---

## Constraints

| ID | Constraint | Source | Status |
|----|-----------|--------|--------|
| C-001 | Clean-cutover migration: each touchpoint's old direct-Vikunja-read code is deleted in the same change that introduces the cache read. No fallback path. No runtime config flag. No coexistence period. | Operator decision Q1 (2026-06-04) | Locked |
| C-002 | No silent fallback to Vikunja under any condition (cache-miss, stale, missing task, private-project empty fields). All failure paths surface structured stderr errors and non-zero exit codes. | Inherited from #518 Constitutional Compliance § Failure behavior; reinforced by Q1 decision | Locked |
| C-003 | Driver remains read-only against Vikunja. Write callsites are NOT migrated by this mission. | Inherited from #518 C-003 | Locked |
| C-004 | Touchpoints route every cache read through `scripts/common/sync_cache.py`. No touchpoint imports `scripts.sync.state` or other driver-internal modules directly. This keeps the driver's internal schema decoupled from touchpoint code. | Architectural decision (this spec) — preserves cache schema evolution flexibility | Locked |
| C-005 | Privacy boundary mirrors #518's C-009. Touchpoints treat empty-fields cache entries (private-project tasks) identically to "task data unavailable" → structured stderr error. Never fall back to direct Vikunja for private-project tasks. | Inherited from #518 C-009; Felix Constitution privacy boundary | Locked |
| C-006 | Migration order proceeds by domain cluster, in this sequence: `scripts/habits/` → `scripts/escalation/` → `scripts/openclaw/agents/felix-admin-*/` → `scripts/tasker/` → `scripts/enrichment/`. Each domain cluster is one WP. The `sync_cache.py` helper + shared mock fixture are a foundation WP that precedes all cluster WPs. | Operator-derived migration prudence (habits has highest precedent and blast radius; escalation next; agent prompts third because of cross-references to habits/escalation cache patterns) | Locked |
| C-007 | Field-set expansion (`TRACKED_TASK_FIELDS`) is a plan-phase decision. Any touchpoint reading a field outside the current 7-field set forces an explicit choice recorded in plan.md. Implement phase MUST NOT silently widen the field set. | Locked from #519 issue body Risk Considerations | Locked |
| C-008 | All touchpoint test suites run with fully mocked I/O via the new `tests/common/conftest.py` fixture. No live `/data/services/openclaw/state/sync/` interaction, no live network calls. | Inherited from memory `feedback_no_live_integration_tests`; reinforced by this spec | Locked |

---

## Success Criteria

| ID | Criterion (measurable, technology-agnostic) | Verification |
|----|--------------------------------------------|--------------|
| SC-001 | After mission merges and deploys to office2, none of the 18 migrated touchpoints make any HTTP call to Vikunja during a normal invocation. | Manual: run each touchpoint via its standard entry point with the cache healthy; observe network traffic (e.g., via stderr logging that surfaces the helper's read path); confirm zero Vikunja HTTP calls per touchpoint per invocation. |
| SC-002 | When the sync driver is stopped on office2 (the freshness pointer ages beyond every touchpoint's SLA), every touchpoint invocation surfaces a structured "stale freshness" stderr error and exits non-zero — no touchpoint produces incorrect or silent output. | Manual: `systemctl --user stop felix-vikunja-sync.timer`; wait beyond max SLA; invoke each touchpoint; observe stderr + exit code. |
| SC-003 | When `task-cache.json` is removed from the state directory (cache-missing condition), every touchpoint invocation surfaces a structured "cache missing" stderr error naming the recovery command. | Manual: rename the cache file; invoke each touchpoint; observe stderr + exit code. |
| SC-004 | Cumulative Vikunja HTTP read volume from Felix to Vikunja over 24 hours drops by ≥ 95% versus the pre-migration baseline. | Manual: capture pre-migration Vikunja access-log count of GET requests sourced from Felix's token (24-hour window); compare to post-migration window; compute reduction. |
| SC-005 | Habit check-in flow (the highest-volume touchpoint domain) produces identical operator-visible output (same morning WhatsApp message, same set of habits, same order) for at least 7 consecutive days post-migration when compared to a pre-migration baseline of 7 prior days. | 7-day observation window post-deployment with daily comparison to prior-7-day baseline. |
| SC-006 | A simulated "Vikunja added a task after the driver's last tick" condition (the requested task ID is not in the cache) produces a structured stderr "task not in cache" error from the affected touchpoint and exits non-zero, without falling back to direct Vikunja. | Manual: create a task in Vikunja UI; before the next driver tick, invoke a touchpoint that references that task by ID; observe stderr + exit code. |
| SC-007 | Private-project tasks (empty-fields cache entries) cause every touchpoint that would read their fields to surface a structured "task data unavailable" stderr error and exit non-zero, with no leak of the task title or other content to logs. | Manual: create a private-project task in Vikunja UI; trigger a driver tick to populate the cache with the redacted entry; invoke a relevant touchpoint; observe stderr + exit code; verify no task title or content appears in any operator-visible output. |
| SC-008 | All migrated touchpoints have unit-test coverage that runs without any live state directory or network interaction. The test suite for each touchpoint can be invoked in isolation (per-file pytest invocation) and passes. | `python3 -m pytest tests/<domain>/<touchpoint>.py -q` returns 0 for every migrated touchpoint. |
| SC-009 | A code audit confirms zero remaining direct-Vikunja-read patterns in the migrated files. | `grep -E 'urlopen\\|requests\\.get' scripts/habits/ scripts/escalation/ scripts/openclaw/agents/felix-admin-* scripts/tasker/ scripts/enrichment/ --include='*.py'` returns zero hits matching the Vikunja base URL or the existing direct-read patterns. |

---

## Key Entities

| Entity | Purpose | Owns |
|--------|---------|------|
| **`sync_cache` helper module** | Canonical cache-read entry point for all touchpoints. Wraps `scripts/sync/state.read_task_cache()` + `read_freshness()` plus per-touchpoint SLA enforcement. | The three primary entry points (`read_cached_tasks`, `read_cached_task_by_id`, `read_freshness_pointer`), the SLA check logic, the canonical error-message formatting. |
| **Migrated touchpoint (each of 18)** | An existing Felix script that previously issued direct Vikunja HTTP reads; now reads from the cache via the helper. | Its own pre-migration logic minus the direct-read code, plus a single call into the helper at the read site, plus an SLA constant. |
| **Shared mock cache fixture** | Test substrate enabling every touchpoint's tests to run under fully mocked I/O. Provided in `tests/common/conftest.py`. | A pytest fixture that injects synthetic `TaskCacheRecord` content, a configurable `last_polled_utc`, and a configurable private-project list. |
| **Per-touchpoint SLA constant** | The freshness threshold (in seconds) for one touchpoint. Reflects time-sensitivity of that callsite. | Local to each migrated touchpoint as a module-level constant; documented in plan.md. |
| **Field-set audit deliverable (plan-phase only)** | Enumeration of every field each touchpoint reads, cross-referenced against `TRACKED_TASK_FIELDS`. Drives the plan-phase decision on field-set expansion. | Recorded in `plan.md` and `research.md`; no in-code artifact. |

---

## Assumptions

The plan phase must validate each assumption before implementation work begins. Probe office2 and the touchpoints' live behavior to confirm.

- **A-1**: The sync driver is running on office2 with cycles completing successfully (verified 2026-06-04 21:48 UTC; 50 tasks + 7 projects in cache; cycle_error: null). Plan phase confirms it is still running at planning time.
- **A-2**: All 18 touchpoints enumerated in #518's RQ-2 still exist on `main` and have not been removed or reorganized since the research mission closed. Plan phase verifies by file existence + line citations from RQ-2.
- **A-3**: The cache schema (`TaskCacheRecord` from `scripts/sync/state.py`) is stable for the duration of this mission. No schema migrations land in parallel.
- **A-4**: All 18 touchpoints read tasks but do NOT read projects (TP-01..TP-18 are all task-scoped per RQ-2). Project-layer reads land in #520. Plan phase confirms by re-checking every touchpoint's read pattern.
- **A-5**: Operator-driven recovery for any failure mode is `python3 -m scripts.sync.driver --bootstrap` followed by `systemctl --user start felix-vikunja-sync.timer` if stopped. The runbook (`docs/runbooks/sync-driver-ops.md`) is the authoritative recovery procedure; this mission does not introduce additional recovery flows.
- **A-6**: The Felix sub-agents that invoke these touchpoints via `python3 -m scripts.…` shell-outs (e.g., AGENTS.md Step 2 patterns) do not need agent-prompt changes. The touchpoint's CLI surface, exit codes, and stderr semantics remain compatible with how the agents currently invoke them. If a touchpoint's exit-code semantics change, the relevant AGENTS.md is reviewed and updated as part of the same WP.
- **A-7**: There exists no touchpoint that does `for task in fetch_all_active_tasks(): write_via_vikunja_api(task); read_back_via_vikunja_api(task)` in a tight loop within a single invocation. If such a touchpoint exists, plan phase surfaces it as needing special treatment (since the cache will not reflect the just-written state); A-7 will be falsified if RQ-2's catalog reveals such a pattern.

---

## Out of Scope

- Project-layer touchpoints (none currently inventoried per RQ-2). Tracked as #520.
- Migration of write callsites. Felix sub-agents continue to write directly to Vikunja; only reads migrate.
- Adding new touchpoints. This is a migration mission, not a feature mission.
- Modifying the sync driver itself (`scripts/sync/`). Out of scope; tracked as future work (e.g., the #525 janitor follow-ups address driver-internal cleanup separately).
- RRULE-based recurrence handling (upstream `go-vikunja#2032`; tracked as #506).
- Coexistence of cache-read + direct-read patterns. Q1 locked clean cutover.
- A runtime configuration flag to disable cache reads. Q1 rejected as out of scope.
- Field-set expansion as a default decision. Each expansion is explicitly recorded in plan.md per FR-008.
- Modification of the sync driver's cadence, freshness-pointer behavior, or conflict-event log. All inherited from #518.

---

## References

- **Parent epic**: [#507 — Felix-Vikunja bi-directional sync foundation](https://github.com/kentonium3/kg-automation/issues/507)
- **Source issue**: [#519 — Feature: Migrate Felix touchpoints to sync cache](https://github.com/kentonium3/kg-automation/issues/519)
- **Direct prerequisite (deployed)**: [#518 — Sync reconciliation driver foundation](https://github.com/kentonium3/kg-automation/issues/518) (merged `cf74f33e`; deployed to office2 2026-06-04 21:48 UTC)
- **Research substrate (touchpoint catalog)**: [`docs/research/felix-vikunja-sync-architecture/findings/rq-2-touchpoints.md`](../../docs/research/felix-vikunja-sync-architecture/findings/rq-2-touchpoints.md) — exhaustive enumeration of TP-01..TP-18
- **Sync driver state contract**: [`scripts/sync/state.py`](../../scripts/sync/state.py) — `TaskCacheRecord`, `read_task_cache`, `read_freshness`
- **Sibling implementation mission**: [#520 — Feature: Project-layer sync + deletion handling + URL normalization](https://github.com/kentonium3/kg-automation/issues/520) (independent)
- **Tracked follow-up (orthogonal)**: [#525 — P3-debt: post-mission janitor cleanup for #518](https://github.com/kentonium3/kg-automation/issues/525) (does NOT block this mission)
- **Forward-compat target**: [#516 — Felix observability and emission framework](https://github.com/kentonium3/kg-automation/issues/516) — `TRACKED_TASK_FIELDS` expansion decisions (FR-008) must remain forward-compatible with #516's three framework outcomes inherited from #518.
- **Operator runbook**: [`docs/runbooks/sync-driver-ops.md`](../../docs/runbooks/sync-driver-ops.md) — authoritative recovery procedures.
