# Implementation Plan: All-Day Fallback for Unanswered Clarifications

**Branch**: `feat/clarification-allday-fallback` | **Date**: 2026-07-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/clarification-allday-fallback-01KXVBPK/spec.md`
**Source issue**: kentonium3/kg-automation#780 (items 2 & 3; item 1 shipped in #786)

## Summary

When a start-time calendar clarification goes unanswered for 24h, a **deterministic
sweep-finalize path** converts the pending record's `partial_payload` into an
**all-day** Google Calendar event, creates it, and marks the source note processed —
idempotently and atomically by routing through the existing #746 `route_and_finalize`
transaction. Records that are pending for any other reason keep today's
delete-and-release behavior.

Two load-bearing gaps discovered during seam research (see [research.md](./research.md))
shape this plan and were NOT visible from the issue text:

1. **The add-time `partial_payload` does not persist a stable resolved date.**
   `validate_calendar_event` discards the resolved `start_dt` when an event is
   incomplete; `fields_so_far` carries only `start_natural` ("Thursday"). Re-parsing
   that at sweep time (24h+ later) resolves to the **wrong week**. The resolved date
   (and the `missing_fields` eligibility signal) must be persisted at add-time.
2. **The #746 transaction's calendar seam is timed-only.**
   `route_calendar_event.build_delegation_payload` hard-maps `start → start_rfc3339`
   with no `start_date` branch and `REQUIRED_FIELDS = ("title", "start")`. Routing an
   all-day payload through the transaction requires teaching that layer the all-day
   (`start_date`/`end_date`) shape — `calendar_helper` itself already supports it (#786).

## Technical Context

**Language/Version**: Python 3.12 (office2 is python3-only; `python3 -m …` invocation form per helper conventions)
**Primary Dependencies**: `scripts.inbox.route_and_finalize` (#746 note-level transaction, `_run_finalize`), `scripts.inbox.route_calendar_event` (calendar seam, `_adapt_calendar` delegate), `scripts.google.calendar_helper` (#786 all-day create), `scripts.calendar_routing.validate_calendar_event` (missing-field + resolved-date source), `scripts.inbox.handle_clarification_state` (pending-record store)
**Storage**: JSON state file `/data/services/openclaw/state/pending-calendar-clarifications.json`; inbox note markdown; routing log (`RoutingLogWriter`)
**Testing**: pytest; full gate via `make test` (~5.7k tests); new unit + integration tests for eligibility gate, week-drift avoidance, idempotency-across-retries, fail-closed, and the non-start-time boundary
**Target Platform**: office2 (Ubuntu 24.04) inside the `felix-admin-capture` agent tick (the sweep's live caller); calendar auth = `personal` account, obtained exactly as the capture happy path does today
**Project Type**: single (Python helpers under `scripts/`)
**Performance Goals**: runs within the existing 24h clarification sweep invocation; no new latency budget
**Constraints**: deterministic — 0 LLM/agent calls on the sweep-finalize path (Directive 6); fail-closed on any create failure (retain record, leave note unprocessed); idempotent (exactly one event across retries); reuse #746 + #786 (0 new calendar-auth or transaction substrate); Tier 3
**Scale/Scope**: bounded to the count of pending clarification records (single-digit typical); no unbounded scans

## Charter Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **DIR-001 Architectural Integrity / separation of concerns** — PASS. Eligibility + date persistence (add-time), all-day seam (route_calendar_event), and the deterministic finalize path are separable concerns reusing existing boundaries; no new cross-cutting substrate.
- **Directive 6 — deterministic work → helper** — PASS. The sweep-finalize path is a deterministic helper (Q2 decision); no LLM on the mechanical convert+create path. The only agent-driven step is the pre-existing add-time capture.
- **Testing Standards / Quality Gates** — PASS. `make test` must stay green; new tests assert the invariants (SC-002/003, NFR-004).
- **Change-Risk Taxonomy** — Tier 3 (Python helpers + one agent-prompt edit).
- **Rebaseline Obligation (#557)** — The `felix-admin-capture` AGENTS.md prompt edit is an agent-prompt change; per the audited-surface model (`audit.sh` does not hash agent AGENTS.md — see `project_rebaseline_directives_gap`), **no rebaseline is required**. The merge record will state `Rebaseline: not required — agent AGENTS.md is not a hashed audited surface; no openclaw.json / systemd / deploy-lib / dependency change`.
- **Deployment** — deploys via `agent-prompt-sync` (the AGENTS.md edit) + office2 self-pull (the Python helpers). No `deploys/queued/` manifest needed (no service/cron/credential/topology change).

No violations → Complexity Tracking is empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/clarification-allday-fallback-01KXVBPK/
├── plan.md              # This file
├── research.md          # Phase 0 — the 3 load-bearing decisions
├── data-model.md        # Phase 1 — pending-record schema + all-day block/payload shapes
├── quickstart.md        # Phase 1 — how to exercise the fallback end-to-end
├── contracts/           # Phase 1 — pending-record schema + calendar-block plan contract
└── tasks.md             # Phase 2 — /spec-kitty.tasks (NOT created here)
```

