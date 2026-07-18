# Feature Specification: All-Day Fallback for Unanswered Clarifications

**Mission**: clarification-allday-fallback-01KXVBPK
**Mission type**: software-dev
**Source**: GitHub issue kentonium3/kg-automation#780 (items 2 & 3; item 1 shipped in #786)
**Base**: `main` @ b84bc081 (post-#751)

## Overview

When a captured note resolves to an appointment that has a date but **no explicit
time** ("Meet Rob Thursday"), the #739 policy asks the operator for the missing
start time (clarification, already shipped). Per the #739 operator decision option
(iii), if that clarification goes **unanswered** the appointment should still land
on the calendar — as an **all-day event** — rather than being re-asked every sweep
window forever. Today the 24-hour clarification sweep simply **drops** the pending
record, so the note is re-scanned and re-asked next window but never scheduled.

This mission adds a **deterministic age-out → create-all-day fallback**, scoped
strictly to start-time-missing clarifications, reusing the already-shipped all-day
calendar-helper support (#786) and the #746 `route_and_finalize` transaction for
idempotent, atomic scheduling.

## User Scenarios & Testing

### Primary scenario (happy path)

1. A note is captured that resolves to an appointment with a **resolved date and a
   title but no time** (e.g. "Meet Rob Thursday").
2. The system records a **pending clarification** carrying the reason it is pending
   (missing `start_time`) plus the partial payload (resolved date + title), and asks
   the operator for the time.
3. The operator does **not** answer within 24 hours.
4. On the next clarification sweep, instead of dropping the aged-out record, the
   system derives an **all-day** calendar payload from the partial payload, creates
   the all-day event, marks the source note processed, and removes the pending
   record — atomically.
5. The appointment now appears on the calendar as an all-day event on the resolved
   date; the operator is no longer re-asked.

### Exception / alternate paths

- **Non-start-time clarification ages out** — a pending record whose missing field
  was the **title** or an **unparseable date** ages out. It MUST follow today's
  delete-and-release behavior (drop → re-scan/re-ask). It MUST NOT become an all-day
  event.
- **Legacy in-flight record** — a pending record created before this feature (no
  reason marker) ages out. Absent a reason marker it is treated as **not eligible**
  → today's delete-and-release.
- **Create fails** (calendar/auth/IO error) — the operation fails **closed**: no
  partial state, the pending record is **retained** (note not marked processed, event
  not created) so a later sweep retries. No double-create, no silent drop.
- **Operator answers just before age-out** — the answered path (timed event) is
  unchanged; an answered record never reaches the all-day fallback.

### Edge cases

- Retry after a transient failure must create **exactly one** event (idempotency).
- A single-day all-day event uses an **exclusive** end date (`end = start + 1 day`).
- A record missing multiple fields including `start_time` is **not** start-time-only
  and is therefore **not eligible**.

## Domain Language

| Term | Canonical meaning | Avoid |
|---|---|---|
| Pending clarification record | The stored `{note_filename, partial_payload, created_at, reason}` entry awaiting an operator answer | "pending note", "queue item" |
| Sweep | The 24-hour clarification garbage-collection pass over pending records | "cleanup", "cron" |
| Age-out | A pending record older than the 24-hour threshold | "expired", "stale" |
| Sweep-finalize | The deterministic path that converts an eligible aged-out record into an all-day event and finalizes the note | "agent create", "auto-schedule" |
| Start-time clarification | A pending record whose **only** missing field was `start_time` | "no-time note" |
| All-day event | A calendar event expressed as `start.date` / `end.date` (exclusive end), not `start.dateTime` | "midnight event", "0:00 event" |

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | When a pending clarification record is created because the appointment is missing a start time, the record MUST carry a reason marker identifying it as a start-time clarification (e.g. `reason: "start_time"` or the `missing_fields` list), populated at record-creation time from the validation output. | Approved |
| FR-002 | A pending record that lacks a start-time reason marker — whether legacy/in-flight or a non-start-time missing field — MUST be treated as **not eligible** for the all-day fallback; the sweep applies today's delete-and-release behavior to it. | Approved |
| FR-003 | When an **eligible** start-time clarification record ages out (≥24h unanswered), the system MUST create an all-day calendar event derived from the record's partial payload instead of dropping the record. | Approved |
| FR-004 | The all-day event creation MUST be idempotent and atomic with marking the source note processed and removing the pending record: a failure or crash at any point MUST NOT double-create the event or strand the note. This MUST be achieved by routing the create through the #746 `route_and_finalize` transaction. | Approved |
| FR-005 | A clarification is eligible for the all-day fallback **iff** the appointment has a **resolved date** and a **title** and the only unresolved fields are **timing** fields — a missing start time, optionally accompanied by a missing end/duration (an all-day event needs no end time). A clarification missing a **title**, or whose **date could not be resolved**, MUST NOT be converted to an all-day event. *(Rationale: the canonical "Meet Rob Thursday" with no stated duration yields `missing_fields = ["start_time", "end_or_duration"]`; the gate keys on "timing-only gap + resolved date + title", not on an exact `["start_time"]` match.)* | Approved |
| FR-006 | The all-day payload MUST be derived from the resolved date: `start_date` = resolved date, `end_date` = `start_date + 1 day` (single-day, exclusive end — regardless of whether an end/duration was among the missing timing fields), with all timed fields (e.g. `start_rfc3339`, `start_timezone`) dropped. | Approved |
| FR-007 | The age-out create MUST be recorded in the routing log via a **concrete, durable marker** (e.g. a distinct `kind` such as `calendar_all_day_fallback`, or an explicit field) that is separable from a normal timed/answered calendar create and from a plain sweep-delete, so the operator can count appointments that landed via this fallback. | Approved |
| FR-008 | If the all-day create/mark cannot complete, the operation MUST fail closed: the pending record is retained and the note is left unprocessed for a later sweep to retry; no partial or duplicate state is produced. This governs the case where the transaction did **not** finish (see FR-009 for the after-mark case). | Approved |
| FR-009 | On retry after a partial failure in which the event **was** created and the note **was** marked processed but the pending record removal did not complete, the sweep-finalize path MUST **reconcile**: recognize the already-finalized note (via the note's processed state / routing-log key) and remove the stale pending record **without re-creating** the event. "Note left unprocessed" (FR-008) is guaranteed only when the transaction did not reach mark. | Approved |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | The eligibility decision and the create path MUST be deterministic — no LLM/agent invocation on the sweep-finalize path (Directive 6: deterministic work → helper). | 0 agent/LLM calls in the sweep-finalize path | Approved |
| NFR-002 | The fallback MUST NOT introduce a new always-on process; it executes within the existing clarification sweep invocation. | 0 new services/timers/daemons | Approved |
| NFR-003 | The fallback MUST reuse existing substrates (calendar-helper all-day support #786; #746 `route_and_finalize`) rather than introducing new calendar-auth or transaction machinery. | 0 new calendar/transaction modules | Approved |
| NFR-004 | Repeated **sequential** sweeps over the same aged-out record (including after a transient failure) MUST converge to exactly one calendar event. Concurrency is **out of scope**: the sweep-finalize runs inside the single, serialized `felix-admin-capture` agent tick, so two sweep-finalize processes never race; the guarantee is not a lock but the serial invocation model. | 1 event across N≥2 **sequential** retries; 0 duplicates | Approved |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Risk tier: **Tier 3** (Python helper + agent-prompt edit). Deploys via `agent-prompt-sync` (prompt) + office2 self-pull (helper). | Approved |
| C-002 | The pending-record schema change MUST be backward-compatible: records that predate the reason field (in-flight at deploy) MUST degrade to today's delete-and-release, never crash the sweep. | Approved |
| C-003 | Adding the reason marker requires a calendar-agent AGENTS.md prompt change so newly created records carry it. Per the audited-surface model, agent AGENTS.md changes do not require a rebaseline (audit.sh does not hash agent AGENTS.md); confirm no rebaseline is required in the merge record. | Approved |
| C-004 | Google Calendar all-day events use `start.date` / `end.date` with an **exclusive** end; a single-day event has `end_date = start_date + 1 day`. | Approved |

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | An unanswered no-time appointment lands on the calendar as an all-day event within one sweep cycle after the 24-hour window, instead of being re-asked indefinitely. |
| SC-002 | Zero all-day events are created from clarifications that were missing anything other than (only) the start time. |
| SC-003 | Zero duplicate events across retries or transient failures. |
| SC-004 | From the routing log alone, the operator can count how many appointments landed via the unanswered-clarification all-day fallback, distinct from normal creates and sweep-deletes. |

## Key Entities

- **Pending clarification record** — `{note_filename, partial_payload, created_at, reason}` in the clarification state store. The `reason` field is the new eligibility signal.
- **Partial payload** — the resolved appointment data captured at ask time: resolved date + title, no time.
- **All-day calendar event** — `start.date` / `end.date` (exclusive end) event created via the existing calendar helper.

## Assumptions

- The partial payload reliably carries the resolved date in a stable, parseable form (to be confirmed at plan/implement time — Q3).
- The #746 `route_and_finalize` transaction can wrap a calendar-create side effect as its idempotent/atomic unit; the exact integration seam is a plan-phase decision.
- The deployed office2 checkout has the #786 all-day calendar-helper support.

## Scope

**In scope**: the age-out → create-all-day fallback (items 2 & 3 of #780) — record reason marker, deterministic sweep-finalize path, strict start-time-only eligibility gate, idempotent/atomic create via #746, distinct routing-log observability.

**Out of scope**:
- Item 1 (all-day support in the calendar helper) — already shipped in #786.
- The `end > start` validation guard in `validate` (backlog note F3 from the #786 review) — a separate follow-up unless trivially co-located.
- Any change to the answered/timed clarification path.
