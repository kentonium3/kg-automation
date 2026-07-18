---
work_package_id: WP03
title: Deterministic sweep-finalize path + observability
dependencies:
- WP01
- WP02
requirement_refs:
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
tracker_refs: []
planning_base_branch: feat/clarification-allday-fallback
merge_target_branch: feat/clarification-allday-fallback
branch_strategy: Planning artifacts for this mission were generated on feat/clarification-allday-fallback. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/clarification-allday-fallback unless the human explicitly redirects the landing branch.
subtasks:
- T005
- T006
- T007
- T008
- T009
shell_pid_created_at: "1784413270.076443"
history:
- '2026-07-18: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/inbox/clarification_sweep_finalize.py
create_intent:
- scripts/inbox/clarification_sweep_finalize.py
execution_mode: code_change
owned_files:
- scripts/inbox/clarification_sweep_finalize.py
- scripts/inbox/handle_clarification_state.py
- scripts/inbox/routing_log.py
- tests/inbox/test_handle_clarification_state.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

Adopt its identity, governance scope, and boundaries before reading further.

## Objective

Build the deterministic **sweep-finalize** path: for each aged-out **eligible**
pending calendar-clarification record, convert it to an all-day event and route it
through the #746 `route_and_finalize` transaction (create → log → mark note
processed), with **reconciliation** and **fail-closed** semantics; ineligible
aged-out records keep today's delete-and-release; the timeout window drops to **8h**.
No LLM on this path (Directive 6).

## Context (read `spec.md` FR-002..009 + C-006/C-007, `research.md` R3/R4, `data-model.md`)

- **Depends on WP01** (record's `partial_payload` now carries `missing_fields` +
  resolved `start_date`) and **WP02** (the delegation seam accepts all-day payloads).
- **Transaction seam**: `scripts/inbox/route_and_finalize.py::_run_finalize(source_path,
  plan, account)` (~L824) routes a plan of blocks, log-before-mark, marks the note
  **once** (~L924). Build a single-block `calendar` plan and call it. Calendar
  idempotency = `calendar_helper --idempotency-key` extended-property dedup (task-
  specific #751 provenance does NOT apply to calendar).
- **State store**: `scripts/inbox/handle_clarification_state.py` — `load_state`,
  `save_state` (atomic replace), `_is_aged_out`, `_is_live`, `subcommand_remove`
  (~L158, atomic), `SWEEP_MAX_AGE` (currently 24h). The live `sweep` caller is the
  `felix-admin-capture` agent tick (rewired in WP05).
- **Placement (R3)**: put the orchestration in a **new module**
  `scripts/inbox/clarification_sweep_finalize.py` that imports the state helpers +
  `route_and_finalize`, keeping `handle_clarification_state.py` dependency-light.

## Subtasks

### T005 — New module + eligibility partition

**File**: `scripts/inbox/clarification_sweep_finalize.py` (new)

1. Provide a CLI subcommand-style entry (invocable as
   `python3 -m scripts.inbox.clarification_sweep_finalize …`, per the `-m`
   invocation convention [[feedback_helper_m_invocation_form]]) and importable
   functions.
2. Load the pending-clarification state; select **aged-out** records via the shared
   `_is_aged_out` (now 8h — see T008).
3. Partition aged-out records into **eligible** vs **ineligible** using the
   deterministic **timing-only-gap** predicate (spec FR-005, data-model):
   ```
   eligible iff  partial_payload.title present
             AND  partial_payload.start_date is a well-formed YYYY-MM-DD
             AND  "start_time" in partial_payload.missing_fields
             AND  missing_fields ⊆ {"start_time", "end_or_duration"}
   ```
   Use the **real** `missing_fields` vocabulary captured by WP01's T002 test; if the
   no-duration case is `["start_time","end_or_duration"]`, the subset rule accepts it.
4. Absent `missing_fields` or `start_date` (legacy/in-flight records) → **ineligible**
   (fail-closed; C-002).

### T006 — Build all-day plan + run the transaction

**File**: `scripts/inbox/clarification_sweep_finalize.py`

1. For each eligible record, reconstruct **one canonical absolute inbox path** from
   `note_filename` (INV-7 / Codex MED-2) — used identically for the `_run_finalize`
   `source_path` and the calendar `--idempotency-key`. Do not let a basename- vs
   path-form record mint two keys.
2. Build a single-block `RoutingPlan`:
   ```json
   {"blocks": [{"block_index": 0, "kind": "calendar", "content": "<note-derived>",
     "payload": {"title": "<title>", "start_date": "<start_date>",
                 "end_date": "<start_date + 1 day, exclusive>"}}]}
   ```
   Compute `end_date = start_date + 1 day` deterministically (C-004).
3. Call `route_and_finalize._run_finalize(canonical_path, plan, account="personal")`.
   Do not re-implement note-marking — reuse the transaction.

### T007 — Reconciliation + fail-closed

**File**: `scripts/inbox/clarification_sweep_finalize.py`

Implement the failure ladder exactly (spec FR-008/FR-009, INV-3/6):
1. **Before the create/mark completes** (transaction returns a not-finalized/error
   result) → **retain** the record, leave the note unprocessed; next tick retries.
2. **After create+mark succeeded** → remove the pending record (reuse
   `subcommand_remove` semantics).
3. **Reconcile-after-mark** (record-removal failed on a prior run, so the note is
   already processed / the routing-log key already exists): detect the already-
   finalized note and remove the stale record **without re-creating** the event. Use
   the routing-log reader / note-processed check that `_run_finalize` itself uses
   (`reader.has_block(...)` / mark-processed state) so this is deterministic.
4. Never double-create (idempotency-key dedup is the backstop; reconciliation avoids
   the pointless re-drive).

### T008 — Ineligible delete-and-release + 8h window

**Files**: `scripts/inbox/clarification_sweep_finalize.py`, `scripts/inbox/handle_clarification_state.py`

1. Ineligible aged-out records → today's **delete-and-release** (reuse
   `_is_aged_out` + `subcommand_remove`/`save_state`); **non-aged-out** records are
   untouched (preserve the read-time release contract in
   `pending_filenames`/`_is_live`).