### Source Code (repository root)

```
scripts/
├── calendar_routing/
│   └── validate_calendar_event.py     # emit resolved start_date + missing_fields on the incomplete branch (IC-01)
├── inbox/
│   ├── handle_clarification_state.py  # record carries `missing_fields`/`start_date`; new deterministic finalize path (IC-01, IC-03)
│   ├── route_calendar_event.py        # all-day support in validate_payload/build_delegation_payload/REQUIRED_FIELDS (IC-02)
│   └── route_and_finalize.py          # reused unchanged (or minimal) as the atomic transaction seam (IC-03)
└── openclaw/agents/felix-admin-capture/
    └── AGENTS.md                       # add-time prompt: persist reason + resolved date; Step 1a invokes the finalize path (IC-01, IC-03)

tests/inbox/  (+ tests/calendar_routing/)
└── unit + integration coverage for IC-01..IC-05
```

**Structure Decision**: Single-project Python helpers under `scripts/`, extended in place; new deterministic finalize logic lives in a dedicated module/subcommand rather than bloating the dependency-light `handle_clarification_state.py` state manager (final placement decided in research.md R3).

## Complexity Tracking

*No Charter Check violations — section intentionally empty.*

## Implementation Concern Map

> Concerns, not work packages. `/spec-kitty.tasks` maps these to WPs.

### IC-01 — Persist eligibility signal + stable resolved date at add-time

