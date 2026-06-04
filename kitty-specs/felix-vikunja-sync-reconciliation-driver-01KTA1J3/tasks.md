# Work Packages: Felix-Vikunja Sync Reconciliation Driver

**Mission**: `felix-vikunja-sync-reconciliation-driver-01KTA1J3`
**Mission ID**: `01KTA1J3FH87XJWT7FQPT1EZE7`
**Date**: 2026-06-04
**Branch contract**: planning_base_branch=`main`; merge_target_branch=`main`
**Mission type**: software-dev
**Change mode**: regular

This document decomposes the plan into 6 work packages (WP01–WP06) covering 25 subtasks. Each WP is independently implementable with mocked tests; WP05 and WP06 integrate the prior outputs. The 6-WP structure trades parallelism (limited — the pipeline data flow is largely linear) for clean ownership boundaries — every Python module ends up in exactly one WP, and no two WPs touch the same source file.

The WP execution order (and dependency graph) is:
- WP01 (Foundation: state.py + http.py) — no deps
- WP02 (Read pipeline: fetch.py + diff.py) — depends on WP01
- WP03 (Judgment: classify.py + guards.py) — depends on WP02
- WP04 (Output pipeline: send_whatsapp.py + emit.py) — depends on WP03
- WP05 (Orchestration: cycle.py + driver.py) — depends on WP01..WP04
- WP06 (Deployment + docs: systemd units + runbook + arch doc updates) — depends on WP05

---

## Subtask Index (reference table — `[P]` indicates parallel-safe within the WP, not status)

| ID   | Description | WP | Parallel |
|------|-------------|----|----------|
| T001 | `scripts/sync/__init__.py` package marker | WP01 | — | [D] |
| T002 | `scripts/sync/state.py` — atomic JSON I/O + FreshnessPointer / TaskCacheRecord / ProjectCacheRecord / PerTickHealthRecord / GuardState schemas | WP01 | — | [D] |
| T003 | `scripts/sync/http.py` — `urllib.request` wrapper with timeout, structured errors, JSON parse | WP01 | [D] |
| T004 | `tests/sync/test_state.py` — atomic-write roundtrip, schema validation, recovery from corrupted file | WP01 | [D] |
| T005 | `tests/sync/test_http.py` — mocked `urlopen` happy path + timeout + HTTPError + non-2xx + non-JSON body | WP01 | [D] |
| T006 | `scripts/sync/fetch.py` — `GET /tasks/all?updated_since=<ts>` + just-in-time `GET /projects/{id}` for unknown projects | WP02 | — | [D] |
| T007 | `scripts/sync/diff.py` — value comparison with canonical normalization; first-observation behavior | WP02 | — | [D] |
| T008 | `tests/sync/test_fetch.py` — mocked Vikunja responses, partial-failure on project fetch, error propagation | WP02 | [D] |
| T009 | `tests/sync/test_diff.py` — comparison matrix, first-observation skip, privacy-boundary redaction | WP02 | [D] |
| T010 | `scripts/sync/classify.py` — UC-1/UC-2 collapsed, UC-3 whitelist, UC-4 inverter; deterministic | WP03 | — | [D] |
| T011 | `scripts/sync/guards.py` — G-1 (24h dedup), G-2 (30-min post-write), G-3 (daily cap) | WP03 | — | [D] |
| T012 | `tests/sync/test_classify.py` — full classification matrix; UC-4 inversion; private-task path | WP03 | [D] |
| T013 | `tests/sync/test_guards.py` — G-1 lookback, G-2 timing window, G-3 day rollover | WP03 | [D] |
| T014 | `scripts/sync/send_whatsapp.py` — `SendResult` dataclass, subprocess wrapper, 3-line message formatter | WP04 | — | [D] |
| T015 | `scripts/sync/emit.py` — deterministic `event_id`, guard application order, JSONL append, delivery dispatch | WP04 | — | [D] |
| T016 | `tests/sync/test_send_whatsapp.py` — exit-code paths, timeout, FileNotFoundError, dry-run, message formatter | WP04 | [D] |
| T017 | `tests/sync/test_emit.py` — `event_id` idempotency, guard interactions, log append failure path | WP04 | [D] |
| T018 | `scripts/sync/cycle.py` — 6-phase orchestration; atomic state commit at `complete` | WP05 | — | [D] |
| T019 | `scripts/sync/driver.py` — argparse CLI surface, env-var resolution, bootstrap mode, exit codes 0/1/2/3 | WP05 | — | [D] |
| T020 | `tests/sync/test_cycle.py` — end-to-end mocked cycle, per-phase failure injection, bootstrap path, atomicity | WP05 | [D] |
| T021 | `tests/sync/test_driver.py` — CLI surface, missing-env validation, bootstrap flag, dry-run flag | WP05 | [D] |
| T022 | `scripts/sync/systemd/felix-vikunja-sync.service` — systemd user service unit | WP06 | — |
| T023 | `scripts/sync/systemd/felix-vikunja-sync.timer` — 5-min cadence timer | WP06 | [P] |
| T024 | `docs/runbooks/sync-driver-ops.md` — operator runbook (install / bootstrap / observe / recover) | WP06 | [P] |
| T025 | `docs/design/architecture/data/{service-inventory,signal-to-doc-map}.json` + `docs/INDEX.md` updates per `change-control.md` | WP06 | [P] |