2. Change `SWEEP_MAX_AGE` in `handle_clarification_state.py` from **24h → 8h**
   (C-006, whole-window) and update the module docstring's "24h aging semantic" note.
   Update the affected assertions in `tests/inbox/test_handle_clarification_state.py`
   (24h → 8h) — this is the only intended behavior change to the shipped aging.

### T009 — Observability marker

**Files**: `scripts/inbox/clarification_sweep_finalize.py`, `scripts/inbox/routing_log.py`

1. Emit a **distinct, durable marker** for the age-out create — a routing-log
   `kind`/event `calendar_all_day_fallback` (or an explicit field) — separable from a
   normal calendar create and a plain sweep-delete (spec FR-007, SC-004).
2. **Extend the existing vocabulary** (C-007): sit alongside
   `calendar_event_clarification_timeout` / the `log_action` convention rather than
   inventing a parallel logging scheme. Grep `routing_log.py` for the existing
   kind/action constants and the `append` shape before adding one.

## Branch Strategy

Planning/base + merge target: `feat/clarification-allday-fallback` (single_branch).
Execution worktree per computed lane in `lanes.json`.

## Definition of Done

- [ ] Eligible aged-out record → one all-day event via `_run_finalize`, note processed, record removed, distinct marker logged.
- [ ] Ineligible aged-out (missing title / non-timing / legacy no-signal) → delete-and-release; non-aged-out untouched.
- [ ] Reconciliation + fail-closed ladder implemented exactly (retain-before-mark, reconcile-after-mark, remove-on-success); never double-creates.
- [ ] `SWEEP_MAX_AGE` = 8h; docstring + `test_handle_clarification_state.py` updated.
- [ ] No LLM/agent call on the path (NFR-001); `-m` invocable.
- [ ] Marker extends the existing routing-log vocabulary.
- [ ] `make test` green (WP04 adds the deep integration coverage).

## Risks / reviewer guidance

- **Reconciliation correctness** is the sharpest risk (Codex HIGH-3) — reviewer walks the create+mark-then-remove-fail interleaving and confirms no re-create and eventual record removal.
- **Canonical path** (Codex MED-2) — confirm the note arg and idempotency-key are the same reconstructed absolute path.
- **8h blast radius** — confirm the constant change doesn't break `_is_live`/`pending_filenames` semantics beyond the intended window shortening.
- **Determinism** — no NL re-parse; the date comes only from the persisted `start_date`.

## Activity Log

- 2026-07-18T22:07:49Z – claude:sonnet:python-pedro:implementer – shell_pid=71488 – Assigned agent via action command
- 2026-07-18T22:21:28Z – claude:sonnet:python-pedro:implementer – shell_pid=71488 – Ready for review (from primary): deterministic sweep-finalize, reconciliation ladder, 8h window, calendar_all_day_fallback marker; 39+478 tests green
- 2026-07-18T22:21:39Z – claude:opus:reviewer-renata:reviewer – shell_pid=76786 – Started review via action command
- 2026-07-18T22:29:41Z – user – Moved to planned
