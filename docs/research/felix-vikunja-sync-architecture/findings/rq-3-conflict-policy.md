---
rq_id: "RQ-3"
title: "Conflict policy and log shape"
depends_on: ["RQ-1", "RQ-2"]
wp: "WP02"
tags: [507, 516]
---

# RQ-3 — Conflict Policy and Log Shape

**Scope**: Defines conflict detection, classification, unsafe-class criteria, WhatsApp surfacing
format, and volume guard mechanism for the Felix-Vikunja sync architecture. Depends on WP01
outputs (RQ-1 Vikunja API surface, RQ-2 touchpoint inventory, RQ-5 pattern fit). Conflict-event
log schema is captured in `findings/conflict-event-log.sketch.md` (T007/T008 output).

**Locked constraints (non-negotiable inputs)**:
- C-002: Vikunja wins all conflicts.
- C-003: Silent in steady-state; log first; WhatsApp only for unsafe class.
- C-004: Idempotency is first-class.

---

## 1. Conflict Detection Mechanism

A conflict is detected during the `diff` phase of the Reconciliation Cycle
(`data-model.md` § Reconciliation Cycle). The cycle runs as:

1. **fetch** — `GET /tasks/all?updated_since=<last_polled_utc>` (per RQ-1 § 5.3;
   evidence-log row `2026-06-03T23:51:00Z` citing `vikunja-api-tasks-updated-since`).
   Returns only tasks whose `updated` field changed since the previous poll cycle.

2. **diff** — For each returned task, compare Vikunja's field values against Felix's
   cached state snapshot for that `task.id`. Felix's cache is the local JSONL ledger
   (`habits-history.jsonl` and analogous per-domain files) plus the freshness pointer
   file written at cycle completion.

3. **classify** — For each differing field, apply the unsafe-class criteria in § 3 below.
   If any criterion fires, the event is `unsafe_to_auto_resolve`; otherwise
   `auto_resolved`.

4. **emit** — Append a conflict event to the conflict-event log. Route
   `unsafe_to_auto_resolve` events to the WhatsApp router per § 4.

5. **update** — Accept Vikunja's value as canonical (C-002). Update Felix's cached state.

6. **complete** — Write freshness pointer (`last_polled_utc`) so the next cycle can
   use `updated_since`.

**Stable identifier anchor**: `id` (integer) is the correct primary key for
cross-cycle re-identification (RQ-1 § 4; evidence-log row `2026-06-03T23:51:00Z`
citing `mem-reference-vikunja-id-vs-identifier`). `identifier` (e.g., `#1`) is
used only for human-readable WhatsApp ping content.

---

## 2. Conflict Classification

Two initial conflict classes (extensible per `schema_version` — see
`conflict-event-log.sketch.md`):

| `conflict_class` | Description | Default routing |
|---|---|---|
| `auto_resolved` | Vikunja value diverged from Felix's cache, but automatic acceptance is safe | log only |
| `unsafe_to_auto_resolve` | At least one unsafe criterion fires (§ 3); automatic acceptance could lose operator intent or produce incorrect downstream behavior | log + WhatsApp ping |

---

## 3. Unsafe-to-Auto-Resolve Criteria

Each criterion is **testable from conflict-event fields alone** — no out-of-band
lookup required. Evaluation occurs during the `classify` phase using the
`felix_state_snapshot`, `vikunja_state_snapshot`, and `ts_emitted_utc` fields
of the conflict event.

### Criterion UC-1: `kent_edit_after_felix_write`

**Definition**: Vikunja's `updated` timestamp for the conflicting field is *more recent*
than Felix's `ts_emitted_utc` (the timestamp Felix last wrote that field), indicating the
operator edited the field after Felix's most recent write.

**Test predicate (evaluable from conflict-event fields)**:
```
vikunja_state_snapshot.updated > felix_state_snapshot.ts_last_write_utc
  AND conflict is on a field Felix writes
```

