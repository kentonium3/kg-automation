# Data Model

**Mission**: `habits-native-repeat-jsonl-state-01KS0M59`
**Phase**: 1 (design)

This document defines the data entities, schemas, and shapes for the habits migration. References Phase 2 (#305) for the JSONL state log substrate.

---

## Entity 1 — Vikunja habit task

Per Vikunja v0.24.6 task model (see `docs/design/research/vikunja-task-model-research.md` for full field inventory). Fields relevant to Phase 3:

| Field | Type | Pre-Phase-3 | Post-Phase-3 (daily) | Post-Phase-3 (MWF) | Notes |
|---|---|---|---|---|---|
| `id` | int | 14..20, 65 | unchanged | new IDs assigned by Vikunja | The 8 production habits have IDs 14, 15, 16, 17, 18, 19, 20, 65 per the research doc. |
| `title` | str | varies | unchanged | "Strength training — Mon/Wed/Fri" | The MWF tasks are 3 distinct tasks with explicit day-of-week titles. |
| `repeat_after` | int (seconds) | 0 | 86400 | 604800 | The core PATCH target. |
| `repeat_mode` | int (0/1/2) | 0 | 0 (interval) | 0 (interval) | All Phase 3 schedules use interval mode. |
| `done` | bool | varies | unchanged | false | The retired workout task ends up `done=true` (its retirement marker). New tasks start `done=false`. |
| `due_date` | str (ISO 8601 datetime) | varies | unchanged | next Mon/Wed/Fri 08:00 UTC | Computed by `migrate_schedule.py` at run time (see research D9). |
| `is_archived` | bool | false | unchanged | false | Phase 3 does NOT archive any task. The retired workout stays in the active task list with `done=true`. |
| `created_by.username` | str | "kent" | unchanged for existing tasks | "felix-bot" for new tasks | Per ADR Q6 + Phase 1 rotation. New tasks created via Phase 3 attribute to felix-bot. |
| `project_id` | int | varies | unchanged | inherited from retired workout task | The MWF strength-training tasks land in the same project as the retired workout (typically the "personal" or "habits" project). |
| `labels` | list[Label] | varies | unchanged | inherited from retired workout task | Same label set (e.g., `["personal", "strength-training"]`). |

### Why the retired workout is `done=true` (not archived or deleted)

Per C-004:
- **Delete**: would lose the `[Felix]` comment history. ADR Q3-D requires comments as the UI-visible mirror; pre-Phase-3 completions are recorded there.
- **Archive**: per Vikunja API research, `is_archived` is a per-project field, not per-task. There's no clean "archive this task" operation.
- **`done=true` with `repeat_after=0`**: marks the task as completed forever (no auto-advance because `repeat_after` stays 0). The task remains visible in the project but doesn't surface on the today-view. History is preserved.

---

## Entity 2 — habits-schedule.yaml

Operator-edited config file at `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml`. Read by `migrate_schedule.py`. Defines the Phase 3 schedule changes.

### Schema

```yaml
# Required top-level key
mission_id: "01KS0M59313RF0WVJZTXYDJC6C"        # Sanity check: must match meta.json

# Required top-level list of operations
operations:
  # ── op: patch — modify an existing task's schedule
  - op: patch
    task_id: <int>                              # Required: Vikunja task ID
    target:
      repeat_after: <int>                       # Required: positive integer
      repeat_mode: <0|1|2>                      # Required
    notes: <str>                                # Optional: human-readable rationale

  # ── op: retire — mark an existing task done=true (no schedule change)
  - op: retire
    task_id: <int>                              # Required
    notes: <str>                                # Optional

  # ── op: create — create a new task
  - op: create
    schedule:
      repeat_after: <int>                       # Required: positive integer
      repeat_mode: <0|1|2>                      # Required
    attributes:
      title: <str>                              # Required
      due_date: <str ISO 8601>                  # Optional (helper computes default if absent)
      project_id: <int>                         # Optional (defaults to retired-task project_id during this mission)
      labels: <list[int|str]>                   # Optional (defaults to retired-task labels)
    notes: <str>                                # Optional
```

### Validation rules (enforced by `migrate_schedule.py` before any HTTP call)

- `mission_id` must equal the value in `meta.json` (prevents accidental cross-mission application).
- Every operation has a recognized `op` value.
- `patch` and `retire` operations have a non-null `task_id` (positive int).
- `create` operations have `attributes.title` non-empty.
- All `schedule.repeat_after` values are positive integers.
- All `schedule.repeat_mode` values are in `{0, 1, 2}`.
- `due_date` (if present) parses as ISO-8601 with timezone offset.

On validation failure: stderr message naming the operation index + field + violation; exit 2.

### Expected Phase 3 content

```yaml
mission_id: "01KS0M59313RF0WVJZTXYDJC6C"

operations:
  # 7 daily PATCHes — IDs filled in during plan-phase lookup
  - op: patch
    task_id: 14
    target:
      repeat_after: 86400
      repeat_mode: 0
    notes: "Daily habit: Wake at 5:00 AM"
  # ... 6 more daily patches (IDs from the 14, 15, 16, 18, 19, 20, 65 set, minus the workout)

  # 1 retire — the workout task (ID identified by identify_workout_task.py)
  - op: retire
    task_id: 17       # placeholder; will be replaced by lookup output
    notes: "Retire single workout task; replaced by 3 weekly MWF tasks below"

  # 3 creates — Mon/Wed/Fri strength training
  - op: create
    schedule:
      repeat_after: 604800
      repeat_mode: 0
    attributes:
      title: "Strength training — Monday"
      # due_date computed at run time by migrate_schedule.py
  - op: create
    schedule:
      repeat_after: 604800
      repeat_mode: 0
    attributes:
      title: "Strength training — Wednesday"
  - op: create
    schedule:
      repeat_after: 604800
      repeat_mode: 0
    attributes:
      title: "Strength training — Friday"
```

---

## Entity 3 — Rollback snapshot

Lives at `/data/services/openclaw/state/habits-pre-phase3-snapshot.json` after migration runs. Written by `migrate_schedule.py` BEFORE any mutation.

### Schema

```json
{
  "schema_version": "1",
  "mission_id": "01KS0M59313RF0WVJZTXYDJC6C",
  "mission_slug": "habits-native-repeat-jsonl-state-01KS0M59",
  "captured_at": "2026-05-20T12:00:00+00:00",
  "config_file_sha256": "<sha256 of the habits-schedule.yaml that was applied>",

  "before_states": [
    {
      "task_id": 14,
      "before": {
        "repeat_after": 0,
        "repeat_mode": 0,
        "done": false,
        "due_date": "2026-05-20T08:00:00Z",
        "is_archived": false,
        "done_at": null,
        "title": "Wake at 5:00 AM"
      },
      "intended_op": "patch"
    }
    // ... entries for each PATCH'd and retired task
  ],

  "created_tasks": [
    {
      "task_id": 100,
      "title": "Strength training — Monday",
      "created_at": "2026-05-20T12:00:01+00:00"
    }
    // ... up to 3 entries for the new MWF tasks
  ],

  "applied_changes": [
    {"task_id": 14, "op": "patch", "applied_at": "2026-05-20T12:00:02+00:00", "result": "success"},
    {"task_id": 17, "op": "retire", "applied_at": "2026-05-20T12:00:03+00:00", "result": "success"},
    {"task_id": 100, "op": "create", "applied_at": "2026-05-20T12:00:04+00:00", "result": "success"}
    // ... one entry per applied operation, in order
  ]
}
```

### Usage

- `migrate_schedule.py` reads the schedule.yaml, captures `before_states` for every task it intends to touch, then iterates `operations`. On each successful HTTP call, appends to `applied_changes` and (for creates) appends to `created_tasks`.
- On failure mid-batch: the snapshot file is already on disk with `before_states` and partial `applied_changes`. Operator can run `migrate_schedule.py --rollback --snapshot-file <path>` to reverse.
- Rollback iterates `applied_changes` in REVERSE order: for each entry, replay the inverse operation (PATCH back to BEFORE for patches; PATCH `done=false` for retires; DELETE for creates).

---

## Entity 4 — JSONL state log entry (inherited from Phase 2)

Per `scripts/common/state_log.py` and `docs/design/architecture/data/agent-state-log-schema.md`. Phase 3 writes habits-domain entries with these `state` values per the locked-in enum:

| `state` value | Semantic meaning |
|---|---|
| `complete` | Task completed for this date (auto-advance triggered, comment mirror written, JSONL recorded) |
| `incomplete` | Task NOT done for this date (Kent declined / negative WhatsApp / missed window) |
| `skipped` | Intentionally skipped (holiday, illness, travel — non-failure) |

### Phase 3-specific `source` values

| `source` value | When |
|---|---|
| `whatsapp` | WhatsApp completion signal during morning check-in (Phase 5+ callers) |
| `vikunja-ui` | Backfill from a Vikunja UI completion (reconcile_completions detected) |
| `cron` | Catch-all for automation-driven writes outside WhatsApp/UI |
| `manual` | Operator-driven (e.g., correcting a missed log entry post-hoc) |

Phase 3 helpers write `source=whatsapp` (record_completion), `source=vikunja-ui` (reconcile backfills), or `source=manual` (operator overrides). Phase 4 (#307) will use `source=backfill` (or similar) for the historical-comment ingestion.

### Example records written by Phase 3 helpers

**record_completion write** (WhatsApp signal):
```json
{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-20","state":"complete","source":"whatsapp","note":null,"timestamp":"2026-05-20T11:05:11+00:00"}
```

**reconcile_completions backfill**:
```json
{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-19","state":"complete","source":"vikunja-ui","note":null,"timestamp":"2026-05-20T11:00:03+00:00"}
```

Note: `date` is the day the completion was FOR; `timestamp` is when this record was written. For backfills, `date` < `timestamp` is the norm.

---

## Entity 5 — Felix comment (UI mirror)

Per ADR Q3-D, every completion records a `[Felix]` comment as the UI-visible mirror. Format:

```
[Felix] <YYYY-MM-DD> | <state>
```

Optional 3rd segment for notes:

```
[Felix] <YYYY-MM-DD> | <state> | <free-form note>
```

Examples:
- `[Felix] 2026-05-20 | complete`
- `[Felix] 2026-05-19 | skipped | travel — no gym access`

Written via `PUT /api/v1/tasks/<id>/comments` (not POST — see Verified API gotchas G4). Attribution is `author.username` (not `created_by` — see G3).

---

## Forward compatibility

- Adding new `source` values: non-breaking. Phase 2 state_log accepts any non-empty string for `source`.
- Adding new `state` values per ADR-0002 Q5-C requires a PR to `scripts/common/state_log_schema.py` (the per-domain enum is canonical).
- Adding new habit tasks beyond the 11 in scope: operators add a Vikunja UI task, then run `migrate_schedule.py` with a new operations list — the schedule.yaml is mission-scoped here but the helper is generic enough to use on future schedule changes.
- The retired workout task can be reactivated later by manual UI un-tick + PATCH `repeat_after=X`, but the recommended path is to add new tasks rather than reuse.
