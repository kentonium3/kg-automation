# Habits native repeat + JSONL state — Specification

**Mission**: `habits-native-repeat-jsonl-state-01KS0M59`
**Mission ID**: `01KS0M59313RF0WVJZTXYDJC6C`
**Mission type**: software-dev
**Source**: GitHub issue [#306](https://github.com/kentonium3/issues/306) (Phase 3 of ADR-0002)
**Risk tier**: 2 (Application / State — Restic snapshot required)
**Created**: 2026-05-19

---

## Overview

Phase 3 of ADR-0002 — build the new habits code paths alongside the old, with the cron still running the old flow until Phase 5 cutover (#308). Five distinct deliverables plus production-state PATCHes on Vikunja habit tasks.

The core motivation: the current habits subsystem uses "completion = dated `[Felix]` comment" semantics on tasks with `repeat_after=0`. This loses Vikunja's native repeat behavior, requires an LLM parser at the agent layer to interpret completion, and cannot natively encode day-of-week patterns. The 2026-05-19 morning check-in surfacing a workout task on a Tuesday (Kent's schedule is MWF) is a representative failure of this architecture.

Per ADR-0002 Q1, Q2, Q3-D, Q7, Q8: native `repeat_after` becomes canonical for "when this task is due"; `done=true` is canonical for "completed today" (triggering Vikunja's auto-advance); the per-domain JSONL log built in Phase 2 (#305) is canonical history.

This mission builds the new path. The cron does NOT switch over in this mission — that's Phase 5 (#308).

---

## User Scenarios & Testing

### Primary actors

- **Kent** (operator) — runs the migration helper to PATCH production task state and review the rollback substrate
- **felix-admin-habits agent** (runs as claude on office2) — future consumer of the new scripts after Phase 5 cutover
- **Kent again, via Vikunja UI** — may tick habit completions directly in the UI; the new reconcile path detects + backfills these to JSONL

### Scenario 1 — Operator runs schedule migration (Tier 2 production change)

Kent confirms a Restic snapshot is current (Tier 2 pre-flight) and invokes the config-driven migration helper. The helper reads `kitty-specs/<mission>/habits-schedule.yaml` describing the intended schedule for each habit task. Helper persists the BEFORE state of every affected task to `/data/services/openclaw/state/habits-pre-phase3-snapshot.json`. Then applies the configured changes: 7 daily PATCHes to set `repeat_after=86400, repeat_mode=0`; the workout task is marked `done=true` to retire it; 3 new tasks (Mon/Wed/Fri strength training) are created with `repeat_after=604800, repeat_mode=0`. Operator confirms via Vikunja `GET /tasks/<id>` for each touched task.

### Scenario 2 — Agent records a completion (future Phase 5 callers; not live yet)

The agent receives a positive WhatsApp completion signal for habit task 14 ("Wake at 5:00 AM"). It invokes `record_completion.py` with `task_id=14, date=2026-05-20, state=complete, source=whatsapp`. The helper performs three writes atomically:
1. `POST /api/v1/tasks/14` with `done=true` (triggers Vikunja's auto-advance)
2. `PUT /api/v1/tasks/14/comments` with body `[Felix] 2026-05-20 | complete` (UI-visible mirror)
3. `state_log.append("habits", {task_id: 14, date: "2026-05-20", state: "complete", source: "whatsapp", ...})` (canonical JSONL history)

If any of the three fails, the helper exits non-zero with a clear stderr message naming the failed step. The helper is idempotent on `(task_id, date, state)` — re-invocation with the same tuple is a no-op (per Phase 2 state_log contract).

### Scenario 3 — Backfill from Vikunja UI completion

Kent ticks the "Wake at 5:00 AM" task done in the Vikunja UI at 2026-05-21T11:00:00Z. The next morning, `reconcile_completions.py` runs at the start of the check-in tick. It enumerates tasks with `done=true` whose `done_at` date has no corresponding JSONL entry for that task+date. It appends a backfill record: `{task_id: 14, date: "2026-05-21", state: "complete", source: "vikunja-ui", timestamp: <reconcile time>}`.

### Scenario 4 — Drift detection

Reconcile also detects the inverse drift: tasks where JSONL says `state: complete` for today's date but Vikunja currently shows `done=false`. This would indicate either Kent un-ticking in the UI or a write race. Reconcile flags it (stdout log entry) but does NOT auto-resolve — surface to the operator.

### Scenario 5 — Phase 5 dry-run (smoke test of new query/exclude variants)

An operator (Kent or a canary cron) invokes the new v2 variants standalone (not via the agent): `query_active_habits_v2.py` returns the list of tasks with `due_date <= now/d AND done = false`. `exclude_completed_v2.py` (given that list) reads the JSONL log and returns the subset where there's no `complete` JSONL entry for today's date. This is the Phase 5 verification gate — the new variants are exercised standalone before AGENTS.md is updated to use them.

### Scenario 6 — Operator-driven rollback (NO-GO recovery)

If any post-PATCH verification fails, operator invokes `migrate_schedule.py --rollback --snapshot-file /data/services/openclaw/state/habits-pre-phase3-snapshot.json`. Helper re-PATCHes each task back to its BEFORE state, un-marks the workout task as not-done, and deletes the 3 newly-created Mon/Wed/Fri tasks (by ID). Verifies each task matches its BEFORE record. Exits 0 only on full rollback success.

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | A schedule-migration helper at `scripts/habits/migrate_schedule.py` accepts a config file describing per-task intended schedule (target schema: list of `{task_id, repeat_after, repeat_mode, ...}` operations, plus optional `create_new` entries for newly-introduced tasks like the MWF strength-training trio). | Active |
| FR-002 | The migration helper captures the BEFORE state of every task it touches (current `repeat_after`, `repeat_mode`, `done`, `due_date`, `is_archived`, `done_at`) to a rollback-substrate JSON file at `/data/services/openclaw/state/habits-pre-phase3-snapshot.json` BEFORE applying any change. | Active |
| FR-003 | The migration helper supports `--dry-run`: prints the planned changes (with BEFORE/AFTER deltas) and the snapshot path, but issues zero PATCH/POST/DELETE calls. | Active |
| FR-004 | The migration helper supports `--rollback --snapshot-file <path>`: reverses every change recorded in the snapshot. After successful rollback, each affected task matches its BEFORE state, and any newly-created tasks (recorded in snapshot) are deleted. | Active |
| FR-005 | The migration helper authenticates as `felix-bot` (reading `/data/services/openclaw/secrets/vikunja-api`). All Vikunja API writes attribute to `felix-bot`. | Active |
| FR-006 | A completion helper at `scripts/habits/record_completion.py` performs three writes atomically per ADR Q3-D: (a) POST `/tasks/<id>` with `done=true`, (b) PUT `/tasks/<id>/comments` with `[Felix] <date> \| <state>` body, (c) `state_log.append("habits", record)`. If any write fails after the first succeeds, the helper exits non-zero with a stderr message naming the failed write; it does NOT attempt automatic compensation. | Active |
| FR-007 | `record_completion.py` is idempotent on `(task_id, date, state)`. Re-invocation with the same tuple performs no destructive Vikunja calls and the state_log dedup ensures no duplicate JSONL line. | Active |
| FR-008 | A reconciliation helper at `scripts/habits/reconcile_completions.py` enumerates all active habit tasks (`is_archived=false`). For each task: if `done=true`, derive the date from `done_at`; if no JSONL entry exists for `(task_id, date)` in the habits log, append a backfill entry with `source=vikunja-ui` and `timestamp` = current UTC. | Active |
| FR-009 | `reconcile_completions.py` also detects drift in the opposite direction: tasks where the JSONL has `state=complete` for today's date but Vikunja currently shows `done=false`. These are reported on stdout as warnings (one line per drift) but NOT auto-resolved. | Active |
| FR-010 | A new variant at `scripts/habits/query_active_habits_v2.py` returns the list of habit tasks active for today using Vikunja's native filter expression `due_date <= now/d AND done = false`. Original `query_active_habits.py` is NOT modified. | Active |
| FR-011 | A new variant at `scripts/habits/exclude_completed_v2.py` accepts a list of active habit tasks (from query_active_habits_v2 or equivalent) and returns the subset that have no `state=complete` JSONL entry for today's date, via `state_log.read("habits", task_id=<id>, date=<today>)`. Original `exclude_completed.py` is NOT modified. | Active |
| FR-012 | `kitty-specs/<mission>/habits-schedule.yaml` is the canonical input for the migration helper. Schema: a top-level list of operations, each with `{op: patch\|create\|retire, task_id?: int, schedule: {repeat_after: int, repeat_mode: int}, attributes?: {...}}`. The 8 production habit tasks (IDs 14-20, 65) and the 3 new MWF tasks are all expressed in this file. | Active |
| FR-013 | After successful migration, `docs/design/architecture/data/data-flows.json` reflects the new write path (habits agent → state_log → habits-history.jsonl) AND the read path (exclude_completed_v2 → state_log.read). Existing comment-write path stays documented (it remains live until Phase 5). `docs/design/architecture/data/service-inventory.json` registers the new scripts under `scripts/habits/`. | Active |
| FR-014 | The agent's `AGENTS.md` workspace file is NOT modified in this phase. The cron continues to invoke the old scripts. Verified by `git diff` showing zero changes to `/home/claude/.openclaw/agents/felix-admin-habits/AGENTS.md` between Phase 3 merge and Phase 5 start. | Active |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | The migration helper's BEFORE-state capture completes within 30 seconds for 12 tasks (the 8 existing + 3 new + 1 retired = 12 touchpoints). | < 30s wall-clock | Active |
| NFR-002 | A single `record_completion.py` invocation (three writes + idempotency check) completes within 5 seconds on a healthy office2 / Vikunja pairing. | < 5s p95 | Active |
| NFR-003 | `reconcile_completions.py` completes within 60 seconds across all 10 active tasks (8 existing daily after retiring workout, +3 MWF — though MWF will only be due 3 days a week, reconcile still examines them all). | < 60s wall-clock | Active |
| NFR-004 | Rollback (via `migrate_schedule.py --rollback`) completes within 5 minutes (matches ADR-0002 SC-005 budget). | < 5min wall-clock | Active |
| NFR-005 | All new code modules + tests have ≥ 85% line + branch coverage (slightly lower than Phase 2's 90% because integration tests against a live Vikunja stub are harder to write deterministically; pure-logic modules should still target ≥90%). | ≥ 85% | Active |
| NFR-006 | Net zero new third-party Python dependencies. PyYAML is the only exception — it's already in the repo's `requirements.txt` for spec-kitty / other helpers, so reusing it for `habits-schedule.yaml` parsing introduces no new dependency. | 0 new deps | Active |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | **Old code path remains live and unchanged** until Phase 5 (#308) cutover. The cron continues invoking the existing `query_active_habits.py` and `exclude_completed.py`. New variants are `_v2.py` siblings. | Active |
| C-002 | **No modifications to `AGENTS.md`** (the felix-admin-habits agent's workspace file). Phase 5 owns that change. | Active |
| C-003 | All Vikunja API writes MUST authenticate as `felix-bot` (per ADR-0002 Q6). The migration helper, record_completion.py, and reconcile_completions.py all read the felix-bot token from `/data/services/openclaw/secrets/vikunja-api`. | Active |
| C-004 | The retired workout task is marked `done=true` rather than deleted. This preserves its existing `[Felix]` comment history. The 3 new strength-training tasks get fresh Vikunja task IDs. | Active |
| C-005 | The state log is the canonical history per ADR Q3-D. The `[Felix]` comment is the UI-visible mirror. Both are written by `record_completion.py` on the same invocation; if the helper is interrupted between writes, reconcile is responsible for surfacing the partial state. | Active |
| C-006 | The migration helper, record_completion, reconcile_completions, and the two `_v2.py` variants MUST be callable from both Python (in-process import) and CLI (via Bash exec, matching the Phase 2 `state_log` pattern). | Active |
| C-007 | Tier 2 pre-flight protocol applies: Restic snapshot within 24h MUST be confirmed before invoking the migration helper without `--dry-run`. | Active |

---

## Key Entities

### Habit task (Vikunja-side)

The 8 production tasks (IDs 14, 15, 16, 17, 18, 19, 20, 65) and the 3 new strength-training tasks. Per Vikunja's task model:

| Field | Pre-Phase-3 value | Post-Phase-3 (daily habits) | Post-Phase-3 (MWF) |
|---|---|---|---|
| `repeat_after` | 0 | 86400 (1 day) | 604800 (1 week) |
| `repeat_mode` | 0 | 0 (interval) | 0 (interval) |
| `done` | varies | unchanged | false (new) |
| `due_date` | varies | unchanged | next Mon/Wed/Fri |
| `is_archived` | false | unchanged | false |

The retired workout task: `done=true` after Phase 3 (and stays that way; Vikunja's auto-advance does NOT re-flip it because we are NOT setting its repeat_after to a positive value).

### habits-schedule.yaml (mission-scoped config)

Lives at `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml`. Concrete schema:

```yaml
operations:
  - op: patch
    task_id: 14
    target:
      repeat_after: 86400
      repeat_mode: 0
    notes: "Daily habit: Wake at 5:00 AM"
  # ... 6 more daily patches (15, 16, 18, 19, 20, 65) ...

  - op: retire
    task_id: 17                       # The current workout task (TBD — confirm during plan/lookup)
    notes: "Retire single workout task; replaced by 3 weekly MWF tasks below"

  - op: create
    schedule:
      repeat_after: 604800
      repeat_mode: 0
    attributes:
      title: "Strength training — Monday"
      due_date: "2026-05-25T08:00:00+00:00"
      project_id: <inherited from retired workout task>
      labels: <inherited from retired workout task>
  - op: create
    schedule:
      repeat_after: 604800
      repeat_mode: 0
    attributes:
      title: "Strength training — Wednesday"
      due_date: "2026-05-27T08:00:00+00:00"
      project_id: <inherited>
      labels: <inherited>
  - op: create
    schedule:
      repeat_after: 604800
      repeat_mode: 0
    attributes:
      title: "Strength training — Friday"
      due_date: "2026-05-29T08:00:00+00:00"
      project_id: <inherited>
      labels: <inherited>
```

The exact workout task ID is TBD during the plan phase (operator runs a lookup query against Vikunja). Schedule values + due_dates are confirmed during planning.

### Rollback substrate (BEFORE snapshot)

```json
{
  "captured_at": "2026-05-20T12:00:00+00:00",
  "mission_slug": "habits-native-repeat-jsonl-state-01KS0M59",
  "tasks": [
    {
      "task_id": 14,
      "before": {"repeat_after": 0, "repeat_mode": 0, "done": false, "due_date": "2026-05-20T08:00:00Z", "is_archived": false, "done_at": null}
    }
  ],
  "created_tasks": [
    {"task_id": 100, "title": "Strength training — Monday", "created_at": "2026-05-20T12:00:00+00:00"}
  ]
}
```

### JSONL state log (per Phase 2)

The `habits-history.jsonl` file at `/data/services/openclaw/state/habits-history.jsonl`. Receives entries from `record_completion.py` (forward writes) and from `reconcile_completions.py` (backfills).

---

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | After migration runs successfully, all 7 daily habit tasks have `repeat_after=86400` and `repeat_mode=0` (verified by GET on each). |
| SC-002 | The retired workout task has `done=true` AND its old `[Felix]` comment history is intact (no deletion). |
| SC-003 | 3 new strength-training tasks exist with `repeat_after=604800`, distinct task IDs, due_dates on the next Mon/Wed/Fri respectively, inheriting project + labels from the retired workout task. |
| SC-004 | A `record_completion.py` invocation against a sandbox task (NOT production) successfully performs the three writes, and the resulting JSONL line matches the Phase 2 schema exactly. |
| SC-005 | `reconcile_completions.py` correctly backfills a Vikunja-UI completion (verified by Kent ticking a habit done in the UI, then running reconcile, then observing the JSONL backfill entry with `source=vikunja-ui`). |
| SC-006 | `query_active_habits_v2.py` standalone invocation returns the correct active-today set (verified by spot-comparison against the old script's output on a day where both should agree). |
| SC-007 | `exclude_completed_v2.py` standalone invocation correctly omits tasks with today's JSONL `complete` entry. |
| SC-008 | Rollback from the snapshot completes within 5 minutes and leaves every task in its BEFORE state. |
| SC-009 | The cron's morning check-in runs identically before and after Phase 3 merge (this confirms C-001). |

---

## Assumptions

1. The Vikunja API token at `/data/services/openclaw/secrets/vikunja-api` is the `felix-bot` token (post Phase 1 rotation, 2026-05-17). Confirmed.
2. The state_log library from Phase 2 (#305) is on `main` and importable from `scripts.common`. Confirmed (commit 231e880).
3. The current 8 habit tasks all have `repeat_after=0, repeat_mode=0` per `docs/design/research/vikunja-task-model-research.md`. The migration helper SHOULD verify this in pre-flight; if any task has a different baseline, the helper should refuse to run (operator manual intervention required).
4. The workout task's exact ID is unknown to this spec; it will be identified during plan phase via a Vikunja query. The spec assumes ONE such task exists with the title "Workout" or equivalent.
5. The Phase 5 cron-cutover mission (#308) will update AGENTS.md. This spec assumes that mission exists and will execute after Phase 3 + Phase 4 (#307).
6. Operator (Kent) is available to run the Tier 2 pre-flight + invoke the migration helper interactively. The mission does NOT attempt to auto-trigger production state mutations via spec-kitty's implement-review loop.

---

## Out of scope

- Cron cutover / AGENTS.md update — Phase 5 (#308)
- Backfill of `habits-history.jsonl` from the existing `[Felix]` comment history on the 8 production tasks — Phase 4 (#307)
- Escalation migration to JSONL — Phase 6 (#309)
- Tasker (enrichment) migration to JSONL — Phase 7 (#310)
- Webhook receiver per ADR Q4 — deferred ADR-0002 Phase 8
- RRULE migration once upstream Vikunja PR #2032 lands — deferred ADR-0002 Phase 8
- Adding NEW habit tasks beyond the MWF strength-training trio (e.g., guitar practice) — operator-driven addition via the config-driven helper after Phase 3 merges