- **Purpose**: Give the deterministic sweep path the two facts it needs — *why* the record is pending (`missing_fields`/`reason`) and a *stable resolved date* — neither of which the record carries today.
- **Relevant requirements**: FR-001, FR-002, FR-006; C-002 (backward-compat)
- **Affected surfaces**: `scripts/calendar_routing/validate_calendar_event.py` (emit resolved `start_date` + `missing_fields` **whenever `start_time` is missing and `start_dt` resolved** — NOT only on an exact `missing==["start_time"]` branch, since the canonical no-duration case yields `["start_time","end_or_duration"]`), `scripts/inbox/handle_clarification_state.py` (`subcommand_add` accepts/stores the fields), `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (Step 3c passes them into `--partial-payload`)
- **Sequencing/depends-on**: none (foundation)
- **Risks**: LLM-in-the-loop at add-time — mitigate by having `validate` emit the fields deterministically so the agent copies `fields_so_far` verbatim; read-side default treats an absent signal as **not eligible** (C-002), so a legacy/in-flight record degrades to delete-and-release, never crashes. **Codex HIGH-1/HIGH-2**: the eligibility rule is a *timing-only gap* (see FR-005), so `validate` must surface the resolved date on every start-time-missing result, and the gate must accept `end_or_duration` alongside `start_time`.

### IC-02 — All-day support in the transaction's calendar seam

- **Purpose**: Let the #746 transaction route an all-day (`start_date`/`end_date`) calendar create end-to-end, so the finalize path reuses the transaction's atomicity instead of re-implementing note-marking.
- **Relevant requirements**: FR-004, FR-006; C-004 (exclusive end)
- **Affected surfaces**: `scripts/inbox/route_calendar_event.py` (`REQUIRED_FIELDS`, `validate_payload`, `build_delegation_payload` — accept `start_date`/`end_date`, pass through to `calendar_helper --payload-file`)
- **Sequencing/depends-on**: none (parallelizable with IC-01)
- **Risks**: must not regress the timed path; both timed and all-day forms validate and build correctly. `calendar_helper` all-day is reachable only via `--payload-file` (no `--start-date` flag) — the delegation builder must emit a payload-file, which it already does.

### IC-03 — Deterministic sweep-finalize path

- **Purpose**: For each aged-out **eligible** record, build a single-block calendar plan from `partial_payload`, run it through `route_and_finalize._run_finalize(note_path, plan, account)` (create → log → mark-once), then remove the pending record; ineligible aged-out records keep today's delete-and-release.
- **Relevant requirements**: FR-003, FR-004, FR-005, FR-008; NFR-001, NFR-002, NFR-004
- **Affected surfaces**: new deterministic finalize function/subcommand (placement per R3), `scripts/inbox/handle_clarification_state.py` (eligibility gate + record removal reuse `subcommand_remove`), `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` Step 1a (invoke the finalize path in place of / in addition to `sweep`)
- **Sequencing/depends-on**: IC-01 (needs the persisted signal + date), IC-02 (needs the all-day seam)
- **Risks**: idempotency across partial failure — `_run_finalize` marks the note once and `calendar_helper` dedups on `--idempotency-key`, so a re-run after a failed record-removal does not double-create. **Codex HIGH-3 (reconciliation, FR-009)**: record removal happens *after* the atomic transaction, so after a mark-succeeds/remove-fails the note **is** processed — the finalize path must **reconcile** on retry (detect the note is already processed / the routing-log key exists → remove the stale record, do NOT re-create), and must NOT assume "note unprocessed" after every failure. **Codex MED-2 (idempotency-key identity)**: the pending record stores only `note_filename` (basename); the finalize path MUST reconstruct **one canonical absolute inbox path** for both the note argument and the `--idempotency-key`, so a basename- vs path-form record can never yield two different keys. **Codex HIGH-4 (concurrency)**: exactly-once relies on the serial single-agent tick (NFR-004 narrowed) — no lock; document that concurrent sweep-finalize is out of scope.

### IC-04 — Observability: distinct age-out-create signal

- **Purpose**: Let the operator count appointments that landed via the unanswered-clarification fallback, separate from normal creates and plain sweep-deletes.
- **Relevant requirements**: FR-007; SC-004
- **Affected surfaces**: the finalize path's routing-log/emit, and the sweep-delete path for ineligible records
- **Sequencing/depends-on**: IC-03
- **Risks**: **Codex MED-1**: a normal calendar routing-log row is just `kind="calendar"` + destination — not separable today. Pick a **concrete durable marker** before implementing: preferred is a distinct routing-log `kind`/event `calendar_all_day_fallback` (or an explicit boolean field on the entry), consistent with `RoutingLogWriter` conventions, so the operator can grep an exact count (SC-004).

### IC-05 — Test coverage for the invariants

- **Purpose**: Prove the boundary and safety invariants.
- **Relevant requirements**: SC-001..004; NFR-004; FR-005; FR-008
- **Affected surfaces**: `tests/inbox/`, `tests/calendar_routing/`
- **Sequencing/depends-on**: IC-01..IC-04
- **Risks**: must include the **week-drift** case (a record whose `start_natural` would re-parse to a different date), the **non-start-time** boundary (missing-title / multi-missing records NOT converted), **idempotency across a simulated create→remove failure** (exactly one event), and **legacy record without the signal** (delete-and-release).
