# Specification: Felix-Vikunja Sync Reconciliation Driver

**Mission ID**: `01KTA1J3FH87XJWT7FQPT1EZE7`
**Mission slug**: `felix-vikunja-sync-reconciliation-driver-01KTA1J3`
**Source issue**: [#518](https://github.com/kentonium3/kg-automation/issues/518) (sub-issue of Epic [#507](https://github.com/kentonium3/kg-automation/issues/507))
**Authoritative architecture**: [ADR-0003](https://github.com/kentonium3/kg-automation/blob/main/docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md)
**Research substrate**: [`docs/research/felix-vikunja-sync-architecture/`](../../docs/research/felix-vikunja-sync-architecture/)

---

## Overview

Felix and Vikunja currently maintain divergent views of task state. Each Felix script polls Vikunja independently with its own freshness assumptions, and when the operator edits a task directly in the Vikunja UI, the change is invisible to Felix's local caches until the next implicit re-fetch. There is no shared anchor for incremental polling, no audit trail of detected divergences, and no signal to the operator when an automated decision-not-to-act is downstream of a silent drift.

This mission delivers the **foundation** of the bi-directional sync architecture defined in ADR-0003: a centralized reconciliation driver, an append-only conflict-event log, and a deterministic delivery path for unsafe-class conflicts to the operator's WhatsApp. The driver covers the **status** and **task** layers; the **project** layer (with its deletion-confirmation algorithm and URL-base normalization) lands later in #520, and the migration of the 18 existing Vikunja-touching scripts to read from the driver's cache lands in #519. Until #519 ships, the new driver coexists with current callsites — it observes their effects but does not replace their reads or writes.

The architecture's load-bearing decisions (polling-only, Vikunja wins all conflicts, integer `task.id` as cross-cycle identifier, 3–5 minute cadence, structured 15-field conflict-event schema, forward-compatibility with #516) are locked in ADR-0003 and recommendation.md. This spec carries them forward as constraints; the plan phase confirms their implementation.

---

## User Scenarios & Testing

The actors are the **operator** (Kent, using the Vikunja UI and WhatsApp) and the **Felix sub-agents** (existing agents that read/write Vikunja today, observed by the driver). Acceptance scenarios describe operator-visible flows; edge cases describe correctness boundaries.

### Acceptance scenarios

**AS-1 — Operator UI edit reflected in Felix cache**
The operator updates a task's due date in the Vikunja UI. Within the cycle latency budget, the driver detects the divergence between its cached value and Vikunja's current value, accepts Vikunja's value, updates the cache, and appends a conflict event to the log. Because the conflicting field was authored by the operator (UC-2), the event is classified as unsafe-to-auto-resolve and the operator receives a single WhatsApp message describing the change. Subsequent Felix activity on that task uses the new due date.

**AS-2 — Felix-authored update produces no operator-facing noise**
A Felix sub-agent (e.g., `felix-admin-habits`) marks a daily habit complete. On the next cycle, the driver observes Vikunja's `done=true` state and recognizes the felix-bot identity as the author (none of UC-1 through UC-4 fire). The event is classified as auto-resolved, the cache is updated, the conflict log records the routine reconciliation, and the operator's WhatsApp stays silent.

**AS-3 — Operator edits soon after Felix write — suppression window holds**
A Felix sub-agent updates a task. Within 30 minutes, the operator edits the same task in the UI. UC-1 fires (`kent_edit_after_felix_write`) but the G-2 guard (30-minute post-Felix-write suppression) holds the WhatsApp ping. The event is logged. After G-2 expires, the next operator edit on the task produces a normal unsafe-class ping.

**AS-4 — Driver tick health is operator-observable**
The operator runs a single command on office2 to read the driver's per-tick health record. The record shows the most recent cycle start time, duration, layer pointers advanced, count of events emitted, and any cycle-level error. A driver that has stopped running on schedule is identifiable from this record alone.

**AS-5 — Same-day repeat edits collapse to a single ping**
The operator edits the same task three times in a single day. The first unsafe edit produces a WhatsApp ping. The second and third edits produce log entries but no additional pings: G-1 (24-hour dedup by event_id stem) suppresses the duplicates. The next calendar day, the dedup window resets.

### Edge cases

**EC-1 — Vikunja unreachable for one or more cycles**
Vikunja returns network errors or 5xx HTTP status for the driver's fetch phase. The driver does not advance its freshness pointer for the affected layer, surfaces the error in the per-tick health record, and recovers on the next successful cycle by covering the unprocessed delta. No edits are silently missed.

**EC-2 — Driver crashes mid-cycle**
The driver process is killed between fetch and complete. The freshness pointer remains at its pre-cycle value. The next cycle re-fetches the same delta. Any conflict events already appended in the crashed cycle are de-duplicated by `event_id` on the next cycle's emit phase.

**EC-3 — Many edits in one cycle**
The operator does a bulk reorganization that touches dozens of tasks in one cycle. The driver processes all of them. Conflict events are logged for each. WhatsApp ping volume remains bounded by G-1 (per-event-id dedup) and G-3 (hard daily cap) — the operator never sees a flood.

**EC-4 — Conflict-log append failure**
The disk is full or the log file is otherwise un-writable. The driver does not silently continue. The cycle is marked failed in the per-tick health record, the cycle's effects are not committed (cache not updated, freshness pointer not advanced), and the failure mode escalates per the same path as a Vikunja-write-class failure in existing scripts.

**EC-5 — Clock skew between office2 and Vikunja**
Vikunja's server clock drifts from Felix's wall clock. The driver uses Vikunja's reported `updated` timestamp as the canonical "edit time" and Felix's wall clock only for the local `ts_observed_utc` field. Skew does not produce false-positive UC-1 classifications because UC-1 compares two Vikunja-side timestamps (operator edit vs. felix-bot last write recorded by Vikunja), both on the same clock.

---

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | The reconciliation driver runs autonomously on a recurring schedule, with cadence configurable between 3 and 10 minutes (default 5). | Locked |
| FR-002 | Each cycle executes the 6-phase pipeline defined in ADR-0003 (fetch → diff → classify → emit → update → complete) for the status and task layers. The project layer is excluded and tracked as #520. | Locked |
| FR-003 | The driver maintains a per-layer freshness pointer (`last_polled_utc`) persisted across restarts. The pointer is used as the `updated_since` parameter on the next delta fetch and is advanced only after a cycle completes successfully. | Locked |
| FR-004 | Detected divergences are appended to an append-only conflict-event log using the 15-field schema specified in `docs/research/felix-vikunja-sync-architecture/findings/conflict-event-log.sketch.md`, including a deterministic `event_id` so duplicate events are idempotent. | Locked |
| FR-005 | Each detected divergence is classified against the four unsafe-class criteria (UC-1 `kent_edit_after_felix_write`, UC-2 `operator_authored_field`, UC-3 `downstream_behavior_depends`, UC-4 `manual_override_signal`) defined in RQ-3. Classification is deterministic and reads only from log fields. | Locked |
| FR-006 | Events classified as `unsafe_to_auto_resolve` route to the operator's WhatsApp via a deterministic send path, formatted as a structured three-line message (class, entity, diff summary). Events classified as `auto_resolved` are logged only. | Locked |
| FR-007 | The driver applies three delivery guards before emitting an unsafe-class WhatsApp message: G-1 (24-hour dedup by `event_id` stem), G-2 (30-minute post-Felix-write suppression), and G-3 (hard daily cap). | Locked |
| FR-008 | The driver writes a per-tick health record containing cycle start time, duration, per-layer pointer values, count of events emitted by class, and any cycle-level error. The record is overwrite-on-success and append-on-error. | Locked |
| FR-009 | The driver only reads from Vikunja; it does not write task or project state to Vikunja. Existing Felix sub-agents continue to write directly to Vikunja until #519 migrates them. | Locked |
| FR-010 | All cycle-level failures (Vikunja unavailable, malformed response, log-append failure, classification panic) surface as structured stderr output and a non-null error field in the per-tick health record. No failure mode silently swallows a cycle. | Locked |

---

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Convergence latency from operator UI write to Felix cache reflecting the change. | ≤ 5 minutes (95th percentile under steady state) | Locked |
| NFR-002 | WhatsApp ping volume to the operator under steady state. | ≤ 1 unsafe-class ping per calendar day (after G-1/G-2/G-3 guards) | Locked |
| NFR-003 | Single driver cycle duration at current Felix scale (≤ 20 active tasks; ≤ 20 projects). | ≤ 5 seconds per cycle | Locked |
| NFR-004 | Conflict-event log file size growth under steady-state writes. | Externally rotated per `habits-history.jsonl` precedent; driver itself does not own rotation | Locked |
| NFR-005 | Operator-visible time-to-detect a stopped driver via the per-tick health record. | ≤ 1 cadence interval (5 min at default) | Locked |
| NFR-006 | Driver tolerance to transient Vikunja unavailability without operator intervention. | Recovers without missing any edit upon next successful cycle | Locked |

---

## Constraints

| ID | Constraint | Source | Status |
|----|-----------|--------|--------|
| C-001 | Polling only — no webhooks, even if Vikunja supports them. | Operator decision per memory `feedback_vikunja_sync_polling_not_webhooks` | Locked |
| C-002 | Vikunja wins all conflicts unconditionally. Felix never overrides Vikunja's state. | ADR-0003 § Conflict Resolution; C-002 in research spec | Locked |
| C-003 | Driver is read-only against Vikunja. All writes continue via existing Felix sub-agents until #519. | This mission's bounded scope; ADR-0003 § Migration | Locked |
| C-004 | The integer `task.id` is the canonical cross-cycle identifier. The driver does not depend on Vikunja UUIDs. | ADR-0003 § Identifier; RQ-1 evidence | Locked |
| C-005 | The driver reuses the existing `vikunja-api` credential (owned by the `felix-bot` Vikunja user) at its established secrets path. No new Vikunja credential is provisioned. | Existing credential manifest entry; ADR-0002 Phase 1 identity model | Locked |
| C-006 | The WhatsApp send path is deterministic-script-callable (Directive 6 alignment). If a deterministic send mechanism already exists in OpenClaw, the driver wires into it. If not, this mission produces a reusable send helper that any future deterministic driver can call. | Operator decision Q1 (2026-06-04) | Locked |
| C-007 | The conflict-event log schema and emission semantics are forward-compatible with each of the three possible framework outcomes in #516. | RQ-3 § Forward compatibility | Locked |
| C-008 | The driver runs as the `claude` user on office2 (the existing host for Felix deterministic drivers). No new host, no sudo. | Existing felix-doc-auditor-driver + felix-heartbeat-gate precedent; CLAUDE.md sudo-prohibition | Locked |
| C-009 | The driver's privacy boundary mirrors the system's: task records routed through `02-Growth/_private/` are never logged with content references, only with the integer `task.id`. | Felix Constitution privacy boundary | Locked |

---

## Success Criteria

| ID | Criterion (measurable, technology-agnostic) | Verification |
|----|--------------------------------------------|--------------|
| SC-001 | After an operator UI edit, Felix's cache reflects the new value within 5 minutes, measured across at least 3 reproducible test edits. | Manual test: edit a task field, wait one cycle, query the cache record. |
| SC-002 | An unsafe-class conflict produces a single WhatsApp message within 5 minutes of the underlying edit, in the prescribed three-line shape. | Manual test: simulate a UC-2 edit; observe the WhatsApp message. |
| SC-003 | Same-day repeat edits to the same field collapse to a single WhatsApp ping (G-1 dedup). | Manual test: edit the same task twice within 24 hours; observe one ping, two log entries. |
| SC-004 | Over 7 consecutive days of steady-state operation, the operator receives no more than 1 unsafe-class WhatsApp ping per calendar day. | 7-day observation window. |
| SC-005 | When Vikunja becomes unreachable mid-cycle, the next successful cycle covers the gap without missing any operator edits. | Manual test: block office2's Vikunja route for one cycle; observe recovery. |
| SC-006 | A driver crash between cycles leaves no missed edits and produces no duplicate conflict events for the same `event_id`. | Manual test: kill the driver process mid-cycle; observe next-cycle behavior. |
| SC-007 | The operator can confirm the driver is alive and current via a single command reading the per-tick health record. | Manual: run the command, see human-readable status. |
| SC-008 | The conflict-event log is structurally forward-compatible with the three #516 framework outcomes: under outcome (a) the `schema_version` field is load-bearing, under (b) the `event_id` is load-bearing, under (c) the `router_route_set` field is load-bearing. | Static review against `conflict-event-log.sketch.md` § Forward compatibility. |
| SC-009 | The driver completes the implementation arc without introducing a new Vikunja write-path bug (per #524 precedent: any new Vikunja call uses the read-modify-write pattern from memory `reference_vikunja_post_partial_replace`). | Code review during implement-review loop; cycle-level test in plan phase. |

---

## Key Entities

| Entity | Purpose | Owns |
|--------|---------|------|
| **Reconciliation cycle** | One execution of the 6-phase pipeline (fetch → diff → classify → emit → update → complete) on a configurable cadence. | The per-cycle health record; advances the per-layer freshness pointer. |
| **Conflict event** | One detected divergence between Felix's cached value for a field and Vikunja's authoritative value, classified as `auto_resolved` or `unsafe_to_auto_resolve`. | The 15-field record in the conflict-event log. |
| **Freshness pointer** | Per-layer (status, task) record of the most recent Vikunja update timestamp the driver has confirmed it processed. | The next `updated_since` parameter value. |
| **Task cache record** | Felix's local view of one Vikunja task, addressed by the integer `task.id`. | The current state Felix's downstream consumers will read once #519 migrates them. |
| **Per-tick health record** | The driver's self-report of the most recent cycle: started_at, duration, pointer values, event counts, error. | The operator's primary "is the driver alive" signal. |
| **WhatsApp delivery path** | The deterministic-callable mechanism through which unsafe-class events reach the operator. | Either wires into an existing OpenClaw send mechanism, or owns a new reusable helper (Q1 decision). |

---

## Assumptions

The plan phase must validate each assumption before implementation work begins. Live-probe office2 and the Vikunja instance to confirm.

- **A-1**: The existing `vikunja-api` token at the established secrets path (mode 0600, owned by `claude:felix`) is sufficient for all read endpoints the driver requires (`GET /api/v1/tasks/all?updated_since=<ts>`, `GET /api/v1/tasks/<id>`, `GET /api/v1/projects`).
- **A-2**: The driver state directory `/data/services/openclaw/state/<driver-name>/` is the correct location for the conflict-event log, per-tick health record, and freshness pointers — matching the precedent established by `felix-doc-auditor-driver` and `felix-heartbeat-gate`.
- **A-3**: A deterministic WhatsApp send mechanism is exposed somewhere in the OpenClaw runtime (gateway REST endpoint, plugin Python API, or callable helper). If not, this mission's scope expands to include a small reusable send helper — accepted by the operator at discovery (Q1, 2026-06-04).
- **A-4**: First-run bootstrap initializes each layer's `last_polled_utc` at install time. Historical divergences predating the install are not back-filled. Operator validates this is acceptable before plan phase commits.
- **A-5**: Vikunja v0.24.6's `GET /api/v1/tasks/all?updated_since=<ts>` endpoint reliably returns all task updates between the pointer value and now, with no silent skip on edge cases (deletion handling is explicitly deferred to #520).
- **A-6**: Existing Felix sub-agents' writes to Vikunja remain transparent to the driver — meaning, the driver observes the resulting state changes through the same `updated_since` polling and processes them through the classification phase (where felix-bot authorship causes UC-1/UC-2 to NOT fire and the events resolve as `auto_resolved`).
- **A-7**: Conflict-event log rotation is handled by an external mechanism analogous to existing JSONL log rotation in the system. The driver does not own rotation; plan phase confirms the rotation interface.

---

## Out of Scope

- Touchpoint migration. The 18 existing Felix scripts that touch Vikunja remain unchanged. Migration to the driver's cache is #519.
- Project-layer reconciliation, deletion-confirmation (the 3-cycle absence algorithm), and URL-base normalization (Tailscale HTTPS vs direct IP). All three land in #520.
- Modifications to OpenClaw's WhatsApp credential boundary or session management.
- RRULE-based recurrence handling. Tracked upstream as `go-vikunja#2032` and watched as #506.
- A bi-directional cache where Felix's local writes propagate to Vikunja through the driver. Felix's writes continue to go through existing sub-agent paths.
- Replacement or refactoring of any existing Felix sub-agent. The driver coexists.

---

## References

- **Parent epic**: [#507 — Felix-Vikunja bi-directional sync foundation](https://github.com/kentonium3/kg-automation/issues/507)
- **Source issue**: [#518 — Feature: Felix-Vikunja sync reconciliation driver foundation](https://github.com/kentonium3/kg-automation/issues/518)
- **Research mission (closed)**: [#508 — Research: Vikunja state model + Felix-Vikunja sync architecture design](https://github.com/kentonium3/kg-automation/issues/508)
- **Sibling implementation missions**:
  - [#519 — Feature: Migrate Felix touchpoints to sync cache](https://github.com/kentonium3/kg-automation/issues/519)
  - [#520 — Feature: Project-layer sync + deletion handling + URL normalization](https://github.com/kentonium3/kg-automation/issues/520)
- **Canonical architecture**: [ADR-0003 — Felix-Vikunja sync architecture](../../docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md)
- **Extends**: [ADR-0002 — Felix-Vikunja task model](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md)
- **Forward-compat target**: [#516 — Felix observability and emission framework](https://github.com/kentonium3/kg-automation/issues/516) (per `conflict-event-log.sketch.md` § Forward compatibility)
- **Research deliverables**: [`docs/research/felix-vikunja-sync-architecture/`](../../docs/research/felix-vikunja-sync-architecture/)
- **Related credentials**: `vikunja-api` (felix-bot identity)
- **Adjacent recent work**: [#524 — Vikunja POST partial-replace fix in record_completion.py](https://github.com/kentonium3/kg-automation/issues/524) — read-modify-write pattern now mandatory for any new Vikunja writes (relevant to the existing-touchpoint co-existence period).