---

## WP01 — Foundation: state I/O + HTTP wrapper

**Goal**: Lay down the storage and HTTP primitives every downstream module imports. No business logic; purely deterministic plumbing.

**Priority**: Setup. Blocks WP02 onward.

**Independent test**: With WP01 alone, the test suite can roundtrip JSON files atomically and mock-call Vikunja's HTTP API — sufficient to verify all foundation contracts in isolation.

**Estimated prompt size**: ~320 lines.

**Included subtasks**:
- [x] T001 `scripts/sync/__init__.py` package marker (WP01)
- [x] T002 `scripts/sync/state.py` — atomic JSON I/O + state schemas (WP01)
- [x] T003 `scripts/sync/http.py` — urllib wrapper (WP01)
- [x] T004 `tests/sync/test_state.py` — atomic-write tests (WP01)
- [x] T005 `tests/sync/test_http.py` — HTTP wrapper tests (WP01)

**Implementation sketch**:
1. Create `scripts/sync/__init__.py` (empty package marker).
2. Implement `state.py` with `atomic_write_json(path, data)` mirroring `scripts/habits/sweeper.py:_atomic_write_json` (write `.tmp` + fsync + `os.replace`). Include reader/writer helpers per entity (FreshnessPointer, TaskCacheRecord, ProjectCacheRecord, PerTickHealthRecord, GuardState).
3. Implement `http.py` modeled on `scripts/habits/record_completion.py:_http_request` (urllib + 10s default timeout, raises OSError on non-2xx or network failure, returns `(status, parsed_json_or_none)`).
4. Tests use `tmp_path` for state I/O and `unittest.mock.patch` for urlopen.

**Parallel opportunities**: T003 (http.py) is independent of state I/O. T004 + T005 can be written in parallel within the WP.

**Dependencies**: None.

