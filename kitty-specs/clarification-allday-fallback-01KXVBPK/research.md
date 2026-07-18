# Research: All-Day Fallback for Unanswered Clarifications

Phase 0 output. Resolves the three load-bearing decisions surfaced by the seam
research. Grounded in the actual code (paths + line numbers cited).

## Seam inventory (verified)

| Seam | Location | State today |
|---|---|---|
| Note-level atomic transaction | `scripts/inbox/route_and_finalize.py::_run_finalize` (L824) | Routes `kind:"calendar"` blocks via `_adapt_calendar` (L376), log-before-mark, marks note **once** (L924). Reusable. |
| Calendar delegation | `scripts/inbox/route_calendar_event.py::build_delegation_payload` (L205), `REQUIRED_FIELDS=("title","start")` (L66) | **Timed-only.** Hard-maps `start→start_rfc3339`; no `start_date` branch. |
| All-day create | `scripts/google/calendar_helper.py::_create_fields_from_payload` (L266), `_build_event_body(all_day=…)` (L204), `_all_day_field` (L182) | **All-day works** via `--payload-file` JSON with `start_date`/`end_date` (exclusive end). Idempotent on `--idempotency-key`. |
| Missing-field + resolved date source | `scripts/calendar_routing/validate_calendar_event.py::validate` (L525) | Emits `missing_fields` (e.g. `["start_time"]`); **discards** resolved `start_dt` when incomplete. |
| Pending-record store | `scripts/inbox/handle_clarification_state.py` | Record = `{note_filename, partial_payload, created_at}`; `subcommand_sweep` = pure GC; `subcommand_remove` (L158) atomic removal. |
| Sweep live caller | `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` Step 1a (L90) | Agent tick runs `handle_clarification_state sweep`; runs in the capture agent context (has `personal` calendar auth). |
| Add-time call site | `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` Step 3c (L147) | Agent composes `--partial-payload <json>` from finalize's `blocks[].missing` + `fields_so_far`. |

## R1 — How to make the create atomic + idempotent

**Decision**: Route the all-day create **through the existing #746 transaction**
(`_run_finalize`) by teaching the calendar delegation layer
(`route_calendar_event`) the all-day shape (IC-02), rather than calling
`calendar_helper` directly from the sweep path.

**Rationale**:
- Reuses the transaction's proven **log-before-mark** and **mark-note-once**
  atomicity (route_and_finalize.py L890/L924) — the sweep path builds a
  single-block plan and calls `_run_finalize(note_path, plan, account)`; it does
  **not** re-implement note-marking.
- `calendar_helper` already dedups on `--idempotency-key <source_inbox_path>`
  (private extended property `felix_source_key`, L341/L367), so a re-run after a
  partial failure returns the existing event — **exactly one event** (NFR-004,
  SC-003) with no new dedup logic.
- The #751 provenance precheck is **task-specific** (Vikunja/someday) and does not
  apply to calendar; calendar idempotency is the extended-property path above.

**Alternative rejected**: Bypass `route_calendar_event` and call `calendar_helper
create --payload-file` directly from the sweep path. Rejected — it forfeits the
transaction's note-mark atomicity, forcing the sweep path to re-implement
mark-processed + log, duplicating #746 and creating a second, divergent
finalize path.

## R2 — How to get a stable resolved date at sweep time

**Decision**: Have `validate_calendar_event.validate` **emit the resolved
`start_date`** (from `start_dt.date().isoformat()`) **and `missing_fields`** in the
incomplete-result payload on the `missing==["start_time"]` branch, so the capture
agent persists them into `partial_payload` at add-time. The sweep-finalize path
reads the already-resolved `start_date` — it never re-parses natural language.

**Rationale**:
- `start_natural` ("Thursday") re-parsed 24h+ later resolves to the **wrong week**
  — a silent-wrong-date bug. The date must be resolved **once**, at capture time
  (when the tick timestamp anchors "Thursday" correctly), and persisted.
- `validate` already computes `start_dt` (L535) and already emits `start_date` on
  the *complete* all-day branch (L607–631) — extending it to also surface the
  resolved date on the incomplete start-time branch is a small, consistent change.
- Keeps the sweep path **deterministic** (NFR-001): no parser, no tick-context
  reconstruction — just read `start_date`, set `end_date = start_date + 1 day`.

**Alternative rejected**: Persist the original `tick_iso` in the record and
re-derive the date at sweep time via `parse_datetime(start_natural, tick_iso)`.
Rejected — it couples the sweep to the NL parser (re-does work, inherits its
failure modes) and risks drift if the parser changes between capture and sweep.
Persisting the resolved answer is simpler and safer.

**Eligibility gate (derived) — corrected per Codex HIGH-1/HIGH-2.**
An early draft used `missing_fields == ["start_time"]`. That is **wrong**: the
canonical "Meet Rob Thursday" with no stated duration makes `validate` return
`missing_fields = ["start_time", "end_or_duration"]` (verified against
`validate_calendar_event.py:L541-565`), so the exact-match rule would make the
feature **fail on its own headline case**. The correct predicate is a
**timing-only gap**:

