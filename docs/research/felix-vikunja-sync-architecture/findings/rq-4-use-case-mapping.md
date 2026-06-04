---
rq_id: "RQ-4"
title: "Use-case → layer mapping"
depends_on: ["RQ-1", "RQ-2", "RQ-3", "RQ-5"]
wp: "WP02"
tags: [507, 516]
---

# RQ-4 — Use-Case to Layer Mapping

**Scope**: Maps each of Epic #507's seven operator use cases (a–g) to the proposed
three-layer model (`status` / `task` / `project`), with detection mechanism,
Felix-side action, and worst-case latency. Includes NFR-002 enforcement (T010).

**Source**: Use cases extracted verbatim from Epic #507 body
(source-register `issue-507`; evidence-log row added below as WP02 row).

**Polling cadence assumption**: ~5-minute polling cadence (`updated_since` delta
poll per RQ-1 § 5.3). This is the design parameter chosen to satisfy the 5-min
overall ceiling (NFR-002). Each layer is polled on the same cadence; worst-case
latency = 1 full poll interval = 5 minutes (event happens just after a poll completes;
next poll detects it).

---

## 1. Use Cases (verbatim from Epic #507)

The following use cases are reproduced verbatim from Epic #507
("Concrete use cases (operator-supplied)"):

> **(a)** Operator manually changes the **status** of a task in Vikunja that's also
> being tracked by Felix → Felix's local state must reflect that change before it
> next acts
>
> **(b)** Operator **deletes** an obsolete task manually in Vikunja → Felix must stop
> referencing that task without erroring
>
> **(c)** Operator **moves a task** from one project to another for better organization
> → Felix's project-scoped queries must still find it (or correctly stop finding it)
>
> **(d)** Operator **adds a new project** in Vikunja → Felix should be aware that the
> project exists for future configuration
>
> **(e)** Operator **manually moves some or all tasks** from one project to a newly
> created project → Felix's project_id references must update or fail loudly
>
> **(f)** Operator **renames a task or project** in Vikunja → Felix's title-based
> identifiers (where used) must follow; task_id-based identifiers remain stable
>
> **(g)** Operator sets a **new due_date** on a task in Vikunja → Felix must not
> overwrite that with a stale computed value on the next sweep

---

## 2. Use Case → Layer Mapping Table

| Use case | Layer(s) | Change shape | Detection mechanism | Felix-side action | Worst-case latency | NFR-002 |
|---|---|---|---|---|---|---|
| **(a)** Status change | `status` | state-change (`done`: false→true or true→false) | `diff` phase: compare `done` + `done_at` in Vikunja response vs Felix JSONL cache | Cache invalidate the domain JSONL entry; suppress next Felix write of `done` for that task (C-002 Vikunja wins); if UC-1 or UC-3 fires, emit unsafe event | ≤ 5 min | Pass |
| **(b)** Task deleted | `task` | structural-change (entity no longer exists) | `diff` phase: task `id` present in Felix cache but absent from `GET /tasks/all?updated_since=<ts>` response *and* confirmed absent by explicit `GET /tasks/{id}` → 404 | Mark entity as `deleted` in Felix's cache; stop referencing `task_id` in schedule YAML and future queries; log deletion event | ≤ 5 min | Pass |
| **(c)** Task moved (project_id change) | `task` + `project` | content-change (`project_id` field change) | `diff` phase: `project_id` in Vikunja response differs from Felix's cached `project_id` for that `task.id` | Update Felix's cached `project_id` for the task; project-scoped queries (`GET /projects/{id}/tasks`) will now return/exclude the task correctly; no explicit cache invalidation needed for project layer | ≤ 5 min | Pass |
| **(d)** New project added | `project` | structural-change (new entity) | `diff` phase on the project layer: `GET /projects` returns a `project.id` not in Felix's project cache | Add project to Felix's project cache; emit a low-priority project-layer discovery event (no WhatsApp ping — not an unsafe class; new project is additive) | ≤ 5 min | Pass |
| **(e)** Tasks bulk-moved to new project | `task` + `project` | content-change (`project_id` change on N tasks) + structural-change (new project) | `diff` phase: multiple tasks show `project_id` change in `updated_since` results; project layer detects the new project simultaneously | Update Felix's cached `project_id` for each moved task; project references update automatically since Felix uses `task.id` as primary key (not `project_id` hardcoded); emit per-task conflict events if UC-2 fires (operator-authored moves) | ≤ 5 min | Pass |
| **(f)** Task or project renamed | `task` or `project` | content-change (`title` field change) | `diff` phase: `title` in Vikunja response differs from Felix's cached `title`; for task layer, `updated_since` will surface the change; for project layer, full `GET /projects` is needed (projects may not be surfaced by `updated_since`) | Update Felix's cached `title`; for task layer: update WhatsApp ping templates that reference title by name; for project layer: update project cache; emit task-layer conflict event if UC-3 fires (title is a downstream-behavior-dependent field for ping content) | ≤ 5 min | Pass |
| **(g)** New due_date set manually | `task` | content-change (`due_date` field change) | `diff` phase: `due_date` in Vikunja response differs from Felix's cached `due_date`; `updated_since` surfaces the change; UC-1 fires if `vikunja.updated > felix.ts_last_write_utc` | Accept Vikunja's `due_date` (C-002); update Felix's cached `due_date`; suppress Felix's next scheduled `due_date` write for this task for the current day (per Guard G-2 in rq-3-conflict-policy.md); emit unsafe event → WhatsApp ping | ≤ 5 min | Pass |

