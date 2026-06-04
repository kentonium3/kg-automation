# Contract: Reconciliation Cycle Pipeline

**Mission**: `felix-vikunja-sync-reconciliation-driver-01KTA1J3`
**Phase**: Plan / Phase 1 / contracts
**Date**: 2026-06-04

This document is the **interface contract** for the 6-phase reconciliation cycle. It enumerates each phase's inputs, outputs, error handling, and the invariants that must hold across phase boundaries. Implementation goes in `scripts/sync/cycle.py` and is exercised by `tests/sync/test_cycle.py`.

The architectural design of the cycle lives in [ADR-0003](../../../docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md). This contract translates the design into concrete pre/post conditions that the implementation and its tests can be checked against.

---

## Cycle entry point

The driver is invoked as:

```bash
python3 -m scripts.sync.driver
```

CLI flags (parsed in `scripts/sync/driver.py`):

| Flag | Type | Default | Purpose |
|---|---|---|---|
| `--cadence-seconds` | int | env `FELIX_SYNC_CADENCE_SECONDS` → 300 | Effective cadence. Used only for record-keeping (the timer enforces the actual tick rate). Floor 180, ceiling 600 — outside these the script exits 3 with `validation_error`. |
| `--state-dir` | path | env `FELIX_SYNC_STATE_DIR` → `/data/services/openclaw/state/sync` | State directory. |
| `--secrets-dir` | path | env `FELIX_SYNC_SECRETS_DIR` → `/data/services/openclaw/secrets` | Where to read `vikunja-api`. |
| `--api-base-url` | URL | env `FELIX_VIKUNJA_API_BASE_URL` → `https://office2.tail0f5f56.ts.net/api/v1/` | Vikunja API base URL. |
| `--whatsapp-recipient` | E.164 | env `FELIX_WHATSAPP_RECIPIENT` (required) | Operator's phone number. |
| `--dry-run` | bool | false | Run all phases; skip writes to state files AND skip the openclaw-CLI WhatsApp invocation. Used for testing and operator-driven probes. |
| `--bootstrap` | bool | false | First-run mode (see "Bootstrap" section). |
| `--help` | — | — | Standard argparse help. |

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Cycle completed successfully. |
| 1 | Cycle failed during a phase (Vikunja unreachable, classification panic, etc.). Health record contains the failure detail. Freshness pointer NOT advanced. |
| 2 | Cycle completed all read/diff/classify/emit phases but failed during `update` or `complete`. Conflict events ARE written to disk and ARE delivered (already committed); cache update and pointer advance FAILED. Operator must reconcile manually. |
| 3 | Validation error before any I/O (bad CLI args, env vars out of range, missing credential file). No state mutated. |

---

## Phase 1 — `fetch`

**Purpose**: Pull the current state of all tasks updated since the freshness pointer, plus any referenced projects not in the project cache.

**Inputs**:
- `FreshnessPointer.layers.status_and_task.last_polled_utc`
- `vikunja-api` token (from secrets file)
- Vikunja API base URL

**HTTP calls** (in order):
1. `GET {base}/tasks/all?updated_since={last_polled_utc}` — single delta poll covering status + task layers. Returns a list of changed tasks with their full payload.
2. For each unique `project_id` referenced by the returned tasks NOT already in `ProjectCacheRecord`: `GET {base}/projects/{id}`.

**Outputs**:
- In-memory list of `VikunjaTask` payloads (dicts; structure validated post-fetch)
- Updated `ProjectCacheRecord` (just-in-time, in-memory only — not yet persisted)

**Error handling**:
- HTTP timeout (10s default per call): propagate as cycle error. Exit code 1.
- HTTP 5xx: propagate. Exit code 1.
- HTTP 4xx: propagate. Exit code 1. (4xx on the `vikunja-api` token signals credential rotation or revocation — operator action required.)
- Malformed JSON (decode failure): propagate. Exit code 1.
- Project fetch failure: logged as a warning; affected tasks proceed but UC-3 evaluation gracefully degrades for those tasks (treats project_id as "unknown project" — does not fire UC-3 due to insufficient info).