**Include**: Yes. This is the canonical "stale-write" class that motivated Epic #507
(mission #408 WP01 task_id mis-binding). Felix computing a new `due_date` and
overwriting a manually set `due_date` is an instance of this criterion.

**Worked example — TP-05 (`set_due_dates.py`)**: TP-05 writes `due_date` on all
active habit tasks (evidence-log row `2026-06-03T23:51:00Z`, citation
`code-scripts-habits-set-due-dates`). If Kent manually sets `due_date` to a different
value in Vikunja UI, then TP-05 runs and overwrites it, the next reconciliation cycle
detects `vikunja_state_snapshot.due_date ≠ felix_state_snapshot.due_date` *and*
`vikunja_state_snapshot.updated > felix_state_snapshot.ts_last_write_utc`. This fires
UC-1. Route: log + WhatsApp ping.

**Worked example — TP-06 (`sweeper.py`)**: TP-06 advances `due_date` on completion
or reschedule (evidence-log row `2026-06-03T23:51:00Z`, citation
`code-scripts-habits-sweeper`). Same pattern — if Kent moves the due date manually
between sweeper runs, UC-1 fires on the next cycle.

---

### Criterion UC-2: `operator_authored_field`

**Definition**: The conflicting field's value in Vikunja was authored by the `kent`
user, not by `felix-bot`. Detectable from `vikunja_state_snapshot.created_by.username`
(for task-level creates) or, for field-level edits, from the task's `updated` timestamp
being more recent than the last Felix write with `felix_state_snapshot.last_writer = "felix-bot"`.

**Test predicate**:
```
vikunja_state_snapshot.created_by.username != "felix-bot"
  OR (felix_state_snapshot.last_writer == "felix-bot"
      AND vikunja_state_snapshot.updated > felix_state_snapshot.ts_last_write_utc)
```

**Include**: Yes. Operator-originated content should not be silently overwritten.
A task Kent created directly in Vikunja UI will have `created_by.username = "kent"`;
if Felix's reconciliation would modify it (e.g., label it, set a due date), this
criterion fires to surface the action.

**Worked example — TP-13 (`vikunja_writer.py`)**: `vikunja_writer.py` creates
alert tasks in the Inbox project (evidence-log row `2026-06-03T23:51:00Z`, citation
`code-scripts-security-vikunja-writer`). If a task with the same title already exists
(operator-created), Felix should not silently duplicate or overwrite it. UC-2 fires,
routing the event to WhatsApp so Kent can adjudicate.

---

### Criterion UC-3: `downstream_behavior_depends`

**Definition**: The conflicting field is one that downstream Felix agents act on
to produce externally-visible effects (WhatsApp messages, completions, due-date
advances). Automatic acceptance of a stale or wrong value would produce an incorrect
downstream action before the next reconciliation cycle corrects it.

**Load-bearing fields in this category** (from RQ-2 write-set survey):
- `done` / `done_at` — controls whether morning check-in lists the task
- `due_date` — controls sweeper advancement and morning-checkin filtering
- `repeat_after` / `repeat_mode` — controls recurrence computation
- `title` — controls WhatsApp ping content (incorrect task name in a ping is confusing)

**Test predicate**:
```
diff_field IN ["done", "done_at", "due_date", "repeat_after", "repeat_mode", "title"]
  AND conflict_class == "auto_resolved"  # re-classify to unsafe if field is load-bearing
```

**Include**: Yes. This is a distinct criterion from UC-1 because it fires even when
Felix hasn't recently written the field — the *value itself* is what matters, not
the recency of Felix's write. If Vikunja's `done=true` differs from Felix's cache
`done=false` on a habits task, that changes what the morning check-in delivers to
Kent.

**Worked example — TP-01 (`record_completion.py`)**: TP-01 writes `done=true` to
Vikunja and records to JSONL (evidence-log row `2026-06-03T23:51:00Z`, citation
`code-scripts-habits-record-completion`). If Vikunja shows `done=false` on a task
Felix marked done (Felix's cache says `done=true`), the diff is `done` field
discrepancy. UC-3 fires because `done` is downstream-behavior-dependent.

---

### Criterion UC-4: `manual_override_signal`

**Definition**: The conflict-event's `felix_state_snapshot` contains a recorded
"do not overwrite" marker — a flag or annotation that a previous reconciliation cycle
(or the operator via WhatsApp) placed to suppress automatic resolution on this field.

**Test predicate**:
```
felix_state_snapshot.override_flags contains {field: <conflicting_field>, expires_at: <future>}
```

**Include**: Yes, with caveat. This criterion is **prospective** — it requires that
the conflict-event schema and Felix's cache support an `override_flags` sub-object.
WP03's recommendation will determine whether this mechanism is part of the initial
implementation scope or a follow-on. It is included here because the unsafe-class
criterion set must be forward-extensible; omitting it creates a design gap.

**Worked example**: Kent responds "skip" on a WhatsApp habits ping for a task. Felix
records `state=rescheduled` in JSONL and sets `override_flags: [{field: "done", expires_at: end-of-day}]`.
If a stale sync later produces a `done=true` value, UC-4 fires to prevent
re-completing a task Kent explicitly deferred.

---

### Criterion Evaluation Summary

| Criterion | Include | Testable from log fields | Requires out-of-band | Worked example TP |
|---|---|---|---|---|
| UC-1 `kent_edit_after_felix_write` | Yes | Yes (`updated` vs `ts_last_write_utc`) | No | TP-05, TP-06 |
| UC-2 `operator_authored_field` | Yes | Yes (`created_by.username` or `last_writer`) | No | TP-13 |
| UC-3 `downstream_behavior_depends` | Yes | Yes (field name lookup in static list) | No | TP-01 |
| UC-4 `manual_override_signal` | Yes (prospective) | Yes (if override_flags in cache) | No | habits skip flow |

All four criteria are evaluated from conflict-event fields alone, satisfying the
`data-model.md` § Unsafe-Class testability requirement.

---

## 4. WhatsApp Ping Format

Per C-003: succinct, ≤3 lines, `conflict_class + Vikunja entity ID + diff_summary`.
The `identifier` field (e.g., `#14`) is used for human-readable context; `id` (integer)
is the internal anchor.

**Template**:
```
⚠ Felix sync conflict — task #<identifier> (id:<id>)
Field: <field_name> | Felix had: <felix_value> → Vikunja has: <vikunja_value>
Reason: <criterion_name>. Vikunja accepted (C-002). [Reply "ack" to silence follow-ups.]
```

**Example (UC-1, TP-05 due_date)**:
```
⚠ Felix sync conflict — task #7 (id:14)
Field: due_date | Felix had: 2026-06-04T23:59:00Z → Vikunja has: 2026-06-10T23:59:00Z
Reason: kent_edit_after_felix_write. Vikunja accepted. [Reply "ack" to silence follow-ups.]
```

**Example (UC-3, TP-01 done)**:
```
⚠ Felix sync conflict — task #3 (id:5)
Field: done | Felix had: true → Vikunja has: false
Reason: downstream_behavior_depends. Vikunja accepted. [Reply "ack" to silence follow-ups.]
```

**Format rationale**: Three-line format stays within WhatsApp's message-preview
threshold. The `identifier` field is human-readable (RQ-1 § 4 verdict); the `id`
is machine-stable. `[Reply "ack"]` provides a feedback loop for noise calibration
without requiring operator action for every event.

**Noise-floor calibration**: see § 5 (Volume Estimate, T010) below.

---

## 5. Volume Estimate (T010 — NFR-003 Enforcement)

**NFR-003 target**: unsafe-class WhatsApp pings ≤ 1/day in steady-state.
**Noise floor**: 4× daily IDLE WhatsApps from inbox-cron (memory
`feedback_idle_pings_acceptable_for_now`; evidence-log row added below as WP02 row).

### Math

**Inputs**:
- Active habit tasks tracked by Felix: ~10 (based on 14 habits-layer tasks in
  Habits project, ~10 active on any given day from probe data). Conservative: 15.
- Felix write operations per day per task: habits TP-01 (1× per completion event,
  ~1/day per task), TP-05/TP-06 (1× per morning cron + 1× per evening cron = ~2/day).
  Total Felix-initiated writes per task per day: ~3.
- Probability that Kent manually edits a field Felix is also writing: estimated
  at ~5% per write-day per task. This is conservative-toward-noisier: Kent uses
  Vikunja UI daily for review but rarely edits Felix-managed fields mid-cron.
- Field-conflict detection rate (fraction of diffs that trip an unsafe criterion):
  given C-002 (Vikunja wins), any Kent edit after a Felix write trips UC-1. Any
  Felix overwrite of a downstream field trips UC-3 if Vikunja diverges. Estimate:
  75% of detected diffs trip at least one criterion (conservative).

**Calculation**:
```
daily_felix_writes = 15 tasks × 3 writes/task/day = 45 write events/day
probability_kent_edits_same_field = 0.05  (5% per write event)
raw_conflict_events_per_day = 45 × 0.05 = 2.25 conflicts/day
fraction_unsafe = 0.75
raw_unsafe_per_day = 2.25 × 0.75 = ~1.69 unsafe-class pings/day
```

**This exceeds NFR-003 (> 1/day).** A guard mechanism is required.

### Guard Mechanism

**Guard G-1: Stable-state suppression (primary guard)**

If the same `{vikunja_entity_id, field_name}` tuple has already been pinged within
a 24-hour rolling window, suppress additional pings for that tuple. Emit only once
per field per entity per day. This is directly implementable using the `count_rolling`
mechanism from the signal pipeline (RQ-5, Pattern 1; evidence-log row
`2026-06-03T23:51:00Z`, citing `mem-feedback-signal-driven-doc-audit`).

**Guard G-1 re-estimate**:
```
After G-1: each unique field×entity pair fires at most once per 24h.
Active tracked tasks: 15; conflict-prone fields per task: ~2 (due_date, done).
Unique pairs: 15 × 2 = 30 max, but conflict probability is 5%.
Expected unique-pair conflicts per day: 30 × 0.05 = 1.5 pairs/day
Fraction unsafe: 0.75 → 1.5 × 0.75 = 1.13 pings/day
```

Still marginally above 1/day. Apply Guard G-2.

**Guard G-2: Auto-quiet during active Felix-write window**

During the 30-minute window following a scheduled cron run (when Felix itself
wrote the field), automatically suppress conflict pings for fields Felix just
wrote. This eliminates the false-positive class where Felix's own write creates
a race condition with the next poll cycle. Rationale: if Felix just wrote
`due_date`, and the next poll cycle runs within the write-window, the diff is
likely a timing artifact, not a genuine Kent edit.

**Guard G-2 re-estimate**:
```
Morning cron writes at ~06:00; evening sweeper at ~22:00.
Write window suppression covers 2× 30-min windows = 1h/day per script.
Fraction of poll cycles in a write window: 1h / (5-min cadence × 24h) ≈ 1/24 ≈ 4%.
This does not dramatically change the per-day count, but eliminates false-positive
class where Felix races itself. Adjusted: -0.1 pings/day → ~1.03/day.
```

**Guard G-3: Threshold-based daily cap (final backstop)**

Apply a hard cap: max 1 unsafe-class WhatsApp ping per day, regardless of unique
pairs. Events that would exceed the cap are still logged (C-003: log first); they
are simply not routed to WhatsApp. The rolling-window count in the signal pipeline
handles this cap natively (`count_rolling` threshold = 1/day).

**Guard G-3 final estimate**: ≤ 1 unsafe-class WhatsApp ping/day. ✓

### Summary

| Guard | Mechanism | Without | After |
|---|---|---|---|
| G-1 | 24h per-field-per-entity dedup | 1.69/day | 1.13/day |
| G-2 | 30-min post-write suppression | 1.13/day | ~1.03/day |
| G-3 | Hard daily cap (log-only above threshold) | 1.03/day | ≤ 1/day |

**NFR-003 passes** with all three guards active. Events above the cap are logged
and counted; Kent can review the conflict-event log if the daily cap seems to be
masking signal.

**Noise-floor context**: With all guards, 1 unsafe-class ping/day sits below the
4× IDLE inbox-cron ping noise floor (memory `feedback_idle_pings_acceptable_for_now`).
This means adding the sync-conflict channel does not increase the WhatsApp notification
burden beyond existing noise levels.

---

## 6. Cross-Reference to Conflict-Event Log

The conflict-event log schema (T007) and #516 forward-compatibility analysis (T008)
are captured in `findings/conflict-event-log.sketch.md`. This file cross-references
that document for the log shape; the unsafe-class criteria in § 3 above map directly
to the `conflict_class` and `resolution_decision` fields in the log schema.

---

## 7. Limitations

- **Volume estimate is back-of-envelope**: The 5% probability that Kent manually
  edits a Felix-managed field mid-cron is an estimate, not an observed measurement.
  Implementation must wire the guard mechanism first and tune the threshold after
  observing real steady-state conflict rates.

- **In-prompt callsites not covered**: The escalation and tasker agents issue
  `GET /tasks/all?filter=...` calls in-prompt (RQ-2 Note 2; evidence-log row
  `2026-06-03T23:51:00Z` citing `code-scripts-escalation-record`). These are not
  grep-discoverable and were not modeled in the volume estimate. Implementation
  must verify their write surface when those agents are migrated to script-based
  helpers.

- **UC-4 is prospective**: The `manual_override_signal` criterion requires an
  `override_flags` sub-object in Felix's cache and the conflict-event schema. This
  is a design gap that implementation must close before UC-4 fires correctly.

---

## Deferred to Implementation

- Calibrate the write-window suppression duration (Guard G-2) against live cron
  scheduling on office2.
- Verify that `updated_since` ordering semantics handle clock-skew (RQ-1 § Deferred).
- Instrument real steady-state conflict rates after initial deployment to validate
  the volume estimate.
- Implement UC-4 `override_flags` mechanism in Felix's JSONL cache schema.
