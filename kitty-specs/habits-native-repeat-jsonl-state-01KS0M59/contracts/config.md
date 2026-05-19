# Contract — habits-schedule.yaml

**Mission**: `habits-native-repeat-jsonl-state-01KS0M59`
**File**: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/habits-schedule.yaml`

This is the canonical input to `migrate_schedule.py`. It is mission-scoped (lives in the kitty-specs dir, not in production config) because it describes the one-shot schedule change applied during this mission. Future schedule changes (adding guitar practice, etc.) would be a new mission with its own schedule.yaml or operator-driven additions via Vikunja UI.

---

## Top-level structure

```yaml
mission_id: <string ULID>   # MUST match meta.json mission_id
operations:                  # MUST be a list (can be empty for a no-op file)
  - <operation 1>
  - <operation 2>
  ...
```

If `mission_id` doesn't match `meta.json`, `migrate_schedule.py` refuses to run (exit 2). This prevents accidentally applying one mission's schedule against another's snapshot.

---

## Operation types

### `op: patch` — modify an existing task's schedule

```yaml
- op: patch
  task_id: <int>            # REQUIRED: positive integer Vikunja task ID
  target:                   # REQUIRED
    repeat_after: <int>     # REQUIRED: positive integer (seconds). 0 not allowed.
    repeat_mode: <0|1|2>    # REQUIRED
  notes: <str>              # OPTIONAL: human-readable rationale
```

**Semantics**: PATCH `/api/v1/tasks/<task_id>` with body `{repeat_after, repeat_mode}`. Other task fields untouched.

**Idempotency**: if the task already has the target values, the PATCH is skipped (helper logs "task <id> already matches target schedule"). Snapshot still records the BEFORE state.

### `op: retire` — mark an existing task `done=true`

```yaml
- op: retire
  task_id: <int>            # REQUIRED
  notes: <str>              # OPTIONAL
```

**Semantics**: PATCH `/api/v1/tasks/<task_id>` with body `{done: true}`. Implicitly relies on the task's existing `repeat_after=0` to prevent Vikunja's auto-advance from flipping it back. The helper verifies `repeat_after=0` in the BEFORE state and refuses to retire if not (because auto-advance would un-retire).

**Why not delete**: see data-model.md "Why the retired workout is done=true (not archived or deleted)".

### `op: create` — create a new task

```yaml
- op: create
  schedule:                 # REQUIRED
    repeat_after: <int>     # REQUIRED: positive integer
    repeat_mode: <0|1|2>    # REQUIRED
  attributes:               # REQUIRED
    title: <str>            # REQUIRED: non-empty
    due_date: <str>         # OPTIONAL: ISO-8601 datetime with timezone. Helper computes default if absent.
    project_id: <int>       # OPTIONAL: defaults to project_id of the most recent retired task in the same schedule.yaml
    labels: <list>          # OPTIONAL: defaults to labels of the most recent retired task
  notes: <str>              # OPTIONAL
```

**Semantics**: PUT `/api/v1/projects/<project_id>/tasks` (Vikunja's create-task endpoint is project-scoped) with body comprising schedule + attributes. The created task's ID is captured in the snapshot's `created_tasks` list.

**Default due_date computation** (when omitted from YAML):
- For weekly schedules (`repeat_after=604800`): next occurrence of the target weekday (Mon/Wed/Fri inferred from title) at 08:00 UTC.
- For daily schedules: tomorrow at 08:00 UTC.
- For other intervals: today + (repeat_after seconds) at 08:00 UTC.

**Default project_id and labels**: inherit from the most recent `retire` op in the same schedule.yaml (this Phase 3 case: workout task → 3 strength-training tasks share its project + labels).

---

## Full schema validation rules

Enforced by `migrate_schedule.py` BEFORE any HTTP call. Validation order:

1. **YAML parses**: load with `yaml.safe_load`. Parse errors → exit 2 with the YAML library's error message.
2. **Top-level keys**: `mission_id` (string) and `operations` (list) both required. `mission_id` must match `meta.json`.
3. **Each operation has `op`**: must be one of `{patch, retire, create}`. Unknown → exit 2 naming the operation index.
4. **`patch` and `retire` ops**: `task_id` required, type int, positive.
5. **`patch` and `create` ops**: `target` (or `schedule`) required, with `repeat_after` (positive int) and `repeat_mode` (in `{0, 1, 2}`).
6. **`create` ops**: `attributes.title` required, non-empty after strip.
7. **`due_date` (if present)**: parses via `datetime.fromisoformat()`, has timezone offset.
8. **No duplicate task_ids in `patch`/`retire` ops**: each task can be touched at most once per schedule.yaml.

On any validation failure: stderr message naming the operation index + field + violation; exit 2. No HTTP issued.

---

## Example: this mission's schedule.yaml (populated post-lookup)

```yaml
mission_id: "01KS0M59313RF0WVJZTXYDJC6C"