**Invariants**:
- The `updated_since` parameter is the EXACT value of `FreshnessPointer.layers.status_and_task.last_polled_utc`. No clock-skew adjustment.
- The cycle records the wall-clock `started_at_utc` at the moment of THIS phase entry. That timestamp becomes the candidate next-pointer value, advanced only after `complete` succeeds.

---

## Phase 2 — `diff`

**Purpose**: Compare each fetched Vikunja task's tracked fields against the corresponding `TaskCacheRecord`. Emit a `DivergenceCandidate` for each (task, field) pair whose Vikunja value differs from the cached value.

**Inputs**:
- Fetched task payloads (from phase 1)
- `TaskCacheRecord` (current state, on disk)

**Outputs**:
- List of `DivergenceCandidate` in-memory tuples: `(task_id, field, vikunja_value, felix_cached_value, vikunja_updated_at)`.

**Per-field comparison**:
- Field set is `TRACKED_TASK_FIELDS` (constant in `scripts/sync/state.py`).
- Comparison uses Python equality after canonical normalization:
  - Datetime fields normalized to ISO-8601 UTC string before compare.
  - Lists (labels, assignees) sorted before compare.
  - String fields compared verbatim (Vikunja's behavior on whitespace is preserved).
- "Not in cache" (first observation of a task) does NOT fire a divergence. The diff phase records "first observation" → all tracked fields written to cache without classify/emit. This is the unambiguous bootstrap behavior.

**Invariants**:
- The diff phase is pure (no I/O, no state mutation). Output depends only on inputs.
- Privacy-boundary tasks: their tracked-field set in the cache is empty; the diff phase therefore never produces divergence candidates for them. They are tracked solely for their continued existence.

---

## Phase 3 — `classify`

**Purpose**: Apply UC-1..UC-4 (UC-1 collapsed with UC-2 per research.md Unknown 3) to each `DivergenceCandidate` and label it `auto_resolved` or `unsafe_to_auto_resolve` with reason codes.

**Inputs**:
- List of `DivergenceCandidate` (from phase 2)
- Static "downstream-affecting field" whitelist (`scripts/sync/classify.py` constant): `{due_date, project_id, done, repeat_after, repeat_mode, title}` (operator-overridable in a future config).
- Static "manual override" markers: presence of the label `felix:ignore` on the task, or `[NO FELIX]` prefix in the title.

**Classification rules** (in order):
1. **UC-1 / UC-2 (collapsed)** — divergence from cache: ALWAYS fires when the candidate's `vikunja_value != felix_cached_value`. By definition of how DivergenceCandidate is constructed (the diff phase only emits a candidate when values differ), this rule ALWAYS adds the reason code `uc1_uc2_divergence` to every candidate. Unsafe by default unless the candidate is overridden by neither UC-3 nor UC-4 being applicable, in which case "unsafe by virtue of having diverged at all."
2. **UC-3 — downstream behavior depends on this field**: if `field ∈ downstream_affecting_fields` → adds reason code `uc3_downstream_behavior`. Strengthens "unsafe" classification.
3. **UC-4 — manual override signal**: if the task has the `felix:ignore` label OR `[NO FELIX]` title prefix → adds reason code `uc4_manual_override`. The presence of UC-4 INVERTS the class to `auto_resolved` (the operator has explicitly signaled "don't bother me about this task"). This is the only criterion that downgrades rather than upgrades.

**Resulting class**:
- `unsafe_to_auto_resolve`: any reason code present AND no UC-4 override
- `auto_resolved`: UC-4 override present, OR (theoretically) a DivergenceCandidate that doesn't actually represent a divergence — impossible given phase 2's semantics, but the implementation defensively handles the empty-reasons case as `auto_resolved`.

**Outputs**:
- List of `ClassifiedConflict` tuples adding `class` and `unsafe_reasons` to each candidate.

**Invariants**:
- Pure function. No I/O. Identical inputs → identical outputs (deterministic).
- Reason codes are the only field driving downstream guard and delivery decisions.

---

## Phase 4 — `emit`

**Purpose**: For each ClassifiedConflict, apply guards (G-1/G-2/G-3 in order), compute `event_id`, append a `ConflictEvent` row to the JSONL log, and — for unsafe-class events that pass all guards — dispatch the WhatsApp delivery.

**Inputs**:
- List of `ClassifiedConflict` (from phase 3)
- Current `guard-state.json` (G-3 daily cap state)
- Recent slice of `conflict-events.jsonl` (G-1 dedup lookback; last 24h)
- `TaskCacheRecord` (G-2 post-write suppression check)

**Guard application order**:
1. **G-3 (hard daily cap)** — first because it's the cheapest check and the most catastrophic limit. If the cap is reached, ALL subsequent unsafe events this cycle are suppressed. Logged as `suppressed_by_g3`.
2. **G-2 (post-Felix-write suppression)** — checks `felix_last_observed_at` per the field. If within 30 minutes, suppress. Logged as `suppressed_by_g2`.
3. **G-1 (24h dedup by event-id stem)** — checks recent JSONL events. If a matching stem has been delivered or auto-resolved in the last 24h, suppress. Logged as `suppressed_by_g1`.

`auto_resolved` events are NOT subject to guards (they don't trigger WhatsApp). They are appended to the log directly.

**`event_id` computation** (deterministic, idempotent):

```python
def event_id(layer: str, entity_id: int, field: str, ts_observed_utc: str, value: object) -> str:
    canonical_value = json.dumps(value, sort_keys=True, separators=(",", ":"))
    payload = f"{layer}|{entity_id}|{field}|{ts_observed_utc}|{canonical_value}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
```

Re-running the same cycle on the same fetched data produces identical `event_id` values, so retries do not duplicate log rows when combined with a "skip if event_id already in log" pre-check (idempotency property).

**WhatsApp delivery (unsafe + all guards passed)**:
- Build the 3-line message per `contracts/whatsapp-send.md`
- Invoke `scripts/sync/send_whatsapp.send(...)` (which calls the openclaw CLI per `contracts/whatsapp-send.md`)
- Record the result in the event's `delivery_status` and `delivery_error` fields
- Increment `guard-state.json.g3_daily_cap.unsafe_pings_sent_today`

**Outputs**:
- N JSONL rows appended to `conflict-events.jsonl`
- Possibly one or more openclaw CLI invocations (success or failure recorded per event)
- Updated `guard-state.json` (if any unsafe event was delivered)

**Error handling**:
- JSONL append failure: cycle error. Exit code 2 (already-classified events may have partial delivery; cache NOT updated; pointer NOT advanced).
- openclaw CLI failure: NOT a cycle error. Logged in the event's `delivery_error` field; the cycle continues.

**Invariants**:
- Every `ClassifiedConflict` produces exactly ONE `ConflictEvent` row (idempotency by `event_id` enforces this).
- Suppressed events ARE logged (with `delivery_status` reflecting the guard) — never silently dropped.
- The order events are processed within the cycle is determined by `vikunja_updated_at` ascending — this gives consistent G-1 behavior under multi-field divergence on the same task.

---

## Phase 5 — `update`

**Purpose**: Replace the diverged fields in `TaskCacheRecord` with Vikunja's values (Vikunja wins, C-002). Update `ProjectCacheRecord` with any newly-fetched projects. Update `felix_last_observed_at` timestamp for every task seen this cycle.

**Inputs**:
- Original `TaskCacheRecord` (read at cycle start)
- Fetched task payloads
- In-memory list of accepted (non-error) ClassifiedConflicts from phase 4

**Outputs**:
- Updated `TaskCacheRecord` (in-memory, not yet persisted)
- Updated `ProjectCacheRecord` (in-memory)

**Update rules**:
- For each fetched task: replace cached `fields[*]` with Vikunja's tracked fields, set `vikunja_updated_at` to Vikunja's `updated`, set `felix_last_observed_at` to cycle's `started_at_utc`.
- For privacy-boundary tasks: only `vikunja_updated_at` and `felix_last_observed_at` are updated; `fields` stays empty.
- For tasks NOT fetched this cycle: untouched (no change to `felix_last_observed_at`).
- For new tasks (first observation): full record created in cache.

**Invariants**:
- The update phase is the ONLY phase that may overwrite TaskCacheRecord fields.
- `felix_last_observed_at` strictly monotonic: never goes backward.
- This phase does NOT advance the freshness pointer (that's phase 6).

---

## Phase 6 — `complete`

**Purpose**: Atomically commit all in-memory state changes to disk. Advance the freshness pointer. Write the per-tick health record.

**Inputs**:
- In-memory updated `TaskCacheRecord`
- In-memory updated `ProjectCacheRecord`
- Cycle's `started_at_utc` (the new freshness pointer value)
- Cycle's tick_id, duration, events_emitted counts, layer pointer before/after

**Writes** (in order, fail-fast):
1. `task-cache.json` — atomic replace (write to `.tmp`, fsync, rename).
2. `project-cache.json` — atomic replace if changed.
3. `freshness.json` — atomic replace with new pointer value.
4. `last-tick.json` — atomic replace with the cycle's health record (success path).

**Failure during this phase**:
- File 1 fails → cycle exits with code 2. Events already in JSONL + delivered. Cache stale.
- File 2 or 3 fails → same as file 1; cycle code 2.
- File 4 fails → cycle code 1 (cache may be advanced but health record won't reflect it — corner case; operator notices the failure via the next tick's freshness pointer mismatch).

**Invariants**:
- All four writes use the atomic-replace pattern (write `.tmp`, fsync, rename) to prevent torn writes on power loss.
- The freshness pointer is the LAST piece of state advanced. If anything else fails before this, the next cycle re-polls from the unchanged pointer.
- Success of `complete` is the ONLY signal that the cycle succeeded. Health record writes "cycle_error: null" only after all four files land.

---

## Cross-phase invariants

The pipeline as a whole satisfies:

- **Atomicity at the pointer level**: a cycle either advances the freshness pointer or doesn't. Partial-progress cycles re-poll the same delta next cycle, idempotently.
- **At-least-once event semantics**: events may be re-emitted if a cycle fails between `emit` and `complete`. Idempotency by `event_id` prevents downstream observers from seeing duplicates.
- **No silent failure**: every phase records its outcome in either the success-path health record (overwrite) or the failure stream (append). Operator can always diagnose what happened on the most recent tick.

---

## Bootstrap (first run)

Invoked with `--bootstrap`. Behavior differs from the standard cycle:

1. `fetch` uses `updated_since=0001-01-01T00:00:00Z` (Vikunja's epoch zero) — pulls all task state.
2. `diff` short-circuits: every task is treated as "first observation."
3. `classify` and `emit` are skipped entirely.
4. `update` writes the full cache from scratch.
5. `complete` advances the freshness pointer to `started_at_utc`.

Bootstrap runs **once at install time**. The operator invokes it manually per `quickstart.md`. After bootstrap, subsequent ticks run the standard cycle.

---

## Testing contract

`tests/sync/test_cycle.py` covers (at minimum):

- Each phase tested in isolation with mocked I/O
- End-to-end cycle with mocked Vikunja HTTP + mocked openclaw CLI subprocess
- Failure injection at every phase boundary (verifies exit codes and freshness-pointer behavior)
- Idempotency: re-run identical fetched data → no duplicate JSONL rows
- Bootstrap path: empty cache → full cache after one --bootstrap invocation
- Privacy-boundary path: task tagged for `02-Growth/_private/` → cache fields stays empty
- UC-4 inversion: divergence on a task labeled `felix:ignore` → class is `auto_resolved`

The test approach mirrors `tests/habits/test_record_completion.py` (mocked `urllib.request.urlopen`, mocked `subprocess.run`). No live integration tests per memory `feedback_no_live_integration_tests`.