**Risks**:
- Atomic-write pattern must handle the `tmp` file naming collision case (concurrent runs would conflict; mitigated by the timer's serialized invocation).
- HTTP wrapper must not retry on network failure within a single call (driver's outer loop handles retry via the next cycle, not in-call).

**FR coverage**: FR-003 (freshness pointer storage), FR-008 (last-tick.json storage), FR-009 (read-only HTTP foundation), FR-010 (no silent failure — errors propagate as OSError).

---

## WP02 — Read pipeline: Vikunja fetch + value diff

**Goal**: Pull delta changes from Vikunja and identify divergences from the driver's cache. Pure data transformation; no judgment or side effects.

**Priority**: Foundational. Blocks WP03 onward.

**Independent test**: Mocked Vikunja responses + a synthetic cache → emit a list of `DivergenceCandidate` tuples matching the expected diff matrix.

**Estimated prompt size**: ~360 lines.

**Included subtasks**:
- [x] T006 `scripts/sync/fetch.py` — Vikunja delta poll + project fetch (WP02)
- [x] T007 `scripts/sync/diff.py` — value comparison (WP02)
- [x] T008 `tests/sync/test_fetch.py` — mocked Vikunja paths (WP02)
- [x] T009 `tests/sync/test_diff.py` — comparison matrix (WP02)

**Implementation sketch**:
1. `fetch.py`: one function `fetch_delta(token, base_url, since_utc, known_project_ids) → FetchedDelta` that calls `http.get(...)` for `/tasks/all?updated_since=<ts>` and then iterates per-task to fetch any project_id not in `known_project_ids`. Returns a dataclass with `tasks: list[dict]`, `projects: dict[int, dict]`, `vikunja_version: str`.
2. `diff.py`: `compute_divergences(fetched_tasks, task_cache, tracked_fields) → list[DivergenceCandidate]`. Pure function. First observation produces no candidate (recorded internally as "new"). Canonical normalization: ISO-8601 datetimes, sorted list fields.
3. Tests: mock Vikunja JSON payloads, verify project-fetch failure gracefully degrades to "unknown project" without aborting the whole fetch.

**Parallel opportunities**: T008 + T009 parallel within the WP. Across WPs: WP02 can start once WP01's `http.py` + `state.py` types are merged on lane.

**Dependencies**: WP01.

**Risks**:
- Vikunja's `updated_since` endpoint may have edge behavior at the exact second boundary; mitigated by comparison on the value cache, not on the timestamp.
- Clock skew between Felix and Vikunja: handled per spec EC-5 (use Vikunja's `updated` for ordering, Felix's wall clock for `ts_observed_utc` only).

**FR coverage**: FR-002 (phases 1-2 of the pipeline), FR-009 (read-only).

---

## WP03 — Judgment: UC classification + delivery guards

**Goal**: Classify each divergence into `auto_resolved` or `unsafe_to_auto_resolve` (UC-1..UC-4), and prepare the three guards that gate WhatsApp delivery.

**Priority**: Core. Blocks WP04.

**Independent test**: Synthetic `DivergenceCandidate` lists → expected `ClassifiedConflict` outputs covering all classification combinations. Guards tested in isolation against synthetic event logs.

**Estimated prompt size**: ~370 lines.

**Included subtasks**:
- [x] T010 `scripts/sync/classify.py` — UC classification (WP03)
- [x] T011 `scripts/sync/guards.py` — G-1, G-2, G-3 (WP03)
- [x] T012 `tests/sync/test_classify.py` — classification matrix (WP03)
- [x] T013 `tests/sync/test_guards.py` — guard semantics (WP03)

**Implementation sketch**:
1. `classify.py`: `classify(candidate: DivergenceCandidate, downstream_fields: set[str], override_signal_present: Callable[[task], bool]) → ClassifiedConflict`. The UC-1/UC-2 collapse: divergence implies `uc1_uc2_divergence` always present. UC-3 if `candidate.field ∈ downstream_fields`. UC-4 inverts class to `auto_resolved` regardless of other criteria. Pure function.
2. `guards.py`: `apply_guards(event, recent_events_24h, task_cache, guard_state) → GuardDecision` returning `("approve", None)` or `("suppress", reason_code)`. G-3 first (cheapest), then G-2 (cache lookup), then G-1 (recent-events scan).
3. Tests: a matrix of (field, in_downstream_set, has_felix:ignore) and expected `(class, unsafe_reasons)` pairs. Plus guard-by-guard tests for the three suppression cases.

**Parallel opportunities**: T012 + T013 parallel within the WP.

**Dependencies**: WP02 (uses `DivergenceCandidate` type).

**Risks**:
- The "downstream-affecting field" whitelist is a soft default in research.md. Initial set: `{due_date, project_id, done, repeat_after, repeat_mode, title}`. Operator can override via a configuration mechanism in a future mission; not in this scope. **Implementer notes the default constant in `classify.py` and surfaces it in the WP05 driver CLI** so it can be inspected.
- G-1 dedup performance: scanning the full `conflict-events.jsonl` is O(n). At current log size this is negligible; at 100MB+ it becomes notable. Mitigation: read in reverse byte-stream chunks and stop at the first row older than 24h. Documented as an optimization for future work.

**FR coverage**: FR-005 (UC classification), FR-007 (G-1/G-2/G-3 guards), NFR-002 (≤1/day cap).

---

## WP04 — Output pipeline: WhatsApp send + conflict-event emit

**Goal**: Format and deliver unsafe-class WhatsApp messages; append every classified event to the JSONL log idempotently.

**Priority**: Core. Blocks WP05.

**Independent test**: Synthetic `ClassifiedConflict` lists + guard outcomes → expected JSONL rows + subprocess invocations. Send-helper tested with mocked `subprocess.run`.

**Estimated prompt size**: ~380 lines.

**Included subtasks**:
- [x] T014 `scripts/sync/send_whatsapp.py` — subprocess wrapper + message formatter (WP04)
- [x] T015 `scripts/sync/emit.py` — event_id, JSONL append, guard application, delivery dispatch (WP04)
- [x] T016 `tests/sync/test_send_whatsapp.py` — exit-code paths (WP04)
- [x] T017 `tests/sync/test_emit.py` — event_id idempotency, guard interactions (WP04)

**Implementation sketch**:
1. `send_whatsapp.py`: implement `send(*, message, recipient, agent="main", timeout_seconds=60, dry_run=False) → SendResult` per `contracts/whatsapp-send.md`. Subprocess invocation MUST match the documented argument order exactly. Never raises; all failures return a SendResult.
2. Also in `send_whatsapp.py`: `format_message(event: ConflictEvent) → str` producing the 3-line shape per `contracts/whatsapp-send.md`. Privacy-boundary tasks: redact title and field name.
3. `emit.py`: 
   - `event_id(layer, entity_id, field, ts_observed_utc, vikunja_value) → str` — sha256 prefix per the schema contract.
   - `emit_events(classified_conflicts, guards, jsonl_path, send_callable, recipient) → list[ConflictEvent]`. For each conflict: apply guards (G-3, G-2, G-1 in order), build the event row, append to JSONL atomically (per-line), invoke send_callable if unsafe and approved, return the list of committed rows.
4. Tests: 
   - `event_id` is deterministic across re-runs with same inputs
   - JSONL append failure does NOT silently drop the event; surfaces as an exception
   - G-3 cap state correctly increments and persists between events within one cycle
   - Privacy redaction applied at format time

**Parallel opportunities**: T016 + T017 parallel within the WP.

**Dependencies**: WP03 (uses `ClassifiedConflict` + guard decisions).

**Risks**:
- JSONL append must use `write(line + "\n")` followed by `flush()` to ensure atomicity per single line. No partial-line state must be possible.
- The `--dry-run` mode in `send_whatsapp.send` must not invoke `subprocess.run` (verified by the test asserting `mock_subprocess.run.call_count == 0` in dry-run path).

**FR coverage**: FR-004 (15-field log), FR-006 (WhatsApp delivery + 3-line shape), FR-007 (guard application in emit phase).

---

## WP05 — Orchestration: cycle pipeline + driver CLI

**Goal**: Compose the 6-phase cycle from WP01..WP04 modules and expose a CLI invokable by systemd. Bootstrap mode handles first-run state population.

**Priority**: Integration. Blocks WP06.

**Independent test**: End-to-end mocked cycle with full I/O patched, plus per-phase failure injection covering all cycle exit-code semantics. Bootstrap test verifies empty-state initial population.

**Estimated prompt size**: ~430 lines.

**Included subtasks**:
- [x] T018 `scripts/sync/cycle.py` — 6-phase orchestration (WP05)
- [x] T019 `scripts/sync/driver.py` — CLI + bootstrap + exit codes (WP05)
- [x] T020 `tests/sync/test_cycle.py` — end-to-end with mocked I/O + failure injection (WP05)
- [x] T021 `tests/sync/test_driver.py` — CLI surface tests (WP05)

**Implementation sketch**:
1. `cycle.py`: `run_cycle(config: CycleConfig, dry_run: bool) → CycleResult`. Orchestrates fetch → diff → classify → emit → update → complete. State writes happen only in `complete` (atomic). Failure at any phase exits with the appropriate code (1 for pre-emit phases, 2 for emit-onward where partial commit may have occurred).
2. `driver.py`: argparse + env-var resolution per `contracts/cycle-pipeline.md` § "Cycle entry point". `--bootstrap` short-circuits the cycle to read all Vikunja state and seed the cache. Exit code 3 on validation failure (before any I/O).
3. Tests: 
   - End-to-end mocked: all 6 phases execute, last-tick.json reflects success
   - Failure at phase N: subsequent phases NOT executed, last-tick.errors.jsonl appended, freshness pointer unchanged
   - Bootstrap: empty state directory → populated state files after `--bootstrap` invocation
   - Atomicity: simulated SIGTERM between emit (rows appended) and complete (cache not advanced) → next cycle re-processes via `event_id` dedup

**Parallel opportunities**: T020 + T021 parallel within the WP.

**Dependencies**: WP01, WP02, WP03, WP04. All four foundation/pipeline WPs must be merged on the mission lane before this WP's tests can run end-to-end.

**Risks**:
- Atomic-replace race against system shutdown: `os.replace` is POSIX-atomic; on a non-POSIX environment this would need different handling, but office2 is Linux.
- The "phases NOT executed after failure" invariant requires careful structure in `cycle.py` — early-exit on first phase error. Tests verify this with mocked phase functions returning failures at each boundary.

**FR coverage**: FR-001 (cadence CLI surface + env), FR-002 (full pipeline), FR-003 (pointer advance only on success), FR-008 (last-tick.json write), FR-010 (cycle errors surface — exit codes + structured stderr).

---

## WP06 — Deployment: systemd units + operator runbook + architecture docs

**Goal**: Produce the systemd user units, the operator runbook, and the architecture-doc updates per the change-control protocol. Deployment to office2 is a separate manual operator step (not part of the WP).

**Priority**: Final. Wraps the mission for release.

**Independent test**: Static review — the systemd unit files parse with `systemd-analyze verify`; the runbook covers all SC verification commands from `quickstart.md`; the JSON docs validate per `tooling/scripts/validate_docs.py`.

**Estimated prompt size**: ~390 lines.

**Included subtasks**:
- [ ] T022 `scripts/sync/systemd/felix-vikunja-sync.service` (WP06)
- [ ] T023 `scripts/sync/systemd/felix-vikunja-sync.timer` (WP06)
- [ ] T024 `docs/runbooks/sync-driver-ops.md` (WP06)
- [ ] T025 Architecture data + INDEX updates per change-control (WP06)

**Implementation sketch**:
1. `felix-vikunja-sync.service`: systemd user unit with `ExecStart=/usr/bin/python3 -m scripts.sync.driver`, `Environment=FELIX_WHATSAPP_RECIPIENT=+16179300916`, `Environment=FELIX_VIKUNJA_API_BASE_URL=https://office2.tail0f5f56.ts.net/api/v1/`, `WorkingDirectory=/home/claude/kg-automation`. Match the existing pattern in any deployed user unit (look at `~/.config/systemd/user/` on office2 during implement-phase live-probe).
2. `felix-vikunja-sync.timer`: `OnUnitInactiveSec=300s` (5-min cadence), `Persistent=true`.
3. `docs/runbooks/sync-driver-ops.md`: distilled from `quickstart.md`, formatted as a Felix-standard runbook (frontmatter + sections). Include all SC verification commands.
4. `docs/design/architecture/data/service-inventory.json`: add the `felix-vikunja-sync` service entry. `docs/design/architecture/data/signal-to-doc-map.json`: add the runbook to the `runbook-added` change class. `docs/INDEX.md`: add the new runbook to the runbooks list. `docs/DEVELOPER_PORTAL.md`: add to onboarding sitemap if the driver is operator-facing (it is — observability and recovery are operator concerns).

**Parallel opportunities**: T023, T024, T025 are mostly independent of each other; T022 + T023 share the systemd-unit concern.

**Dependencies**: WP05 (uses the driver entry point in the systemd unit's `ExecStart`).

**Risks**:
- `signal-to-doc-map.json` and `service-inventory.json` are JSON sources of truth; per CLAUDE.md, machine-readable wins on conflict. Validate with `tooling/scripts/validate_docs.py` before claiming WP done.
- Runbook completeness: cross-reference every SC in `spec.md` against a verification command in the runbook. Missing coverage is a reviewer rejection.

**FR coverage**: FR-001 (timer cadence), NFR-001 (latency budget set by 5-min timer), NFR-005 (operator-observable stopped-driver via runbook commands).

---

## Parallel-execution summary

The data flow is largely linear (WP02 → WP03 → WP04 → WP05 → WP06). Lane-level parallelism within the mission is limited. Spec-kitty's `finalize-tasks` will compute lanes accordingly. **In practice, expect sequential lane execution** with each WP merging to the mission's lane branch before the next starts.

Within a single WP, the `[P]` markers in the Subtask Index indicate test files that can be written in parallel with their corresponding source files (e.g., T004 in parallel with T002).

---

## MVP scope recommendation

**WP01 + WP02 + WP05 (driver + cycle, without classify/emit/output)** is technically the smallest meaningful slice — a driver that reads Vikunja, detects divergences, but does NOT classify or emit events. This would surface raw divergence counts in `last-tick.json` and provide observability into the sync surface without operator-facing pings.

Per the operator's planning decision ("operational reliability is the priority"), we are **not** recommending this MVP cut. Ship the full mission. The added WP03/WP04 cost is small compared to the value of the unsafe-class signal and conflict log audit trail.

---

## Next: Implement

Once `finalize-tasks` and `map-requirements` complete, this mission is ready for `/spec-kitty.implement`. The natural starting point is `spec-kitty agent action implement WP01 --agent <name>` (no dependencies — foundation).