---

## 3. Layer → Detection Mechanism Notes

### Status layer (use case a)

- **Primary detection**: `GET /tasks/all?updated_since=<last_polled_utc>` returns any
  task whose `updated` timestamp changed. The `done` and `done_at` fields are in the
  response — no extra per-task fetch needed.
- **Reconciliation cycle step**: `fetch` returns changed tasks; `diff` compares `done`
  and `done_at` fields; `classify` applies UC-1 and UC-3 criteria.
- **Felix-side action detail**: The JSONL ledger (`habits-history.jsonl`) is
  append-only. Cache invalidation means: on next agent run, the reconciler's
  source-of-truth for `done` is the conflict-event log's most recent
  `resolution_decision: accepted_vikunja` value, not the stale JSONL entry.
  Implementation must decide whether the reconciler reads the conflict-event log
  or whether the conflict-event log's `update` phase directly appends a corrective
  entry to the domain JSONL. The latter is cleaner (single source of truth remains
  the domain JSONL).
- **Evidence**: RQ-1 confirmed `done` and `done_at` are first-class task fields
  (evidence-log row `2026-06-03T23:51:00Z`, citation `vikunja-api-tasks-all`).
  RQ-2 confirmed habits TP-01/TP-09 write `done` (citations
  `code-scripts-habits-record-completion`, `code-scripts-escalation-record`).

### Task layer (use cases b, c, e, f, g)

- **Primary detection**: `GET /tasks/all?updated_since=<ts>` covers field changes (c,
  f, g) and is the primary vehicle. Deletion (b) requires a supplementary probe:
  when a task known to Felix is *absent* from the `updated_since` response for N
  consecutive cycles, Felix issues `GET /tasks/{id}` to confirm 404. N = 3 cycles
  (15 minutes) is a reasonable confirmation window before marking as deleted.
- **Stable identifier**: `task.id` (integer) is the anchor for all task-layer
  operations (RQ-1 § 4 verdict). `project_id` changes (use cases c, e) are
  detected because the `project_id` field is included in the task response body.
- **Evidence**: RQ-1 `updated_since` probe confirmed it returns full task objects
  including `project_id` and `title` (evidence-log row `2026-06-03T23:51:00Z`,
  citation `vikunja-api-tasks-updated-since`).

### Project layer (use cases c, d, e, f)

- **Primary detection**: Project-layer changes are NOT surfaced by `updated_since`
  (that endpoint is task-scoped). Project-layer polling requires a full
  `GET /projects` per cycle (14 projects in the current instance;
  evidence-log row `2026-06-03T23:51:00Z`, citation `vikunja-api-projects`).
  At 14 projects, this is a single lightweight request per cycle — not a
  performance concern.
- **New project detection (d, e)**: project `id` absent from Felix's project
  cache appears in the `GET /projects` response. This is a structural-change
  detection at the project layer.
- **Rename detection (f)**: `title` field in `GET /projects` response differs from
  Felix's cached `title` for that `project.id`. Stable identifier is `project.id`
  (same stability model as `task.id` — RQ-1 § 3 confirms `id` is immutable on
  projects; `title` can change without changing `id`).
- **Evidence**: RQ-2 TP-02/TP-03/TP-04 all perform `GET /projects` reads
  (evidence-log row `2026-06-03T23:51:00Z`, citations
  `code-scripts-habits-reconcile-completions`, `code-scripts-habits-query-active-v2`,
  `code-scripts-habits-set-due-dates`).

---

## 4. NFR-002 Enforcement (T010)

**NFR-002 requirement**: every use-case worst-case latency ≤ 5 minutes.

### Latency Analysis

**Polling cadence**: 5 minutes.

**Worst-case latency per use case** = time between when the operator action occurs
and when Felix's cache reflects the correct state. Under a 5-minute poll cadence:

- **Absolute worst case**: operator action occurs 1 second after a poll cycle completes.
  The next poll occurs 5 minutes later. Detection latency = ~5 minutes.
- **Expected average case**: operator action is uniformly distributed across the
  poll interval. Expected detection = 2.5 minutes.
- **Processing latency** (diff + classify + emit + update): Felix-side processing
  of the `updated_since` response is deterministic Python — sub-second for the
  current scale (≤100 tasks). Not a contributor to the 5-minute budget.