operations:
  # ── 7 daily PATCHes ──
  - op: patch
    task_id: 14
    target: {repeat_after: 86400, repeat_mode: 0}
    notes: "Daily habit: Wake at 5:00 AM"

  - op: patch
    task_id: 15
    target: {repeat_after: 86400, repeat_mode: 0}
    notes: "Daily habit: <title>"

  - op: patch
    task_id: 16
    target: {repeat_after: 86400, repeat_mode: 0}
    notes: "Daily habit: <title>"

  - op: patch
    task_id: 18
    target: {repeat_after: 86400, repeat_mode: 0}
    notes: "Daily habit: <title>"

  - op: patch
    task_id: 19
    target: {repeat_after: 86400, repeat_mode: 0}
    notes: "Daily habit: <title>"

  - op: patch
    task_id: 20
    target: {repeat_after: 86400, repeat_mode: 0}
    notes: "Daily habit: <title>"

  - op: patch
    task_id: 65
    target: {repeat_after: 86400, repeat_mode: 0}
    notes: "Daily habit: <title>"

  # ── 1 retire (workout task; ID filled in after identify_workout_task.py lookup) ──
  - op: retire
    task_id: 17       # placeholder — operator runs identify_workout_task.py to confirm
    notes: "Retire single workout task; replaced by 3 weekly MWF tasks below"

  # ── 3 creates (Mon/Wed/Fri strength training) ──
  - op: create
    schedule: {repeat_after: 604800, repeat_mode: 0}
    attributes:
      title: "Strength training — Monday"
      # project_id and labels inherited from workout task above
      # due_date computed as next Monday at 08:00 UTC

  - op: create
    schedule: {repeat_after: 604800, repeat_mode: 0}
    attributes:
      title: "Strength training — Wednesday"

  - op: create
    schedule: {repeat_after: 604800, repeat_mode: 0}
    attributes:
      title: "Strength training — Friday"
```

**Note**: the 8 daily task IDs are 14, 15, 16, 17, 18, 19, 20, 65 per the research doc. Item ordering above lists 14, 15, 16, 18, 19, 20, 65 as daily (skipping 17 which is the workout). The operator should confirm the workout task ID via `identify_workout_task.py` and update the placeholder before running `migrate_schedule.py`.

---

## Future evolution

The schedule.yaml format is intentionally generic: future habits-related schedule changes (adding guitar practice, switching a habit from daily to MWF, retiring a habit) can use this exact schema in a fresh schedule.yaml. The Phase 3 helper is the only implementation for now; future missions may either share the helper or fork it.

To add guitar practice after Phase 3 merges:

```yaml
# kitty-specs/<future-mission>/habits-schedule.yaml
mission_id: "<new mission id>"
operations:
  - op: create
    schedule: {repeat_after: 604800, repeat_mode: 0}
    attributes:
      title: "Guitar practice — Tuesday"
      project_id: <personal project>
      labels: ["personal", "music"]
```

Run `python3 -m scripts.habits.migrate_schedule --schedule <new file> --snapshot-out <new file>`. The helper would create the new task without touching anything else.