```
eligible iff  title present
          AND  a resolved start_date is present   (the date WAS parseable)
          AND  "start_time" in missing_fields
          AND  missing_fields is a subset of {"start_time", "end_or_duration"}
```

- `end_or_duration` missing is **fine** for an all-day event (no end time needed;
  `end_date = start_date + 1 day`).
- Missing **title**, or a `start_date` that is absent/malformed (date could not be
  resolved), is **not eligible** — delete-and-release (FR-002, FR-005).
- Any *non-timing* field in `missing_fields` (e.g. title) is **not eligible**.

`validate` must therefore surface the resolved `start_date` on **every**
start-time-missing result (not only the exact-`["start_time"]` branch) so the gate
has the date it needs. Pin the exact `missing_fields` vocabulary against
`validate`'s real output during IC-01/IC-03.

## R4 — Reconciliation + concurrency (Codex HIGH-3 / HIGH-4)

**Reconciliation (HIGH-3)**: `_run_finalize` is atomic for create->log->mark, but
the pending-record removal is a **separate** state rewrite that happens *after*.
Failure ladder:
- create/mark did NOT complete: note unprocessed, record retained, retry (FR-008).
- create+mark DID complete, record removal failed: **note is already processed**.
  The next sweep MUST **reconcile** — detect the note is processed (or the
  routing-log key exists) and remove the stale record **without re-creating**
  (FR-009). Do NOT assume "note unprocessed" after every failure.

The `calendar_helper --idempotency-key` dedup makes even a blind re-run safe
(returns the existing event), but reconciliation avoids a pointless re-drive and
cleans the record deterministically.

**Idempotency-key identity (MED-2)**: the record stores only `note_filename`
(basename); the finalize path must reconstruct **one canonical absolute inbox
path** used identically for the `_run_finalize` note argument and the
`--idempotency-key`, so basename-form vs path-form records cannot mint two keys.
Test this explicitly.

**Concurrency (HIGH-4)**: exactly-once is a **find-before-insert**, not a lock — two
concurrent sweep-finalize processes could both find-no-event and both insert. This
is **out of scope**: the sweep-finalize runs inside the single, serialized
`felix-admin-capture` agent tick, so concurrent invocations do not occur. NFR-004
is narrowed to the sequential model with this rationale rather than adding a lock.

## R3 — Where the deterministic sweep-finalize logic lives, and how it's invoked

**Decision (proposed, to confirm at implement)**: Add a new deterministic
**subcommand** to the clarification tooling (e.g. `sweep-finalize`) that:
1. loads the state, partitions aged-out records into **eligible** (R2 gate) vs
   **ineligible**;
2. for each eligible record: builds a single-block `calendar` plan from
   `partial_payload` (all-day shape) and calls
   `route_and_finalize._run_finalize(note_path, plan, account="personal")`; on
   success removes the record (reusing `subcommand_remove` semantics); on failure
   **retains** the record and leaves the note unprocessed (FR-008);
3. for each ineligible aged-out record: today's delete-and-release.

The `felix-admin-capture` AGENTS.md **Step 1a** is edited to invoke this
finalize subcommand **in place of** the bare `sweep` (the finalize path subsumes
the GC for aged-out records; non-aged-out records are untouched, preserving the
read-time release contract in `pending_filenames`/`_is_live`).

**Open placement question for implement**: `handle_clarification_state.py` is
deliberately dependency-light (only `json`/`os`/`datetime`). Importing
`route_and_finalize` (which pulls calendar/route deps) into it changes its
character. Two options, decided at IC-03 implementation:
- **(a)** New module `scripts/inbox/clarification_sweep_finalize.py` that imports
  both `handle_clarification_state` (state I/O + eligibility) and
  `route_and_finalize` (transaction). Keeps the state manager pure. **Leaning (a).**
- **(b)** New subcommand inside `handle_clarification_state.py` with a lazy import
  of `route_and_finalize` inside the subcommand body. Fewer files; slightly muddies
  the module's dependency story.

**Rationale for a new deterministic entry point (not the LLM agent doing it)**:
Q2 decision — no stochastic agent on the mechanical convert+create path. The agent
only *invokes* the deterministic command in its tick; all branching/eligibility/
conversion is code (NFR-001). This mirrors the #739(i) lesson where relying on the
agent to act (haiku non-delegation) was the fragility.

## Deploy + risk

- **Tier 3.** Deploys via `agent-prompt-sync` (AGENTS.md) + office2 self-pull
  (Python). No `deploys/queued/` manifest (no service/cron/credential/topology
  change). Calendar auth is the pre-existing `personal` account in the capture
  agent context — no new auth surface.
- **Rebaseline: not required** — agent AGENTS.md is not a hashed audited surface
  (`project_rebaseline_directives_gap`); no openclaw.json / systemd / deploy-lib /
  dependency manifest change.