- **`updated_since` anchor drift**: if Felix's `last_polled_utc` pointer drifts
  (e.g., due to clock skew on write timestamps — noted in RQ-1 § Deferred), there
  could be a missed-cycle gap. Implementation must validate that `updated_since`
  returns tasks consistently and handle the skew case explicitly.

### Verdict per use case

| Use case | Worst-case latency | Meets NFR-002 (≤5 min) | Notes |
|---|---|---|---|
| (a) Status change | ≤ 5 min | Yes | `updated_since` returns `done`/`done_at` changes |
| (b) Task deleted | ≤ 15 min (3-cycle confirmation) | **Gap: 15 min > 5 min** | See discussion below |
| (c) Task moved | ≤ 5 min | Yes | `project_id` in task body; `updated_since` surfaces it |
| (d) New project | ≤ 5 min | Yes | `GET /projects` per cycle |
| (e) Bulk tasks moved | ≤ 5 min | Yes | Each moved task in `updated_since` results |
| (f) Rename | ≤ 5 min | Yes | Title in task/project body |
| (g) Due date set | ≤ 5 min | Yes | `updated_since` returns `due_date` change |

### Use Case (b) — Deletion Detection Gap

**Finding**: Task deletion is not surfaced by `updated_since`. A deleted task does
not appear in `GET /tasks/all` responses at all — there is no "soft-delete" or
tombstone mechanism observed in Vikunja v0.24.6 (RQ-1 § Deferred — write-path
probes were out of scope per C-006). Reliable deletion detection requires a
supplementary confirmation: absent from N consecutive cycles, then probe
`GET /tasks/{id}` to confirm 404.

**With N=3 cycles (15 min)**: worst-case latency = 15 minutes. This **exceeds
NFR-002 (5 min)**.

**Tension documented** (per prompt: do NOT silently shrink latency):

The deletion use case cannot achieve 5-minute worst-case latency under a polling
architecture unless Vikunja provides a tombstone/event API or webhook delivery for
deletes. Options:
1. Accept 15-minute deletion detection latency and document as a design exception.
   Rationale: task deletion is an infrequent operation; the downstream risk of
   Felix erroring on a stale `task_id` for 15 minutes is low compared to the
   architectural cost of adding a webhook channel for this single case (C-001 locks
   polling-only).
2. Reduce N to 1 cycle: probe `GET /tasks/{id}` on every task absent from
   `updated_since`. This adds N per-task HTTP GETs per cycle (where N = number of
   Felix-tracked tasks). At 15 tracked tasks, this is 15 extra GETs per 5-minute
   cycle — acceptable at Felix's scale but adds polling load.
3. File a sub-issue to investigate Vikunja soft-delete or event log API
   (currently `webhooks_enabled=true` but unconfigured — RQ-1 § 7).

**Recommendation gap**: Option 1 (accept 15-min for deletes) is the pragmatic
choice. WP03's recommendation should document this explicitly. The `rq-4` table
above marks use case (b) as a **Gap** with worst-case 15 min. This is the only
NFR-002 miss across all 7 use cases.

---

## 5. Evidence CSV Rows (WP02 additions)

The following evidence-log rows are added (see CSV file in `kitty-specs/research/`):

- Row for Epic #507 use-case extraction (source `issue-507`) — WP02 load-bearing claim.
- Rows for each use-case layer assignment.
- Row for deletion-detection gap.

---

## 6. Limitations

- **In-prompt agent callsites** (RQ-2 Note 2): The escalation and tasker agents
  issue Vikunja queries in-prompt, not via versioned Python scripts. Their latency
  budget is dependent on the OpenClaw agent's cron cadence (not verified in this
  research). If those agents run on a >5-minute cadence, their effective sync
  latency may exceed NFR-002 even after the sync layer is implemented.

- **Deletion confirmed via API probe**: The claim that Vikunja does not provide a
  tombstone API is based on absence of evidence (no `events`, `audit-log`, or
  soft-delete mechanism was observed in RQ-1 probes). The write-path was out of
  scope (C-006). Implementation must verify this claim before committing to the
  N-cycle confirmation pattern.

- **Project layer `updated_since` gap**: The `updated_since` parameter applies to
  tasks only. Projects must be fetched in full on every cycle. If the Vikunja instance
  grows to hundreds of projects, per-cycle full project enumeration may become
  expensive. Not a concern at 14 projects.

---

## 7. Deferred to Implementation

- Confirm whether `GET /tasks/all?updated_since=<ts>` includes tasks where only
  metadata fields (labels, `project_id`) changed — or only fields that trigger
  `updated` timestamp update. This affects detection reliability for use case (c).
- Verify deletion behavior on Vikunja v0.24.6 (does a DELETE trigger an `updated`
  entry in `updated_since`, or does it just remove the task?).
- Tune N-cycle confirmation window for deletion (balance between detection latency
  and per-cycle HTTP load).
- Design the corrective-entry write path: does the conflict-event log's `update`
  phase append a corrective entry to the domain JSONL, or does it write a side-channel
  override? The former is recommended (single source of truth).
