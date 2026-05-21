# Specification: Migrate escalation to JSONL state model

**Mission ID**: 01KS5R4D79WQQWY2MCHZVCT85G
**Mission slug**: migrate-escalation-to-jsonl-state-model-01KS5R4D
**Mission type**: software-dev
**Source**: GitHub issue [#309](https://github.com/kentonium3/kg-automation/issues/309) (ADR-0002 Phase 6)
**Target branch**: main

---

## Overview

Migrate the `felix-admin-escalation` subsystem from `[Felix-Escalation]` Vikunja comment-as-state to JSONL-canonical state, mirroring the Phase 3-5 pattern proven by habits (ADR-0002 Phases 3-5). The migration closes the vulnerability class exposed by the 2026-05-16 habits incident — Kent UI-marking-done outside Felix's comment trail caused stale state and spurious re-alerts. Escalation has the same vulnerability for any task where Kent resolves outside of Felix's [Felix-Escalation] comment workflow.

This mission delivers: helper scripts implementing the canonical write+reconcile contract, a one-time backfill of existing [Felix-Escalation] comments, updated AGENTS.md + SKILL.md that consume the helpers, and Q10 hard-fail behavior so a malformed/missing record never silently downgrades a notification.

---

## User Scenarios & Testing

### Primary scenario — escalation tick under post-migration driver

A cron-triggered escalation tick fires at 8:00 AM ET. The agent:

1. Calls `reconcile_completions.py` to detect any UI-marking-done events since the last tick. Synthetic `{event_type: "done", source: "reconcile"}` records emitted into the per-project JSONL for each detected case.
2. For each escalation-subscribed Vikunja task (i.e., tasks with at least one prior `level_sent` record in JSONL, AND not yet terminally resolved):
   - Query the JSONL for the task's most recent state-defining record
   - Determine current escalation state: `pending` (no level sent yet), `level_N` (last record was `level_sent`), `snoozed` (last record was `snoozed` AND `now < snooze_until`), `resolved` (last record was `done`, `dismissed`, or `rescheduled` with a future date)
   - If state warrants the next escalation level (per existing escalation policy): send the WhatsApp + record a `{event_type: "level_sent", level: N+1, ...}` entry via `record_completion.py`
3. Emit a structured tick summary (analogous to felix-doc-auditor's per-tick activity log).

Expected behavior: the cron fires deterministically off JSONL state alone. No comment parsing inside the agent's prompt. Kent UI-marking-done is detected within one tick (24h max latency at 8 AM daily cadence) via reconcile.

### Secondary scenario — Kent resolves a task via UI

Kent marks Vikunja task #1234 (`done=true`) from the iPhone app between escalation ticks. On the next tick:

1. `reconcile_completions.py` enumerates escalation-subscribed tasks and queries each via the Vikunja API.
2. Task #1234 is `done=true` in Vikunja but the JSONL has no `done` record.
3. Reconcile emits a `{event_type: "done", source: "reconcile", recorded_at: <now>}` record.
4. The escalation walk sees the new `done` record and short-circuits — no Level 2 alert is sent.

Expected behavior: Kent is NOT re-alerted for tasks he already resolved.

### Tertiary scenario — Q10 hard-fail on malformed/missing record

A task's JSONL contains a record with `event_type: "level_sent"` but no `level` parameter (malformed). On the next tick:

1. `record_completion.py`'s schema validator catches the malformed record on read.
2. The escalation walk for this task aborts immediately — NO level is sent, NO synthetic correction is applied.
3. The helper invokes `felix-file-issue.py` to file a P2-bug. Title format: `Escalation hard-fail: <task title> (task #<vikunja_id>) — <reason>`. Title-prefix dedup ensures only one open bug per task at a time.
4. The tick continues processing OTHER tasks; this one task is skipped.

Expected behavior: an asymmetric-consequence default. The bad outcome (re-alerting Kent for a resolved task, or silently downgrading to Level 1) is structurally impossible. The neutral outcome (skip + alert operator) is what happens.

### Edge cases

- **First escalation for a task** (no prior `level_sent` records, no resolution events): the task is `pending`; if the next-level policy says send Level 1, record + send. Standard new-escalation path.
- **Snooze that expired since last tick**: most recent record is `{event_type: "snoozed", snooze_until: <past-date>}`. Walk treats the snooze as expired; next alert level is determined as if the task were back to pending or resuming the previous level (existing escalation policy determines).
- **Rescheduled then UI-edited to original date**: task has `rescheduled` event but Vikunja shows the original due date. Reconcile detects the rescheduled-date mismatch and either: (a) emits a synthetic `rescheduled` event with the new effective date, OR (b) flags as malformed and hard-fails. **The detailed semantics here are deferred to the plan phase** — the spec requires the reconcile pass to consider rescheduled-state drift but doesn't dictate the exact handling.
- **Project moves**: a task moves from one Vikunja project to another. The JSONL is keyed on the Vikunja `id` (immutable per memory `reference_vikunja_id_vs_identifier.md`); the project move does not affect record continuity.
- **Multiple ticks while a hard-fail issue is open**: dedup ensures only one open P2-bug per task. Subsequent ticks skip the task (still hard-failing) but do NOT file additional issues.

---

## Functional Requirements

| ID | Status | Requirement |
|---|---|---|
| FR-001 | required | The escalation subsystem MUST derive its current state for any task from the project's JSONL state log, NOT from Vikunja comment parsing. |
| FR-002 | required | `scripts/escalation/record_completion.py` MUST implement the atomic three-write contract from Phase 2 (`scripts/state_log.append`): append entry → flush → fsync. No partial writes. |
| FR-003 | required | The JSONL schema for escalation events MUST use a flat-enum `event_type ∈ {level_sent, snoozed, dismissed, done, rescheduled}` with structured parameter fields (e.g., `level: int`, `snooze_days: int`, `snooze_until: ISO-8601-date`, `reschedule_to: ISO-8601-date`). Composite event-type strings (e.g., `"snoozed:3d"`) MUST NOT be used. |
| FR-004 | required | `snooze_until` MUST be persisted at write-time as an ISO-8601 date, NOT computed at read-time from `snoozed_at + snooze_days`. The recorded value is authoritative. |
| FR-005 | required | `scripts/escalation/reconcile_completions.py` MUST detect UI-marking-done events: enumerate escalation-subscribed tasks, query each via Vikunja API, emit synthetic `{event_type: "done", source: "reconcile", recorded_at: <now>}` records for tasks where `vikunja.done=true` but JSONL has no `done` record. |
| FR-006 | required | One-time backfill (`scripts/escalation/backfill_jsonl_from_comments.py` or equivalent) MUST replay existing `[Felix-Escalation]` Vikunja comments as JSONL entries. Reuse the Phase 4 pattern: read-only `.bak` snapshot of input, locked HISTORICAL state-mapping, idempotent via Phase 2's dedup. Malformed comments are reported with snippets (per Phase 4 cycle 2 FR-009 lesson). |
| FR-007 | required | The escalation agent's standing orders (`/data/services/openclaw/escalation-agent/AGENTS.md`) and skill (`~/.openclaw/skills/escalation/SKILL.md`) MUST stop parsing `[Felix-Escalation]` comments and invoke the helpers for all state reads/writes. |
| FR-008 | required | Q10 hard-fail behavior: when a JSONL record for a task is malformed (schema-invalid) or missing entirely while Vikunja shows the task is escalation-subscribed, the helper MUST: (a) skip the task this tick (NO level sent, NO synthetic correction), (b) file a P2-bug via `scripts/openclaw/agents/main/felix-file-issue.py`, (c) continue processing other tasks. The hard-fail MUST NOT silently downgrade to Level 1. |
| FR-009 | required | P2-bug filing MUST use title-prefix dedup keyed on the immutable Vikunja `id`. Title format: `Escalation hard-fail: <task title> (task #<vikunja_id>) — <reason>`. Helper queries `gh issue list --search 'in:title "task #<id>"'` and only files if no existing open hard-fail issue matches. |
| FR-010 | required | The agent identity for all JSONL writes and Vikunja mutations (resolution, snooze, etc.) MUST be `felix-bot` (the service account provisioned in Phase 1, #304). Kent-driven mutations remain attributed to `kentonium3`. |
| FR-011 | required | A 3-day post-cutover soak period MUST be observed before Phase 6 is declared complete. During soak, no v1 (comment-as-state) code paths are removed; rollback to v1 must be a single config flip. |

---

## Non-Functional Requirements

| ID | Status | Requirement |
|---|---|---|
| NFR-001 | required | The reconcile pass MUST complete within the systemd `TimeoutStartSec` envelope for the escalation cron unit (currently 30 minutes per the felix-doc-auditor template; verify in plan). For typical escalation-subscribed task counts (≤50), reconcile completes in ≤60 seconds. |
| NFR-002 | required | Over the 3-day post-cutover soak window, ≥95% of escalation ticks MUST complete with a successful structured signal (exit 0, JSONL writes successful, no unhandled exception). Hard-fail counts (tasks skipped due to Q10) are recorded separately and do NOT count against this gate. |
| NFR-003 | required | The escalation JSONL files MUST be bounded: per-project files (one per Vikunja project that hosts escalation-subscribed tasks) with no per-tick rotation. File size is bounded by record count × ~200 bytes per record. After 1 year of operation at typical traffic, total JSONL state size MUST stay under 10 MB per project. |
| NFR-004 | required | Code coverage on new helpers (`record_completion.py`, `reconcile_completions.py`, the backfill helper) MUST be ≥85% (matches Phase 3-5 NFR-005). |
| NFR-005 | required | Schema validation for JSONL records MUST be reviewable: a reviewer reading the validator code MUST be able to enumerate every event_type and its required/optional parameter fields without running tests. |

---

## Constraints

| ID | Status | Constraint |
|---|---|---|
| C-001 | required | This mission MUST preserve v1 (comment-as-state) code paths during the 3-day soak window. v1 removal happens in a follow-on mission only after Phase 6 is declared complete. |
| C-002 | required | The mission MUST NOT change the existing escalation policy (timing, level thresholds, WhatsApp message format). State migration only; policy unchanged. |
| C-003 | required | The mission MUST NOT modify Phase 2's `scripts/state_log/` library's I/O contract (append, read, validate semantics; field naming for shared required fields). Updates to `DOMAIN_STATES["escalation"]` in `scripts/common/state_log_schema.py` are NOT considered a "library modification" — the per-domain state enum is the canonical mechanism each consuming phase uses to declare its vocabulary. Phase 6 owns the escalation enum. |
| C-004 | required | Architecture documentation updates (service-inventory.json, data-flows.json, credential-manifest.json as applicable) are part of THIS mission, not a separate follow-on. `updated_by: #309` on touched entries; markdown views must match JSON sources. |
| C-005 | required | Constitutional autonomy level: Observed (Level 2). The agent writes JSONL records autonomously per existing escalation policy; hard-fail bugs are filed autonomously. No new autonomy-elevation. |
| C-006 | required | Privacy boundary: the helpers MUST NOT read second-brain notes or any path under `~/second-brain/notes/04-Growth/_private/`. |
| C-007 | required | Backfill is one-time. The mission MUST NOT introduce a persistent comment-watcher daemon; comments-to-JSONL replay is a single offline run. |

---

## Success Criteria

| ID | Outcome |
|---|---|
| SC-001 | Escalation runs deterministically from JSONL state across the 3-day soak window. Zero `[Felix-Escalation]` comment parses occur during the soak (verified by SKILL.md/AGENTS.md inspection + telemetry). |
| SC-002 | Kent UI-marking-done on an escalation-subscribed task is detected within one tick window (24 hours at 8 AM ET daily cadence). No spurious re-alert occurs after a UI resolution. |
| SC-003 | At least one hard-fail scenario is verified end-to-end during the mission (synthetic malformed record → P2-bug filed → dedup verified on second tick → no spurious additional bug). |
| SC-004 | All existing escalation-subscribed tasks are backfilled into JSONL. Backfill summary report enumerates malformed comments (if any) with snippets per Phase 4 cycle 2 pattern. |
| SC-005 | A reviewer can read the JSONL schema validator code and enumerate every event_type + required parameter without running the test suite. |
| SC-006 | 3-day post-cutover soak completes with ≥95% successful ticks per NFR-002. |
| SC-007 | v1 (comment-as-state) code paths remain in the tree; rollback to v1 is a single config flip. (v1 removal deferred to follow-on mission.) |

---

## Key Entities

- **JSONL state record** — a single line in `<project>-escalation-history.jsonl` (path exact form deferred to plan). Required fields: `event_type`, `recorded_at`, `task_id` (Vikunja id), `task_title` (snapshot at write-time for human grep). Per-event optional fields per FR-003.
- **Escalation-subscribed task** — a Vikunja task with at least one `level_sent` record in JSONL AND no terminal resolution record (`done`, `dismissed`) since the most recent `level_sent`.
- **Reconcile sweep** — enumeration step at the start of each tick that detects Vikunja `done=true` drift vs JSONL state and emits synthetic `done` records.
- **Hard-fail event** — a tick-time detection of malformed/missing JSONL state for an escalation-subscribed task. Triggers SKIP + P2-bug filing.
- **Phase-6 backfill** — one-time replay of existing `[Felix-Escalation]` comments into JSONL. Idempotent via Phase 2 dedup.
- **Felix-bot identity** — `felix-bot` Vikunja service account (provisioned Phase 1, #304) — used for all agent-driven Vikunja writes during Phase 6.

---

## Assumptions

The plan phase MUST validate these before implementation begins:

1. The Phase 2 `scripts/state_log/` library is stable and exposes `append()` per Phase 3's usage. Plan phase confirms via direct read.
2. Vikunja API access for `felix-bot` is available with sufficient permissions to write comments + read task state for the escalation project. Already verified during Phase 3.
3. The `felix-file-issue.py` helper at `scripts/openclaw/agents/main/felix-file-issue.py` continues to work as the canonical issue-filing surface.
4. The existing `[Felix-Escalation]` comment vocabulary (per the deployed AGENTS.md and SKILL.md) is enumerable; the locked HISTORICAL state map can be determined by reading the deployed SKILL.md.
5. The OpenClaw escalation cron at office2 (UUID `5f734842-ca17-44f7-8040-f8e6a15355c4` per `reference_felix_doc_auditor_ops.md` memory family — verify the exact UUID for escalation in plan phase) is stable; this mission does not change the timer cadence.
6. Q10 hard-fail behavior MUST work for both: (a) explicit malformed record (schema-invalid JSONL line) and (b) record-not-found-but-Vikunja-shows-subscribed (escalation walk has no anchor to determine current state).

---

## Out of Scope

The following are explicitly NOT part of this mission:

1. Removing v1 (comment-as-state) code paths. Deferred to follow-on mission after the 3-day soak.
2. Phase 7 (tasker enrichment migration, #310). Separate mission.
3. The deferred Phase 8 items per ADR-0002: webhook receiver, saved-view creation helpers, RRULE migration.
4. Changing the escalation policy itself (timing, levels, message format).
5. Modifying Phase 2's `scripts/state_log/` library.
6. New telemetry / alerting beyond the existing tick-completion signal pattern.
7. Modifying any non-escalation OpenClaw agent or its standing orders.

---

## Cross-References

- **GitHub issue**: [#309](https://github.com/kentonium3/kg-automation/issues/309)
- **Umbrella**: [#311](https://github.com/kentonium3/kg-automation/issues/311) — ADR-0002 implementation tracker
- **Predecessor**: [#308](https://github.com/kentonium3/kg-automation/issues/308) — Phase 5 (habits cutover) — closed, pattern validated
- **Foundation**: [#305](https://github.com/kentonium3/kg-automation/issues/305) — Phase 2 (JSONL state-log library)
- **Foundation**: [#304](https://github.com/kentonium3/kg-automation/issues/304) — Phase 1 (felix-bot Vikunja provisioning)
- **Pattern source**: [#306](https://github.com/kentonium3/kg-automation/issues/306) — Phase 3 (habits to native repeat + JSONL); same write+reconcile contract
- **Backfill pattern source**: [#307](https://github.com/kentonium3/kg-automation/issues/307) — Phase 4 (habits backfill); same locked-mapping approach
- **ADR**: `docs/design/architecture/adr/0002-felix-vikunja-task-model.md`
- **Memory**: `reference_vikunja_id_vs_identifier.md` (Vikunja `id` is immutable; basis for FR-009 dedup)

---

## Discovery Record

The following decisions were resolved during specify-phase discovery on 2026-05-21:

| # | Question | Decision | Encoded in |
|---|---|---|---|
| Q1 | Schema shape for escalation events | **Flat enum** (`event_type ∈ {level_sent, snoozed, dismissed, done, rescheduled}`) **with structured parameter fields**. Composite event-type strings rejected. | FR-003, NFR-005, SC-005 |
| Q2 | `snooze_until` encoding | **Persist at write-time** as ISO-8601 date. Read-time computation rejected — write-time is the authoritative clock. | FR-004 |
| Q3 | Q10 hard-fail dedup strategy | **Title-prefix dedup** keyed on immutable Vikunja `id`. Survives task renames + project moves. Re-fires correctly if Kent closes the issue without fixing the record. | FR-009, SC-003 |
| Q-adj | Soak window length | **3 days** (adjusted from 7 per Kent — no additional quality information gained from the longer window). | FR-011, NFR-002, SC-006 |
